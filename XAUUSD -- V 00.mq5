//+------------------------------------------------------------------+
//| XAUUSD-V6.mq5                                                    |
//| Simple Expert Advisor for XAUUSD                                  |
//+------------------------------------------------------------------+
#property copyright "Your Name"
#property link      "https://www.example.com"
#property version   "6.00"

// Input parameters
input double LotSize = 0.1;         // Lot size
input int StopLoss = 500;           // Stop Loss (in points)
input int TakeProfit = 1000;        // Take Profit (in points)
input int MA_Period = 20;           // Moving Average Period

//+------------------------------------------------------------------+
//| Expert initialization function                                     |
//+------------------------------------------------------------------+
int OnInit()
{
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Check if we already have an open position
   if(PositionsTotal() > 0) return;

   // Get Moving Average
   double ma[];
   ArraySetAsSeries(ma, true);
   int maHandle = iMA(_Symbol, PERIOD_CURRENT, MA_Period, 0, MODE_SMA, PRICE_CLOSE);
   CopyBuffer(maHandle, 0, 0, 3, ma);

   // Get current price
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   // Buy condition: Price above MA
   if(ask > ma[0])
   {
      MqlTradeRequest request = {};
      MqlTradeResult result = {};
      request.action = TRADE_ACTION_DEAL;
      request.symbol = _Symbol;
      request.volume = LotSize;
      request.type = ORDER_TYPE_BUY;
      request.price = ask;
      request.sl = ask - StopLoss * _Point;
      request.tp = ask + TakeProfit * _Point;
      request.deviation = 10;
      OrderSend(request, result);
   }

   // Sell condition: Price below MA
   if(bid < ma[0])
   {
      MqlTradeRequest request = {};
      MqlTradeResult result = {};
      request.action = TRADE_ACTION_DEAL;
      request.symbol = _Symbol;
      request.volume = LotSize;
      request.type = ORDER_TYPE_SELL;
      request.price = bid;
      request.sl = bid + StopLoss * _Point;
      request.tp = bid - TakeProfit * _Point;
      request.deviation = 10;
      OrderSend(request, result);
   }
}
//+------------------------------------------------------------------+