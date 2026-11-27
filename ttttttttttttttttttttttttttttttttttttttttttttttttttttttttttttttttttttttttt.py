import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

# Configure the page
st.set_page_config(
    page_title="ربات معاملاتی هوشمند",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import utility modules
from utils.technical_analysis import TechnicalAnalysis
from utils.signal_generator import SignalGenerator
from utils.data_handler import DataHandler

# Initialize session state
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = 'AAPL'
if 'timeframe' not in st.session_state:
    st.session_state.timeframe = '1d'
if 'period' not in st.session_state:
    st.session_state.period = '1y'

def main():
    st.title("🤖 ربات معاملاتی هوشمند")
    st.markdown("---")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ تنظیمات")
        
        # Asset class selection
        asset_class = st.selectbox(
            "نوع دارایی:",
            ["سهام (Stocks)", "ارزهای دیجیتال (Crypto)", "فارکس (Forex)", 
             "کالاها (Commodities)", "شاخص‌ها (Indices)"],
            help="نوع دارایی مورد نظر برای تحلیل را انتخاب کنید"
        )
        
        # Popular symbols based on asset class
        if asset_class == "سهام (Stocks)":
            popular_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NFLX", "NVDA"]
            help_text = "مثال: AAPL, MSFT, GOOGL"
        elif asset_class == "ارزهای دیجیتال (Crypto)":
            popular_symbols = ["BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "ADA-USD", "SOL-USD", "DOGE-USD"]
            help_text = "مثال: BTC-USD, ETH-USD, ADA-USD"
        elif asset_class == "فارکس (Forex)":
            popular_symbols = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X"]
            help_text = "مثال: EURUSD=X, GBPUSD=X, USDJPY=X"
        elif asset_class == "کالاها (Commodities)":
            popular_symbols = ["GC=F", "SI=F", "CL=F", "NG=F", "HG=F"]
            help_text = "مثال: GC=F (طلا), CL=F (نفت), SI=F (نقره)"
        else:  # Indices
            popular_symbols = ["^GSPC", "^DJI", "^IXIC", "^VIX", "^FTSE", "^N225"]
            help_text = "مثال: ^GSPC (S&P 500), ^DJI (Dow Jones)"
        
        # Quick selection buttons
        st.write("انتخاب سریع:")
        cols = st.columns(2)
        for i, pop_symbol in enumerate(popular_symbols[:8]):
            col = cols[i % 2]
            with col:
                if st.button(pop_symbol, key=f"quick_{pop_symbol}"):
                    st.session_state.selected_symbol = pop_symbol
                    st.rerun()
        
        # Symbol input
        symbol = st.text_input(
            "نماد دلخواه:",
            value=st.session_state.selected_symbol,
            help=help_text
        )
        
        # Symbol search and suggestions
        if symbol and symbol != st.session_state.selected_symbol:
            data_handler = DataHandler()
            search_results = data_handler.search_symbols(symbol)
            
            if search_results:
                st.write("پیشنهادات:")
                for result in search_results[:5]:
                    if st.button(
                        f"{result['symbol']} - {result['persian']} ({result['type']})",
                        key=f"suggest_{result['symbol']}"
                    ):
                        st.session_state.selected_symbol = result['symbol']
                        st.rerun()
        
        st.markdown("---")
        st.info("💡 برای مشاهده لیست کامل نمادها به صفحه **کاوشگر نمادها** مراجعه کنید")
        
        # Timeframe selection
        timeframe = st.selectbox(
            "بازه زمانی:",
            options=['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'],
            index=8,  # Default to '1d'
            help="بازه زمانی برای تحلیل"
        )
        
        # Period selection
        period = st.selectbox(
            "دوره زمانی:",
            options=['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'],
            index=5,  # Default to '1y'
            help="دوره زمانی داده‌ها"
        )
        
        # Update session state
        st.session_state.selected_symbol = symbol
        st.session_state.timeframe = timeframe
        st.session_state.period = period
        
        st.markdown("---")
        
        # Technical Analysis Parameters
        st.subheader("پارامترهای تحلیل تکنیکال")
        
        rsi_period = st.slider("دوره RSI:", min_value=5, max_value=50, value=14)
        sma_short = st.slider("SMA کوتاه:", min_value=5, max_value=50, value=20)
        sma_long = st.slider("SMA بلند:", min_value=20, max_value=200, value=50)
        ema_period = st.slider("دوره EMA:", min_value=5, max_value=50, value=12)
        
        # MACD Parameters
        macd_fast = st.slider("MACD سریع:", min_value=5, max_value=20, value=12)
        macd_slow = st.slider("MACD کند:", min_value=20, max_value=50, value=26)
        macd_signal = st.slider("سیگنال MACD:", min_value=5, max_value=15, value=9)
        
        # Risk Management
        st.subheader("مدیریت ریسک")
        stop_loss_pct = st.slider("درصد Stop Loss:", min_value=0.5, max_value=10.0, value=2.0, step=0.1)
        take_profit_pct = st.slider("درصد Take Profit:", min_value=1.0, max_value=20.0, value=4.0, step=0.1)
    
    # Main content
    try:
        # Load data
        data_handler = DataHandler()
        df = data_handler.get_market_data(symbol, period, timeframe)
        
        if df is None or df.empty:
            st.error(f"❌ خطا در دریافت داده‌ها برای نماد {symbol}")
            return
        
        # Technical Analysis
        ta = TechnicalAnalysis()
        df = ta.calculate_all_indicators(
            df, rsi_period, sma_short, sma_long, ema_period,
            macd_fast, macd_slow, macd_signal
        )
        
        # Signal Generation
        signal_gen = SignalGenerator()
        signals = signal_gen.generate_signals(df)
        df = pd.concat([df, signals], axis=1)
        
        # Current price and basic info
        current_price = df['Close'].iloc[-1]
        price_change = df['Close'].iloc[-1] - df['Close'].iloc[-2]
        price_change_pct = (price_change / df['Close'].iloc[-2]) * 100
        
        # Display current status
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="قیمت فعلی",
                value=f"${current_price:.2f}",
                delta=f"{price_change:+.2f} ({price_change_pct:+.2f}%)"
            )
        
        with col2:
            rsi_current = df['RSI'].iloc[-1]
            rsi_status = "خرید بیش‌ازحد" if rsi_current > 70 else "فروش بیش‌ازحد" if rsi_current < 30 else "خنثی"
            st.metric(
                label="RSI",
                value=f"{rsi_current:.2f}",
                delta=rsi_status
            )
        
        with col3:
            latest_signal = df['Signal'].iloc[-1]
            signal_color = "🟢" if latest_signal == 1 else "🔴" if latest_signal == -1 else "⚪"
            signal_text = "خرید" if latest_signal == 1 else "فروش" if latest_signal == -1 else "خنثی"
            st.metric(
                label="سیگنال فعلی",
                value=f"{signal_color} {signal_text}",
                delta=""
            )
        
        with col4:
            # Calculate Stop Loss and Take Profit
            if latest_signal == 1:  # Buy signal
                stop_loss = current_price * (1 - stop_loss_pct / 100)
                take_profit = current_price * (1 + take_profit_pct / 100)
            elif latest_signal == -1:  # Sell signal
                stop_loss = current_price * (1 + stop_loss_pct / 100)
                take_profit = current_price * (1 - take_profit_pct / 100)
            else:
                stop_loss = take_profit = current_price
            
            st.metric(
                label="Stop Loss",
                value=f"${stop_loss:.2f}",
                delta=f"Take Profit: ${take_profit:.2f}"
            )
        
        # Main chart
        st.subheader("📊 نمودار تحلیل تکنیکال")
        
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=['قیمت و میانگین‌های متحرک', 'RSI', 'MACD'],
            vertical_spacing=0.08,
            row_heights=[0.6, 0.2, 0.2]
        )
        
        # Price chart with moving averages
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='قیمت',
                increasing_line_color='green',
                decreasing_line_color='red'
            ),
            row=1, col=1
        )
        
        # Moving averages
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['SMA_Short'],
                mode='lines',
                name=f'SMA {sma_short}',
                line=dict(color='blue', width=1)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['SMA_Long'],
                mode='lines',
                name=f'SMA {sma_long}',
                line=dict(color='orange', width=1)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['EMA'],
                mode='lines',
                name=f'EMA {ema_period}',
                line=dict(color='purple', width=1)
            ),
            row=1, col=1
        )
        
        # Buy/Sell signals
        buy_signals = df[df['Signal'] == 1]
        sell_signals = df[df['Signal'] == -1]
        
        if not buy_signals.empty:
            fig.add_trace(
                go.Scatter(
                    x=buy_signals.index,
                    y=buy_signals['Close'],
                    mode='markers',
                    name='سیگنال خرید',
                    marker=dict(symbol='triangle-up', size=10, color='green')
                ),
                row=1, col=1
            )
        
        if not sell_signals.empty:
            fig.add_trace(
                go.Scatter(
                    x=sell_signals.index,
                    y=sell_signals['Close'],
                    mode='markers',
                    name='سیگنال فروش',
                    marker=dict(symbol='triangle-down', size=10, color='red')
                ),
                row=1, col=1
            )
        
        # RSI
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['RSI'],
                mode='lines',
                name='RSI',
                line=dict(color='purple', width=2)
            ),
            row=2, col=1
        )
        
        # RSI levels
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", row=2, col=1)
        
        # MACD
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MACD'],
                mode='lines',
                name='MACD',
                line=dict(color='blue', width=2)
            ),
            row=3, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['MACD_Signal'],
                mode='lines',
                name='سیگنال MACD',
                line=dict(color='red', width=1)
            ),
            row=3, col=1
        )
        
        # MACD histogram
        colors = ['green' if val >= 0 else 'red' for val in df['MACD_Histogram']]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['MACD_Histogram'],
                name='هیستوگرام MACD',
                marker_color=colors,
                opacity=0.7
            ),
            row=3, col=1
        )
        
        fig.update_layout(
            title=f"تحلیل تکنیکال {symbol}",
            xaxis_title="تاریخ",
            height=800,
            showlegend=True,
            template="plotly_white"
        )
        
        fig.update_xaxes(rangeslider_visible=False)
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Recent signals table
        st.subheader("📋 سیگنال‌های اخیر")
        
        # Get recent signals
        recent_signals = df[df['Signal'] != 0].tail(10)
        
        if not recent_signals.empty:
            signal_df = pd.DataFrame({
                'تاریخ': recent_signals.index.strftime('%Y-%m-%d %H:%M'),
                'قیمت': recent_signals['Close'].round(2),
                'سیگنال': recent_signals['Signal'].map({1: '🟢 خرید', -1: '🔴 فروش'}),
                'RSI': recent_signals['RSI'].round(2),
                'MACD': recent_signals['MACD'].round(4),
                'قوت سیگنال': recent_signals['Signal_Strength'].round(2)
            })
            
            st.dataframe(signal_df, use_container_width=True)
        else:
            st.info("هیچ سیگنالی در داده‌های اخیر یافت نشد.")
        
        # Performance metrics
        st.subheader("📈 معیارهای عملکرد")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Calculate some basic metrics
            returns = df['Close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252) * 100  # Annualized volatility
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() != 0 else 0
            
            st.metric("نوسانات سالانه", f"{volatility:.2f}%")
            st.metric("نسبت شارپ", f"{sharpe_ratio:.2f}")
        
        with col2:
            # Signal statistics
            total_signals = len(df[df['Signal'] != 0])
            buy_signals_count = len(df[df['Signal'] == 1])
            sell_signals_count = len(df[df['Signal'] == -1])
            
            st.metric("کل سیگنال‌ها", total_signals)
            st.metric("سیگنال خرید / فروش", f"{buy_signals_count} / {sell_signals_count}")
        
        # Latest market summary
        st.subheader("📊 خلاصه بازار")
        
        summary_data = {
            'شاخص': ['قیمت بازگشایی', 'بالاترین قیمت', 'پایین‌ترین قیمت', 'حجم معاملات'],
            'مقدار': [
                f"${df['Open'].iloc[-1]:.2f}",
                f"${df['High'].iloc[-1]:.2f}",
                f"${df['Low'].iloc[-1]:.2f}",
                f"{df['Volume'].iloc[-1]:,.0f}" if 'Volume' in df.columns else "N/A"
            ]
        }
        
        summary_df = pd.DataFrame(summary_data)
        st.dataframe(summary_df, hide_index=True, use_container_width=True)
        
    except Exception as e:
        st.error(f"❌ خطا در پردازش داده‌ها: {str(e)}")
        st.info("لطفاً نماد سهم صحیح وارد کنید و از اتصال اینترنت اطمینان حاصل کنید.")

if __name__ == "__main__":
    main()
import pandas as pd
import numpy as np

class SignalGenerator:
    def __init__(self):
        self.signal_weights = {
            'rsi': 0.25,
            'macd': 0.30,
            'sma_cross': 0.25,
            'bollinger': 0.20
        }
    
    def generate_rsi_signals(self, rsi, oversold=30, overbought=70):
        """Generate signals based on RSI"""
        signals = pd.Series(0, index=rsi.index)
        
        # Buy signal when RSI crosses above oversold level
        signals[(rsi.shift(1) <= oversold) & (rsi > oversold)] = 1
        
        # Sell signal when RSI crosses below overbought level
        signals[(rsi.shift(1) >= overbought) & (rsi < overbought)] = -1
        
        return signals
    
    def generate_macd_signals(self, macd, macd_signal):
        """Generate signals based on MACD crossover"""
        signals = pd.Series(0, index=macd.index)
        
        # Buy signal when MACD crosses above signal line
        signals[(macd.shift(1) <= macd_signal.shift(1)) & (macd > macd_signal)] = 1
        
        # Sell signal when MACD crosses below signal line
        signals[(macd.shift(1) >= macd_signal.shift(1)) & (macd < macd_signal)] = -1
        
        return signals
    
    def generate_sma_crossover_signals(self, sma_short, sma_long):
        """Generate signals based on SMA crossover"""
        signals = pd.Series(0, index=sma_short.index)
        
        # Buy signal when short SMA crosses above long SMA
        signals[(sma_short.shift(1) <= sma_long.shift(1)) & (sma_short > sma_long)] = 1
        
        # Sell signal when short SMA crosses below long SMA
        signals[(sma_short.shift(1) >= sma_long.shift(1)) & (sma_short < sma_long)] = -1
        
        return signals
    
    def generate_bollinger_signals(self, close, bb_upper, bb_lower):
        """Generate signals based on Bollinger Bands"""
        signals = pd.Series(0, index=close.index)
        
        # Buy signal when price touches lower band and bounces
        signals[(close.shift(1) <= bb_lower.shift(1)) & (close > bb_lower)] = 1
        
        # Sell signal when price touches upper band and falls
        signals[(close.shift(1) >= bb_upper.shift(1)) & (close < bb_upper)] = -1
        
        return signals
    
    def generate_stochastic_signals(self, stoch_k, stoch_d, oversold=20, overbought=80):
        """Generate signals based on Stochastic Oscillator"""
        signals = pd.Series(0, index=stoch_k.index)
        
        # Buy signal when %K crosses above %D in oversold territory
        signals[
            (stoch_k.shift(1) <= stoch_d.shift(1)) & 
            (stoch_k > stoch_d) & 
            (stoch_k < oversold)
        ] = 1
        
        # Sell signal when %K crosses below %D in overbought territory
        signals[
            (stoch_k.shift(1) >= stoch_d.shift(1)) & 
            (stoch_k < stoch_d) & 
            (stoch_k > overbought)
        ] = -1
        
        return signals
    
    def generate_williams_r_signals(self, williams_r, oversold=-80, overbought=-20):
        """Generate signals based on Williams %R"""
        signals = pd.Series(0, index=williams_r.index)
        
        # Buy signal when Williams %R crosses above oversold level
        signals[(williams_r.shift(1) <= oversold) & (williams_r > oversold)] = 1
        
        # Sell signal when Williams %R crosses below overbought level
        signals[(williams_r.shift(1) >= overbought) & (williams_r < overbought)] = -1
        
        return signals
    
    def calculate_signal_strength(self, signals_dict):
        """Calculate weighted signal strength"""
        weighted_signals = pd.Series(0.0, index=next(iter(signals_dict.values())).index)
        
        for signal_type, signals in signals_dict.items():
            if signal_type in self.signal_weights:
                weighted_signals += signals * self.signal_weights[signal_type]
        
        return weighted_signals
    
    def generate_volume_confirmation(self, volume, volume_sma, threshold=1.5):
        """Generate volume confirmation signals"""
        volume_ratio = volume / volume_sma
        return volume_ratio > threshold
    
    def apply_trend_filter(self, signals, trend_direction):
        """Filter signals based on overall trend"""
        filtered_signals = signals.copy()
        
        # In uptrend, favor buy signals; in downtrend, favor sell signals
        if trend_direction > 0:  # Uptrend
            filtered_signals[filtered_signals == -1] = 0  # Remove sell signals
        elif trend_direction < 0:  # Downtrend
            filtered_signals[filtered_signals == 1] = 0  # Remove buy signals
        
        return filtered_signals
    
    def generate_signals(self, df):
        """Generate comprehensive trading signals"""
        
        # Initialize results
        signals_df = pd.DataFrame(index=df.index)
        
        # Individual indicator signals
        rsi_signals = self.generate_rsi_signals(df['RSI'])
        macd_signals = self.generate_macd_signals(df['MACD'], df['MACD_Signal'])
        sma_signals = self.generate_sma_crossover_signals(df['SMA_Short'], df['SMA_Long'])
        bb_signals = self.generate_bollinger_signals(df['Close'], df['BB_Upper'], df['BB_Lower'])
        
        # Store individual signals
        signals_df['RSI_Signal'] = rsi_signals
        signals_df['MACD_Signal'] = macd_signals
        signals_df['SMA_Signal'] = sma_signals
        signals_df['BB_Signal'] = bb_signals
        
        # Additional signals if available
        if 'Stoch_K' in df.columns and 'Stoch_D' in df.columns:
            stoch_signals = self.generate_stochastic_signals(df['Stoch_K'], df['Stoch_D'])
            signals_df['Stoch_Signal'] = stoch_signals
        
        if 'Williams_R' in df.columns:
            williams_signals = self.generate_williams_r_signals(df['Williams_R'])
            signals_df['Williams_Signal'] = williams_signals
        
        # Calculate weighted signal strength
        main_signals = {
            'rsi': rsi_signals,
            'macd': macd_signals,
            'sma_cross': sma_signals,
            'bollinger': bb_signals
        }
        
        signal_strength = self.calculate_signal_strength(main_signals)
        signals_df['Signal_Strength'] = signal_strength
        
        # Generate final signal based on threshold
        final_signals = pd.Series(0, index=df.index)
        
        # Strong buy/sell thresholds
        buy_threshold = 0.6
        sell_threshold = -0.6
        
        final_signals[signal_strength >= buy_threshold] = 1
        final_signals[signal_strength <= sell_threshold] = -1
        
        signals_df['Signal'] = final_signals
        
        # Add volume confirmation if available
        if 'Volume' in df.columns and 'Volume_SMA' in df.columns:
            volume_confirmation = self.generate_volume_confirmation(
                df['Volume'], df['Volume_SMA']
            )
            signals_df['Volume_Confirmation'] = volume_confirmation
            
            # Apply volume filter to final signals
            volume_filtered_signals = final_signals.copy()
            volume_filtered_signals[~volume_confirmation] = 0
            signals_df['Volume_Filtered_Signal'] = volume_filtered_signals
        
        # Calculate signal consistency (how many indicators agree)
        signal_consistency = pd.Series(0, index=df.index)
        
        for idx in df.index:
            individual_signals = [
                rsi_signals.loc[idx],
                macd_signals.loc[idx],
                sma_signals.loc[idx],
                bb_signals.loc[idx]
            ]
            
            if final_signals.loc[idx] == 1:  # Buy signal
                signal_consistency.loc[idx] = sum([1 for s in individual_signals if s == 1])
            elif final_signals.loc[idx] == -1:  # Sell signal
                signal_consistency.loc[idx] = sum([1 for s in individual_signals if s == -1])
        
        signals_df['Signal_Consistency'] = signal_consistency
        
        # Add signal confidence (combination of strength and consistency)
        max_consistency = 4  # Number of main indicators
        signals_df['Signal_Confidence'] = (
            (np.abs(signal_strength) + (signal_consistency / max_consistency)) / 2
        ) * 100
        
        return signals_df
    
    def get_entry_exit_points(self, df, signals_df, atr_multiplier=2.0):
        """Calculate entry and exit points with stop loss and take profit"""
        
        entry_exit_df = pd.DataFrame(index=df.index)
        
        # Get signals
        signals = signals_df['Signal']
        
        # Calculate ATR-based stop loss and take profit
        atr = df['ATR']
        
        entry_points = []
        exit_points = []
        
        for i, (idx, signal) in enumerate(signals.items()):
            if signal != 0:  # Entry signal
                entry_price = df.loc[idx, 'Close']
                current_atr = atr.loc[idx]
                
                if signal == 1:  # Buy signal
                    stop_loss = entry_price - (current_atr * atr_multiplier)
                    take_profit = entry_price + (current_atr * atr_multiplier * 1.5)
                elif signal == -1:  # Sell signal
                    stop_loss = entry_price + (current_atr * atr_multiplier)
                    take_profit = entry_price - (current_atr * atr_multiplier * 1.5)
                
                entry_points.append({
                    'timestamp': idx,
                    'signal_type': 'Buy' if signal == 1 else 'Sell',
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'atr': current_atr
                })
        
        return entry_points
    
    def backtest_signals(self, df, signals_df, initial_capital=10000):
        """Simple backtest of generated signals"""
        
        capital = initial_capital
        position = 0
        trades = []
        equity_curve = []
        
        signals = signals_df['Signal']
        
        for idx, signal in signals.items():
            current_price = df.loc[idx, 'Close']
            
            if signal == 1 and position <= 0:  # Buy signal
                if position < 0:  # Close short position
                    pnl = position * (entry_price - current_price)
                    capital += pnl
                    trades.append({
                        'type': 'close_short',
                        'price': current_price,
                        'pnl': pnl,
                        'timestamp': idx
                    })
                
                # Open long position
                position = capital / current_price
                entry_price = current_price
                trades.append({
                    'type': 'buy',
                    'price': current_price,
                    'position': position,
                    'timestamp': idx
                })
                
            elif signal == -1 and position >= 0:  # Sell signal
                if position > 0:  # Close long position
                    pnl = position * (current_price - entry_price)
                    capital = position * current_price
                    trades.append({
                        'type': 'close_long',
                        'price': current_price,
                        'pnl': pnl,
                        'timestamp': idx
                    })
                
                # Open short position
                position = -capital / current_price
                entry_price = current_price
                trades.append({
                    'type': 'sell',
                    'price': current_price,
                    'position': position,
                    'timestamp': idx
                })
            
            # Calculate current equity
            if position > 0:
                current_equity = position * current_price
            elif position < 0:
                current_equity = capital + position * (entry_price - current_price)
            else:
                current_equity = capital
            
            equity_curve.append({
                'timestamp': idx,
                'equity': current_equity,
                'position': position
            })
        
        return {
            'trades': trades,
            'equity_curve': equity_curve,
            'final_capital': equity_curve[-1]['equity'] if equity_curve else initial_capital,
            'total_return': ((equity_curve[-1]['equity'] / initial_capital) - 1) * 100 if equity_curve else 0
        }
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings('ignore')


class DataHandler:

    def __init__(self):
        self.cache = {}
        self.cache_duration = timedelta(minutes=5)  # Cache data for 5 minutes

    def get_market_data(self, symbol, period='1y', interval='1d'):
        """
        Get market data from Yahoo Finance
        
        Parameters:
        - symbol: Stock symbol (e.g., 'AAPL', 'MSFT')
        - period: Data period ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
        - interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
        """

        cache_key = f"{symbol}_{period}_{interval}"

        # Check cache
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data

        try:
            # Create ticker object
            ticker = yf.Ticker(symbol)

            # Download data
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                print(f"No data found for symbol {symbol}")
                return None

            # Clean data
            df = self._clean_data(df)

            # Cache the data
            self.cache[cache_key] = (df, datetime.now())

            return df

        except Exception as e:
            print(f"Error fetching data for {symbol}: {str(e)}")
            return None

    def _clean_data(self, df):
        """Clean and validate market data"""

        # Remove any rows with missing data
        df = df.dropna()

        # Ensure positive values for OHLCV
        numeric_columns = ['Open', 'High', 'Low', 'Close']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = df[col].abs()

        if 'Volume' in df.columns:
            df['Volume'] = df['Volume'].abs()

        # Validate OHLC relationships
        df = df[(df['High'] >= df['Low']) & (df['High'] >= df['Open']) &
                (df['High'] >= df['Close']) & (df['Low'] <= df['Open']) &
                (df['Low'] <= df['Close'])]

        # Remove extreme outliers (price changes > 50%)
        if len(df) > 1:
            price_change = df['Close'].pct_change().abs()
            df = df[price_change <= 0.5]

        return df

    def get_company_info(self, symbol):
        """Get company information"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                'name': info.get('longName', symbol),
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
                'market_cap': info.get('marketCap', 0),
                'pe_ratio': info.get('trailingPE', 0),
                'dividend_yield': info.get('dividendYield', 0),
                'beta': info.get('beta', 0),
                'website': info.get('website', ''),
                'description': info.get('longBusinessSummary', '')
            }
        except Exception as e:
            print(f"Error fetching company info for {symbol}: {str(e)}")
            return None

    def get_financial_statements(self, symbol):
        """Get financial statements"""
        try:
            ticker = yf.Ticker(symbol)

            return {
                'income_statement': ticker.financials,
                'balance_sheet': ticker.balance_sheet,
                'cash_flow': ticker.cashflow
            }
        except Exception as e:
            print(
                f"Error fetching financial statements for {symbol}: {str(e)}")
            return None

    def get_multiple_symbols_data(self, symbols, period='1y', interval='1d'):
        """Get data for multiple symbols"""
        data = {}

        for symbol in symbols:
            df = self.get_market_data(symbol, period, interval)
            if df is not None:
                data[symbol] = df

        return data

    def get_market_indices(self):
        """Get major market indices data"""
        indices = {
            'S&P 500': '^GSPC',
            'Dow Jones': '^DJI',
            'NASDAQ': '^IXIC',
            'Russell 2000': '^RUT',
            'VIX': '^VIX'
        }

        indices_data = {}

        for name, symbol in indices.items():
            df = self.get_market_data(symbol, period='1y', interval='1d')
            if df is not None:
                indices_data[name] = {
                    'symbol':
                    symbol,
                    'current_price':
                    df['Close'].iloc[-1],
                    'change':
                    df['Close'].iloc[-1] - df['Close'].iloc[-2],
                    'change_pct':
                    ((df['Close'].iloc[-1] / df['Close'].iloc[-2]) - 1) * 100
                }

        return indices_data

    def get_crypto_data(self, symbol, period='1y', interval='1d'):
        """Get cryptocurrency data"""
        # Add -USD suffix for crypto symbols if not present
        if not symbol.endswith('-USD'):
            symbol = f"{symbol}-USD"

        return self.get_market_data(symbol, period, interval)
    
    def get_all_supported_symbols(self):
        """Get comprehensive list of supported symbols"""
        return {
            'stocks': {
                'US_Major': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NFLX', 'NVDA', 'AMD', 'INTC'],
                'US_Financial': ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF'],
                'US_Energy': ['XOM', 'CVX', 'COP', 'EOG', 'SLB', 'MPC', 'VLO', 'PSX', 'KMI', 'OKE'],
                'US_Healthcare': ['JNJ', 'PFE', 'UNH', 'MRK', 'ABBV', 'TMO', 'DHR', 'BMY', 'AMGN', 'GILD']
            },
            'crypto': {
                'Major': ['BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD', 'ADA-USD', 'SOL-USD', 'DOGE-USD', 'DOT-USD'],
                'DeFi': ['UNI-USD', 'LINK-USD', 'AAVE-USD', 'COMP-USD', 'MKR-USD', 'SUSHI-USD', 'CRV-USD', 'YFI-USD'],
                'Layer1': ['AVAX-USD', 'ALGO-USD', 'ATOM-USD', 'NEAR-USD', 'FTM-USD', 'ONE-USD', 'HBAR-USD', 'ICP-USD'],
                'Meme': ['SHIB-USD', 'PEPE-USD', 'FLOKI-USD', 'BONK-USD', 'WIF-USD', 'BRETT-USD']
            },
            'forex': {
                'Major_Pairs': ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCHF=X', 'AUDUSD=X', 'USDCAD=X', 'NZDUSD=X'],
                'Minor_Pairs': ['EURGBP=X', 'EURJPY=X', 'GBPJPY=X', 'EURCHF=X', 'AUDCAD=X', 'GBPAUD=X', 'AUDNZD=X'],
                'Exotic_Pairs': ['USDTRY=X', 'USDZAR=X', 'USDMXN=X', 'USDBRL=X', 'USDINR=X', 'USDCNY=X', 'USDSGD=X'],
                'Middle_East': ['USDAED=X', 'USDSAR=X', 'USDQAR=X', 'USDKWD=X', 'USDBHD=X', 'USDOMR=X']
            },
            'commodities': {
                'Precious_Metals': ['GC=F', 'SI=F', 'PL=F', 'PA=F'],  # Gold, Silver, Platinum, Palladium
                'Energy': ['CL=F', 'NG=F', 'BZ=F', 'RB=F'],  # Crude Oil, Natural Gas, Brent, RBOB Gas
                'Agricultural': ['ZC=F', 'ZW=F', 'ZS=F', 'ZL=F', 'ZM=F', 'CC=F', 'KC=F', 'SB=F'],  # Corn, Wheat, Soybeans, etc.
                'Industrial': ['HG=F', 'ALI=F']  # Copper, Aluminum
            },
            'indices': {
                'US': ['^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX'],
                'International': ['^FTSE', '^GDAXI', '^FCHI', '^N225', '^HSI', '^AXJO'],
                'Emerging': ['^BSESN', '^NSEI', '^MXX', '^BVSP', '^TA125.TA']
            },
            'bonds': {
                'US_Treasury': ['^TNX', '^FVX', '^TYX', '^IRX'],  # 10Y, 5Y, 30Y, 3M
                'International': ['^TNX', 'IEBT.L', 'EXS2.DE']
            }
        }

    def get_forex_data(self,
                       base_currency,
                       quote_currency='USD',
                       period='1y',
                       interval='1d'):
        """Get forex data"""
        symbol = f"{base_currency}{quote_currency}=X"
        return self.get_market_data(symbol, period, interval)

    def validate_symbol(self, symbol):
        """Validate if a symbol exists"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d')
            return not hist.empty
        except:
            return False

    def search_symbols(self, query):
        """Enhanced symbol search across all asset classes"""
        query_lower = query.lower().strip()
        matches = []
        
        # Enhanced symbol mappings with Persian names
        symbol_mappings = {
            # Cryptocurrencies
            'bitcoin': {'symbol': 'BTC-USD', 'name': 'Bitcoin', 'persian': 'بیت کوین', 'type': 'Crypto'},
            'ethereum': {'symbol': 'ETH-USD', 'name': 'Ethereum', 'persian': 'اتریوم', 'type': 'Crypto'},
            'binance': {'symbol': 'BNB-USD', 'name': 'Binance Coin', 'persian': 'بایننس کوین', 'type': 'Crypto'},
            'ripple': {'symbol': 'XRP-USD', 'name': 'XRP', 'persian': 'ریپل', 'type': 'Crypto'},
            'cardano': {'symbol': 'ADA-USD', 'name': 'Cardano', 'persian': 'کاردانو', 'type': 'Crypto'},
            'solana': {'symbol': 'SOL-USD', 'name': 'Solana', 'persian': 'سولانا', 'type': 'Crypto'},
            'dogecoin': {'symbol': 'DOGE-USD', 'name': 'Dogecoin', 'persian': 'دوج کوین', 'type': 'Crypto'},
            'polkadot': {'symbol': 'DOT-USD', 'name': 'Polkadot', 'persian': 'پولکادات', 'type': 'Crypto'},
            'chainlink': {'symbol': 'LINK-USD', 'name': 'Chainlink', 'persian': 'چین لینک', 'type': 'Crypto'},
            'uniswap': {'symbol': 'UNI-USD', 'name': 'Uniswap', 'persian': 'یونی سواپ', 'type': 'Crypto'},
            
            # Stocks  
            'apple': {'symbol': 'AAPL', 'name': 'Apple Inc.', 'persian': 'اپل', 'type': 'Stock'},
            'microsoft': {'symbol': 'MSFT', 'name': 'Microsoft', 'persian': 'مایکروسافت', 'type': 'Stock'},
            'google': {'symbol': 'GOOGL', 'name': 'Alphabet Inc.', 'persian': 'گوگل', 'type': 'Stock'},
            'amazon': {'symbol': 'AMZN', 'name': 'Amazon', 'persian': 'آمازون', 'type': 'Stock'},
            'tesla': {'symbol': 'TSLA', 'name': 'Tesla', 'persian': 'تسلا', 'type': 'Stock'},
            'meta': {'symbol': 'META', 'name': 'Meta Platforms', 'persian': 'متا', 'type': 'Stock'},
            'netflix': {'symbol': 'NFLX', 'name': 'Netflix', 'persian': 'نت فلیکس', 'type': 'Stock'},
            'nvidia': {'symbol': 'NVDA', 'name': 'NVIDIA', 'persian': 'انویدیا', 'type': 'Stock'},
            
            # Forex
            'euro': {'symbol': 'EURUSD=X', 'name': 'EUR/USD', 'persian': 'یورو/دلار', 'type': 'Forex'},
            'pound': {'symbol': 'GBPUSD=X', 'name': 'GBP/USD', 'persian': 'پوند/دلار', 'type': 'Forex'},
            'yen': {'symbol': 'USDJPY=X', 'name': 'USD/JPY', 'persian': 'دلار/ین', 'type': 'Forex'},
            'swiss': {'symbol': 'USDCHF=X', 'name': 'USD/CHF', 'persian': 'دلار/فرانک سوئیس', 'type': 'Forex'},
            'australian': {'symbol': 'AUDUSD=X', 'name': 'AUD/USD', 'persian': 'دلار استرالیا/دلار', 'type': 'Forex'},
            'canadian': {'symbol': 'USDCAD=X', 'name': 'USD/CAD', 'persian': 'دلار/دلار کانادا', 'type': 'Forex'},
            'turkish': {'symbol': 'USDTRY=X', 'name': 'USD/TRY', 'persian': 'دلار/لیر ترکیه', 'type': 'Forex'},
            
            # Commodities
            'gold': {'symbol': 'GC=F', 'name': 'Gold Futures', 'persian': 'طلا', 'type': 'Commodity'},
            'silver': {'symbol': 'SI=F', 'name': 'Silver Futures', 'persian': 'نقره', 'type': 'Commodity'},
            'oil': {'symbol': 'CL=F', 'name': 'Crude Oil', 'persian': 'نفت خام', 'type': 'Commodity'},
            'gas': {'symbol': 'NG=F', 'name': 'Natural Gas', 'persian': 'گاز طبیعی', 'type': 'Commodity'},
            'copper': {'symbol': 'HG=F', 'name': 'Copper Futures', 'persian': 'مس', 'type': 'Commodity'},
            
            # Indices
            'sp500': {'symbol': '^GSPC', 'name': 'S&P 500', 'persian': 'اس اند پی 500', 'type': 'Index'},
            'nasdaq': {'symbol': '^IXIC', 'name': 'NASDAQ', 'persian': 'نزداک', 'type': 'Index'},
            'dow': {'symbol': '^DJI', 'name': 'Dow Jones', 'persian': 'داو جونز', 'type': 'Index'},
            'vix': {'symbol': '^VIX', 'name': 'VIX Fear Index', 'persian': 'شاخص ترس', 'type': 'Index'}
        }
        
        # Search in symbol mappings
        for key, info in symbol_mappings.items():
            if (query_lower in key or 
                query_lower in info['name'].lower() or 
                query_lower in info['persian'] or
                query_lower == info['symbol'].lower()):
                matches.append({
                    'symbol': info['symbol'],
                    'name': info['name'],
                    'persian': info['persian'],
                    'type': info['type']
                })
        
        # If no matches found, try direct symbol lookup
        if not matches:
            # Try common crypto patterns
            if query_lower.endswith('usd') or query_lower.endswith('-usd'):
                test_symbol = query_lower.replace('usd', '').replace('-', '').upper() + '-USD'
                matches.append({
                    'symbol': test_symbol,
                    'name': f'{test_symbol.split("-")[0]} Cryptocurrency',
                    'persian': f'ارز دیجیتال {test_symbol.split("-")[0]}',
                    'type': 'Crypto'
                })
            
            # Try forex patterns
            elif len(query_lower) == 6 and query_lower.isalpha():
                test_symbol = query_lower[:3].upper() + query_lower[3:].upper() + '=X'
                matches.append({
                    'symbol': test_symbol,
                    'name': f'{query_lower[:3].upper()}/{query_lower[3:].upper()}',
                    'persian': f'{query_lower[:3].upper()}/{query_lower[3:].upper()}',
                    'type': 'Forex'
                })
            
            # Try direct symbol
            else:
                matches.append({
                    'symbol': query_lower.upper(),
                    'name': query_lower.upper(),
                    'persian': query_lower.upper(),
                    'type': 'Unknown'
                })
        
        return matches[:10]  # Return top 10 matches
    
    def get_symbol_type(self, symbol):
        """Determine symbol type"""
        symbol_upper = symbol.upper()
        
        if symbol_upper.endswith('-USD'):
            return 'cryptocurrency'
        elif symbol_upper.endswith('=X'):
            return 'forex'
        elif symbol_upper.endswith('=F'):
            return 'commodity'
        elif symbol_upper.startswith('^'):
            return 'index'
        else:
            return 'stock'

    def get_real_time_price(self, symbol):
        """Get real-time price (actually latest available price)"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d', interval='1m')

            if not data.empty:
                return {
                    'price':
                    data['Close'].iloc[-1],
                    'timestamp':
                    data.index[-1],
                    'volume':
                    data['Volume'].iloc[-1] if 'Volume' in data.columns else 0
                }
            return None
        except Exception as e:
            print(f"Error fetching real-time price for {symbol}: {str(e)}")
            return None

    def calculate_correlation_matrix(self, symbols, period='1y'):
        """Calculate correlation matrix for multiple symbols"""
        data = {}

        for symbol in symbols:
            df = self.get_market_data(symbol, period=period)
            if df is not None:
                data[symbol] = df['Close']

        if len(data) < 2:
            return None

        # Create DataFrame with all closing prices
        price_df = pd.DataFrame(data)

        # Calculate returns
        returns_df = price_df.pct_change().dropna()

        # Calculate correlation matrix
        correlation_matrix = returns_df.corr()

        return correlation_matrix

    def get_sector_performance(self):
        """Get sector performance data"""
        sector_etfs = {
            'Technology': 'XLK',
            'Healthcare': 'XLV',
            'Financial': 'XLF',
            'Energy': 'XLE',
            'Consumer Discretionary': 'XLY',
            'Consumer Staples': 'XLP',
            'Industrials': 'XLI',
            'Materials': 'XLB',
            'Utilities': 'XLU',
            'Real Estate': 'XLRE',
            'Communication': 'XLC'
        }

        sector_data = {}

        for sector, etf in sector_etfs.items():
            df = self.get_market_data(etf, period='1mo', interval='1d')
            if df is not None:
                current_price = df['Close'].iloc[-1]
                start_price = df['Close'].iloc[0]
                performance = ((current_price / start_price) - 1) * 100

                sector_data[sector] = {
                    'etf': etf,
                    'current_price': current_price,
                    'performance_1m': performance
                }

        return sector_data
import pandas as pd
import numpy as np
import talib

class TechnicalAnalysis:
    def __init__(self):
        pass
    
    def calculate_rsi(self, data, period=14):
        """Calculate Relative Strength Index"""
        try:
            return talib.RSI(data, timeperiod=period)
        except:
            # Fallback implementation if talib is not available
            delta = data.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi
    
    def calculate_sma(self, data, period):
        """Calculate Simple Moving Average"""
        try:
            return talib.SMA(data, timeperiod=period)
        except:
            return data.rolling(window=period).mean()
    
    def calculate_ema(self, data, period):
        """Calculate Exponential Moving Average"""
        try:
            return talib.EMA(data, timeperiod=period)
        except:
            return data.ewm(span=period).mean()
    
    def calculate_macd(self, data, fast_period=12, slow_period=26, signal_period=9):
        """Calculate MACD"""
        try:
            macd, macd_signal, macd_hist = talib.MACD(
                data, fastperiod=fast_period, slowperiod=slow_period, signalperiod=signal_period
            )
            return macd, macd_signal, macd_hist
        except:
            # Fallback implementation
            ema_fast = data.ewm(span=fast_period).mean()
            ema_slow = data.ewm(span=slow_period).mean()
            macd = ema_fast - ema_slow
            macd_signal = macd.ewm(span=signal_period).mean()
            macd_hist = macd - macd_signal
            return macd, macd_signal, macd_hist
    
    def calculate_bollinger_bands(self, data, period=20, std_dev=2):
        """Calculate Bollinger Bands"""
        try:
            bb_upper, bb_middle, bb_lower = talib.BBANDS(
                data, timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev
            )
            return bb_upper, bb_middle, bb_lower
        except:
            sma = data.rolling(window=period).mean()
            std = data.rolling(window=period).std()
            bb_upper = sma + (std * std_dev)
            bb_lower = sma - (std * std_dev)
            return bb_upper, sma, bb_lower
    
    def calculate_stochastic(self, high, low, close, k_period=14, d_period=3):
        """Calculate Stochastic Oscillator"""
        try:
            slowk, slowd = talib.STOCH(
                high, low, close, fastk_period=k_period, slowk_period=3, slowd_period=d_period
            )
            return slowk, slowd
        except:
            lowest_low = low.rolling(window=k_period).min()
            highest_high = high.rolling(window=k_period).max()
            k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
            d_percent = k_percent.rolling(window=d_period).mean()
            return k_percent, d_percent
    
    def calculate_atr(self, high, low, close, period=14):
        """Calculate Average True Range"""
        try:
            return talib.ATR(high, low, close, timeperiod=period)
        except:
            high_low = high - low
            high_close = np.abs(high - close.shift())
            low_close = np.abs(low - close.shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            return true_range.rolling(window=period).mean()
    
    def calculate_williams_r(self, high, low, close, period=14):
        """Calculate Williams %R"""
        try:
            return talib.WILLR(high, low, close, timeperiod=period)
        except:
            highest_high = high.rolling(window=period).max()
            lowest_low = low.rolling(window=period).min()
            williams_r = -100 * ((highest_high - close) / (highest_high - lowest_low))
            return williams_r
    
    def calculate_all_indicators(self, df, rsi_period=14, sma_short=20, sma_long=50, 
                               ema_period=12, macd_fast=12, macd_slow=26, macd_signal=9):
        """Calculate all technical indicators"""
        
        # Ensure we have OHLCV columns
        required_columns = ['Open', 'High', 'Low', 'Close']
        for col in required_columns:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Make a copy to avoid modifying original data
        df_copy = df.copy()
        
        # RSI
        df_copy['RSI'] = self.calculate_rsi(df_copy['Close'], rsi_period)
        
        # Moving Averages
        df_copy['SMA_Short'] = self.calculate_sma(df_copy['Close'], sma_short)
        df_copy['SMA_Long'] = self.calculate_sma(df_copy['Close'], sma_long)
        df_copy['EMA'] = self.calculate_ema(df_copy['Close'], ema_period)
        
        # MACD
        macd, macd_sig, macd_hist = self.calculate_macd(
            df_copy['Close'], macd_fast, macd_slow, macd_signal
        )
        df_copy['MACD'] = macd
        df_copy['MACD_Signal'] = macd_sig
        df_copy['MACD_Histogram'] = macd_hist
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self.calculate_bollinger_bands(df_copy['Close'])
        df_copy['BB_Upper'] = bb_upper
        df_copy['BB_Middle'] = bb_middle
        df_copy['BB_Lower'] = bb_lower
        
        # Stochastic
        stoch_k, stoch_d = self.calculate_stochastic(
            df_copy['High'], df_copy['Low'], df_copy['Close']
        )
        df_copy['Stoch_K'] = stoch_k
        df_copy['Stoch_D'] = stoch_d
        
        # ATR
        df_copy['ATR'] = self.calculate_atr(
            df_copy['High'], df_copy['Low'], df_copy['Close']
        )
        
        # Williams %R
        df_copy['Williams_R'] = self.calculate_williams_r(
            df_copy['High'], df_copy['Low'], df_copy['Close']
        )
        
        # Price change and returns
        df_copy['Price_Change'] = df_copy['Close'].pct_change()
        df_copy['Price_Change_Abs'] = df_copy['Close'].diff()
        
        # Volume indicators (if volume is available)
        if 'Volume' in df_copy.columns:
            df_copy['Volume_SMA'] = self.calculate_sma(df_copy['Volume'], 20)
            df_copy['Volume_Ratio'] = df_copy['Volume'] / df_copy['Volume_SMA']
        
        return df_copy
    
    def get_trend_direction(self, df):
        """Determine overall trend direction"""
        latest_idx = -1
        
        # SMA trend
        sma_trend = 1 if df['SMA_Short'].iloc[latest_idx] > df['SMA_Long'].iloc[latest_idx] else -1
        
        # EMA vs Price
        ema_trend = 1 if df['Close'].iloc[latest_idx] > df['EMA'].iloc[latest_idx] else -1
        
        # MACD trend
        macd_trend = 1 if df['MACD'].iloc[latest_idx] > df['MACD_Signal'].iloc[latest_idx] else -1
        
        # Overall trend (majority vote)
        trend_votes = [sma_trend, ema_trend, macd_trend]
        overall_trend = 1 if sum(trend_votes) > 0 else -1
        
        return {
            'sma_trend': sma_trend,
            'ema_trend': ema_trend,
            'macd_trend': macd_trend,
            'overall_trend': overall_trend
        }
    
    def get_support_resistance_levels(self, df, window=20):
        """Calculate support and resistance levels"""
        highs = df['High'].rolling(window=window).max()
        lows = df['Low'].rolling(window=window).min()
        
        # Find local peaks and troughs
        resistance_levels = []
        support_levels = []
        
        for i in range(window, len(df) - window):
            if df['High'].iloc[i] == highs.iloc[i]:
                resistance_levels.append(df['High'].iloc[i])
            if df['Low'].iloc[i] == lows.iloc[i]:
                support_levels.append(df['Low'].iloc[i])
        
        return {
            'resistance': sorted(set(resistance_levels), reverse=True)[:5],  # Top 5 resistance
            'support': sorted(set(support_levels))[:5]  # Top 5 support
        }
import pandas as pd
import numpy as np

class SignalGenerator:
    def __init__(self):
        self.signal_weights = {
            'rsi': 0.25,
            'macd': 0.30,
            'sma_cross': 0.25,
            'bollinger': 0.20
        }
    
    def generate_rsi_signals(self, rsi, oversold=30, overbought=70):
        """Generate signals based on RSI"""
        signals = pd.Series(0, index=rsi.index)
        
        # Buy signal when RSI crosses above oversold level
        signals[(rsi.shift(1) <= oversold) & (rsi > oversold)] = 1
        
        # Sell signal when RSI crosses below overbought level
        signals[(rsi.shift(1) >= overbought) & (rsi < overbought)] = -1
        
        return signals
    
    def generate_macd_signals(self, macd, macd_signal):
        """Generate signals based on MACD crossover"""
        signals = pd.Series(0, index=macd.index)
        
        # Buy signal when MACD crosses above signal line
        signals[(macd.shift(1) <= macd_signal.shift(1)) & (macd > macd_signal)] = 1
        
        # Sell signal when MACD crosses below signal line
        signals[(macd.shift(1) >= macd_signal.shift(1)) & (macd < macd_signal)] = -1
        
        return signals
    
    def generate_sma_crossover_signals(self, sma_short, sma_long):
        """Generate signals based on SMA crossover"""
        signals = pd.Series(0, index=sma_short.index)
        
        # Buy signal when short SMA crosses above long SMA
        signals[(sma_short.shift(1) <= sma_long.shift(1)) & (sma_short > sma_long)] = 1
        
        # Sell signal when short SMA crosses below long SMA
        signals[(sma_short.shift(1) >= sma_long.shift(1)) & (sma_short < sma_long)] = -1
        
        return signals
    
    def generate_bollinger_signals(self, close, bb_upper, bb_lower):
        """Generate signals based on Bollinger Bands"""
        signals = pd.Series(0, index=close.index)
        
        # Buy signal when price touches lower band and bounces
        signals[(close.shift(1) <= bb_lower.shift(1)) & (close > bb_lower)] = 1
        
        # Sell signal when price touches upper band and falls
        signals[(close.shift(1) >= bb_upper.shift(1)) & (close < bb_upper)] = -1
        
        return signals
    
    def generate_stochastic_signals(self, stoch_k, stoch_d, oversold=20, overbought=80):
        """Generate signals based on Stochastic Oscillator"""
        signals = pd.Series(0, index=stoch_k.index)
        
        # Buy signal when %K crosses above %D in oversold territory
        signals[
            (stoch_k.shift(1) <= stoch_d.shift(1)) & 
            (stoch_k > stoch_d) & 
            (stoch_k < oversold)
        ] = 1
        
        # Sell signal when %K crosses below %D in overbought territory
        signals[
            (stoch_k.shift(1) >= stoch_d.shift(1)) & 
            (stoch_k < stoch_d) & 
            (stoch_k > overbought)
        ] = -1
        
        return signals
    
    def generate_williams_r_signals(self, williams_r, oversold=-80, overbought=-20):
        """Generate signals based on Williams %R"""
        signals = pd.Series(0, index=williams_r.index)
        
        # Buy signal when Williams %R crosses above oversold level
        signals[(williams_r.shift(1) <= oversold) & (williams_r > oversold)] = 1
        
        # Sell signal when Williams %R crosses below overbought level
        signals[(williams_r.shift(1) >= overbought) & (williams_r < overbought)] = -1
        
        return signals
    
    def calculate_signal_strength(self, signals_dict):
        """Calculate weighted signal strength"""
        weighted_signals = pd.Series(0.0, index=next(iter(signals_dict.values())).index)
        
        for signal_type, signals in signals_dict.items():
            if signal_type in self.signal_weights:
                weighted_signals += signals * self.signal_weights[signal_type]
        
        return weighted_signals
    
    def generate_volume_confirmation(self, volume, volume_sma, threshold=1.5):
        """Generate volume confirmation signals"""
        volume_ratio = volume / volume_sma
        return volume_ratio > threshold
    
    def apply_trend_filter(self, signals, trend_direction):
        """Filter signals based on overall trend"""
        filtered_signals = signals.copy()
        
        # In uptrend, favor buy signals; in downtrend, favor sell signals
        if trend_direction > 0:  # Uptrend
            filtered_signals[filtered_signals == -1] = 0  # Remove sell signals
        elif trend_direction < 0:  # Downtrend
            filtered_signals[filtered_signals == 1] = 0  # Remove buy signals
        
        return filtered_signals
    
    def generate_signals(self, df):
        """Generate comprehensive trading signals"""
        
        # Initialize results
        signals_df = pd.DataFrame(index=df.index)
        
        # Individual indicator signals
        rsi_signals = self.generate_rsi_signals(df['RSI'])
        macd_signals = self.generate_macd_signals(df['MACD'], df['MACD_Signal'])
        sma_signals = self.generate_sma_crossover_signals(df['SMA_Short'], df['SMA_Long'])
        bb_signals = self.generate_bollinger_signals(df['Close'], df['BB_Upper'], df['BB_Lower'])
        
        # Store individual signals
        signals_df['RSI_Signal'] = rsi_signals
        signals_df['MACD_Signal'] = macd_signals
        signals_df['SMA_Signal'] = sma_signals
        signals_df['BB_Signal'] = bb_signals
        
        # Additional signals if available
        if 'Stoch_K' in df.columns and 'Stoch_D' in df.columns:
            stoch_signals = self.generate_stochastic_signals(df['Stoch_K'], df['Stoch_D'])
            signals_df['Stoch_Signal'] = stoch_signals
        
        if 'Williams_R' in df.columns:
            williams_signals = self.generate_williams_r_signals(df['Williams_R'])
            signals_df['Williams_Signal'] = williams_signals
        
        # Calculate weighted signal strength
        main_signals = {
            'rsi': rsi_signals,
            'macd': macd_signals,
            'sma_cross': sma_signals,
            'bollinger': bb_signals
        }
        
        signal_strength = self.calculate_signal_strength(main_signals)
        signals_df['Signal_Strength'] = signal_strength
        
        # Generate final signal based on threshold
        final_signals = pd.Series(0, index=df.index)
        
        # Strong buy/sell thresholds
        buy_threshold = 0.6
        sell_threshold = -0.6
        
        final_signals[signal_strength >= buy_threshold] = 1
        final_signals[signal_strength <= sell_threshold] = -1
        
        signals_df['Signal'] = final_signals
        
        # Add volume confirmation if available
        if 'Volume' in df.columns and 'Volume_SMA' in df.columns:
            volume_confirmation = self.generate_volume_confirmation(
                df['Volume'], df['Volume_SMA']
            )
            signals_df['Volume_Confirmation'] = volume_confirmation
            
            # Apply volume filter to final signals
            volume_filtered_signals = final_signals.copy()
            volume_filtered_signals[~volume_confirmation] = 0
            signals_df['Volume_Filtered_Signal'] = volume_filtered_signals
        
        # Calculate signal consistency (how many indicators agree)
        signal_consistency = pd.Series(0, index=df.index)
        
        for idx in df.index:
            individual_signals = [
                rsi_signals.loc[idx],
                macd_signals.loc[idx],
                sma_signals.loc[idx],
                bb_signals.loc[idx]
            ]
            
            if final_signals.loc[idx] == 1:  # Buy signal
                signal_consistency.loc[idx] = sum([1 for s in individual_signals if s == 1])
            elif final_signals.loc[idx] == -1:  # Sell signal
                signal_consistency.loc[idx] = sum([1 for s in individual_signals if s == -1])
        
        signals_df['Signal_Consistency'] = signal_consistency
        
        # Add signal confidence (combination of strength and consistency)
        max_consistency = 4  # Number of main indicators
        signals_df['Signal_Confidence'] = (
            (np.abs(signal_strength) + (signal_consistency / max_consistency)) / 2
        ) * 100
        
        return signals_df
    
    def get_entry_exit_points(self, df, signals_df, atr_multiplier=2.0):
        """Calculate entry and exit points with stop loss and take profit"""
        
        entry_exit_df = pd.DataFrame(index=df.index)
        
        # Get signals
        signals = signals_df['Signal']
        
        # Calculate ATR-based stop loss and take profit
        atr = df['ATR']
        
        entry_points = []
        exit_points = []
        
        for i, (idx, signal) in enumerate(signals.items()):
            if signal != 0:  # Entry signal
                entry_price = df.loc[idx, 'Close']
                current_atr = atr.loc[idx]
                
                if signal == 1:  # Buy signal
                    stop_loss = entry_price - (current_atr * atr_multiplier)
                    take_profit = entry_price + (current_atr * atr_multiplier * 1.5)
                elif signal == -1:  # Sell signal
                    stop_loss = entry_price + (current_atr * atr_multiplier)
                    take_profit = entry_price - (current_atr * atr_multiplier * 1.5)
                
                entry_points.append({
                    'timestamp': idx,
                    'signal_type': 'Buy' if signal == 1 else 'Sell',
                    'entry_price': entry_price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'atr': current_atr
                })
        
        return entry_points
    
    def backtest_signals(self, df, signals_df, initial_capital=10000):
        """Simple backtest of generated signals"""
        
        capital = initial_capital
        position = 0
        trades = []
        equity_curve = []
        
        signals = signals_df['Signal']
        
        for idx, signal in signals.items():
            current_price = df.loc[idx, 'Close']
            
            if signal == 1 and position <= 0:  # Buy signal
                if position < 0:  # Close short position
                    pnl = position * (entry_price - current_price)
                    capital += pnl
                    trades.append({
                        'type': 'close_short',
                        'price': current_price,
                        'pnl': pnl,
                        'timestamp': idx
                    })
                
                # Open long position
                position = capital / current_price
                entry_price = current_price
                trades.append({
                    'type': 'buy',
                    'price': current_price,
                    'position': position,
                    'timestamp': idx
                })
                
            elif signal == -1 and position >= 0:  # Sell signal
                if position > 0:  # Close long position
                    pnl = position * (current_price - entry_price)
                    capital = position * current_price
                    trades.append({
                        'type': 'close_long',
                        'price': current_price,
                        'pnl': pnl,
                        'timestamp': idx
                    })
                
                # Open short position
                position = -capital / current_price
                entry_price = current_price
                trades.append({
                    'type': 'sell',
                    'price': current_price,
                    'position': position,
                    'timestamp': idx
                })
            
            # Calculate current equity
            if position > 0:
                current_equity = position * current_price
            elif position < 0:
                current_equity = capital + position * (entry_price - current_price)
            else:
                current_equity = capital
            
            equity_curve.append({
                'timestamp': idx,
                'equity': current_equity,
                'position': position
            })
        
        return {
            'trades': trades,
            'equity_curve': equity_curve,
            'final_capital': equity_curve[-1]['equity'] if equity_curve else initial_capital,
            'total_return': ((equity_curve[-1]['equity'] / initial_capital) - 1) * 100 if equity_curve else 0
        }
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import numpy as np

def show_dashboard():
    st.title("📊 داشبورد مدیریت")
    
    # Portfolio overview section
    st.header("نمای کلی پرتفولیو")
    
    # Mock portfolio data - in a real app this would come from a database
    portfolio_data = {
        'Symbol': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'],
        'Shares': [100, 50, 30, 25, 40],
        'Entry Price': [150.25, 280.50, 2100.75, 3200.25, 650.50],
        'Current Price': [175.30, 310.25, 2250.50, 3150.75, 680.25],
        'P/L': [2505, 1487.5, 4492.5, -1237.5, 1190],
        'P/L %': [16.7, 10.6, 7.1, -1.5, 4.6]
    }
    
    portfolio_df = pd.DataFrame(portfolio_data)
    
    # Portfolio metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_value = sum(portfolio_df['Shares'] * portfolio_df['Current Price'])
        st.metric("ارزش کل پرتفولیو", f"${total_value:,.2f}")
    
    with col2:
        total_pnl = portfolio_df['P/L'].sum()
        st.metric("سود/زیان کل", f"${total_pnl:,.2f}", f"{total_pnl:+.2f}")
    
    with col3:
        avg_return = portfolio_df['P/L %'].mean()
        st.metric("متوسط بازده", f"{avg_return:.1f}%")
    
    with col4:
        winning_positions = len(portfolio_df[portfolio_df['P/L'] > 0])
        win_rate = (winning_positions / len(portfolio_df)) * 100
        st.metric("نرخ برد", f"{win_rate:.1f}%")
    
    # Portfolio table
    st.subheader("جزئیات پرتفولیو")
    
    # Format the dataframe for display
    display_df = portfolio_df.copy()
    display_df['Entry Price'] = display_df['Entry Price'].apply(lambda x: f"${x:.2f}")
    display_df['Current Price'] = display_df['Current Price'].apply(lambda x: f"${x:.2f}")
    display_df['P/L'] = display_df['P/L'].apply(lambda x: f"${x:,.2f}")
    display_df['P/L %'] = display_df['P/L %'].apply(lambda x: f"{x:+.1f}%")
    
    st.dataframe(display_df, use_container_width=True)
    
    # Portfolio allocation chart
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("تخصیص پرتفولیو")
        portfolio_values = portfolio_df['Shares'] * portfolio_df['Current Price']
        
        fig = px.pie(
            values=portfolio_values,
            names=portfolio_df['Symbol'],
            title="تخصیص بر اساس ارزش"
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("عملکرد سهام")
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=portfolio_df['Symbol'],
            y=portfolio_df['P/L %'],
            marker_color=['green' if x > 0 else 'red' for x in portfolio_df['P/L %']],
            text=portfolio_df['P/L %'].apply(lambda x: f"{x:+.1f}%"),
            textposition='auto'
        ))
        
        fig.update_layout(
            title="بازده هر سهم (%)",
            xaxis_title="نماد",
            yaxis_title="بازده (%)",
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Recent signals section
    st.header("سیگنال‌های اخیر")
    
    # Mock recent signals data
    recent_signals = {
        'تاریخ': ['2024-01-15 10:30', '2024-01-15 09:45', '2024-01-14 15:20', '2024-01-14 11:15'],
        'نماد': ['AAPL', 'MSFT', 'GOOGL', 'TSLA'],
        'سیگنال': ['🟢 خرید', '🔴 فروش', '🟢 خرید', '🔴 فروش'],
        'قیمت': [175.30, 310.25, 2250.50, 680.25],
        'قوت سیگنال': [0.85, 0.78, 0.92, 0.71],
        'وضعیت': ['فعال', 'بسته شده', 'فعال', 'بسته شده']
    }
    
    signals_df = pd.DataFrame(recent_signals)
    st.dataframe(signals_df, use_container_width=True)
    
    # Performance analytics
    st.header("تحلیل عملکرد")
    
    # Generate mock performance data
    dates = pd.date_range(start='2024-01-01', end='2024-01-15', freq='D')
    portfolio_values = 100000 + np.cumsum(np.random.normal(200, 1000, len(dates)))
    benchmark_values = 100000 + np.cumsum(np.random.normal(150, 800, len(dates)))
    
    performance_df = pd.DataFrame({
        'Date': dates,
        'Portfolio': portfolio_values,
        'Benchmark': benchmark_values
    })
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("منحنی عملکرد")
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=performance_df['Date'],
            y=performance_df['Portfolio'],
            mode='lines',
            name='پرتفولیو',
            line=dict(color='blue', width=2)
        ))
        
        fig.add_trace(go.Scatter(
            x=performance_df['Date'],
            y=performance_df['Benchmark'],
            mode='lines',
            name='شاخص مرجع',
            line=dict(color='gray', width=1, dash='dash')
        ))
        
        fig.update_layout(
            title="مقایسه عملکرد",
            xaxis_title="تاریخ",
            yaxis_title="ارزش ($)",
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("آمار عملکرد")
        
        # Calculate performance metrics
        portfolio_return = (portfolio_values[-1] / portfolio_values[0] - 1) * 100
        benchmark_return = (benchmark_values[-1] / benchmark_values[0] - 1) * 100
        
        portfolio_vol = np.std(np.diff(portfolio_values) / portfolio_values[:-1]) * np.sqrt(252) * 100
        sharpe_ratio = portfolio_return / portfolio_vol if portfolio_vol > 0 else 0
        
        max_drawdown = np.min(portfolio_values / np.maximum.accumulate(portfolio_values) - 1) * 100
        
        metrics_data = {
            'معیار': [
                'بازده کل (%)',
                'بازده شاخص مرجع (%)',
                'آلفا (%)',
                'نوسانات (%)',
                'نسبت شارپ',
                'حداکثر افت (%)'
            ],
            'مقدار': [
                f"{portfolio_return:.2f}",
                f"{benchmark_return:.2f}",
                f"{portfolio_return - benchmark_return:.2f}",
                f"{portfolio_vol:.2f}",
                f"{sharpe_ratio:.2f}",
                f"{max_drawdown:.2f}"
            ]
        }
        
        metrics_df = pd.DataFrame(metrics_data)
        st.dataframe(metrics_df, hide_index=True, use_container_width=True)
    
    # Risk metrics
    st.header("معیارهای ریسک")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("VaR روزانه (95%)", "-$2,340", help="ارزش در معرض ریسک با اطمینان 95%")
    
    with col2:
        st.metric("بتا پرتفولیو", "1.15", help="حساسیت نسبت به بازار")
    
    with col3:
        st.metric("ضریب همبستگی", "0.82", help="همبستگی با شاخص مرجع")
    
    # Trading activity
    st.header("فعالیت معاملاتی")
    
    # Mock trading data
    trading_data = {
        'امروز': [5, 3, 2, 8500],
        'این هفته': [23, 15, 8, 42300],
        'این ماه': [89, 52, 37, 168900]
    }
    
    trading_df = pd.DataFrame(
        trading_data,
        index=['تعداد معاملات', 'معاملات موفق', 'معاملات ناموفق', 'حجم معاملات ($)']
    ).T
    
    st.dataframe(trading_df, use_container_width=True)
    
    # Market sentiment
    st.header("حس و حال بازار")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Fear & Greed Index (mock)
        fear_greed_value = 65
        
        fig = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = fear_greed_value,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "شاخص ترس و طمع"},
            delta = {'reference': 50},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 25], 'color': "red"},
                    {'range': [25, 50], 'color': "orange"},
                    {'range': [50, 75], 'color': "yellow"},
                    {'range': [75, 100], 'color': "green"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))
        
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Market sentiment indicators
        sentiment_data = {
            'شاخص': ['VIX', 'Put/Call Ratio', 'Bull/Bear Ratio', 'Insider Trading'],
            'مقدار': [18.5, 0.95, 1.25, 'خنثی'],
            'وضعیت': ['کم', 'خنثی', 'صعودی', 'خنثی']
        }
        
        sentiment_df = pd.DataFrame(sentiment_data)
        st.dataframe(sentiment_df, hide_index=True, use_container_width=True)
    
    # Alerts and notifications
    st.header("هشدارها و اطلاعیه‌ها")
    
    alerts = [
        "🟡 AAPL نزدیک به سطح مقاومت $180",
        "🔴 TSLA شکست سطح حمایت $650",
        "🟢 MSFT سیگنال خرید قوی تولید کرد",
        "⚪ حجم معاملات بازار پایین‌تر از متوسط"
    ]
    
    for alert in alerts:
        st.info(alert)

if __name__ == "__main__":
    show_dashboard()
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
from utils.signal_generator import SignalGenerator
from utils.technical_analysis import TechnicalAnalysis
from utils.data_handler import DataHandler

def show_signals():
    st.title("🎯 مرکز سیگنال‌های معاملاتی")
    
    # Sidebar for signal configuration
    with st.sidebar:
        st.header("تنظیمات سیگنال")
        
        # Signal types
        st.subheader("انواع سیگنال")
        use_rsi = st.checkbox("RSI", value=True)
        use_macd = st.checkbox("MACD", value=True)
        use_sma = st.checkbox("SMA Crossover", value=True)
        use_bollinger = st.checkbox("Bollinger Bands", value=True)
        use_stochastic = st.checkbox("Stochastic", value=False)
        
        # Signal strength threshold
        signal_threshold = st.slider(
            "حد آستانه قوت سیگنال:",
            min_value=0.1,
            max_value=1.0,
            value=0.6,
            step=0.1,
            help="سیگنال‌هایی با قوت بالاتر از این مقدار نمایش داده می‌شوند"
        )
        
        # Risk management
        st.subheader("مدیریت ریسک")
        use_stop_loss = st.checkbox("استفاده از Stop Loss", value=True)
        stop_loss_pct = st.slider("درصد Stop Loss:", 1.0, 10.0, 2.0, 0.5)
        
        use_take_profit = st.checkbox("استفاده از Take Profit", value=True)
        take_profit_pct = st.slider("درصد Take Profit:", 1.0, 20.0, 4.0, 0.5)
        
        # Volume filter
        use_volume_filter = st.checkbox("فیلتر حجم", value=True)
        volume_threshold = st.slider("ضریب حجم:", 1.0, 3.0, 1.5, 0.1)
        
        # Trend filter
        use_trend_filter = st.checkbox("فیلتر روند", value=True)
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🎯 سیگنال‌های فعلی",
        "📊 تحلیل سیگنال",
        "📈 عملکرد تاریخی",
        "⚙️ سیگنال‌های سفارشی"
    ])
    
    with tab1:
        show_current_signals(signal_threshold, use_volume_filter, volume_threshold)
    
    with tab2:
        show_signal_analysis()
    
    with tab3:
        show_historical_performance()
    
    with tab4:
        show_custom_signals()

def show_current_signals(signal_threshold, use_volume_filter, volume_threshold):
    st.subheader("🎯 سیگنال‌های معاملاتی فعلی")
    
    if 'selected_symbol' not in st.session_state:
        st.info("لطفاً ابتدا یک نماد انتخاب کنید")
        return
    
    symbol = st.session_state.selected_symbol
    
    try:
        # Get data
        data_handler = DataHandler()
        df = data_handler.get_market_data(symbol, '3mo', '1d')
        
        if df is None or df.empty:
            st.error("داده‌ای برای تحلیل یافت نشد")
            return
        
        # Calculate indicators and signals
        ta = TechnicalAnalysis()
        df = ta.calculate_all_indicators(df)
        
        signal_gen = SignalGenerator()
        signals_df = signal_gen.generate_signals(df)
        
        # Combine data
        combined_df = pd.concat([df, signals_df], axis=1)
        
        # Current signal information
        latest_data = combined_df.iloc[-1]
        current_price = latest_data['Close']
        current_signal = latest_data['Signal']
        signal_strength = latest_data['Signal_Strength']
        
        # Display current signal
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if current_signal == 1:
                signal_text = "🟢 خرید"
                signal_color = "green"
            elif current_signal == -1:
                signal_text = "🔴 فروش"
                signal_color = "red"
            else:
                signal_text = "⚪ خنثی"
                signal_color = "gray"
            
            st.metric("سیگنال فعلی", signal_text)
        
        with col2:
            st.metric("قوت سیگنال", f"{abs(signal_strength):.2f}")
        
        with col3:
            confidence = latest_data.get('Signal_Confidence', 0)
            st.metric("اطمینان", f"{confidence:.1f}%")
        
        with col4:
            consistency = latest_data.get('Signal_Consistency', 0)
            st.metric("سازگاری", f"{int(consistency)}/4")
        
        # Signal details
        if abs(signal_strength) >= signal_threshold:
            st.success(f"✅ سیگنال قوی تولید شد برای {symbol}")
            
            # Calculate stop loss and take profit
            if current_signal == 1:  # Buy signal
                stop_loss = current_price * (1 - 0.02)  # 2% stop loss
                take_profit = current_price * (1 + 0.04)  # 4% take profit
                action = "خرید"
            elif current_signal == -1:  # Sell signal
                stop_loss = current_price * (1 + 0.02)
                take_profit = current_price * (1 - 0.04)
                action = "فروش"
            else:
                stop_loss = take_profit = current_price
                action = "انتظار"
            
            # Signal summary
            signal_summary = pd.DataFrame({
                'پارامتر': [
                    'نوع سیگنال',
                    'قیمت ورود',
                    'Stop Loss',
                    'Take Profit',
                    'نسبت ریسک/سود',
                    'RSI',
                    'MACD',
                    'وضعیت روند'
                ],
                'مقدار': [
                    action,
                    f"${current_price:.2f}",
                    f"${stop_loss:.2f}",
                    f"${take_profit:.2f}",
                    f"1:{abs(take_profit - current_price) / abs(stop_loss - current_price):.1f}",
                    f"{latest_data['RSI']:.1f}",
                    f"{latest_data['MACD']:.4f}",
                    "صعودی" if latest_data['SMA_Short'] > latest_data['SMA_Long'] else "نزولی"
                ]
            })
            
            st.dataframe(signal_summary, use_container_width=True, hide_index=True)
        
        else:
            st.info("⏳ در انتظار سیگنال قوی...")
        
        # Recent signals table
        st.subheader("📋 سیگنال‌های اخیر")
        
        # Filter recent signals
        recent_signals = combined_df[combined_df['Signal'] != 0].tail(20)
        
        if not recent_signals.empty:
            signals_table = pd.DataFrame({
                'تاریخ': recent_signals.index.strftime('%Y-%m-%d'),
                'نوع': recent_signals['Signal'].map({1: '🟢 خرید', -1: '🔴 فروش'}),
                'قیمت': recent_signals['Close'].round(2),
                'قوت': recent_signals['Signal_Strength'].round(3),
                'اطمینان': recent_signals['Signal_Confidence'].round(1),
                'RSI': recent_signals['RSI'].round(1),
                'MACD': recent_signals['MACD'].round(4),
                'حجم': recent_signals['Volume'].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "N/A")
            })
            
            # Highlight strong signals
            def highlight_strong_signals(row):
                if row['قوت'] >= signal_threshold:
                    return ['background-color: lightgreen'] * len(row)
                return [''] * len(row)
            
            styled_table = signals_table.style.apply(highlight_strong_signals, axis=1)
            st.dataframe(styled_table, use_container_width=True, hide_index=True)
        else:
            st.info("هیچ سیگنالی در داده‌های اخیر یافت نشد")
        
        # Signal distribution chart
        st.subheader("📊 توزیع سیگنال‌ها")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Signal strength distribution
            signal_strengths = combined_df['Signal_Strength'].dropna()
            
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=signal_strengths,
                nbinsx=30,
                name='توزیع قوت سیگنال',
                marker_color='blue',
                opacity=0.7
            ))
            
            fig.add_vline(
                x=signal_threshold,
                line_dash="dash",
                line_color="red",
                annotation_text=f"حد آستانه: {signal_threshold}"
            )
            
            fig.update_layout(
                title="توزیع قوت سیگنال‌ها",
                xaxis_title="قوت سیگنال",
                yaxis_title="فراوانی"
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Signal type distribution
            buy_signals = len(combined_df[combined_df['Signal'] == 1])
            sell_signals = len(combined_df[combined_df['Signal'] == -1])
            neutral_signals = len(combined_df[combined_df['Signal'] == 0])
            
            fig = go.Figure(data=[
                go.Pie(
                    labels=['خرید', 'فروش', 'خنثی'],
                    values=[buy_signals, sell_signals, neutral_signals],
                    marker_colors=['green', 'red', 'gray']
                )
            ])
            
            fig.update_layout(title="توزیع نوع سیگنال‌ها")
            st.plotly_chart(fig, use_container_width=True)
        
    except Exception as e:
        st.error(f"خطا در تولید سیگنال‌ها: {str(e)}")

def show_signal_analysis():
    st.subheader("📊 تحلیل عمقی سیگنال‌ها")
    
    if 'selected_symbol' not in st.session_state:
        st.info("لطفاً ابتدا یک نماد انتخاب کنید")
        return
    
    # Multi-timeframe analysis
    st.subheader("🕐 تحلیل چند بازه زمانی")
    
    timeframes = ['1d', '4h', '1h']
    timeframe_results = {}
    
    data_handler = DataHandler()
    ta = TechnicalAnalysis()
    signal_gen = SignalGenerator()
    
    for tf in timeframes:
        try:
            df = data_handler.get_market_data(st.session_state.selected_symbol, '1mo', tf)
            if df is not None and not df.empty:
                df = ta.calculate_all_indicators(df)
                signals_df = signal_gen.generate_signals(df)
                combined_df = pd.concat([df, signals_df], axis=1)
                
                latest = combined_df.iloc[-1]
                timeframe_results[tf] = {
                    'signal': latest['Signal'],
                    'strength': latest['Signal_Strength'],
                    'rsi': latest['RSI'],
                    'macd_signal': 1 if latest['MACD'] > latest['MACD_Signal'] else -1
                }
        except:
            timeframe_results[tf] = None
    
    # Display timeframe analysis
    tf_cols = st.columns(len(timeframes))
    
    for i, (tf, result) in enumerate(timeframe_results.items()):
        with tf_cols[i]:
            if result:
                signal_emoji = "🟢" if result['signal'] == 1 else "🔴" if result['signal'] == -1 else "⚪"
                signal_text = "خرید" if result['signal'] == 1 else "فروش" if result['signal'] == -1 else "خنثی"
                
                st.metric(
                    f"بازه {tf}",
                    f"{signal_emoji} {signal_text}",
                    f"قوت: {result['strength']:.2f}"
                )
                
                st.write(f"RSI: {result['rsi']:.1f}")
                macd_status = "صعودی" if result['macd_signal'] == 1 else "نزولی"
                st.write(f"MACD: {macd_status}")
            else:
                st.metric(f"بازه {tf}", "❌ خطا")
    
    # Signal consensus
    valid_signals = [r['signal'] for r in timeframe_results.values() if r is not None]
    if valid_signals:
        consensus = sum(valid_signals)
        if consensus > 0:
            consensus_text = f"🟢 اجماع خرید ({consensus}/{len(valid_signals)})"
        elif consensus < 0:
            consensus_text = f"🔴 اجماع فروش ({abs(consensus)}/{len(valid_signals)})"
        else:
            consensus_text = "⚪ عدم اجماع"
        
        st.info(f"**اجماع چند بازه زمانی:** {consensus_text}")
    
    # Individual indicator analysis
    st.subheader("🔍 تحلیل اندیکاتورهای جداگانه")
    
    try:
        df = data_handler.get_market_data(st.session_state.selected_symbol, '3mo', '1d')
        if df is not None:
            df = ta.calculate_all_indicators(df)
            signals_df = signal_gen.generate_signals(df)
            
            latest = df.iloc[-1]
            
            # Create indicator analysis table
            indicator_analysis = pd.DataFrame({
                'اندیکاتور': ['RSI', 'MACD', 'SMA Crossover', 'Bollinger Bands', 'Stochastic'],
                'مقدار فعلی': [
                    f"{latest['RSI']:.1f}",
                    f"{latest['MACD']:.4f}",
                    f"SMA20: {latest['SMA_Short']:.2f}",
                    f"موقعیت: {'بالا' if latest['Close'] > latest['BB_Upper'] else 'پایین' if latest['Close'] < latest['BB_Lower'] else 'وسط'}",
                    f"%K: {latest.get('Stoch_K', 0):.1f}"
                ],
                'سیگنال': [
                    signals_df['RSI_Signal'].iloc[-1],
                    signals_df['MACD_Signal'].iloc[-1],
                    signals_df['SMA_Signal'].iloc[-1],
                    signals_df['BB_Signal'].iloc[-1],
                    signals_df.get('Stoch_Signal', pd.Series([0])).iloc[-1]
                ],
                'وضعیت': [
                    'خرید بیش‌ازحد' if latest['RSI'] > 70 else 'فروش بیش‌ازحد' if latest['RSI'] < 30 else 'خنثی',
                    'صعودی' if latest['MACD'] > latest['MACD_Signal'] else 'نزولی',
                    'صعودی' if latest['SMA_Short'] > latest['SMA_Long'] else 'نزولی',
                    'نزدیک باند بالا' if latest['Close'] > latest['BB_Upper'] * 0.98 else 'نزدیک باند پایین' if latest['Close'] < latest['BB_Lower'] * 1.02 else 'نرمال',
                    'خرید بیش‌ازحد' if latest.get('Stoch_K', 50) > 80 else 'فروش بیش‌ازحد' if latest.get('Stoch_K', 50) < 20 else 'خنثی'
                ]
            })
            
            # Map signals to text
            indicator_analysis['سیگنال'] = indicator_analysis['سیگنال'].map({
                1: '🟢 خرید',
                -1: '🔴 فروش',
                0: '⚪ خنثی'
            })
            
            st.dataframe(indicator_analysis, use_container_width=True, hide_index=True)
            
    except Exception as e:
        st.error(f"خطا در تحلیل اندیکاتورها: {str(e)}")

def show_historical_performance():
    st.subheader("📈 عملکرد تاریخی سیگنال‌ها")
    
    if 'selected_symbol' not in st.session_state:
        st.info("لطفاً ابتدا یک نماد انتخاب کنید")
        return
    
    try:
        # Get longer historical data
        data_handler = DataHandler()
        df = data_handler.get_market_data(st.session_state.selected_symbol, '1y', '1d')
        
        if df is None or df.empty:
            st.error("داده‌های تاریخی کافی یافت نشد")
            return
        
        # Calculate indicators and signals
        ta = TechnicalAnalysis()
        df = ta.calculate_all_indicators(df)
        
        signal_gen = SignalGenerator()
        signals_df = signal_gen.generate_signals(df)
        
        # Backtest signals
        backtest_results = signal_gen.backtest_signals(df, signals_df, initial_capital=10000)
        
        # Display backtest results
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            final_capital = backtest_results['final_capital']
            total_return = backtest_results['total_return']
            st.metric("بازده کل", f"{total_return:.1f}%", f"${final_capital:,.0f}")
        
        with col2:
            total_trades = len(backtest_results['trades'])
            st.metric("تعداد معاملات", total_trades)
        
        with col3:
            if total_trades > 0:
                winning_trades = len([t for t in backtest_results['trades'] if t.get('pnl', 0) > 0])
                win_rate = (winning_trades / total_trades) * 100
                st.metric("نرخ موفقیت", f"{win_rate:.1f}%")
            else:
                st.metric("نرخ موفقیت", "N/A")
        
        with col4:
            # Calculate max drawdown
            equity_curve = backtest_results['equity_curve']
            if equity_curve:
                equity_values = [point['equity'] for point in equity_curve]
                peak = np.maximum.accumulate(equity_values)
                drawdown = (np.array(equity_values) / peak - 1) * 100
                max_drawdown = np.min(drawdown)
                st.metric("حداکثر افت", f"{max_drawdown:.1f}%")
            else:
                st.metric("حداکثر افت", "N/A")
        
        # Equity curve chart
        if equity_curve:
            st.subheader("منحنی سرمایه")
            
            equity_df = pd.DataFrame(equity_curve)
            equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'])
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=equity_df['timestamp'],
                y=equity_df['equity'],
                mode='lines',
                name='ارزش پرتفولیو',
                line=dict(color='blue', width=2)
            ))
            
            # Add buy/sell markers
            trades = backtest_results['trades']
            buy_trades = [t for t in trades if t['type'] in ['buy', 'close_short']]
            sell_trades = [t for t in trades if t['type'] in ['sell', 'close_long']]
            
            if buy_trades:
                buy_dates = [t['timestamp'] for t in buy_trades]
                buy_prices = [equity_df[equity_df['timestamp'] == d]['equity'].iloc[0] if len(equity_df[equity_df['timestamp'] == d]) > 0 else 0 for d in buy_dates]
                
                fig.add_trace(go.Scatter(
                    x=buy_dates,
                    y=buy_prices,
                    mode='markers',
                    name='خرید',
                    marker=dict(symbol='triangle-up', size=10, color='green')
                ))
            
            if sell_trades:
                sell_dates = [t['timestamp'] for t in sell_trades]
                sell_prices = [equity_df[equity_df['timestamp'] == d]['equity'].iloc[0] if len(equity_df[equity_df['timestamp'] == d]) > 0 else 0 for d in sell_dates]
                
                fig.add_trace(go.Scatter(
                    x=sell_dates,
                    y=sell_prices,
                    mode='markers',
                    name='فروش',
                    marker=dict(symbol='triangle-down', size=10, color='red')
                ))
            
            fig.update_layout(
                title="عملکرد استراتژی در طول زمان",
                xaxis_title="تاریخ",
                yaxis_title="ارزش پرتفولیو ($)",
                hovermode='x unified'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Trade analysis
        if trades:
            st.subheader("تحلیل معاملات")
            
            # Calculate PnL for each trade
            pnl_trades = [t for t in trades if 'pnl' in t]
            
            if pnl_trades:
                pnl_values = [t['pnl'] for t in pnl_trades]
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # PnL distribution
                    fig = go.Figure()
                    fig.add_trace(go.Histogram(
                        x=pnl_values,
                        nbinsx=20,
                        name='توزیع سود/زیان',
                        marker_color='blue',
                        opacity=0.7
                    ))
                    
                    fig.update_layout(
                        title="توزیع سود/زیان معاملات",
                        xaxis_title="سود/زیان ($)",
                        yaxis_title="تعداد معاملات"
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Trade statistics
                    avg_pnl = np.mean(pnl_values)
                    std_pnl = np.std(pnl_values)
                    best_trade = max(pnl_values)
                    worst_trade = min(pnl_values)
                    
                    trade_stats = pd.DataFrame({
                        'آماره': [
                            'متوسط سود/زیان',
                            'انحراف معیار',
                            'بهترین معامله',
                            'بدترین معامله',
                            'نسبت سود به زیان'
                        ],
                        'مقدار': [
                            f"${avg_pnl:.2f}",
                            f"${std_pnl:.2f}",
                            f"${best_trade:.2f}",
                            f"${worst_trade:.2f}",
                            f"{abs(avg_pnl / worst_trade):.2f}" if worst_trade != 0 else "N/A"
                        ]
                    })
                    
                    st.dataframe(trade_stats, hide_index=True, use_container_width=True)
        
    except Exception as e:
        st.error(f"خطا در محاسبه عملکرد تاریخی: {str(e)}")

def show_custom_signals():
    st.subheader("⚙️ تنظیمات سیگنال‌های سفارشی")
    
    st.info("این بخش امکان ساخت سیگنال‌های سفارشی بر اساس ترکیب اندیکاتورهای مختلف را فراهم می‌کند.")
    
    # Custom signal builder
    with st.expander("🔧 سازنده سیگنال سفارشی"):
        st.subheader("شرایط خرید")
        
        # Buy conditions
        col1, col2 = st.columns(2)
        
        with col1:
            rsi_buy_min = st.slider("RSI حداقل برای خرید:", 0, 100, 30)
            rsi_buy_max = st.slider("RSI حداکثر برای خرید:", 0, 100, 70)
        
        with col2:
            macd_buy = st.selectbox("شرط MACD برای خرید:", 
                                   ["MACD > Signal", "MACD < Signal", "بی‌اهمیت"])
            
            volume_buy = st.selectbox("شرط حجم برای خرید:",
                                     ["حجم > متوسط", "حجم < متوسط", "بی‌اهمیت"])
        
        st.subheader("شرایط فروش")
        
        col3, col4 = st.columns(2)
        
        with col3:
            rsi_sell_min = st.slider("RSI حداقل برای فروش:", 0, 100, 30)
            rsi_sell_max = st.slider("RSI حداکثر برای فروش:", 0, 100, 80)
        
        with col4:
            macd_sell = st.selectbox("شرط MACD برای فروش:",
                                    ["MACD > Signal", "MACD < Signal", "بی‌اهمیت"])
            
            volume_sell = st.selectbox("شرط حجم برای فروش:",
                                      ["حجم > متوسط", "حجم < متوسط", "بی‌اهمیت"])
        
        # Test custom signal
        if st.button("🧪 تست سیگنال سفارشی"):
            if 'selected_symbol' in st.session_state:
                try:
                    # Get data and test custom signal
                    data_handler = DataHandler()
                    df = data_handler.get_market_data(st.session_state.selected_symbol, '3mo', '1d')
                    
                    if df is not None:
                        ta = TechnicalAnalysis()
                        df = ta.calculate_all_indicators(df)
                        
                        # Apply custom conditions
                        custom_signals = pd.Series(0, index=df.index)
                        
                        # Buy conditions
                        buy_condition = (df['RSI'] >= rsi_buy_min) & (df['RSI'] <= rsi_buy_max)
                        
                        if macd_buy == "MACD > Signal":
                            buy_condition &= (df['MACD'] > df['MACD_Signal'])
                        elif macd_buy == "MACD < Signal":
                            buy_condition &= (df['MACD'] < df['MACD_Signal'])
                        
                        if volume_buy == "حجم > متوسط" and 'Volume_SMA' in df.columns:
                            buy_condition &= (df['Volume'] > df['Volume_SMA'])
                        elif volume_buy == "حجم < متوسط" and 'Volume_SMA' in df.columns:
                            buy_condition &= (df['Volume'] < df['Volume_SMA'])
                        
                        custom_signals[buy_condition] = 1
                        
                        # Sell conditions
                        sell_condition = (df['RSI'] >= rsi_sell_min) & (df['RSI'] <= rsi_sell_max)
                        
                        if macd_sell == "MACD > Signal":
                            sell_condition &= (df['MACD'] > df['MACD_Signal'])
                        elif macd_sell == "MACD < Signal":
                            sell_condition &= (df['MACD'] < df['MACD_Signal'])
                        
                        if volume_sell == "حجم > متوسط" and 'Volume_SMA' in df.columns:
                            sell_condition &= (df['Volume'] > df['Volume_SMA'])
                        elif volume_sell == "حجم < متوسط" and 'Volume_SMA' in df.columns:
                            sell_condition &= (df['Volume'] < df['Volume_SMA'])
                        
                        custom_signals[sell_condition] = -1
                        
                        # Show results
                        total_signals = len(custom_signals[custom_signals != 0])
                        buy_signals = len(custom_signals[custom_signals == 1])
                        sell_signals = len(custom_signals[custom_signals == -1])
                        
                        st.success(f"✅ سیگنال سفارشی تست شد!")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("کل سیگنال‌ها", total_signals)
                        with col2:
                            st.metric("سیگنال‌های خرید", buy_signals)
                        with col3:
                            st.metric("سیگنال‌های فروش", sell_signals)
                        
                        # Show recent custom signals
                        recent_custom = custom_signals[custom_signals != 0].tail(10)
                        if not recent_custom.empty:
                            custom_table = pd.DataFrame({
                                'تاریخ': recent_custom.index.strftime('%Y-%m-%d'),
                                'سیگنال': recent_custom.map({1: '🟢 خرید', -1: '🔴 فروش'}),
                                'قیمت': df.loc[recent_custom.index, 'Close'].round(2),
                                'RSI': df.loc[recent_custom.index, 'RSI'].round(1)
                            })
                            
                            st.dataframe(custom_table, hide_index=True, use_container_width=True)
                        
                except Exception as e:
                    st.error(f"خطا در تست سیگنال سفارشی: {str(e)}")
            else:
                st.warning("لطفاً ابتدا یک نماد انتخاب کنید")
    
    # Signal alerts
    with st.expander("🔔 تنظیم هشدارها"):
        st.subheader("هشدارهای سیگنال")
        
        alert_email = st.text_input("ایمیل برای دریافت هشدار:")
        alert_phone = st.text_input("شماره تلفن برای SMS:")
        
        alert_types = st.multiselect(
            "نوع هشدارها:",
            ["سیگنال خرید قوی", "سیگنال فروش قوی", "RSI بیش‌ازحد", "شکست سطح حمایت/مقاومت"]
        )
        
        if st.button("💾 ذخیره تنظیمات هشدار"):
            st.success("✅ تنظیمات هشدار ذخیره شد!")
            # In a real app, this would save to database
    
    # Strategy templates
    with st.expander("📋 قالب‌های استراتژی"):
        st.subheader("استراتژی‌های آماده")
        
        strategies = {
            "استراتژی محافظه‌کارانه": {
                "توضیح": "بر اساس RSI و MACD با فیلتر حجم",
                "پارامترها": "RSI: 20-80, MACD Crossover, Volume > 1.5x"
            },
            "استراتژی تهاجمی": {
                "توضیح": "سیگنال‌های سریع با RSI حساس",
                "پارامترها": "RSI: 30-70, MACD + Stochastic"
            },
            "استراتژی روند‌پیرو": {
                "توضیح": "تمرکز بر میانگین‌های متحرک و روند",
                "پارامترها": "SMA Crossover + EMA + MACD"
            }
        }
        
        selected_strategy = st.selectbox("انتخاب استراتژی:", list(strategies.keys()))
        
        if selected_strategy:
            strategy = strategies[selected_strategy]
            st.info(f"**توضیح:** {strategy['توضیح']}")
            st.code(f"**پارامترها:** {strategy['پارامترها']}")
            
            if st.button(f"🔄 اعمال استراتژی {selected_strategy}"):
                st.success(f"✅ استراتژی {selected_strategy} اعمال شد!")

if __name__ == "__main__":
    show_signals()
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from utils.technical_analysis import TechnicalAnalysis
from utils.data_handler import DataHandler

def show_chart_analysis():
    st.title("📈 تحلیل نمودار پیشرفته")
    
    # Sidebar for chart configuration
    with st.sidebar:
        st.header("تنظیمات نمودار")
        
        # Chart type selection
        chart_type = st.selectbox(
            "نوع نمودار:",
            ["کندل استیک", "خطی", "میله‌ای", "ناحیه‌ای"]
        )
        
        # Technical indicators selection
        st.subheader("اندیکاتورهای تکنیکال")
        
        show_ma = st.checkbox("میانگین متحرک", value=True)
        if show_ma:
            ma_periods = st.multiselect(
                "دوره‌های MA:",
                [5, 10, 20, 50, 100, 200],
                default=[20, 50]
            )
        
        show_bollinger = st.checkbox("باندهای بولینگر")
        show_ichimoku = st.checkbox("ایچیموکو")
        show_fibonacci = st.checkbox("اصلاح فیبوناچی")
        
        # Oscillators
        st.subheader("اسیلاتورها")
        show_rsi = st.checkbox("RSI", value=True)
        show_macd = st.checkbox("MACD", value=True)
        show_stochastic = st.checkbox("Stochastic")
        show_williams = st.checkbox("Williams %R")
        
        # Volume indicators
        st.subheader("اندیکاتورهای حجم")
        show_volume = st.checkbox("حجم معاملات", value=True)
        show_volume_ma = st.checkbox("میانگین متحرک حجم")
        show_obv = st.checkbox("OBV")
        
        # Pattern detection
        st.subheader("تشخیص الگو")
        detect_patterns = st.checkbox("تشخیص الگوهای کندل استیک")
        detect_support_resistance = st.checkbox("سطوح حمایت و مقاومت")
        detect_trend_lines = st.checkbox("خطوط روند")
    
    # Get data
    if 'selected_symbol' in st.session_state:
        symbol = st.session_state.selected_symbol
        period = st.session_state.period
        timeframe = st.session_state.timeframe
        
        try:
            data_handler = DataHandler()
            df = data_handler.get_market_data(symbol, period, timeframe)
            
            if df is None or df.empty:
                st.error("داده‌ای برای نمایش یافت نشد")
                return
            
            # Calculate technical indicators
            ta = TechnicalAnalysis()
            df = ta.calculate_all_indicators(df)
            
            # Determine number of subplots
            subplot_count = 1  # Main price chart
            subplot_titles = ['قیمت']
            
            if show_rsi or show_stochastic or show_williams:
                subplot_count += 1
                subplot_titles.append('اسیلاتورها')
            
            if show_macd:
                subplot_count += 1
                subplot_titles.append('MACD')
            
            if show_volume:
                subplot_count += 1
                subplot_titles.append('حجم')
            
            # Create subplots
            row_heights = [0.6] + [0.4/(subplot_count-1)] * (subplot_count-1) if subplot_count > 1 else [1.0]
            
            fig = make_subplots(
                rows=subplot_count,
                cols=1,
                subplot_titles=subplot_titles,
                vertical_spacing=0.05,
                row_heights=row_heights,
                shared_xaxes=True
            )
            
            # Main price chart
            current_row = 1
            
            if chart_type == "کندل استیک":
                fig.add_trace(
                    go.Candlestick(
                        x=df.index,
                        open=df['Open'],
                        high=df['High'],
                        low=df['Low'],
                        close=df['Close'],
                        name='قیمت',
                        increasing_line_color='green',
                        decreasing_line_color='red'
                    ),
                    row=current_row, col=1
                )
            elif chart_type == "خطی":
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['Close'],
                        mode='lines',
                        name='قیمت بسته شدن',
                        line=dict(color='blue', width=2)
                    ),
                    row=current_row, col=1
                )
            elif chart_type == "میله‌ای":
                colors = ['green' if close >= open else 'red' 
                         for close, open in zip(df['Close'], df['Open'])]
                fig.add_trace(
                    go.Bar(
                        x=df.index,
                        y=df['Close'],
                        name='قیمت',
                        marker_color=colors
                    ),
                    row=current_row, col=1
                )
            elif chart_type == "ناحیه‌ای":
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['Close'],
                        fill='tonexty',
                        mode='lines',
                        name='قیمت',
                        line=dict(color='blue')
                    ),
                    row=current_row, col=1
                )
            
            # Moving averages
            if show_ma and ma_periods:
                colors = ['blue', 'orange', 'red', 'purple', 'brown', 'pink']
                for i, period in enumerate(ma_periods):
                    ma_data = ta.calculate_sma(df['Close'], period)
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=ma_data,
                            mode='lines',
                            name=f'MA{period}',
                            line=dict(color=colors[i % len(colors)], width=1)
                        ),
                        row=current_row, col=1
                    )
            
            # Bollinger Bands
            if show_bollinger and 'BB_Upper' in df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['BB_Upper'],
                        mode='lines',
                        name='BB بالا',
                        line=dict(color='gray', width=1, dash='dash'),
                        showlegend=False
                    ),
                    row=current_row, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['BB_Lower'],
                        mode='lines',
                        name='BB پایین',
                        line=dict(color='gray', width=1, dash='dash'),
                        fill='tonexty',
                        fillcolor='rgba(128,128,128,0.1)',
                        showlegend=False
                    ),
                    row=current_row, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['BB_Middle'],
                        mode='lines',
                        name='BB میانه',
                        line=dict(color='gray', width=1)
                    ),
                    row=current_row, col=1
                )
            
            # Support and Resistance levels
            if detect_support_resistance:
                levels = ta.get_support_resistance_levels(df)
                
                for level in levels['resistance'][:3]:  # Show top 3 resistance levels
                    fig.add_hline(
                        y=level,
                        line_dash="dash",
                        line_color="red",
                        annotation_text=f"مقاومت: {level:.2f}",
                        row=current_row
                    )
                
                for level in levels['support'][:3]:  # Show top 3 support levels
                    fig.add_hline(
                        y=level,
                        line_dash="dash",
                        line_color="green",
                        annotation_text=f"حمایت: {level:.2f}",
                        row=current_row
                    )
            
            # Oscillators subplot
            if show_rsi or show_stochastic or show_williams:
                current_row += 1
                
                if show_rsi and 'RSI' in df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=df['RSI'],
                            mode='lines',
                            name='RSI',
                            line=dict(color='purple', width=2)
                        ),
                        row=current_row, col=1
                    )
                    
                    # RSI levels
                    fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row)
                    fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row)
                    fig.add_hline(y=50, line_dash="dot", line_color="gray", row=current_row)
                
                if show_stochastic and 'Stoch_K' in df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=df['Stoch_K'],
                            mode='lines',
                            name='Stoch %K',
                            line=dict(color='blue', width=1)
                        ),
                        row=current_row, col=1
                    )
                    
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=df['Stoch_D'],
                            mode='lines',
                            name='Stoch %D',
                            line=dict(color='red', width=1)
                        ),
                        row=current_row, col=1
                    )
                
                if show_williams and 'Williams_R' in df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=df['Williams_R'],
                            mode='lines',
                            name='Williams %R',
                            line=dict(color='orange', width=1)
                        ),
                        row=current_row, col=1
                    )
            
            # MACD subplot
            if show_macd and 'MACD' in df.columns:
                current_row += 1
                
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['MACD'],
                        mode='lines',
                        name='MACD',
                        line=dict(color='blue', width=2)
                    ),
                    row=current_row, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=df['MACD_Signal'],
                        mode='lines',
                        name='سیگنال',
                        line=dict(color='red', width=1)
                    ),
                    row=current_row, col=1
                )
                
                # MACD histogram
                colors = ['green' if val >= 0 else 'red' for val in df['MACD_Histogram']]
                fig.add_trace(
                    go.Bar(
                        x=df.index,
                        y=df['MACD_Histogram'],
                        name='هیستوگرام',
                        marker_color=colors,
                        opacity=0.7
                    ),
                    row=current_row, col=1
                )
            
            # Volume subplot
            if show_volume and 'Volume' in df.columns:
                current_row += 1
                
                colors = ['green' if close >= open else 'red' 
                         for close, open in zip(df['Close'], df['Open'])]
                
                fig.add_trace(
                    go.Bar(
                        x=df.index,
                        y=df['Volume'],
                        name='حجم',
                        marker_color=colors,
                        opacity=0.7
                    ),
                    row=current_row, col=1
                )
                
                if show_volume_ma and 'Volume_SMA' in df.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=df.index,
                            y=df['Volume_SMA'],
                            mode='lines',
                            name='میانگین حجم',
                            line=dict(color='orange', width=1)
                        ),
                        row=current_row, col=1
                    )
            
            # Update layout
            fig.update_layout(
                title=f"تحلیل پیشرفته نمودار {symbol}",
                height=800,
                showlegend=True,
                template="plotly_white",
                xaxis_rangeslider_visible=False
            )
            
            # Remove x-axis labels for all but the bottom subplot
            for i in range(1, subplot_count):
                fig.update_xaxes(showticklabels=False, row=i)
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Pattern detection results
            if detect_patterns:
                st.subheader("🔍 الگوهای شناسایی شده")
                
                # Simple pattern detection (mock implementation)
                patterns_found = []
                
                # Doji detection
                for i in range(-10, 0):  # Check last 10 candles
                    if i < -len(df):
                        continue
                    
                    open_price = df['Open'].iloc[i]
                    close_price = df['Close'].iloc[i]
                    high_price = df['High'].iloc[i]
                    low_price = df['Low'].iloc[i]
                    
                    body_size = abs(close_price - open_price)
                    total_range = high_price - low_price
                    
                    if total_range > 0 and body_size / total_range < 0.1:
                        patterns_found.append({
                            'تاریخ': df.index[i].strftime('%Y-%m-%d'),
                            'الگو': 'Doji',
                            'توضیح': 'عدم تعادل بین خریداران و فروشندگان',
                            'اهمیت': 'متوسط'
                        })
                
                # Hammer detection
                for i in range(-10, 0):
                    if i < -len(df):
                        continue
                    
                    open_price = df['Open'].iloc[i]
                    close_price = df['Close'].iloc[i]
                    high_price = df['High'].iloc[i]
                    low_price = df['Low'].iloc[i]
                    
                    body_size = abs(close_price - open_price)
                    lower_shadow = min(open_price, close_price) - low_price
                    upper_shadow = high_price - max(open_price, close_price)
                    
                    if lower_shadow > 2 * body_size and upper_shadow < body_size:
                        patterns_found.append({
                            'تاریخ': df.index[i].strftime('%Y-%m-%d'),
                            'الگو': 'Hammer',
                            'توضیح': 'سیگنال احتمالی برگشت روند صعودی',
                            'اهمیت': 'بالا'
                        })
                
                if patterns_found:
                    patterns_df = pd.DataFrame(patterns_found)
                    st.dataframe(patterns_df, use_container_width=True)
                else:
                    st.info("هیچ الگوی خاصی در داده‌های اخیر شناسایی نشد")
            
            # Technical analysis summary
            st.subheader("📊 خلاصه تحلیل تکنیکال")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Trend analysis
                trend_info = ta.get_trend_direction(df)
                trend_text = "صعودی" if trend_info['overall_trend'] > 0 else "نزولی"
                trend_color = "🟢" if trend_info['overall_trend'] > 0 else "🔴"
                
                st.metric("روند کلی", f"{trend_color} {trend_text}")
                
                # Current RSI
                current_rsi = df['RSI'].iloc[-1]
                rsi_status = "خرید بیش‌ازحد" if current_rsi > 70 else "فروش بیش‌ازحد" if current_rsi < 30 else "خنثی"
                st.metric("وضعیت RSI", rsi_status, f"{current_rsi:.1f}")
            
            with col2:
                # MACD status
                current_macd = df['MACD'].iloc[-1]
                macd_signal = df['MACD_Signal'].iloc[-1]
                macd_status = "صعودی" if current_macd > macd_signal else "نزولی"
                macd_color = "🟢" if current_macd > macd_signal else "🔴"
                
                st.metric("وضعیت MACD", f"{macd_color} {macd_status}")
                
                # Bollinger position
                if 'BB_Upper' in df.columns and 'BB_Lower' in df.columns:
                    current_price = df['Close'].iloc[-1]
                    bb_upper = df['BB_Upper'].iloc[-1]
                    bb_lower = df['BB_Lower'].iloc[-1]
                    
                    if current_price > bb_upper:
                        bb_status = "بالای باند بالا"
                    elif current_price < bb_lower:
                        bb_status = "پایین باند پایین"
                    else:
                        bb_status = "درون باندها"
                    
                    st.metric("موقعیت بولینگر", bb_status)
            
            with col3:
                # Volume analysis
                if 'Volume' in df.columns:
                    current_volume = df['Volume'].iloc[-1]
                    avg_volume = df['Volume'].rolling(20).mean().iloc[-1]
                    volume_ratio = current_volume / avg_volume
                    
                    volume_status = "بالا" if volume_ratio > 1.5 else "پایین" if volume_ratio < 0.5 else "نرمال"
                    st.metric("حجم معاملات", volume_status, f"{volume_ratio:.1f}x")
                
                # Volatility
                volatility = df['Close'].pct_change().std() * 100
                volatility_status = "بالا" if volatility > 3 else "پایین" if volatility < 1 else "متوسط"
                st.metric("نوسانات", volatility_status, f"{volatility:.1f}%")
            
        except Exception as e:
            st.error(f"خطا در نمایش نمودار: {str(e)}")
    else:
        st.info("لطفاً ابتدا یک نماد انتخاب کنید")

if __name__ == "__main__":
    show_chart_analysis()
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
from utils.data_handler import DataHandler
from utils.technical_analysis import TechnicalAnalysis
from utils.signal_generator import SignalGenerator

def show_portfolio():
    st.title("💼 مدیریت پرتفولیو")
    
    # Initialize session state for portfolio
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = pd.DataFrame(columns=[
            'Symbol', 'Shares', 'Entry_Price', 'Entry_Date', 'Stop_Loss', 'Take_Profit'
        ])
    
    if 'portfolio_history' not in st.session_state:
        st.session_state.portfolio_history = []
    
    # Tabs for different portfolio functions
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 نمای کلی پرتفولیو",
        "➕ افزودن موقعیت",
        "📈 تحلیل عملکرد",
        "⚙️ مدیریت ریسک"
    ])
    
    with tab1:
        show_portfolio_overview()
    
    with tab2:
        show_add_position()
    
    with tab3:
        show_performance_analysis()
    
    with tab4:
        show_risk_management()

def show_portfolio_overview():
    st.subheader("📊 نمای کلی پرتفولیو")
    
    portfolio = st.session_state.portfolio
    
    if portfolio.empty:
        st.info("🏛️ پرتفولیو شما خالی است. از تب 'افزودن موقعیت' برای شروع استفاده کنید.")
        return
    
    # Get current prices for all symbols
    data_handler = DataHandler()
    current_prices = {}
    portfolio_data = []
    
    for _, position in portfolio.iterrows():
        symbol = position['Symbol']
        try:
            # Get current price
            df = data_handler.get_market_data(symbol, '1d', '1d')
            if df is not None and not df.empty:
                current_price = df['Close'].iloc[-1]
                current_prices[symbol] = current_price
                
                # Calculate position metrics
                shares = position['Shares']
                entry_price = position['Entry_Price']
                current_value = shares * current_price
                entry_value = shares * entry_price
                pnl = current_value - entry_value
                pnl_pct = (pnl / entry_value) * 100
                
                portfolio_data.append({
                    'Symbol': symbol,
                    'Shares': shares,
                    'Entry_Price': entry_price,
                    'Current_Price': current_price,
                    'Entry_Value': entry_value,
                    'Current_Value': current_value,
                    'PnL': pnl,
                    'PnL_Pct': pnl_pct,
                    'Entry_Date': position['Entry_Date'],
                    'Stop_Loss': position.get('Stop_Loss', 0),
                    'Take_Profit': position.get('Take_Profit', 0)
                })
        except Exception as e:
            st.warning(f"خطا در دریافت قیمت {symbol}: {str(e)}")
    
    if not portfolio_data:
        st.error("❌ خطا در دریافت اطلاعات قیمت پرتفولیو")
        return
    
    portfolio_df = pd.DataFrame(portfolio_data)
    
    # Portfolio summary metrics
    total_value = portfolio_df['Current_Value'].sum()
    total_pnl = portfolio_df['PnL'].sum()
    total_entry_value = portfolio_df['Entry_Value'].sum()
    total_pnl_pct = (total_pnl / total_entry_value) * 100 if total_entry_value > 0 else 0
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "ارزش کل پرتفولیو", 
            f"${total_value:,.2f}",
            help="ارزش فعلی کل دارایی‌های پرتفولیو"
        )
    
    with col2:
        st.metric(
            "سود/زیان کل", 
            f"${total_pnl:,.2f}",
            f"{total_pnl_pct:+.2f}%"
        )
    
    with col3:
        winning_positions = len(portfolio_df[portfolio_df['PnL'] > 0])
        total_positions = len(portfolio_df)
        win_rate = (winning_positions / total_positions) * 100 if total_positions > 0 else 0
        st.metric("نرخ موفقیت", f"{win_rate:.1f}%", f"{winning_positions}/{total_positions}")
    
    with col4:
        avg_return = portfolio_df['PnL_Pct'].mean()
        st.metric("متوسط بازده", f"{avg_return:.2f}%")
    
    # Portfolio composition chart
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("ترکیب پرتفولیو")
        
        fig = px.pie(
            portfolio_df, 
            values='Current_Value', 
            names='Symbol',
            title="تخصیص دارایی‌ها بر اساس ارزش فعلی"
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("عملکرد موقعیت‌ها")
        
        colors = ['green' if pnl > 0 else 'red' for pnl in portfolio_df['PnL_Pct']]
        
        fig = go.Figure(data=[
            go.Bar(
                x=portfolio_df['Symbol'],
                y=portfolio_df['PnL_Pct'],
                marker_color=colors,
                text=portfolio_df['PnL_Pct'].apply(lambda x: f"{x:+.1f}%"),
                textposition='auto'
            )
        ])
        
        fig.update_layout(
            title="بازده هر موقعیت (%)",
            xaxis_title="نماد",
            yaxis_title="بازده (%)",
            showlegend=False
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Detailed portfolio table
    st.subheader("جزئیات موقعیت‌ها")
    
    # Format display dataframe
    display_df = portfolio_df.copy()
    display_df['Entry_Price'] = display_df['Entry_Price'].apply(lambda x: f"${x:.2f}")
    display_df['Current_Price'] = display_df['Current_Price'].apply(lambda x: f"${x:.2f}")
    display_df['Current_Value'] = display_df['Current_Value'].apply(lambda x: f"${x:,.2f}")
    display_df['PnL'] = display_df['PnL'].apply(lambda x: f"${x:+,.2f}")
    display_df['PnL_Pct'] = display_df['PnL_Pct'].apply(lambda x: f"{x:+.2f}%")
    display_df['Stop_Loss'] = display_df['Stop_Loss'].apply(lambda x: f"${x:.2f}" if x > 0 else "تنظیم نشده")
    display_df['Take_Profit'] = display_df['Take_Profit'].apply(lambda x: f"${x:.2f}" if x > 0 else "تنظیم نشده")
    
    # Rename columns for display
    display_df = display_df.rename(columns={
        'Symbol': 'نماد',
        'Shares': 'تعداد سهام',
        'Entry_Price': 'قیمت ورود',
        'Current_Price': 'قیمت فعلی',
        'Current_Value': 'ارزش فعلی',
        'PnL': 'سود/زیان',
        'PnL_Pct': 'بازده (%)',
        'Entry_Date': 'تاریخ ورود',
        'Stop_Loss': 'حد ضرر',
        'Take_Profit': 'هدف سود'
    })
    
    st.dataframe(
        display_df[['نماد', 'تعداد سهام', 'قیمت ورود', 'قیمت فعلی', 'ارزش فعلی', 'سود/زیان', 'بازده (%)', 'حد ضرر', 'هدف سود']],
        use_container_width=True,
        hide_index=True
    )
    
    # Position management
    st.subheader("مدیریت موقعیت‌ها")
    
    # Select position to modify or close
    position_options = [f"{row['Symbol']} ({row['تعداد سهام']} سهام)" for _, row in display_df.iterrows()]
    
    if position_options:
        selected_position = st.selectbox("انتخاب موقعیت برای مدیریت:", position_options)
        
        if selected_position:
            symbol = selected_position.split(' (')[0]
            position_idx = portfolio_df[portfolio_df['Symbol'] == symbol].index[0]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button(f"❌ بستن موقعیت {symbol}"):
                    # Remove position from portfolio
                    st.session_state.portfolio = st.session_state.portfolio.drop(position_idx).reset_index(drop=True)
                    st.success(f"✅ موقعیت {symbol} بسته شد")
                    st.rerun()
            
            with col2:
                new_stop_loss = st.number_input(
                    f"حد ضرر جدید برای {symbol}:",
                    min_value=0.0,
                    value=float(portfolio_df.loc[position_idx, 'Stop_Loss']),
                    step=0.01
                )
                
                if st.button(f"🔄 بروزرسانی حد ضرر"):
                    st.session_state.portfolio.loc[position_idx, 'Stop_Loss'] = new_stop_loss
                    st.success(f"✅ حد ضرر {symbol} بروزرسانی شد")
                    st.rerun()
            
            with col3:
                new_take_profit = st.number_input(
                    f"هدف سود جدید برای {symbol}:",
                    min_value=0.0,
                    value=float(portfolio_df.loc[position_idx, 'Take_Profit']),
                    step=0.01
                )
                
                if st.button(f"🎯 بروزرسانی هدف سود"):
                    st.session_state.portfolio.loc[position_idx, 'Take_Profit'] = new_take_profit
                    st.success(f"✅ هدف سود {symbol} بروزرسانی شد")
                    st.rerun()

def show_add_position():
    st.subheader("➕ افزودن موقعیت جدید")
    
    # Position entry form
    with st.form("add_position_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            symbol = st.text_input(
                "نماد سهم:",
                help="نماد سهم را وارد کنید (مثال: AAPL, MSFT, GOOGL)"
            )
            
            shares = st.number_input(
                "تعداد سهام:",
                min_value=1,
                value=100,
                help="تعداد سهام برای خرید"
            )
            
            entry_price = st.number_input(
                "قیمت ورود:",
                min_value=0.01,
                value=100.0,
                step=0.01,
                help="قیمت خرید هر سهم"
            )
        
        with col2:
            entry_date = st.date_input(
                "تاریخ ورود:",
                value=datetime.now().date(),
                help="تاریخ خرید سهام"
            )
            
            stop_loss = st.number_input(
                "حد ضرر (اختیاری):",
                min_value=0.0,
                value=0.0,
                step=0.01,
                help="قیمت فروش خودکار در صورت ضرر"
            )
            
            take_profit = st.number_input(
                "هدف سود (اختیاری):",
                min_value=0.0,
                value=0.0,
                step=0.01,
                help="قیمت فروش خودکار در صورت رسیدن به سود هدف"
            )
        
        # Auto-calculate stop loss and take profit
        col1, col2 = st.columns(2)
        
        with col1:
            if st.checkbox("محاسبه خودکار حد ضرر"):
                stop_loss_pct = st.slider("درصد حد ضرر:", 1, 20, 5)
                calculated_stop_loss = entry_price * (1 - stop_loss_pct / 100)
                st.info(f"حد ضرر محاسبه شده: ${calculated_stop_loss:.2f}")
                stop_loss = calculated_stop_loss
        
        with col2:
            if st.checkbox("محاسبه خودکار هدف سود"):
                take_profit_pct = st.slider("درصد هدف سود:", 1, 50, 10)
                calculated_take_profit = entry_price * (1 + take_profit_pct / 100)
                st.info(f"هدف سود محاسبه شده: ${calculated_take_profit:.2f}")
                take_profit = calculated_take_profit
        
        # Validate symbol before adding
        symbol_valid = False
        if symbol:
            data_handler = DataHandler()
            symbol_valid = data_handler.validate_symbol(symbol.upper())
            
            if symbol_valid:
                st.success(f"✅ نماد {symbol.upper()} معتبر است")
                # Show current price
                try:
                    df = data_handler.get_market_data(symbol.upper(), '1d', '1d')
                    if df is not None and not df.empty:
                        current_price = df['Close'].iloc[-1]
                        price_diff = current_price - entry_price
                        price_diff_pct = (price_diff / entry_price) * 100
                        st.info(f"قیمت فعلی: ${current_price:.2f} ({price_diff_pct:+.2f}%)")
                except:
                    pass
            else:
                st.error(f"❌ نماد {symbol.upper()} معتبر نیست")
        
        submitted = st.form_submit_button("➕ افزودن به پرتفولیو")
        
        if submitted:
            if not symbol:
                st.error("❌ لطفاً نماد سهم را وارد کنید")
            elif not symbol_valid:
                st.error("❌ نماد وارد شده معتبر نیست")
            elif shares <= 0:
                st.error("❌ تعداد سهام باید بیشتر از صفر باشد")
            elif entry_price <= 0:
                st.error("❌ قیمت ورود باید بیشتر از صفر باشد")
            else:
                # Check if symbol already exists
                if symbol.upper() in st.session_state.portfolio['Symbol'].values:
                    st.warning(f"⚠️ نماد {symbol.upper()} قبلاً در پرتفولیو موجود است")
                else:
                    # Add new position
                    new_position = pd.DataFrame([{
                        'Symbol': symbol.upper(),
                        'Shares': shares,
                        'Entry_Price': entry_price,
                        'Entry_Date': entry_date.strftime('%Y-%m-%d'),
                        'Stop_Loss': stop_loss,
                        'Take_Profit': take_profit
                    }])
                    
                    st.session_state.portfolio = pd.concat([
                        st.session_state.portfolio, 
                        new_position
                    ], ignore_index=True)
                    
                    st.success(f"✅ موقعیت {symbol.upper()} با موفقیت به پرتفولیو اضافه شد")
                    st.rerun()
    
    # Quick add from signals
    st.subheader("🎯 افزودن سریع از سیگنال‌ها")
    
    if 'selected_symbol' in st.session_state:
        current_symbol = st.session_state.selected_symbol
        
        try:
            data_handler = DataHandler()
            df = data_handler.get_market_data(current_symbol, '1mo', '1d')
            
            if df is not None and not df.empty:
                ta = TechnicalAnalysis()
                df = ta.calculate_all_indicators(df)
                
                signal_gen = SignalGenerator()
                signals_df = signal_gen.generate_signals(df)
                
                latest_signal = signals_df['Signal'].iloc[-1]
                signal_strength = signals_df['Signal_Strength'].iloc[-1]
                current_price = df['Close'].iloc[-1]
                
                if latest_signal != 0 and abs(signal_strength) >= 0.6:
                    signal_type = "خرید" if latest_signal == 1 else "فروش"
                    signal_color = "🟢" if latest_signal == 1 else "🔴"
                    
                    st.success(f"{signal_color} سیگنال {signal_type} قوی برای {current_symbol}")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.info(f"قیمت فعلی: ${current_price:.2f}")
                        st.info(f"قوت سیگنال: {abs(signal_strength):.2f}")
                    
                    with col2:
                        quick_shares = st.number_input(
                            "تعداد سهام برای افزودن سریع:",
                            min_value=1,
                            value=100,
                            key="quick_shares"
                        )
                        
                        if st.button(f"⚡ افزودن سریع {current_symbol}"):
                            if current_symbol not in st.session_state.portfolio['Symbol'].values:
                                # Calculate automatic stop loss and take profit
                                if latest_signal == 1:  # Buy signal
                                    auto_stop_loss = current_price * 0.98  # 2% stop loss
                                    auto_take_profit = current_price * 1.04  # 4% take profit
                                else:  # Sell signal (short position)
                                    auto_stop_loss = current_price * 1.02
                                    auto_take_profit = current_price * 0.96
                                
                                new_position = pd.DataFrame([{
                                    'Symbol': current_symbol,
                                    'Shares': quick_shares if latest_signal == 1 else -quick_shares,
                                    'Entry_Price': current_price,
                                    'Entry_Date': datetime.now().strftime('%Y-%m-%d'),
                                    'Stop_Loss': auto_stop_loss,
                                    'Take_Profit': auto_take_profit
                                }])
                                
                                st.session_state.portfolio = pd.concat([
                                    st.session_state.portfolio,
                                    new_position
                                ], ignore_index=True)
                                
                                st.success(f"✅ {current_symbol} بر اساس سیگنال به پرتفولیو اضافه شد")
                                st.rerun()
                            else:
                                st.warning(f"⚠️ {current_symbol} قبلاً در پرتفولیو موجود است")
                else:
                    st.info("⏳ در انتظار سیگنال قوی برای افزودن سریع...")
        except Exception as e:
            st.error(f"خطا در دریافت سیگنال: {str(e)}")

def show_performance_analysis():
    st.subheader("📈 تحلیل عملکرد پرتفولیو")
    
    portfolio = st.session_state.portfolio
    
    if portfolio.empty:
        st.info("🏛️ پرتفولیو شما خالی است.")
        return
    
    # Performance over time simulation
    st.subheader("📊 عملکرد در طول زمان")
    
    # Generate sample performance data (in a real app, this would be historical data)
    days = 30
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # Simulate portfolio performance
    base_value = 10000
    returns = np.random.normal(0.001, 0.02, days)  # Daily returns with slight positive bias
    portfolio_values = [base_value]
    
    for r in returns:
        portfolio_values.append(portfolio_values[-1] * (1 + r))
    
    # Create benchmark (market index)
    benchmark_returns = np.random.normal(0.0005, 0.015, days)
    benchmark_values = [base_value]
    
    for r in benchmark_returns:
        benchmark_values.append(benchmark_values[-1] * (1 + r))
    
    performance_df = pd.DataFrame({
        'Date': dates,
        'Portfolio': portfolio_values[1:],
        'Benchmark': benchmark_values[1:]
    })
    
    # Performance chart
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=performance_df['Date'],
        y=performance_df['Portfolio'],
        mode='lines',
        name='پرتفولیو',
        line=dict(color='blue', width=3)
    ))
    
    fig.add_trace(go.Scatter(
        x=performance_df['Date'],
        y=performance_df['Benchmark'],
        mode='lines',
        name='شاخص مرجع',
        line=dict(color='gray', width=2, dash='dash')
    ))
    
    fig.update_layout(
        title="مقایسه عملکرد پرتفولیو با شاخص مرجع",
        xaxis_title="تاریخ",
        yaxis_title="ارزش ($)",
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Performance metrics
    col1, col2, col3, col4 = st.columns(4)
    
    portfolio_return = (portfolio_values[-1] / portfolio_values[0] - 1) * 100
    benchmark_return = (benchmark_values[-1] / benchmark_values[0] - 1) * 100
    alpha = portfolio_return - benchmark_return
    
    portfolio_volatility = np.std(returns) * np.sqrt(252) * 100
    sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    
    with col1:
        st.metric("بازده پرتفولیو", f"{portfolio_return:.2f}%")
    
    with col2:
        st.metric("بازده شاخص مرجع", f"{benchmark_return:.2f}%")
    
    with col3:
        st.metric("آلفا", f"{alpha:.2f}%", help="عملکرد اضافی نسبت به شاخص مرجع")
    
    with col4:
        st.metric("نسبت شارپ", f"{sharpe_ratio:.2f}", help="نسبت بازده به ریسک")
    
    # Sector allocation analysis
    st.subheader("🏭 تحلیل بخشی")
    
    # Get sector information for each symbol
    data_handler = DataHandler()
    sector_data = {}
    
    for symbol in portfolio['Symbol'].unique():
        try:
            company_info = data_handler.get_company_info(symbol)
            if company_info:
                sector = company_info.get('sector', 'نامشخص')
                sector_data[symbol] = sector
            else:
                sector_data[symbol] = 'نامشخص'
        except:
            sector_data[symbol] = 'نامشخص'
    
    # Calculate sector allocation
    portfolio_with_sectors = portfolio.copy()
    portfolio_with_sectors['Sector'] = portfolio_with_sectors['Symbol'].map(sector_data)
    
    # Get current values for sector analysis
    current_values = []
    for _, position in portfolio_with_sectors.iterrows():
        try:
            df = data_handler.get_market_data(position['Symbol'], '1d', '1d')
            if df is not None and not df.empty:
                current_price = df['Close'].iloc[-1]
                current_value = position['Shares'] * current_price
                current_values.append(current_value)
            else:
                current_values.append(0)
        except:
            current_values.append(0)
    
    portfolio_with_sectors['Current_Value'] = current_values
    
    # Sector allocation chart
    if not portfolio_with_sectors.empty and portfolio_with_sectors['Current_Value'].sum() > 0:
        sector_allocation = portfolio_with_sectors.groupby('Sector')['Current_Value'].sum()
        
        fig = px.pie(
            values=sector_allocation.values,
            names=sector_allocation.index,
            title="تخصیص بخشی پرتفولیو"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    # Risk metrics
    st.subheader("⚠️ معیارهای ریسک")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        var_95 = np.percentile(returns, 5) * base_value
        st.metric("VaR روزانه (95%)", f"${var_95:,.0f}", help="حداکثر زیان احتمالی در 95% موارد")
    
    with col2:
        max_drawdown = np.min(np.array(portfolio_values) / np.maximum.accumulate(portfolio_values) - 1) * 100
        st.metric("حداکثر افت", f"{max_drawdown:.2f}%", help="بیشترین کاهش از اوج قیمت")
    
    with col3:
        beta = np.cov(returns[1:], benchmark_returns[1:])[0, 1] / np.var(benchmark_returns[1:]) if len(returns) > 1 else 1.0
        st.metric("بتا", f"{beta:.2f}", help="حساسیت نسبت به بازار")

def show_risk_management():
    st.subheader("⚙️ مدیریت ریسک پرتفولیو")
    
    # Risk management settings
    with st.expander("📊 تنظیمات مدیریت ریسک"):
        col1, col2 = st.columns(2)
        
        with col1:
            max_position_size = st.slider(
                "حداکثر اندازه موقعیت (% از پرتفولیو):",
                min_value=1,
                max_value=50,
                value=10,
                help="حداکثر درصدی از پرتفولیو که می‌تواند به یک موقعیت اختصاص یابد"
            )
            
            max_sector_allocation = st.slider(
                "حداکثر تخصیص بخشی (%):",
                min_value=10,
                max_value=100,
                value=30,
                help="حداکثر درصدی از پرتفولیو که می‌تواند به یک بخش اختصاص یابد"
            )
        
        with col2:
            portfolio_stop_loss = st.slider(
                "حد ضرر کل پرتفولیو (%):",
                min_value=1.0,
                max_value=20.0,
                value=5.0,
                step=0.5,
                help="در صورت رسیدن به این میزان ضرر، تمام موقعیت‌ها بسته شود"
            )
            
            correlation_threshold = st.slider(
                "حد آستانه همبستگی:",
                min_value=0.1,
                max_value=1.0,
                value=0.7,
                step=0.1,
                help="هشدار در صورت همبستگی بالای دارایی‌ها"
            )
    
    # Risk alerts and warnings
    st.subheader("🚨 هشدارهای ریسک")
    
    portfolio = st.session_state.portfolio
    
    if portfolio.empty:
        st.info("🏛️ پرتفولیو شما خالی است.")
        return
    
    # Calculate current portfolio value and check risks
    data_handler = DataHandler()
    total_portfolio_value = 0
    position_risks = []
    
    for _, position in portfolio.iterrows():
        try:
            df = data_handler.get_market_data(position['Symbol'], '1d', '1d')
            if df is not None and not df.empty:
                current_price = df['Close'].iloc[-1]
                position_value = abs(position['Shares']) * current_price
                total_portfolio_value += position_value
                
                position_risks.append({
                    'Symbol': position['Symbol'],
                    'Value': position_value,
                    'Shares': position['Shares'],
                    'Current_Price': current_price,
                    'Entry_Price': position['Entry_Price'],
                    'Stop_Loss': position.get('Stop_Loss', 0),
                    'Take_Profit': position.get('Take_Profit', 0)
                })
        except:
            continue
    
    # Check for risk violations
    risk_alerts = []
    
    # Position size risk
    for pos in position_risks:
        position_pct = (pos['Value'] / total_portfolio_value) * 100 if total_portfolio_value > 0 else 0
        if position_pct > max_position_size:
            risk_alerts.append({
                'Type': 'اندازه موقعیت',
                'Symbol': pos['Symbol'],
                'Message': f"موقعیت {pos['Symbol']} {position_pct:.1f}% از پرتفولیو را تشکیل می‌دهد (حد مجاز: {max_position_size}%)",
                'Severity': 'متوسط'
            })
    
    # Stop loss alerts
    for pos in position_risks:
        if pos['Stop_Loss'] > 0:
            if pos['Shares'] > 0 and pos['Current_Price'] <= pos['Stop_Loss']:
                risk_alerts.append({
                    'Type': 'حد ضرر',
                    'Symbol': pos['Symbol'],
                    'Message': f"قیمت {pos['Symbol']} به حد ضرر ${pos['Stop_Loss']:.2f} رسیده است",
                    'Severity': 'بالا'
                })
            elif pos['Shares'] < 0 and pos['Current_Price'] >= pos['Stop_Loss']:
                risk_alerts.append({
                    'Type': 'حد ضرر',
                    'Symbol': pos['Symbol'],
                    'Message': f"قیمت {pos['Symbol']} به حد ضرر ${pos['Stop_Loss']:.2f} رسیده است",
                    'Severity': 'بالا'
                })
    
    # Take profit alerts
    for pos in position_risks:
        if pos['Take_Profit'] > 0:
            if pos['Shares'] > 0 and pos['Current_Price'] >= pos['Take_Profit']:
                risk_alerts.append({
                    'Type': 'هدف سود',
                    'Symbol': pos['Symbol'],
                    'Message': f"قیمت {pos['Symbol']} به هدف سود ${pos['Take_Profit']:.2f} رسیده است",
                    'Severity': 'پایین'
                })
            elif pos['Shares'] < 0 and pos['Current_Price'] <= pos['Take_Profit']:
                risk_alerts.append({
                    'Type': 'هدف سود',
                    'Symbol': pos['Symbol'],
                    'Message': f"قیمت {pos['Symbol']} به هدف سود ${pos['Take_Profit']:.2f} رسیده است",
                    'Severity': 'پایین'
                })
    
    # Display alerts
    if risk_alerts:
        for alert in risk_alerts:
            if alert['Severity'] == 'بالا':
                st.error(f"🔴 {alert['Type']}: {alert['Message']}")
            elif alert['Severity'] == 'متوسط':
                st.warning(f"🟡 {alert['Type']}: {alert['Message']}")
            else:
                st.success(f"🟢 {alert['Type']}: {alert['Message']}")
    else:
        st.success("✅ هیچ هشدار ریسک فعالی وجود ندارد")
    
    # Portfolio correlation analysis
    st.subheader("🔗 تحلیل همبستگی")
    
    symbols = portfolio['Symbol'].unique()
    if len(symbols) > 1:
        try:
            correlation_matrix = data_handler.calculate_correlation_matrix(symbols, period='3mo')
            
            if correlation_matrix is not None:
                # Create correlation heatmap
                fig = px.imshow(
                    correlation_matrix,
                    text_auto=True,
                    aspect="auto",
                    color_continuous_scale='RdYlBu_r',
                    title="ماتریس همبستگی دارایی‌های پرتفولیو"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Check for high correlations
                high_corr_pairs = []
                for i in range(len(correlation_matrix.columns)):
                    for j in range(i+1, len(correlation_matrix.columns)):
                        corr_value = correlation_matrix.iloc[i, j]
                        if abs(corr_value) >= correlation_threshold:
                            high_corr_pairs.append({
                                'Pair': f"{correlation_matrix.columns[i]} - {correlation_matrix.columns[j]}",
                                'Correlation': corr_value
                            })
                
                if high_corr_pairs:
                    st.warning("⚠️ جفت‌های دارایی با همبستگی بالا:")
                    for pair in high_corr_pairs:
                        st.write(f"• {pair['Pair']}: {pair['Correlation']:.2f}")
                else:
                    st.success("✅ همبستگی دارایی‌ها در حد مطلوب است")
            
        except Exception as e:
            st.error(f"خطا در محاسبه همبستگی: {str(e)}")
    else:
        st.info("برای تحلیل همبستگی حداقل 2 دارایی در پرتفولیو نیاز است")
    
    # Emergency actions
    st.subheader("🆘 اقدامات اضطراری")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🚨 بستن تمام موقعیت‌ها", type="secondary"):
            if st.session_state.get('confirm_close_all', False):
                st.session_state.portfolio = pd.DataFrame(columns=[
                    'Symbol', 'Shares', 'Entry_Price', 'Entry_Date', 'Stop_Loss', 'Take_Profit'
                ])
                st.session_state.confirm_close_all = False
                st.success("✅ تمام موقعیت‌ها بسته شد")
                st.rerun()
            else:
                st.session_state.confirm_close_all = True
                st.warning("⚠️ برای تأیید دوباره کلیک کنید")
    
    with col2:
        if st.button("📉 بستن موقعیت‌های زیان‌ده"):
            losing_positions = []
            for _, position in portfolio.iterrows():
                try:
                    df = data_handler.get_market_data(position['Symbol'], '1d', '1d')
                    if df is not None and not df.empty:
                        current_price = df['Close'].iloc[-1]
                        if position['Shares'] > 0 and current_price < position['Entry_Price']:
                            losing_positions.append(position.name)
                        elif position['Shares'] < 0 and current_price > position['Entry_Price']:
                            losing_positions.append(position.name)
                except:
                    continue
            
            if losing_positions:
                st.session_state.portfolio = st.session_state.portfolio.drop(losing_positions).reset_index(drop=True)
                st.success(f"✅ {len(losing_positions)} موقعیت زیان‌ده بسته شد")
                st.rerun()
            else:
                st.info("هیچ موقعیت زیان‌ده‌ای یافت نشد")
    
    with col3:
        if st.button("🎯 اعمال حد ضرر خودکار"):
            updated_positions = 0
            for idx, position in portfolio.iterrows():
                if position.get('Stop_Loss', 0) == 0:
                    # Set automatic stop loss at 5% below entry price
                    auto_stop_loss = position['Entry_Price'] * 0.95
                    st.session_state.portfolio.loc[idx, 'Stop_Loss'] = auto_stop_loss
                    updated_positions += 1
            
            if updated_positions > 0:
                st.success(f"✅ حد ضرر خودکار برای {updated_positions} موقعیت تنظیم شد")
                st.rerun()
            else:
                st.info("تمام موقعیت‌ها قبلاً حد ضرر دارند")

if __name__ == "__main__":
    show_portfolio()
├── app.py                    # فایل اصلی اپلیکیشن
├── utils/
│   ├── data_handler.py      # مدیریت داده‌های بازار
│   ├── technical_analysis.py # تحلیل تکنیکال
│   └── signal_generator.py  # تولید سیگنال‌های معاملاتی
├── pages/
│   ├── dashboard.py         # داشبورد مدیریت
│   ├── chart_analysis.py    # تحلیل نمودار پیشرفته
│   ├── signals.py          # مرکز سیگنال‌های معاملاتی
│   ├── portfolio.py        # مدیریت پرتفولیو
│   ├── symbol_explorer.py   # کاوشگر نمادها
│   └── live_prices.py      # قیمت‌های لحظه‌ای
├── .streamlit/
│   └── config.toml         # تنظیمات Streamlit
└── replit.md              # مستندات پروژه
