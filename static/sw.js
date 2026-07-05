self.addEventListener("install", function (event) {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  var targetUrl = event.notification.data && event.notification.data.url ? event.notification.data.url : "/admin?status=待联系";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clients) {
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
