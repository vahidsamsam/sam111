/* هوش‌مانیتور پرو — نسخه کامل بدون سرور
   منابع داده عمومی: CoinGecko، Binance (data-api.binance.vision)، OKX، Nobitex، gold-api، Frankfurter،
   alternative.me، Coin Metrics Community، Blockchain.com، mempool.space، rss2json */
'use strict';

/* ---------------- ابزارها ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const store = {
  get(k, d) { try { const v = localStorage.getItem('hm_' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('hm_' + k, JSON.stringify(v)); } catch (e) { toast('حافظه مرورگر پر است', 'err'); } },
  del(k) { localStorage.removeItem('hm_' + k); }
};
const faNum = new Intl.NumberFormat('fa-IR');
const toFa = s => String(s).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
const toEn = s => String(s).replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const sleep = ms => new Promise(r => setTimeout(r, ms));

function decimalsFor(p) { p = Math.abs(p); return p >= 1000 ? 0 : p >= 100 ? 2 : p >= 1 ? 3 : p >= 0.01 ? 4 : p >= 0.0001 ? 6 : 8; }
function fmtNum(v, dec) {
  if (v == null || !isFinite(v)) return '—';
  if (dec == null) dec = decimalsFor(v);
  return Number(v).toLocaleString('en-US', { minimumFractionDigits: Math.min(dec, 2), maximumFractionDigits: dec });
}
function fmtUsd(v, dec) { return v == null || !isFinite(v) ? '—' : '$' + fmtNum(v, dec); }
function fmtIrt(v) { return v == null || !isFinite(v) ? '—' : fmtNum(Math.round(v), 0) + ' ت'; }
function fmtBig(v, cur = 'usd') {
  if (v == null || !isFinite(v)) return '—';
  if (cur === 'irt') v *= state.rate;
  const a = Math.abs(v), u = cur === 'irt' ? ' ت' : '';
  const s = a >= 1e12 ? (v / 1e12).toFixed(2) + 'T' : a >= 1e9 ? (v / 1e9).toFixed(2) + 'B' : a >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : v.toFixed(0);
  return (cur === 'irt' ? '' : '$') + s + u;
}
/* قیمت با واحد انتخابی کاربر */
function fmtPrice(usd, cur = state.currency) { return cur === 'irt' ? fmtIrt(usd * state.rate) : fmtUsd(usd); }
function fmtPct(v, dec = 2) { if (v == null || !isFinite(v)) return '—'; return (v > 0 ? '+' : '') + v.toFixed(dec) + '%'; }
function pctCls(v) { return v > 0 ? 'up' : v < 0 ? 'down' : ''; }
function timeAgo(ts) {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return toFa(Math.max(s, 0)) + ' ثانیه پیش';
  if (s < 3600) return toFa(Math.round(s / 60)) + ' دقیقه پیش';
  if (s < 86400) return toFa(Math.round(s / 3600)) + ' ساعت پیش';
  return toFa(Math.round(s / 86400)) + ' روز پیش';
}
const faDate = ts => new Date(ts).toLocaleString('fa-IR', { dateStyle: 'short', timeStyle: 'short' });

async function getJSON(url, opt = {}, timeout = 15000) {
  const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), timeout);
  try {
    const r = await fetch(url, { ...opt, signal: ctl.signal });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return await r.json();
  } finally { clearTimeout(t); }
}

function toast(msg, type = '') {
  const el = document.createElement('div'); el.className = 'toast ' + type; el.innerHTML = msg;
  $('#toastBox').appendChild(el); setTimeout(() => el.remove(), 6000);
}
let audioCtx;
function beep(kind = 'alert') {
  if (!state.rules.sound) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const seq = kind === 'whale' ? [440, 330, 220] : kind === 'news' ? [880, 660] : [660, 880, 990];
    seq.forEach((f, i) => {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = f; o.type = 'sine'; o.connect(g); g.connect(audioCtx.destination);
      const t = audioCtx.currentTime + i * 0.18; g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      o.start(t); o.stop(t + 0.17);
    });
  } catch { }
}
function browserNotify(title, body) {
  if (!state.rules.notif || !('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) navigator.serviceWorker.ready.then(r => r.showNotification(title, { body, icon: 'icon.svg', dir: 'rtl', lang: 'fa' }));
    else new Notification(title, { body, icon: 'icon.svg', dir: 'rtl', lang: 'fa' });
  } catch { }
}
function download(name, content, type = 'text/plain') {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ---------------- پیکربندی ---------------- */
const MAIN5 = ['bitcoin', 'ethereum', 'binancecoin', 'solana', 'ripple'];
const STABLES = new Set(['usdt', 'usdc', 'dai', 'fdusd', 'tusd', 'usde', 'usds', 'pyusd', 'usdd', 'busd', 'usd1', 'susde', 'usdtb', 'bsc-usd', 'usdf', 'rlusd', 'usd0', 'gho', 'frax', 'usdg']);
const TIERS = {
  blue: { title: 'Blue-chip — پایداری و نقدشوندگی بالا', weight: 50, cagr: { bear: 0.08, base: 0.32, bull: 0.6 }, ids: ['bitcoin', 'ethereum', 'binancecoin', 'solana', 'ripple'] },
  mid: { title: 'Mid-cap — رشد متوسط با بنیاد قوی', weight: 30, cagr: { bear: 0.02, base: 0.45, bull: 0.9 }, ids: ['chainlink', 'avalanche-2', 'sui', 'near', 'polkadot'] },
  moon: { title: 'High-potential / Moonshot — پتانسیل رشد بالاتر با ریسک بیشتر', weight: 20, cagr: { bear: -0.15, base: 0.6, bull: 1.4 }, ids: ['render-token', 'injective-protocol', 'ondo-finance', 'celestia', 'arbitrum'] }
};
const ECO = {
  bitcoin: 'طلای دیجیتال، ورود ETFها و عرضه محدود', ethereum: 'بزرگ‌ترین اکوسیستم DeFi و لایه ۲، ETF اسپات', binancecoin: 'سوخت بزرگ‌ترین صرافی و BNB Chain',
  solana: 'سرعت بالا، میم‌کوین‌ها و رشد DePIN', ripple: 'پرداخت‌های بین‌بانکی و پایان پرونده SEC', chainlink: 'اوراکل استاندارد بازار و توکنیزه‌سازی دارایی (RWA)',
  'avalanche-2': 'ساب‌نت‌های سازمانی و RWA', sui: 'لایه ۱ جدید با رشد سریع TVL', near: 'تمرکز روی هوش مصنوعی و انتزاع زنجیره', polkadot: 'اینترآپرابیلیتی و ارتقای JAM',
  'render-token': 'رندر و GPU غیرمتمرکز برای AI', 'injective-protocol': 'زنجیره مخصوص مشتقات و فایننس', 'ondo-finance': 'پیشتاز توکنیزه‌سازی اوراق خزانه (RWA)',
  celestia: 'لایه دسترسی‌پذیری داده ماژولار', arbitrum: 'بزرگ‌ترین لایه ۲ اتریوم'
};
const BINANCE_SYMS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'TRXUSDT', 'DOTUSDT', 'SUIUSDT', 'NEARUSDT', 'LTCUSDT', 'TONUSDT', 'PAXGUSDT'];
const SIGNAL_POOL = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT', 'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'SUIUSDT', 'NEARUSDT', 'DOTUSDT', 'LTCUSDT', 'TRXUSDT', 'INJUSDT', 'RENDERUSDT', 'ARBUSDT', 'TIAUSDT', 'ONDOUSDT', 'APTUSDT'];
const FA_NAMES = {
  BTC: ['بیت کوین', 'بیتکوین', 'بیت‌کوین', 'btc', 'bitcoin'], ETH: ['اتریوم', 'اتر', 'eth', 'ethereum'], SOL: ['سولانا', 'sol', 'solana'], XRP: ['ریپل', 'xrp', 'ripple'],
  BNB: ['بایننس', 'بی ان بی', 'bnb'], DOGE: ['دوج', 'دوج کوین', 'doge'], ADA: ['کاردانو', 'ada', 'cardano'], AVAX: ['آوالانچ', 'اولانچ', 'avax'], LINK: ['چین لینک', 'چینلینک', 'link'],
  TRX: ['ترون', 'trx', 'tron'], DOT: ['پولکادات', 'dot', 'polkadot'], SUI: ['سویی', 'سوی', 'sui'], NEAR: ['نیر', 'near'], LTC: ['لایت کوین', 'لایتکوین', 'ltc'], TON: ['تون', 'ton', 'toncoin'],
  PAXG: ['طلا', 'انس', 'gold', 'xau', 'paxg'], INJ: ['اینجکتیو', 'inj'], RENDER: ['رندر', 'render'], ARB: ['آربیتروم', 'arb'], ONDO: ['اوندو', 'ondo'], TIA: ['سلستیا', 'tia'], APT: ['آپتوس', 'apt'],
  SHIB: ['شیبا', 'shib'], PEPE: ['پپه', 'pepe']
};

/* ---------------- وضعیت ---------------- */
const state = {
  currency: store.get('currency', 'usd'),
  rate: store.get('rate', 110000), rateSrc: store.get('rateSrc', 'nobitex'), rateLive: false,
  markets: [], byId: {}, bySym: {}, global: null, live: {}, gold: null, dxy: null, fng: null,
  futures: {}, news: [], seenNews: new Set(store.get('seenNews', [])), whales: [], seenTx: new Set(),
  portfolio: [], signals: [], regime: null, klineCache: {},
  rules: Object.assign({ vol: 2, whale: 5e6, words: 'ETF, SEC, Rate, Hack, Fed, CPI', tf: '15m', sound: true, notif: true }, store.get('rules', {})),
  tg: Object.assign({ token: '', chat: '', on: false, whale: true, volume: true, news: true, price: true, signal: false }, store.get('tg', {})),
  alerts: store.get('alerts', []), feed: store.get('feed', []),
  paper: store.get('paper', { balance: 10000, positions: [], history: [] }),
  keys: store.get('keys', { openai: '', model: 'gpt-4o-mini', whale: '' })
};
function priceOf(sym) { // sym: BTC
  sym = sym.toUpperCase().replace(/USDT$/, '');
  if (state.live[sym + 'USDT']) return state.live[sym + 'USDT'].c;
  if (sym === 'PAXG' && state.gold) return state.gold;
  const m = state.bySym[sym.toLowerCase()]; return m ? m.current_price : null;
}

/* ---------------- دریافت داده ---------------- */
const CG = 'https://api.coingecko.com/api/v3';
const BN = 'https://data-api.binance.vision/api/v3';
async function loadMarkets() {
  const d = await getJSON(`${CG}/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=60&page=1&sparkline=true&price_change_percentage=1h,24h,7d,30d`);
  state.markets = d.filter(c => !STABLES.has(c.symbol)).slice(0, 50);
  state.allMarkets = d;
  indexMarkets(d);
  setStatus(true);
}
function indexMarkets(list) {
  list.forEach(c => { state.byId[c.id] = c; const p = state.bySym[c.symbol]; if (!p || p.id === c.id || (p.market_cap_rank || 1e9) > (c.market_cap_rank || 1e9)) state.bySym[c.symbol] = c; });
}
async function loadPortfolioCoins() {
  const ids = Object.values(TIERS).flatMap(t => t.ids).join(',');
  const d = await getJSON(`${CG}/coins/markets?vs_currency=usd&ids=${ids}&sparkline=true&price_change_percentage=24h,7d,30d`);
  indexMarkets(d);
}
async function loadGlobal() { state.global = (await getJSON(`${CG}/global`)).data; }
async function loadRate() {
  if (state.rateSrc === 'manual') { state.rate = Number(store.get('manualRate', state.rate)); state.rateLive = false; return; }
  try {
    const d = await getJSON('https://api.nobitex.ir/market/stats?srcCurrency=usdt&dstCurrency=rls', {}, 8000);
    const st = d.stats && d.stats['usdt-rls'];
    const v = st && Number(st.latest || st.bestSell);
    if (v > 0) { state.rate = Math.round(v / 10); state.rateLive = true; store.set('rate', state.rate); return; }
    throw new Error('no data');
  } catch {
    try {
      const d = await getJSON('https://api.nobitex.ir/v2/orderbook/USDTIRT', {}, 8000);
      const v = Number(d.lastTradePrice); if (v > 0) { state.rate = Math.round(v / 10); state.rateLive = true; store.set('rate', state.rate); return; }
    } catch { }
    state.rate = Number(store.get('manualRate', state.rate)); state.rateLive = false;
  }
}
async function loadGold() {
  try { const d = await getJSON('https://api.gold-api.com/price/XAU'); state.gold = d.price; state.goldSrc = 'XAU'; }
  catch { const x = state.byId['pax-gold'] || state.bySym.paxg; if (x) { state.gold = x.current_price; state.goldSrc = 'PAXG'; } }
  try { const d = await getJSON('https://api.gold-api.com/price/XAG'); state.silver = d.price; } catch { }
}
async function loadDXY() {
  // فرمول رسمی ICE از روی نرخ‌های مرجع روزانه
  const d = await getJSON('https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,JPY,GBP,CAD,SEK,CHF');
  const r = d.rates;
  const dxy = 50.14348112 * Math.pow(1 / r.EUR, -0.576) * Math.pow(r.JPY, 0.136) * Math.pow(1 / r.GBP, -0.119) * Math.pow(r.CAD, 0.091) * Math.pow(r.SEK, 0.042) * Math.pow(r.CHF, 0.036);
  state.fx = r; state.dxy = dxy; state.fxDate = d.date;
}
async function loadFNG() { const d = await getJSON('https://api.alternative.me/fng/?limit=30'); state.fng = d.data; }
async function loadFutures() {
  const out = {};
  await Promise.all(['BTC', 'ETH', 'SOL'].map(async c => {
    try {
      const [f, oi] = await Promise.all([
        getJSON(`https://www.okx.com/api/v5/public/funding-rate?instId=${c}-USDT-SWAP`),
        getJSON(`https://www.okx.com/api/v5/public/open-interest?instId=${c}-USDT-SWAP`)]);
      out[c] = { funding: Number(f.data[0].fundingRate) * 100, oiUsd: Number(oi.data[0].oiUsd) };
    } catch { }
  }));
  try { const ls = await getJSON('https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio?ccy=BTC&period=1H'); out.lsRatio = Number(ls.data[0][1]); } catch { }
  try {
    const lq = await getJSON('https://www.okx.com/api/v5/public/liquidation-orders?instType=SWAP&uly=BTC-USDT&state=filled');
    out.liqs = (lq.data[0]?.details || []).map(x => ({ px: Number(x.bkPx), sz: Number(x.sz) * 0.01, side: x.posSide, t: Number(x.ts) }));
  } catch { }
  state.futures = out;
}
async function klines(symbol, interval = '4h', limit = 300) {
  const key = symbol + interval + limit, c = state.klineCache[key];
  if (c && Date.now() - c.t < 60000) return c.d;
  const d = await getJSON(`${BN}/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`);
  const out = d.map(k => ({ t: k[0], o: +k[1], h: +k[2], l: +k[3], c: +k[4], v: +k[5], qv: +k[7] }));
  state.klineCache[key] = { t: Date.now(), d: out };
  return out;
}
function setStatus(ok, txt) {
  const el = $('#netStatus'); el.className = 'status ' + (ok ? 'ok' : 'bad');
  el.querySelector('span').textContent = txt || (ok ? 'داده زنده' : 'اتصال قطع');
}

/* ---------------- استریم زنده Binance ---------------- */
let ws, wsSyms = [];
function startStream() {
  const syms = new Set(BINANCE_SYMS);
  state.markets.forEach(c => { if (!STABLES.has(c.symbol)) syms.add(c.symbol.toUpperCase() + 'USDT'); });
  const list = [...syms].slice(0, 80);
  if (ws && list.join() === wsSyms.join() && ws.readyState <= 1) return;
  wsSyms = list; try { ws && ws.close(); } catch { }
  ws = new WebSocket('wss://data-stream.binance.vision/stream?streams=' + list.map(s => s.toLowerCase() + '@miniTicker').join('/'));
  ws.onmessage = e => {
    const m = JSON.parse(e.data).data; if (!m) return;
    const prev = state.live[m.s]; const c = +m.c;
    state.live[m.s] = { c, o: +m.o, h: +m.h, l: +m.l, v: +m.q, chg: (c / +m.o - 1) * 100, dir: prev ? Math.sign(c - prev.c) : 0 };
    onLiveTick(m.s);
  };
  ws.onopen = () => setStatus(true, 'استریم زنده');
  ws.onclose = () => { setTimeout(startStream, 5000); };
  ws.onerror = () => { };
}
let tickQueued = false;
function onLiveTick(sym) {
  checkPriceAlerts(sym);
  if (tickQueued) return; tickQueued = true;
  requestAnimationFrame(() => {
    tickQueued = false;
    updateLivePrices();
    updatePaperPnL();
    if (chartState.symbol === sym && chartState.data.length) liveCandle(sym);
  });
}

