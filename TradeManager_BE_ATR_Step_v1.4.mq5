//+------------------------------------------------------------------+
//|              TradeManager_BE_ATR_Step_v1.4.mq5                    |
//|  BreakEven + Advanced Trailing (ATR + Step) + BoS/FVG entries    |
//|  Enhanced Step-Lock by TP progress + Trailing after 1st lock     |
//|  Added LTF confirmations, session filter and strategy registry    |
//|  © 2025                                                          |
//+------------------------------------------------------------------+
#property strict
#property version   "1.40"
#property description "Risk-Free + Hybrid Trailing; Optional BoS/FVG entries (no indicators) + Enhanced Lock/Trail + LTF/Session"
#include <Trade/Trade.mqh>

/*
   This expert advisor manages open positions and can optionally open trades
   based on simple price‑action patterns. It supports multiple layers of
   stop‑loss management including break even, ATR‑based trailing, legacy
   step‑locking and an enhanced lock/trailing system based on the percentage
   progress towards take profit. It also includes optional lower time frame
   bias filtering, session filters to restrict trading to certain hours, and
   a simple registry to allow adding additional entry strategies in order
   of priority without changing the core logic.
*/

CTrade Trade;

//====================== Inputs =====================================
// General
input long   InpMagicNumber           = 123456;    // Magic to manage (-1 = all)
input bool   ManageAllSymbols         = true;      // true: manage all; false: only current symbol

// Risk-Free (BE)
input bool   UseRiskFree              = true;      // Enable Risk-Free
input int    BE_Trigger_Points        = 300;       // Trigger to set BE (points)
input int    BE_Safety_OffsetPts      = 20;        // Extra offset beyond entry (points)
input bool   BE_By_CandleCount        = true;      // Use Candle-BE after N closes past entry
input int    BE_Candle_Count          = 1;         // #closes in profit direction before BE

// ATR Trailing (legacy hybrid)
input bool   Use_ATR_Trailing         = true;      // Enable ATR trailing
input ENUM_TIMEFRAMES ATR_TF          = PERIOD_H1; // ATR timeframe
input int    ATR_Period               = 14;        // ATR period
input double ATR_Multiplier           = 2.0;       // Chandelier distance = ATR*Mult

// Step-Lock Trailing (legacy)
input bool   Use_StepLock             = true;      // Enable Step-Lock trailing
input int    Step_Size_Points         = 200;       // Profit step size (points)
input int    Step_Lock_Percent        = 50;        // Lock % of running profit at each step (0..90)

// Safety & Broker Limits
input int    Min_SL_Distance_Points   = 50;        // Do not set SL closer than this to price
input bool   Respect_StopLevels       = true;      // Respect stops/freeze levels

// ===== Optional Entries (NO indicator for signals) =====
input bool   Allow_Entries_BoS        = true;      // Enable BoS entries (no indicator)
input bool   Allow_Entries_FVG        = true;      // Enable FVG entries (no indicator)
input ENUM_TIMEFRAMES ExecTF          = PERIOD_H1; // Execution TF for entries

// --- Trend/Bias (no-indicator) for HTF filtering
input bool   Use_HTF_Bias_NoInd       = true;      // Use candle-based bias on HTFs
input ENUM_TIMEFRAMES HTF1            = PERIOD_D1; // Higher TF 1
input ENUM_TIMEFRAMES HTF2            = PERIOD_H4; // Higher TF 2
input int    HTF_Bars_To_Check        = 20;        // Number of bars to evaluate bias
input double HTF_Bull_Threshold       = 0.55;      // >=55% bullish closes -> bullish bias
input double HTF_Bear_Threshold       = 0.55;      // >=55% bearish closes -> bearish bias

// --- Lower TF (LTF) confirmation
input bool   Use_LTF_Confirm          = false;      // Enable lower TF confirmation
input ENUM_TIMEFRAMES LTF1            = PERIOD_M30; // Lower TF 1
input ENUM_TIMEFRAMES LTF2            = PERIOD_M15; // Lower TF 2
input int    LTF_Bars_To_Check        = 20;         // Number of bars to evaluate bias on LTF
input double LTF_Bull_Threshold       = 0.55;       // >=55% bullish closes -> bullish bias
input double LTF_Bear_Threshold       = 0.55;       // >=55% bearish closes -> bearish bias

