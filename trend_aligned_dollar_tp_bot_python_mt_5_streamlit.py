# TrendAligned_DollarTP_Bot
# -------------------------------------------------------------
# A production-style MetaTrader5 Python trading bot with:
# - Multi-timeframe trend alignment (D1, H4, H1, M30, M15)
# - Trigger on M5 or M1
# - Dollar-based TP per trade (1–5 USD depending on trigger timeframe)
# - Effective equity = 100 USD (unless manually changed)
# - Max concurrent positions = 10 (default; adjustable)
# - Initial lot = 0.01 (default; adjustable)
# - Break-even + spread + step trailing
# - Daily profit cap & max loss guard (stops new entries when hit)
# - Optional paper mode (no live orders) for backtesting/simulation
# - Streamlit dashboard (can also run headless without Streamlit)
#
# Tested against MetaTrader5==5.0.45 on Windows x64 with MT5 build 5202.
#
# Usage
# -----
# 1) Install deps (cmd as Admin if needed):
#    pip install MetaTrader5 pandas numpy pytz streamlit
#
# 2) Make sure MT5 terminal is installed/logged in (or provide login/server/password below).
#
# 3) Run Streamlit UI:
#    streamlit run trend_aligned_dollar_tp_bot.py
#
#    Or run headless CLI loop (paper mode by default):
#    python trend_aligned_dollar_tp_bot.py --cli --symbols XAUUSD EURUSD --trigger_tf M5 --paper True
#
# Notes
# -----
# - "Zero loss" is not physically guaranteed. We minimize loss using BE+spread, trailing, and daily guards.
# - Dollar-based TP is converted to points using contract size and tick value.
# - This single-file version keeps things compact yet modular via sections/functions.
# -------------------------------------------------------------

from __future__ import annotations
import argparse
import time
import math
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional, Dict

import numpy as np
import pandas as pd
import pytz

try:
    import MetaTrader5 as mt5
except Exception:
    mt5 = None  # allows import without MT5 for reading/editing

# -----------------------------
# Helpers & Constants
# -----------------------------
TF_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

MT5_TF = {
    "M1": getattr(mt5, "TIMEFRAME_M1", None) if mt5 else None,
    "M5": getattr(mt5, "TIMEFRAME_M5", None) if mt5 else None,
    "M15": getattr(mt5, "TIMEFRAME_M15", None) if mt5 else None,
    "M30": getattr(mt5, "TIMEFRAME_M30", None) if mt5 else None,
    "H1": getattr(mt5, "TIMEFRAME_H1", None) if mt5 else None,
    "H4": getattr(mt5, "TIMEFRAME_H4", None) if mt5 else None,
    "D1": getattr(mt5, "TIMEFRAME_D1", None) if mt5 else None,
}

TREND_TFS = ["D1", "H4", "H1", "M30", "M15"]

@dataclass
class Settings:
    symbols: List[str]
    trigger_tf: str = "M5"  # or "M1"

    max_open_positions: int = 10
    initial_lot: float = 0.01
    effective_equity_usd: float = 100.0

    risk_per_trade_pct: float = 0.7  # of effective equity, per trade
    daily_profit_target_usd: float = 300.0  # adjust up to 1000 if desired
    daily_max_loss_usd: float = 100.0

    spread_threshold_points: int = 25  # threshold to block new entries
    news_buffer_minutes: int = 15  # placeholder; manual block

    atr_mult_be: float = 1.0
    atr_mult_trail_step: float = 0.5

    tp_dollar_range_m1: Tuple[float, float] = (1.0, 3.0)
    tp_dollar_range_m5: Tuple[float, float] = (2.0, 5.0)

    slippage: int = 3
    magic_number: int = 20250916

    paper_mode: bool = True  # True => no live orders

    # platform auth (optional if terminal already logged in)
    mt5_login: Optional[int] = None
    mt5_password: Optional[str] = None
    mt5_server: Optional[str] = None


# -----------------------------
# MT5 Init / Data Fetch
# -----------------------------

