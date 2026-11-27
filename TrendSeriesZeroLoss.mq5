//+------------------------------------------------------------------+
//|                                                 TrendSeriesZeroLoss.mq5
//|  Zero-Loss Manager: Break-Even + Trailing with series controls
//|  Fixed: using CPositionInfo (no PositionGet*/PositionSelectByIndex())
//+------------------------------------------------------------------+
#property strict
#property description "Manages open positions to minimize loss via Break-Even and Trailing."
#property description "Includes daily loss limit, equity freeze option, and series close helpers."
#property version   "1.10"

// --- Includes (standard MQL5)
#include <Trade/Trade.mqh>
#include <Trade/PositionInfo.mqh>
#include <Trade/OrderInfo.mqh>
#include <Trade/DealInfo.mqh>
#include <Object.mqh>
#include <StdLibErr.mqh>
#include <ArrayObj.mqh>
#include <Array.mqh>

// --- Trade classes
CTrade         trade;
CPositionInfo  pos;
COrderInfo     ord;
CDealInfo      deal;

// ===================== Inputs ======================
input int      InpMagicNumber            = 12345;     // Magic Number (series id)
input bool     InpManageAllSymbols       = true;      // Manage all symbols (false -> only chart symbol)
input bool     InpAllowNewEntries        = false;     // (Optional) Enable basic entries (for demo)
input double   InpLots                   = 0.10;      // Default lot size for demo entries

// ---- Risk & Protection
input double   InpBreakEvenProfit        = 10.0;      // Move SL to entry when profit >= this (account currency)
input bool     InpUseTrailing            = true;      // Enable trailing
input double   InpTrailStart             = 15.0;      // Start trailing after profit >= this (currency)
input double   InpTrailStep              = 5.0;       // Trail step (currency)

// ---- Daily loss & equity freeze
input bool     InpUseDailyLossLimit      = true;      // Enforce daily realized PnL limit
input double   InpMaxDailyLoss           = -200.0;    // Stop managing/entries if daily PnL <= this
input bool     InpFreezeWhenLimitHit     = true;      // Freeze all positions (close or stop managing) when limit hit
input bool     InpCloseAllOnFreeze       = false;     // If freeze => close all series positions

// ---- Misc
input int      InpSlippagePoints         = 20;        // Slippage in points when closing
input int      InpMaxModifyRetries       = 3;         // Retries for modify/close
input int      InpManageIntervalMs       = 250;       // Throttle management loop (ms)

// ===================== Globals =====================
datetime       g_lastManageTick = 0;
bool           g_frozen         = false;

// ===================== Helpers =====================
string SymOf(const int i)
{
   if(pos.SelectByIndex(i)) return pos.Symbol();
   return _Symbol;
}

bool SameSeries(const int i)
{
   if(!pos.SelectByIndex(i)) return false;
   return (pos.Magic() == (long)InpMagicNumber) && (InpManageAllSymbols || pos.Symbol()==_Symbol);
}

int CountSeriesPositions()
{
   int cnt=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Magic()==(long)InpMagicNumber && (InpManageAllSymbols || pos.Symbol()==_Symbol))
         cnt++;
   }
   return cnt;
}

double SymbolPoint(const string sym)
{
   double pt; if(SymbolInfoDouble(sym,SYMBOL_POINT,pt)) return pt;
   return _Point;
}

int SymbolDigits(const string sym)
{
   int dg; if((int)SymbolInfoInteger(sym,SYMBOL_DIGITS,dg)) return dg;
   return _Digits;
}

double NormalizeToSymbol(const string sym, double price)
{
   return (double)NormalizeDouble(price, SymbolDigits(sym));
}

double MarketBid(const string sym){ double v; if(SymbolInfoDouble(sym,SYMBOL_BID,v)) return v; return 0.0; }
double MarketAsk(const string sym){ double v; if(SymbolInfoDouble(sym,SYMBOL_ASK,v)) return v; return 0.0; }

// --- Daily realized PnL (today, account currency)
bool TodayRange(datetime &from, datetime &to)
{
   MqlDateTime now; TimeToStruct(TimeCurrent(),now);
   now.hour=0; now.min=0; now.sec=0;
   from=StructToTime(now);
   to  =TimeCurrent();
   return true;
}

double DailyRealizedPnL()
{
   datetime from,to; TodayRange(from,to);
   if(!HistorySelect(from,to)) return 0.0;

   double pnl=0.0;
   int deals=HistoryDealsTotal();
   for(int i=0;i<deals;i++)
   {
      ulong ticket=HistoryDealGetTicket(i);
      if(!deal.Select(ticket)) continue;

      // Filter only series-related deals by magic (when available)
      long magic = (long)deal.Magic();
      if(magic!=(long)InpMagicNumber) continue;

      double profit   = deal.Profit();
      double swap     = deal.Swap();
      double commission = deal.Commission();
      pnl += (profit + swap + commission);
   }
   return pnl;
}

