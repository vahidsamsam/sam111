import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk
import threading

# تنظیمات پایه
SYMBOL = "EURUSD"
LOT_SIZE = 0.01
ACCOUNT_BALANCE = 1000
SL_PIPS = 200
TP_PIPS = 400
NEWS_TIMES = [("13:30", "14:30")]
MAX_POSITIONS = 5
DAILY_LOSS_LIMIT = -100

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

def get_candles(symbol, timeframe=mt5.TIMEFRAME_M5, count=10):
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

def place_order(action, sl, tp):
    price = mt5.symbol_info_tick(SYMBOL).ask if action == "buy" else mt5.symbol_info_tick(SYMBOL).bid
    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
    trend_now = check_trend(get_candles(SYMBOL))
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
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
    return mt5.order_send(request)

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
        self.root.title("ربات پرایس اکشن و تحلیل فاندامنتال")

        self.symbol_var = tk.StringVar(value="XAUUSD")
        self.tf_var = tk.StringVar(value="M5")
        self.avoid_news_var = tk.BooleanVar(value=True)
        self.max_positions_var = tk.IntVar(value=MAX_POSITIONS)

        ttk.Label(root, text="نماد (Symbol):").pack()
        ttk.Combobox(root, textvariable=self.symbol_var, values=["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]).pack()

        ttk.Label(root, text="تایم فریم:").pack()
        ttk.Combobox(root, textvariable=self.tf_var, values=["M1", "M5", "M15", "M30", "H1", "D1"]).pack()

        ttk.Label(root, text="حداکثر پوزیشن باز:").pack()
        ttk.Combobox(root, textvariable=self.max_positions_var, values=[1, 2, 3, 5, 10]).pack()

        ttk.Checkbutton(root, text="اجتناب از زمان اخبار", variable=self.avoid_news_var).pack()

        self.session_label = ttk.Label(root, text="سشن فعلی: ---")
        self.session_label.pack()

        self.signal_label = ttk.Label(root, text="سیگنال فعلی: ---")
        self.signal_label.pack()

        self.pnl_label = ttk.Label(root, text="سود باز: ---")
        self.pnl_label.pack()

        self.log_box = tk.Text(root, height=10)
        self.log_box.pack()

        self.start_button = ttk.Button(root, text="شروع", command=self.start_bot)
        self.start_button.pack(side=tk.LEFT)

        self.stop_button = ttk.Button(root, text="توقف", command=self.stop_bot)
        self.stop_button.pack(side=tk.LEFT)

        self.close_button = ttk.Button(root, text="بستن پوزیشن‌ها", command=close_all_positions)
        self.close_button.pack(side=tk.LEFT)

        self.running = False

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_box.see(tk.END)

    def update_price_display(self):
        symbol = self.symbol_var.get()
        price = mt5.symbol_info_tick(symbol).ask
        session = get_current_session()
        self.session_label.config(text=f"سشن فعلی: {session}")

        # محاسبه سود باز
        pnl = 0
        for pos in get_open_positions(symbol):
            if pos.type == mt5.POSITION_TYPE_BUY:
                pnl += (price - pos.price_open) * pos.volume * 100000
            elif pos.type == mt5.POSITION_TYPE_SELL:
                pnl += (pos.price_open - price) * pos.volume * 100000
        self.pnl_label.config(text=f"سود باز: {pnl:.2f}")

    def start_bot(self):
        self.running = True
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
            self.update_price_display()
            if check_daily_loss() < DAILY_LOSS_LIMIT:
                self.log_message("🔴 حد ضرر روزانه فعال شد. ربات متوقف می‌شود.")
                self.stop_bot()
                break
            if self.avoid_news_var.get() and is_during_news():
                self.signal_label.config(text="سیگنال فعلی: توقف (زمان اخبار)")
                self.log_message("در حال حاضر زمان اخبار است. توقف معاملات...")
            else:
                symbol = self.symbol_var.get()
                tf = tf_map.get(self.tf_var.get(), mt5.TIMEFRAME_M5)
                candles = get_candles(symbol, timeframe=tf)
                if candles.empty or len(candles) < 3:
                    self.signal_label.config(text="سیگنال فعلی: داده ناکافی")
                    self.log_message("داده‌های کافی برای تحلیل موجود نیست")
                    time.sleep(5)
                    continue
                trend = check_trend(candles)
                signal = check_price_action(candles)
                self.signal_label.config(text=f"سیگنال فعلی: {signal if signal else '---'} | روند: {trend}")
                if signal:
                    if len(get_open_positions(symbol)) < self.max_positions_var.get():
                        price = mt5.symbol_info_tick(symbol).ask if signal == "buy" else mt5.symbol_info_tick(symbol).bid
                        sl, tp = calculate_levels(signal, price)
                        result = place_order(signal, sl, tp)
                        self.log_message(f"ارسال سفارش {signal}: نتیجه = {result.retcode}")
                    else:
                        self.log_message("تعداد پوزیشن‌های باز به حداکثر رسیده است")
                else:
                    self.log_message("سیگنالی وجود ندارد")
            time.sleep(5)

# اجرای رابط گرافیکی
tk_root = tk.Tk()
app = TradingBotApp(tk_root)
tk_root.mainloop()

# پایان اجرای ربات
del app
mt5.shutdown()
