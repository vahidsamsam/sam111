import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from pytz import timezone

class AdvancedTradingBot:
    def __init__(self):
        self.running = False
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
        self.daily_loss_limit = -100  # $
        self.daily_profit_limit = 200  # $
        self.daily_pnl = 0
        self.news_times = []
        
        # اتصال به متاتریدر
        self.connect_mt5()
        
    def connect_mt5(self):
        if not mt5.initialize():
            raise Exception(f"اتصال به MT5 ناموفق بود. خطا: {mt5.last_error()}")
        if not mt5.symbol_select(self.symbol, True):
            raise Exception(f"نماد {self.symbol} در دسترس نیست")

    def get_candles(self, count=100):
        candles = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
        return pd.DataFrame(candles) if candles is not None else None

    def calculate_rsi(self, candles, period=14):
        delta = candles['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def check_price_action(self, candles):
        if len(candles) < 3:
            return None
            
        current = candles.iloc[-1]
        previous = candles.iloc[-2]
        rsi = self.calculate_rsi(candles).iloc[-1]
        
        if current['close'] > previous['high'] and rsi < 70:
            return "buy"
        elif current['close'] < previous['low'] and rsi > 30:
            return "sell"
        return None

    def calculate_lot_size(self):
        account_info = mt5.account_info()
        if not account_info:
            return self.lot_size
            
        risk_amount = account_info.balance * (self.risk_percentage / 100)
        point_value = 1  # برای XAUUSD
        lot_size = risk_amount / (self.sl_pips * point_value)
        return round(min(lot_size, self.max_lot), 2)

    def place_order(self, signal):
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
        today = datetime.now().date()
        deals = mt5.history_deals_get(today, datetime.now())
        if deals:
            self.daily_pnl = sum(deal.profit for deal in deals)
        return self.daily_pnl

    def check_risk_limits(self):
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
        if now.hour == 0 and now.minute < 5:  # پنج دقیقه اول نیمه شب
            self.daily_pnl = 0
            self.risk_freeze = False
            return True
        return False

class TradingGUI:
    def __init__(self, root):
        self.root = root
        self.bot = AdvancedTradingBot()
        self.setup_ui()
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()

    def setup_ui(self):
        self.root.title("ربات معامله‌گر طلا")
        self.root.geometry("800x600")
        
        # تب‌های اصلی
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)
        
        # تب معاملات
        self.trade_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.trade_tab, text="معاملات")
        self.setup_trade_tab()
        
        # تب ریسک
        self.risk_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.risk_tab, text="مدیریت ریسک")
        self.setup_risk_tab()
        
        # تب گزارشات
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="گزارشات")
        self.setup_log_tab()
        
    def setup_trade_tab(self):
        frame = ttk.LabelFrame(self.trade_tab, text="تنظیمات معاملاتی")
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ورودی‌های معاملاتی
        ttk.Label(frame, text="حجم (لات):").grid(row=0, column=0)
        self.lot_entry = ttk.Entry(frame)
        self.lot_entry.insert(0, str(self.bot.lot_size))
        self.lot_entry.grid(row=0, column=1)
        
        ttk.Label(frame, text="حد ضرر (پیپ):").grid(row=1, column=0)
        self.sl_entry = ttk.Entry(frame)
        self.sl_entry.insert(0, str(self.bot.sl_pips))
        self.sl_entry.grid(row=1, column=1)
        
        ttk.Label(frame, text="حد سود (پیپ):").grid(row=2, column=0)
        self.tp_entry = ttk.Entry(frame)
        self.tp_entry.insert(0, str(self.bot.tp_pips))
        self.tp_entry.grid(row=2, column=1)
        
        # چک‌باکس‌ها
        self.avoid_news_var = tk.BooleanVar(value=self.bot.avoid_news)
        ttk.Checkbutton(frame, text="اجتناب از اخبار", variable=self.avoid_news_var).grid(row=3, column=0, columnspan=2)
        
        self.trailing_var = tk.BooleanVar(value=self.bot.trailing_stop)
        ttk.Checkbutton(frame, text="فعال کردن تریلینگ استاپ", variable=self.trailing_var).grid(row=4, column=0, columnspan=2)
        
        # دکمه‌های کنترل
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        
        ttk.Button(btn_frame, text="شروع ربات", command=self.start_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="توقف ربات", command=self.stop_bot).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="بستن معاملات", command=self.close_positions).pack(side='left', padx=5)
        
        # نمایش وضعیت
        self.status_var = tk.StringVar(value="آماده")
        ttk.Label(frame, textvariable=self.status_var).grid(row=6, column=0, columnspan=2)
        
    def setup_risk_tab(self):
        frame = ttk.LabelFrame(self.risk_tab, text="تنظیمات ریسک")
        frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # محدودیت‌های روزانه
        ttk.Label(frame, text="حد ضرر روزانه ($):").grid(row=0, column=0)
        self.daily_loss_entry = ttk.Entry(frame)
        self.daily_loss_entry.insert(0, str(self.bot.daily_loss_limit))
        self.daily_loss_entry.grid(row=0, column=1)
        
        ttk.Label(frame, text="حد سود روزانه ($):").grid(row=1, column=0)
        self.daily_profit_entry = ttk.Entry(frame)
        self.daily_profit_entry.insert(0, str(self.bot.daily_profit_limit))
        self.daily_profit_entry.grid(row=1, column=1)
        
        # درصد ریسک
        ttk.Label(frame, text="درصد ریسک هر معامله:").grid(row=2, column=0)
        self.risk_percent_entry = ttk.Entry(frame)
        self.risk_percent_entry.insert(0, str(self.bot.risk_percentage))
        self.risk_percent_entry.grid(row=2, column=1)
        
        # دکمه اعمال تنظیمات
        ttk.Button(frame, text="اعمال تنظیمات", command=self.apply_risk_settings).grid(row=3, column=0, columnspan=2)
        
        # نمایش وضعیت ریسک
        self.risk_status_var = tk.StringVar(value=f"سود/ضرر روزانه: ${self.bot.daily_pnl:.2f}")
        ttk.Label(frame, textvariable=self.risk_status_var).grid(row=4, column=0, columnspan=2)
        
    def setup_log_tab(self):
        self.log_text = tk.Text(self.log_tab, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(self.log_tab, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        
    def start_bot(self):
        try:
            self.bot.lot_size = float(self.lot_entry.get())
            self.bot.sl_pips = int(self.sl_entry.get())
            self.bot.tp_pips = int(self.tp_entry.get())
            self.bot.avoid_news = self.avoid_news_var.get()
            self.bot.trailing_stop = self.trailing_var.get()
            
            self.bot.running = True
            self.status_var.set("در حال اجرا...")
            self.log_message("ربات شروع به کار کرد")
        except ValueError:
            messagebox.showerror("خطا", "مقادیر وارد شده نامعتبر هستند")
            
    def stop_bot(self):
        self.bot.running = False
        self.status_var.set("متوقف شده")
        self.log_message("ربات متوقف شد")
        
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
            self.log_message(f"{len(positions)} معامله بسته شد")
        else:
            self.log_message("معامله‌ای برای بستن وجود ندارد")
            
    def apply_risk_settings(self):
        try:
            self.bot.daily_loss_limit = float(self.daily_loss_entry.get())
            self.bot.daily_profit_limit = float(self.daily_profit_entry.get())
            self.bot.risk_percentage = float(self.risk_percent_entry.get())
            self.log_message("تنظیمات ریسک به‌روزرسانی شد")
        except ValueError:
            messagebox.showerror("خطا", "مقادیر ریسک نامعتبر هستند")
            
    def update_loop(self):
        while True:
            try:
                # بروزرسانی وضعیت ریسک
                self.bot.reset_daily_limits()
                risk_status = self.bot.check_risk_limits()
                
                if risk_status == "loss_limit":
                    self.risk_status_var.set(f"توقف ضرر! (${self.bot.daily_pnl:.2f})")
                elif risk_status == "profit_limit":
                    self.risk_status_var.set(f"توقف سود! (${self.bot.daily_pnl:.2f})")
                else:
                    self.risk_status_var.set(f"سود/ضرر روزانه: ${self.bot.daily_pnl:.2f}")
                
                # اجرای معاملات اگر ربات فعال است
                if self.bot.running and not self.bot.risk_freeze:
                    self.execute_trading()
                    
                time.sleep(5)
            except Exception as e:
                self.log_message(f"خطا در به‌روزرسانی: {str(e)}")
                time.sleep(10)
                
    def execute_trading(self):
        candles = self.bot.get_candles()
        if candles is None:
            self.log_message("خطا در دریافت داده‌های قیمت")
            return
            
        signal = self.bot.check_price_action(candles)
        if signal:
            result = self.bot.place_order(signal)
            if result:
                self.log_message(f"سفارش {signal} با حجم {result.volume} ارسال شد")
            else:
                self.log_message("خطا در ارسال سفارش")
        
        if self.bot.trailing_stop:
            self.bot.update_trailing_stop()

# اجرای برنامه
if __name__ == "__main__":
    root = tk.Tk()
    app = TradingGUI(root)
    root.mainloop()
    
    # تمیزکاری پس از بسته شدن پنجره
    mt5.shutdown()