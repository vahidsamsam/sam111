import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk
import threading

# تنظیمات پایه
SYMBOL = "XAUUSD"
LOT_SIZE = 0.04
ACCOUNT_BALANCE = 1000
SL_PIPS = 200
TP_PIPS = 200
NEWS_TIMES = [("13:30", "14:30")]

# اتصال به متاتریدر
if not mt5.initialize():
    print("خطا در اتصال به MT5:", mt5.last_error())
    exit()
if not mt5.symbol_select(SYMBOL, True):
    print(f"عدم دسترسی به نماد: {SYMBOL}")
    exit()

# توابع اصلی
def is_during_news():
    now = datetime.now().strftime("%H:%M")
    for start, end in NEWS_TIMES:
        if start <= now <= end:
            return True
    return False

def get_candles(symbol, timeframe=mt5.TIMEFRAME_M5, count=3):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    return pd.DataFrame(rates)

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
    sl_pips = SL_PIPS
    tp_pips = TP_PIPS
    if action == "buy":
        return price - sl_pips * 0.01, price + tp_pips * 0.01
    elif action == "sell":
        return price + sl_pips * 0.01, price - tp_pips * 0.01

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

def get_open_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    return positions if positions else []

def close_all_positions():
    positions = get_open_positions()
    for pos in positions:
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(SYMBOL).bid if pos.type == 0 else mt5.symbol_info_tick(SYMBOL).ask
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
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

# رابط کاربری
class TradingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پرایس اکشن پیشرفته")

        self.avoid_news_var = tk.BooleanVar(value=True)

        self.status = ttk.Label(root, text="آماده برای اجرا", foreground="green")
        self.status.pack(pady=10)

        frame_inputs = ttk.Frame(root)
        frame_inputs.pack(pady=5)

        ttk.Label(frame_inputs, text="حجم (لات):").grid(row=0, column=0)
        self.lot_entry = ttk.Entry(frame_inputs)
        self.lot_entry.insert(0, str(LOT_SIZE))
        self.lot_entry.grid(row=0, column=1)

        ttk.Label(frame_inputs, text="SL (پیپ):").grid(row=1, column=0)
        self.sl_entry = ttk.Entry(frame_inputs)
        self.sl_entry.insert(0, str(SL_PIPS))
        self.sl_entry.grid(row=1, column=1)

        ttk.Label(frame_inputs, text="TP (پیپ):").grid(row=2, column=0)
        self.tp_entry = ttk.Entry(frame_inputs)
        self.tp_entry.insert(0, str(TP_PIPS))
        self.tp_entry.grid(row=2, column=1)

        self.avoid_news_checkbox = ttk.Checkbutton(root, text="عدم معامله هنگام اخبار", variable=self.avoid_news_var)
        self.avoid_news_checkbox.pack()

        self.price_label = ttk.Label(root, text="قیمت فعلی: ---")
        self.price_label.pack()

        self.signal_label = ttk.Label(root, text="سیگنال فعلی: ---")
        self.signal_label.pack()

        self.start_button = ttk.Button(root, text="شروع ربات", command=self.start_bot)
        self.start_button.pack(pady=5)

        self.stop_button = ttk.Button(root, text="توقف ربات", command=self.stop_bot)
        self.stop_button.pack(pady=5)

        self.close_button = ttk.Button(root, text="بستن تمام معاملات", command=self.close_positions)
        self.close_button.pack(pady=5)

        self.log = tk.Text(root, height=10, width=60)
        self.log.pack(pady=5)

        self.running = False

    def log_message(self, msg):
        self.log.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        self.log.see(tk.END)

    def update_price_display(self):
        price = mt5.symbol_info_tick(SYMBOL).ask
        self.price_label.config(text=f"قیمت فعلی: {price:.2f}")

    def start_bot(self):
        global LOT_SIZE, SL_PIPS, TP_PIPS
        try:
            LOT_SIZE = float(self.lot_entry.get())
            SL_PIPS = int(self.sl_entry.get())
            TP_PIPS = int(self.tp_entry.get())
        except ValueError:
            self.log_message("ورودی نامعتبر است!")
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
        while self.running:
            self.update_price_display()

            if self.avoid_news_var.get() and is_during_news():
                self.signal_label.config(text="سیگنال فعلی: توقف (زمان اخبار)")
                self.log_message("در حال حاضر زمان اخبار است. توقف معاملات...")
            else:
                candles = get_candles(SYMBOL)
                signal = check_price_action(candles)
                self.signal_label.config(text=f"سیگنال فعلی: {signal if signal else '---'}")
                if signal:
                    price = mt5.symbol_info_tick(SYMBOL).ask if signal == "buy" else mt5.symbol_info_tick(SYMBOL).bid
                    sl, tp = calculate_levels(signal, price)
                    result = place_order(signal, sl, tp)
                    self.log_message(f"ارسال سفارش {signal}: نتیجه = {result.retcode}")
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