// --- Modify with retries
bool SafePositionModify(const string sym, double new_sl, double new_tp)
{
   new_sl = NormalizeToSymbol(sym,new_sl);
   new_tp = NormalizeToSymbol(sym,new_tp);

   for(int r=0; r<InpMaxModifyRetries; ++r)
   {
      if(trade.PositionModify(sym,new_sl,new_tp))
         return true;
      Sleep(50);
   }
   PrintFormat("Modify failed for %s: err=%d", sym, _LastError);
   return false;
}

// --- Close with retries
bool SafePositionClose(const string sym)
{
   for(int r=0; r<InpMaxModifyRetries; ++r)
   {
      if(trade.PositionClose(sym, InpSlippagePoints))
         return true;
      Sleep(50);
   }
   PrintFormat("Close failed for %s: err=%d", sym, _LastError);
   return false;
}

// ===================== Core Management =====================
// Apply Break-Even and Trailing to a single position (already pos.SelectByIndex(i))
void ApplyZeroLossLogic()
{
   const string sym = pos.Symbol();
   const long   type= pos.PositionType(); // POSITION_TYPE_BUY / SELL
   const double open= pos.PriceOpen();
   double currSL    = pos.SL();
   double currTP    = pos.TP();
   const double profitCCY = pos.Profit(); // account currency

   // ---- Break-Even
   if(InpBreakEvenProfit>0 && profitCCY >= InpBreakEvenProfit)
   {
      // Move SL to entry if it's not already at/above entry (for BUY) or at/below entry (for SELL)
      if(type==POSITION_TYPE_BUY && (currSL < open || currSL==0.0))
      {
         if(SafePositionModify(sym, open, currTP))
            PrintFormat("[BE] %s -> SL moved to entry (BUY) ticket=%I64u", sym, pos.Ticket());
      }
      else if(type==POSITION_TYPE_SELL && (currSL > open || currSL==0.0))
      {
         if(SafePositionModify(sym, open, currTP))
            PrintFormat("[BE] %s -> SL moved to entry (SELL) ticket=%I64u", sym, pos.Ticket());
      }
   }

   // ---- Trailing
   if(InpUseTrailing && InpTrailStart>0.0 && profitCCY >= InpTrailStart)
   {
      // Approximate: trail by account-currency profit step using points distance based on current price
      // For robustness across symbols, we trail in price terms by translating currency step to price step
      // Here: we trail by the last TrailingStep *in currency* as a proxy with simple percent-of-price.
      // Simpler alternative: ensure new SL follows price using fixed ATR/points; here we keep currency-based.
      double bid = MarketBid(sym), ask = MarketAsk(sym);
      if(bid==0 || ask==0) return;

      double newSL = currSL;
      if(type==POSITION_TYPE_BUY)
      {
         // ensure SL trails below bid by a step if profit advanced
         double stepPrice = (InpTrailStep>0? (InpTrailStep / MathMax(1.0, (ask+bid)/2.0))* (ask+bid)/2.0 : 0.0);
         if(stepPrice<=0.0) stepPrice = SymbolPoint(sym)*10.0; // fallback: 10 points
         double candidate = bid - stepPrice;
         if(candidate > currSL && candidate > open) // keep beyond BE
         {
            newSL = candidate;
            if(SafePositionModify(sym,newSL,currTP))
               PrintFormat("[TRAIL] %s BUY -> SL=%.5f (ticket=%I64u)", sym, newSL, pos.Ticket());
         }
      }
      else if(type==POSITION_TYPE_SELL)
      {
         double stepPrice = (InpTrailStep>0? (InpTrailStep / MathMax(1.0, (ask+bid)/2.0))* (ask+bid)/2.0 : 0.0);
         if(stepPrice<=0.0) stepPrice = SymbolPoint(sym)*10.0;
         double candidate = ask + stepPrice;
         if((currSL==0.0 || candidate < currSL) && candidate < open) // keep beyond BE
         {
            newSL = candidate;
            if(SafePositionModify(sym,newSL,currTP))
               PrintFormat("[TRAIL] %s SELL -> SL=%.5f (ticket=%I64u)", sym, newSL, pos.Ticket());
         }
      }
   }
}

