import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import requests
from pytz import timezone
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from PIL import Image, ImageTk
import os
import json

# ======================
# کلاس Trading Bot
# ======================
class AdvancedTradingBot:
    def __init__(self):
        # پارامترهای معاملاتی
        self.symbol = "XAUUSD"
        self.timeframe = mt5.TIMEFRAME_M5
        self.lot_size = 0.1
        self.sl_pips = 200
        self.tp_pips = 400
        self.risk_percentage = 1
        self.max_lot = 20
        self.trailing_stop = False
        self.trailing_distance = 50
        self.avoid_news = True
        
        # مدیریت ریسک
        self.risk_freeze = False
        self.daily_loss_limit = -100
        self.daily_profit_limit = 200
        self.daily_pnl = 0
        
        # اتصال به متاتریدر
        self.connect_mt5()
        
        # بارگذاری تنظیمات
        self.load_settings()

    def connect_mt5(self):
        """اتصال به پلتفرم متاتریدر 5"""
        if not mt5.initialize():
            raise Exception(f"اتصال به MT5 ناموفق بود. خطا: {mt5.last_error()}")
        if not mt5.symbol_select(self.symbol, True):
            raise Exception(f"نماد {self.symbol} در دسترس نیست")
    
    def load_settings(self):
        """بارگذاری تنظیمات از فایل"""
        try:
            if os.path.exists("bot_settings.json"):
                with open("bot_settings.json", "r") as f:
                    settings = json.load(f)
                    self.lot_size = settings.get("lot_size", self.lot_size)
                    self.sl_pips = settings.get("sl_pips", self.sl_pips)
                    self.tp_pips = settings.get("tp_pips", self.tp_pips)
                    self.risk_percentage = settings.get("risk_percentage", self.risk_percentage)
                    self.daily_loss_limit = settings.get("daily_loss_limit", self.daily_loss_limit)
                    self.daily_profit_limit = settings.get("daily_profit_limit", self.daily_profit_limit)
        except Exception as e:
            print(f"خطا در بارگذاری تنظیمات: {e}")
    
    def save_settings(self):
        """ذخیره تنظیمات در فایل"""
        try:
            settings = {
                "lot_size": self.lot_size,
                "sl_pips": self.sl_pips,
                "tp_pips": self.tp_pips,
                "risk_percentage": self.risk_percentage,
                "daily_loss_limit": self.daily_loss_limit,
                "daily_profit_limit": self.daily_profit_limit
            }
            with open("bot_settings.json", "w") as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"خطا در ذخیره تنظیمات: {e}")
    
    def get_candles(self, count=100):
        """دریافت داده‌های کندل‌های قیمتی"""
        candles = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
        return pd.DataFrame(candles) if candles is not None else None
    
    def calculate_rsi(self, candles, period=14):
        """محاسبه شاخص RSI"""
        if len(candles) < period:
            return 50
            
        delta = candles['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    
    def check_price_action(self, candles):
        """بررسی شرایط پرایس اکشن برای تولید سیگنال"""
        if len(candles) < 3:
            return None
            
        current = candles.iloc[-1]
        previous = candles.iloc[-2]
        rsi = self.calculate_rsi(candles)
        
        if current['close'] > previous['high'] and rsi < 70:
            return "buy"
        elif current['close'] < previous['low'] and rsi > 30:
            return "sell"
        return None
    
    def calculate_lot_size(self):
        """محاسبه حجم معامله بر اساس ریسک حساب"""
        account_info = mt5.account_info()
        if not account_info:
            return self.lot_size
            
        risk_amount = account_info.balance * (self.risk_percentage / 100)
        point_value = 1  # برای XAUUSD
        lot_size = risk_amount / (self.sl_pips * point_value)
        return round(min(lot_size, self.max_lot), 2)
    
    def place_order(self, signal):
        """ارسال سفارش معاملاتی"""
        if self.risk_freeze:
            return None
            
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return None
            
        price = tick.ask if signal == "buy" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if signal == "buy" else mt5.ORDER_TYPE_SELL
        sl = price - self.sl_pips * 0.01 if signal == "buy" else price + self.sl_pips * 0.01
        tp = price + self.tp_pips * 0.01 if signal == "buy" else price - self.tp_pips * 0.01
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.calculate_lot_size(),
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 10,
            "magic": 123456,
            "comment": "auto_trade",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        return mt5.order_send(request)
    
    def update_trailing_stop(self):
        """به‌روزرسانی تریلینگ استاپ"""
        if not self.trailing_stop:
            return
            
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return
            
        for pos in positions:
            tick = mt5.symbol_info_tick(self.symbol)
            if not tick:
                continue
                
            current_price = tick.bid if pos.type == 0 else tick.ask
            new_sl = None
            
            if pos.type == 0:  # خرید
                if current_price - pos.sl >= self.trailing_distance * 0.01:
                    new_sl = current_price - self.trailing_distance * 0.01
            else:  # فروش
                if pos.sl - current_price >= self.trailing_distance * 0.01:
                    new_sl = current_price + self.trailing_distance * 0.01
                    
            if new_sl:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": self.symbol,
                    "sl": new_sl,
                    "tp": pos.tp,
                }
                mt5.order_send(request)
    
    def calculate_daily_pnl(self):
        """محاسبه سود/ضرر روزانه"""
        today = datetime.now().date()
        deals = mt5.history_deals_get(today, datetime.now())
        if deals:
            self.daily_pnl = sum(deal.profit for deal in deals)
        return self.daily_pnl
    
    def check_risk_limits(self):
        """بررسی محدودیت‌های ریسک"""
        self.calculate_daily_pnl()
        
        if self.daily_pnl <= self.daily_loss_limit:
            self.risk_freeze = True
            return "loss_limit"
        elif self.daily_pnl >= self.daily_profit_limit:
            self.risk_freeze = True
            return "profit_limit"
        return None
    
    def reset_daily_limits(self):
        """بازنشانی محدودیت‌های روزانه"""
        now = datetime.now()
        if now.hour == 0 and now.minute < 5:
            self.daily_pnl = 0
            self.risk_freeze = False
            return True
        return False