// --- Session filter (server time)
input bool   Use_Session_Filter       = false;      // Restrict trading to session hours
input int    Session_Start_Hour       = 8;          // Start hour (0-23) server time
input int    Session_End_Hour         = 17;         // End hour (0-23) server time

// --- BoS params
input int    SR_Lookback_Left         = 3;         // swing pivot left bars
input int    SR_Lookback_Right        = 3;         // swing pivot right bars
input int    BoS_MinBreak_Points      = 50;        // min break beyond swing (points)
input int    BoS_SL_Buffer_Points     = 80;        // SL buffer beyond opposite swing (points)
input int    BoS_TP_Default_Points    = 600;       // optional TP (0=none)
input double Risk_Per_Trade_Percent   = 0.5;       // Risk % per trade (for lot calc)

// --- FVG params (3-candle gap)
input int    FVG_Scan_Bars            = 120;       // scan window on ExecTF
input int    FVG_Min_Gap_Points       = 30;        // min gap size (points)
input int    FVG_SL_Buffer_Points     = 60;        // SL beyond gap bound
input int    FVG_TP_Default_Points    = 500;       // optional TP (0=none)

// --- NEW: Enhanced Step-Lock by TP progress + Trailing after first lock
input bool   Use_Enhanced_LockTrail     = true;    // enable new module
input double Step1_Progress_Percent     = 33.0;    // 1st lock at % of distance-to-TP
input double Step2_Progress_Percent     = 50.0;    // 2nd lock at % of distance-to-TP
input int    Step1_Lock_Points          = 10;      // Buy: Entry+10pt / Sell: Entry-10pt
input int    Step2_Lock_Points          = 30;      // Buy: Entry+30pt / Sell: Entry-30pt
input int    Trail_AfterLock_Points     = 20;      // trailing distance (points) after lock#1

// --- Strategy registry (placeholders for future strategies 3-10)
input bool   Use_Strategy3             = false;
input bool   Use_Strategy4             = false;
input bool   Use_Strategy5             = false;
input bool   Use_Strategy6             = false;
input bool   Use_Strategy7             = false;
input bool   Use_Strategy8             = false;
input bool   Use_Strategy9             = false;
input bool   Use_Strategy10            = false;

// Logging
input bool   VerboseLogs              = true;

//====================== Utilities ==================================
double GetPoint(const string sym){ return(SymbolInfoDouble(sym,SYMBOL_POINT)); }

bool GetStopsLevels(const string sym,long &stopLevel,long &freezeLevel)
{
   bool ok1 = SymbolInfoInteger(sym,SYMBOL_TRADE_STOPS_LEVEL,stopLevel);
   bool ok2 = SymbolInfoInteger(sym,SYMBOL_TRADE_FREEZE_LEVEL,freezeLevel);
   return(ok1 && ok2);
}

double iATR_val(const string sym,ENUM_TIMEFRAMES tf,int period,int shift=0)
{
   int handle = iATR(sym,tf,period);
   if(handle==INVALID_HANDLE) return(0.0);
   double buffer[];
   if(CopyBuffer(handle,0,shift,2,buffer)!=2){ IndicatorRelease(handle); return(0.0); }
   double v = buffer[0];
   IndicatorRelease(handle);
   return(v);
}

//====================== HTF Bias (No Indicator) =====================
int CountBullBear(const string sym,ENUM_TIMEFRAMES tf,int bars,double &bullRatio,double &bearRatio)
{
   MqlRates r[];
   int got = CopyRates(sym,tf,0,bars,r);
   if(got<5){ bullRatio=0; bearRatio=0; return 0; }
   int bull=0,bear=0;
   for(int i=1;i<got;i++){
      if(r[i].close>r[i].open) bull++;
      else if(r[i].close<r[i].open) bear++;
   }
   bullRatio = (double)bull/(double)(got-1);
   bearRatio = (double)bear/(double)(got-1);
   return got;
}

bool HTF_Bias_Long(const string sym)
{
   if(!Use_HTF_Bias_NoInd) return true; // no filter
   double b1,b2,br1,br2;
   CountBullBear(sym,HTF1,HTF_Bars_To_Check,b1,br1);
   CountBullBear(sym,HTF2,HTF_Bars_To_Check,b2,br2);
   bool long1 = (b1>=HTF_Bull_Threshold);
   bool long2 = (b2>=HTF_Bull_Threshold);
   return(long1 && long2);
}

