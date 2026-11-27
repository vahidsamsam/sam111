/**
 * Expert Adviser created with MQLGen
 * MQL base code updated on 2025-06-09
 * Copyright © 2025 Forex Software Ltd.
 *
 * Website : https://mqlgen.forexsb.com
 * Contacts: info@forexsb.com
 *
 * Risk Disclosure
 *
 * Futures and forex trading contains substantial risk and is not for every investor.
 * An investor could potentially lose all or more than the initial investment.
 * Risk capital is money that can be lost without jeopardizing ones’ financial security or life style.
 * Only risk capital should be used for trading and only those with sufficient risk capital should consider trading.
 */

#property copyright "Forex Software Ltd."
#property version   "1.1"
#property strict

static input string _Properties_ = "------"; // --- Expert Properties ---
static input int    Magic_Number = 1638509872; // Magic number
static input double Entry_Amount =     0.10; // Entry lots
       input int    Stop_Loss    =        0; // Stop Loss   (pips)
       input int    Take_Profit  =        0; // Take Profit (pips)

static input string ___0______   = "------"; // --- Moving Average ---
       input int    Ind0Param0   =       21; // Period
       input int    Ind0Param1   =        0; // Shift

static input string ___1______   = "------"; // --- Stochastic ---
       input int    Ind1Param0   =        9; // %K Period
       input int    Ind1Param1   =        1; // %D Period
       input int    Ind1Param2   =        3; // Slowing
       input double Ind1Param3   =     89.0; // Level

static input string _Settings___ = "------"; // --- Settings ---
static input bool   Show_inds    =    false; // Show indicators

#define TRADE_RETRY_COUNT   4
#define TRADE_RETRY_WAIT  100
#define OP_FLAT            -1
#define OP_BUY            ORDER_TYPE_BUY
#define OP_SELL           ORDER_TYPE_SELL

const double sigma = 0.000001;

int      posType       = OP_FLAT;
ulong    posTicket     = 0;
double   posLots       = 0;
double   posStopLoss   = 0;
double   posTakeProfit = 0;
double   posProfit     = 0;
double   posPriceOpen  = 0;
double   posPriceCurr  = 0;
datetime posOpenTime   = 0;

datetime barTime;
double   pip;
double   stopLevel;
bool     isTrailingStop=false;
int      indHandlers[12][2];

ENUM_ORDER_TYPE_FILLING orderFillingType = ORDER_FILLING_FOK;

