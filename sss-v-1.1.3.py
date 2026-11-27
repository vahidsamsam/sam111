import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, time
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import pytz
import json
import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# تنظیمات پایه
CONFIG_FILE = "bot_config.json"
DEFAULT_CONFIG = {
    "symbol": "XAUUSD",
    "lot_size": 0.1,
    "sl_factor": 1.5,
    "tp_factor": 3.0,
    "news_times": [["13:30", "14:30"]],
    "timeframe": "M5",
    "risk_percent": 1.0,
    "magic_number": 123456,
    "max_open_positions": 5,
    "ma_period": 50
}

# مدیریت پیکربندی
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# تبدیل تایم‌فریم به مقدار MT5
TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1
}

# کلاس اصلی ربات معاملاتی
class TradingBot:
    def __init__(self):
        self.config = load_config()
        self.running = False
        self.connected = False
        self.positions = []
        
    def connect_mt5(self):
        if not mt5.initialize():
            return False, f"اتصال به MT5 ناموفق: {mt5.last_error()}"
        
        symbol_info = mt5.symbol_info(self.config['symbol'])
        if symbol_info is None:
            mt5.shutdown()
            return False, f"نماد {self.config['symbol']} یافت نشد"
            
        if not symbol_info.visible:
            if not mt5.symbol_select(self.config['symbol'], True):
                mt5.shutdown()
                return False, f"فعال‌سازی نماد {self.config['symbol']} ناموفق"
        
        self.connected = True
        return True, "اتصال به MT5 موفقیت‌آمیز"
    
    def disconnect_mt5(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False
        return True
    
    def is_during_news(self):
        now = datetime.now(pytz.timezone('UTC')).astimezone(pytz.timezone('Asia/Tehran'))
        current_time = now.strftime("%H:%M")
        for start, end in self.config['news_times']:
            if start <= current_time <= end:
                return True
        return False
    
    def get_candles(self, count=100):
        timeframe = TIMEFRAMES.get(self.config['timeframe'], mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_from_pos(self.config['symbol'], timeframe, 0, count)
        return pd.DataFrame(rates) if rates is not None else None
    
    def check_price_action(self, candles):
        if candles is None or len(candles) < self.config['ma_period'] + 1:
            return None
            
        current = candles.iloc[-1]
        previous = candles.iloc[-2]
        ma = candles['close'].rolling(self.config['ma_period']).mean().iloc[-1]
        
        if current['close'] > previous['high'] and current['close'] > ma:
            return "buy"
        elif current['close'] < previous['low'] and current['close'] < ma:
            return "sell"
        return None
    
    def calculate_position_size(self, atr):
        account_info = mt5.account_info()
        if account_info is None:
            return self.config['lot_size']
            
        balance = account_info.balance
        risk_amount = balance * (self.config['risk_percent'] / 100)
        symbol_info = mt5.symbol_info(self.config['symbol'])
        point_value = symbol_info.point * 10
        
        if point_value == 0 or atr == 0:
            return self.config['lot_size']
            
        sl_pips = atr * self.config['sl_factor'] / symbol_info.point
        lot_size = risk_amount / (sl_pips * point_value)
        return round(max(0.01, min(lot_size, symbol_info.volume_max)), 2)
    
    def calculate_levels(self, action, price):
        symbol_info = mt5.symbol_info(self.config['symbol'])
        rates = mt5.copy_rates_from_pos(self.config['symbol'], mt5.TIMEFRAME_M15, 0, 14)
        df = pd.DataFrame(rates)
        atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
        
        sl_distance = atr * self.config['sl_factor'] / symbol_info.point
        tp_distance = atr * self.config['tp_factor'] / symbol_info.point
        
        if action == "buy":
            sl = price - sl_distance * symbol_info.point
            tp = price + tp_distance * symbol_info.point
        elif action == "sell":
            sl = price + sl_distance * symbol_info.point
            tp = price - tp_distance * symbol_info.point
        else:
            return None, None, None
            
        return sl, tp, atr
    
    def place_order(self, action):
        if len(self.positions) >= self.config['max_open_positions']:
            return False, "حداکثر تعداد معاملات باز شده است"
            
        symbol = self.config['symbol']
        price = mt5.symbol_info_tick(symbol).ask if action == "buy" else mt5.symbol_info_tick(symbol).bid
        order_type = mt5.ORDER_TYPE_BUY if action == "buy" else mt5.ORDER_TYPE_SELL
        sl, tp, atr = self.calculate_levels(action, price)
        lot_size = self.calculate_position_size(atr)
        
        if sl is None or tp is None:
            return False, "محاسبه SL/TP ناموفق"
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": self.config['magic_number'],
            "comment": "AdvancedBot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return False, f"خطا در ارسال سفارش: {result.comment}"
        return True, f"سفارش {action} موفقیت‌آمیز | حجم: {lot_size}"
    
    def get_open_positions(self):
        positions = mt5.positions_get(symbol=self.config['symbol'])
        self.positions = positions if positions else []
        return self.positions
    
    def close_all_positions(self):
        positions = self.get_open_positions()
        if not positions:
            return True, "هیچ پوزیشن بازی وجود ندارد"
            
        results = []
        for pos in positions:
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(self.config['symbol']).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.config['symbol']).ask
            
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.config['symbol'],
                "volume": pos.volume,
                "type": order_type,
                "position": pos.ticket,
                "price": price,
                "deviation": 20,
                "magic": self.config['magic_number'],
                "comment": "بسته شدن دستی",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            result = mt5.order_send(close_request)
            status = "موفق" if result.retcode == mt5.TRADE_RETCODE_DONE else "ناموفق"
            results.append(f"بستن پوزیشن {pos.ticket}: {status}")
        
        return True, "\n".join(results)
    
    def backtest_strategy(self, start_date, end_date):
        timeframe = TIMEFRAMES.get(self.config['timeframe'], mt5.TIMEFRAME_M5)
        rates = mt5.copy_rates_range(self.config['symbol'], timeframe, start_date, end_date)
        if rates is None:
            return None, "دریافت داده‌ها ناموفق"
            
        df = pd.DataFrame(rates)
        signals = []
        for i in range(self.config['ma_period'], len(df)):
            current = df.iloc[i]
            previous = df.iloc[i-1]
            ma = df['close'].iloc[i-self.config['ma_period']:i].mean()
            if current['close'] > previous['high'] and current['close'] > ma:
                signals.append(("buy", current['time'], current['close']))
            elif current['close'] < previous['low'] and current['close'] < ma:
                signals.append(("sell", current['time'], current['close']))
        
        return signals, "بک‌تست با موفقیت انجام شد"

# رابط کاربری حرفه‌ای
class TradingBotApp(tk.Tk):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.title("ربات تریدر پیشرفته فارکس")
        self.geometry("1000x700")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # استایل‌های حرفه‌ای
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TFrame", background="#f0f0f0")
        self.style.configure("TLabel", background="#f0f0f0", font=("Arial", 10))
        self.style.configure("Header.TLabel", font=("Arial", 12, "bold"))
        self.style.configure("TButton", font=("Arial", 10))
        self.style.configure("Red.TButton", foreground="red")
        self.style.configure("Green.TButton", foreground="dark green")
        self.style.configure("TNotebook.Tab", font=("Arial", 10, "bold"))
        
        # نوت‌بوک (تب‌ها)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # تب‌ها
        self.control_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.control_frame, text="کنترل ربات")
        self.create_control_tab()
        
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="تنظیمات")
        self.create_settings_tab()
        
        self.market_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.market_frame, text="وضعیت بازار")
        self.create_market_tab()
        
        self.log_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.log_frame, text="لاگ فعالیت")
        self.create_log_tab()
        
        self.backtest_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.backtest_frame, text="بک‌تست")
        self.create_backtest_tab()
        
        # اتصال اولیه و به‌روزرسانی UI
        self.connect_to_mt5()
        self.update_ui()
        self.after(1000, self.update_ui)
    
    def create_control_tab(self):
        status_frame = ttk.LabelFrame(self.control_frame, text="وضعیت سیستم")
        status_frame.pack(fill="x", padx=10, pady=5)
        
        self.connection_status = ttk.Label(status_frame, text="در حال بررسی...", foreground="gray")
        self.connection_status.pack(pady=5, padx=5, anchor="w")
        
        self.bot_status = ttk.Label(status_frame, text="ربات غیرفعال", foreground="red")
        self.bot_status.pack(pady=5, padx=5, anchor="w")
        
        self.price_label = ttk.Label(status_frame, text="قیمت فعلی: ---")
        self.price_label.pack(pady=5, padx=5, anchor="w")
        
        self.signal_label = ttk.Label(status_frame, text="سیگنال فعلی: ---")
        self.signal_label.pack(pady=5, padx=5, anchor="w")
        
        control_buttons = ttk.Frame(self.control_frame)
        control_buttons.pack(fill="x", padx=10, pady=10)
        
        self.start_btn = ttk.Button(control_buttons, text="شروع ربات", command=self.start_bot, style="Green.TButton")
        self.start_btn.pack(side="left", padx=5)
        
        self.stop_btn = ttk.Button(control_buttons, text="توقف ربات", command=self.stop_bot, style="Red.TButton")
        self.stop_btn.pack(side="left", padx=5)
        
        self.close_btn = ttk.Button(control_buttons, text="بستن تمام معاملات", command=self.close_positions)
        self.close_btn.pack(side="left", padx=5)
        
        account_frame = ttk.LabelFrame(self.control_frame, text="اطلاعات حساب")
        account_frame.pack(fill="x", padx=10, pady=5)
        
        self.balance_label = ttk.Label(account_frame, text="موجودی: ---")
        self.balance_label.pack(pady=2, padx=5, anchor="w")
        
        self.equity_label = ttk.Label(account_frame, text="ارزش خالص: ---")
        self.equity_label.pack(pady=2, padx=5, anchor="w")
        
        self.risk_label = ttk.Label(account_frame, text="ریسک فعلی: ---")
        self.risk_label.pack(pady=2, padx=5, anchor="w")
    
    def create_settings_tab(self):
        symbol_frame = ttk.LabelFrame(self.settings_frame, text="تنظیمات نماد")
        symbol_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(symbol_frame, text="نماد معاملاتی:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.symbol_entry = ttk.Entry(symbol_frame, width=10)
        self.symbol_entry.insert(0, self.bot.config['symbol'])
        self.symbol_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(symbol_frame, text="تایم‌فریم:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.timeframe_combo = ttk.Combobox(symbol_frame, values=list(TIMEFRAMES.keys()), width=5)
        self.timeframe_combo.set(self.bot.config['timeframe'])
        self.timeframe_combo.grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        risk_frame = ttk.LabelFrame(self.settings_frame, text="مدیریت ریسک")
        risk_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(risk_frame, text="حجم ثابت (لات):").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.lot_entry = ttk.Entry(risk_frame, width=8)
        self.lot_entry.insert(0, str(self.bot.config['lot_size']))
        self.lot_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(risk_frame, text="ریسک هر معامله (%):").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.risk_entry = ttk.Entry(risk_frame, width=8)
        self.risk_entry.insert(0, str(self.bot.config['risk_percent']))
        self.risk_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(risk_frame, text="ضریب حد ضرر (ATR):").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.sl_factor_entry = ttk.Entry(risk_frame, width=8)
        self.sl_factor_entry.insert(0, str(self.bot.config['sl_factor']))
        self.sl_factor_entry.grid(row=2, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(risk_frame, text="ضریب حد سود (ATR):").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.tp_factor_entry = ttk.Entry(risk_frame, width=8)
        self.tp_factor_entry.insert(0, str(self.bot.config['tp_factor']))
        self.tp_factor_entry.grid(row=3, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(risk_frame, text="حداکثر معاملات باز:").grid(row=4, column=0, padx=5, pady=2, sticky="e")
        self.max_pos_entry = ttk.Entry(risk_frame, width=8)
        self.max_pos_entry.insert(0, str(self.bot.config['max_open_positions']))
        self.max_pos_entry.grid(row=4, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(risk_frame, text="دوره MA:").grid(row=5, column=0, padx=5, pady=2, sticky="e")
        self.ma_period_entry = ttk.Entry(risk_frame, width=8)
        self.ma_period_entry.insert(0, str(self.bot.config['ma_period']))
        self.ma_period_entry.grid(row=5, column=1, padx=5, pady=2, sticky="w")
        
        news_frame = ttk.LabelFrame(self.settings_frame, text="زمان‌بندی اخبار")
        news_frame.pack(fill="x", padx=10, pady=5)
        
        self.news_listbox = tk.Listbox(news_frame, height=4, width=25)
        self.news_listbox.pack(side="left", padx=5, pady=5, fill="both", expand=True)
        self.refresh_news_list()
        
        news_controls = ttk.Frame(news_frame)
        news_controls.pack(side="right", padx=5, pady=5)
        
        ttk.Label(news_controls, text="شروع (HH:MM):").grid(row=0, column=0, padx=2, pady=2)
        self.news_start = ttk.Entry(news_controls, width=7)
        self.news_start.grid(row=0, column=1, padx=2, pady=2)
        
        ttk.Label(news_controls, text="پایان (HH:MM):").grid(row=1, column=0, padx=2, pady=2)
        self.news_end = ttk.Entry(news_controls, width=7)
        self.news_end.grid(row=1, column=1, padx=2, pady=2)
        
        ttk.Button(news_controls, text="افزودن", command=self.add_news_time).grid(row=2, column=0, columnspan=2, pady=5)
        ttk.Button(news_controls, text="حذف", command=self.remove_news_time).grid(row=3, column=0, columnspan=2, pady=5)
        
        save_frame = ttk.Frame(self.settings_frame)
        save_frame.pack(fill="x", padx=10, pady=10)
        ttk.Button(save_frame, text="ذخیره تنظیمات", command=self.save_settings).pack(pady=5)
    
    def create_market_tab(self):
        price_frame = ttk.LabelFrame(self.market_frame, text="وضعیت قیمت")
        price_frame.pack(fill="x", padx=10, pady=5)
        
        self.bid_label = ttk.Label(price_frame, text="قیمت خرید: ---")
        self.bid_label.pack(pady=2, padx=5, anchor="w")
        
        self.ask_label = ttk.Label(price_frame, text="قیمت فروش: ---")
        self.ask_label.pack(pady=2, padx=5, anchor="w")
        
        self.spread_label = ttk.Label(price_frame, text="اسپرد: ---")
        self.spread_label.pack(pady=2, padx=5, anchor="w")
        
        chart_frame = ttk.LabelFrame(self.market_frame, text="نمودار قیمت")
        chart_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.fig, self.ax = plt.subplots(figsize=(8, 3))
        self.price_chart = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.price_chart.get_tk_widget().pack(fill="both", expand=True)
        
        positions_frame = ttk.LabelFrame(self.market_frame, text="معاملات باز")
        positions_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        columns = ("ticket", "symbol", "type", "volume", "price", "sl", "tp", "profit")
        self.positions_tree = ttk.Treeview(positions_frame, columns=columns, show="headings", height=6)
        
        self.positions_tree.heading("ticket", text="شماره")
        self.positions_tree.heading("symbol", text="نماد")
        self.positions_tree.heading("type", text="نوع")
        self.positions_tree.heading("volume", text="حجم")
        self.positions_tree.heading("price", text="قیمت")
        self.positions_tree.heading("sl", text="حد ضرر")
        self.positions_tree.heading("tp", text="حد سود")
        self.positions_tree.heading("profit", text="سود")
        
        self.positions_tree.column("ticket", width=50, anchor="center")
        self.positions_tree.column("symbol", width=60, anchor="center")
        self.positions_tree.column("type", width=60, anchor="center")
        self.positions_tree.column("volume", width=60, anchor="center")
        self.positions_tree.column("price", width=80, anchor="center")
        self.positions_tree.column("sl", width=80, anchor="center")
        self.positions_tree.column("tp", width=80, anchor="center")
        self.positions_tree.column("profit", width=80, anchor="center")
        
        scrollbar = ttk.Scrollbar(positions_frame, orient="vertical", command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        self.positions_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_log_tab(self):
        log_frame = ttk.LabelFrame(self.log_frame, text="لاگ فعالیت")
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Arial", 10))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_text.configure(state="disabled")
        
        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill="x", padx=5, pady=5)
        
        ttk.Button(log_controls, text="پاک کردن لاگ", command=self.clear_log).pack(side="left")
        ttk.Button(log_controls, text="خروجی CSV", command=self.export_log).pack(side="left", padx=5)
    
    def create_backtest_tab(self):
        backtest_frame = ttk.LabelFrame(self.backtest_frame, text="تنظیمات بک‌تست")
        backtest_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(backtest_frame, text="تاریخ شروع (YYYY-MM-DD):").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.start_date_entry = ttk.Entry(backtest_frame)
        self.start_date_entry.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Label(backtest_frame, text="تاریخ پایان (YYYY-MM-DD):").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.end_date_entry = ttk.Entry(backtest_frame)
        self.end_date_entry.grid(row=1, column=1, padx=5, pady=2, sticky="w")
        
        ttk.Button(backtest_frame, text="اجرای بک‌تست", command=self.run_backtest).grid(row=2, column=0, columnspan=2, pady=5)
        
        result_frame = ttk.LabelFrame(self.backtest_frame, text="نتایج بک‌تست")
        result_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.backtest_result = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, font=("Arial", 10), height=10)
        self.backtest_result.pack(fill="both", expand=True, padx=5, pady=5)
        self.backtest_result.configure(state="disabled")
    
    def connect_to_mt5(self):
        success, message = self.bot.connect_mt5()
        self.log_message(message, "info" if success else "error")
        self.connection_status.config(text="متصل به MT5" if success else "عدم اتصال", foreground="dark green" if success else "red")
        return success
    
    def start_bot(self):
        if not self.bot.connected and not self.connect_to_mt5():
            return
        
        self.bot.running = True
        self.bot_status.config(text="ربات فعال", foreground="dark green")
        self.log_message("ربات شروع به کار کرد", "info")
        threading.Thread(target=self.run_bot, daemon=True).start()
    
    def stop_bot(self):
        self.bot.running = False
        self.bot_status.config(text="ربات غیرفعال", foreground="red")
        self.log_message("ربات متوقف شد", "warning")
    
    def close_positions(self):
        if not self.bot.connected:
            return
        success, message = self.bot.close_all_positions()
        self.log_message(message, "info" if success else "error")
        self.update_positions()
    
    def save_settings(self):
        try:
            self.bot.config.update({
                "symbol": self.symbol_entry.get(),
                "lot_size": float(self.lot_entry.get()),
                "sl_factor": float(self.sl_factor_entry.get()),
                "tp_factor": float(self.tp_factor_entry.get()),
                "risk_percent": float(self.risk_entry.get()),
                "timeframe": self.timeframe_combo.get(),
                "max_open_positions": int(self.max_pos_entry.get()),
                "ma_period": int(self.ma_period_entry.get())
            })
            save_config(self.bot.config)
            self.log_message("تنظیمات با موفقیت ذخیره شد", "info")
            return True
        except Exception as e:
            self.log_message(f"خطا در ذخیره تنظیمات: {str(e)}", "error")
            return False
    
    def add_news_time(self):
        start, end = self.news_start.get(), self.news_end.get()
        if not start or not end:
            self.log_message("زمان شروع و پایان باید وارد شوند", "error")
            return
        try:
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
            self.bot.config['news_times'].append([start, end])
            self.refresh_news_list()
            self.log_message(f"زمان اخبار اضافه شد: {start} - {end}", "info")
        except ValueError:
            self.log_message("فرمت زمان نامعتبر (از HH:MM استفاده کنید)", "error")
    
    def remove_news_time(self):
        selected = self.news_listbox.curselection()
        if selected:
            index = selected[0]
            if 0 <= index < len(self.bot.config['news_times']):
                removed = self.bot.config['news_times'].pop(index)
                self.refresh_news_list()
                self.log_message(f"زمان اخبار حذف شد: {removed[0]} - {removed[1]}", "info")
    
    def refresh_news_list(self):
        self.news_listbox.delete(0, tk.END)
        for start, end in self.bot.config['news_times']:
            self.news_listbox.insert(tk.END, f"{start} - {end}")
    
    def update_ui(self):
        if self.bot.connected:
            tick = mt5.symbol_info_tick(self.bot.config['symbol'])
            if tick:
                self.price_label.config(text=f"قیمت فعلی: {tick.last:.2f}")
                self.bid_label.config(text=f"قیمت خرید: {tick.bid:.2f}")
                self.ask_label.config(text=f"قیمت فروش: {tick.ask:.2f}")
                self.spread_label.config(text=f"اسپرد: {(tick.ask - tick.bid):.2f}")
                
                candles = self.bot.get_candles(100)
                if candles is not None:
                    self.ax.clear()
                    self.ax.plot(candles['close'], label='Close Price', color='blue')
                    self.ax.legend()
                    self.price_chart.draw()
            
            account = mt5.account_info()
            if account:
                self.balance_label.config(text=f"موجودی: {account.balance:.2f}")
                self.equity_label.config(text=f"ارزش خالص: {account.equity:.2f}")
                self.risk_label.config(text=f"ریسک فعلی: {self.bot.config['risk_percent']}%")
        
        self.update_positions()
        
        if self.bot.running:
            candles = self.bot.get_candles()
            signal = self.bot.check_price_action(candles)
            signal_text = {"buy": "خرید", "sell": "فروش", None: "---"}.get(signal)
            color = {"buy": "dark green", "sell": "red", None: "black"}.get(signal)
            self.signal_label.config(text=f"سیگنال فعلی: {signal_text}", foreground=color)
        
        self.after(2000, self.update_ui)
    
    def update_positions(self):
        if not self.bot.connected:
            return
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        positions = self.bot.get_open_positions()
        for pos in positions:
            pos_type = "خرید" if pos.type == mt5.ORDER_TYPE_BUY else "فروش"
            self.positions_tree.insert("", "end", values=(
                pos.ticket, pos.symbol, pos_type, pos.volume,
                f"{pos.price_open:.2f}", f"{pos.sl:.2f}" if pos.sl > 0 else "---",
                f"{pos.tp:.2f}" if pos.tp > 0 else "---", f"{pos.profit:.2f}"
            ))
    
    def run_bot(self):
        while self.bot.running:
            try:
                if self.bot.is_during_news():
                    self.log_message("زمان اخبار فعال - معاملات متوقف می‌شوند", "warning")
                    time.sleep(60)
                    continue
                
                tick = mt5.symbol_info_tick(self.config['symbol'])
                if tick:
                    candles = self.bot.get_candles()
                    signal = self.bot.check_price_action(candles)
                    if signal:
                        success, message = self.bot.place_order(signal)
                        self.log_message(message, "info" if success else "error")
                
                time.sleep(1)
            except Exception as e:
                self.log_message(f"خطای غیرمنتظره: {str(e)}", "error")
                time.sleep(10)
    
    def run_backtest(self):
        try:
            start_date = datetime.strptime(self.start_date_entry.get(), "%Y-%m-%d")
            end_date = datetime.strptime(self.end_date_entry.get(), "%Y-%m-%d")
            signals, message = self.bot.backtest_strategy(start_date, end_date)
            self.backtest_result.configure(state="normal")
            self.backtest_result.delete(1.0, tk.END)
            self.backtest_result.insert(tk.END, f"{message}\n\nتعداد سیگنال‌ها: {len(signals)}\n")
            for sig in signals[:10]:  # نمایش 10 سیگنال اول
                self.backtest_result.insert(tk.END, f"{sig[0]} در {datetime.fromtimestamp(sig[1])} - قیمت: {sig[2]}\n")
            self.backtest_result.configure(state="disabled")
            self.log_message("بک‌تست با موفقیت اجرا شد", "info")
        except Exception as e:
            self.log_message(f"خطا در بک‌تست: {str(e)}", "error")
    
    def log_message(self, message, msg_type="info"):
        self.log_text.configure(state="normal")
        colors = {"info": "black", "error": "red", "warning": "orange", "success": "dark green"}
        tag = f"tag_{msg_type}"
        self.log_text.tag_configure(tag, foreground=colors.get(msg_type, "black"))
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)
    
    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state="disabled")
    
    def export_log(self):
        with open("trading_log.csv", "w", encoding="utf-8") as f:
            f.write("زمان,پیام\n")
            for line in self.log_text.get(1.0, tk.END).splitlines():
                if line.strip():
                    f.write(f"{line.strip()}\n")
        self.log_message("لاگ به صورت CSV ذخیره شد", "info")
    
    def on_close(self):
        self.stop_bot()
        self.bot.disconnect_mt5()
        self.destroy()

if __name__ == "__main__":
    bot = TradingBot()
    app = TradingBotApp(bot)
    app.mainloop()