/* ---------------- رندر داشبورد ---------------- */
function sparkline(canvas, data, color) {
  if (!canvas || !data || data.length < 2) return;
  const dpr = window.devicePixelRatio || 1, w = canvas.clientWidth || 110, h = canvas.clientHeight || 30;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext('2d'); g.scale(dpr, dpr);
  const mn = Math.min(...data), mx = Math.max(...data), sx = w / (data.length - 1);
  const y = v => h - 2 - (v - mn) / (mx - mn || 1) * (h - 4);
  color = color || (data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444');
  const grad = g.createLinearGradient(0, 0, 0, h); grad.addColorStop(0, color + '55'); grad.addColorStop(1, color + '00');
  g.beginPath(); data.forEach((v, i) => i ? g.lineTo(i * sx, y(v)) : g.moveTo(0, y(v)));
  g.strokeStyle = color; g.lineWidth = 1.4; g.stroke();
  g.lineTo(w, h); g.lineTo(0, h); g.closePath(); g.fillStyle = grad; g.fill();
}
function livePriceFor(c) { const l = state.live[c.symbol.toUpperCase() + 'USDT']; return l ? l.c : c.current_price; }
function liveChgFor(c) { const l = state.live[c.symbol.toUpperCase() + 'USDT']; return l ? l.chg : c.price_change_percentage_24h; }

function renderTicker() {
  const items = [];
  state.markets.slice(0, 20).forEach(c => items.push(`<span data-tk="${c.symbol}"><b>${c.symbol.toUpperCase()}</b><span class="ltr">${fmtPrice(livePriceFor(c))}</span> <span class="${pctCls(liveChgFor(c))} ltr">${fmtPct(liveChgFor(c))}</span></span>`));
  if (state.gold) items.push(`<span><b>طلا XAU</b><span class="ltr">${fmtPrice(state.gold)}</span></span>`);
  if (state.silver) items.push(`<span><b>نقره XAG</b><span class="ltr">${fmtPrice(state.silver)}</span></span>`);
  if (state.dxy) items.push(`<span><b>DXY</b><span class="ltr">${state.dxy.toFixed(2)}</span></span>`);
  if (state.fx) items.push(`<span><b>EUR/USD</b><span class="ltr">${(1 / state.fx.EUR).toFixed(4)}</span></span><span><b>USD/JPY</b><span class="ltr">${state.fx.JPY.toFixed(2)}</span></span><span><b>GBP/USD</b><span class="ltr">${(1 / state.fx.GBP).toFixed(4)}</span></span>`);
  items.push(`<span><b>دلار/تومان</b><span class="ltr">${fmtNum(state.rate, 0)}</span></span>`);
  const html = items.join('');
  $('#tickerTrack').innerHTML = html + html;
}
function renderTop5() {
  const box = $('#top5');
  const coins = MAIN5.map(id => state.byId[id]).filter(Boolean);
  if (!box.children.length || box.children.length !== coins.length) {
    box.innerHTML = coins.map(c => `<div class="coin-card" data-sym="${c.symbol.toUpperCase()}USDT">
      <div class="hd"><img src="${c.image}" alt="" loading="lazy"><div><div class="sym">${c.symbol.toUpperCase()}</div><div class="nm">${esc(c.name)}</div></div></div>
      <div class="px" data-px></div><div class="meta"><span data-chg></span><span data-hl></span></div>
      <div class="meta"><span>حجم: <b data-vol></b></span><span>رتبه ${toFa(c.market_cap_rank)}</span></div><canvas></canvas></div>`).join('');
    $$('.coin-card', box).forEach((el, i) => { el.onclick = () => openChart(el.dataset.sym); sparkline(el.querySelector('canvas'), coins[i].sparkline_in_7d?.price); });
  }
  coins.forEach((c, i) => {
    const el = box.children[i]; const l = state.live[c.symbol.toUpperCase() + 'USDT'];
    const p = livePriceFor(c), chg = liveChgFor(c);
    const pxEl = el.querySelector('[data-px]'); const old = pxEl.dataset.v;
    pxEl.textContent = fmtPrice(p); pxEl.dataset.v = p;
    if (old && +old !== p) { el.classList.remove('flash-up', 'flash-down'); void el.offsetWidth; el.classList.add(p > old ? 'flash-up' : 'flash-down'); }
    el.querySelector('[data-chg]').innerHTML = `<span class="${pctCls(chg)} ltr">${fmtPct(chg)}</span> ۲۴س`;
    el.querySelector('[data-hl]').innerHTML = `<span class="ltr">H ${fmtNum(l ? l.h : c.high_24h)} / L ${fmtNum(l ? l.l : c.low_24h)}</span>`;
    el.querySelector('[data-vol]').textContent = fmtBig(l ? l.v : c.total_volume, state.currency);
  });
}
let tableFilter = '';
function renderTable() {
  const tb = $('#marketTable tbody');
  const rows = state.markets.filter(c => !tableFilter || c.symbol.includes(tableFilter) || c.name.toLowerCase().includes(tableFilter));
  tb.innerHTML = rows.map((c, i) => `<tr data-sym="${c.symbol.toUpperCase()}USDT" data-id="${c.id}">
    <td>${toFa(c.market_cap_rank || i + 1)}</td>
    <td><div class="coin"><img src="${c.image}" alt="" loading="lazy"><b>${c.symbol.toUpperCase()}</b><span class="muted">${esc(c.name)}</span></div></td>
    <td class="num" data-px>${fmtPrice(livePriceFor(c))}</td>
    <td class="num ${pctCls(c.price_change_percentage_1h_in_currency)}">${fmtPct(c.price_change_percentage_1h_in_currency)}</td>
    <td class="num ${pctCls(liveChgFor(c))}" data-chg>${fmtPct(liveChgFor(c))}</td>
    <td class="num ${pctCls(c.price_change_percentage_7d_in_currency)}">${fmtPct(c.price_change_percentage_7d_in_currency)}</td>
    <td class="num">${fmtBig(c.total_volume, state.currency)}</td>
    <td class="num">${fmtBig(c.market_cap, state.currency)}</td>
    <td class="num down">${fmtPct(c.ath_change_percentage, 1)}</td>
    <td><canvas></canvas></td></tr>`).join('');
  $$('tr', tb).forEach((tr, i) => {
    sparkline(tr.querySelector('canvas'), rows[i].sparkline_in_7d?.price);
    tr.onclick = () => { if (BINANCE_SYMS.includes(tr.dataset.sym) || state.live[tr.dataset.sym]) openChart(tr.dataset.sym); };
  });
}
function updateLivePrices() {
  renderTop5();
  $$('#marketTable tbody tr').forEach(tr => {
    const l = state.live[tr.dataset.sym]; if (!l) return;
    const px = tr.querySelector('[data-px]'), txt = fmtPrice(l.c);
    if (px.textContent !== txt) { px.textContent = txt; px.classList.remove('flash-up', 'flash-down'); void px.offsetWidth; px.classList.add(l.dir >= 0 ? 'flash-up' : 'flash-down'); }
    const ch = tr.querySelector('[data-chg]'); ch.textContent = fmtPct(l.chg); ch.className = 'num ' + pctCls(l.chg);
  });
  $$('#tickerTrack [data-tk]').forEach(sp => {
    const l = state.live[sp.dataset.tk.toUpperCase() + 'USDT']; if (!l) return;
    sp.children[1].textContent = fmtPrice(l.c); sp.children[2].textContent = fmtPct(l.chg); sp.children[2].className = pctCls(l.chg) + ' ltr';
  });
  const p = $('#pSym') && priceOf($('#pSym').value || 'BTC'); if (p && $('#pPrice')) $('#pPrice').value = fmtNum(p);
}
function stableCaps() {
  const all = state.allMarkets || [];
  const f = s => (all.find(c => c.symbol === s) || {}).market_cap;
  return { usdt: f('usdt'), usdc: f('usdc') };
}
function renderLiquidity() {
  const g = state.global; const sc = stableCaps(); const fut = state.futures;
  const btcDom = g ? g.market_cap_percentage.btc : null, ethDom = g ? g.market_cap_percentage.eth : null;
  const fng = state.fng && state.fng[0];
  const it = (t, v, sub = '') => `<div class="it"><small>${t}</small><b>${v}</b>${sub}</div>`;
  const fngFa = { 'Extreme Fear': 'ترس شدید', Fear: 'ترس', Neutral: 'خنثی', Greed: 'طمع', 'Extreme Greed': 'طمع شدید' };
  const items = [
    it('دامیننس بیت‌کوین', btcDom ? btcDom.toFixed(2) + '%' : '—', ethDom ? `<em class="muted">ETH ${ethDom.toFixed(1)}%</em>` : ''),
    it('موجودی USDT', fmtBig(sc.usdt), ''), it('موجودی USDC', fmtBig(sc.usdc), ''),
    it('شاخص دلار DXY', state.dxy ? state.dxy.toFixed(2) : '—', `<em class="muted">${state.fxDate ? toFa(state.fxDate) : ''}</em>`),
    it('انس طلا', state.gold ? fmtUsd(state.gold, 1) : '—', state.silver ? `<em class="muted">نقره ${fmtUsd(state.silver, 2)}</em>` : ''),
    it('ارزش کل بازار', g ? fmtBig(g.total_market_cap.usd) : '—', g ? `<em class="${pctCls(g.market_cap_change_percentage_24h_usd)}">${fmtPct(g.market_cap_change_percentage_24h_usd)}</em>` : ''),
    it('ترس و طمع', fng ? toFa(fng.value) : '—', fng ? `<em class="muted">${fngFa[fng.value_classification] || fng.value_classification}</em>` : ''),
    it('Funding BTC', fut.BTC ? fut.BTC.funding.toFixed(4) + '%' : '—', ''),
    it('لیکوییدیشن اخیر BTC', fut.liqs ? fmtBig(fut.liqs.reduce((a, x) => a + x.sz * x.px, 0)) : '—', fut.liqs ? `<em class="muted">${toFa(fut.liqs.length)} سفارش</em>` : '')
  ];
  $('#liqDash').innerHTML = items.join('');
  $('#liqChart').innerHTML = items.slice(0, 8).join('');
}
function renderFutures() {
  const f = state.futures, rows = [];
  ['BTC', 'ETH', 'SOL'].forEach(c => { if (f[c]) rows.push(`<div><span>Funding ${c}</span><b class="${f[c].funding > 0.03 ? 'down' : f[c].funding < 0 ? 'up' : ''}">${f[c].funding.toFixed(4)}%</b></div><div><span>Open Interest ${c}</span><b>${fmtBig(f[c].oiUsd)}</b></div>`); });
  if (f.lsRatio) rows.push(`<div><span>نسبت حساب‌های لانگ/شورت BTC</span><b>${f.lsRatio.toFixed(2)}</b></div>`);
  $('#futuresBox').innerHTML = rows.join('') || '<p class="muted">داده فیوچرز در دسترس نیست.</p>';
  const lq = (f.liqs || []).slice(0, 25);
  const mx = Math.max(1, ...lq.map(x => x.sz * x.px));
  $('#liqMap').innerHTML = lq.length ? lq.map(x => `<div class="bar"><span>${fmtUsd(x.px, 0)} · ${fmtBig(x.sz * x.px)}</span><i style="width:${Math.max(3, x.sz * x.px / mx * 100)}%;background:${x.side === 'long' ? 'var(--down)' : 'var(--up)'}"></i><small class="muted">${x.side === 'long' ? 'لانگ' : 'شورت'} · ${timeAgo(x.t)}</small></div>`).join('') : '<p class="muted">لیکوییدیشنی ثبت نشده.</p>';
}
function renderNews() {
  const words = state.rules.words.split(',').map(w => w.trim()).filter(Boolean);
  const re = words.length ? new RegExp('\\b(' + words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b', 'i') : null;
  $('#newsList').innerHTML = state.news.slice(0, 40).map(n => {
    const hot = re && re.test(n.title);
    return `<li><a href="${esc(n.link)}" target="_blank" rel="noopener">${hot ? '<span class="hot">مهم</span>' : ''}${esc(n.title)}</a><div class="t">${esc(n.src)} · ${timeAgo(n.t)} · <span class="${n.s > 0 ? 'up' : n.s < 0 ? 'down' : 'muted'}">${n.s > 0 ? 'مثبت' : n.s < 0 ? 'منفی' : 'خنثی'}</span></div></li>`;
  }).join('') || '<li class="muted">خبری دریافت نشد.</li>';
}
function renderRate() {
  $('#rateChip').textContent = 'دلار: ' + fmtNum(state.rate, 0) + ' ت' + (state.rateLive ? ' (نوبیتکس)' : ' (دستی)');
  $('#rateInfo').textContent = state.rateLive ? `نرخ لحظه‌ای تتر در نوبیتکس: ${fmtNum(state.rate, 0)} تومان` : `نوبیتکس در دسترس نبود یا حالت دستی انتخاب شده؛ نرخ فعلی ${fmtNum(state.rate, 0)} تومان است. نرخ دلار آزاد روز را این‌جا وارد کنید.`;
}
function renderAll() { renderTicker(); renderTop5(); renderTable(); renderLiquidity(); renderRate(); fillCoinSelects(); }

/* TradingView embeds (تقویم اقتصادی + DXY/طلا/نفت) */
function tvEmbed(container, script, cfg) {
  const el = typeof container === 'string' ? $(container) : container; if (!el || el.dataset.loaded) return;
  el.dataset.loaded = 1; el.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
  const s = document.createElement('script'); s.src = 'https://s3.tradingview.com/external-embedding/' + script; s.async = true;
  s.textContent = JSON.stringify(cfg); el.appendChild(s);
}
function loadTVWidgets() {
  tvEmbed('#tvCalendar', 'embed-widget-events.js', { colorTheme: 'dark', isTransparent: true, width: '100%', height: 420, locale: 'en', importanceFilter: '0,1', countryFilter: 'us,eu,cn,gb,jp' });
  tvEmbed('#tvTickers', 'embed-widget-market-quotes.js', {
    width: '100%', height: 420, colorTheme: 'dark', isTransparent: true, locale: 'en', showSymbolLogo: true,
    symbolsGroups: [
      { name: 'Indices & Commodities', symbols: [{ name: 'TVC:DXY', displayName: 'DXY' }, { name: 'OANDA:XAUUSD', displayName: 'Gold' }, { name: 'TVC:USOIL', displayName: 'WTI Oil' }, { name: 'TVC:UKOIL', displayName: 'Brent Oil' }, { name: 'TVC:SPX', displayName: 'S&P 500' }] },
      { name: 'Forex', symbols: [{ name: 'FX:EURUSD' }, { name: 'FX:GBPUSD' }, { name: 'FX:USDJPY' }, { name: 'FX:USDCHF' }, { name: 'FX:AUDUSD' }] }
    ]
  });
}

/* ---------------- اندیکاتورها ---------------- */
function sma(a, n) { const o = Array(a.length).fill(null); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
function ema(a, n) { const o = Array(a.length).fill(null), k = 2 / (n + 1); let p = null; for (let i = 0; i < a.length; i++) { if (i < n - 1) continue; if (p == null) { p = a.slice(0, n).reduce((x, y) => x + y, 0) / n; } else p = a[i] * k + p * (1 - k); o[i] = p; } return o; }
function bollinger(a, n = 20, m = 2) {
  const mid = sma(a, n), up = [], lo = [];
  for (let i = 0; i < a.length; i++) {
    if (mid[i] == null) { up.push(null); lo.push(null); continue; }
    let s = 0; for (let j = i - n + 1; j <= i; j++) s += (a[j] - mid[i]) ** 2;
    const sd = Math.sqrt(s / n); up.push(mid[i] + m * sd); lo.push(mid[i] - m * sd);
  }
  return { mid, up, lo };
}
function rsi(a, n = 14) {
  const o = Array(a.length).fill(null); if (a.length <= n) return o;
  let g = 0, l = 0;
  for (let i = 1; i <= n; i++) { const d = a[i] - a[i - 1]; d > 0 ? g += d : l -= d; }
  g /= n; l /= n; o[n] = 100 - 100 / (1 + g / (l || 1e-9));
  for (let i = n + 1; i < a.length; i++) { const d = a[i] - a[i - 1]; g = (g * (n - 1) + Math.max(d, 0)) / n; l = (l * (n - 1) + Math.max(-d, 0)) / n; o[i] = 100 - 100 / (1 + g / (l || 1e-9)); }
  return o;
}
function atr(k, n = 14) {
  const tr = k.map((c, i) => i ? Math.max(c.h - c.l, Math.abs(c.h - k[i - 1].c), Math.abs(c.l - k[i - 1].c)) : c.h - c.l);
  const o = Array(k.length).fill(null); let p = null;
  for (let i = 0; i < k.length; i++) { if (i < n - 1) continue; p = p == null ? tr.slice(0, n).reduce((a, b) => a + b, 0) / n : (p * (n - 1) + tr[i]) / n; o[i] = p; }
  return o;
}
function techSnapshot(k) {
  const c = k.map(x => x.c), last = c.length - 1;
  const e20 = ema(c, 20), e50 = ema(c, 50), e200 = ema(c, Math.min(200, c.length - 1)), r = rsi(c), a = atr(k), bb = bollinger(c);
  const vols = k.map(x => x.v); const avgV = vols.slice(-21, -1).reduce((x, y) => x + y, 0) / 20;
  const hi = Math.max(...k.slice(-30).map(x => x.h)), lo = Math.min(...k.slice(-30).map(x => x.l));
  return { price: c[last], e20: e20[last], e50: e50[last], e200: e200[last], rsi: r[last], rsiPrev: r[last - 1], atr: a[last], bbUp: bb.up[last], bbLo: bb.lo[last], bbMid: bb.mid[last], volRatio: vols[last] / (avgV || 1), hi30: hi, lo30: lo, chg: (c[last] / c[Math.max(0, last - 6)] - 1) * 100 };
}

/* ---------------- چارت ---------------- */
const chartState = { symbol: 'BTCUSDT', tf: '4h', data: [], hover: -1, tv: false, offset: 0 };
function openChart(sym) {
  showSection('chart');
  const sel = $('#chartSymbol');
  if (![...sel.options].some(o => o.value === sym)) { const o = document.createElement('option'); o.value = sym; o.textContent = sym.replace('USDT', ''); sel.appendChild(o); }
  sel.value = sym; loadChart();
}
async function loadChart() {
  chartState.symbol = $('#chartSymbol').value; chartState.offset = 0;
  const isOil = chartState.symbol === 'OIL';
  const useTV = chartState.tv || isOil;
  $('#priceCanvas').hidden = useTV; $('#rsiCanvas').hidden = useTV; $('#chartLegend').hidden = useTV; $('#tvChart').hidden = !useTV;
  if (useTV) { renderTVChart(isOil ? 'TVC:USOIL' : chartState.symbol === 'PAXGUSDT' ? 'OANDA:XAUUSD' : 'BINANCE:' + chartState.symbol); renderTechSummary(null); return; }
  try {
    chartState.data = await klines(chartState.symbol, chartState.tf, 500);
    drawChart(); renderTechSummary(techSnapshot(chartState.data));
  } catch (e) { $('#chartLegend').textContent = 'خطا در دریافت داده چارت: ' + e.message; }
}
function renderTVChart(symbol) {
  const el = $('#tvChart'); delete el.dataset.loaded;
  const tfMap = { '15m': '15', '1h': '60', '4h': '240', '1d': 'D', '1w': 'W' };
  const studies = []; if ($('#indMA').checked) studies.push('STD;SMA'); if ($('#indBB').checked) studies.push('STD;Bollinger_Bands'); if ($('#indRSI').checked) studies.push('STD;RSI');
  tvEmbed(el, 'embed-widget-advanced-chart.js', { autosize: true, symbol, interval: tfMap[chartState.tf], timezone: 'Asia/Tehran', theme: 'dark', style: '1', locale: 'en', allow_symbol_change: true, studies, support_host: 'https://www.tradingview.com' });
}
function renderTechSummary(t) {
  const box = $('#techSummary');
  if (!t) { box.innerHTML = '<div><span>نمایش</span><b>TradingView</b></div>'; return; }
  const trend = t.price > t.e50 && t.e20 > t.e50 ? ['صعودی', 'up'] : t.price < t.e50 && t.e20 < t.e50 ? ['نزولی', 'down'] : ['خنثی', ''];
  const rs = t.rsi > 70 ? 'اشباع خرید' : t.rsi < 30 ? 'اشباع فروش' : 'نرمال';
  box.innerHTML = `<div><span>قیمت</span><b>${fmtPrice(t.price)}</b></div><div><span>روند</span><b class="${trend[1]}">${trend[0]}</b></div>
    <div><span>RSI(14)</span><b>${t.rsi?.toFixed(1)} · ${rs}</b></div><div><span>EMA20 / EMA50</span><b>${fmtNum(t.e20)} / ${fmtNum(t.e50)}</b></div>
    <div><span>بولینگر بالا/پایین</span><b>${fmtNum(t.bbUp)} / ${fmtNum(t.bbLo)}</b></div><div><span>ATR(14)</span><b>${fmtNum(t.atr)}</b></div>
    <div><span>حمایت / مقاومت ۳۰ کندل</span><b>${fmtNum(t.lo30)} / ${fmtNum(t.hi30)}</b></div><div><span>حجم نسبت به میانگین ۲۰</span><b class="${t.volRatio >= state.rules.vol ? 'up' : ''}">×${t.volRatio.toFixed(2)}</b></div>`;
}
function liveCandle(sym) {
  const l = state.live[sym], d = chartState.data, last = d[d.length - 1]; if (!l || !last) return;
  const step = d.length > 1 ? last.t - d[d.length - 2].t : 0;
  if (step > 0 && Date.now() >= last.t + step) { d.push({ t: last.t + Math.floor((Date.now() - last.t) / step) * step, o: last.c, h: l.c, l: l.c, c: l.c, v: 0 }); if (d.length > 1000) d.shift(); }
  else { last.c = l.c; last.h = Math.max(last.h, l.c); last.l = Math.min(last.l, l.c); }
  if (!liveCandle.t || Date.now() - liveCandle.t > 1000) { liveCandle.t = Date.now(); drawChart(); }
}
function setupCanvas(cv) {
  const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width !== w * dpr || cv.height !== h * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, w, h); g.direction = 'ltr'; g.textAlign = 'left';
  return { g, w, h };
}
function drawChart() {
  const cv = $('#priceCanvas'); if (cv.hidden || !cv.clientWidth) return;
  const all = chartState.data; if (!all.length) return;
  const { g, w, h } = setupCanvas(cv);
  const padR = 70, padT = 30, padB = 22, cw = 8;
  const n = Math.min(all.length, Math.floor((w - padR) / cw));
  const end = all.length - chartState.offset, start = Math.max(0, end - n);
  const closes = all.map(x => x.c), ma20 = sma(closes, 20), ma50 = sma(closes, 50), bb = bollinger(closes), rs = rsi(closes);
  const vis = all.slice(start, end);
  let mn = Math.min(...vis.map(x => x.l)), mx = Math.max(...vis.map(x => x.h));
  if ($('#indBB').checked) for (let i = start; i < end; i++) { if (bb.up[i]) { mx = Math.max(mx, bb.up[i]); mn = Math.min(mn, bb.lo[i]); } }
  const pad = (mx - mn) * 0.05; mn -= pad; mx += pad;
  const y = v => padT + (mx - v) / (mx - mn) * (h - padT - padB);
  const x = i => (i - start) * cw + cw / 2 + 4;
  // grid
  g.strokeStyle = '#1c2a44'; g.fillStyle = '#8a9bb8'; g.font = '11px Vazirmatn, Tahoma'; g.lineWidth = 1;
  for (let i = 0; i <= 6; i++) { const v = mn + (mx - mn) * i / 6, yy = y(v); g.beginPath(); g.moveTo(0, yy); g.lineTo(w - padR, yy); g.stroke(); g.fillText(fmtNum(v), w - padR + 6, yy + 4); }
  // volume
  const vmx = Math.max(...vis.map(c => c.v));
  vis.forEach((c, j) => { const i = start + j; const vh = c.v / vmx * 60; g.fillStyle = c.c >= c.o ? 'rgba(34,197,94,.18)' : 'rgba(239,68,68,.18)'; g.fillRect(x(i) - cw / 2 + 1, h - padB - vh, cw - 2, vh); });
  // bollinger
  const line = (arr, color, wd = 1.3, dash) => { g.beginPath(); let st = false; for (let i = start; i < end; i++) { if (arr[i] == null) continue; st ? g.lineTo(x(i), y(arr[i])) : g.moveTo(x(i), y(arr[i])); st = true; } g.strokeStyle = color; g.lineWidth = wd; g.setLineDash(dash || []); g.stroke(); g.setLineDash([]); };
  if ($('#indBB').checked) {
    g.beginPath(); let st = false;
    for (let i = start; i < end; i++) { if (bb.up[i] == null) continue; st ? g.lineTo(x(i), y(bb.up[i])) : g.moveTo(x(i), y(bb.up[i])); st = true; }
    for (let i = end - 1; i >= start; i--) { if (bb.lo[i] == null) continue; g.lineTo(x(i), y(bb.lo[i])); }
    g.fillStyle = 'rgba(96,165,250,.07)'; g.fill();
    line(bb.up, '#60a5fa', 1); line(bb.lo, '#60a5fa', 1); line(bb.mid, '#60a5fa', 1, [4, 4]);
  }
  // candles
  vis.forEach((c, j) => {
    const i = start + j, up = c.c >= c.o; g.strokeStyle = g.fillStyle = up ? '#22c55e' : '#ef4444';
    g.beginPath(); g.moveTo(x(i), y(c.h)); g.lineTo(x(i), y(c.l)); g.stroke();
    const top = y(Math.max(c.o, c.c)), bh = Math.max(1, Math.abs(y(c.o) - y(c.c))); g.fillRect(x(i) - cw / 2 + 1.5, top, cw - 3, bh);
  });
  if ($('#indMA').checked) { line(ma20, '#f5b83d', 1.5); line(ma50, '#c084fc', 1.5); }
  // last price
  const lp = all[all.length - 1].c, ly = y(lp);
  if (ly > padT && ly < h - padB) { g.setLineDash([3, 3]); g.strokeStyle = '#f5b83d'; g.beginPath(); g.moveTo(0, ly); g.lineTo(w - padR, ly); g.stroke(); g.setLineDash([]); g.fillStyle = '#f5b83d'; g.fillRect(w - padR, ly - 9, padR, 18); g.fillStyle = '#111'; g.fillText(fmtNum(lp), w - padR + 5, ly + 4); }
  // time labels
  g.fillStyle = '#8a9bb8'; const step = Math.ceil(vis.length / 7);
  for (let j = 0; j < vis.length; j += step) { const d = new Date(vis[j].t); g.fillText(chartState.tf === '1d' || chartState.tf === '1w' ? d.toLocaleDateString('fa-IR', { month: 'short', day: 'numeric' }) : d.toLocaleString('fa-IR', { day: 'numeric', hour: '2-digit', minute: '2-digit' }), x(start + j) - 20, h - 6); }
  // crosshair
  let hi = chartState.hover >= 0 ? clamp(start + chartState.hover, start, end - 1) : end - 1;
  if (chartState.hover >= 0) { g.strokeStyle = 'rgba(255,255,255,.25)'; g.beginPath(); g.moveTo(x(hi), padT); g.lineTo(x(hi), h - padB); g.stroke(); }
  const c = all[hi];
  $('#chartLegend').innerHTML = `<b>${chartState.symbol.replace('USDT', '/USDT')}</b> · ${chartState.tf} &nbsp; O <b>${fmtNum(c.o)}</b> H <b>${fmtNum(c.h)}</b> L <b>${fmtNum(c.l)}</b> C <b class="${c.c >= c.o ? 'up' : 'down'}">${fmtNum(c.c)}</b>` +
    ($('#indMA').checked ? ` &nbsp; <span style="color:#f5b83d">MA20 ${fmtNum(ma20[hi])}</span> <span style="color:#c084fc">MA50 ${fmtNum(ma50[hi])}</span>` : '') +
    ($('#indBB').checked ? ` &nbsp; <span style="color:#60a5fa">BB ${fmtNum(bb.up[hi])} / ${fmtNum(bb.lo[hi])}</span>` : '') +
    ($('#indRSI').checked ? ` &nbsp; RSI <b>${rs[hi]?.toFixed(1) ?? '—'}</b>` : '');
  drawRSI(rs, start, end, x, hi);
}
function drawRSI(rs, start, end, x, hi) {
  const cv = $('#rsiCanvas'); cv.style.display = $('#indRSI').checked ? 'block' : 'none'; if (!$('#indRSI').checked) return;
  const { g, w, h } = setupCanvas(cv), padR = 70;
  const y = v => 8 + (100 - v) / 100 * (h - 16);
  g.fillStyle = 'rgba(192,132,252,.07)'; g.fillRect(0, y(70), w - padR, y(30) - y(70));
  g.strokeStyle = '#2a3a5a'; g.setLineDash([3, 3]); [30, 50, 70].forEach(v => { g.beginPath(); g.moveTo(0, y(v)); g.lineTo(w - padR, y(v)); g.stroke(); });
  g.setLineDash([]); g.fillStyle = '#8a9bb8'; g.font = '11px Vazirmatn, Tahoma'; g.fillText('RSI 14', w - padR + 6, 16); [30, 70].forEach(v => g.fillText(v, w - padR + 6, y(v) + 4));
  g.beginPath(); let st = false; for (let i = start; i < end; i++) { if (rs[i] == null) continue; st ? g.lineTo(x(i), y(rs[i])) : g.moveTo(x(i), y(rs[i])); st = true; }
  g.strokeStyle = '#c084fc'; g.lineWidth = 1.5; g.stroke();
  if (rs[hi] != null) { g.fillStyle = '#c084fc'; g.beginPath(); g.arc(x(hi), y(rs[hi]), 3, 0, 7); g.fill(); }
}
function bindChart() {
  const cv = $('#priceCanvas');
  cv.addEventListener('mousemove', e => { const r = cv.getBoundingClientRect(); chartState.hover = Math.floor((e.clientX - r.left - 4) / 8); drawChart(); });
  cv.addEventListener('mouseleave', () => { chartState.hover = -1; drawChart(); });
  cv.addEventListener('wheel', e => { e.preventDefault(); chartState.offset = clamp(chartState.offset + (e.deltaY > 0 ? -10 : 10), 0, Math.max(0, chartState.data.length - 60)); drawChart(); }, { passive: false });
  $('#chartSymbol').onchange = loadChart;
  $$('#tfSeg button').forEach(b => b.onclick = () => { $$('#tfSeg button').forEach(x => x.classList.remove('active')); b.classList.add('active'); chartState.tf = b.dataset.tf; loadChart(); });
  ['indMA', 'indBB', 'indRSI'].forEach(id => $('#' + id).onchange = () => chartState.tv ? loadChart() : drawChart());
  $('#tvToggle').onclick = () => { chartState.tv = !chartState.tv; $('#tvToggle').textContent = chartState.tv ? 'نمایش چارت داخلی' : 'نمایش با TradingView'; loadChart(); };
  window.addEventListener('resize', () => { drawChart(); });
}

/* ---------------- لایه هشدار ---------------- */
const FEED_ICONS = { whale: '🐋', volume: '📊', news: '📰', price: '🔔', signal: '🎯', info: 'ℹ️' };
function pushAlert(type, title, body = '', opts = {}) {
  const item = { type, title, body, t: Date.now() };
  state.feed.unshift(item); state.feed = state.feed.slice(0, 120); store.set('feed', state.feed);
  renderFeed();
  if (opts.silent) return;
  toast(`${FEED_ICONS[type] || ''} <b>${esc(title)}</b><br><small>${esc(body)}</small>`);
  beep(type); browserNotify('هوش‌مانیتور: ' + title, body);
  if (state.tg.on && state.tg[type]) sendTelegram(`${FEED_ICONS[type] || ''} <b>${esc(title)}</b>\n${esc(body)}`);
}
function renderFeed() {
  $('#alertFeed').innerHTML = state.feed.length ? state.feed.slice(0, 60).map(f => `<li class="${f.type}">${FEED_ICONS[f.type] || ''} <b>${esc(f.title)}</b><div>${esc(f.body)}</div><div class="t">${timeAgo(f.t)}</div></li>`).join('') : '<li class="muted">هنوز هشداری ثبت نشده است. پایش هر ۶۰ ثانیه انجام می‌شود.</li>';
}
const seenVol = new Set();
async function monitorVolume() {
  const syms = BINANCE_SYMS.slice(0, 12);
  for (const s of syms) {
    try {
      const k = await klines(s, state.rules.tf, 22);
      const closed = k[k.length - 2], prev = k.slice(-22, -2);
      const avg = prev.reduce((a, x) => a + x.v, 0) / prev.length;
      const ratio = closed.v / (avg || 1), key = s + closed.t;
      if (ratio >= state.rules.vol && !seenVol.has(key)) {
        seenVol.add(key);
        const dir = closed.c >= closed.o ? 'صعودی' : 'نزولی';
        pushAlert('volume', `رشد حجم ${s.replace('USDT', '')} ×${ratio.toFixed(1)}`, `کندل ${state.rules.tf} ${dir} با حجم ${fmtBig(closed.qv)} — ${ratio.toFixed(1)} برابر میانگین ۲۰ کندل. قیمت ${fmtUsd(closed.c)}`);
      }
    } catch { }
    await sleep(150);
  }
}
async function monitorWhales() {
  const btc = priceOf('BTC'); if (!btc) return;
  try {
    const recent = await getJSON('https://mempool.space/api/mempool/recent');
    recent.forEach(tx => {
      const usd = tx.value / 1e8 * btc;
      if (usd >= state.rules.whale / 5 && !state.seenTx.has(tx.txid)) {
        state.seenTx.add(tx.txid);
        const w = { id: tx.txid, coin: 'BTC', amount: tx.value / 1e8, usd, t: Date.now(), src: 'mempool', link: 'https://mempool.space/tx/' + tx.txid };
        state.whales.unshift(w);
        if (usd >= state.rules.whale) pushAlert('whale', `تراکنش نهنگ: ${fmtNum(w.amount, 2)} BTC`, `ارزش ${fmtBig(usd)} — در حال تأیید در شبکه بیت‌کوین`);
      }
    });
  } catch { }
  if (state.keys.whale) {
    try {
      const start = Math.floor(Date.now() / 1000) - 3500;
      const d = await getJSON(`https://api.whale-alert.io/v1/transactions?api_key=${encodeURIComponent(state.keys.whale)}&min_value=${state.rules.whale}&start=${start}`);
      (d.transactions || []).forEach(tx => {
        if (state.seenTx.has(tx.hash)) return; state.seenTx.add(tx.hash);
        const w = { id: tx.hash, coin: tx.symbol.toUpperCase(), amount: tx.amount, usd: tx.amount_usd, t: tx.timestamp * 1000, src: `${tx.from.owner || 'ناشناس'} ← ${tx.to.owner || 'ناشناس'}`, link: '#' };
        state.whales.unshift(w);
        pushAlert('whale', `نهنگ ${w.coin}: ${fmtBig(w.usd)}`, `${fmtNum(w.amount, 0)} ${w.coin} از ${tx.from.owner || 'کیف ناشناس'} به ${tx.to.owner || 'کیف ناشناس'}`);
      });
    } catch { }
  }
  state.whales = state.whales.slice(0, 60);
  renderWhales();
}
function renderWhales() {
  $('#whaleList').innerHTML = state.whales.length ? state.whales.map(w => `<li class="whale">🐋 <b class="ltr">${fmtNum(w.amount, 2)} ${w.coin}</b> — <b>${fmtBig(w.usd)}</b>${w.usd >= state.rules.whale ? ' <span class="badge">نهنگ</span>' : ''}<div class="t">${esc(w.src)} · ${timeAgo(w.t)} ${w.link !== '#' ? `· <a href="${w.link}" target="_blank" rel="noopener">مشاهده</a>` : ''}</div></li>`).join('') : `<li class="muted">در چند دقیقه اخیر تراکنش بالای ${fmtBig(state.rules.whale / 5)} دیده نشده است.</li>`;
}

/* اخبار + سنتیمنت */
const FEEDS = [
  ['CoinDesk', 'https://www.coindesk.com/arc/outboundfeeds/rss/'],
  ['The Block', 'https://www.theblock.co/rss.xml'],
  ['Cointelegraph', 'https://cointelegraph.com/rss']
];
const POS_W = ['surge', 'soar', 'rally', 'jump', 'gain', 'bull', 'record', 'high', 'approve', 'approval', 'inflow', 'adopt', 'partnership', 'launch', 'upgrade', 'breakout', 'rise', 'buy', 'accumulat', 'boost', 'win', 'growth', 'recover', 'etf inflow', 'rebound', 'optimis'];
const NEG_W = ['crash', 'plunge', 'drop', 'fall', 'bear', 'hack', 'exploit', 'lawsuit', 'sue', 'ban', 'outflow', 'liquidat', 'fraud', 'scam', 'sell-off', 'selloff', 'dump', 'low', 'fear', 'reject', 'delay', 'investigat', 'charge', 'loss', 'slump', 'tumble', 'warn', 'decline', 'risk', 'collapse'];
function sentimentScore(text) {
  const t = text.toLowerCase(); let s = 0;
  POS_W.forEach(w => { if (t.includes(w)) s++; }); NEG_W.forEach(w => { if (t.includes(w)) s--; });
  return clamp(s, -3, 3);
}
async function loadNews(first) {
  const out = [];
  await Promise.all(FEEDS.map(async ([src, url]) => {
    try {
      const d = await getJSON('https://api.rss2json.com/v1/api.json?rss_url=' + encodeURIComponent(url));
      (d.items || []).forEach(i => out.push({ title: i.title, link: i.link, src, t: new Date((i.pubDate || '').replace(' ', 'T') + 'Z').getTime() || Date.now() }));
    } catch { }
  }));
  if (!out.length) return;
  out.forEach(n => n.s = sentimentScore(n.title));
  out.sort((a, b) => b.t - a.t);
  const words = state.rules.words.split(',').map(w => w.trim()).filter(Boolean);
  const re = words.length ? new RegExp('\\b(' + words.join('|') + ')\\b', 'i') : null;
  out.forEach(n => {
    if (state.seenNews.has(n.link)) return; state.seenNews.add(n.link);
    if (!first && re && re.test(n.title) && Date.now() - n.t < 3 * 3600e3) pushAlert('news', 'خبر مهم: ' + (n.title.match(re)[0]), n.title + ' — ' + n.src);
  });
  store.set('seenNews', [...state.seenNews].slice(-400));
  state.news = out; renderNews(); renderSentiment();
}
function renderSentiment() {
  const coins = ['BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'LINK'];
  const fng = state.fng ? Number(state.fng[0].value) : 50;
  $('#sentGrid').innerHTML = coins.map(c => {
    const names = (FA_NAMES[c] || []).filter(n => /^[a-z]+$/.test(n));
    const rel = state.news.filter(n => names.some(nm => new RegExp('\\b' + nm + '\\b', 'i').test(n.title)));
    const ns = rel.length ? rel.reduce((a, n) => a + n.s, 0) / rel.length : 0;
    const m = state.bySym[c.toLowerCase()]; const mom = m ? clamp((m.price_change_percentage_7d_in_currency || 0) / 2, -10, 10) : 0;
    const score = Math.round(clamp(50 + ns * 15 + (fng - 50) * 0.3 + mom * 1.5, 0, 100));
    const lbl = score >= 60 ? ['مثبت', 'up'] : score <= 40 ? ['منفی', 'down'] : ['خنثی', 'muted'];
    return `<div class="sent-card"><div class="row" style="justify-content:space-between"><b>${c}</b><span class="score ${lbl[1]}">${toFa(score)}</span></div>
      <div class="sent-meter"><i style="right:${100 - score}%"></i></div><small class="${lbl[1]}">جو ${lbl[0]}</small> <small class="muted">· ${toFa(rel.length)} خبر</small>
      ${rel[0] ? `<div class="hint" style="margin-top:4px">${esc(rel[0].title.slice(0, 90))}</div>` : ''}</div>`;
  }).join('');
}

/* هشدار شرطی قیمت */
function checkPriceAlerts(sym) {
  const l = state.live[sym]; if (!l) return;
  let changed = false;
  state.alerts.forEach(a => {
    if (a.done || a.sym + 'USDT' !== sym) return;
    if ((a.cond === 'above' && l.c >= a.price) || (a.cond === 'below' && l.c <= a.price)) {
      a.done = true; a.hitAt = Date.now(); changed = true;
      pushAlert('price', `${a.sym} ${a.cond === 'above' ? 'بالاتر از' : 'پایین‌تر از'} ${fmtUsd(a.price)}`, `قیمت فعلی ${fmtUsd(l.c)}${a.note ? ' — ' + a.note : ''}`);
    }
  });
  if (changed) { store.set('alerts', state.alerts); renderAlertList(); }
}
function renderAlertList() {
  $('#alertList').innerHTML = state.alerts.length ? state.alerts.map((a, i) => `<li><span>${a.done ? '✅' : '⏳'} <b>${esc(a.sym)}</b> ${a.cond === 'above' ? 'بالاتر از' : 'پایین‌تر از'} <b class="ltr">${fmtUsd(a.price)}</b> ${a.note ? '<small class="muted">' + esc(a.note) + '</small>' : ''} <small class="muted ltr">(اکنون ${fmtUsd(priceOf(a.sym))})</small></span><button class="btn sm ghost" data-del="${i}">حذف</button></li>`).join('') : '<li class="muted">هشداری تعریف نشده.</li>';
  $$('#alertList [data-del]').forEach(b => b.onclick = () => { state.alerts.splice(+b.dataset.del, 1); store.set('alerts', state.alerts); renderAlertList(); });
}

/* تلگرام */
async function sendTelegram(text, force) {
  const { token, chat } = state.tg; if (!token || !chat) { if (force) toast('توکن و Chat ID را وارد کنید', 'err'); return false; }
  try {
    const r = await getJSON(`https://api.telegram.org/bot${token}/sendMessage`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chat_id: chat, text, parse_mode: 'HTML', disable_web_page_preview: true }) });
    if (force) toast('پیام تلگرام ارسال شد ✅', 'ok'); return r.ok;
  } catch (e) { if (force) toast('ارسال تلگرام ناموفق: ' + e.message, 'err'); return false; }
}

