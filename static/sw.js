self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", function (event) {
  var payload = {
    title: "北京东科保洁有新订单",
    body: "有新的客户预约，请尽快联系！",
    url: "/admin?status=待联系",
    tag: "dongke-new-order",
    badgeCount: 1
  };

  if (event.data) {
    try {
      payload = Object.assign(payload, event.data.json());
    } catch (error) {
      payload.body = event.data.text() || payload.body;
    }
  }

  event.waitUntil((async function () {
    if (self.registration.setAppBadge && payload.badgeCount) {
      try {
        await self.registration.setAppBadge(Number(payload.badgeCount));
      } catch (error) {}
    }

    await self.registration.showNotification(payload.title, {
      body: payload.body,
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/icon-192.png",
      tag: payload.tag || "dongke-new-order",
      renotify: true,
      requireInteraction: true,
      vibrate: [260, 120, 260, 120, 420],
      data: { url: payload.url || "/admin?status=待联系" }
    });
  })());
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : "/admin?status=待联系";

  event.waitUntil(
    (self.registration.clearAppBadge ? self.registration.clearAppBadge().catch(function () {}) : Promise.resolve()).then(function () {
      return self.clients.matchAll({ type: "window", includeUncontrolled: true });
    }).then(function (clients) {
      for (var i = 0; i < clients.length; i += 1) {
        var client = clients[i];
        if ("focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
      return null;
    })
  );
});
