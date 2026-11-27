import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import os

# تنظیمات پایه
LOT_SIZE = 0.01
SL_PIPS = 200
TP_PIPS = 400
NEWS_TIMES = [("13:30", "14:30")]
DAILY_LOSS_LIMIT = -100
LOG_FILE = "trades_log.xlsx"

# اتصال به متاتریدر
if not mt5.initialize():
    print("خطا در اتصال به MT5:", mt5.last_error())
    exit()

SESSION_TIMES = {
    "London": ("08:00", "16:00"),
    "New York": ("13:00", "21:00"),
    "Tokyo": ("00:00", "09:00"),
    "Sydney": ("22:00", "06:00")
}

def get_current_session():
    now = datetime.now().strftime("%H:%M")
    for session, (start, end) in SESSION_TIMES.items():
        if start <= now <= end or (start > end and (now >= start or now <= end)):
            return session
    return "خارج از سشن‌ اصلی"

def is_during_news():
    now = datetime.now().strftime("%H:%M")
    for start, end in NEWS_TIMES:
        if start <= now <= end:
            return True
    return False

def get_candles(symbol, timeframe, count=10):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    return pd.DataFrame(rates)

def check_trend(candles):
    closes = candles['close']
    if closes.iloc[-1] > closes.mean():
        return "up"
    elif closes.iloc[-1] < closes.mean():
        return "down"
    else:
        return "side"

def check_price_action(candles):
    if len(candles) < 3:
        return None
    current = candles.iloc[-1]
    previous = candles.iloc[-2]
    if current['close'] > previous['high']:
        return "buy"
    elif current['close'] < previous['low']:
        return "sell"
    else:
        return None

def calculate_levels(action, price):
    if action == "buy":
        return price - SL_PIPS * 0.01, price + TP_PIPS * 0.01
    elif action == "sell":
        return price + SL_PIPS * 0.01, price - TP_PIPS * 0.01

def place_order(symbol, action, sl, tp):
    price = mt5.symbol_info_tick(symbol).ask if action == "buy" else mt5.symbol_info_tick(symbol).bid
    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
    trend_now = check_trend(get_candles(symbol, mt5.TIMEFRAME_H1))
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 123456,
        "comment": f"سیگنال: {action.upper()} - روند: {trend_now}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        save_trade_to_excel(symbol, action, price, sl, tp)
        messagebox.showinfo("✅ سیگنال اجرا شد", f"{action.upper()} @ {price:.2f}")
    return result

def save_trade_to_excel(symbol, signal, price, sl, tp):
    data = {
        "زمان": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        "نماد": [symbol],
        "سیگنال": [signal],
        "قیمت": [price],
        "SL": [sl],
        "TP": [tp],
    }
    df_new = pd.DataFrame(data)
    if os.path.exists(LOG_FILE):
        df_old = pd.read_excel(LOG_FILE)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_excel(LOG_FILE, index=False)

def get_open_positions(symbol):
    positions = mt5.positions_get(symbol=symbol)
    return positions if positions else []

def close_all_positions():
    positions = mt5.positions_get()
    for pos in positions:
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pos.symbol).bid if pos.type == 0 else mt5.symbol_info_tick(pos.symbol).ask
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 10,
            "magic": 123456,
            "comment": "auto_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(close_request)

def check_daily_loss():
    history = mt5.history_deals_get(datetime.now().replace(hour=0, minute=0), datetime.now())
    if history:
        return sum([deal.profit for deal in history])
    return 0
class TradingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پرایس‌اکشن + تحلیل فاندامنتال + ثبت اکسل + هشدار")

        self.symbol_var = tk.StringVar(value="XAUUSD")
        self.tf_var = tk.StringVar(value="M5")
        self.avoid_news_var = tk.BooleanVar(value=True)
        self.max_positions_var = tk.IntVar(value=3)

        ttk.Label(root, text="نماد (Symbol):").pack()
        ttk.Combobox(root, textvariable=self.symbol_var, values=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]).pack()

        ttk.Label(root, text="تایم‌فریم:").pack()
        ttk.Combobox(root, textvariable=self.tf_var, values=["M1", "M5", "M15", "M30", "H1", "D1"]).pack()

        ttk.Label(root, text="حداکثر پوزیشن باز:").pack()
        ttk.Combobox(root, textvariable=self.max_positions_var, values=[1, 2, 3, 5, 10]).pack()

        ttk.Checkbutton(root, text="توقف معامله در زمان اخبار", variable=self.avoid_news_var).pack(pady=5)

        self.session_label = ttk.Label(root, text="سشن فعلی: ---")
        self.session_label.pack()
        self.session_description = ttk.Label(root, text="توضیح سشن: ---")
        self.session_description.pack()

        self.signal_label = ttk.Label(root, text="📈 سیگنال فعلی: ---")
        self.signal_label.pack()
        self.pnl_label = ttk.Label(root, text="💰 سود باز: ---")
        self.pnl_label.pack()
        self.open_positions_label = ttk.Label(root, text="📊 پوزیشن‌های باز: ---")
        self.open_positions_label.pack()

        self.log_box = tk.Text(root, height=10)
        self.log_box.pack()

        ttk.Button(root, text="▶ شروع ربات", command=self.start_bot).pack(side=tk.LEFT, padx=5)
        ttk.Button(root, text="⏹ توقف", command=self.stop_bot).pack(side=tk.LEFT, padx=5)
        ttk.Button(root, text="✖ بستن پوزیشن‌ها", command=close_all_positions).pack(side=tk.LEFT, padx=5)

        self.running = False

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_box.see(tk.END)

    def update_status(self):
        symbol = self.symbol_var.get()
        price = mt5.symbol_info_tick(symbol).ask
        self.session_label.config(text=f"سشن فعلی: {get_current_session()}")
        self.open_positions_label.config(text=f"پوزیشن‌های باز: {len(get_open_positions(symbol))}")
        self.pnl_label.config(text=f"سود باز: {self.calculate_unrealized_pnl(symbol, price):.2f}")
        session = get_current_session()
        description = {
            "London": "فعالیت بالا – EUR و GBP نوسانی",
            "New York": "بازار فعال – طلا و دلار پرنوسان",
            "Tokyo": "آسیا فعال – JPY نوسانی",
            "Sydney": "آغاز هفته با نقدینگی کمتر",
            "خارج از سشن‌ اصلی": "فعالیت کم، نوسانات تصادفی"
        }
        self.session_description.config(text=f"توضیح سشن: {description.get(session, '')}")

    def calculate_unrealized_pnl(self, symbol, current_price):
        pnl = 0
        for pos in get_open_positions(symbol):
            if pos.type == mt5.POSITION_TYPE_BUY:
                pnl += (current_price - pos.price_open) * pos.volume * 100000
            elif pos.type == mt5.POSITION_TYPE_SELL:
                pnl += (pos.price_open - current_price) * pos.volume * 100000
        return pnl

    def start_bot(self):
        self.running = True
        mt5.symbol_select(self.symbol_var.get(), True)
        threading.Thread(target=self.run_loop).start()

    def stop_bot(self):
        self.running = False

    def run_loop(self):
        tf_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "D1": mt5.TIMEFRAME_D1
        }
        while self.running:
            self.update_status()
            if check_daily_loss() < DAILY_LOSS_LIMIT:
                self.log_message("⛔ حد ضرر روزانه فعال شد. توقف ربات.")
                self.stop_bot()
                break
            if self.avoid_news_var.get() and is_during_news():
                self.signal_label.config(text="📡 سیگنال: توقف (اخبار)")
                self.log_message("📢 زمان اخبار – توقف معاملات")
            else:
                symbol = self.symbol_var.get()
                tf = tf_map.get(self.tf_var.get(), mt5.TIMEFRAME_M5)
                candles = get_candles(symbol, tf)
                candles_h1 = get_candles(symbol, mt5.TIMEFRAME_H1)
                if candles.empty or len(candles) < 3 or candles_h1.empty or len(candles_h1) < 3:
                    self.signal_label.config(text="📉 داده ناکافی")
                    self.log_message("⚠️ داده‌های کافی برای تحلیل وجود ندارد")
                    time.sleep(5)
                    continue
                trend = check_trend(candles_h1)
                signal = check_price_action(candles)
                self.signal_label.config(text=f"📊 سیگنال: {signal or '---'} | روند: {trend}")
                if signal:
                    if len(get_open_positions(symbol)) < self.max_positions_var.get():
                        price = mt5.symbol_info_tick(symbol).ask if signal == "buy" else mt5.symbol_info_tick(symbol).bid
                        sl, tp = calculate_levels(signal, price)
                        result = place_order(symbol, signal, sl, tp)
                        self.log_message(f"🟢 سفارش {signal.upper()} ارسال شد – نتیجه: {result.retcode}")
                    else:
                        self.log_message("🚫 پوزیشن‌های باز به سقف رسیدند.")
                else:
                    self.log_message("🔍 سیگنالی شناسایی نشد.")
            time.sleep(5)

# اجرای برنامه
if __name__ == "__main__":
    tk_root = tk.Tk()
    app = TradingBotApp(tk_root)
    tk_root.mainloop()
    del app
    mt5.shutdown()