/* ---------------- رژیم بازار، سیگنال و سبد ---------------- */
async function computeRegime() {
  const k = await klines('BTCUSDT', '1d', 400);
  const c = k.map(x => x.c), last = c.length - 1;
  const e50 = ema(c, 50)[last], e200 = ema(c, 200)[last], r = rsi(c)[last];
  const chg30 = (c[last] / c[last - 30] - 1) * 100, chg90 = (c[last] / c[last - 90] - 1) * 100;
  const fng = state.fng ? Number(state.fng[0].value) : 50;
  const fund = state.futures.BTC ? state.futures.BTC.funding : 0.01;
  const f = [
    ['قیمت نسبت به EMA200 روزانه', c[last] > e200 ? 14 : -14, c[last] > e200 ? 'بالای میانگین ۲۰۰' : 'زیر میانگین ۲۰۰'],
    ['EMA50 نسبت به EMA200', e50 > e200 ? 10 : -10, e50 > e200 ? 'تقاطع طلایی' : 'تقاطع مرگ'],
    ['بازده ۳۰ روزه', clamp(chg30 * 0.6, -10, 10), fmtPct(chg30, 1)],
    ['بازده ۹۰ روزه', clamp(chg90 * 0.25, -8, 8), fmtPct(chg90, 1)],
    ['RSI روزانه', clamp((r - 50) * 0.4, -8, 8), r.toFixed(1)],
    ['شاخص ترس و طمع', clamp((fng - 50) * 0.2, -8, 8), toFa(fng)],
    ['Funding Rate', fund > 0.05 ? -3 : fund < 0 ? -2 : 3, fund.toFixed(4) + '%']
  ];
  const score = Math.round(clamp(50 + f.reduce((a, x) => a + x[1], 0), 0, 100));
  const label = score >= 65 ? 'گاوی' : score >= 55 ? 'متمایل به گاوی' : score > 45 ? 'خنثی / رنج' : score > 35 ? 'متمایل به خرسی' : 'خرسی';
  state.regime = { score, label, factors: f, price: c[last], e200, e50, rsi: r, chg30, chg90 };
  drawGauge(score, label);
  $('#regimeFactors').innerHTML = f.map(x => `<div><span>${x[0]}</span><b class="${pctCls(x[1])}">${x[2]}</b></div>`).join('');
}
function drawGauge(score, label) {
  const cv = $('#gaugeCanvas'), g = cv.getContext('2d'), W = cv.width, H = cv.height, cx = W / 2, cy = H - 30, R = 120;
  g.clearRect(0, 0, W, H);
  const cols = ['#ef4444', '#f97316', '#eab308', '#84cc16', '#22c55e'];
  cols.forEach((col, i) => { g.beginPath(); g.arc(cx, cy, R, Math.PI + i * Math.PI / 5, Math.PI + (i + 1) * Math.PI / 5); g.strokeStyle = col; g.lineWidth = 22; g.stroke(); });
  const a = Math.PI + score / 100 * Math.PI;
  g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(a) * (R - 18), cy + Math.sin(a) * (R - 18)); g.strokeStyle = '#fff'; g.lineWidth = 4; g.stroke();
  g.beginPath(); g.arc(cx, cy, 8, 0, 7); g.fillStyle = '#fff'; g.fill();
  g.fillStyle = '#e6edf7'; g.font = 'bold 22px Vazirmatn, Tahoma'; g.textAlign = 'center'; g.fillText(toFa(score) + ' — ' + label, cx, cy + 26 > H ? H - 4 : cy - 40);
  g.font = '12px Vazirmatn, Tahoma'; g.fillStyle = '#8a9bb8'; g.fillText('خرسی', cx - R, cy + 22); g.fillText('گاوی', cx + R, cy + 22);
}
async function computeSignals() {
  const res = [];
  for (const s of SIGNAL_POOL) {
    try {
      const k = await klines(s, '4h', 220); if (k.length < 60) continue;
      const t = techSnapshot(k);
      const live = state.live[s]; if (live) t.price = live.c;
      let L = 0, S = 0;
      if (t.price > t.e50) L += 2; else S += 2;
      if (t.e20 > t.e50) L += 2; else S += 2;
      if (t.price > t.e200) L += 1; else S += 1;
      if (t.rsi >= 45 && t.rsi <= 65) L += 2; if (t.rsi >= 35 && t.rsi <= 55) S += 2;
      if (t.rsi < 35 && t.rsi > t.rsiPrev) L += 1.5; if (t.rsi > 70 && t.rsi < t.rsiPrev) S += 1.5;
      if (t.volRatio > 1.3) { L += 1; S += 1; }
      if (Math.abs(t.price - t.e20) < t.atr) { L += 1.5; S += 1.5; }
      if (t.rsi > 75) L -= 2; if (t.rsi < 25) S -= 2;
      const side = L >= S ? 'long' : 'short', score = Math.max(L, S);
      const a = t.atr, p = t.price, dir = side === 'long' ? 1 : -1;
      const e1 = side === 'long' ? p - 0.5 * a : p, e2 = side === 'long' ? p : p + 0.5 * a, mid = (e1 + e2) / 2;
      res.push({ sym: s.replace('USDT', ''), side, score, price: p, entry: [e1, e2], mid, sl: mid - dir * 1.5 * a, tp: [mid + dir * 1.5 * a, mid + dir * 3 * a, mid + dir * 4.5 * a], rsi: t.rsi, vol: t.volRatio, tf: t.volRatio > 1.3 ? '۴ ساعته (تأیید ۱ ساعته)' : '۴ ساعته' });
    } catch { }
    await sleep(80);
  }
  res.sort((a, b) => b.score - a.score);
  state.signals = res.slice(0, 5); state.signalsAt = Date.now();
  renderSignals();
  if (state.tg.on && state.tg.signal && state.signals.length) {
    const day = new Date().toDateString();
    if (store.get('sigSentDay') !== day) { store.set('sigSentDay', day); sendTelegram('🎯 <b>۵ پیشنهاد امروز هوش‌مانیتور</b>\n' + state.signals.map((x, i) => `${i + 1}. ${x.sym} ${x.side === 'long' ? 'لانگ' : 'شورت'} | ورود ${fmtNum(x.entry[0])}–${fmtNum(x.entry[1])} | SL ${fmtNum(x.sl)} | TP ${x.tp.map(v => fmtNum(v)).join(' / ')}`).join('\n')); }
  }
}
function renderSignals() {
  const tb = $('#signalsTable tbody');
  if (!state.signals.length) { tb.innerHTML = '<tr><td colspan="8" class="muted">داده کافی برای سیگنال در دسترس نیست.</td></tr>'; return; }
  tb.innerHTML = state.signals.map((s, i) => `<tr><td>${toFa(i + 1)}</td><td><b>${s.sym}</b></td><td class="${s.side === 'long' ? 'up' : 'down'}">${s.side === 'long' ? 'لانگ' : 'شورت'}</td>
    <td class="num">${fmtNum(s.entry[0])} – ${fmtNum(s.entry[1])}</td><td class="num down">${fmtNum(s.sl)}</td><td class="num up">${s.tp.map(v => fmtNum(v)).join(' / ')}</td><td>${s.tf}</td>
    <td><button class="btn sm ghost" data-sig="${i}">ماشین‌حساب</button></td></tr>`).join('');
  $$('[data-sig]', tb).forEach(b => b.onclick = () => { fillCalcFromSignal(state.signals[+b.dataset.sig]); showSection('calc'); });
  $('#signalsInfo').textContent = `بر اساس قیمت واقعی ${faDate(state.signalsAt)}، روند EMA، RSI، ATR و حجم کندل‌های ۴ ساعته. ریسک به ریوارد تارگت ۱ = ۱:۱، تارگت ۲ = ۱:۲، تارگت ۳ = ۱:۳.`;
}