bool HTF_Bias_Short(const string sym)
{
   if(!Use_HTF_Bias_NoInd) return true; // no filter
   double b1,b2,br1,br2;
   CountBullBear(sym,HTF1,HTF_Bars_To_Check,b1,br1);
   CountBullBear(sym,HTF2,HTF_Bars_To_Check,b2,br2);
   bool sh1 = (br1>=HTF_Bear_Threshold);
   bool sh2 = (br2>=HTF_Bear_Threshold);
   return(sh1 && sh2);
}

//====================== LTF Bias (No Indicator) =====================
bool LTF_Bias_Long(const string sym)
{
   if(!Use_LTF_Confirm) return true;
   double b1,b2,br1,br2;
   CountBullBear(sym,LTF1,LTF_Bars_To_Check,b1,br1);
   CountBullBear(sym,LTF2,LTF_Bars_To_Check,b2,br2);
   bool long1 = (b1>=LTF_Bull_Threshold);
   bool long2 = (b2>=LTF_Bull_Threshold);
   return(long1 && long2);
}

bool LTF_Bias_Short(const string sym)
{
   if(!Use_LTF_Confirm) return true;
   double b1,b2,br1,br2;
   CountBullBear(sym,LTF1,LTF_Bars_To_Check,b1,br1);
   CountBullBear(sym,LTF2,LTF_Bars_To_Check,b2,br2);
   bool sh1 = (br1>=LTF_Bear_Threshold);
   bool sh2 = (br2>=LTF_Bear_Threshold);
   return(sh1 && sh2);
}

//====================== Session Filter ==============================
// Returns true if current server hour is within session (handles wrap around)
bool IsWithinSession()
{
   if(!Use_Session_Filter) return true;
   datetime t = TimeCurrent();
   MqlDateTime dt;
   TimeToStruct(t,dt);
   int curHour = dt.hour;
   if(Session_Start_Hour==Session_End_Hour) return true; // full day
   if(Session_Start_Hour < Session_End_Hour)
   {
      return(curHour >= Session_Start_Hour && curHour < Session_End_Hour);
   }
   else // wrap around (e.g. 22 to 4)
   {
      return(curHour >= Session_Start_Hour || curHour < Session_End_Hour);
   }
}

//====================== Core: Proposals =============================
bool Propose_RiskFree_SL(const string sym,const long type,double entry,double &sl_out)
{
   if(!UseRiskFree) return(false);
   double pt = GetPoint(sym);
   double spread = (SymbolInfoDouble(sym,SYMBOL_ASK)-SymbolInfoDouble(sym,SYMBOL_BID));
   double off = BE_Safety_OffsetPts*pt;
   if(type==POSITION_TYPE_BUY)  sl_out = entry + spread/2.0 + off;
   else                         sl_out = entry - spread/2.0 - off;
   return(true);
}

bool Propose_ATR_Trail(const string sym,const long type,double &sl_out)
{
   if(!Use_ATR_Trailing) return(false);
   double atr = iATR_val(sym,ATR_TF,ATR_Period);
   if(atr<=0) return(false);
   double dist = atr * ATR_Multiplier;
   double price_bid = SymbolInfoDouble(sym,SYMBOL_BID);
   double price_ask = SymbolInfoDouble(sym,SYMBOL_ASK);
   if(type==POSITION_TYPE_BUY)  sl_out = price_bid - dist;
   else                         sl_out = price_ask + dist;
   return(true);
}

bool Propose_StepLock(const string sym,const long type,double entry,double &sl_out)
{
   if(!Use_StepLock || Step_Size_Points<=0) return(false);
   double pt   = GetPoint(sym);
   double bid  = SymbolInfoDouble(sym,SYMBOL_BID);
   double ask  = SymbolInfoDouble(sym,SYMBOL_ASK);
   double runProfitPts = (type==POSITION_TYPE_BUY)? (bid-entry)/pt : (entry-ask)/pt;
   if(runProfitPts < Step_Size_Points) return(false);
   int steps = (int)MathFloor(runProfitPts / Step_Size_Points);
   double lockPct = (double)MathMin(MathMax(Step_Lock_Percent,0),90)/100.0;
   double lockedPts = (double)steps * Step_Size_Points * lockPct;
   if(type==POSITION_TYPE_BUY)  sl_out = entry + lockedPts*pt;
   else                         sl_out = entry - lockedPts*pt;
   return(true);
}

