#property copyright "xAI"
#property link      "https://x.ai"
#property version   "2.31"
#property strict
#include <Trade\Trade.mqh>
#include <Arrays\ArrayString.mqh>

//--- Input Parameters
input string   SymbolsToTrade     = "EURUSD,GBPUSD,USDJPY"; // Comma-separated symbols
input double   RiskPercent        = 1.0;                    // Risk per trade (%)
input double   SL_Pips            = 20;                     // Stop-loss in pips
input double   RR_Ratio           = 2.0;                    // Reward:Risk ratio
input int      MaxOpenTrades      = 5;                      // Max open trades per symbol
input double   DailyLossLimitPct  = 5.0;                    // Daily loss limit (%)
input bool     UseTrailingStop    = true;                   // Use trailing stop
input int      TrailATRPeriod     = 14;                     // ATR period for trailing stop
input bool     EnableNewsFilter   = true;                   // Enable news filter
input int      NewsPauseMinutes   = 30;                     // Pause duration around news (minutes)
input int      MaxConsecLosses    = 3;                      // Max consecutive losses
input int      PauseAfterLossesMins = 60;                   // Pause after losses (minutes)
input string   TradeSession       = "London,NewYork,Tokyo"; // Trading sessions
input bool     EnableEmailAlerts  = true;                   // Enable email notifications

//--- Global Variables
CTrade trade;
double AccountEquityStart;
int ConsecutiveLosses = 0;
datetime LastLossTime = 0;
bool TradingPaused = false;
datetime LastBarTime = 0;
int TradeWins = 0;
int TradeLosses = 0;
CArrayString *SymbolsArray;

//--- Structs for trade tracking
struct TradeStats {
   double dailyLoss;
   int openTrades;
   int totalTrades;
   int wins;
   int losses;
};

//--- Session times (in broker time)
struct SessionTimes {
   int londonOpen;
   int londonClose;
   int newYorkOpen;
   int newYorkClose;
   int tokyoOpen;
   int tokyoClose;
};

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   // Initialize symbol array
   SymbolsArray = new CArrayString;
   StringSplit(SymbolsToTrade, ',', SymbolsArray);
   
   // Verify symbols are available
   for(int i=0; i<SymbolsArray.Total(); i++)
   {
      if(!SymbolInfoInteger(SymbolsArray.At(i), SYMBOL_SELECT))
      {
         Print("Symbol not available: ", SymbolsArray.At(i));
         return(INIT_FAILED);
      }
   }
   
   // Set initial equity
   AccountEquityStart = AccountEquity();
   
   // Initialize trade object
   trade.SetExpertMagicNumber(12345);
   trade.SetMarginMode();
   trade.SetTypeFillingBySymbol(_Symbol);
   
   Print("EA Initialized. Trading ", SymbolsArray.Total(), " symbols.");
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   delete SymbolsArray;
   Print("EA Deinitialized. Final Stats - Wins: ", TradeWins, ", Losses: ", TradeLosses);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check if trading is paused
   if(TradingPaused)
   {
      if(TimeCurrent() > LastLossTime + (PauseAfterLossesMins * 60))
      {
         TradingPaused = false;
         Print("Trading resumed after pause period.");
      }
      else
      {
         return;
      }
   }
   
   // Check daily loss limit
   if(CheckDailyLossLimit())
   {
      Print("Daily loss limit reached. No new trades will be opened today.");
      return;
   }
   
   // Process each symbol
   for(int i=0; i<SymbolsArray.Total(); i++)
   {
      string symbol = SymbolsArray.At(i);
      
      // Check trading session
      if(!IsTradingSession(symbol))
         continue;
         
      // Check for new bar
      if(IsNewBar(symbol))
      {
         // Check news filter
         if(EnableNewsFilter && IsNewsTime(symbol))
         {
            Print("News filter active for ", symbol, ". Skipping trade.");
            continue;
         }
         
         // Trading logic
         CheckForEntry(symbol);
      }
      
      // Manage open positions
      ManageOpenPositions(symbol);
   }
}

//+------------------------------------------------------------------+
//| Check for new trading entry                                      |
//+------------------------------------------------------------------+
void CheckForEntry(string symbol)
{
   // Check max open trades
   if(CountOpenTrades(symbol) >= MaxOpenTrades)
      return;
      
   // Your trading strategy logic here
   // Example: Simple moving average crossover
   double maFast = iMA(symbol, PERIOD_CURRENT, 10, 0, MODE_SMA, PRICE_CLOSE, 0);
   double maSlow = iMA(symbol, PERIOD_CURRENT, 50, 0, MODE_SMA, PRICE_CLOSE, 0);
   
   double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD) * point;
   
   // Calculate position size based on risk
   double riskAmount = AccountEquity() * (RiskPercent / 100);
   double slDistance = SL_Pips * point;
   double lotSize = NormalizeDouble(riskAmount / (slDistance * SymbolInfoDouble(symbol, SYMBOL_TRADE_CONTRACT_SIZE)), 2);
   
   // Ensure minimum and maximum lot size
   lotSize = MathMax(lotSize, SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN));
   lotSize = MathMin(lotSize, SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX));
   
   if(maFast > maSlow && maFast > bid)
   {
      // Buy signal
      double sl = bid - slDistance;
      double tp = bid + (slDistance * RR_Ratio);
      
      if(trade.Buy(lotSize, symbol, bid, sl, tp, "Buy Order"))
      {
         Print("Buy order opened for ", symbol, " at ", bid, " SL: ", sl, " TP: ", tp);
      }
      else
      {
         Print("Failed to open Buy order for ", symbol, " Error: ", GetLastError());
      }
   }
   else if(maFast < maSlow && maFast < bid)
   {
      // Sell signal
      double sl = ask + slDistance;
      double tp = ask - (slDistance * RR_Ratio);
      
      if(trade.Sell(lotSize, symbol, ask, sl, tp, "Sell Order"))
      {
         Print("Sell order opened for ", symbol, " at ", ask, " SL: ", sl, " TP: ", tp);
      }
      else
      {
         Print("Failed to open Sell order for ", symbol, " Error: ", GetLastError());
      }
   }
}