/* مدل سناریو هولد تا ۲۰۳۰ */
const CYCLE = [[2026.85, 1.0], [2027.5, 0.95], [2028.3, 1.08], [2029.75, 1.45], [2030.9, 1.02]];
function cycleAt(y) {
  if (y <= CYCLE[0][0]) return CYCLE[0][1];
  for (let i = 1; i < CYCLE.length; i++) if (y <= CYCLE[i][0]) { const [a, va] = CYCLE[i - 1], [b, vb] = CYCLE[i]; return va + (vb - va) * (y - a) / (b - a); }
  return CYCLE[CYCLE.length - 1][1];
}
function projectPrice(coin, tierKey, monthsAhead, scen = 'base') {
  const tier = TIERS[tierKey] || TIERS.mid; let g = tier.cagr[scen];
  const dd = clamp(-(coin.ath_change_percentage || 0) / 100, 0, 0.95);
  if (scen !== 'bear') g += dd * (scen === 'bull' ? 0.35 : 0.2);
  const now = new Date(), yNow = now.getFullYear() + now.getMonth() / 12, yT = yNow + monthsAhead / 12;
  const damp = scen === 'bear' ? 0.4 : scen === 'bull' ? 1.2 : 1;
  const cyc = 1 + (cycleAt(yT) / cycleAt(yNow) - 1) * damp;
  return coin.current_price * Math.pow(1 + g, monthsAhead / 12) * cyc;
}
function horizonCols() {
  const now = new Date(), m = (y, mo = 11) => (y - now.getFullYear()) * 12 + (mo - now.getMonth());
  return [['۳ ماه', 3], ['۶ ماه', 6], ['۹ ماه', 9], ['۱ سال', 12], ['پایان ۲۰۲۷', m(2027)], ['پایان ۲۰۲۸', m(2028)], ['پایان ۲۰۲۹', m(2029)], ['پایان ۲۰۳۰', m(2030)]].filter(c => c[1] > 0);
}
let horizon = 'short', scenario = 'base';
function renderPortfolio() {
  const hz = { short: [3, 'تارگت ۳ ماهه'], mid: [9, 'تارگت ۶ تا ۹ ماهه'], long: [12, 'تارگت ۱۲ ماهه'] }[horizon];
  $('#portfolioTiers').innerHTML = Object.entries(TIERS).map(([key, t]) => {
    const coins = t.ids.map(id => state.byId[id]).filter(Boolean);
    return `<div class="tier"><h4>${t.title} · وزن ${toFa(t.weight)}٪</h4><div class="tier-grid">${coins.map(c => {
      const sp = c.sparkline_in_7d?.price || [c.current_price]; const lo = Math.min(...sp), hi = Math.max(...sp);
      const pos = Math.round((livePriceFor(c) - lo) / (hi - lo || 1) * 100);
      const tgt = projectPrice(c, key, hz[0], 'base');
      return `<div class="pick"><div class="hd"><img src="${c.image}" alt=""><b>${c.symbol.toUpperCase()}</b><small class="muted">${esc(c.name)}</small></div>
        <div class="px">${fmtPrice(livePriceFor(c))}</div>
        <div class="row2"><span>۷ روز</span><span class="${pctCls(c.price_change_percentage_7d_in_currency)} ltr">${fmtPct(c.price_change_percentage_7d_in_currency, 1)}</span></div>
        <div class="row2"><span>از سقف تاریخی</span><span class="down ltr">${fmtPct(c.ath_change_percentage, 0)}</span></div>
        <div class="row2"><span>موقعیت در دامنه ۷ روزه</span><span>${toFa(clamp(pos, 0, 100))}٪</span></div><div class="bar-floor"><i style="width:${clamp(pos, 2, 100)}%"></i></div>
        <div class="tgt">${hz[1]}: <span class="ltr">${fmtPrice(tgt)}</span> <small class="ltr">(${fmtPct((tgt / c.current_price - 1) * 100, 0)})</small></div>
        <div class="why">${ECO[c.id] || ''}</div></div>`;
    }).join('') || '<p class="muted">در حال دریافت…</p>'}</div></div>`;
  }).join('');
  renderHoldTable();
}
function renderHoldTable() {
  const cols = horizonCols();
  $('#holdTable thead').innerHTML = `<tr><th>سطح</th><th>ارز</th><th>قیمت امروز</th>${cols.map(c => `<th>${c[0]}</th>`).join('')}<th>رشد تا ۲۰۳۰</th></tr>`;
  const tierFa = { blue: 'Blue-chip', mid: 'Mid-cap', moon: 'Moonshot' };
  $('#holdTable tbody').innerHTML = Object.entries(TIERS).flatMap(([key, t]) => t.ids.map(id => state.byId[id]).filter(Boolean).map(c => {
    const vals = cols.map(col => projectPrice(c, key, col[1], scenario));
    const last = vals[vals.length - 1];
    return `<tr><td>${tierFa[key]}</td><td><div class="coin"><img src="${c.image}" alt=""><b>${c.symbol.toUpperCase()}</b></div></td><td class="num">${fmtPrice(c.current_price)}</td>
      ${vals.map(v => `<td class="num ${pctCls(v - c.current_price)}">${fmtPrice(v)}</td>`).join('')}<td class="num ${pctCls(last - c.current_price)}">${fmtPct((last / c.current_price - 1) * 100, 0)}</td></tr>`;
  })).join('');
}