bool CandleBE_Triggered(const string sym,const long type,double entry)
{
   if(!UseRiskFree || !BE_By_CandleCount || BE_Candle_Count<=0) return(false);
   MqlRates rates[];
   if(CopyRates(sym,ExecTF,0,BE_Candle_Count+1,rates) < BE_Candle_Count+1) return(false);
   int count=0;
   for(int i=1;i<=BE_Candle_Count;i++)
   {
      double cls = rates[i].close;
      if(type==POSITION_TYPE_BUY  && cls>entry) count++;
      if(type==POSITION_TYPE_SELL && cls<entry) count++;
   }
   return(count==BE_Candle_Count);
}

//====================== Manage Single Position ======================
bool WithinBrokerLimits(const string sym,double price,double sl,long type,double &adjSL)
{
   long stopLevel=0,freezeLevel=0;
   double pt = GetPoint(sym);
   double ptMin = (double)Min_SL_Distance_Points;
   if(Respect_StopLevels && GetStopsLevels(sym,stopLevel,freezeLevel))
      ptMin = MathMax(ptMin,(double)stopLevel);
   adjSL = sl;
   if(type==POSITION_TYPE_BUY){
      if( (SymbolInfoDouble(sym,SYMBOL_BID)-adjSL)/pt < ptMin )
         adjSL = SymbolInfoDouble(sym,SYMBOL_BID) - ptMin*pt;
   }else{
      if( (adjSL - SymbolInfoDouble(sym,SYMBOL_ASK))/pt < ptMin )
         adjSL = SymbolInfoDouble(sym,SYMBOL_ASK) + ptMin*pt;
   }
   adjSL = NormalizeDouble(adjSL,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS));
   return(true);
}

bool ManagePosition(ulong ticket)
{
   if(!PositionSelectByTicket(ticket)) return(false);
   string sym   = PositionGetString(POSITION_SYMBOL);
   long   type  = PositionGetInteger(POSITION_TYPE);
   long   mgc   = PositionGetInteger(POSITION_MAGIC);
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl    = PositionGetDouble(POSITION_SL);
   double tp    = PositionGetDouble(POSITION_TP);
   if(!ManageAllSymbols && sym!=_Symbol) return(false);
   if(InpMagicNumber!=-1 && mgc!=InpMagicNumber) return(false);
   double pt    = GetPoint(sym);
   double bid   = SymbolInfoDouble(sym,SYMBOL_BID);
   double ask   = SymbolInfoDouble(sym,SYMBOL_ASK);
   // Profit in points
   double runPts = (type==POSITION_TYPE_BUY)? (bid-entry)/pt : (entry-ask)/pt;
   // --- BE trigger
   bool beReady = (UseRiskFree && runPts >= BE_Trigger_Points) || CandleBE_Triggered(sym,type,entry);
   double sl_BE, sl_ATR, sl_Step;
   bool have_BE   = (beReady) ? Propose_RiskFree_SL(sym,type,entry,sl_BE) : false;
   bool have_ATR  = Propose_ATR_Trail(sym,type,sl_ATR);
   bool have_Step = Propose_StepLock(sym,type,entry,sl_Step);
   // choose the TIGHTEST (closest to price on profit side)
   double newSL = 0.0;
   bool   any   = false;
   if(have_BE)   { newSL = sl_BE;  any=true; }
   if(have_ATR)  {
      if(!any) { newSL=sl_ATR; any=true; }
      else     { if(type==POSITION_TYPE_BUY) newSL=MathMax(newSL,sl_ATR); else newSL=MathMin(newSL,sl_ATR); }
   }
   if(have_Step) {
      if(!any) { newSL=sl_Step; any=true; }
      else     { if(type==POSITION_TYPE_BUY) newSL=MathMax(newSL,sl_Step); else newSL=MathMin(newSL,sl_Step); }
   }
   if(!any) return(false);
   // never loosen
   if(sl>0){
      if(type==POSITION_TYPE_BUY && newSL<=sl) return(false);
      if(type==POSITION_TYPE_SELL&& newSL>=sl) return(false);
   }
   // Broker constraints + sanity
   double adjSL=0.0;
   WithinBrokerLimits(sym,(type==POSITION_TYPE_BUY?bid:ask),newSL,type,adjSL);
   if(type==POSITION_TYPE_BUY && adjSL > bid) adjSL = bid - Min_SL_Distance_Points*pt;
   if(type==POSITION_TYPE_SELL&& adjSL < ask) adjSL = ask + Min_SL_Distance_Points*pt;
   adjSL = NormalizeDouble(adjSL,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS));
   Trade.SetAsyncMode(false);
   bool ok = Trade.PositionModify(ticket,adjSL,tp);
   if(!ok && VerboseLogs)
      PrintFormat("Modify failed ticket=%I64u err=%d newSL=%.5f",ticket,_LastError,adjSL);
   else if(VerboseLogs)
      PrintFormat("SL moved ticket=%I64u -> %.5f (BE:%s ATR:%s STEP:%s RunPts=%.1f)",
                  ticket,adjSL, have_BE?"Y":"n", have_ATR?"Y":"n", have_Step?"Y":"n", runPts);
   return(ok);
}

