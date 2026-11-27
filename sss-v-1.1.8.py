# ترکیب نسخه 1.1.0 و 1.1.5
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk
import threading

# تنظیمات پیش‌فرض
SYMBOL = "XAUUSD"
LOT_SIZE = 0.1
SL_PIPS = 200
TP_PIPS = 400
MAX_POSITIONS = 3
DAILY_LOSS_LIMIT = -100
NEWS_TIMES = [("13:30", "14:30")]
SESSION_TIMES = {
    "London": ("08:00", "16:00"),
    "New York": ("13:00", "21:00"),
    "Tokyo": ("00:00", "09:00"),
    "Sydney": ("22:00", "06:00")
}

# اتصال به MT5
if not mt5.initialize():
    print("خطا در اتصال به MT5:", mt5.last_error())
    exit()

def is_during_news():
    now = datetime.now().strftime("%H:%M")
    for start, end in NEWS_TIMES:
        if start <= now <= end:
            return True
    return False

def get_current_session():
    now = datetime.now().strftime("%H:%M")
    for session, (start, end) in SESSION_TIMES.items():
        if start <= now <= end or (start > end and (now >= start or now <= end)):
            return session
    return "خارج از سشن"

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
    return None

def calculate_levels(action, price):
    if action == "buy":
        return price - SL_PIPS * 0.01, price + TP_PIPS * 0.01
    elif action == "sell":
        return price + SL_PIPS * 0.01, price - TP_PIPS * 0.01

def place_order(action, sl, tp):
    price = mt5.symbol_info_tick(SYMBOL).ask if action == "buy" else mt5.symbol_info_tick(SYMBOL).bid
    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
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
        "comment": "auto_trade_bot",
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
    return sum(deal.profit for deal in history) if history else 0