/* ---------------- ماشین‌حساب ---------------- */
let calcCur = 'usd';
function fillCoinSelects() {
  const syms = [...new Set([...BINANCE_SYMS.map(s => s.replace('USDT', '')), ...state.markets.map(c => c.symbol.toUpperCase())])];
  ['#cCoin', '#pSym', '#aSym', '#btSym'].forEach(sel => {
    const el = $(sel); if (!el || el.options.length) return;
    const list = sel === '#btSym' ? BINANCE_SYMS.map(s => s.replace('USDT', '')) : syms;
    el.innerHTML = list.map(s => `<option value="${s}">${s}${s === 'PAXG' ? ' (طلا)' : ''}</option>`).join('');
  });
}
function calcInputs() {
  const n = id => parseFloat(toEn($('#' + id).value)) || 0;
  return { coin: $('#cCoin').value, mode: $('#cMode').value, capital: n('cCapital'), risk: n('cRisk'), entry: n('cEntry'), stop: n('cStop'), exit: n('cExit'), lev: $('#cMode').value === 'spot' ? 1 : Math.max(1, n('cLev')), fee: n('cFee') / 100, qty: n('cQty') };
}
function calcCompute(i = calcInputs()) {
  const r = { ...i, warns: [] };
  if (!i.entry) return null;
  const dir = i.mode === 'short' ? -1 : 1;
  const riskUsd = i.capital * i.risk / 100;
  const unitRisk = i.stop ? Math.abs(i.entry - i.stop) * i.lev : 0;
  let qty = i.qty;
  if (!qty) {
    qty = unitRisk ? riskUsd / unitRisk : i.capital * 0.1 / i.entry;
    const maxQty = i.capital * 0.15 / i.entry;
    if (qty > maxQty) { qty = maxQty; r.warns.push('مقدار با سقف ۱۵٪ سرمایه در یک ترید محدود شد.'); }
  }
  r.qtyCalc = qty; r.margin = qty * i.entry; r.position = r.margin * i.lev;
  const feeIn = r.position * i.fee;
  const pnlAt = px => dir * (px - i.entry) * qty * i.lev - feeIn - qty * i.lev * px * i.fee;
  if (i.exit) { r.pnl = pnlAt(i.exit); r.pct = r.pnl / r.margin * 100; r.movePct = (i.exit / i.entry - 1) * 100 * dir; }
  if (i.stop) { r.loss = pnlAt(i.stop); r.lossPct = r.loss / i.capital * 100; }
  if (i.stop && i.exit) r.rr = Math.abs(i.exit - i.entry) / Math.abs(i.entry - i.stop);
  if (i.mode !== 'spot') {
    r.liq = i.mode === 'long' ? i.entry * (1 - 1 / i.lev + 0.005) : i.entry * (1 + 1 / i.lev - 0.005);
    if (i.stop && ((i.mode === 'long' && i.stop <= r.liq) || (i.mode === 'short' && i.stop >= r.liq))) r.warns.push('⚠️ استاپ‌لاس بعد از قیمت لیکوییدیشن است؛ اهرم را کم کنید.');
  }
  if (i.stop && ((dir === 1 && i.stop >= i.entry) || (dir === -1 && i.stop <= i.entry))) r.warns.push('استاپ‌لاس در سمت اشتباه قیمت ورود است.');
  if (r.margin > i.capital * 0.15 + 1e-9) r.warns.push('بیش از ۱۵٪ سرمایه وارد این ترید شده است.');
  if (r.lossPct && Math.abs(r.lossPct) > 2) r.warns.push(`ریسک این ترید ${Math.abs(r.lossPct).toFixed(1)}٪ سرمایه است (توصیه: ۱ تا ۲٪).`);
  if (r.rr && r.rr < 1.5) r.warns.push('ریوارد به ریسک کمتر از ۱٫۵ است.');
  r.fees = feeIn + qty * i.lev * (i.exit || i.entry) * i.fee;
  return r;
}
function renderCalc() {
  const r = calcCompute(), box = $('#calcResult');
  if (!r) { box.innerHTML = '<p class="muted">قیمت ورود را وارد کنید یا دکمه «دریافت اطلاعات ترید خودکار» را بزنید.</p>'; return; }
  const m = v => calcCur === 'irt' ? fmtIrt(v * state.rate) : fmtUsd(v, 2);
  box.innerHTML = `<div class="big"><small>سود / زیان در خروج</small><b class="${pctCls(r.pnl)}">${r.pnl != null ? m(r.pnl) : '—'}</b><div class="${pctCls(r.pct)} ltr">${r.pct != null ? fmtPct(r.pct) + ' روی مارجین' : ''}</div></div>
    <div><small>مقدار خرید ${r.coin}</small><b>${fmtNum(r.qtyCalc, 6)}</b></div><div><small>مارجین / مبلغ ورود</small><b>${m(r.margin)}</b></div>
    <div><small>ارزش پوزیشن (با اهرم)</small><b>${m(r.position)}</b></div><div><small>ریوارد به ریسک</small><b>${r.rr ? '1 : ' + r.rr.toFixed(2) : '—'}</b></div>
    <div><small>زیان در استاپ</small><b class="down">${r.loss != null ? m(r.loss) : '—'}</b></div><div><small>درصد ریسک از کل سرمایه</small><b>${r.lossPct != null ? Math.abs(r.lossPct).toFixed(2) + '%' : '—'}</b></div>
    <div><small>قیمت تقریبی لیکوییدیشن</small><b class="down">${r.liq ? fmtUsd(r.liq) : 'ندارد (اسپات)'}</b></div><div><small>کارمزد کل</small><b>${m(r.fees)}</b></div>
    <div><small>حرکت قیمت تا تارگت</small><b>${r.movePct != null ? fmtPct(r.movePct) : '—'}</b></div><div><small>معادل تومانی سود</small><b>${r.pnl != null ? fmtIrt(r.pnl * state.rate) : '—'}</b></div>
    ${r.warns.map(w => `<div class="warn">${w}</div>`).join('')}`;
}
function fillCalcFromSignal(s) {
  $('#cCoin').value = s.sym; if ($('#cCoin').value !== s.sym) { const o = new Option(s.sym, s.sym); $('#cCoin').add(o); $('#cCoin').value = s.sym; }
  $('#cMode').value = s.side === 'long' ? ($('#cMode').value === 'long' ? 'long' : 'spot') : 'short';
  if (s.side === 'short' && +$('#cLev').value < 2) $('#cLev').value = 3;
  $('#cEntry').value = +s.mid.toPrecision(6); $('#cStop').value = +s.sl.toPrecision(6); $('#cExit').value = +s.tp[1].toPrecision(6); $('#cQty').value = '';
  renderCalc(); toast(`اطلاعات ترید ${s.sym} از سیگنال‌های امروز وارد شد`, 'ok');
}
async function calcAuto() {
  const sym = $('#cCoin').value;
  let s = state.signals.find(x => x.sym === sym);
  if (!s) {
    try {
      const k = await klines(sym + 'USDT', '4h', 120), t = techSnapshot(k), p = priceOf(sym) || t.price;
      const side = t.price >= t.e50 ? 'long' : 'short', d = side === 'long' ? 1 : -1;
      s = { sym, side, mid: p, sl: p - d * 1.5 * t.atr, tp: [p + d * 1.5 * t.atr, p + d * 3 * t.atr, p + d * 4.5 * t.atr] };
    } catch { const p = priceOf(sym); if (!p) return toast('قیمت این ارز در دسترس نیست', 'err'); s = { sym, side: 'long', mid: p, sl: p * 0.95, tp: [p * 1.05, p * 1.1, p * 1.15] }; }
  }
  fillCalcFromSignal(s);
}

/* ---------------- مشاور هوش مصنوعی ---------------- */
function normFa(t) { return toEn(t).replace(/ي/g, 'ی').replace(/ك/g, 'ک').replace(/\u200c/g, ' ').toLowerCase(); }
function detectCoin(t) {
  for (const [sym, names] of Object.entries(FA_NAMES)) for (const n of names) {
    if (/^[a-z]+$/.test(n) ? new RegExp('(^|[^a-z])' + n + '([^a-z]|$)').test(t) : t.includes(n.replace(/\u200c/g, ' '))) return sym;
  }
  const tok = (t.match(/[a-z]{2,10}/g) || []).find(w => state.bySym[w]); return tok ? tok.toUpperCase() : null;
}
function detectAmount(t) {
  const m = t.match(/(\d[\d,\.]*)\s*(میلیارد|میلیون|هزار|k|m)?\s*(دلار|تومان|تومن|ریال|usd|usdt|\$)?/);
  if (!m) return null;
  let v = parseFloat(m[1].replace(/,/g, '')); if (!v || v < 10 && !m[2]) return null;
  const mul = { 'میلیارد': 1e9, 'میلیون': 1e6, 'هزار': 1e3, k: 1e3, m: 1e6 }[m[2]] || 1; v *= mul;
  const cur = m[3] || (/تومان|تومن/.test(t) ? 'تومان' : 'دلار');
  if (/تومان|تومن/.test(cur)) return { usd: v / state.rate, raw: v, cur: 'تومان' };
  if (cur === 'ریال') return { usd: v / 10 / state.rate, raw: v, cur: 'ریال' };
  return { usd: v, raw: v, cur: 'دلار' };
}
function addMsg(html, who = 'bot') { const d = document.createElement('div'); d.className = 'msg ' + who; d.innerHTML = html; $('#chatLog').appendChild(d); $('#chatLog').scrollTop = 1e9; return d; }
async function analyzeCoin(sym) {
  const m = state.bySym[sym.toLowerCase()];
  let html = `<b>📊 تحلیل ${sym}${m ? ' (' + esc(m.name) + ')' : ''}</b><br>`;
  const p = priceOf(sym);
  html += `قیمت لحظه‌ای: <b class="ltr">${fmtUsd(p)}</b> ≈ <b class="ltr">${fmtIrt(p * state.rate)}</b><br>`;
  if (m) html += `تغییر ۲۴ ساعت: <span class="${pctCls(m.price_change_percentage_24h)} ltr">${fmtPct(m.price_change_percentage_24h)}</span> · ۷ روز: <span class="${pctCls(m.price_change_percentage_7d_in_currency)} ltr">${fmtPct(m.price_change_percentage_7d_in_currency)}</span> · فاصله از سقف تاریخی: <span class="down ltr">${fmtPct(m.ath_change_percentage, 0)}</span><br>`;
  try {
    const [d, h4] = await Promise.all([klines(sym + 'USDT', '1d', 250), klines(sym + 'USDT', '4h', 200)]);
    const td = techSnapshot(d), t4 = techSnapshot(h4);
    const trendD = td.price > td.e200 ? (td.e50 > td.e200 ? 'صعودی قوی (بالای EMA50 و EMA200)' : 'صعودی ضعیف') : (td.e50 < td.e200 ? 'نزولی (زیر EMA200 با تقاطع مرگ)' : 'زیر EMA200، در حال اصلاح');
    const trend4 = t4.price > t4.e50 ? 'صعودی' : 'نزولی';
    html += `روند روزانه: <b>${trendD}</b> · روند ۴ ساعته: <b class="${trend4 === 'صعودی' ? 'up' : 'down'}">${trend4}</b><br>`;
    html += `RSI روزانه ${td.rsi.toFixed(1)} ${td.rsi > 70 ? '(اشباع خرید)' : td.rsi < 30 ? '(اشباع فروش – احتمال برگشت)' : ''} · RSI چهارساعته ${t4.rsi.toFixed(1)}<br>`;
    html += `حمایت‌های مهم: <b class="ltr">${fmtNum(t4.lo30)}</b> و <b class="ltr">${fmtNum(td.lo30)}</b> · مقاومت‌ها: <b class="ltr">${fmtNum(t4.hi30)}</b> و <b class="ltr">${fmtNum(td.hi30)}</b><br>`;
    const bull = (td.price > td.e200) + (t4.price > t4.e50) + (td.rsi > 50) + (t4.rsi > 50);
    const verdict = bull >= 3 ? '🟢 جمع‌بندی: ساختار مثبت است؛ ورود پله‌ای در اصلاح‌ها به سمت حمایت ۴ ساعته منطقی‌تر از خرید در سقف است.' : bull <= 1 ? '🔴 جمع‌بندی: ساختار منفی است؛ صبر برای تثبیت بالای مقاومت یا خرید پله‌ای فقط در حمایت‌های روزانه با حجم کم.' : '🟡 جمع‌بندی: بازار در حالت رنج است؛ معامله بین حمایت و مقاومت با استاپ نزدیک.';
    html += verdict + `<br>ATR روزانه: ${fmtNum(td.atr)} — استاپ پیشنهادی حدود ${fmtNum(td.price - 1.5 * td.atr)} برای لانگ.`;
  } catch { html += '<span class="muted">داده کندل این ارز در Binance موجود نیست؛ تحلیل فقط بر اساس CoinGecko است.</span>'; }
  return html + `<br><small class="muted">این تحلیل خودکار است و توصیه مالی نیست.</small>`;
}
function moneyPlan(a) {
  const usd = a.usd;
  let html = `<b>💼 برنامه مدیریت سرمایه برای ${fmtNum(a.raw, 0)} ${a.cur}</b> (≈ <span class="ltr">${fmtUsd(usd, 0)}</span>)<br>`;
  html += `• ریسک هر معامله (۱ تا ۲٪): <b class="ltr">${fmtUsd(usd * 0.01, 0)} – ${fmtUsd(usd * 0.02, 0)}</b> ≈ ${fmtIrt(usd * 0.01 * state.rate)} تا ${fmtIrt(usd * 0.02 * state.rate)}<br>`;
  html += `• حداکثر ورود به یک ترید (۱۰ تا ۱۵٪): <b class="ltr">${fmtUsd(usd * 0.1, 0)} – ${fmtUsd(usd * 0.15, 0)}</b><br>• ذخیره نقد (تتر) پیشنهادی برای خرید در ریزش: ۱۰ تا ۲۰٪<br>`;
  html += '<table><tr><th>سطح</th><th>وزن</th><th>مبلغ دلاری</th><th>مبلغ تومانی</th><th>ارزها</th></tr>';
  Object.values(TIERS).forEach(t => { const v = usd * t.weight / 100; html += `<tr><td>${t.title.split('—')[0]}</td><td>${toFa(t.weight)}٪</td><td class="ltr">${fmtUsd(v, 0)}</td><td>${fmtIrt(v * state.rate)}</td><td>${t.ids.map(id => (state.byId[id]?.symbol || id).toUpperCase()).join('، ')}</td></tr>`; });
  html += '</table>هر سطح را مساوی بین ۵ ارز آن تقسیم کنید و خرید را در ۳ پله (۴۰٪، ۳۰٪، ۳۰٪) انجام دهید.';
  if (state.regime) html += `<br>رژیم فعلی بازار: <b>${state.regime.label}</b> — ${state.regime.score < 45 ? 'در بازار خرسی سهم Blue-chip و نقد را بالاتر نگه دارید.' : 'در بازار گاوی می‌توانید سهم Mid-cap را کمی بیشتر کنید.'}`;
  return html;
}
function forecastFor(sym) {
  const m = state.bySym[sym.toLowerCase()]; if (!m) return `اطلاعات ${sym} در دسترس نیست.`;
  const key = Object.keys(TIERS).find(k => TIERS[k].ids.includes(m.id)) || (m.market_cap_rank <= 10 ? 'blue' : m.market_cap_rank <= 40 ? 'mid' : 'moon');
  const cols = horizonCols();
  let html = `<b>🔮 سناریوی ${sym} تا ۲۰۳۰</b> (قیمت امروز <span class="ltr">${fmtUsd(m.current_price)}</span>)<br><table><tr><th>بازه</th><th>بدبینانه</th><th>پایه</th><th>خوش‌بینانه</th></tr>`;
  cols.forEach(c => { html += `<tr><td>${c[0]}</td>${['bear', 'base', 'bull'].map(s => `<td class="ltr">${fmtUsd(projectPrice(m, key, c[1], s))}</td>`).join('')}</tr>`; });
  return html + `</table>مدل بر اساس رشد مرکب سطح ${key === 'blue' ? 'Blue-chip' : key === 'mid' ? 'Mid-cap' : 'Moonshot'}، فاصله از سقف تاریخی و چرخه هاوینگ ۲۰۲۸ ساخته شده و قطعی نیست.`;
}
function regimeText() {
  const r = state.regime; if (!r) return 'داده رژیم بازار هنوز آماده نیست.';
  return `<b>🧭 وضعیت بازار: ${r.label} (امتیاز ${toFa(r.score)} از ۱۰۰)</b><br>` + r.factors.map(f => `• ${f[0]}: <b class="${pctCls(f[1])}">${f[2]}</b>`).join('<br>') +
    `<br>${r.score >= 55 ? 'روند غالب صعودی است؛ خرید در اصلاح‌ها و هولد Blue-chipها منطقی است.' : r.score <= 45 ? 'روند غالب نزولی است؛ حجم معاملات را کم کنید، نقد نگه دارید و خرید پله‌ای فقط در حمایت‌های اصلی.' : 'بازار بدون روند مشخص است؛ معاملات رنج با حد ضرر نزدیک.'}`;
}
function signalsText() {
  if (!state.signals.length) return 'سیگنال‌ها هنوز محاسبه نشده‌اند.';
  return '<b>🎯 ۵ پیشنهاد امروز</b><table><tr><th>نماد</th><th>جهت</th><th>ورود</th><th>استاپ</th><th>تارگت‌ها</th></tr>' + state.signals.map(s => `<tr><td>${s.sym}</td><td class="${s.side === 'long' ? 'up' : 'down'}">${s.side === 'long' ? 'لانگ' : 'شورت'}</td><td class="ltr">${fmtNum(s.entry[0])}–${fmtNum(s.entry[1])}</td><td class="ltr">${fmtNum(s.sl)}</td><td class="ltr">${s.tp.map(v => fmtNum(v)).join(' / ')}</td></tr>`).join('') + '</table>ریسک هر پوزیشن ۱ تا ۲٪ سرمایه.';
}
async function localAnswer(q) {
  const t = normFa(q), coin = detectCoin(t), amt = detectAmount(t);
  if (/سیگنال|پیشنهاد امروز|ترید امروز|signal/.test(t)) return signalsText();
  if (/گاوی|خرسی|رژیم|وضعیت بازار|bull|bear|روند کلی/.test(t)) return regimeText();
  if (amt && (/سرمایه|سبد|چطور|بچین|تقسیم|مدیریت|بخرم|پورتفو|سرمایه گذاری/.test(t) || !coin)) return moneyPlan(amt);
  if (/نفت|oil|برنت/.test(t)) return '🛢️ برای نفت WTI و برنت از بخش چارت گزینه «نفت» را انتخاب کنید (چارت TradingView با اندیکاتورها). تقویم اقتصادی (گزارش ذخایر EIA و تصمیمات اوپک) هم در داشبورد هست.';
  if (/دلار|تومان|تومن/.test(t) && /نرخ|قیمت/.test(t) && !coin) return `💵 نرخ فعلی دلار (تتر): <b>${fmtNum(state.rate, 0)} تومان</b> ${state.rateLive ? '(نوبیتکس، لحظه‌ای)' : '(دستی)'}.`;
  if (coin && /پیش بینی|پیشبینی|پیش‌بینی|آینده|203|202|سال|هولد|نگه/.test(t)) return forecastFor(coin);
  if (coin) return await analyzeCoin(coin);
  if (/مدیریت سرمایه|ریسک|استاپ|حد ضرر/.test(t)) return '<b>📐 قانون مدیریت سرمایه</b><br>• در هر پوزیشن فقط ۱ تا ۲٪ کل سرمایه ریسک کنید.<br>• حداکثر ۱۰ تا ۱۵٪ سرمایه وارد یک ترید شود.<br>• ریوارد به ریسک حداقل ۱:۲.<br>• بعد از ۳ ضرر پشت سر هم آن روز معامله نکنید.<br>• مبلغ سرمایه را بنویسید تا برنامه دقیق بدهم؛ مثلاً «با ۲۰۰۰ دلار».';
  return 'می‌توانم این‌ها را جواب بدهم:<br>• تحلیل هر ارز: «اتریوم را تحلیل کن»<br>• مدیریت سرمایه با مبلغ: «با ۵۰ میلیون تومان سبد بچین»<br>• پیش‌بینی چندساله: «پیش‌بینی سولانا تا ۲۰۳۰»<br>• تشخیص بازار گاوی یا خرسی<br>• سیگنال‌های امروز و نرخ دلار';
}
async function openAIAnswer(q) {
  const ctx = {
    rate_toman: state.rate, regime: state.regime && { score: state.regime.score, label: state.regime.label },
    prices: Object.fromEntries(state.markets.slice(0, 20).map(c => [c.symbol.toUpperCase(), { usd: livePriceFor(c), ch24: c.price_change_percentage_24h, ath_chg: c.ath_change_percentage }])),
    fear_greed: state.fng && state.fng[0].value, btc_dominance: state.global && state.global.market_cap_percentage.btc, signals: state.signals
  };
  const d = await getJSON('https://api.openai.com/v1/chat/completions', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + state.keys.openai },
    body: JSON.stringify({ model: state.keys.model || 'gpt-4o-mini', temperature: 0.4, messages: [
      { role: 'system', content: 'تو مشاور فارسی بازارهای مالی در وب‌سایت هوش‌مانیتور پرو هستی. کوتاه، دقیق و با عدد جواب بده. قانون مدیریت سرمایه: ریسک ۱ تا ۲٪ در هر پوزیشن و حداکثر ۱۰ تا ۱۵٪ سرمایه در یک ترید. همیشه یادآوری کن که توصیه مالی نیست. داده لحظه‌ای بازار: ' + JSON.stringify(ctx) },
      { role: 'user', content: q }] })
  }, 30000);
  return esc(d.choices[0].message.content).replace(/\n/g, '<br>');
}
async function ask(q) {
  q = q.trim(); if (!q) return;
  addMsg(esc(q), 'user'); const wait = addMsg('در حال تحلیل…', 'bot typing');
  let ans;
  try { ans = state.keys.openai ? await openAIAnswer(q) : await localAnswer(q); }
  catch (e) { ans = (state.keys.openai ? '<small class="muted">اتصال به OpenAI ناموفق بود؛ پاسخ تحلیل‌گر داخلی:</small><br>' : '') + await localAnswer(q); }
  wait.classList.remove('typing'); wait.innerHTML = ans; $('#chatLog').scrollTop = 1e9;
}