//====================== Lots by Risk ================================
double LotByRisk(const string sym,double sl_pts,double risk_percent)
{
   if(sl_pts<=0) return(0.0);
   double balance = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
   double risk    = balance * risk_percent/100.0;
   double tickval = SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_VALUE);
   double ticksize= SymbolInfoDouble(sym,SYMBOL_TRADE_TICK_SIZE);
   double pt      = GetPoint(sym);
   double ticks   = (sl_pts*pt)/ticksize;
   if(ticks<=0 || tickval<=0) return(0.0);
   double lots    = risk/(ticks*tickval);
   double minLot  = SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(sym,SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(sym,SYMBOL_VOLUME_STEP);
   lots = MathFloor(MathMax(minLot,MathMin(maxLot,lots))/stepLot)*stepLot;
   return(lots);
}

//====================== BoS (No Indicator) ==========================
struct SwingPoint { double price; int index; };
bool FindLastSwings(const string sym,ENUM_TIMEFRAMES tf,int left,int right, SwingPoint &lastHigh, SwingPoint &lastLow)
{
   MqlRates r[]; int need = 300;
   int got = CopyRates(sym,tf,0,need,r);
   if(got < left+right+5) return(false);
   lastHigh.index = -1; lastLow.index = -1;
   for(int i=right; i<got-left; i++)
   {
      bool isHigh=true,isLow=true;
      for(int k=1;k<=left;k++){ if(r[i].high<=r[i-k].high) isHigh=false; if(r[i].low>=r[i-k].low) isLow=false; }
      for(int k=1;k<=right;k++){ if(r[i].high<=r[i+k].high) isHigh=false; if(r[i].low>=r[i+k].low) isLow=false; }
      if(isHigh){ lastHigh.price=r[i].high; lastHigh.index=i; }
      if(isLow ){ lastLow.price =r[i].low ; lastLow.index =i; }
   }
   return(lastHigh.index!=-1 && lastLow.index!=-1);
}