//+------------------------------------------------------------------+
//| Manage open positions                                            |
//+------------------------------------------------------------------+
void ManageOpenPositions(string symbol)
{
   if(UseTrailingStop)
   {
      TrailingStop(symbol);
   }
   
   // Other position management logic can be added here
}

//+------------------------------------------------------------------+
//| Trailing stop function                                           |
//+------------------------------------------------------------------+
void TrailingStop(string symbol)
{
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   double atr = iATR(symbol, PERIOD_CURRENT, TrailATRPeriod, 0);
   
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      if(PositionSelect(PositionGetSymbol(i))
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == 12345)
         {
            double currentStop = PositionGetDouble(POSITION_SL);
            double newStop = 0;
            
            if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
            {
               newStop = SymbolInfoDouble(symbol, SYMBOL_BID) - (atr * 1.5);
               newStop = NormalizeDouble(newStop, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
               
               if(newStop > currentStop || currentStop == 0)
               {
                  if(!trade.PositionModify(PositionGetInteger(POSITION_TICKET), newStop, PositionGetDouble(POSITION_TP)))
                  {
                     Print("Failed to modify buy position stop. Error: ", GetLastError());
                  }
               }
            }
            else if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
            {
               newStop = SymbolInfoDouble(symbol, SYMBOL_ASK) + (atr * 1.5);
               newStop = NormalizeDouble(newStop, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
               
               if(newStop < currentStop || currentStop == 0)
               {
                  if(!trade.PositionModify(PositionGetInteger(POSITION_TICKET), newStop, PositionGetDouble(POSITION_TP)))
                  {
                     Print("Failed to modify sell position stop. Error: ", GetLastError());
                  }
               }
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check if new bar has formed                                      |
//+------------------------------------------------------------------+
bool IsNewBar(string symbol)
{
   datetime currentBarTime = (datetime)SeriesInfoInteger(symbol, PERIOD_CURRENT, SERIES_LASTBAR_DATE);
   
   if(currentBarTime != LastBarTime)
   {
      LastBarTime = currentBarTime;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Check if current time is within trading session                  |
//+------------------------------------------------------------------+
bool IsTradingSession(string symbol)
{
   // This is a simplified version. You would need to implement proper session checking
   // based on the TradeSession input and broker time
   MqlDateTime timeStruct;
   TimeCurrent(timeStruct);
   
   // Example: Check if current hour is between 8am and 5pm (would need adjustment)
   return (timeStruct.hour >= 8 && timeStruct.hour < 17);
}

//+------------------------------------------------------------------+
//| Check if current time is around news event                       |
//+------------------------------------------------------------------+
bool IsNewsTime(string symbol)
{
   // This is a placeholder. You would need to implement actual news checking
   // possibly through an external calendar or web service
   return false;
}

//+------------------------------------------------------------------+
//| Check daily loss limit                                           |
//+------------------------------------------------------------------+
bool CheckDailyLossLimit()
{
   double currentEquity = AccountEquity();
   double lossPercent = ((AccountEquityStart - currentEquity) / AccountEquityStart) * 100;
   
   return (lossPercent >= DailyLossLimitPct);
}

//+------------------------------------------------------------------+
//| Count open trades for a symbol                                   |
//+------------------------------------------------------------------+
int CountOpenTrades(string symbol)
{
   int count = 0;
   
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      if(PositionSelect(PositionGetSymbol(i)))
      {
         if(PositionGetString(POSITION_SYMBOL) == symbol && PositionGetInteger(POSITION_MAGIC) == 12345)
         {
            count++;
         }
      }
   }
   
   return count;
}

//+------------------------------------------------------------------+
//| Trade transaction function                                       |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                       const MqlTradeRequest& request,
                       const MqlTradeResult& result)
{
   // Track trade results for statistics
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      if(HistoryDealSelect(trans.deal))
      {
         long dealType = HistoryDealGetInteger(trans.deal, DEAL_TYPE);
         double profit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         
         if(dealType == DEAL_TYPE_BUY || dealType == DEAL_TYPE_SELL)
         {
            if(profit > 0)
            {
               TradeWins++;
               ConsecutiveLosses = 0;
            }
            else if(profit < 0)
            {
               TradeLosses++;
               ConsecutiveLosses++;
               LastLossTime = TimeCurrent();
               
               if(ConsecutiveLosses >= MaxConsecLosses)
               {
                  TradingPaused = true;
                  if(EnableEmailAlerts)
                  {
                     SendMail("Trading Paused - Max Consecutive Losses Reached",
                            "The EA has paused trading after " + IntegerToString(MaxConsecLosses) + " consecutive losses.");
                  }
               }
            }
         }
      }
   }
}