/* ---------------- ترید آزمایشی + وب‌هوک + متاتریدر ---------------- */
function savePaper() { store.set('paper', state.paper); }
function openPaper({ sym, side, amount, lev = 1, sl = 0, tp = 0, src = 'دستی' }) {
  sym = sym.toUpperCase().replace(/USDT$/, ''); const price = priceOf(sym);
  if (!price) return toast('قیمت لحظه‌ای ' + sym + ' در دسترس نیست', 'err');
  amount = +amount; lev = clamp(+lev || 1, 1, 50);
  if (!(amount > 0)) return toast('مبلغ نامعتبر است', 'err');
  if (amount > state.paper.balance) return toast('موجودی حساب آزمایشی کافی نیست', 'err');
  const fee = amount * lev * 0.001;
  state.paper.balance -= amount + fee;
  state.paper.positions.push({ id: Date.now() + Math.random(), sym, side, entry: price, qty: amount * lev / price, lev, margin: amount, sl: +sl || 0, tp: +tp || 0, t: Date.now(), src, fee });
  savePaper(); renderPaper(); toast(`سفارش آزمایشی ${side === 'long' ? 'خرید' : 'فروش'} ${sym} با قیمت ${fmtUsd(price)} اجرا شد`, 'ok');
}
function posPnl(p, cur) { return (p.side === 'long' ? 1 : -1) * (cur - p.entry) * p.qty; }
function closePaper(id, reason = 'بستن دستی') {
  const i = state.paper.positions.findIndex(p => p.id === id); if (i < 0) return;
  const p = state.paper.positions[i], cur = priceOf(p.sym) || p.entry;
  const fee = p.qty * cur * 0.001, pnl = Math.max(posPnl(p, cur), -p.margin) - fee - p.fee;
  state.paper.balance += Math.max(0, p.margin + posPnl(p, cur) - fee);
  state.paper.positions.splice(i, 1);
  state.paper.history.unshift({ t: Date.now(), sym: p.sym, side: p.side, entry: p.entry, exit: cur, pnl, src: p.src + ' · ' + reason, qty: p.qty, lev: p.lev });
  state.paper.history = state.paper.history.slice(0, 200);
  savePaper(); renderPaper(); toast(`پوزیشن ${p.sym} بسته شد: ${fmtUsd(pnl, 2)}`, pnl >= 0 ? 'ok' : 'err');
}
function updatePaperPnL() {
  let eq = state.paper.balance;
  for (const p of [...state.paper.positions]) {
    const cur = priceOf(p.sym); if (!cur) { eq += p.margin; continue; }
    const pnl = posPnl(p, cur);
    if (p.sl && ((p.side === 'long' && cur <= p.sl) || (p.side === 'short' && cur >= p.sl))) { closePaper(p.id, 'استاپ‌لاس'); continue; }
    if (p.tp && ((p.side === 'long' && cur >= p.tp) || (p.side === 'short' && cur <= p.tp))) { closePaper(p.id, 'تیک‌پرافیت'); continue; }
    if (pnl <= -p.margin * 0.95) { closePaper(p.id, 'لیکوییدیشن'); continue; }
    eq += p.margin + pnl;
    const row = document.querySelector(`#posTable tr[data-id="${p.id}"]`);
    if (row) { row.children[3].textContent = fmtNum(cur); row.children[7].innerHTML = `<span class="${pctCls(pnl)}">${fmtUsd(pnl, 2)} (${fmtPct(pnl / p.margin * 100)})</span>`; }
  }
  state.paper.equity = eq;
  if ($('#paperEquity')) $('#paperEquity').textContent = 'ارزش کل حساب: ' + fmtUsd(eq, 2);
}
function renderPaper() {
  $('#paperBal').textContent = 'موجودی آزاد: ' + fmtUsd(state.paper.balance, 2);
  $('#posTable tbody').innerHTML = state.paper.positions.length ? state.paper.positions.map(p => `<tr data-id="${p.id}"><td><b>${p.sym}</b></td><td class="${p.side === 'long' ? 'up' : 'down'}">${p.side === 'long' ? 'لانگ' : 'شورت'}</td><td class="num">${fmtNum(p.entry)}</td><td class="num">—</td><td class="num">${fmtNum(p.qty, 6)}</td><td>×${toFa(p.lev)}</td><td class="num">${p.sl ? fmtNum(p.sl) : '—'} / ${p.tp ? fmtNum(p.tp) : '—'}</td><td class="num">—</td><td><button class="btn sm ghost" data-close="${p.id}">بستن</button></td></tr>`).join('') : '<tr><td colspan="9" class="muted">پوزیشن بازی ندارید.</td></tr>';
  $$('[data-close]').forEach(b => b.onclick = () => closePaper(+b.dataset.close));
  $('#histTable tbody').innerHTML = state.paper.history.slice(0, 50).map(h => `<tr><td>${faDate(h.t)}</td><td>${h.sym}</td><td class="${h.side === 'long' ? 'up' : 'down'}">${h.side === 'long' ? 'لانگ' : 'شورت'}</td><td class="num">${fmtNum(h.entry)}</td><td class="num">${fmtNum(h.exit)}</td><td class="num ${pctCls(h.pnl)}">${fmtUsd(h.pnl, 2)}</td><td>${esc(h.src)}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">تاریخچه‌ای نیست.</td></tr>';
  updatePaperPnL();
}
function webhookTemplate() {
  return JSON.stringify({ secret: 'HM-' + (store.get('whSecret') || 'xxxx'), symbol: '{{ticker}}', side: '{{strategy.order.action}}', price: '{{close}}', amount: 100, leverage: 2, sl: 0, tp: 0, time: '{{timenow}}' }, null, 2);
}
function runWebhook(text) {
  let d; try { d = JSON.parse(text); } catch { return toast('JSON نامعتبر است', 'err'); }
  const sym = String(d.symbol || d.ticker || '').toUpperCase().replace(/^.*:/, '').replace(/(USDT|USD|PERP|\.P)$/, '');
  const act = String(d.side || d.action || '').toLowerCase();
  if (!sym || !act) return toast('فیلدهای symbol و side الزامی هستند', 'err');
  if (/close|exit/.test(act)) { state.paper.positions.filter(p => p.sym === sym).forEach(p => closePaper(p.id, 'وب‌هوک')); return; }
  const side = /sell|short/.test(act) ? 'short' : 'long';
  openPaper({ sym, side, amount: d.amount || 100, lev: d.leverage || 1, sl: d.sl, tp: d.tp, src: 'وب‌هوک TradingView' });
  pushAlert('signal', `وب‌هوک اجرا شد: ${sym} ${side === 'long' ? 'خرید' : 'فروش'}`, 'سفارش در حساب آزمایشی ثبت شد', { silent: true });
}
function mqlEA(v5) {
  const sym = $('#mtSym').value.trim() || 'XAUUSD', side = $('#mtSide').value, risk = +$('#mtRisk').value || 1, sl = +$('#mtSL').value || 300, tp = +$('#mtTP').value || 600;
  const head = `//+------------------------------------------------------------------+
//| HooshMonitor Pro – Risk Based Order EA (${v5 ? 'MT5' : 'MT4'})                    |
//| ساخته شده توسط هوش‌مانیتور پرو — ابتدا روی حساب دمو تست کنید          |
//+------------------------------------------------------------------+
#property strict
input string InpSymbol   = "${sym}";
input bool   InpBuy      = ${side === 'buy' ? 'true' : 'false'};
input double InpRiskPct  = ${risk};     // درصد ریسک از موجودی
input int    InpSLPoints = ${sl};       // استاپ به پوینت
input int    InpTPPoints = ${tp};       // تارگت به پوینت
input int    InpMagic    = 777001;
bool done=false;
double CalcLots(){
   double tickVal = SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize= SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE);
   double point   = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   double riskMoney = AccountInfoDouble(ACCOUNT_BALANCE) * InpRiskPct / 100.0;
   double lossPerLot = InpSLPoints * point / tickSize * tickVal;
   double lots = lossPerLot > 0 ? riskMoney / lossPerLot : 0.01;
   double step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   double mn = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN), mx = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   lots = MathFloor(lots / step) * step;
   if(lots < mn){ Print("HooshMonitor: risk budget below minimum volume, order skipped"); return 0; }
   return MathMin(mx, lots);
}
`;
  const body5 = `#include <Trade/Trade.mqh>
CTrade trade;
int OnInit(){ trade.SetExpertMagicNumber(InpMagic); return(INIT_SUCCEEDED); }
bool HasOpen(){
   for(int i = PositionsTotal() - 1; i >= 0; i--){ ulong tk = PositionGetTicket(i); if(tk > 0 && PositionGetInteger(POSITION_MAGIC) == InpMagic && PositionGetString(POSITION_SYMBOL) == InpSymbol) return true; }
   return false;
}
void OnTick(){
   if(done) return;
   if(HasOpen()){ done = true; return; }
   double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   double ask = SymbolInfoDouble(InpSymbol, SYMBOL_ASK), bid = SymbolInfoDouble(InpSymbol, SYMBOL_BID);
   double lots = CalcLots();
   if(lots <= 0){ done = true; return; }
   bool ok = InpBuy ? trade.Buy(lots, InpSymbol, ask, ask - InpSLPoints*point, ask + InpTPPoints*point, "HooshMonitor")
                    : trade.Sell(lots, InpSymbol, bid, bid + InpSLPoints*point, bid - InpTPPoints*point, "HooshMonitor");
   if(ok){ done = true; Print("HooshMonitor order sent, lots=", lots); }
   else Print("HooshMonitor order failed: ", GetLastError());
}
`;
  const body4 = `int OnInit(){ return(INIT_SUCCEEDED); }