bool TryEntry_BoS()
{
   if(!Allow_Entries_BoS) return(false);
   if(!IsWithinSession()) return(false);
   string sym=_Symbol; double pt=GetPoint(sym);
   // avoid duplicates per symbol/magic
   for(int i=0;i<PositionsTotal();i++){
      if(PositionSelectByTicket(PositionGetTicket(i))){
         if(PositionGetString(POSITION_SYMBOL)==sym){
            long mg=PositionGetInteger(POSITION_MAGIC);
            if(InpMagicNumber==-1 || mg==InpMagicNumber) return(false);
         }
      }
   }
   SwingPoint sh,sl;
   if(!FindLastSwings(sym,ExecTF,SR_Lookback_Left,SR_Lookback_Right,sh,sl)) return(false);
   MqlRates r[]; if(CopyRates(sym,ExecTF,0,5,r)<3) return(false);
   double lastClose = r[1].close;
   bool longBias  = HTF_Bias_Long(sym)  && LTF_Bias_Long(sym);
   bool shortBias = HTF_Bias_Short(sym) && LTF_Bias_Short(sym);
   bool brokeHigh = (lastClose > sh.price + BoS_MinBreak_Points*pt);
   bool brokeLow  = (lastClose < sl.price - BoS_MinBreak_Points*pt);
   Trade.SetExpertMagicNumber(InpMagicNumber);
   Trade.SetAsyncMode(false);
   if(brokeHigh && longBias)
   {
      double ask = SymbolInfoDouble(sym,SYMBOL_ASK);
      double slp = sl.price - BoS_SL_Buffer_Points*pt;
      double lots= LotByRisk(sym, (ask-slp)/pt, Risk_Per_Trade_Percent);
      double tp  = (BoS_TP_Default_Points>0)? ask + BoS_TP_Default_Points*pt : 0.0;
      if(lots>0) return Trade.Buy(lots,sym,ask,slp,tp,"BoS");
   }
   if(brokeLow && shortBias)
   {
      double bid = SymbolInfoDouble(sym,SYMBOL_BID);
      double slp = sl.price + BoS_SL_Buffer_Points*pt;
      double lots= LotByRisk(sym, (slp-bid)/pt, Risk_Per_Trade_Percent);
      double tp  = (BoS_TP_Default_Points>0)? bid - BoS_TP_Default_Points*pt : 0.0;
      if(lots>0) return Trade.Sell(lots,sym,bid,slp,tp,"BoS");
   }
   return(false);
}

//====================== FVG (No Indicator) ==========================
struct FVGGap { bool bullish; double lowBound; double highBound; int index; };
bool FindRecentFVG(const string sym,ENUM_TIMEFRAMES tf,int scanBars,int minGapPts,FVGGap &out)
{
   out.index=-1; out.bullish=false; out.lowBound=0; out.highBound=0;
   MqlRates r[]; int got = CopyRates(sym,tf,0,scanBars,r);
   if(got<5) return false;
   double pt = GetPoint(sym);
   for(int i=2;i<got;i++)
   {
      double Ahi=r[i].high, Alo=r[i].low;
      double Bhi=r[i-1].high, Blo=r[i-1].low;
      double Chi=r[i-2].high, Clo=r[i-2].low;
      if(Blo > Chi && ( (Blo - Chi)/pt >= minGapPts ))
      {
         out.bullish = true;
         out.lowBound = Chi;
         out.highBound= Blo;
         out.index = i-1;
         return true;
      }
      if(Bhi < Clo && ( (Clo - Bhi)/pt >= minGapPts ))
      {
         out.bullish = false;
         out.lowBound = Bhi;
         out.highBound= Clo;
         out.index = i-1;
         return true;
      }
   }
   return false;
}

bool TryEntry_FVG()
{
   if(!Allow_Entries_FVG) return(false);
   if(!IsWithinSession()) return(false);
   string sym=_Symbol; double pt=GetPoint(sym);
   // avoid duplicates per symbol/magic
   for(int i=0;i<PositionsTotal();i++){
      if(PositionSelectByTicket(PositionGetTicket(i))){
         if(PositionGetString(POSITION_SYMBOL)==sym){
            long mg=PositionGetInteger(POSITION_MAGIC);
            if(InpMagicNumber==-1 || mg==InpMagicNumber) return(false);
         }
      }
   }
   FVGGap g;
   if(!FindRecentFVG(sym,ExecTF,FVG_Scan_Bars,FVG_Min_Gap_Points,g)) return(false);
   double bid=SymbolInfoDouble(sym,SYMBOL_BID);
   double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
   bool longBias  = HTF_Bias_Long(sym)  && LTF_Bias_Long(sym);
   bool shortBias = HTF_Bias_Short(sym) && LTF_Bias_Short(sym);
   // Entry only when price revisits the gap
   bool inGap = ( (g.bullish && bid>=g.lowBound && bid<=g.highBound) ||
                  (!g.bullish && ask>=g.lowBound && ask<=g.highBound) );
   if(!inGap) return(false);
   Trade.SetExpertMagicNumber(InpMagicNumber);
   Trade.SetAsyncMode(false);
   if(g.bullish && longBias)
   {
      double sl = g.lowBound - FVG_SL_Buffer_Points*pt;
      double lots = LotByRisk(sym,(ask-sl)/pt,Risk_Per_Trade_Percent);
      double tp = (FVG_TP_Default_Points>0)? ask + FVG_TP_Default_Points*pt : 0.0;
      if(lots>0) return Trade.Buy(lots,sym,ask,sl,tp,"FVG");
   }
   if(!g.bullish && shortBias)
   {
      double sl = g.highBound + FVG_SL_Buffer_Points*pt;
      double lots = LotByRisk(sym,(sl-bid)/pt,Risk_Per_Trade_Percent);
      double tp = (FVG_TP_Default_Points>0)? bid - FVG_TP_Default_Points*pt : 0.0;
      if(lots>0) return Trade.Sell(lots,sym,bid,sl,tp,"FVG");
   }
   return(false);
}