//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int OnInit(void)
  {
   Comment("");
   barTime         = Time(0);
   stopLevel       = (int) SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   pip             = GetPipValue();
   isTrailingStop  = isTrailingStop && Stop_Loss > 0;

   InitIndicators();
   UpdatePosition();

   OnTick();
   ChartRedraw(0);

   return INIT_SUCCEEDED;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(Show_inds)
      RemoveIndicators();
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void OnTick(void)
  {
   if(!MQLInfoInteger(MQL_TESTER))
     {
      UpdatePosition();
     }

   const datetime time = Time(0);
   if(time > barTime)
     {
      barTime = time;
      OnBar();
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void OnBar(void)
  {
   UpdatePosition();

   if(posType != OP_FLAT)
     {
      ManageClose();
      UpdatePosition();
     }

   if(posType != OP_FLAT && isTrailingStop)
     {
      const double trailingStop = GetTrailingStopPrice();
      ManageTrailingStop(trailingStop);
      UpdatePosition();
     }

   int entrySignal = GetEntrySignal();

   if(posType == OP_FLAT && entrySignal != OP_FLAT)
     {
      OpenPosition(entrySignal);
      UpdatePosition();
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void UpdatePosition(void)
  {
   posType       = OP_FLAT;
   posTicket     = 0;
   posLots       = 0;
   posProfit     = 0;
   posStopLoss   = 0;
   posTakeProfit = 0;
   posPriceOpen  = 0;
   posPriceCurr  = 0;
   posOpenTime   = 0;

   for(int posIndex = PositionsTotal() - 1; posIndex >= 0; posIndex -= 1)
     {
      const ulong ticket = PositionGetTicket(posIndex);

      if(PositionSelectByTicket(ticket) &&
         PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == Magic_Number)
        {
         posType       = (int) PositionGetInteger(POSITION_TYPE);
         posTicket     = ticket;
         posLots       = NormalizeDouble(PositionGetDouble(POSITION_VOLUME), 2);
         posProfit     = NormalizeDouble(PositionGetDouble(POSITION_PROFIT), 2);
         posStopLoss   = NormalizeDouble(PositionGetDouble(POSITION_SL), _Digits);
         posTakeProfit = NormalizeDouble(PositionGetDouble(POSITION_TP), _Digits);
         posPriceOpen  = NormalizeDouble(PositionGetDouble(POSITION_PRICE_OPEN),    _Digits);
         posPriceCurr  = NormalizeDouble(PositionGetDouble(POSITION_PRICE_CURRENT), _Digits);
         posOpenTime   = (datetime) PositionGetInteger(POSITION_TIME);
         break;
        }
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void InitIndicators(void)
  {
   // Moving Average (Simple, Close, 21, 0)
   indHandlers[0][0] = iMA(NULL, 0, Ind0Param0, Ind0Param1, MODE_SMA, PRICE_CLOSE);
   if(Show_inds) ChartIndicatorAdd(0, 0, indHandlers[0][0]);
   // Stochastic (9, 1, 3), Levels: 89.0, 11.0
   indHandlers[1][0] = iStochastic(NULL, 0, Ind1Param0, Ind1Param1, Ind1Param2, MODE_SMA, 0);
   if(Show_inds) ChartIndicatorAdd(0, 1, indHandlers[1][0]);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void RemoveIndicators(void)
  {
   long windowsCount = -1;
   ChartGetInteger(0, CHART_WINDOWS_TOTAL, 0, windowsCount);

   for(int window = (int) windowsCount - 1; window >= 0; window--)
     {
      const int indicatorsCount = ChartIndicatorsTotal(0, window);
      for(int i = indicatorsCount - 1; i >= 0; i--)
        {
         const string name = ChartIndicatorName(0, window, i);
         ChartIndicatorDelete(0, window, name);
        }
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int GetEntrySignal(void)
  {
   // Moving Average (Simple, Close, 21, 0)
   double ind0buffer[]; CopyBuffer(indHandlers[0][0], 0, 1, 3, ind0buffer);
   double ind0val1  = ind0buffer[2];
   double ind0val2  = ind0buffer[1];
   bool   ind0long  = Open(0) < ind0val1 - sigma && Open(1) > ind0val2 + sigma;
   bool   ind0short = Open(0) > ind0val1 + sigma && Open(1) < ind0val2 - sigma;

   bool canOpenLong  = ind0long;
   bool canOpenShort = ind0short;

   return canOpenLong  && !canOpenShort ? OP_BUY
        : canOpenShort && !canOpenLong  ? OP_SELL
        : OP_FLAT;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ManageClose(void)
  {
   // Stochastic (9, 1, 3), Levels: 89.0, 11.0
   double ind1buffer[]; CopyBuffer(indHandlers[1][0], MAIN_LINE, 1, 3, ind1buffer);
   double ind1val1  = ind1buffer[2];
   bool   ind1long  = ind1val1 > Ind1Param3 + sigma;
   bool   ind1short = ind1val1 < 100 - Ind1Param3 - sigma;

   if( (posType == OP_BUY  && ind1long) ||
        (posType == OP_SELL && ind1short) )
      ClosePosition();
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void OpenPosition(const int command)
  {
   const double stopLoss   = GetStopLossPrice(command);
   const double takeProfit = GetTakeProfitPrice(command);
   ManageOrderSend(command, Entry_Amount, stopLoss, takeProfit, 0);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ClosePosition(void)
  {
   const int command = posType == OP_BUY ? OP_SELL : OP_BUY;
   ManageOrderSend(command, posLots, 0, 0, posTicket);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ManageOrderSend(int command, double lots, double stopLoss, double takeProfit, ulong ticket)
  {
   for(int attempt = 0; attempt < TRADE_RETRY_COUNT; attempt++)
     {
      if(IsTradeContextFree())
        {
         MqlTradeRequest request;
         MqlTradeResult  result;
         ZeroMemory(request);
         ZeroMemory(result);

         request.action       = TRADE_ACTION_DEAL;
         request.symbol       = _Symbol;
         request.volume       = lots;
         request.type         = command == OP_BUY ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         request.price        = command == OP_BUY ? Ask() : Bid();
         request.type_filling = orderFillingType;
         request.deviation    = 10;
         request.sl           = stopLoss;
         request.tp           = takeProfit;
         request.magic        = Magic_Number;
         request.position     = ticket;
         request.comment      = IntegerToString(Magic_Number);

         bool isOrderCheck = CheckOrder(request);
         bool isOrderSend  = false;

         if(isOrderCheck)
           {
            ResetLastError();
            isOrderSend = OrderSend(request, result);
           }

         if(isOrderCheck && isOrderSend && result.retcode == TRADE_RETCODE_DONE)
            return;
        }

      Sleep(TRADE_RETRY_WAIT);
      Print("Order Send retry: " + IntegerToString(attempt + 2));
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ModifyPosition(double stopLoss, double takeProfit, ulong ticket)
  {
   for(int attempt = 0; attempt < TRADE_RETRY_COUNT; attempt++)
     {
      if(IsTradeContextFree())
        {
         MqlTradeRequest request;
         MqlTradeResult  result;
         ZeroMemory(request);
         ZeroMemory(result);

         request.action   = TRADE_ACTION_SLTP;
         request.symbol   = _Symbol;
         request.sl       = stopLoss;
         request.tp       = takeProfit;
         request.magic    = Magic_Number;
         request.position = ticket;
         request.comment  = IntegerToString(Magic_Number);

         bool isOrderCheck = CheckOrder(request);
         bool isOrderSend  = false;

         if(isOrderCheck)
           {
            ResetLastError();
            isOrderSend = OrderSend(request, result);
           }

         if(isOrderCheck && isOrderSend && result.retcode == TRADE_RETCODE_DONE)
            return;
        }

      Sleep(TRADE_RETRY_WAIT);
      Print("Order Send retry: " + IntegerToString(attempt + 2));
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool CheckOrder(MqlTradeRequest &request)
  {
   MqlTradeCheckResult check;
   ZeroMemory(check);
   ResetLastError();

   if(OrderCheck(request, check))
      return true;

   Print("Error with OrderCheck: " + check.comment);

   if(check.retcode == TRADE_RETCODE_INVALID_FILL)
     {
      switch (orderFillingType)
        {
         case ORDER_FILLING_FOK:
            Print("Filling mode changed to: ORDER_FILLING_IOC");
            orderFillingType = ORDER_FILLING_IOC;
            break;
         case ORDER_FILLING_IOC:
            Print("Filling mode changed to: ORDER_FILLING_RETURN");
            orderFillingType = ORDER_FILLING_RETURN;
            break;
         case ORDER_FILLING_RETURN:
            Print("Filling mode changed to: ORDER_FILLING_FOK");
            orderFillingType = ORDER_FILLING_FOK;
            break;
        }

      request.type_filling = orderFillingType;

      return CheckOrder(request);
     }

   return false;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double GetStopLossPrice(const int command)
  {
   if(Stop_Loss == 0)
      return 0;

   const double delta    = MathMax(pip * Stop_Loss, _Point * stopLevel);
   const double stopLoss = command == OP_BUY ? Bid() - delta : Ask() + delta;

   return NormalizeDouble(stopLoss, _Digits);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double GetTakeProfitPrice(const int command)
  {
   if(Take_Profit == 0) return 0;

   const double delta      = MathMax(pip * Take_Profit, _Point * stopLevel);
   const double takeProfit = command == OP_BUY ? Bid() + delta : Ask() - delta;

   return NormalizeDouble(takeProfit, _Digits);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double GetTrailingStopPrice(void)
  {
   const double bid = Bid();
   const double ask = Ask();
   const double spread = ask - bid;
   const double stopLevelPoints = _Point * stopLevel;
   const double stopLossPoints  = pip * Stop_Loss;

   if(posType == OP_BUY)
     {
      const double newStopLoss = High(1) - stopLossPoints;
      if(posStopLoss <= newStopLoss - pip)
         return newStopLoss < bid
                  ? newStopLoss >= bid - stopLevelPoints
                     ? bid - stopLevelPoints
                     : newStopLoss
                  : bid;
     }

   if(posType == OP_SELL)
     {
      const double newStopLoss = Low(1) + spread + stopLossPoints;
      if(posStopLoss >= newStopLoss + pip)
         return newStopLoss > ask
                  ? newStopLoss <= ask + stopLevelPoints
                     ? ask + stopLevelPoints
                     : newStopLoss
                  : ask;
     }

   return posStopLoss;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void ManageTrailingStop(const double trailingStop)
  {
   if((posType == OP_BUY  && MathAbs(trailingStop - Bid()) < _Point) ||
      (posType == OP_SELL && MathAbs(trailingStop - Ask()) < _Point))
     {
      ClosePosition();
      return;
     }

   if(MathAbs(trailingStop - posStopLoss) > _Point)
     {
      posStopLoss = NormalizeDouble(trailingStop, _Digits);
      ModifyPosition(posStopLoss, posTakeProfit, posTicket);
     }
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Bid(void)
  {
   return SymbolInfoDouble(_Symbol, SYMBOL_BID);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Ask(void)
  {
   return SymbolInfoDouble(_Symbol, SYMBOL_ASK);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
datetime Time(const int bar)
  {
   datetime buffer[];
   ArrayResize(buffer, 1);
   return CopyTime(_Symbol, _Period, bar, 1, buffer) == 1 ? buffer[0] : 0;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Open(const int bar)
  {
   double buffer[];
   ArrayResize(buffer, 1);
   return CopyOpen(_Symbol, _Period, bar, 1, buffer) == 1 ? buffer[0] : 0;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double High(const int bar)
  {
   double buffer[];
   ArrayResize(buffer, 1);
   return CopyHigh(_Symbol, _Period, bar, 1, buffer) == 1 ? buffer[0] : 0;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Low(const int bar)
  {
   double buffer[];
   ArrayResize(buffer, 1);
   return CopyLow(_Symbol, _Period, bar, 1, buffer) == 1 ? buffer[0] : 0;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Close(const int bar)
  {
   double buffer[];
   ArrayResize(buffer, 1);
   return CopyClose(_Symbol, _Period, bar, 1, buffer) == 1 ? buffer[0] : 0;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double GetPipValue(void)
  {
   return _Digits == 4 || _Digits == 5 ? 0.0001
        : _Digits == 2 || _Digits == 3 ? 0.01
                        : _Digits == 1 ? 0.1 : 1;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool IsTradeAllowed(void)
  {
   return (bool) MQLInfoInteger(MQL_TRADE_ALLOWED);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int DayOfWeek(void)
  {
   MqlDateTime mqlTime;
   TimeToStruct(Time(0), mqlTime);
   return mqlTime.day_of_week;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
bool IsTradeContextFree(void)
  {
   if(IsTradeAllowed())
      return true;

   const uint startWait = GetTickCount();
   Print("Trade context is busy! Waiting...");

   while(true)
     {
      if(IsStopped())
         return false;

      const uint diff = GetTickCount() - startWait;
      if(diff > 30 * 1000)
        {
         Print("The waiting limit exceeded!");
         return false;
        }

      if(IsTradeAllowed())
        {
         return true;
        }

      Sleep(TRADE_RETRY_WAIT);
     }

   return true;
  }
//+------------------------------------------------------------------+
/*STRATEGY MARKET MetaQuotes XAUUSD M5 */
/*STRATEGY CODE {"properties":{"entryLots":0.1,"tradeDirectionMode":0,"oppositeEntrySignal":0,"stopLoss":100,"takeProfit":100,"useStopLoss":false,"useTakeProfit":false,"isTrailingStop":false},"openFilters":[{"name":"Moving Average","listIndexes":[5,0,3,0,0],"numValues":[21,0,0,0,0,0]}],"closeFilters":[{"name":"Stochastic","listIndexes":[2,0,0,0,0],"numValues":[9,1,3,89,0,0]}]} */