bool HasOpen(){
   for(int i = OrdersTotal() - 1; i >= 0; i--) if(OrderSelect(i, SELECT_BY_POS, MODE_TRADES) && OrderMagicNumber() == InpMagic && OrderSymbol() == InpSymbol) return true;
   return false;
}
void OnTick(){
   if(done) return;
   if(HasOpen()){ done = true; return; }
   double point = MarketInfo(InpSymbol, MODE_POINT);
   double ask = MarketInfo(InpSymbol, MODE_ASK), bid = MarketInfo(InpSymbol, MODE_BID);
   double lots = CalcLots();
   if(lots <= 0){ done = true; return; }
   int t = InpBuy ? OrderSend(InpSymbol, OP_BUY, lots, ask, 30, ask - InpSLPoints*point, ask + InpTPPoints*point, "HooshMonitor", InpMagic, 0, clrGreen)
                  : OrderSend(InpSymbol, OP_SELL, lots, bid, 30, bid + InpSLPoints*point, bid - InpTPPoints*point, "HooshMonitor", InpMagic, 0, clrRed);
   if(t > 0){ done = true; Print("HooshMonitor order sent #", t); }
   else Print("HooshMonitor order failed: ", GetLastError());
}
`;
  let src = head + (v5 ? body5 : body4);
  if (!v5) src = src.replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_TRADE_TICK_VALUE\)/, 'MarketInfo(InpSymbol, MODE_TICKVALUE)').replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_TRADE_TICK_SIZE\)/, 'MarketInfo(InpSymbol, MODE_TICKSIZE)')
    .replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_POINT\)/, 'MarketInfo(InpSymbol, MODE_POINT)').replace(/AccountInfoDouble\(ACCOUNT_BALANCE\)/, 'AccountBalance()')
    .replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_VOLUME_STEP\)/, 'MarketInfo(InpSymbol, MODE_LOTSTEP)').replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_VOLUME_MIN\)/, 'MarketInfo(InpSymbol, MODE_MINLOT)').replace(/SymbolInfoDouble\(InpSymbol, SYMBOL_VOLUME_MAX\)/, 'MarketInfo(InpSymbol, MODE_MAXLOT)');
  download(`HooshMonitor_${sym}.${v5 ? 'mq5' : 'mq4'}`, src);
}

/* ---------------- ژورنال تصویری (IndexedDB) ---------------- */
const idb = {
  db: null,
  open() { return this.db ? Promise.resolve(this.db) : new Promise((res, rej) => { const r = indexedDB.open('hooshmonitor', 1); r.onupgradeneeded = () => r.result.createObjectStore('journal', { keyPath: 'id' }); r.onsuccess = () => res(this.db = r.result); r.onerror = () => rej(r.error); }); },
  async tx(mode, fn) { const db = await this.open(); return new Promise((res, rej) => { const t = db.transaction('journal', mode), s = t.objectStore('journal'), q = fn(s); t.oncomplete = () => res(q && q.result); t.onerror = () => rej(t.error); }); },
  all() { return this.tx('readonly', s => s.getAll()); }, put(v) { return this.tx('readwrite', s => s.put(v)); }, del(id) { return this.tx('readwrite', s => s.delete(id)); }, clear() { return this.tx('readwrite', s => s.clear()); }
};
function compressImage(file, max = 1100) {
  return new Promise(res => {
    if (!file) return res(null);
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => { const s = Math.min(1, max / Math.max(img.width, img.height)); const c = document.createElement('canvas'); c.width = img.width * s; c.height = img.height * s; c.getContext('2d').drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url); res(c.toDataURL('image/jpeg', 0.78)); };
    img.onerror = () => res(null); img.src = url;
  });
}
function tradePnl(j) {
  if (!j.exit) return null;
  return (j.side === 'short' ? -1 : 1) * (j.exit - j.entry) * j.qty * (j.lev || 1) - (j.fee || 0);
}
const safeImg = v => typeof v === 'string' && /^data:image\/(png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=]+$/.test(v) ? v : '';
let journal = [];
async function loadJournal() { let db = []; try { db = await idb.all(); } catch { } const ids = new Set(db.map(j => j.id)); journal = db.concat(store.get('journalFallback', []).filter(j => !ids.has(j.id))).sort((a, b) => (b.date || '').localeCompare(a.date || '')); renderJournal(); }
async function saveJournalEntry(entry) { try { await idb.put(entry); } catch { const f = store.get('journalFallback', []); f.push(entry); store.set('journalFallback', f); if (!store.get('journalFallback', []).some(j => j.id === entry.id)) { toast('ذخیره ژورنال ناموفق بود (حافظه مرورگر)', 'err'); return false; } } return true; }
async function addJournal(e) {
  const n = id => parseFloat(toEn($('#' + id).value)) || 0;
  const entry = { id: Date.now(), date: $('#jDate').value, sym: $('#jSym').value.toUpperCase().trim(), side: $('#jSide').value, lev: n('jLev') || 1, entry: n('jEntry'), exit: n('jExit') || null, qty: n('jQty'), fee: n('jFee'), sl: n('jSL') || null, tp: n('jTP') || null, emotion: $('#jEmotion').value, rate: +$('#jRate').value, reason: $('#jReason').value.trim(), lesson: $('#jLesson').value.trim(),
    imgBefore: await compressImage($('#jImgBefore').files[0]), imgAfter: await compressImage($('#jImgAfter').files[0]) };
  if (!(await saveJournalEntry(entry))) return;
  $('#jForm').reset(); setNow(); toast('ترید در ژورنال ثبت شد 📒', 'ok'); loadJournal();
}
function setNow() { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); $('#jDate').value = d.toISOString().slice(0, 16); }
function journalStats(list) {
  const closed = list.filter(j => j.exit), pnls = closed.map(tradePnl);
  const wins = pnls.filter(p => p > 0), losses = pnls.filter(p => p <= 0);
  const gw = wins.reduce((a, b) => a + b, 0), gl = -losses.reduce((a, b) => a + b, 0);
  return { n: list.length, closed: closed.length, win: closed.length ? wins.length / closed.length * 100 : 0, total: pnls.reduce((a, b) => a + b, 0), avg: pnls.length ? pnls.reduce((a, b) => a + b, 0) / pnls.length : 0, pf: gl ? gw / gl : (gw ? Infinity : 0), rate: list.length ? list.reduce((a, j) => a + (j.rate || 0), 0) / list.length : 0 };
}
function renderJournal() {
  const s = journalStats(journal);
  $('#jStats').innerHTML = `<div><small>تعداد ترید</small><b>${toFa(s.n)}</b></div><div><small>وین‌ریت</small><b>${s.win.toFixed(1)}%</b></div><div><small>سود/زیان کل</small><b class="${pctCls(s.total)}">${fmtUsd(s.total, 2)}</b></div>
    <div><small>میانگین هر ترید</small><b class="${pctCls(s.avg)}">${fmtUsd(s.avg, 2)}</b></div><div><small>Profit Factor</small><b>${isFinite(s.pf) ? s.pf.toFixed(2) : '∞'}</b></div><div><small>میانگین امتیاز</small><b>${s.rate.toFixed(1)} ★</b></div>`;
  $('#jTable tbody').innerHTML = journal.length ? journal.map(j => { const p = tradePnl(j); return `<tr><td>${j.date ? faDate(j.date) : ''}</td><td><b>${esc(j.sym)}</b></td><td class="${j.side === 'long' ? 'up' : 'down'}">${j.side === 'long' ? 'لانگ' : 'شورت'}${j.lev > 1 ? ' ×' + toFa(j.lev) : ''}</td>
    <td class="num">${fmtNum(j.entry)}</td><td class="num">${j.exit ? fmtNum(j.exit) : 'باز'}</td><td class="num">${fmtNum(j.qty, 6)}</td><td class="num ${pctCls(p)}">${p != null ? fmtUsd(p, 2) : '—'}</td><td>${esc(j.emotion)}</td><td>${'★'.repeat(j.rate || 0)}</td>
    <td style="white-space:normal;max-width:260px">${esc(j.reason)}${j.lesson ? `<br><small class="muted">درس: ${esc(j.lesson)}</small>` : ''}</td>
    <td>${safeImg(j.imgBefore) ? `<img class="thumb" src="${safeImg(j.imgBefore)}" title="قبل" alt="قبل">` : ''}${safeImg(j.imgAfter) ? `<img class="thumb" src="${safeImg(j.imgAfter)}" title="بعد" alt="بعد">` : ''}</td>
    <td class="no-print"><button class="btn sm ghost" data-jdel="${j.id}">حذف</button></td></tr>`; }).join('') : '<tr><td colspan="12" class="muted">هنوز تریدی ثبت نشده است.</td></tr>';
  $$('[data-jdel]').forEach(b => b.onclick = async () => { if (!confirm('این ترید حذف شود؟')) return; try { await idb.del(+b.dataset.jdel); } catch { } store.set('journalFallback', store.get('journalFallback', []).filter(j => j.id !== +b.dataset.jdel)); loadJournal(); });
  $$('#jTable .thumb').forEach(im => im.onclick = () => { $('#imgModal img').src = im.src; $('#imgModal').hidden = false; });
}
function journalCSV() {
  const cols = ['date', 'sym', 'side', 'lev', 'entry', 'exit', 'qty', 'fee', 'sl', 'tp', 'pnl', 'emotion', 'rate', 'reason', 'lesson'];
  const rows = journal.map(j => cols.map(c => { const v = c === 'pnl' ? (tradePnl(j) ?? '') : (j[c] ?? ''); return '"' + String(v).replace(/"/g, '""') + '"'; }).join(','));
  download('hooshmonitor-journal.csv', '\ufeff' + cols.join(',') + '\n' + rows.join('\n'), 'text/csv;charset=utf-8');
}
async function addToJournalFromCalc() {
  const r = calcCompute(); if (!r) return toast('ابتدا ماشین‌حساب را پر کنید', 'err');
  const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  const e = { id: Date.now(), date: d.toISOString().slice(0, 16), sym: r.coin, side: r.mode === 'short' ? 'short' : 'long', lev: r.lev, entry: r.entry, exit: null, qty: +r.qtyCalc.toPrecision(6), fee: +(r.position * r.fee).toFixed(2), sl: r.stop || null, tp: r.exit || null, emotion: 'آرام و منطقی', rate: 3, reason: `ثبت از ماشین‌حساب — R:R ${r.rr ? r.rr.toFixed(2) : '—'}`, lesson: '' };
  if (!(await saveJournalEntry(e))) return;
  toast('ترید در ژورنال ثبت شد 📒', 'ok'); loadJournal();
}

/* ---------------- بک‌تست ---------------- */
async function runBacktest() {
  const sym = $('#btSym').value + 'USDT', tf = $('#btTf').value, strat = $('#btStrat').value;
  const cap0 = +$('#btCap').value || 1000, risk = (+$('#btRisk').value || 2) / 100, slM = +$('#btSL').value || 1.5, tpM = +$('#btTP').value || 3, fee = (+$('#btFee').value || 0) / 100;
  $('#btInfo').textContent = 'در حال دریافت داده…';
  let k; try { k = await klines(sym, tf, 1000); } catch (e) { $('#btInfo').textContent = 'خطا: ' + e.message; return; }
  const c = k.map(x => x.c), m20 = sma(c, 20), m50 = sma(c, 50), r = rsi(c), bb = bollinger(c), a = atr(k);
  const sig = i => {
    if (strat === 'ma') return m20[i - 1] != null && m50[i - 1] != null ? (m20[i - 1] <= m50[i - 1] && m20[i] > m50[i] ? 1 : m20[i - 1] >= m50[i - 1] && m20[i] < m50[i] ? -1 : 0) : 0;
    if (strat === 'rsi') return r[i - 1] != null ? (r[i - 1] < 30 && r[i] >= 30 ? 1 : r[i - 1] > 70 && r[i] <= 70 ? -1 : 0) : 0;
    if (strat === 'bb') return bb.lo[i] != null ? (c[i] < bb.lo[i] ? 1 : c[i] > bb.up[i] ? -1 : 0) : 0;
    if (i < 21) return 0; const hh = Math.max(...k.slice(i - 20, i).map(x => x.h)), ll = Math.min(...k.slice(i - 20, i).map(x => x.l));
    return c[i] > hh ? 1 : c[i] < ll ? -1 : 0;
  };
  let eq = cap0, peak = cap0, mdd = 0, pos = null; const trades = [], curve = [{ t: k[0].t, e: eq }];
  const close = (i, px, why) => {
    const gross = pos.dir * (px - pos.entry) * pos.qty, f = (pos.entry + px) * pos.qty * fee;
    const pnl = gross - f; eq += pnl;
    trades.push({ dir: pos.dir, entry: pos.entry, exit: px, pct: pos.dir * (px / pos.entry - 1) * 100, pnl, eq, why, t: k[i].t }); pos = null;
  };
  for (let i = 51; i < k.length; i++) {
    const bar = k[i];
    if (pos) {
      const hitSL = pos.dir === 1 ? bar.l <= pos.sl : bar.h >= pos.sl, hitTP = pos.dir === 1 ? bar.h >= pos.tp : bar.l <= pos.tp;
      if (hitSL) close(i, pos.sl, 'SL'); else if (hitTP) close(i, pos.tp, 'TP');
      else if (strat === 'bb' && ((pos.dir === 1 && c[i] >= bb.mid[i]) || (pos.dir === -1 && c[i] <= bb.mid[i]))) close(i, c[i], 'MID');
      else { const s = sig(i); if (s && s === -pos.dir) close(i, c[i], 'REV'); }
    }
    if (!pos && a[i]) {
      const s = sig(i);
      if (s) { const slD = slM * a[i], qty = Math.min(eq * risk / slD, eq / c[i]); pos = { dir: s, entry: c[i], qty, sl: c[i] - s * slD, tp: c[i] + s * tpM * a[i] }; }
    }
    const mtm = eq + (pos ? pos.dir * (c[i] - pos.entry) * pos.qty : 0);
    peak = Math.max(peak, mtm); mdd = Math.max(mdd, (peak - mtm) / peak * 100); curve.push({ t: bar.t, e: mtm });
  }
  if (pos) close(k.length - 1, c[c.length - 1], 'END');
  const wins = trades.filter(t => t.pnl > 0), gw = wins.reduce((s, t) => s + t.pnl, 0), gl = -trades.filter(t => t.pnl <= 0).reduce((s, t) => s + t.pnl, 0);
  const bh = (c[c.length - 1] / c[51] - 1) * 100;
  $('#btStats').innerHTML = `<div><small>تعداد معامله</small><b>${toFa(trades.length)}</b></div><div><small>وین‌ریت</small><b>${trades.length ? (wins.length / trades.length * 100).toFixed(1) : 0}%</b></div>
    <div><small>میانگین سود هر معامله</small><b class="${pctCls(trades.reduce((s, t) => s + t.pct, 0))}">${trades.length ? fmtPct(trades.reduce((s, t) => s + t.pct, 0) / trades.length) : '—'}</b></div>
    <div><small>بازده کل</small><b class="${pctCls(eq - cap0)}">${fmtPct((eq / cap0 - 1) * 100)}</b></div><div><small>بیش‌ترین افت سرمایه</small><b class="down">-${mdd.toFixed(1)}%</b></div>
    <div><small>Profit Factor</small><b>${gl ? (gw / gl).toFixed(2) : '∞'}</b></div><div><small>موجودی نهایی</small><b>${fmtUsd(eq, 0)}</b></div><div><small>خرید و نگهداری</small><b class="${pctCls(bh)}">${fmtPct(bh)}</b></div>`;
  $('#btTrades tbody').innerHTML = trades.map((t, i) => `<tr><td>${toFa(i + 1)}</td><td class="${t.dir === 1 ? 'up' : 'down'}">${t.dir === 1 ? 'لانگ' : 'شورت'}</td><td class="num">${fmtNum(t.entry)}</td><td class="num">${fmtNum(t.exit)} <small class="muted">${t.why}</small></td><td class="num ${pctCls(t.pct)}">${fmtPct(t.pct)}</td><td class="num">${fmtUsd(t.eq, 0)}</td></tr>`).join('');
  $('#btInfo').textContent = `${sym} · ${tf} · ${toFa(k.length)} کندل از ${new Date(k[0].t).toLocaleDateString('fa-IR')} تا امروز`;
  drawLine($('#equityCanvas'), curve.map(p => p.e), '#2dd4bf', v => fmtUsd(v, 0));
}
function drawLine(cv, data, color, lbl = v => v.toFixed(2), refLines = []) {
  if (!cv || !data.length) return;
  const { g, w, h } = setupCanvas(cv), pl = 70, pt = 12, pb = 12;
  const mn = Math.min(...data, ...refLines.map(r => r[0])), mx = Math.max(...data, ...refLines.map(r => r[0]));
  const y = v => pt + (mx - v) / (mx - mn || 1) * (h - pt - pb), x = i => pl + i / (data.length - 1) * (w - pl - 8);
  g.font = '11px Vazirmatn, Tahoma'; g.fillStyle = '#8a9bb8'; g.strokeStyle = '#1c2a44';
  for (let i = 0; i <= 4; i++) { const v = mn + (mx - mn) * i / 4; g.beginPath(); g.moveTo(pl, y(v)); g.lineTo(w, y(v)); g.stroke(); g.fillText(lbl(v), 4, y(v) + 4); }
  refLines.forEach(([v, c, t]) => { g.strokeStyle = c; g.setLineDash([4, 4]); g.beginPath(); g.moveTo(pl, y(v)); g.lineTo(w, y(v)); g.stroke(); g.setLineDash([]); g.fillStyle = c; g.fillText(t, pl + 4, y(v) - 3); });
  g.beginPath(); data.forEach((v, i) => i ? g.lineTo(x(i), y(v)) : g.moveTo(x(i), y(v))); g.strokeStyle = color; g.lineWidth = 1.8; g.stroke();
  g.lineTo(x(data.length - 1), h - pb); g.lineTo(pl, h - pb); g.closePath(); const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, color + '44'); gr.addColorStop(1, color + '00'); g.fillStyle = gr; g.fill();
}

/* ---------------- آن‌چین ---------------- */
async function loadOnchain() {
  const box = $('#onchainBox'), rows = [];
  try {
    const d = await getJSON('https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur,SplyExNtv,FlowInExNtv,FlowOutExNtv&page_size=365&paging_from=end');
    const data = d.data, last = data[data.length - 1], wk = data.slice(-7), m30 = data[data.length - 31] || data[0];
    const mvrv = +last.CapMVRVCur, net7 = wk.reduce((s, x) => s + (+x.FlowInExNtv - +x.FlowOutExNtv), 0);
    const mvrvTxt = mvrv > 3.5 ? 'محدوده سقف (فروش)' : mvrv > 2.4 ? 'گران' : mvrv < 1 ? 'محدوده کف تاریخی (خرید)' : mvrv < 1.3 ? 'نزدیک کف – ارزان' : 'منصفانه';
    rows.push(`<div><span>MVRV</span><b>${mvrv.toFixed(2)} · ${mvrvTxt}</b></div>`,
      `<div><span>موجودی BTC صرافی‌ها</span><b>${fmtNum(+last.SplyExNtv, 0)} BTC</b></div>`,
      `<div><span>تغییر موجودی صرافی ۳۰ روز</span><b class="${+last.SplyExNtv < +m30.SplyExNtv ? 'up' : 'down'}">${fmtNum(+last.SplyExNtv - +m30.SplyExNtv, 0)} BTC</b></div>`,
      `<div><span>خالص ورود/خروج صرافی ۷ روز</span><b class="${net7 < 0 ? 'up' : 'down'}">${net7 < 0 ? 'خروج' : 'ورود'} ${fmtNum(Math.abs(net7), 0)} BTC</b></div>`,
      `<div><span>ورود دیروز به صرافی</span><b>${fmtNum(+last.FlowInExNtv, 0)} BTC</b></div>`, `<div><span>خروج دیروز از صرافی</span><b>${fmtNum(+last.FlowOutExNtv, 0)} BTC</b></div>`);
    state.onchain = { mvrv, mvrvTxt, net7, sply: +last.SplyExNtv };
    setTimeout(() => drawLine($('#mvrvCanvas'), data.map(x => +x.CapMVRVCur), '#f5b83d', v => 'MVRV ' + v.toFixed(2), [[1, '#22c55e', 'کف ۱٫۰'], [3.5, '#ef4444', 'سقف ۳٫۵']].filter(r => r[0] >= Math.min(...data.map(x => +x.CapMVRVCur)) - 0.5 && r[0] <= Math.max(...data.map(x => +x.CapMVRVCur)) + 0.5)), 50);
  } catch { rows.push('<div><span>Coin Metrics</span><b>در دسترس نیست</b></div>'); }
  try {
    const [rev, hr] = await Promise.all([getJSON('https://api.blockchain.info/charts/miners-revenue?timespan=60days&format=json&cors=true'), getJSON('https://api.blockchain.info/charts/hash-rate?timespan=60days&format=json&cors=true')]);
    const rv = rev.values, h = hr.values, avg = (arr, n) => arr.slice(-n).reduce((s, x) => s + x.y, 0) / n;
    rows.push(`<div><span>درآمد روزانه ماینرها</span><b>${fmtBig(avg(rv, 7))}</b></div>`, `<div><span>هش‌ریت (میانگین ۷ روز)</span><b>${(avg(h, 7) / 1e6).toFixed(0)} EH/s</b></div>`,
      `<div><span>روند هش‌ریت ۳۰ روز</span><b class="${pctCls(avg(h, 7) - avg(h.slice(0, -30), 7))}">${fmtPct((avg(h, 7) / avg(h.slice(0, -30), 7) - 1) * 100, 1)}</b></div>`);
  } catch { }
  rows.push('<div><span>SOPR / کیف‌پول‌های قدیمی</span><b>نیازمند Glassnode</b></div>');
  box.innerHTML = rows.join('');
}

/* ---------------- گزارش PDF ---------------- */
let rpLogo = store.get('rpLogo', null);
function buildReport() {
  const now = Date.now(), weekAgo = now - 7 * 864e5;
  const name = $('#rpName').value.trim() || 'تحلیل‌گر هوش‌مانیتور'; store.set('rpName', name);
  const sig = $('#sigPad').toDataURL(); const r = state.regime;
  const btc = state.byId.bitcoin, eth = state.byId.ethereum;
  const jw = journal.filter(j => new Date(j.date).getTime() >= weekAgo), js = journalStats(jw);
  const ph = state.paper.history.filter(h => h.t >= weekAgo), ppnl = ph.reduce((s, h) => s + h.pnl, 0);
  const tierRows = Object.entries(TIERS).flatMap(([k, t]) => t.ids.map(id => state.byId[id]).filter(Boolean).map(c => `<tr><td>${k === 'blue' ? 'Blue-chip' : k === 'mid' ? 'Mid-cap' : 'Moonshot'}</td><td>${c.symbol.toUpperCase()}</td><td class="num">${fmtUsd(c.current_price)}</td><td class="num">${fmtPct(c.price_change_percentage_7d_in_currency, 1)}</td><td class="num">${fmtPct(c.ath_change_percentage, 0)}</td><td>${toFa(t.weight / 5)}٪</td><td class="num">${fmtUsd(projectPrice(c, k, 12))}</td></tr>`)).join('');
  $('#reportDoc').innerHTML = `<div class="rp">
    <div class="rp-h"><div><h2>${esc($('#rpTitle').value)}</h2><div>بازه: ${new Date(weekAgo).toLocaleDateString('fa-IR')} تا ${new Date(now).toLocaleDateString('fa-IR')}</div><div>تهیه‌کننده: <b>${esc(name)}</b></div></div>
      ${safeImg(rpLogo) ? `<img src="${safeImg(rpLogo)}" alt="logo">` : '<img src="icon.svg" alt="logo" style="height:60px"><b style="color:#a8730d">هوش‌مانیتور پرو</b>'}</div>
    <h3>۱. خلاصه بازار</h3><table><tr><th>شاخص</th><th>مقدار</th><th>شاخص</th><th>مقدار</th></tr>
      <tr><td>بیت‌کوین</td><td class="num">${fmtUsd(btc?.current_price)} (${fmtPct(btc?.price_change_percentage_7d_in_currency, 1)} هفتگی)</td><td>اتریوم</td><td class="num">${fmtUsd(eth?.current_price)} (${fmtPct(eth?.price_change_percentage_7d_in_currency, 1)})</td></tr>
      <tr><td>دامیننس BTC</td><td class="num">${state.global ? state.global.market_cap_percentage.btc.toFixed(2) + '%' : '—'}</td><td>ارزش کل بازار</td><td class="num">${state.global ? fmtBig(state.global.total_market_cap.usd) : '—'}</td></tr>
      <tr><td>انس طلا</td><td class="num">${fmtUsd(state.gold, 1)}</td><td>شاخص دلار DXY</td><td class="num">${state.dxy ? state.dxy.toFixed(2) : '—'}</td></tr>
      <tr><td>ترس و طمع</td><td>${state.fng ? toFa(state.fng[0].value) : '—'}</td><td>دلار / تومان</td><td class="num">${fmtNum(state.rate, 0)}</td></tr>
      <tr><td>رژیم بازار</td><td>${r ? r.label + ' (' + toFa(r.score) + ')' : '—'}</td><td>MVRV بیت‌کوین</td><td>${state.onchain ? state.onchain.mvrv.toFixed(2) + ' · ' + state.onchain.mvrvTxt : '—'}</td></tr></table>
    <h3>۲. سبد سه‌سطحی و هدف ۱۲ ماهه (سناریو پایه)</h3><table><tr><th>سطح</th><th>ارز</th><th>قیمت</th><th>۷ روز</th><th>از ATH</th><th>وزن</th><th>هدف ۱۲ ماهه</th></tr>${tierRows}</table>
    <h3>۳. پنج پیشنهاد معاملاتی</h3><table><tr><th>اولویت</th><th>نماد</th><th>جهت</th><th>محدوده ورود</th><th>استاپ‌لاس</th><th>تارگت‌ها</th></tr>${state.signals.map((s, i) => `<tr><td>${toFa(i + 1)}</td><td>${s.sym}</td><td>${s.side === 'long' ? 'لانگ' : 'شورت'}</td><td class="num">${fmtNum(s.entry[0])} – ${fmtNum(s.entry[1])}</td><td class="num">${fmtNum(s.sl)}</td><td class="num">${s.tp.map(v => fmtNum(v)).join(' / ')}</td></tr>`).join('')}</table>
    <h3>۴. عملکرد هفته</h3><table><tr><th>ژورنال: تعداد ترید</th><th>وین‌ریت</th><th>سود/زیان</th><th>حساب آزمایشی: معاملات</th><th>سود/زیان</th><th>ارزش حساب</th></tr>
      <tr><td>${toFa(js.n)}</td><td>${js.win.toFixed(1)}%</td><td class="num">${fmtUsd(js.total, 2)}</td><td>${toFa(ph.length)}</td><td class="num">${fmtUsd(ppnl, 2)}</td><td class="num">${fmtUsd(state.paper.equity ?? state.paper.balance, 2)}</td></tr></table>
    <h3>۵. جمع‌بندی تحلیل‌گر</h3><p>${r ? (r.score >= 55 ? 'ساختار بازار مثبت است؛ استراتژی پیشنهادی هفته آینده خرید در اصلاح و حفظ سبد Blue-chip است.' : r.score <= 45 ? 'بازار در فاز نزولی/احتیاط است؛ سهم نقد بالاتر، ریسک هر معامله حداکثر ۱٪ و خرید پله‌ای فقط در حمایت‌های اصلی پیشنهاد می‌شود.' : 'بازار در فاز رنج است؛ معاملات کوتاه‌مدت بین حمایت و مقاومت با حد ضرر نزدیک انجام شود.') : ''} قانون مدیریت سرمایه: ریسک ۱ تا ۲٪ در هر پوزیشن و حداکثر ۱۰ تا ۱۵٪ سرمایه در یک ترید.</p>
    <div class="sign"><div><img src="${sig}" alt="امضا"><div>${esc(name)}</div><small>${new Date().toLocaleDateString('fa-IR')}</small></div></div>
    <div class="disc">این گزارش به‌صورت خودکار از داده‌های عمومی بازار تهیه شده و توصیه مالی نیست. مسئولیت تصمیمات معاملاتی با سرمایه‌گذار است.</div></div>`;
}
function bindSigPad() {
  const cv = $('#sigPad'), g = cv.getContext('2d'); let dr = false;
  g.lineWidth = 2.2; g.lineCap = 'round'; g.strokeStyle = '#0b1f5c';
  const pos = e => { const r = cv.getBoundingClientRect(), p = e.touches ? e.touches[0] : e; return [(p.clientX - r.left) * cv.width / r.width, (p.clientY - r.top) * cv.height / r.height]; };
  const start = e => { dr = true; g.beginPath(); g.moveTo(...pos(e)); e.preventDefault(); };
  const move = e => { if (!dr) return; g.lineTo(...pos(e)); g.stroke(); e.preventDefault(); };
  const end = () => { if (dr) store.set('sig', cv.toDataURL()); dr = false; };
  cv.addEventListener('pointerdown', start); cv.addEventListener('pointermove', move); window.addEventListener('pointerup', end);
  const saved = store.get('sig'); if (saved) { const im = new Image(); im.onload = () => g.drawImage(im, 0, 0); im.src = saved; }
  $('#sigClear').onclick = () => { g.clearRect(0, 0, cv.width, cv.height); store.del('sig'); };
}

/* ---------------- ناوبری و اتصال رابط کاربری ---------------- */
function showSection(id) {
  $$('.sec').forEach(s => s.classList.toggle('active', s.id === 'sec-' + id));
  $$('#sidebar a').forEach(a => a.classList.toggle('active', a.dataset.sec === id));
  $('#sidebar').classList.remove('open'); history.replaceState(null, '', '#' + id);
  if (id === 'chart') { if (!chartState.data.length) loadChart(); else setTimeout(drawChart, 30); }
  if (id === 'calc') renderCalc();
  if (id === 'trade') renderPaper();
  if (id === 'onchain' && state.onchain) setTimeout(loadOnchain, 30);
  window.scrollTo(0, 0);
}
function bindUI() {
  $$('#sidebar a').forEach(a => a.onclick = () => showSection(a.dataset.sec));
  $('#menuBtn').onclick = () => $('#sidebar').classList.toggle('open');
  $$('#currencySeg button').forEach(b => { b.classList.toggle('active', b.dataset.cur === state.currency); b.onclick = () => { state.currency = b.dataset.cur; store.set('currency', state.currency); $$('#currencySeg button').forEach(x => x.classList.toggle('active', x === b)); renderAll(); renderPortfolio(); renderTop5Reset(); }; });
  $('#tableSearch').oninput = e => { tableFilter = e.target.value.trim().toLowerCase(); renderTable(); };
  $('#clearFeed').onclick = () => { state.feed = []; store.set('feed', []); renderFeed(); };
  bindChart();
  // advisor
  $('#chatForm').onsubmit = e => { e.preventDefault(); const q = $('#chatInput').value; $('#chatInput').value = ''; ask(q); };
  $$('#chatChips button').forEach(b => b.onclick = () => ask(b.textContent));
  addMsg('سلام! من مشاور هوش‌مانیتور هستم. درباره تحلیل هر ارز، مدیریت سرمایه با مبلغ مشخص، پیش‌بینی تا ۲۰۳۰ و گاوی یا خرسی بودن بازار بپرسید.');
  $('#aiMode').textContent = state.keys.openai ? 'حالت: OpenAI + داده زنده' : 'حالت: تحلیل‌گر داخلی (بدون نیاز به کلید)';
  // calculator
  $$('#sec-calc input, #sec-calc select').forEach(el => el.addEventListener('input', renderCalc));
  $('#cCoin').addEventListener('change', () => { const p = priceOf($('#cCoin').value); if (p) $('#cEntry').value = +p.toPrecision(6); renderCalc(); });
  $('#cMode').addEventListener('change', () => { if ($('#cMode').value === 'spot') $('#cLev').value = 1; renderCalc(); });
  $$('#calcCurSeg button').forEach(b => b.onclick = () => { calcCur = b.dataset.cur; $$('#calcCurSeg button').forEach(x => x.classList.toggle('active', x === b)); renderCalc(); });
  $('#calcAuto').onclick = calcAuto; $('#calcToJournal').onclick = addToJournalFromCalc;
  $('#calcToPaper').onclick = () => { const r = calcCompute(); if (!r) return; openPaper({ sym: r.coin, side: r.mode === 'short' ? 'short' : 'long', amount: r.margin, lev: r.lev, sl: r.stop, tp: r.exit, src: 'ماشین‌حساب' }); showSection('trade'); };
  // forecast
  $('#refreshSignals').onclick = () => { $('#signalsTable tbody').innerHTML = '<tr><td colspan="8" class="muted">در حال محاسبه…</td></tr>'; computeSignals(); };
  $$('#horizonSeg button').forEach(b => b.onclick = () => { horizon = b.dataset.h; $$('#horizonSeg button').forEach(x => x.classList.toggle('active', x === b)); renderPortfolio(); });
  $$('#scenarioSeg button').forEach(b => b.onclick = () => { scenario = b.dataset.s; $$('#scenarioSeg button').forEach(x => x.classList.toggle('active', x === b)); renderHoldTable(); });
  // exchange / paper
  const ex = store.get('exchange', {}); $('#exName').value = ex.name || 'Binance'; $('#exKey').value = ex.key || ''; $('#exSecret').value = ex.secret || '';
  $('#exMode').onchange = () => { if ($('#exMode').value === 'live') { toast('سفارش واقعی از داخل مرورگر امکان‌پذیر نیست (CORS و امنیت کلید). سفارش‌ها در حالت آزمایشی اجرا می‌شوند.', 'err'); $('#exMode').value = 'paper'; } };
  $('#exSave').onclick = () => { store.set('exchange', { name: $('#exName').value, key: $('#exKey').value, secret: $('#exSecret').value }); $('#exBadge').textContent = $('#exName').value + ' · آزمایشی'; $('#exBadge').classList.add('on'); toast('کلیدها روی همین مرورگر ذخیره شد', 'ok'); };
  $('#exForget').onclick = () => { store.del('exchange'); $('#exKey').value = $('#exSecret').value = ''; $('#exBadge').textContent = 'حالت آزمایشی'; $('#exBadge').classList.remove('on'); };
  if (ex.key) { $('#exBadge').textContent = (ex.name || 'Binance') + ' · آزمایشی'; $('#exBadge').classList.add('on'); }
  $('#pSym').addEventListener('change', updateLivePrices);
  const order = side => openPaper({ sym: $('#pSym').value, side, amount: $('#pAmt').value, lev: $('#pLev').value, sl: $('#pSL').value, tp: $('#pTP').value });
  $('#pBuy').onclick = () => order('long'); $('#pSell').onclick = () => order('short');
  $('#pReset').onclick = () => { if (confirm('حساب آزمایشی به ۱۰٬۰۰۰ دلار ریست شود؟')) { state.paper = { balance: 10000, positions: [], history: [] }; savePaper(); renderPaper(); } };
  if (!store.get('whSecret')) store.set('whSecret', Math.random().toString(36).slice(2, 8));
  $('#webhookTpl').textContent = webhookTemplate();
  $('#webhookRun').onclick = () => runWebhook($('#webhookIn').value);
  $('#webhookCopy').onclick = () => navigator.clipboard.writeText(webhookTemplate()).then(() => toast('قالب کپی شد', 'ok'));
  $('#mt5Dl').onclick = () => mqlEA(true); $('#mt4Dl').onclick = () => mqlEA(false);
  // alerts
  $('#notifPerm').onclick = async () => { if (!('Notification' in window)) return toast('مرورگر از نوتیف پشتیبانی نمی‌کند', 'err'); const p = await Notification.requestPermission(); toast(p === 'granted' ? 'نوتیف مرورگر فعال شد ✅' : 'اجازه نوتیف داده نشد', p === 'granted' ? 'ok' : 'err'); beep(); };
  $('#aSym').addEventListener('change', () => { const p = priceOf($('#aSym').value); if (p) $('#aPrice').placeholder = 'اکنون ' + fmtNum(p); });
  $('#alertForm').onsubmit = e => { e.preventDefault(); state.alerts.push({ sym: $('#aSym').value, cond: $('#aCond').value, price: parseFloat(toEn($('#aPrice').value)), note: $('#aNote').value.trim(), done: false, t: Date.now() }); store.set('alerts', state.alerts); $('#alertForm').reset(); renderAlertList(); toast('هشدار قیمت اضافه شد 🔔', 'ok'); };
  $('#tgToken').value = state.tg.token; $('#tgChat').value = state.tg.chat; $('#tgOn').checked = state.tg.on;
  $$('[data-tg]').forEach(c => c.checked = !!state.tg[c.dataset.tg]);
  const tgBadge = () => { $('#tgBadge').textContent = state.tg.on ? 'فعال' : 'غیرفعال'; $('#tgBadge').classList.toggle('on', state.tg.on); };
  const tgSave = () => { state.tg.token = $('#tgToken').value.trim(); state.tg.chat = $('#tgChat').value.trim(); state.tg.on = $('#tgOn').checked; $$('[data-tg]').forEach(c => state.tg[c.dataset.tg] = c.checked); store.set('tg', state.tg); tgBadge(); };
  tgBadge(); $('#tgSave').onclick = () => { tgSave(); toast('تنظیمات تلگرام ذخیره شد', 'ok'); };
  $('#tgOn').onchange = tgSave; $$('[data-tg]').forEach(c => c.onchange = tgSave);
  $('#tgTest').onclick = () => { tgSave(); sendTelegram('✅ <b>هوش‌مانیتور پرو</b>\nاتصال ربات تلگرام برقرار است. BTC: ' + fmtUsd(priceOf('BTC')), true); };
  $('#tgFind').onclick = async () => { tgSave(); if (!state.tg.token) return toast('ابتدا توکن را وارد کنید', 'err'); try { const d = await getJSON(`https://api.telegram.org/bot${state.tg.token}/getUpdates`); const m = (d.result || []).reverse().find(u => u.message); if (m) { $('#tgChat').value = m.message.chat.id; tgSave(); toast('Chat ID پیدا شد: ' + m.message.chat.id, 'ok'); } else toast('پیامی پیدا نشد؛ ابتدا به ربات پیام بدهید', 'err'); } catch (e) { toast('خطا: ' + e.message, 'err'); } };
  const R = state.rules; $('#rVol').value = R.vol; $('#rWhale').value = R.whale; $('#rWords').value = R.words; $('#rTf').value = R.tf; $('#rSound').checked = R.sound; $('#rNotif').checked = R.notif;
  $('#rulesSave').onclick = () => { Object.assign(state.rules, { vol: +$('#rVol').value || 2, whale: +$('#rWhale').value || 5e6, words: $('#rWords').value, tf: $('#rTf').value, sound: $('#rSound').checked, notif: $('#rNotif').checked }); store.set('rules', state.rules); renderNews(); toast('قوانین هشدار ذخیره شد', 'ok'); };
  $('#monitorInfo').textContent = `حجم ×${R.vol} · نهنگ > ${fmtBig(R.whale)} · خبر`;
  // journal
  setNow(); $('#jForm').onsubmit = e => { e.preventDefault(); addJournal(); };
  $('#jCsv').onclick = journalCSV;
  $('#jPrint').onclick = () => { document.body.classList.add('print-journal'); window.print(); document.body.classList.remove('print-journal'); };
  $('#imgModal').onclick = () => $('#imgModal').hidden = true;
  // backtest
  $('#btRun').onclick = runBacktest;
  // report
  $('#rpName').value = store.get('rpName', '');
  $('#rpLogo').onchange = async e => { rpLogo = await compressImage(e.target.files[0], 400); store.set('rpLogo', rpLogo); };
  $('#rpBuild').onclick = buildReport;
  $('#rpPrint').onclick = () => { if (!$('#reportDoc').innerHTML) buildReport(); document.body.classList.add('print-report'); window.print(); document.body.classList.remove('print-report'); };
  bindSigPad();
  // settings
  $('#sRateSrc').value = state.rateSrc; $('#sRate').value = store.get('manualRate', state.rate);
  $('#sRateSave').onclick = async () => { state.rateSrc = $('#sRateSrc').value; store.set('rateSrc', state.rateSrc); store.set('manualRate', +$('#sRate').value); await loadRate(); renderRate(); renderAll(); toast('نرخ دلار به‌روز شد', 'ok'); };
  $('#sOpenAI').value = state.keys.openai; $('#sModel').value = state.keys.model; $('#sWhale').value = state.keys.whale;
  $('#sKeysSave').onclick = () => { state.keys = { openai: $('#sOpenAI').value.trim(), model: $('#sModel').value.trim() || 'gpt-4o-mini', whale: $('#sWhale').value.trim() }; store.set('keys', state.keys); $('#aiMode').textContent = state.keys.openai ? 'حالت: OpenAI + داده زنده' : 'حالت: تحلیل‌گر داخلی (بدون نیاز به کلید)'; toast('کلیدها ذخیره شد', 'ok'); };
  $('#backupDl').onclick = async () => { const ls = {}; Object.keys(localStorage).filter(k => k.startsWith('hm_')).forEach(k => ls[k] = localStorage.getItem(k)); let j = []; try { j = await idb.all(); } catch { } download(`hooshmonitor-backup-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify({ v: 1, ls, journal: j }), 'application/json'); };
  $('#backupUp').onchange = async e => { try { const d = JSON.parse(await e.target.files[0].text()); Object.entries(d.ls || {}).forEach(([k, v]) => localStorage.setItem(k, v)); for (const j of d.journal || []) await idb.put(j); toast('پشتیبان بازیابی شد؛ صفحه دوباره بارگذاری می‌شود', 'ok'); setTimeout(() => location.reload(), 1200); } catch { toast('فایل پشتیبان نامعتبر است', 'err'); } };
  $('#wipeAll').onclick = async () => { if (!confirm('همه داده‌ها (ژورنال، هشدارها، کلیدها، حساب آزمایشی) پاک شود؟')) return; Object.keys(localStorage).filter(k => k.startsWith('hm_')).forEach(k => localStorage.removeItem(k)); try { await idb.clear(); } catch { } location.reload(); };
}
function renderTop5Reset() { $('#top5').innerHTML = ''; renderTop5(); }

/* ---------------- PWA ---------------- */
let deferredInstall;
function setupPWA() {
  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('sw.js').catch(() => { });
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); deferredInstall = e; $('#installBtn').hidden = false; });
  $('#installBtn').onclick = async () => { if (!deferredInstall) return; deferredInstall.prompt(); await deferredInstall.userChoice; deferredInstall = null; $('#installBtn').hidden = true; };
  window.addEventListener('online', () => setStatus(true)); window.addEventListener('offline', () => setStatus(false, 'آفلاین – نمایش آخرین داده'));
}

/* ---------------- شروع ---------------- */
const safe = (fn, ...a) => Promise.resolve().then(() => fn(...a)).catch(e => console.warn(fn.name, e));
async function init() {
  bindUI(); setupPWA(); renderFeed(); renderAlertList(); renderPaper(); loadJournal();
  const cached = store.get('marketsCache'); if (cached) { state.markets = cached.filter(c => !STABLES.has(c.symbol)).slice(0, 50); state.allMarkets = cached; indexMarkets(cached); }
  await safe(loadRate); renderRate();
  try { await loadMarkets(); store.set('marketsCache', state.allMarkets); } catch { setStatus(false, navigator.onLine ? 'CoinGecko در دسترس نیست' : 'آفلاین'); }
  renderAll(); startStream();
  const hash = location.hash.slice(1); if (hash && $('#sec-' + hash)) showSection(hash);
  await Promise.all([safe(loadGlobal), safe(loadGold), safe(loadDXY), safe(loadFNG), safe(loadFutures), safe(loadPortfolioCoins)]);
  renderLiquidity(); renderFutures(); renderTicker(); renderPortfolio(); renderCalc();
  loadTVWidgets();
  safe(loadNews, true); safe(computeRegime); safe(loadOnchain); safe(monitorWhales);
  safe(computeSignals).then(() => { if (!$('#cEntry').value && state.signals[0]) { $('#cCoin').value = state.signals[0].sym; } });
  setTimeout(() => safe(monitorVolume), 8000);
  // زمان‌بندی‌ها
  setInterval(async () => { try { await loadMarkets(); store.set('marketsCache', state.allMarkets); renderTable(); renderTicker(); startStream(); } catch { } }, 90e3);
  setInterval(async () => { await Promise.all([safe(loadGlobal), safe(loadGold), safe(loadFutures), safe(loadFNG)]); renderLiquidity(); renderFutures(); }, 120e3);
  setInterval(() => safe(loadNews), 75e3);
  setInterval(() => safe(monitorWhales), 60e3);
  setInterval(() => safe(monitorVolume), 120e3);
  setInterval(async () => { await safe(loadRate); renderRate(); }, 300e3);
  setInterval(async () => { await safe(loadPortfolioCoins); renderPortfolio(); await safe(computeRegime); await safe(computeSignals); safe(loadDXY); }, 900e3);
  setInterval(() => { renderFeed(); renderWhales(); }, 30e3);
}
document.addEventListener('DOMContentLoaded', init);
