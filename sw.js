/* Service Worker هوش‌مانیتور پرو — حالت آفلاین */
const CACHE = 'hooshmonitor-v2';
const SHELL = ['./', './index.html', './style.css', './script.js', './manifest.json', './icon.svg'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const req = e.request; if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin || /jsdelivr|coin-images/.test(url.host)) {
    // فایل‌های برنامه: اول شبکه (برای دریافت نسخه جدید)، در حالت آفلاین از کش
    e.respondWith(fetch(req).then(r => { if (r.ok) { const cp = r.clone(); caches.open(CACHE).then(c => c.put(req, cp)); } return r; }).catch(() => caches.match(req)));
    return;
  }
  // داده‌های API: اول شبکه، در صورت قطعی آخرین پاسخ ذخیره‌شده
  if (/coingecko|binance|okx|gold-api|frankfurter|alternative\.me|coinmetrics|blockchain\.info|rss2json/.test(url.host)) {
    e.respondWith(fetch(req).then(r => { if (r.ok) { const cp = r.clone(); caches.open(CACHE + '-api').then(c => c.put(req, cp)); } return r; }).catch(() => caches.match(req)));
  }
});
self.addEventListener('notificationclick', e => { e.notification.close(); e.waitUntil(self.clients.matchAll({ type: 'window' }).then(cs => cs.length ? cs[0].focus() : self.clients.openWindow('./'))); });