# رابط کاربری
class TradingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات هوشمند پرایس اکشن و فاندامنتال")

        self.status = ttk.Label(root, text="آماده اجرا", foreground="green")
        self.status.pack(pady=10)

        frame_inputs = ttk.Frame(root)
        frame_inputs.pack(pady=5)

        self.symbol_var = tk.StringVar(value=SYMBOL)
        self.symbol_menu = ttk.Combobox(frame_inputs, textvariable=self.symbol_var, values=["XAUUSD", "EURUSD", "GBPUSD", "BTCUSD"])
        ttk.Label(frame_inputs, text="نماد:").grid(row=0, column=0)
        self.symbol_menu.grid(row=0, column=1)

        self.tf_var = tk.StringVar(value="M5")
        self.tf_menu = ttk.Combobox(frame_inputs, textvariable=self.tf_var, values=["M1", "M5", "M15", "M30", "H1", "D1"])
        ttk.Label(frame_inputs, text="تایم‌فریم:").grid(row=1, column=0)
        self.tf_menu.grid(row=1, column=1)

        self.lot_entry = ttk.Entry(frame_inputs)
        self.lot_entry.insert(0, str(LOT_SIZE))
        ttk.Label(frame_inputs, text="حجم:").grid(row=2, column=0)
        self.lot_entry.grid(row=2, column=1)

        self.sl_entry = ttk.Entry(frame_inputs)
        self.sl_entry.insert(0, str(SL_PIPS))
        ttk.Label(frame_inputs, text="SL (پیپ):").grid(row=3, column=0)
        self.sl_entry.grid(row=3, column=1)

        self.tp_entry = ttk.Entry(frame_inputs)
        self.tp_entry.insert(0, str(TP_PIPS))
        ttk.Label(frame_inputs, text="TP (پیپ):").grid(row=4, column=0)
        self.tp_entry.grid(row=4, column=1)

        self.max_pos_var = tk.StringVar(value=str(MAX_POSITIONS))
        self.max_pos_menu = ttk.Combobox(frame_inputs, textvariable=self.max_pos_var, values=["1", "2", "3", "5", "10"])
        ttk.Label(frame_inputs, text="حداکثر پوزیشن‌ها:").grid(row=5, column=0)
        self.max_pos_menu.grid(row=5, column=1)

        self.avoid_news_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(root, text="عدم معامله هنگام اخبار", variable=self.avoid_news_var).pack()

        self.price_label = ttk.Label(root, text="قیمت فعلی: ---")
        self.price_label.pack()
        self.signal_label = ttk.Label(root, text="سیگنال فعلی: ---")
        self.signal_label.pack()
        self.session_label = ttk.Label(root, text="سشن فعلی: ---")
        self.session_label.pack()
        self.open_pos_label = ttk.Label(root, text="تعداد پوزیشن‌ها: 0")
        self.open_pos_label.pack()

        self.start_button = ttk.Button(root, text="شروع", command=self.start_bot)
        self.start_button.pack(pady=5)
        self.stop_button = ttk.Button(root, text="توقف", command=self.stop_bot)
        self.stop_button.pack(pady=5)
        self.close_button = ttk.Button(root, text="بستن معاملات", command=self.close_positions)
        self.close_button.pack(pady=5)

        self.log = tk.Text(root, height=10, width=70)
        self.log.pack(pady=5)

        self.running = False

    def log_message(self, msg):
        self.log.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        self.log.see(tk.END)

    def update_display(self):
        symbol = self.symbol_var.get()
        try:
            price = mt5.symbol_info_tick(symbol).ask
            self.price_label.config(text=f"قیمت فعلی: {price:.2f}")
            self.session_label.config(text=f"سشن فعلی: {get_current_session()}")
            self.open_pos_label.config(text=f"تعداد پوزیشن‌ها: {len(get_open_positions(symbol))}")
        except:
            self.log_message("خطا در دریافت قیمت")

    def start_bot(self):
        global SYMBOL, LOT_SIZE, SL_PIPS, TP_PIPS, MAX_POSITIONS
        try:
            SYMBOL = self.symbol_var.get()
            LOT_SIZE = float(self.lot_entry.get())
            SL_PIPS = int(self.sl_entry.get())
            TP_PIPS = int(self.tp_entry.get())
            MAX_POSITIONS = int(self.max_pos_var.get())
        except ValueError:
            self.log_message("ورودی نامعتبر!")
            return

        if not self.running:
            self.running = True
            self.status.config(text="در حال اجرا...", foreground="blue")
            threading.Thread(target=self.run_loop, daemon=True).start()

    def stop_bot(self):
        self.running = False
        self.status.config(text="متوقف شد", foreground="red")
        self.log_message("ربات متوقف شد")

    def close_positions(self):
        close_all_positions()
        self.log_message("همه معاملات بسته شدند")

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
            self.update_display()

            if check_daily_loss() < DAILY_LOSS_LIMIT:
                self.log_message("⛔️ حد ضرر روزانه فعال شد. توقف ربات.")
                self.stop_bot()
                break

            if self.avoid_news_var.get() and is_during_news():
                self.signal_label.config(text="سیگنال: توقف (اخبار)")
                self.log_message("⏸ توقف معاملات - زمان اخبار")
            else:
                tf = tf_map.get(self.tf_var.get(), mt5.TIMEFRAME_M5)
                candles = get_candles(SYMBOL, timeframe=tf)
                trend = check_trend(candles)
                signal = check_price_action(candles)
                self.signal_label.config(text=f"سیگنال: {signal or '---'} | روند: {trend}")

                if signal and len(get_open_positions(SYMBOL)) < MAX_POSITIONS:
                    price = mt5.symbol_info_tick(SYMBOL).ask if signal == "buy" else mt5.symbol_info_tick(SYMBOL).bid
                    sl, tp = calculate_levels(signal, price)
                    result = place_order(signal, sl, tp)
                    self.log_message(f"📥 سفارش {signal.upper()} | RetCode = {result.retcode}")
                else:
                    self.log_message("⏳ بدون سیگنال یا سقف پوزیشن پر شده")

            time.sleep(5)

# اجرا
tk_root = tk.Tk()
app = TradingBotApp(tk_root)
tk_root.mainloop()
mt5.shutdown()