// Manage all positions in the series (by InpMagicNumber and optional symbol scope)
void ManagePositionsSeries()
{
   // Equity freeze check
   if(InpUseDailyLossLimit)
   {
      double daily = DailyRealizedPnL();
      if(daily <= InpMaxDailyLoss)
      {
         if(!g_frozen)
         {
            g_frozen = true;
            PrintFormat("[FREEZE] Daily PnL=%.2f <= limit %.2f -> freeze=%s, closeAll=%s",
                        daily, InpMaxDailyLoss,
                        (string)(InpFreezeWhenLimitHit?"true":"false"),
                        (string)(InpCloseAllOnFreeze?"true":"false"));
            if(InpFreezeWhenLimitHit && InpCloseAllOnFreeze)
               CloseAllSeriesPositions();
         }
      }
      else
      {
         // auto unfreeze once above limit (fresh day usually)
         if(g_frozen)
         {
            PrintFormat("[UNFREEZE] Daily PnL=%.2f back above limit %.2f", daily, InpMaxDailyLoss);
            g_frozen=false;
         }
      }
   }

   if(g_frozen && InpFreezeWhenLimitHit)
      return; // stop managing further if frozen

   // Loop positions
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Magic()!=(long)InpMagicNumber) continue;
      if(!InpManageAllSymbols && pos.Symbol()!=_Symbol) continue;

      ApplyZeroLossLogic();
   }
}

// Close all positions in the series (respecting symbol scope)
void CloseAllSeriesPositions()
{
   bool any=false;
   for(int i=PositionsTotal()-1;i>=0;i--)
   {
      if(!pos.SelectByIndex(i)) continue;
      if(pos.Magic()!=(long)InpMagicNumber) continue;
      if(!InpManageAllSymbols && pos.Symbol()!=_Symbol) continue;

      const string sym = pos.Symbol();
      if(SafePositionClose(sym))
      {
         any=true;
         PrintFormat("[SERIES CLOSE] Closed %s (ticket=%I64u)", sym, pos.Ticket());
      }
      else
      {
         PrintFormat("[SERIES CLOSE] Failed to close %s (ticket=%I64u) err=%d", sym, pos.Ticket(), _LastError);
      }
   }
   if(!any) Print("[SERIES CLOSE] No matching positions.");
}

// ===================== (Optional) Entry Demo =====================
// Very simple demo entry (disabled by default) -> to verify manager behavior
void TryDemoEntry()
{
   if(!InpAllowNewEntries) return;
   if(CountSeriesPositions()>0) return; // only one at a time for demo

   string sym = _Symbol;
   double ask = MarketAsk(sym), bid=MarketBid(sym);
   if(ask==0 || bid==0) return;

   // naive trend filter: if last two closes ascending -> buy; descending -> sell
   MqlRates r[3];
   if(CopyRates(sym, PERIOD_M5, 0, 3, r)!=3) return;
   ArraySetAsSeries(r,true);

   bool up   = (r[0].close>r[1].close && r[1].close>r[2].close);
   bool down = (r[0].close<r[1].close && r[1].close<r[2].close);

   trade.SetExpertMagicNumber(InpMagicNumber);

   double pt = SymbolPoint(sym);
   double sl_buy = bid - 100*pt;
   double tp_buy = ask + 200*pt;
   double sl_sell= ask + 100*pt;
   double tp_sell= bid - 200*pt;

   if(up)
   {
      if(trade.Buy(InpLots, sym, ask, NormalizeToSymbol(sym,sl_buy), NormalizeToSymbol(sym,tp_buy)))
         Print("[ENTRY DEMO] BUY placed.");
   }
   else if(down)
   {
      if(trade.Sell(InpLots, sym, bid, NormalizeToSymbol(sym,sl_sell), NormalizeToSymbol(sym,tp_sell)))
         Print("[ENTRY DEMO] SELL placed.");
   }
}

// ===================== Standard Handlers =====================
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   Print("TrendSeriesZeroLoss initialized. Magic=", InpMagicNumber);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   Print("TrendSeriesZeroLoss deinitialized. reason=", reason);
}

void OnTick()
{
   static ulong last_call=0;
   ulong now=GetMicrosecondCount();
   if(now - last_call < (ulong)InpManageIntervalMs*1000ULL)
      return;
   last_call = now;

   // Optional demo entries (off by default)
   TryDemoEntry();

   // Core management
   ManagePositionsSeries();
}

// ===================== Utility Commands (optional hotkeys) ======
// You can call these from the MetaTrader "Call Function" dialog or convert to buttons as desired.
void Cmd_CloseAllSeries()
{
   CloseAllSeriesPositions();
}

int  Cmd_CountSeriesPositions()
{
   return CountSeriesPositions();
}

double Cmd_TodayPnL()
{
   return DailyRealizedPnL();
}
//+------------------------------------------------------------------+