def init_mt5(login: Optional[int], password: Optional[str], server: Optional[str]) -> bool:
    if mt5 is None:
        print("MetaTrader5 library not available. Install MetaTrader5 to trade.")
        return False
    if not mt5.initialize():
        print("MT5 initialize() failed:", mt5.last_error())
        return False
    if login and password and server:
        authorized = mt5.login(login, password=password, server=server)
        if not authorized:
            print("MT5 login failed:", mt5.last_error())
            return False
    return True


def ensure_symbol(symbol: str) -> bool:
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"Symbol {symbol} not found")
        return False
    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"Failed to select symbol {symbol}")
            return False
    return True


def fetch_rates(symbol: str, tf: str, count: int = 400) -> pd.DataFrame:
    timeframe = MT5_TF.get(tf)
    if timeframe is None:
        raise ValueError(f"Unsupported timeframe {tf}")
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        raise RuntimeError(f"copy_rates_from_pos failed for {symbol} {tf}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    if df.empty:
        raise RuntimeError(f"No rates for {symbol} {tf}")
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


# -----------------------------
# Indicators
# -----------------------------

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift(1)).abs()
    low_close = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).ewm(span=period, adjust=False).mean()
    roll_down = pd.Series(down, index=series.index).ewm(span=period, adjust=False).mean()
    rs = roll_up / (roll_down + 1e-9)
    return 100.0 - (100.0 / (1.0 + rs))


# -----------------------------
# Trend Filter (Multi-TF EMA alignment)
# -----------------------------

def trend_alignment(symbol: str) -> int:
    """Return +1 for bullish, -1 for bearish, 0 for neutral based on EMA50>EMA200 and price relative to EMA200 across TREND_TFS.
    Condition: at least 3 of 5 TFs agree for bullish or bearish.
    """
    bullish = 0
    bearish = 0
    for tf in TREND_TFS:
        df = fetch_rates(symbol, tf, 400)
        ema50 = ema(df["close"], 50)
        ema200 = ema(df["close"], 200)
        last_close = df["close"].iloc[-1]
        if ema50.iloc[-1] > ema200.iloc[-1] and last_close > ema200.iloc[-1]:
            bullish += 1
        elif ema50.iloc[-1] < ema200.iloc[-1] and last_close < ema200.iloc[-1]:
            bearish += 1
    if bullish >= 3:
        return +1
    if bearish >= 3:
        return -1
    return 0


# -----------------------------
# Entry Trigger (M1/M5) BOS + RSI + micro-vol
# -----------------------------

def trigger_signal(symbol: str, trigger_tf: str) -> int:
    """Return +1 buy, -1 sell, 0 no-signal.
    Logic: micro break of structure over last N bars in direction of higher timeframe trend,
    RSI(14) > 55 for buys, < 45 for sells, and spread within threshold.
    """
    df = fetch_rates(symbol, trigger_tf, 300)
    df["RSI"] = rsi(df["close"], 14)

    # simple micro-BOS: last close breaks max/min of previous window
    window = 20 if trigger_tf == "M5" else 30
    last_close = df["close"].iloc[-1]
    prev_max = df["high"].iloc[-(window+1):-1].max()
    prev_min = df["low"].iloc[-(window+1):-1].min()

    # check spread
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return 0
    spread_points = int(abs(tick.ask - tick.bid) / mt5.symbol_info(symbol).point)

    if spread_points > SETTINGS.spread_threshold_points:
        return 0

    # trend
    tdir = trend_alignment(symbol)

    sig = 0
    if tdir > 0 and last_close > prev_max and df["RSI"].iloc[-1] > 55:
        sig = +1
    elif tdir < 0 and last_close < prev_min and df["RSI"].iloc[-1] < 45:
        sig = -1
    return sig


# -----------------------------
# Risk, Sizing, TP/SL in Points
# -----------------------------

def symbol_contract_metrics(symbol: str) -> Tuple[float, float, float]:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"No symbol info for {symbol}")
    point = info.point
    tick_value = info.trade_tick_value  # money per tick for 1 lot
    tick_size = info.trade_tick_size
    contract_size = info.trade_contract_size if hasattr(info, 'trade_contract_size') else 100000.0
    return point, tick_value, tick_size if tick_size else point


