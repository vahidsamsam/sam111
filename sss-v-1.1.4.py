import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk, messagebox
import threading

# تنظیمات پایه
DEFAULT_SYMBOL = "XAUUSD"
DEFAULT_LOT_SIZE = 0.1
DEFAULT_SL_PIPS = 200
DEFAULT_TP_PIPS = 400
NEWS_TIMES = [("13:30", "14:30")]  # به دلخواه ویرایش کنید

# اتصال به متاتریدر
if not mt5.initialize():
    messagebox.showerror("MT5 Error", f"خطا در اتصال به MT5: {mt5.last_error()}")
    exit()

def get_symbols():
    return [s.name for s in mt5.symbols_get() if s.visible]

def select_symbol(symbol):
    if not mt5.symbol_select(symbol, True):
        messagebox.showerror("MT5 Error", f"عدم دسترسی به نماد: {symbol}")
        return False
    return True

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

def calculate_levels(action, price, sl_pips, tp_pips):
    pip = 0.01 if "JPY" not in action else 0.1
    if action == "buy":
        return price - sl_pips * pip, price + tp_pips * pip
    elif action == "sell":
        return price + sl_pips * pip, price - tp_pips * pip

def place_order(symbol, action, sl, tp, lot):
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if action == "buy" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
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
    result = mt5.order_send(request)
    return result

def get_open_positions(symbol):
    positions = mt5.positions_get(symbol=symbol)
    return positions if positions else []

def close_all_positions(symbol):
    positions = get_open_positions(symbol)
    for pos in positions:
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if pos.type == 0 else mt5.symbol_info_tick(symbol).ask
        close_request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
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

def get_account_info():
    info = mt5.account_info()
    if info:
        return info.balance
    return 0

def calc_lot_by_risk(symbol, sl_pips, risk_percent):
    balance = get_account_info()
    if balance == 0:
        return DEFAULT_LOT_SIZE
    pip_value = 1  # فرض برای XAUUSD (ممکن است برای نمادهای دیگر متفاوت باشد)
    risk_money = balance * (risk_percent / 100)
    lot = risk_money / (sl_pips * pip_value)
    lot = max(0.01, round(lot, 2))
    return lot