# ======================
# رابط کاربری پیشرفته
# ======================
class TradingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gold Trading Bot Pro")
        self.root.geometry("1000x700")
        self.root.configure(bg="#2c3e50")
        
        # ایجاد استایل برای ویجت‌ها
        self.setup_styles()
        
        # ایجاد ربات
        self.bot = AdvancedTradingBot()
        
        # ایجاد رابط کاربری
        self.setup_ui()
        
        # شروع بروزرسانی اطلاعات
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        
        # ذخیره تنظیمات هنگام بسته شدن
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def setup_styles(self):
        """تنظیم استایل‌های رابط کاربری"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # استایل کلی
        style.configure('.', background='#2c3e50', foreground='white')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='#ecf0f1', font=('Tahoma', 10))
        style.configure('TButton', font=('Tahoma', 10), padding=6)
        style.configure('TNotebook', background='#2c3e50')
        style.configure('TNotebook.Tab', background='#34495e', foreground='#ecf0f1', padding=[10, 5])
        style.map('TNotebook.Tab', background=[('selected', '#3498db')])
        
        # استایل مخصوص
        style.configure('Title.TLabel', font=('Tahoma', 16, 'bold'))
        style.configure('Status.TLabel', font=('Tahoma', 12, 'bold'))
        style.configure('Positive.TLabel', foreground='#2ecc71', font=('Tahoma', 10, 'bold'))
        style.configure('Negative.TLabel', foreground='#e74c3c', font=('Tahoma', 10, 'bold'))
        style.configure('TradeButton.TButton', foreground='white', background='#27ae60')
        style.configure('StopButton.TButton', foreground='white', background='#e74c3c')
        style.configure('CloseButton.TButton', foreground='white', background='#f39c12')
    
    def setup_ui(self):
        """ایجاد رابط کاربری"""
        # هدر برنامه
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(header_frame, text="ربات معامله‌گر طلا (XAUUSD)", 
                 style='Title.TLabel').pack(side='left')
        
        # نمایش وضعیت
        self.status_var = tk.StringVar(value="آماده")
        status_label = ttk.Label(header_frame, textvariable=self.status_var, style='Status.TLabel')
        status_label.pack(side='right', padx=10)
        
        # تب‌های اصلی
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        
        # ایجاد تب‌ها
        self.setup_trade_tab()
        self.setup_risk_tab()
        self.setup_performance_tab()
        self.setup_log_tab()
        
        # پانل پایینی
        footer_frame = ttk.Frame(self.root)
        footer_frame.pack(fill='x', padx=10, pady=10)
        
        # نمایش اطلاعات حساب
        account_frame = ttk.LabelFrame(footer_frame, text="وضعیت حساب")
        account_frame.pack(fill='x', side='left', expand=True)
        
        self.balance_var = tk.StringVar(value="موجودی: $---")
        ttk.Label(account_frame, textvariable=self.balance_var).grid(row=0, column=0, padx=5, sticky='w')
        
        self.equity_var = tk.StringVar(value="سرمایه: $---")
        ttk.Label(account_frame, textvariable=self.equity_var).grid(row=0, column=1, padx=5, sticky='w')
        
        self.margin_var = tk.StringVar(value="مارجین: $---")
        ttk.Label(account_frame, textvariable=self.margin_var).grid(row=0, column=2, padx=5, sticky='w')
        
        # نمایش وضعیت ریسک
        risk_frame = ttk.LabelFrame(footer_frame, text="مدیریت ریسک")
        risk_frame.pack(fill='x', side='right', expand=True)
        
        self.daily_pnl_var = tk.StringVar(value="سود/ضرر روزانه: $0.00")
        ttk.Label(risk_frame, textvariable=self.daily_pnl_var).grid(row=0, column=0, padx=5, sticky='w')
        
        self.risk_status_var = tk.StringVar(value="وضعیت ریسک: عادی")
        ttk.Label(risk_frame, textvariable=self.risk_status_var).grid(row=0, column=1, padx=5, sticky='w')
    
    def setup_trade_tab(self):
        """ایجاد تب معاملات"""
        self.trade_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.trade_tab, text="معاملات")
        
        # قاب تنظیمات
        settings_frame = ttk.LabelFrame(self.trade_tab, text="تنظیمات معاملاتی")
        settings_frame.pack(fill='both', padx=10, pady=10)
        
        # تنظیمات حجم و حدها
        params_frame = ttk.Frame(settings_frame)
        params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(params_frame, text="حجم (لات):").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.lot_entry = ttk.Entry(params_frame, width=10)
        self.lot_entry.insert(0, str(self.bot.lot_size))
        self.lot_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(params_frame, text="حد ضرر (پیپ):").grid(row=0, column=2, sticky='e', padx=5, pady=5)
        self.sl_entry = ttk.Entry(params_frame, width=10)
        self.sl_entry.insert(0, str(self.bot.sl_pips))
        self.sl_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(params_frame, text="حد سود (پیپ):").grid(row=0, column=4, sticky='e', padx=5, pady=5)
        self.tp_entry = ttk.Entry(params_frame, width=10)
        self.tp_entry.insert(0, str(self.bot.tp_pips))
        self.tp_entry.grid(row=0, column=5, padx=5, pady=5)
        
        # تنظیمات پیشرفته
        advanced_frame = ttk.Frame(settings_frame)
        advanced_frame.pack(fill='x', padx=5, pady=5)
        
        self.avoid_news_var = tk.BooleanVar(value=self.bot.avoid_news)
        ttk.Checkbutton(advanced_frame, text="اجتناب از اخبار", 
                       variable=self.avoid_news_var).pack(side='left', padx=10)
        
        self.trailing_var = tk.BooleanVar(value=self.bot.trailing_stop)
        ttk.Checkbutton(advanced_frame, text="فعال کردن تریلینگ استاپ", 
                       variable=self.trailing_var).pack(side='left', padx=10)
        
        ttk.Label(advanced_frame, text="فاصله تریلینگ (پیپ):").pack(side='left', padx=5)
        self.trailing_dist_entry = ttk.Entry(advanced_frame, width=8)
        self.trailing_dist_entry.insert(0, str(self.bot.trailing_distance))
        self.trailing_dist_entry.pack(side='left', padx=5)
        
        # دکمه‌های کنترل
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text="شروع ربات", style='TradeButton.TButton',
                  command=self.start_bot).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="توقف ربات", style='StopButton.TButton',
                  command=self.stop_bot).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="بستن معاملات", style='CloseButton.TButton',
                  command=self.close_positions).pack(side='left', padx=10)
        
        # نمایش اطلاعات قیمت
        price_frame = ttk.LabelFrame(self.trade_tab, text="اطلاعات بازار")
        price_frame.pack(fill='both', padx=10, pady=10, expand=True)
        
        # نمایش قیمت در قالب نمودار
        self.fig, self.ax = plt.subplots(figsize=(8, 4), facecolor='#2c3e50')
        self.fig.patch.set_alpha(0.0)
        self.ax.set_facecolor('#34495e')
        self.ax.tick_params(colors='white')
        self.ax.spines['bottom'].set_color('#7f8c8d')
        self.ax.spines['top'].set_color('#7f8c8d')
        self.ax.spines['right'].set_color('#7f8c8d')
        self.ax.spines['left'].set_color('#7f8c8d')
        
        self.canvas = FigureCanvasTkAgg(self.fig, price_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # نمایش سیگنال
        signal_frame = ttk.Frame(price_frame)
        signal_frame.pack(fill='x', pady=5)
        
        self.signal_var = tk.StringVar(value="سیگنال فعلی: ---")
        signal_label = ttk.Label(signal_frame, textvariable=self.signal_var, 
                               font=('Tahoma', 12), foreground='#f1c40f')
        signal_label.pack()
        
        self.rsi_var = tk.StringVar(value="RSI: ---")
        rsi_label = ttk.Label(signal_frame, textvariable=self.rsi_var)
        rsi_label.pack()
    
    def setup_risk_tab(self):
        """ایجاد تب مدیریت ریسک"""
        self.risk_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.risk_tab, text="مدیریت ریسک")
        
        # تنظیمات ریسک
        settings_frame = ttk.LabelFrame(self.risk_tab, text="تنظیمات ریسک")
        settings_frame.pack(fill='both', padx=10, pady=10)
        
        ttk.Label(settings_frame, text="حد ضرر روزانه ($):").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.daily_loss_entry = ttk.Entry(settings_frame)
        self.daily_loss_entry.insert(0, str(self.bot.daily_loss_limit))
        self.daily_loss_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="حد سود روزانه ($):").grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.daily_profit_entry = ttk.Entry(settings_frame)
        self.daily_profit_entry.insert(0, str(self.bot.daily_profit_limit))
        self.daily_profit_entry.grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="درصد ریسک هر معامله:").grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.risk_percent_entry = ttk.Entry(settings_frame)
        self.risk_percent_entry.insert(0, str(self.bot.risk_percentage))
        self.risk_percent_entry.grid(row=2, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="حداکثر حجم (لات):").grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.max_lot_entry = ttk.Entry(settings_frame)
        self.max_lot_entry.insert(0, str(self.bot.max_lot))
        self.max_lot_entry.grid(row=3, column=1, padx=5, pady=5)
        
        ttk.Button(settings_frame, text="اعمال تنظیمات", 
                  command=self.apply_risk_settings).grid(row=4, column=0, columnspan=2, pady=10)
        
        # دکمه‌های مدیریت ریسک
        risk_btn_frame = ttk.Frame(settings_frame)
        risk_btn_frame.grid(row=5, column=0, columnspan=2, pady=5)
        
        ttk.Button(risk_btn_frame, text="بازنشانی ریسک فریز", 
                  command=self.reset_risk_freeze).pack(side='left', padx=5)
        
        ttk.Button(risk_btn_frame, text="بروزرسانی موجودی", 
                  command=self.update_account_info).pack(side='left', padx=5)
    
    def setup_performance_tab(self):
        """ایجاد تب عملکرد"""
        self.performance_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.performance_tab, text="عملکرد")
        
        # ایجاد نمودار عملکرد
        perf_frame = ttk.LabelFrame(self.performance_tab, text="عملکرد حساب")
        perf_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.perf_fig, self.perf_ax = plt.subplots(figsize=(8, 4), facecolor='#2c3e50')
        self.perf_fig.patch.set_alpha(0.0)
        self.perf_ax.set_facecolor('#34495e')
        self.perf_ax.tick_params(colors='white')
        self.perf_ax.spines['bottom'].set_color('#7f8c8d')
        self.perf_ax.spines['top'].set_color('#7f8c8d')
        self.perf_ax.spines['right'].set_color('#7f8c8d')
        self.perf_ax.spines['left'].set_color('#7f8c8d')
        
        self.perf_canvas = FigureCanvasTkAgg(self.perf_fig, perf_frame)
        self.perf_canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # نمایش آمار معاملات
        stats_frame = ttk.Frame(self.performance_tab)
        stats_frame.pack(fill='x', padx=10, pady=5)
        
        self.trade_stats_var = tk.StringVar(value="آمار معاملات: 0 خرید | 0 فروش")
        ttk.Label(stats_frame, textvariable=self.trade_stats_var).pack(side='left')
        
        self.win_rate_var = tk.StringVar(value="نرخ برد: 0%")
        ttk.Label(stats_frame, textvariable=self.win_rate_var).pack(side='right')
    
    def setup_log_tab(self):
        """ایجاد تب گزارشات"""
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="گزارشات")
        
        # ایجاد جعبه متن برای لاگ‌ها
        log_frame = ttk.LabelFrame(self.log_tab, text="گزارشات معاملات")
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, 
                                                bg='#34495e', fg='#ecf0f1',
                                                insertbackground='white',
                                                font=('Consolas', 10))
        self.log_text.pack(fill='both', expand=True)
        
        # تنظیمات لاگ
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(log_btn_frame, text="پاک کردن گزارشات", 
                  command=self.clear_log).pack(side='left', padx=5)
        
        ttk.Button(log_btn_frame, text="ذخیره گزارشات", 
                  command=self.save_log).pack(side='left', padx=5)
    
    def log_message(self, message, level="info"):
        """ثبت پیام در لاگ با رنگ‌بندی مناسب"""
        tag = level
        color_map = {
            "info": "#3498db",
            "warning": "#f39c12",
            "error": "#e74c3c",
            "trade": "#2ecc71"
        }
        
        self.log_text.tag_config(tag, foreground=color_map.get(level, "white"))
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
    
    def start_bot(self):
        """شروع فعالیت ربات"""
        try:
            # اعمال تنظیمات جدید
            self.bot.lot_size = float(self.lot_entry.get())
            self.bot.sl_pips = int(self.sl_entry.get())
            self.bot.tp_pips = int(self.tp_entry.get())
            self.bot.avoid_news = self.avoid_news_var.get()
            self.bot.trailing_stop = self.trailing_var.get()
            self.bot.trailing_distance = int(self.trailing_dist_entry.get())
            
            # شروع ربات
            self.bot.running = True
            self.status_var.set("در حال اجرا...")
            self.log_message("ربات شروع به کار کرد", "info")
        except ValueError:
            self.log_message("مقادیر وارد شده نامعتبر هستند", "error")
    
    def stop_bot(self):
        """توقف فعالیت ربات"""
        self.bot.running = False
        self.status_var.set("متوقف شده")
        self.log_message("ربات متوقف شد", "info")
    
    def close_positions(self):
        """بستن تمامی معاملات باز"""
        positions = mt5.positions_get(symbol=self.bot.symbol)
        if positions:
            for pos in positions:
                tick = mt5.symbol_info_tick(self.bot.symbol)
                price = tick.bid if pos.type == 0 else tick.ask
                order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
                
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.bot.symbol,
                    "volume": pos.volume,
                    "type": order_type,
                    "position": pos.ticket,
                    "price": price,
                    "deviation": 10,
                    "magic": 123456,
                    "comment": "manual_close",
                }
                mt5.order_send(request)
            self.log_message(f"{len(positions)} معامله بسته شد", "trade")
        else:
            self.log_message("معامله‌ای برای بستن وجود ندارد", "info")
    
    def apply_risk_settings(self):
        """اعمال تنظیمات مدیریت ریسک"""
        try:
            self.bot.daily_loss_limit = float(self.daily_loss_entry.get())
            self.bot.daily_profit_limit = float(self.daily_profit_entry.get())
            self.bot.risk_percentage = float(self.risk_percent_entry.get())
            self.bot.max_lot = float(self.max_lot_entry.get())
            self.log_message("تنظیمات ریسک به‌روزرسانی شد", "info")
        except ValueError:
            self.log_message("مقادیر ریسک نامعتبر هستند", "error")
    
    def reset_risk_freeze(self):
        """بازنشانی وضعیت ریسک فریز"""
        self.bot.risk_freeze = False
        self.bot.daily_pnl = 0
        self.log_message("وضعیت ریسک فریز بازنشانی شد", "info")
    
    def update_account_info(self):
        """بروزرسانی اطلاعات حساب"""
        account_info = mt5.account_info()
        if account_info:
            self.balance_var.set(f"موجودی: ${account_info.balance:.2f}")
            self.equity_var.set(f"سرمایه: ${account_info.equity:.2f}")
            self.margin_var.set(f"مارجین: ${account_info.margin:.2f}")
    
    def clear_log(self):
        """پاک کردن گزارشات"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("گزارشات پاک شدند", "info")
    
    def save_log(self):
        """ذخیره گزارشات در فایل"""
        try:
            with open("trading_log.txt", "w", encoding="utf-8") as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.log_message("گزارشات با موفقیت ذخیره شدند", "info")
        except Exception as e:
            self.log_message(f"خطا در ذخیره گزارشات: {str(e)}", "error")
    
    def update_price_chart(self):
        """بروزرسانی نمودار قیمت"""
        candles = self.bot.get_candles(count=50)
        if candles is None or len(candles) == 0:
            return
            
        self.ax.clear()
        
        # رسم نمودار کندل‌ها
        for i in range(len(candles)):
            color = 'g' if candles['close'].iloc[i] > candles['open'].iloc[i] else 'r'
            self.ax.plot([i, i], [candles['low'].iloc[i], candles['high'].iloc[i]], color=color, linewidth=1)
            self.ax.plot([i, i], [candles['open'].iloc[i], candles['close'].iloc[i]], color=color, linewidth=3)
        
        self.ax.set_title(f"نمودار قیمت {self.bot.symbol}", color='white')
        self.ax.set_facecolor('#34495e')
        self.ax.tick_params(colors='white')
        self.ax.grid(color='#7f8c8d', linestyle='--', alpha=0.5)
        
        self.canvas.draw()
        
        # محاسبه و نمایش RSI
        rsi_value = self.bot.calculate_rsi(candles)
        self.rsi_var.set(f"RSI: {rsi_value:.2f}")
        
        # نمایش سیگنال
        signal = self.bot.check_price_action(candles)
        if signal == "buy":
            self.signal_var.set("سیگنال فعلی: خرید")
            self.signal_var.set("سیگنال فعلی: خرید")
        elif signal == "sell":
            self.signal_var.set("سیگنال فعلی: فروش")
        else:
            self.signal_var.set("سیگنال فعلی: ---")
    
    def update_performance_chart(self):
        """بروزرسانی نمودار عملکرد"""
        # این تابع می‌تواند با داده‌های واقعی پر شود
        dates = ['01-01', '01-02', '01-03', '01-04', '01-05']
        balances = [1000, 1100, 1050, 1200, 1150]
        
        self.perf_ax.clear()
        self.perf_ax.plot(dates, balances, 'g-', marker='o')
        self.perf_ax.set_title("تغییرات بالانس حساب", color='white')
        self.perf_ax.set_facecolor('#34495e')
        self.perf_ax.tick_params(colors='white')
        self.perf_ax.grid(color='#7f8c8d', linestyle='--', alpha=0.5)
        
        self.perf_canvas.draw()
    
    def update_loop(self):
        """حلقه اصلی بروزرسانی اطلاعات"""
        while True:
            try:
                # بروزرسانی اطلاعات حساب
                self.update_account_info()
                
                # بروزرسانی وضعیت ریسک
                self.bot.reset_daily_limits()
                risk_status = self.bot.check_risk_limits()
                
                if risk_status == "loss_limit":
                    self.risk_status_var.set("وضعیت ریسک: توقف ضرر!")
                    self.log_message("حد ضرر روزانه فعال شد - معاملات متوقف شدند", "warning")
                elif risk_status == "profit_limit":
                    self.risk_status_var.set("وضعیت ریسک: توقف سود!")
                    self.log_message("حد سود روزانه فعال شد - معاملات متوقف شدند", "warning")
                else:
                    self.risk_status_var.set("وضعیت ریسک: عادی")
                
                # نمایش سود/ضرر روزانه
                self.daily_pnl_var.set(f"سود/ضرر روزانه: ${self.bot.daily_pnl:.2f}")
                
                # بروزرسانی نمودارها
                self.update_price_chart()
                self.update_performance_chart()
                
                # اجرای معاملات اگر ربات فعال است
                if self.bot.running and not self.bot.risk_freeze:
                    self.execute_trading()
                    
                time.sleep(5)
            except Exception as e:
                self.log_message(f"خطا در به‌روزرسانی: {str(e)}", "error")
                time.sleep(10)
    
    def execute_trading(self):
        """اجرای معاملات"""
        candles = self.bot.get_candles()
        if candles is None:
            self.log_message("خطا در دریافت داده‌های قیمت", "error")
            return
            
        signal = self.bot.check_price_action(candles)
        if signal:
            result = self.bot.place_order(signal)
            if result:
                self.log_message(f"سفارش {signal} با حجم {result.volume} ارسال شد", "trade")
            else:
                self.log_message("خطا در ارسال سفارش", "error")
        
        if self.bot.trailing_stop:
            self.bot.update_trailing_stop()
    
    def on_close(self):
        """عملیات هنگام بسته شدن پنجره"""
        self.bot.save_settings()
        mt5.shutdown()
        self.root.destroy()

# ======================
# اجرای برنامه
# ======================
if __name__ == "__main__":
    root = tk.Tk()
    app = TradingGUI(root)
    root.mainloop()