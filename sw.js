/* RewardHub — service worker for offline shell + same-origin cache */
const CACHE_NAME = 'rewardhub-pwa-v21';

const PRECACHE_URLS = [
  './',
  './index.html',
  './manifest.webmanifest',
  './guhan.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return Promise.all(
        PRECACHE_URLS.map(function (url) {
          return cache.add(new Request(url, { cache: 'reload' })).catch(function () {
            return null;
          });
        })
      );
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (k) { return k !== CACHE_NAME; })
          .map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  if (event.request.method !== 'GET') return;

  var url;
  try {
    url = new URL(event.request.url);
  } catch (e) {
    return;
  }

  if (url.origin !== self.location.origin) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(function (response) {
        if (response && response.status === 200) {
          var resClone = response.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(event.request, resClone);
          });
        }
        return response;
      })
      .catch(function () {
        return caches.match(event.request).then(function (hit) {
          if (hit) return hit;
          if (event.request.mode === 'navigate' || (event.request.destination || '') === 'document') {
            return caches.match('./index.html').then(function (page) {
              return page || caches.match('index.html');
            });
          }
        });
      })
  );
});
