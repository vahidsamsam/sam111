import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import requests
from pytz import timezone
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import json
import openpyxl
from openpyxl.styles import Font, PatternFill

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
        result = mt5.order_send(request)
        
        # ثبت معامله در تاریخچه
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            self.record_trade(signal, result)
        
        return result
    
    def record_trade(self, signal, result):
        """ثبت معامله در تاریخچه"""
        try:
            if not os.path.exists("trade_history.csv"):
                with open("trade_history.csv", "w") as f:
                    f.write("datetime,symbol,type,volume,price,sl,tp,profit\n")
            
            with open("trade_history.csv", "a") as f:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{now},{self.symbol},{signal},{result.volume},{result.price},{result.sl},{result.tp},0\n")
        except Exception as e:
            print(f"خطا در ثبت معامله: {e}")
    
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
    
    def get_open_positions(self):
        """دریافت پوزیشن‌های باز"""
        return mt5.positions_get(symbol=self.symbol) or []
    
    def get_trade_history(self, period="daily"):
        """دریافت تاریخچه معاملات"""
        now = datetime.now()
        
        if period == "daily":
            start_date = datetime(now.year, now.month, now.day)
        elif period == "hourly":
            start_date = datetime(now.year, now.month, now.day, now.hour)
        else:  # تمام تاریخچه
            start_date = datetime(2020, 1, 1)
        
        deals = mt5.history_deals_get(start_date, now)
        return deals if deals else []