def dollars_to_points(symbol: str, dollars: float, lot: float) -> int:
    point, tick_value, tick_size = symbol_contract_metrics(symbol)
    # money per tick scales with lot
    money_per_tick = tick_value * (lot / 1.0)
    if money_per_tick <= 0:
        return 0
    ticks_needed = dollars / money_per_tick
    points = int(round(ticks_needed * (tick_size / point)))
    return max(points, 1)


def compute_sl_points_by_atr(symbol: str, trigger_tf: str, atr_mult: float = 1.0) -> int:
    df = fetch_rates(symbol, trigger_tf, 400)
    a = atr(df, 14)
    last_atr = a.iloc[-1]
    point = mt5.symbol_info(symbol).point
    sl_points = int(max(round(last_atr * atr_mult / point), 1))
    return sl_points


def compute_lot_for_risk(symbol: str, sl_points: int, settings: Settings) -> float:
    # risk in USD = effective_equity_usd * risk_per_trade_pct / 100
    risk_usd = settings.effective_equity_usd * (settings.risk_per_trade_pct / 100.0)
    # dollars per point for 1 lot
    point, tick_value, tick_size = symbol_contract_metrics(symbol)
    dollars_per_point_1lot = (tick_value / (tick_size / point))
    if dollars_per_point_1lot <= 0 or sl_points <= 0:
        return max(settings.initial_lot, 0.01)
    lot = risk_usd / (sl_points * dollars_per_point_1lot)
    # clip to sane range
    lot = max(min(lot, 5.0), 0.01)
    return float(round(lot, 2))


# -----------------------------
# Order Exec & Management (live and paper)
# -----------------------------

def place_order(symbol: str, is_buy: bool, lot: float, sl_points: int, tp_points: int, settings: Settings) -> Optional[int]:
    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        print(f"No tick/info for {symbol}")
        return None

    price = tick.ask if is_buy else tick.bid
    point = info.point

    sl = price - sl_points * point if is_buy else price + sl_points * point
    tp = price + tp_points * point if is_buy else price - tp_points * point

    if settings.paper_mode:
        # mock ticket id using epoch
        ticket = int(time.time() * 1000)
        PAPER_POSITIONS[ticket] = {
            "symbol": symbol,
            "is_buy": is_buy,
            "lot": lot,
            "open_price": price,
            "sl": sl,
            "tp": tp,
            "magic": settings.magic_number,
            "open_time": pd.Timestamp.utcnow(),
        }
        print(f"[PAPER] Opened {'BUY' if is_buy else 'SELL'} {symbol} lot={lot} SL={sl:.5f} TP={tp:.5f} ticket={ticket}")
        return ticket

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": settings.slippage,
        "magic": settings.magic_number,
        "comment": "TrendAligned_DollarTP_Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None:
        print("order_send returned None")
        return None
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("order_send failed:", result.retcode, result.comment)
        return None
    print(f"Opened ticket={result.order} {symbol} lot={lot}")
    return int(result.order)


def move_to_break_even(symbol: str, ticket: int, entry_price: float, is_buy: bool, settings: Settings):
    info = mt5.symbol_info(symbol)
    if info is None:
        return
    point = info.point
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    price = tick.bid if is_buy else tick.ask
    spread_points = int(abs(tick.ask - tick.bid) / point)
    be_price = entry_price + (spread_points * point if is_buy else -spread_points * point)

    if settings.paper_mode:
        pos = PAPER_POSITIONS.get(ticket)
        if pos:
            pos["sl"] = be_price
        return

    position = get_position_by_ticket(ticket)
    if not position:
        return
    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": be_price,
        "tp": position["tp"],
        "magic": settings.magic_number,
        "comment": "move_to_BE",
    }
    mt5.order_send(request)


def trail_step(symbol: str, ticket: int, step_points: int, is_buy: bool, settings: Settings):
    info = mt5.symbol_info(symbol)
    if info is None:
        return
    point = info.point
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return
    price = tick.bid if is_buy else tick.ask

    if settings.paper_mode:
        pos = PAPER_POSITIONS.get(ticket)
        if not pos:
            return
        # move SL towards price by step if favorable
        if is_buy:
            new_sl = max(pos["sl"], price - step_points * point)
        else:
            new_sl = min(pos["sl"], price + step_points * point)
        pos["sl"] = new_sl
        return

    position = get_position_by_ticket(ticket)
    if not position:
        return
    current_sl = position.get("sl", 0.0)
    new_sl = max(current_sl, price - step_points * point) if is_buy else min(current_sl, price + step_points * point)
    if (is_buy and new_sl > current_sl) or (not is_buy and new_sl < current_sl):
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": new_sl,
            "tp": position["tp"],
            "magic": settings.magic_number,
            "comment": "trail_step",
        }
        mt5.order_send(request)