//====================== Additional Strategies (placeholders) =======
bool TryEntry_Strategy3(){ return(false); }
bool TryEntry_Strategy4(){ return(false); }
bool TryEntry_Strategy5(){ return(false); }
bool TryEntry_Strategy6(){ return(false); }
bool TryEntry_Strategy7(){ return(false); }
bool TryEntry_Strategy8(){ return(false); }
bool TryEntry_Strategy9(){ return(false); }
bool TryEntry_Strategy10(){ return(false); }

//====================== Entry Orchestrator ==========================
// Calls entry strategies in priority order. Returns if any executed.
void TryEntriesOrchestrator()
{
   // BoS has highest priority
   if(TryEntry_BoS()) return;
   // then FVG
   if(TryEntry_FVG()) return;
   // Strategy 3..10 placeholders
   if(Use_Strategy3 && TryEntry_Strategy3()) return;
   if(Use_Strategy4 && TryEntry_Strategy4()) return;
   if(Use_Strategy5 && TryEntry_Strategy5()) return;
   if(Use_Strategy6 && TryEntry_Strategy6()) return;
   if(Use_Strategy7 && TryEntry_Strategy7()) return;
   if(Use_Strategy8 && TryEntry_Strategy8()) return;
   if(Use_Strategy9 && TryEntry_Strategy9()) return;
   if(Use_Strategy10 && TryEntry_Strategy10()) return;
}

//====================== NEW: Enhanced Lock & Trailing ===============
double ProgressToTPPercent(const string sym, const long type, const double entry, const double tp_price)
{
   if(tp_price<=0.0) return(-1.0);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   double cur = (type==POSITION_TYPE_BUY ? bid : ask);
   double num=0.0, den=0.0;
   if(type==POSITION_TYPE_BUY){ den = (tp_price - entry); num = (cur - entry); }
   else                       { den = (entry - tp_price); num = (entry - cur); }
   if(den<=0.0) return(-1.0);
   return(100.0 * (num/den));
}

// clamp SL respecting broker stop levels
double ClampSLToBroker(const string sym, const long type, const double propose)
{
   double pt  = SymbolInfoDouble(sym, SYMBOL_POINT);
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   long stopLevel=0, freezeLevel=0;
   double minPts = (double)Min_SL_Distance_Points;
   if(Respect_StopLevels && GetStopsLevels(sym,stopLevel,freezeLevel))
      minPts = MathMax(minPts,(double)stopLevel);
   double result = propose;
   if(type==POSITION_TYPE_BUY)
   {
      double maxSL = bid - minPts*pt;
      if(result > maxSL) result = maxSL;
   }
   else
   {
      double minSL = ask + minPts*pt;
      if(result < minSL) result = minSL;
   }
   return NormalizeDouble(result,(int)SymbolInfoInteger(sym,SYMBOL_DIGITS));
}

