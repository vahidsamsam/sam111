//+------------------------------------------------------------------+
//| Optimized Expert Advisor for Trading (XAUUSD-V3.mq5)             |
//+------------------------------------------------------------------+
#include <Trade\Trade.mqh>
input string SYMBOL = "XAUUSD";           // Symbol to trade
input double BASE_LOT_SIZE = 0.1;         // Base lot size
input int SL_PIPS = 200;                 // Stop loss in pips
input int TP_PIPS = 400;                 // Take profit in pips
input ENUM_TIMEFRAMES TimeFrame = PERIOD_M5; // Timeframe
input bool AvoidNews = true;             // Avoid trading during news
input string NewsStartTime = "13:30";    // News start time
input string NewsEndTime = "14:30";      // News end time
input int SleepSeconds = 5;              // Sleep between ticks (seconds)
input double LOT_MULTIPLIER = 2.0;       // Lot multiplier for loss recovery
input double EQUITY_USAGE = 0.10;        // Use 10% of equity

CTrade trade;
MqlRates rates[];
double last_loss = 0.0;                  // Track last position loss
double current_lot_size = BASE_LOT_SIZE; // Current lot size

//+------------------------------------------------------------------+
//| Check if current time is during news period                       |
//+------------------------------------------------------------------+
bool IsDuringNews()
{
   string now = TimeToString(TimeCurrent(), TIME_MINUTES);
   if(AvoidNews && now >= NewsStartTime && now <= NewsEndTime)
   {
      Print("News time detected: ", now);
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Get historical candles for price action analysis                  |
//+------------------------------------------------------------------+
bool GetCandles()
{
   ArraySetAsSeries(rates, true);
   datetime fromTime = TimeCurrent() - 60 * PeriodSeconds(TimeFrame) * 3;
   int copied = CopyRates(SYMBOL, TimeFrame, fromTime, TimeCurrent(), rates);
   if(copied <= 0)
   {
      Print("Error getting candles: ", GetLastError());
      return false;
   }
   return true;
}

//+------------------------------------------------------------------+
//| Check price action for buy/sell signals                           |
//+------------------------------------------------------------------+
string CheckPriceAction()
{
   if(ArraySize(rates) < 3)
   {
      Print("Insufficient candles: ", ArraySize(rates));
      return "";
   }
   
   MqlRates current = rates[0];  // Most recent candle
   MqlRates previous = rates[1]; // Previous candle

   if(current.close > previous.high)
      return "buy";
   else if(current.close < previous.low)
      return "sell";
   else
      return "";
}

//+------------------------------------------------------------------+
//| Calculate stop loss and take profit levels                       |
//+------------------------------------------------------------------+
void CalculateLevels(string action, double price, double &sl, double &tp)
{
   double point = SymbolInfoDouble(SYMBOL, SYMBOL_POINT);
   double sl_pips = SL_PIPS * point;
   double tp_pips = TP_PIPS * point;
   
   if(action == "buy")
   {
      sl = price - sl_pips;
      tp = price + tp_pips;
   }
   else if(action == "sell")
   {
      sl = price + sl_pips;
      tp = price - tp_pips;
   }
}

//+------------------------------------------------------------------+
//| Calculate lot size based on equity and loss recovery              |
//+------------------------------------------------------------------+
double CalculateLotSize()
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY); // Use correct function
   double lot_size = BASE_LOT_SIZE;
   
   // If last position was a loss, multiply lot size
   if(last_loss < 0.0)
   {
      lot_size = current_lot_size * LOT_MULTIPLIER;
   }
   else
   {
      lot_size = BASE_LOT_SIZE; // Reset to base lot size on profit or no loss
   }
   
   // Adjust lot size to use approximately 10% of equity
   double max_lot = NormalizeDouble(equity * EQUITY_USAGE / 10000.0, 2); // Risk-based calculation
   lot_size = MathMin(lot_size, max_lot);
   
   // Ensure lot size is within symbol constraints
   double min_lot = SymbolInfoDouble(SYMBOL, SYMBOL_VOLUME_MIN);
   double max_lot_allowed = SymbolInfoDouble(SYMBOL, SYMBOL_VOLUME_MAX);
   lot_size = MathMax(min_lot, MathMin(max_lot_allowed, lot_size));
   
   return NormalizeDouble(lot_size, 2);
}

//+------------------------------------------------------------------+
//| Place a new order based on signal                                 |
//+------------------------------------------------------------------+
void PlaceOrder(string signal)
{
   // Prevent multiple positions
   if(PositionsTotal() > 0)
   {
      Print("Position already open. Skipping new order.");
      return;
   }
   
   ENUM_ORDER_TYPE order_type = (signal == "buy") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   double price = (signal == "buy") ? SymbolInfoDouble(SYMBOL, SYMBOL_ASK) : SymbolInfoDouble(SYMBOL, SYMBOL_BID);
   double sl, tp;
   CalculateLevels(signal, price, sl, tp);
   
   double lot_size = CalculateLotSize();
   trade.SetExpertMagicNumber(123456);
   bool sent = trade.PositionOpen(SYMBOL, order_type, lot_size, price, sl, tp, "auto_trade_bot");
   if(sent)
   {
      current_lot_size = lot_size;
      Print("Order placed: ", signal, ", Lot: ", lot_size, ", Price: ", price, ", SL: ", sl, ", TP: ", tp);
   }
   else
   {
      Print("Failed to place order: ", GetLastError());
   }
}

//+------------------------------------------------------------------+
//| Close all open positions for the symbol                           |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket) && PositionGetString(POSITION_SYMBOL) == SYMBOL)
      {
         double profit = PositionGetDouble(POSITION_PROFIT);
         trade.PositionClose(ticket);
         if(profit < 0.0)
         {
            last_loss = profit; // Track loss for lot size adjustment
         }
         else
         {
            last_loss = 0.0; // Reset on profit
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Check for new bar to avoid over-trading                           |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   static datetime last_bar = 0;
   datetime current_bar = iTime(SYMBOL, TimeFrame, 0);
   if(last_bar != current_bar)
   {
      last_bar = current_bar;
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Initialization function                                          |
//+------------------------------------------------------------------+
int OnInit()
{
   // Validate symbol
   if(!SymbolSelect(SYMBOL, true))
   {
      Print("Invalid symbol: ", SYMBOL);
      return INIT_FAILED;
   }
   
   // Set array as series for easier candle access
   ArraySetAsSeries(rates, true);
   Print("Expert Advisor initialized successfully");
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Deinitialization function                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("Expert Advisor stopped. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Tick function                                                    |
//+------------------------------------------------------------------+
void OnTick()
{
   // Only process on new bar to avoid over-trading
   if(!IsNewBar())
      return;

   // Check for news time
   if(AvoidNews && IsDuringNews())
   {
      Print("News time. Skipping trading.");
      return;
   }

   // Get candle data
   if(!GetCandles())
   {
      Print("Failed to get candles");
      return;
   }

   // Check for trading signal
   string signal = CheckPriceAction();
   if(signal != "")
   {
      Print("Signal detected: ", signal);
      CloseAllPositions(); // Close any existing positions before opening new one
      PlaceOrder(signal);
   }
   else
   {
      Print("No trading signal");
   }
}