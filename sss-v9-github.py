import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import requests
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import json
import openpyxl
from openpyxl.styles import Font, PatternFill

def ensure_data_dir():
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return data_dir

def data_path(filename):
    return os.path.join(ensure_data_dir(), filename)

def validate_positive_float(value, default=1.0):
    try:
        v = float(value)
        return v if v > 0 else default
    except Exception:
        return default

def validate_positive_int(value, default=1):
    try:
        v = int(value)
        return v if v > 0 else default
    except Exception:
        return default

class AdvancedTradingBot:
    def __init__(self):
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

        self.risk_freeze = False
        self.daily_loss_limit = -100
        self.daily_profit_limit = 200
        self.daily_pnl = 0

        # Drawdown parameters
        self.max_drawdown_percent = 25
        self.equity_peak = None
        self.current_drawdown_percent = 0

        self.running = False
        self.lock = threading.Lock()
        self.last_trade_candle_time = None

        self.connect_mt5()
        self.load_settings()

    def connect_mt5(self, retries=3):
        for i in range(retries):
            if mt5.initialize():
                if mt5.symbol_select(self.symbol, True):
                    return True
            time.sleep(2)
        raise Exception(f"Failed to connect to MT5 after {retries} attempts. Error: {mt5.last_error()}")

    def load_settings(self):
        try:
            settings_file = data_path("bot_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, "r") as f:
                    settings = json.load(f)
                    self.lot_size = settings.get("lot_size", self.lot_size)
                    self.sl_pips = settings.get("sl_pips", self.sl_pips)
                    self.tp_pips = settings.get("tp_pips", self.tp_pips)
                    self.risk_percentage = settings.get("risk_percentage", self.risk_percentage)
                    self.daily_loss_limit = settings.get("daily_loss_limit", self.daily_loss_limit)
                    self.daily_profit_limit = settings.get("daily_profit_limit", self.daily_profit_limit)
                    self.max_drawdown_percent = settings.get("max_drawdown_percent", self.max_drawdown_percent)
        except Exception as e:
            print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            settings = {
                "lot_size": self.lot_size,
                "sl_pips": self.sl_pips,
                "tp_pips": self.tp_pips,
                "risk_percentage": self.risk_percentage,
                "daily_loss_limit": self.daily_loss_limit,
                "daily_profit_limit": self.daily_profit_limit,
                "max_drawdown_percent": self.max_drawdown_percent
            }
            with open(data_path("bot_settings.json"), "w") as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get_candles(self, count=100):
        candles = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
        return pd.DataFrame(candles) if candles is not None else None

    def calculate_rsi(self, candles, period=14):
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
        if len(candles) < 3:
            return None
        current = candles.iloc[-1]
        previous = candles.iloc[-2]
        rsi = self.calculate_rsi(candles)
        if self.last_trade_candle_time == current['time']:
            return None
        if current['close'] > previous['high'] and rsi < 70:
            self.last_trade_candle_time = current['time']
            return "buy"
        elif current['close'] < previous['low'] and rsi > 30:
            self.last_trade_candle_time = current['time']
            return "sell"
        return None

    def calculate_lot_size(self):
        account_info = mt5.account_info()
        if not account_info:
            return self.lot_size
        risk_amount = account_info.balance * (self.risk_percentage / 100)
        point_value = 1
        lot_size = risk_amount / (self.sl_pips * point_value)
        return round(min(max(lot_size, 0.01), self.max_lot), 2)

    def place_order(self, signal):
        with self.lock:
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
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.record_trade(signal, result)
            return result

    def record_trade(self, signal, result):
        try:
            history_file = data_path("trade_history.csv")
            if not os.path.exists(history_file):
                with open(history_file, "w") as f:
                    f.write("datetime,symbol,type,volume,price,sl,tp,profit\n")
            with open(history_file, "a") as f:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"{now},{self.symbol},{signal},{result.volume},{result.price},{result.sl},{result.tp},0\n")
        except Exception as e:
            print(f"Error recording trade: {e}")

    def update_trailing_stop(self):
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
            if pos.type == 0:
                if current_price - pos.sl >= self.trailing_distance * 0.01:
                    new_sl = current_price - self.trailing_distance * 0.01
            else:
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
        today = datetime.now().date()
        deals = mt5.history_deals_get(today, datetime.now())
        if deals:
            self.daily_pnl = sum(deal.profit for deal in deals)
        return self.daily_pnl

    def calculate_drawdown(self):
        account_info = mt5.account_info()
        if not account_info:
            return 0
        equity = account_info.equity
        if self.equity_peak is None or equity > self.equity_peak:
            self.equity_peak = equity
        drawdown = (self.equity_peak - equity) / self.equity_peak * 100 if self.equity_peak > 0 else 0
        self.current_drawdown_percent = drawdown
        return drawdown

    def check_risk_limits(self):
        drawdown = self.calculate_drawdown()
        if drawdown >= self.max_drawdown_percent:
            self.risk_freeze = True
            return "drawdown_limit"
        self.calculate_daily_pnl()
        if self.daily_pnl <= self.daily_loss_limit:
            self.risk_freeze = True
            return "loss_limit"
        elif self.daily_pnl >= self.daily_profit_limit:
            self.risk_freeze = True
            return "profit_limit"
        return None

    def reset_daily_limits(self):
        now = datetime.now()
        if now.hour == 0 and now.minute < 5:
            self.daily_pnl = 0
            self.risk_freeze = False
            self.last_trade_candle_time = None
            # Reset equity peak at new day
            account_info = mt5.account_info()
            if account_info:
                self.equity_peak = account_info.equity
            return True
        return False

    def get_open_positions(self):
        return mt5.positions_get(symbol=self.symbol) or []

    def get_trade_history(self, period="daily"):
        now = datetime.now()
        if period == "daily":
            start_date = datetime(now.year, now.month, now.day)
        elif period == "hourly":
            start_date = datetime(now.year, now.month, now.day, now.hour)
        else:
            start_date = datetime(2020, 1, 1)
        deals = mt5.history_deals_get(start_date, now)
        return deals if deals else []

    def get_candle_countdown(self):
        now = datetime.now()
        current_minute = now.minute
        remainder = current_minute % 5
        minutes_left = 5 - remainder if remainder > 0 else 0
        seconds_left = 60 - now.second
        if remainder == 0 and seconds_left == 60:
            minutes_left = 5
            seconds_left = 0
        return minutes_left, seconds_left

class TradingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Gold Trading Bot Pro")
        self.root.geometry("1200x800")
        self.root.configure(bg="#2c3e50")
        self.setup_styles()
        self.bot = AdvancedTradingBot()
        self.setup_ui()
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.last_risk_status = None

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('.', background='#2c3e50', foreground='white')
        style.configure('TFrame', background='#2c3e50')
        style.configure('TLabel', background='#2c3e50', foreground='#ecf0f1', font=('Tahoma', 10))
        style.configure('TButton', font=('Tahoma', 10), padding=6)
        style.configure('TNotebook', background='#2c3e50')
        style.configure('TNotebook.Tab', background='#34495e', foreground='#ecf0f1', padding=[10, 5])
        style.map('TNotebook.Tab', background=[('selected', '#3498db')])
        style.configure('Title.TLabel', font=('Tahoma', 16, 'bold'))
        style.configure('Status.TLabel', font=('Tahoma', 12, 'bold'))
        style.configure('Positive.TLabel', foreground='#2ecc71', font=('Tahoma', 10, 'bold'))
        style.configure('Negative.TLabel', foreground='#e74c3c', font=('Tahoma', 10, 'bold'))
        style.configure('TradeButton.TButton', foreground='white', background='#27ae60')
        style.configure('StopButton.TButton', foreground='white', background='#e74c3c')
        style.configure('CloseButton.TButton', foreground='white', background='#f39c12')
        style.configure('ExportButton.TButton', foreground='white', background='#9b59b6')
        style.configure('Light.TFrame', background='#f0f0f0')
        style.configure('Light.TLabel', background='#f0f0f0', foreground='black', font=('Tahoma', 10))
        style.configure('Light.TCheckbutton', background='#f0f0f0', foreground='black')
        style.configure('Light.TEntry', fieldbackground='white', foreground='black')

    def setup_ui(self):
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill='x', padx=10, pady=10)
        ttk.Label(header_frame, text="Gold Trading Bot (XAUUSD)", style='Title.TLabel').pack(side='left')
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(header_frame, textvariable=self.status_var, style='Status.TLabel')
        status_label.pack(side='right', padx=10)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=5)
        self.setup_trade_tab()
        self.setup_reports_tab()
        self.setup_log_tab()
        footer_frame = ttk.Frame(self.root)
        footer_frame.pack(fill='x', padx=10, pady=10)
        account_frame = ttk.LabelFrame(footer_frame, text="Account Status")
        account_frame.pack(fill='x', side='left', expand=True)
        self.balance_var = tk.StringVar(value="Balance: $---")
        ttk.Label(account_frame, textvariable=self.balance_var).grid(row=0, column=0, padx=5, sticky='w')
        self.equity_var = tk.StringVar(value="Equity: $---")
        ttk.Label(account_frame, textvariable=self.equity_var).grid(row=0, column=1, padx=5, sticky='w')
        self.margin_var = tk.StringVar(value="Margin: $---")
        ttk.Label(account_frame, textvariable=self.margin_var).grid(row=0, column=2, padx=5, sticky='w')
        risk_frame = ttk.LabelFrame(footer_frame, text="Risk Management")
        risk_frame.pack(fill='x', side='right', expand=True)
        self.daily_pnl_var = tk.StringVar(value="Daily P/L: $0.00")
        ttk.Label(risk_frame, textvariable=self.daily_pnl_var).grid(row=0, column=0, padx=5, sticky='w')
        self.risk_status_var = tk.StringVar(value="Risk Status: Normal")
        ttk.Label(risk_frame, textvariable=self.risk_status_var).grid(row=0, column=1, padx=5, sticky='w')

    def setup_trade_tab(self):
        self.trade_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.trade_tab, text="Trading")
        main_frame = ttk.Frame(self.trade_tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        control_frame = ttk.LabelFrame(main_frame, text="Trading Controls")
        control_frame.pack(fill='x', padx=5, pady=5)
        control_frame.configure(style='Light.TFrame')
        self.setup_trade_controls(control_frame)
        risk_frame = ttk.LabelFrame(main_frame, text="Risk Management Settings")
        risk_frame.pack(fill='x', padx=5, pady=5)
        risk_frame.configure(style='Light.TFrame')
        self.setup_risk_controls(risk_frame)
        positions_frame = ttk.LabelFrame(main_frame, text="Open Positions")
        positions_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.setup_positions_table(positions_frame)
        countdown_frame = ttk.Frame(main_frame)
        countdown_frame.pack(fill='x', padx=5, pady=5)
        ttk.Label(countdown_frame, text="Next Candle In:").pack(side='left', padx=5)
        self.countdown_var = tk.StringVar(value="05:00")
        countdown_label = ttk.Label(countdown_frame, textvariable=self.countdown_var, font=('Tahoma', 12, 'bold'), foreground='#3498db')
        countdown_label.pack(side='left', padx=5)

    def setup_trade_controls(self, parent):
        params_frame = ttk.Frame(parent)
        params_frame.pack(fill='x', padx=5, pady=5)
        params_frame.configure(style='Light.TFrame')
        ttk.Label(params_frame, text="Lot Size:", style='Light.TLabel').grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.lot_entry = ttk.Entry(params_frame, width=8, style='Light.TEntry')
        self.lot_entry.insert(0, str(self.bot.lot_size))
        self.lot_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(params_frame, text="Stop Loss (pips):", style='Light.TLabel').grid(row=0, column=2, sticky='e', padx=5, pady=5)
        self.sl_entry = ttk.Entry(params_frame, width=8, style='Light.TEntry')
        self.sl_entry.insert(0, str(self.bot.sl_pips))
        self.sl_entry.grid(row=0, column=3, padx=5, pady=5)
        ttk.Label(params_frame, text="Take Profit (pips):", style='Light.TLabel').grid(row=0, column=4, sticky='e', padx=5, pady=5)
        self.tp_entry = ttk.Entry(params_frame, width=8, style='Light.TEntry')
        self.tp_entry.insert(0, str(self.bot.tp_pips))
        self.tp_entry.grid(row=0, column=5, padx=5, pady=5)
        self.avoid_news_var = tk.BooleanVar(value=self.bot.avoid_news)
        ttk.Checkbutton(params_frame, text="Avoid News", variable=self.avoid_news_var, style='Light.TCheckbutton').grid(row=0, column=6, padx=10)
        self.trailing_var = tk.BooleanVar(value=self.bot.trailing_stop)
        ttk.Checkbutton(params_frame, text="Trailing Stop", variable=self.trailing_var, style='Light.TCheckbutton').grid(row=0, column=7, padx=5)
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill='x', pady=5)
        btn_frame.configure(style='Light.TFrame')
        ttk.Button(btn_frame, text="Start Bot", style='TradeButton.TButton', command=self.start_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Stop Bot", style='StopButton.TButton', command=self.stop_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Close Positions", style='CloseButton.TButton', command=self.close_positions).pack(side='left', padx=5)
        self.bot_status_var = tk.StringVar(value="Status: Ready")
        ttk.Label(btn_frame, textvariable=self.bot_status_var, font=('Tahoma', 10, 'bold')).pack(side='right', padx=20)

    def setup_risk_controls(self, parent):
        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill='x', padx=5, pady=5)
        settings_frame.configure(style='Light.TFrame')
        ttk.Label(settings_frame, text="Daily Loss Limit ($):", style='Light.TLabel').grid(row=0, column=0, sticky='e', padx=5, pady=5)
        self.daily_loss_entry = ttk.Entry(settings_frame, style='Light.TEntry')
        self.daily_loss_entry.insert(0, str(self.bot.daily_loss_limit))
        self.daily_loss_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(settings_frame, text="Daily Profit Limit ($):", style='Light.TLabel').grid(row=1, column=0, sticky='e', padx=5, pady=5)
        self.daily_profit_entry = ttk.Entry(settings_frame, style='Light.TEntry')
        self.daily_profit_entry.insert(0, str(self.bot.daily_profit_limit))
        self.daily_profit_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(settings_frame, text="Risk per Trade (%):", style='Light.TLabel').grid(row=2, column=0, sticky='e', padx=5, pady=5)
        self.risk_percent_entry = ttk.Entry(settings_frame, style='Light.TEntry')
        self.risk_percent_entry.insert(0, str(self.bot.risk_percentage))
        self.risk_percent_entry.grid(row=2, column=1, padx=5, pady=5)
        ttk.Label(settings_frame, text="Max Lot Size:", style='Light.TLabel').grid(row=3, column=0, sticky='e', padx=5, pady=5)
        self.max_lot_entry = ttk.Entry(settings_frame, style='Light.TEntry')
        self.max_lot_entry.insert(0, str(self.bot.max_lot))
        self.max_lot_entry.grid(row=3, column=1, padx=5, pady=5)
        # Drawdown control
        ttk.Label(settings_frame, text="Max Drawdown (%):", style='Light.TLabel').grid(row=4, column=0, sticky='e', padx=5, pady=5)
        self.drawdown_entry = ttk.Entry(settings_frame, style='Light.TEntry')
        self.drawdown_entry.insert(0, str(self.bot.max_drawdown_percent))
        self.drawdown_entry.grid(row=4, column=1, padx=5, pady=5)
        ttk.Button(settings_frame, text="Apply Settings", command=self.apply_risk_settings).grid(row=5, column=0, columnspan=2, pady=10)
        risk_btn_frame = ttk.Frame(settings_frame)
        risk_btn_frame.grid(row=6, column=0, columnspan=2, pady=5)
        risk_btn_frame.configure(style='Light.TFrame')
        ttk.Button(risk_btn_frame, text="Reset Risk Freeze", command=self.reset_risk_freeze).pack(side='left', padx=5)
        ttk.Button(risk_btn_frame, text="Update Balance", command=self.update_account_info).pack(side='left', padx=5)

    def setup_positions_table(self, parent):
        columns = ("ticket", "symbol", "type", "volume", "price", "sl", "tp", "profit")
        self.positions_tree = ttk.Treeview(parent, columns=columns, show="headings", height=5)
        self.positions_tree.heading("ticket", text="Ticket")
        self.positions_tree.heading("symbol", text="Symbol")
        self.positions_tree.heading("type", text="Type")
        self.positions_tree.heading("volume", text="Volume")
        self.positions_tree.heading("price", text="Price")
        self.positions_tree.heading("sl", text="SL")
        self.positions_tree.heading("tp", text="TP")
        self.positions_tree.heading("profit", text="P/L")
        self.positions_tree.column("ticket", width=60)
        self.positions_tree.column("symbol", width=80)
        self.positions_tree.column("type", width=80)
        self.positions_tree.column("volume", width=80)
        self.positions_tree.column("price", width=100)
        self.positions_tree.column("sl", width=100)
        self.positions_tree.column("tp", width=100)
        self.positions_tree.column("profit", width=100)
        style = ttk.Style()
        style.configure("Treeview", font=('Tahoma', 9), foreground="white", background="#34495e")
        style.configure("Treeview.Heading", font=('Tahoma', 10, 'bold'), background="#2c3e50", foreground="white")
        style.map("Treeview", background=[('selected', '#3498db')])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.positions_tree.yview)
        self.positions_tree.configure(yscrollcommand=scrollbar.set)
        self.positions_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def setup_reports_tab(self):
        self.reports_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.reports_tab, text="Reports & Charts")
        main_frame = ttk.Frame(self.reports_tab)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        chart_frame = ttk.LabelFrame(main_frame, text="Price Chart")
        chart_frame.pack(fill='both', expand=True, padx=5, pady=5)
        self.fig, self.ax = plt.subplots(figsize=(12, 5), facecolor='#2c3e50')
        self.fig.subplots_adjust(left=0.05, right=0.95, top=0.95, bottom=0.1)
        self.ax.set_facecolor('#34495e')
        self.ax.tick_params(axis='both', colors='white', labelsize=9)
        for spine in self.ax.spines.values():
            spine.set_color('#7f8c8d')
        self.canvas = FigureCanvasTkAgg(self.fig, chart_frame)
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        export_frame = ttk.LabelFrame(main_frame, text="Report Export")
        export_frame.pack(fill='x', padx=5, pady=5)
        btn_frame = ttk.Frame(export_frame)
        btn_frame.pack(fill='x', pady=10)
        ttk.Button(btn_frame, text="Daily Report (Excel)", style='ExportButton.TButton', command=lambda: self.export_reports("daily")).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Hourly Report (Excel)", style='ExportButton.TButton', command=lambda: self.export_reports("hourly")).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Open Positions (Excel)", style='ExportButton.TButton', command=self.export_positions).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Trade Journal (Excel)", style='ExportButton.TButton', command=self.export_trade_journal).pack(side='left', padx=10)

    def setup_log_tab(self):
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="Log")
        log_frame = ttk.LabelFrame(self.log_tab, text="Trading Log")
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, bg='#34495e', fg='#ecf0f1', insertbackground='white', font=('Consolas', 10))
        self.log_text.pack(fill='both', expand=True)
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill='x', pady=5)
        ttk.Button(log_btn_frame, text="Clear Log", command=self.clear_log).pack(side='left', padx=5)
        ttk.Button(log_btn_frame, text="Save Log", command=self.save_log).pack(side='left', padx=5)

    def log_message(self, message, level="info"):
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

    def show_notification(self, title, message):
        messagebox.showwarning(title, message)

    def start_bot(self):
        try:
            self.bot.lot_size = validate_positive_float(self.lot_entry.get(), self.bot.lot_size)
            self.bot.sl_pips = validate_positive_int(self.sl_entry.get(), self.bot.sl_pips)
            self.bot.tp_pips = validate_positive_int(self.tp_entry.get(), self.bot.tp_pips)
            self.bot.avoid_news = self.avoid_news_var.get()
            self.bot.trailing_stop = self.trailing_var.get()
            self.bot.trailing_distance = 50
            with self.bot.lock:
                self.bot.running = True
            self.status_var.set("Running...")
            self.log_message("Bot started", "info")
        except ValueError:
            self.log_message("Invalid input values", "error")

    def stop_bot(self):
        with self.bot.lock:
            self.bot.running = False
        self.status_var.set("Stopped")
        self.log_message("Bot stopped", "info")

    def close_positions(self):
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
            self.log_message(f"{len(positions)} positions closed", "trade")
        else:
            self.log_message("No positions to close", "info")

    def apply_risk_settings(self):
        try:
            self.bot.daily_loss_limit = float(self.daily_loss_entry.get())
            self.bot.daily_profit_limit = float(self.daily_profit_entry.get())
            self.bot.risk_percentage = float(self.risk_percent_entry.get())
            self.bot.max_lot = float(self.max_lot_entry.get())
            self.bot.max_drawdown_percent = float(self.drawdown_entry.get())
            self.log_message("Risk settings updated", "info")
        except ValueError:
            self.log_message("Invalid risk values", "error")

    def reset_risk_freeze(self):
        self.bot.risk_freeze = False
        self.bot.daily_pnl = 0
        self.log_message("Risk freeze reset", "info")

    def update_account_info(self):
        account_info = mt5.account_info()
        if account_info:
            self.balance_var.set(f"Balance: ${account_info.balance:.2f}")
            self.equity_var.set(f"Equity: ${account_info.equity:.2f}")
            self.margin_var.set(f"Margin: ${account_info.margin:.2f}")

    def update_price_chart(self):
        candles = self.bot.get_candles(count=100)
        if candles is None or len(candles) == 0:
            return
        self.ax.clear()
        prices = candles[['open', 'high', 'low', 'close']].values.flatten()
        min_price, max_price = np.nanmin(prices), np.nanmax(prices)
        price_range = max_price - min_price
        y_min = min_price - price_range * 0.05
        y_max = max_price + price_range * 0.05
        for i in range(len(candles)):
            color = '#2ecc71' if candles['close'].iloc[i] > candles['open'].iloc[i] else '#e74c3c'
            self.ax.vlines(i, candles['low'].iloc[i], candles['high'].iloc[i], color=color, linewidth=1)
            self.ax.vlines(i, min(candles['open'].iloc[i], candles['close'].iloc[i]), max(candles['open'].iloc[i], candles['close'].iloc[i]), color=color, linewidth=3)
        self.ax.set_ylim(y_min, y_max)
        self.ax.set_title(f"{self.bot.symbol} Price Chart (M5)", color='white', fontsize=12)
        self.ax.set_facecolor('#34495e')
        self.ax.grid(color='#7f8c8d', linestyle='--', alpha=0.3)
        self.ax.tick_params(colors='white', labelsize=9)
        self.canvas.draw()

    def update_countdown(self):
        minutes_left, seconds_left = self.bot.get_candle_countdown()
        self.countdown_var.set(f"{minutes_left:02d}:{seconds_left:02d}")

    def update_positions_table(self):
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        positions = self.bot.get_open_positions()
        for pos in positions:
            pos_type = "Buy" if pos.type == 0 else "Sell"
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
        while True:
            try:
                self.update_account_info()
                self.bot.reset_daily_limits()
                risk_status = self.bot.check_risk_limits()
                drawdown = self.bot.current_drawdown_percent
                self.risk_status_var.set(f"Risk Status: {risk_status or 'Normal'} / Drawdown: {drawdown:.2f}%")
                if risk_status == "drawdown_limit" and self.last_risk_status != "drawdown_limit":
                    self.log_message("Max Drawdown reached - trading stopped", "warning")
                    self.show_notification("Drawdown Alert", f"Drawdown exceeded {self.bot.max_drawdown_percent}%. Trading stopped!")
                elif risk_status == "loss_limit" and self.last_risk_status != "loss_limit":
                    self.log_message("Daily loss limit reached - trading stopped", "warning")
                    self.show_notification("Risk Alert", "Daily loss limit reached! Trading stopped.")
                elif risk_status == "profit_limit" and self.last_risk_status != "profit_limit":
                    self.log_message("Daily profit limit reached - trading stopped", "warning")
                    self.show_notification("Risk Alert", "Daily profit limit reached! Trading stopped.")
                self.last_risk_status = risk_status
                self.daily_pnl_var.set(f"Daily P/L: ${self.bot.daily_pnl:.2f}")
                self.update_price_chart()
                self.update_positions_table()
                self.update_countdown()
                with self.bot.lock:
                    running = self.bot.running
                if running and not self.bot.risk_freeze:
                    self.execute_trading()
                time.sleep(1)
            except Exception as e:
                self.log_message(f"Update error: {str(e)}", "error")
                time.sleep(10)

    def execute_trading(self):
        candles = self.bot.get_candles()
        if candles is None:
            self.log_message("Error getting price data", "error")
            return
        signal = self.bot.check_price_action(candles)
        if signal:
            result = self.bot.place_order(signal)
            if result and hasattr(result, "volume"):
                self.log_message(f"{signal.capitalize()} order sent, volume: {result.volume}", "trade")
            else:
                self.log_message("Error sending order", "error")
        if self.bot.trailing_stop:
            self.bot.update_trailing_stop()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log_message("Log cleared", "info")

    def save_log(self):
        try:
            with open(data_path("trading_log.txt"), "w", encoding="utf-8") as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.log_message("Log saved successfully", "info")
        except Exception as e:
            self.log_message(f"Error saving log: {str(e)}", "error")

    def export_reports(self, period):
        try:
            trades = self.bot.get_trade_history(period)
            if not trades:
                self.log_message(f"No trades found for {period} period", "warning")
                return
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Trade Report"
            headers = ["Date", "Symbol", "Type", "Volume", "Price", "SL", "TP", "Profit"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
            for row_num, trade in enumerate(trades, 2):
                trade_time = datetime.fromtimestamp(trade.time).strftime("%Y-%m-%d %H:%M:%S")
                trade_type = "Buy" if trade.type == 0 else "Sell"
                ws.cell(row=row_num, column=1, value=trade_time)
                ws.cell(row=row_num, column=2, value=trade.symbol)
                ws.cell(row=row_num, column=3, value=trade_type)
                ws.cell(row=row_num, column=4, value=trade.volume)
                ws.cell(row=row_num, column=5, value=trade.price)
                ws.cell(row=row_num, column=6, value=trade.sl)
                ws.cell(row=row_num, column=7, value=trade.tp)
                ws.cell(row=row_num, column=8, value=trade.profit)
            filename = data_path(f"trade_report_{period}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
            wb.save(filename)
            self.log_message(f"{period.capitalize()} report saved to {filename}", "info")
        except Exception as e:
            self.log_message(f"Error creating report: {str(e)}", "error")

    def export_positions(self):
        try:
            positions = self.bot.get_open_positions()
            if not positions:
                self.log_message("No open positions found", "warning")
                return
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Open Positions"
            headers = ["Ticket", "Symbol", "Type", "Volume", "Price", "SL", "TP", "Profit"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
            for row_num, pos in enumerate(positions, 2):
                pos_type = "Buy" if pos.type == 0 else "Sell"
                ws.cell(row=row_num, column=1, value=pos.ticket)
                ws.cell(row=row_num, column=2, value=pos.symbol)
                ws.cell(row=row_num, column=3, value=pos_type)
                ws.cell(row=row_num, column=4, value=pos.volume)
                ws.cell(row=row_num, column=5, value=pos.price_open)
                ws.cell(row=row_num, column=6, value=pos.sl)
                ws.cell(row=row_num, column=7, value=pos.tp)
                ws.cell(row=row_num, column=8, value=pos.profit)
            filename = data_path(f"open_positions_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
            wb.save(filename)
            self.log_message(f"Open positions saved to {filename}", "info")
        except Exception as e:
            self.log_message(f"Error creating positions report: {str(e)}", "error")

    def export_trade_journal(self):
        try:
            trades = self.bot.get_trade_history("all")
            if not trades:
                self.log_message("No trades found in journal", "warning")
                return
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Trade Journal"
            headers = ["Date", "Symbol", "Type", "Volume", "Price", "SL", "TP", "Profit", "Comment"]
            for col_num, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col_num, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
            for row_num, trade in enumerate(trades, 2):
                trade_time = datetime.fromtimestamp(trade.time).strftime("%Y-%m-%d %H:%M:%S")
                trade_type = "Buy" if trade.type == 0 else "Sell"
                ws.cell(row=row_num, column=1, value=trade_time)
                ws.cell(row=row_num, column=2, value=trade.symbol)
                ws.cell(row=row_num, column=3, value=trade_type)
                ws.cell(row=row_num, column=4, value=trade.volume)
                ws.cell(row=row_num, column=5, value=trade.price)
                ws.cell(row=row_num, column=6, value=trade.sl)
                ws.cell(row=row_num, column=7, value=trade.tp)
                ws.cell(row=row_num, column=8, value=trade.profit)
                ws.cell(row=row_num, column=9, value=trade.comment)
            filename = data_path(f"trade_journal_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
            wb.save(filename)
            self.log_message(f"Trade journal saved to {filename}", "info")
        except Exception as e:
            self.log_message(f"Error creating trade journal: {str(e)}", "error")

    def on_close(self):
        self.bot.save_settings()
        mt5.shutdown()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingGUI(root)
    root.mainloop()