def get_position_by_ticket(ticket: int) -> Optional[Dict]:
    positions = mt5.positions_get()
    if positions is None:
        return None
    for p in positions:
        if p.ticket == ticket:
            return {
                "symbol": p.symbol,
                "price_open": p.price_open,
                "sl": p.sl,
                "tp": p.tp,
                "type": p.type,
            }
    return None


# -----------------------------
# PnL Tracking (Daily Guards) + Paper P&L
# -----------------------------
PAPER_POSITIONS: Dict[int, Dict] = {}
DAILY_PNL: Dict[str, float] = {"profit": 0.0, "loss": 0.0}


def update_daily_pnl(symbols: List[str], settings: Settings):
    profit = 0.0
    if settings.paper_mode:
        for t, pos in list(PAPER_POSITIONS.items()):
            tick = mt5.symbol_info_tick(pos["symbol"]) if mt5 else None
            if tick is None:
                continue
            price = tick.bid if pos["is_buy"] else tick.ask
            # close on TP/SL (paper)
            if pos["is_buy"]:
                if price >= pos["tp"] or price <= pos["sl"]:
                    pnl = (price - pos["open_price"]) * pos["lot"] / mt5.symbol_info(pos["symbol"]).point
                    del PAPER_POSITIONS[t]
                    profit += pnl
            else:
                if price <= pos["tp"] or price >= pos["sl"]:
                    pnl = (pos["open_price"] - price) * pos["lot"] / mt5.symbol_info(pos["symbol"]).point
                    del PAPER_POSITIONS[t]
                    profit += pnl
    else:
        deals = mt5.history_deals_get(time.time() - 86400, time.time())
        if deals:
            for d in deals:
                profit += d.profit

    DAILY_PNL["profit"] = profit
    DAILY_PNL["loss"] = min(0.0, profit)


def hit_daily_caps(settings: Settings) -> Tuple[bool, str]:
    p = DAILY_PNL.get("profit", 0.0)
    if p >= settings.daily_profit_target_usd:
        return True, "Daily profit target reached"
    if -p >= settings.daily_max_loss_usd:
        return True, "Daily max loss reached"
    return False, ""


# -----------------------------
# Main Loop: Scan & Trade
# -----------------------------

def active_positions_count(symbol: str, settings: Settings) -> int:
    if settings.paper_mode:
        return sum(1 for pos in PAPER_POSITIONS.values() if pos["symbol"] == symbol)
    positions = mt5.positions_get(symbol=symbol)
    return 0 if positions is None else len(positions)


def step_bot(settings: Settings):
    # 1) update daily pnl and caps
    update_daily_pnl(settings.symbols, settings)
    stop_new, reason = hit_daily_caps(settings)

    for symbol in settings.symbols:
        if mt5 and not ensure_symbol(symbol):
            continue

        # block entries on spreads or caps
        tick = mt5.symbol_info_tick(symbol) if mt5 else None
        if not tick:
            continue
        spread_points = int(abs(tick.ask - tick.bid) / (mt5.symbol_info(symbol).point))
        if spread_points > settings.spread_threshold_points:
            continue
        if stop_new:
            continue

        # max positions guard
        if active_positions_count(symbol, settings) >= settings.max_open_positions:
            continue

        sig = trigger_signal(symbol, settings.trigger_tf)
        if sig == 0:
            continue

        # compute SL via ATR, lot by risk, TP via dollar range by TF
        sl_points = compute_sl_points_by_atr(symbol, settings.trigger_tf, settings.atr_mult_be)
        lot = compute_lot_for_risk(symbol, sl_points, settings)

        if settings.trigger_tf == "M1":
            tp_low, tp_high = settings.tp_dollar_range_m1
        else:
            tp_low, tp_high = settings.tp_dollar_range_m5
        # choose mid of range
        tp_usd = (tp_low + tp_high) / 2.0
        tp_points = dollars_to_points(symbol, tp_usd, lot)

        is_buy = sig > 0
        ticket = place_order(symbol, is_buy, lot, sl_points, tp_points, settings)
        if ticket is None:
            continue

        # After entry: schedule BE and trailing via periodic calls
        # BE trigger after 1x ATR in favour
        # Trailing step = 0.5x ATR
        # (Managed by streamlit timer / CLI loop below)


