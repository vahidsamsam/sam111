//+------------------------------------------------------------------+
//|     TradeManager_RiskFree_ATRStep_NoIndicator_v1c.mq5            |
//|     Non-entry Trade Manager: BE + StepTrail + TimeStop            |
//|     Optional ATR trail (disabled by default)                      |
//+------------------------------------------------------------------+
#property strict
#property version   "1.02"

//----- Inputs
input bool   InpEnableManager        = true;      // Enable manager
input long   InpMagicFilter          = -1;        // -1: manage all, else only this Magic
input bool   InpCurrentSymbolOnly    = true;      // Manage only current chart symbol
input bool   InpApplyOnBarClose      = true;      // Apply on bar close (reduces noise)
input int    InpTimerSeconds         = 30;        // Timer frequency

// R-based management
input double InpBE_Arm_R             = 0.5;       // Arm Break-Even at R
input double InpBE_Buffer_Points     = 0;         // Extra BE buffer points (0=auto by spread)
input double InpStep1_R              = 1.0;       // Step-1 threshold (R)
input double InpStep1_LockR          = 0.3;       // Lock at Step-1
input double InpStep2_R              = 1.5;       // Step-2 threshold (R)
input double InpStep2_LockR          = 0.6;       // Lock at Step-2
input double InpStep3_R              = 2.0;       // Step-3 threshold (R)
input double InpStep3_LockR          = 1.0;       // Lock at Step-3

// Time-stop
input int    InpMaxHoldBars          = 8;         // Close weak trades after N bars if R<0.3
input double InpWeakRThreshold       = 0.3;       // Weak trade threshold (R)

// Optional ATR trail (disabled by default)
input bool   InpUseATRTrail          = false;     // Use dynamic ATR trailing
input int    InpATR_Period           = 14;        // ATR period
input double InpATR_k                = 1.5;       // ATR multiple
input ENUM_TIMEFRAMES InpATR_TF      = PERIOD_H1; // ATR timeframe

//------------------- Globals --------------------------------------
int       g_hATR = INVALID_HANDLE;
datetime  g_lastBarTime = 0;

//------------------- Utils ----------------------------------------
double GetATR(){
   if(!InpUseATRTrail) return 0.0;
   if(g_hATR==INVALID_HANDLE){
      g_hATR = iATR(_Symbol, InpATR_TF, InpATR_Period);
   }
   if(g_hATR==INVALID_HANDLE) return 0.0;
   double buf[]; ArraySetAsSeries(buf,true);
   if(CopyBuffer(g_hATR,0,1,1,buf)<=0) return 0.0;
   return buf[0];
}

bool BarJustClosed(){
   if(!InpApplyOnBarClose) return true;
   datetime bt = iTime(_Symbol, PERIOD_H1, 0);
   if(bt!=g_lastBarTime){
      g_lastBarTime = bt;
      return true;
   }
   return false;
}

double CurrentR(ENUM_POSITION_TYPE dir, double entry, double sl, double price){
   double risk = (dir==POSITION_TYPE_BUY) ? (entry - sl) : (sl - entry);
   double run  = (dir==POSITION_TYPE_BUY) ? (price - entry) : (entry - price);
   if(risk<=0.0) return 0.0;
   return run / risk;
}

double LockR(double entry, double riskPts, double lockR, ENUM_POSITION_TYPE dir){
   double lockPts = lockR * riskPts;
   return (dir==POSITION_TYPE_BUY) ? entry + lockPts : entry - lockPts;
}

double ATRTrailSL(ENUM_POSITION_TYPE dir, double price, double atr, double k){
   return (dir==POSITION_TYPE_BUY) ? price - atr*k : price + atr*k;
}

