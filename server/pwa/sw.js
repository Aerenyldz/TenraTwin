// TENRA Service Worker Auto-Purge
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((k) => caches.delete(k)));
    }).then(() => {
      return self.registration.unregister();
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Always fetch fresh from network
  event.respondWith(fetch(event.request));
});

