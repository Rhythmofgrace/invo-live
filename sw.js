// Service Worker for Background Device & System Push Notifications
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
  const data = event.data;
  if (data && data.type === 'SHOW_NOTIFICATION') {
    self.registration.showNotification(data.title, {
      body: data.message,
      icon: 'https://bin.bnbstatic.com/static/images/common/favicon.ico',
      badge: 'https://bin.bnbstatic.com/static/images/common/favicon.ico',
      vibrate: [200, 100, 200],
      tag: data.id || 'invo_alert',
      renotify: true
    });
  }
});