# رابط کاربری
class TradingBotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پرایس اکشن بهینه‌شده")

        self.symbol_var = tk.StringVar(value=DEFAULT_SYMBOL)
        self.lot_entry_var = tk.StringVar(value=str(DEFAULT_LOT_SIZE))
        self.sl_entry_var = tk.StringVar(value=str(DEFAULT_SL_PIPS))
        self.tp_entry_var = tk.StringVar(value=str(DEFAULT_TP_PIPS))
        self.avoid_news_var = tk.BooleanVar(value=True)
        self.use_risk_var = tk.BooleanVar(value=False)
        self.risk_percent_var = tk.StringVar(value="1")

        # وضعیت ربات
        self.status = ttk.Label(root, text="آماده برای اجرا", foreground="green")
        self.status.pack(pady=10)

        frame_inputs = ttk.Frame(root)
        frame_inputs.pack(pady=5)

        ttk.Label(frame_inputs, text="نماد:").grid(row=0, column=0)
        self.symbol_combo = ttk.Combobox(frame_inputs, values=get_symbols(), textvariable=self.symbol_var, width=10)
        self.symbol_combo.grid(row=0, column=1)

        ttk.Label(frame_inputs, text="حجم (لات):").grid(row=1, column=0)
        self.lot_entry = ttk.Entry(frame_inputs, textvariable=self.lot_entry_var, width=10)
        self.lot_entry.grid(row=1, column=1)

        ttk.Label(frame_inputs, text="SL (پیپ):").grid(row=2, column=0)
        self.sl_entry = ttk.Entry(frame_inputs, textvariable=self.sl_entry_var, width=10)
        self.sl_entry.grid(row=2, column=1)

        ttk.Label(frame_inputs, text="TP (پیپ):").grid(row=3, column=0)
        self.tp_entry = ttk.Entry(frame_inputs, textvariable=self.tp_entry_var, width=10)
        self.tp_entry.grid(row=3, column=1)

        self.risk_check = ttk.Checkbutton(frame_inputs, text="حجم بر اساس ریسک", variable=self.use_risk_var, command=self.toggle_risk)
        self.risk_check.grid(row=1, column=2)
        ttk.Label(frame_inputs, text="درصد ریسک:").grid(row=2, column=2)
        self.risk_percent_entry = ttk.Entry(frame_inputs, textvariable=self.risk_percent_var, width=5, state='disabled')
        self.risk_percent_entry.grid(row=2, column=3)

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

        self.log = tk.Text(root, height=7, width=60)
        self.log.pack(pady=5)

        self.positions_table = ttk.Treeview(root, columns=("ticket", "type", "volume", "price_open", "profit"), show="headings", height=4)
        for col in self.positions_table["columns"]:
            self.positions_table.heading(col, text=col)
        self.positions_table.pack(pady=5)

        self.running = False

    def toggle_risk(self):
        if self.use_risk_var.get():
            self.lot_entry.config(state='disabled')
            self.risk_percent_entry.config(state='normal')
        else:
            self.lot_entry.config(state='normal')
            self.risk_percent_entry.config(state='disabled')

    def log_message(self, msg):
        self.log.insert(tk.END, f"{datetime.now().strftime('%H:%M:%S')} - {msg}\n")
        self.log.see(tk.END)

    def update_price_display(self):
        symbol = self.symbol_var.get()
        if not select_symbol(symbol):
            self.price_label.config(text="قیمت فعلی: ---")
            return
        price = mt5.symbol_info_tick(symbol).ask
        self.price_label.config(text=f"قیمت فعلی: {price:.2f}")

    def update_positions_table(self):
        symbol = self.symbol_var.get()
        for i in self.positions_table.get_children():
            self.positions_table.delete(i)
        positions = get_open_positions(symbol)
        for pos in positions:
            self.positions_table.insert("", "end", values=(pos.ticket, "BUY" if pos.type==0 else "SELL", pos.volume, pos.price_open, pos.profit))

    def start_bot(self):
        try:
            symbol = self.symbol_var.get().strip()
            if not symbol or not select_symbol(symbol):
                self.log_message("نماد معتبر انتخاب نشده است.")
                return

            sl_pips = int(self.sl_entry_var.get())
            tp_pips = int(self.tp_entry_var.get())
            if self.use_risk_var.get():
                lot = calc_lot_by_risk(symbol, sl_pips, float(self.risk_percent_var.get()))
            else:
                lot = float(self.lot_entry_var.get())
            self.current_lot = lot
            self.current_sl = sl_pips
            self.current_tp = tp_pips
            self.current_symbol = symbol
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
        close_all_positions(self.symbol_var.get())
        self.log_message("همه معاملات بسته شدند")
        self.update_positions_table()

    def run_loop(self):
        while self.running:
            try:
                self.update_price_display()
                self.update_positions_table()
                symbol = self.current_symbol

                if self.avoid_news_var.get() and is_during_news():
                    self.signal_label.config(text="سیگنال فعلی: توقف (زمان اخبار)")
                    self.log_message("در حال حاضر زمان اخبار است. توقف معاملات...")
                elif get_open_positions(symbol):
                    self.signal_label.config(text="سیگنال فعلی: پوزیشن فعال")
                    self.log_message("معامله باز دارید، منتظر بسته شدن بمانید.")
                else:
                    candles = get_candles(symbol)
                    signal = check_price_action(candles)
                    self.signal_label.config(text=f"سیگنال فعلی: {signal if signal else '---'}")
                    if signal:
                        price = mt5.symbol_info_tick(symbol).ask if signal == "buy" else mt5.symbol_info_tick(symbol).bid
                        sl, tp = calculate_levels(signal, price, self.current_sl, self.current_tp)
                        result = place_order(symbol, signal, sl, tp, self.current_lot)
                        if result.retcode != mt5.TRADE_RETCODE_DONE:
                            self.log_message(f"خطا در ارسال سفارش: {result.retcode} - {result.comment}")
                        else:
                            self.log_message(f"سفارش {signal} ثبت شد. تیکت: {result.order}")
                    else:
                        self.log_message("سیگنالی وجود ندارد")
            except Exception as ex:
                self.log_message(f"خطای غیرمنتظره: {ex}")
            time.sleep(5)

# اجرای رابط گرافیکی
tk_root = tk.Tk()
app = TradingBotApp(tk_root)
tk_root.mainloop()

# پایان اجرای ربات
del app
mt5.shutdown()