bool ApplyEnhancedLockTrail(ulong ticket)
{
   if(!Use_Enhanced_LockTrail) return(false);
   if(!PositionSelectByTicket(ticket)) return(false);
   string sym   = PositionGetString(POSITION_SYMBOL);
   long   type  = PositionGetInteger(POSITION_TYPE);
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl    = PositionGetDouble(POSITION_SL);
   double tp    = PositionGetDouble(POSITION_TP);
   // نیاز به TP برای محاسبه درصد مسیر
   double prog = ProgressToTPPercent(sym,type,entry,tp);
   if(prog<0.0) return(false);
   double pt = GetPoint(sym);
   double bid=SymbolInfoDouble(sym,SYMBOL_BID);
   double ask=SymbolInfoDouble(sym,SYMBOL_ASK);
   // تشخیص وضعیت قفل‌ها بر اساس جایگاه SL نسبت به Entry (بدون state جدا)
   bool firstLocked=false, secondLocked=false;
   if(type==POSITION_TYPE_BUY){
      if(sl >= entry + Step1_Lock_Points*pt - 2*pt) firstLocked=true;
      if(sl >= entry + Step2_Lock_Points*pt - 2*pt) { firstLocked=true; secondLocked=true; }
   }else{
      if(sl <= entry - Step1_Lock_Points*pt + 2*pt) firstLocked=true;
      if(sl <= entry - Step2_Lock_Points*pt + 2*pt) { firstLocked=true; secondLocked=true; }
   }
   bool modified=false;
   // --- Lock #1
   if(prog >= Step1_Progress_Percent && !firstLocked)
   {
      double newSL = (type==POSITION_TYPE_BUY) ? (entry + Step1_Lock_Points*pt)
                                               : (entry - Step1_Lock_Points*pt);
      newSL = ClampSLToBroker(sym,type,newSL);
      if( (type==POSITION_TYPE_BUY && (sl<=0 || newSL>sl)) ||
          (type==POSITION_TYPE_SELL&& (sl<=0 || newSL<sl)) )
      {
         if(Trade.PositionModify(ticket,newSL,tp)){
            sl=newSL; firstLocked=true; modified=true;
            if(VerboseLogs) PrintFormat("Enhanced Lock#1 (%.1f%%) ticket=%I64u SL=%.5f",
                                        Step1_Progress_Percent,ticket,newSL);
         }
      }
   }
   // --- Lock #2
   if(prog >= Step2_Progress_Percent && firstLocked && !secondLocked)
   {
      double newSL = (type==POSITION_TYPE_BUY) ? (entry + Step2_Lock_Points*pt)
                                               : (entry - Step2_Lock_Points*pt);
      newSL = ClampSLToBroker(sym,type,newSL);
      if( (type==POSITION_TYPE_BUY && newSL>sl) ||
          (type==POSITION_TYPE_SELL&& newSL<sl) )
      {
         if(Trade.PositionModify(ticket,newSL,tp)){
            sl=newSL; secondLocked=true; modified=true;
            if(VerboseLogs) PrintFormat("Enhanced Lock#2 (%.1f%%) ticket=%I64u SL=%.5f",
                                        Step2_Progress_Percent,ticket,newSL);
         }
      }
   }
   // --- Trailing only after Lock#1
   if(firstLocked)
   {
      double refPrice = (type==POSITION_TYPE_BUY)? bid : ask;
      double trailSL  = (type==POSITION_TYPE_BUY)? (refPrice - Trail_AfterLock_Points*pt)
                                                 : (refPrice + Trail_AfterLock_Points*pt);
      trailSL = ClampSLToBroker(sym,type,trailSL);
      if( (type==POSITION_TYPE_BUY && trailSL>sl) ||
          (type==POSITION_TYPE_SELL&& trailSL<sl) )
      {
         if(Trade.PositionModify(ticket,trailSL,tp)){
            sl=trailSL; modified=true;
            if(VerboseLogs) PrintFormat("Enhanced Trailing moved: ticket=%I64u SL=%.5f",
                                        ticket,trailSL);
         }
      }
   }
   return(modified);
}

//====================== Standard Events =============================
int OnInit()
{
   Print("TradeManager_BE_ATR_Step v1.4 initialized.");
   return(INIT_SUCCEEDED);
}

void OnTick()
{
   // Manage & Enhanced Lock/Trail
   for(int i=0;i<PositionsTotal();i++)
   {
      ulong tkt = PositionGetTicket(i);
      ManagePosition(tkt);          // legacy manager (BE/ATR/Legacy StepLock)
      ApplyEnhancedLockTrail(tkt);  // NEW: %TP locks + trailing after first lock
   }
   // Entry orchestrator
   TryEntriesOrchestrator();
}

void OnDeinit(const int reason)
{
   Print("TradeManager_BE_ATR_Step deinitialized.");
}