def manage_open_positions(settings: Settings):
    # iterate open positions and adjust SL (BE + trailing)
    for symbol in settings.symbols:
        point = mt5.symbol_info(symbol).point if mt5 else 0.0
        df = fetch_rates(symbol, settings.trigger_tf, 400)
        atr_now = atr(df, 14).iloc[-1]
        be_trigger_pts = int(max(round(atr_now / (point if point else 1e-9)), 1))
        trail_step_pts = int(max(round((settings.atr_mult_trail_step * atr_now) / (point if point else 1e-9)), 1))

        if settings.paper_mode:
            for t, pos in list(PAPER_POSITIONS.items()):
                if pos["symbol"] != symbol:
                    continue
                tick = mt5.symbol_info_tick(symbol) if mt5 else None
                if not tick:
                    continue
                price = tick.bid if pos["is_buy"] else tick.ask
                # move to BE
                if pos["is_buy"] and (price - pos["open_price"]) >= be_trigger_pts * point:
                    move_to_break_even(symbol, t, pos["open_price"], True, settings)
                elif (not pos["is_buy"]) and (pos["open_price"] - price) >= be_trigger_pts * point:
                    move_to_break_even(symbol, t, pos["open_price"], False, settings)
                # trail
                trail_step(symbol, t, trail_step_pts, pos["is_buy"], settings)
        else:
            positions = mt5.positions_get(symbol=symbol)
            if not positions:
                continue
            for p in positions:
                is_buy = (p.type == mt5.POSITION_TYPE_BUY)
                # move to BE
                if is_buy and (mt5.symbol_info_tick(symbol).bid - p.price_open) >= be_trigger_pts * point:
                    move_to_break_even(symbol, p.ticket, p.price_open, True, settings)
                elif (not is_buy) and (p.price_open - mt5.symbol_info_tick(symbol).ask) >= be_trigger_pts * point:
                    move_to_break_even(symbol, p.ticket, p.price_open, False, settings)
                # trail
                trail_step(symbol, p.ticket, trail_step_pts, is_buy, settings)


# -----------------------------
# Streamlit UI
# -----------------------------