//------------------- Core: manage selected position ----------------
void ManageSelected(){
   string sym = PositionGetString(POSITION_SYMBOL);
   if(InpCurrentSymbolOnly && sym!=_Symbol) return;
   long magic = PositionGetInteger(POSITION_MAGIC);
   if(InpMagicFilter!=-1 && magic!=InpMagicFilter) return;

   ENUM_POSITION_TYPE dir = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   double entry = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl    = PositionGetDouble(POSITION_SL);
   double tp    = PositionGetDouble(POSITION_TP);

   double price = (dir==POSITION_TYPE_BUY) ? SymbolInfoDouble(sym, SYMBOL_BID)
                                           : SymbolInfoDouble(sym, SYMBOL_ASK);
   datetime opent = (datetime)PositionGetInteger(POSITION_TIME);
   int barsHeld = (int)MathFloor( (TimeCurrent()-opent)/PeriodSeconds(PERIOD_H1) );

   if(entry<=0 || sl<=0) return;
   if(InpApplyOnBarClose && !BarJustClosed()) return;

   double riskPts = MathAbs(entry - sl);
   double rNow    = CurrentR(dir, entry, sl, price);

   // ---- Time-stop for weak trades ----
   if(barsHeld >= InpMaxHoldBars && rNow < InpWeakRThreshold){
      MqlTradeRequest req; MqlTradeResult res; ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_SLTP; req.symbol = sym;
      req.sl = (dir==POSITION_TYPE_BUY) ? (price - _Point*3) : (price + _Point*3);
      req.tp = tp;
      if(!OrderSend(req,res)) Print("TimeStop SLTP failed: ",res.retcode);
      return;
   }

   // ---- Break-even ----
   if(rNow >= InpBE_Arm_R){
      double spreadPts = SymbolInfoInteger(sym, SYMBOL_SPREAD)*_Point;
      double buf = (InpBE_Buffer_Points>0 ? InpBE_Buffer_Points*_Point : spreadPts);
      double be  = (dir==POSITION_TYPE_BUY) ? (entry + buf) : (entry - buf);
      if( (dir==POSITION_TYPE_BUY && be>sl) || (dir==POSITION_TYPE_SELL && be<sl) ){
         MqlTradeRequest req; MqlTradeResult res; ZeroMemory(req); ZeroMemory(res);
         req.action = TRADE_ACTION_SLTP; req.symbol = sym;
         req.sl = be; req.tp = tp;
         if(!OrderSend(req,res)) Print("BE SLTP failed: ",res.retcode);
         sl = be;
      }
   }

   // ---- Step Trailing ----
   double newSL = sl;
   if(rNow >= InpStep1_R){
      double s1 = LockR(entry, riskPts, InpStep1_LockR, dir);
      if( (dir==POSITION_TYPE_BUY && s1>newSL) || (dir==POSITION_TYPE_SELL && s1<newSL) ) newSL = s1;
   }
   if(rNow >= InpStep2_R){
      double s2 = LockR(entry, riskPts, InpStep2_LockR, dir);
      if( (dir==POSITION_TYPE_BUY && s2>newSL) || (dir==POSITION_TYPE_SELL && s2<newSL) ) newSL = s2;
   }
   if(rNow >= InpStep3_R){
      double s3 = LockR(entry, riskPts, InpStep3_LockR, dir);
      if( (dir==POSITION_TYPE_BUY && s3>newSL) || (dir==POSITION_TYPE_SELL && s3<newSL) ) newSL = s3;
   }

   // ---- Optional ATR trail ----
   if(InpUseATRTrail && rNow >= InpStep2_R){
      double atr = GetATR();
      if(atr>0){
         double satr = ATRTrailSL(dir, price, atr, InpATR_k);
         if( (dir==POSITION_TYPE_BUY && satr>newSL) || (dir==POSITION_TYPE_SELL && satr<newSL) ) newSL = satr;
      }
   }

   if(newSL != sl){
      MqlTradeRequest req; MqlTradeResult res; ZeroMemory(req); ZeroMemory(res);
      req.action = TRADE_ACTION_SLTP; req.symbol = sym;
      req.sl = newSL; req.tp = tp;
      if(!OrderSend(req,res)) Print("Trail SLTP failed: ",res.retcode);
   }
}

//------------------- Manage all positions --------------------------

void ManageAll(){
   if(InpCurrentSymbolOnly){
      if(PositionSelect(_Symbol)) ManageSelected();
      return;
   }
   int total=SymbolsTotal(true);
   for(int si=0; si<total; ++si){
      string s = SymbolName(si, true);
      if(PositionSelect(s)) ManageSelected();
   }
}
int total=PositionsTotal();
   for(int i=0;i<total;i++){
      if(PositionSelectByIndex(i)) ManageSelected();
   }
}

//------------------- MT5 events -----------------------------------
int OnInit(){
   if(InpEnableManager) EventSetTimer(InpTimerSeconds);
   return(INIT_SUCCEEDED);
}
void OnDeinit(const int reason){
   if(InpEnableManager) EventKillTimer();
}
void OnTick(){
   if(!InpEnableManager) return;
   if(!InpApplyOnBarClose) ManageAll();
}
void OnTimer(){
   if(!InpEnableManager) return;
   if(InpApplyOnBarClose) ManageAll();
}
//+------------------------------------------------------------------+