# ======================
# رابط کاربری پیشرفته
# ======================
class TradingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gold Trading Bot Pro")
        self.root.geometry("1200x800")
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
        style.configure('ExportButton.TButton', foreground='white', background='#9b59b6')
    
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
        
        # ایجاد تب معاملات (شیت 1)
        self.setup_trade_tab()
        
        # ایجاد تب گزارشات و عملکرد (شیت 2)
        self.setup_reports_tab()
        
        # ایجاد تب لاگ (شیت 3)
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
        """ایجاد تب معاملات (شیت 1)"""
        self.trade_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.trade_tab, text="معاملات")
        
        # قاب اصلی با چیدمان عمودی
        main_frame = ttk.Frame(self.trade_tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # بخش بالایی: نمودار قیمت
        chart_frame = ttk.LabelFrame(main_frame, text="نمودار قیمت زنده")
        chart_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # ایجاد نمودار قیمت
        self.fig, self.ax = plt.subplots(figsize=(12, 5), facecolor='#2c3e50')
        self.fig.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.1)
        self.ax.set_facecolor('#34495e')
        
        # تنظیمات محورها
        self.ax.tick_params(axis='both', colors='white', labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color('#7f8c8d')
        
        self.canvas = FigureCanvasTkAgg(self.fig, chart_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # بخش میانی: کنترل‌های معاملاتی
        control_frame = ttk.LabelFrame(main_frame, text="کنترل‌های معاملاتی")
        control_frame.pack(fill='x', padx=5, pady=5)
        
        # ایجاد کنترل‌ها
        self.setup_trade_controls(control_frame)
        
        # بخش پایینی: پوزیشن‌های باز
        positions_frame = ttk.LabelFrame(main_frame, text="پوزیشن‌های باز")
        positions_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # ایجاد جدول پوزیشن‌ها
        self.setup_positions_table(positions_frame)
    
    def setup_trade_controls(self, parent):
        """ایجاد کنترل‌های معاملاتی"""
        params_frame = ttk.Frame(parent)
        params_frame.pack(fill='x', padx=5, pady=5)
        
        ttk.Label(params_frame, text="حجم (لات):").grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.lot_entry = ttk.Entry(params_frame, width=8)
        self.lot_entry.insert(0, str(self.bot.lot_size))
        self.lot_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(params_frame, text="حد ضرر (پیپ):").grid(row=0, column=2, sticky='e', padx=5, pady=5)
        self.sl_entry = ttk.Entry(params_frame, width=8)
        self.sl_entry.insert(0, str(self.bot.sl_pips))
        self.sl_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(params_frame, text="حد سود (پیپ):").grid(row=0, column=4, sticky='e', padx=5, pady=5)
        self.tp_entry = ttk.Entry(params_frame, width=8)
        self.tp_entry.insert(0, str(self.bot.tp_pips))
        self.tp_entry.grid(row=0, column=5, padx=5, pady=5)
        
        # چک‌باکس‌ها
        self.avoid_news_var = tk.BooleanVar(value=self.bot.avoid_news)
        ttk.Checkbutton(params_frame, text="اجتناب از اخبار", 
                       variable=self.avoid_news_var).grid(row=0, column=6, padx=10)
        
        self.trailing_var = tk.BooleanVar(value=self.bot.trailing_stop)
        ttk.Checkbutton(params_frame, text="تریلیگ استاپ", 
                       variable=self.trailing_var).grid(row=0, column=7, padx=5)
        
        # دکمه‌های کنترل
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill='x', pady=5)
        
        ttk.Button(btn_frame, text="شروع ربات", style='TradeButton.TButton',
                  command=self.start_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="توقف ربات", style='StopButton.TButton',
                  command=self.stop_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="بستن معاملات", style='CloseButton.TButton',
                  command=self.close_positions).pack(side='left', padx=5)
        
        # نمایش وضعیت ربات
        self.bot_status_var = tk.StringVar(value="وضعیت: آماده")
        ttk.Label(btn_frame, textvariable=self.bot_status_var, 
                 font=('Tahoma', 10, 'bold')).pack(side='right', padx=20)
    
    def setup_positions_table(self, parent):
        """ایجاد جدول پوزیشن‌های باز"""
        # ایجاد Treeview با اسکرول بار
        columns = ("ticket", "symbol", "type", "volume", "price", "sl", "tp", "profit")
        self.positions_tree = ttk.Treeview(parent, columns=columns, show="headings", height=5)
        
        # تنظیم ستون‌ها
        self.positions_tree.heading("ticket", text="شماره")
        self.positions_tree.heading("symbol", text="نماد")
        self.positions_tree.heading("type", text="نوع")
        self.positions_tree.heading("volume", text="حجم")
        self.positions_tree.heading("price", text="قیمت")
        self.positions_tree.heading("sl", text="حد ضرر")
        self.positions_tree.heading("tp", text="حد سود")
        self.positions_tree.heading("profit", text="سود/زیان")
        
        # تنظیم عرض ستون‌ها
        self.positions_tree.column("ticket", width=60)
        self.positions_tree.column("symbol", width=80)
        self.positions_tree.column("type", width=80)
        self.positions_tree.column("volume", width=80)
        self.positions_tree.column("price", width=100)
        self.positions_tree.column("sl", width=100)
        self.positions_tree.column("tp", width=100)
        self.positions_tree.column("profit", width=100)
        
        # اضافه کردن اسکرول بار
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        
        # چیدمان ویجت‌ها
        self.positions_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
    
    def setup_reports_tab(self):
        """ایجاد تب گزارشات و عملکرد (شیت 2)"""
        self.reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text="گزارشات و عملکرد")
        
        # قاب اصلی
        main_frame = ttk.Frame(self.reports_tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # بخش بالایی: نمودار عملکرد
        chart_frame = ttk.LabelFrame(main_frame, text="نمودار عملکرد حساب")
        chart_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # ایجاد نمودار عملکرد
        self.perf_fig, self.perf_ax = plt.subplots(figsize=(10, 4), facecolor='#2c3e50')
        self.perf_fig.patch.set_alpha(0.0)
        self.perf_ax.set_facecolor('#34495e')
        self.perf_ax.tick_params(colors='white')
        self.perf_ax.spines['bottom'].set_color('#7f8c8d')
        self.perf_ax.spines['top'].set_color('#7f8c8d')
        self.perf_ax.spines['right'].set_color('#7f8c8d')
        self.perf_ax.spines['left'].set_color('#7f8c8d')
        
        self.perf_canvas = FigureCanvasTkAgg(self.perf_fig, chart_frame)
        self.perf_canvas.get_tk_widget().pack(fill='both', expand=True)
        
        # بخش پایینی: کنترل‌های خروجی
        export_frame = ttk.LabelFrame(main_frame, text="خروجی گزارشات")
        export_frame.pack(fill='x', padx=5, pady=5)
        
        # دکمه‌های خروجی
        btn_frame = ttk.Frame(export_frame)
        btn_frame.pack(fill='x', pady=10)
        
        ttk.Button(btn_frame, text="خروجی روزانه (اکسل)", style='ExportButton.TButton',
                  command=lambda: self.export_reports("daily")).pack(side='left', padx=10)
        
        ttk.Button(btn_frame, text="خروجی ساعتی (اکسل)", style='ExportButton.TButton',
                  command=lambda: self.export_reports("hourly")).pack(side='left', padx=10)
        
        ttk.Button(btn_frame, text="خروجی پوزیشن‌ها (اکسل)", style='ExportButton.TButton',
                  command=self.export_positions).pack(side='left', padx=10)
        
        ttk.Button(btn_frame, text="خروجی ژورنال معاملات (اکسل)", style='ExportButton.TButton',
                  command=self.export_trade_journal).pack(side='left', padx=10)
    
    def setup_log_tab(self):
        """ایجاد تب لاگ (شیت 3)"""
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="لاگ")
        
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
            self.bot.trailing_distance = 50  # مقدار ثابت برای مثال
            
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
    
    def update_account_info(self):
        """بروزرسانی اطلاعات حساب"""
        account_info = mt5.account_info()
        if account_info:
            self.balance_var.set(f"موجودی: ${account_info.balance:.2f}")
            self.equity_var.set(f"سرمایه: ${account_info.equity:.2f}")
            self.margin_var.set(f"مارجین: ${account_info.margin:.2f}")
    
    def update_market_report(self):
        """بروزرسانی گزارش بازار"""
        try:
            # بروزرسانی اطلاعات نماد
            symbol_info = mt5.symbol_info(self.bot.symbol)
            if symbol_info:
                spread = symbol_info.spread
            
            # بروزرسانی وضعیت حساب
            account_info = mt5.account_info()
            if account_info:
                self.free_margin_var.set(f"${account_info.margin_free:.2f}")
            
            # بروزرسانی سود/زیان روزانه
            self.daily_pnl_var.set(f"${self.bot.daily_pnl:.2f}")
        
        except Exception as e:
            self.log_message(f"خطا در بروزرسانی گزارش بازار: {str(e)}", "error")
    
    def update_price_chart(self):
        """بروزرسانی نمودار قیمت"""
        candles = self.bot.get_candles(count=100)
        if candles is None or len(candles) == 0:
            return
            
        self.ax.clear()
        
        # محاسبه محدوده قیمتی برای نمایش بهتر
        prices = candles[['open', 'high', 'low', 'close']].values.flatten()
        min_price, max_price = np.nanmin(prices), np.nanmax(prices)
        price_range = max_price - min_price
        y_min = min_price - price_range * 0.05
        y_max = max_price + price_range * 0.05
        
        # رسم نمودار کندل‌ها
        for i in range(len(candles)):
            color = '#2ecc71' if candles['close'].iloc[i] > candles['open'].iloc[i] else '#e74c3c'
            self.ax.vlines(i, candles['low'].iloc[i], candles['high'].iloc[i], color=color, linewidth=1)
            self.ax.vlines(i, min(candles['open'].iloc[i], candles['close'].iloc[i]), 
                          max(candles['open'].iloc[i], candles['close'].iloc[i]), 
                          color=color, linewidth=3)
        
        # تنظیمات محورها
        self.ax.set_ylim(y_min, y_max)
        self.ax.set_title(f"نمودار قیمت {self.bot.symbol} (M5)", color='white', fontsize=12)
        self.ax.set_facecolor('#34495e')
        self.ax.grid(color='#7f8c8d', linestyle='--', alpha=0.3)
        self.ax.tick_params(colors='white', labelsize=9)
        
        self.canvas.draw()
    
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
    
    def update_positions_table(self):
        """بروزرسانی جدول پوزیشن‌های باز"""
        # حذف ردیف‌های قبلی
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        # دریافت پوزیشن‌های جاری
        positions = self.bot.get_open_positions()
        
        # افزودن پوزیشن‌ها به جدول
        for pos in positions:
            pos_type = "خرید" if pos.type == 0 else "فروش"
            profit = f"${pos.profit:.2f}"
            self.positions_tree.insert("", "end", values=(
                pos.ticket,
                pos.symbol,
                pos_type,
                pos.volume,
                pos.price_open,
                pos.sl,
                pos.tp,
                profit
            ))
    
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
                
                # بروزرسانی جدول پوزیشن‌ها
                self.update_positions_table()
                
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
    
    def export_reports(self, period):
        """خروجی گزارشات به اکسل"""
        try:
            # دریافت تاریخچه معاملات
            trades = self.bot.get_trade_history(period)
            
            if not trades:
                self.log_message(f"هیچ معامله‌ای برای دوره {period} یافت نشد", "warning")
                return
            
            # ایجاد فایل اکسل
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "گزارش معاملات"
            
            # ایجاد هدرها
            headers = ["تاریخ", "نماد", "نوع", "حجم", "قیمت", "حد ضرر", "حد سود", "سود/زیان"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
            
            # افزودن داده‌ها
            for row_num, trade in enumerate(trades, 2):
                trade_time = datetime.fromtimestamp(trade.time).strftime("%Y-%m-%d %H:%M:%S")
                trade_type = "خرید" if trade.type == 0 else "فروش"
                
                ws.cell(row=row_num, column=1, value=trade_time)
                ws.cell(row=row_num, column=2, value=trade.symbol)
                ws.cell(row=row_num, column=3, value=trade_type)
                ws.cell(row=row_num, column=4, value=trade.volume)
                ws.cell(row=row_num, column=5, value=trade.price)
                ws.cell(row=row_num, column=6, value=trade.sl)
                ws.cell(row=row_num, column=7, value=trade.tp)
                ws.cell(row=row_num, column=8, value=trade.profit)
            
            # ذخیره فایل
            filename = f"trade_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            wb.save(filename)
            self.log_message(f"گزارش {period} با موفقیت در {filename} ذخیره شد", "info")
            
        except Exception as e:
            self.log_message(f"خطا در ایجاد گزارش: {str(e)}", "error")
    
    def export_positions(self):
        """خروجی پوزیشن‌های باز به اکسل"""
        try:
            # دریافت پوزیشن‌های باز
            positions = self.bot.get_open_positions()
            
            if not positions:
                self.log_message("هیچ پوزیشن بازی یافت نشد", "warning")
                return
            
            # ایجاد فایل اکسل
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "پوزیشن‌های باز"
            
            # ایجاد هدرها
            headers = ["شماره", "نماد", "نوع", "حجم", "قیمت", "حد ضرر", "حد سود", "سود/زیان"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
            
            # افزودن داده‌ها
            for row_num, pos in enumerate(positions, 2):
                pos_type = "خرید" if pos.type == 0 else "فروش"
                
                ws.cell(row=row_num, column=1, value=pos.ticket)
                ws.cell(row=row_num, column=2, value=pos.symbol)
                ws.cell(row=row_num, column=3, value=pos_type)
                ws.cell(row=row_num, column=4, value=pos.volume)
                ws.cell(row=row_num, column=5, value=pos.price_open)
                ws.cell(row=row_num, column=6, value=pos.sl)
                ws.cell(row=row_num, column=7, value=pos.tp)
                ws.cell(row=row_num, column=8, value=pos.profit)
            
            # ذخیره فایل
            filename = f"open_positions_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            wb.save(filename)
            self.log_message(f"پوزیشن‌های باز با موفقیت در {filename} ذخیره شدند", "info")
            
        except Exception as e:
            self.log_message(f"خطا در ایجاد گزارش پوزیشن‌ها: {str(e)}", "error")
    
    def export_trade_journal(self):
        """خروجی ژورنال معاملات به اکسل"""
        try:
            # دریافت تمام تاریخچه معاملات
            trades = self.bot.get_trade_history("all")
            
            if not trades:
                self.log_message("هیچ معامله‌ای در ژورنال یافت نشد", "warning")
                return
            
            # ایجاد فایل اکسل
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "ژورنال معاملات"
            
            # ایجاد هدرها
            headers = ["تاریخ", "نماد", "نوع", "حجم", "قیمت", "حد ضرر", "حد سود", "سود/زیان", "یادداشت"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            
            # افزودن داده‌ها
            for row_num, trade in enumerate(trades, 2):
                trade_time = datetime.fromtimestamp(trade.time).strftime("%Y-%m-%d %H:%M:%S")
                trade_type = "خرید" if trade.type == 0 else "فروش"
                
                ws.cell(row=row_num, column=1, value=trade_time)
                ws.cell(row=row_num, column=2, value=trade.symbol)
                ws.cell(row=row_num, column=3, value=trade_type)
                ws.cell(row=row_num, column=4, value=trade.volume)
                ws.cell(row=row_num, column=5, value=trade.price)
                ws.cell(row=row_num, column=6, value=trade.sl)
                ws.cell(row=row_num, column=7, value=trade.tp)
                ws.cell(row=row_num, column=8, value=trade.profit)
                ws.cell(row=row_num, column=9, value=trade.comment)
            
            # ذخیره فایل
            filename = f"trade_journal_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            wb.save(filename)
            self.log_message(f"ژورنال معاملات با موفقیت در {filename} ذخیره شد", "info")
            
        except Exception as e:
            self.log_message(f"خطا در ایجاد ژورنال معاملات: {str(e)}", "error")
    
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