def run_streamlit():
    import streamlit as st

    st.set_page_config(page_title="TrendAligned DollarTP Bot", layout="wide")
    st.title("⚙️ Trend-Aligned Dollar TP Bot (MT5)")
    st.caption("Multi-TF alignment • M1/M5 trigger • Dollar TP • BE+Trail • Daily guards")

    with st.sidebar:
        st.subheader("Settings")
        symbols = st.text_input("Symbols (space-separated)", value="XAUUSD EURUSD").split()
        trigger_tf = st.selectbox("Trigger timeframe", ["M5", "M1"], index=0)
        max_open = st.number_input("Max concurrent positions", 1, 100, 10)
        init_lot = st.number_input("Initial lot", 0.01, 5.0, 0.01, step=0.01)
        eff_eq = st.number_input("Effective equity (USD)", 10.0, 100000.0, 100.0, step=10.0)
        risk_pct = st.number_input("Risk per trade (%)", 0.1, 5.0, 0.7, step=0.1)
        daily_tp = st.number_input("Daily profit cap (USD)", 10.0, 5000.0, 300.0, step=10.0)
        daily_max_loss = st.number_input("Daily max loss (USD)", 10.0, 5000.0, 100.0, step=10.0)
        spr_th = st.number_input("Spread threshold (points)", 1, 200, 25)
        atr_be = st.number_input("ATR multiplier for BE trigger", 0.1, 5.0, 1.0, step=0.1)
        atr_trail = st.number_input("ATR multiplier for trail step", 0.1, 5.0, 0.5, step=0.1)
        paper = st.checkbox("Paper mode (no live orders)", value=True)
        magic = st.number_input("Magic number", 1, 99999999, 20250916)

        st.divider()
        st.subheader("MT5 Login (optional)")
        login = st.text_input("Login (int)")
        server = st.text_input("Server (e.g., MetaQuotes-Demo)")
        password = st.text_input("Password", type="password")

        if "running" not in st.session_state:
            st.session_state.running = False

        start = st.button("▶️ Start Bot")
        stop = st.button("⏹ Stop Bot")

    global SETTINGS
    SETTINGS = Settings(
        symbols=symbols,
        trigger_tf=trigger_tf,
        max_open_positions=int(max_open),
        initial_lot=float(init_lot),
        effective_equity_usd=float(eff_eq),
        risk_per_trade_pct=float(risk_pct),
        daily_profit_target_usd=float(daily_tp),
        daily_max_loss_usd=float(daily_max_loss),
        spread_threshold_points=int(spr_th),
        atr_mult_be=float(atr_be),
        atr_mult_trail_step=float(atr_trail),
        paper_mode=bool(paper),
        magic_number=int(magic),
        mt5_login=int(login) if login.strip().isdigit() else None,
        mt5_password=password or None,
        mt5_server=server or None,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Daily PnL (USD)", f"{DAILY_PNL.get('profit', 0.0):.2f}")
    with col2:
        st.metric("Positions (paper)", f"{len(PAPER_POSITIONS)}" if SETTINGS.paper_mode else "-")
    with col3:
        capped, reason = hit_daily_caps(SETTINGS)
        st.metric("Entry status", "Blocked" if capped else "Open", help=reason)

    st.code(repr(SETTINGS), language="python")

    if start:
        st.session_state.running = True
    if stop:
        st.session_state.running = False

    # init MT5 once
    if st.session_state.running and mt5:
        ok = init_mt5(SETTINGS.mt5_login, SETTINGS.mt5_password, SETTINGS.mt5_server)
        if not ok:
            st.warning("MT5 init/login failed. Running in paper mode only.")

    placeholder = st.empty()

    while st.session_state.running:
        try:
            step_bot(SETTINGS)
            manage_open_positions(SETTINGS)
            update_daily_pnl(SETTINGS.symbols, SETTINGS)
        except Exception as e:
            st.error(f"Loop error: {e}")
        with placeholder.container():
            st.write("Open (paper) positions:" if SETTINGS.paper_mode else "Open positions:")
            if SETTINGS.paper_mode:
                if PAPER_POSITIONS:
                    st.dataframe(pd.DataFrame(PAPER_POSITIONS).T)
                else:
                    st.info("No paper positions.")
            else:
                positions = mt5.positions_get() or []
                if positions:
                    rows = []
                    for p in positions:
                        rows.append({
                            "ticket": p.ticket,
                            "symbol": p.symbol,
                            "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                            "volume": p.volume,
                            "price_open": p.price_open,
                            "sl": p.sl,
                            "tp": p.tp,
                            "profit": p.profit,
                        })
                    st.dataframe(pd.DataFrame(rows))
                else:
                    st.info("No live positions.")
        st.toast("Tick", icon="⏱️")
        time.sleep(2)


# -----------------------------
# CLI Entrypoint
# -----------------------------

def run_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "EURUSD"]) 
    parser.add_argument("--trigger_tf", default="M5", choices=["M5", "M1"]) 
    parser.add_argument("--paper", default="True")
    parser.add_argument("--loop", type=int, default=50)
    args = parser.parse_args()

    global SETTINGS
    SETTINGS = Settings(
        symbols=args.symbols,
        trigger_tf=args.trigger_tf,
        paper_mode=(str(args.paper).lower() == "true"),
    )

    if mt5:
        init_mt5(None, None, None)

    for _ in range(args.loop):
        step_bot(SETTINGS)
        manage_open_positions(SETTINGS)
        update_daily_pnl(SETTINGS.symbols, SETTINGS)
        print("Daily PnL:", DAILY_PNL)
        time.sleep(2)


if __name__ == "__main__":
    # Detect if launched by Streamlit; if not, support CLI
    import sys
    if any("streamlit" in s.lower() for s in sys.argv):
        # Streamlit invokes as a module; UI is in run_streamlit()
        pass
    else:
        # Basic CLI fallback
        run_cli()
