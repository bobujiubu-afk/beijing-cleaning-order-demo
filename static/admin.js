(function () {
  var normalTitle = "北京东科订单后台";
  var newTitle = "【新订单】北京东科订单后台";
  var lastSeenOrderId = null;
  var lastSeenNewCount = null;
  var titleTimer = null;
  var titleFlashOn = false;
  var lastSoundAt = 0;
  var soundBurstTimer = null;
  var soundEnabled = localStorage.getItem("dongkeSoundEnabled") === "1";
  var notificationEnabled = localStorage.getItem("dongkeNotificationEnabled") === "1";
  var audioContext = null;
  var defaultIconHref = null;
  var soundFile = "/static/sounds/new-order.wav";

  function qs(selector) {
    return document.querySelector(selector);
  }

  function setText(selector, value) {
    var node = qs(selector);
    if (node) node.textContent = value;
  }

  function setStatus(message, warning) {
    var node = qs("#reminderStatus");
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("warning", Boolean(warning));
  }

  function updateCounts(data) {
    var pending = data.pending_count || 0;
    var alertBox = qs("#newOrderAlert");
    var dot = qs("#pendingDot");
    if (alertBox) alertBox.classList.toggle("has-new", pending > 0);
    if (dot) dot.classList.toggle("hidden", pending === 0);
    setText("#pendingMessage", pending > 0 ? "当前有 " + pending + " 个待联系客户" : "暂无待联系客户");
    setText("#todayNewCount", data.today_new || 0);
    setText("#waitingCount", data.counts && data.counts["待联系"] ? data.counts["待联系"] : 0);
    setText("#contactedCount", data.counts && data.counts["已联系"] ? data.counts["已联系"] : 0);
    setText("#dealedCount", data.counts && data.counts["已成交"] ? data.counts["已成交"] : 0);

    if (pending === 0) {
      stopTitleFlash();
      hideMessageAlert();
    }
    updateAppBadge(pending);
  }

  function isEditing() {
    var active = document.activeElement;
    if (active && ["INPUT", "TEXTAREA", "SELECT"].indexOf(active.tagName) !== -1) {
      return true;
    }
    return Boolean(document.querySelector(".order-detail[open]"));
  }

  function ensureAudioContext() {
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return null;
    if (!audioContext) audioContext = new AudioContextClass();
    if (audioContext.state === "suspended") audioContext.resume().catch(function () {});
    return audioContext;
  }

  function beepFallback() {
    var context = ensureAudioContext();
    if (!context) {
      setStatus("当前浏览器不支持声音提醒。", true);
      return;
    }

    [0, 0.42, 0.86].forEach(function (offset, index) {
      var start = context.currentTime + offset;
      var oscillator = context.createOscillator();
      var gain = context.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(index === 1 ? 1040 : 880, start);
      oscillator.frequency.exponentialRampToValueAtTime(index === 1 ? 1320 : 1180, start + 0.16);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.28, start + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.36);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.38);
    });
  }

  function vibrateReminder() {
    if ("vibrate" in navigator) {
      navigator.vibrate([260, 120, 260, 120, 420]);
    }
  }

  function playSingleNewOrderSound() {
    var audio = new Audio(soundFile);
    audio.preload = "auto";
    audio.volume = 0.9;

    return audio.play().catch(function () {
      try {
        beepFallback();
      } catch (error) {
        setStatus("声音被浏览器拦截，请点击“开启声音提醒”。", true);
      }
    });
  }

  function playNewOrderSound(force) {
    if (!soundEnabled) {
      setStatus("浏览器限制自动播放，请先点击“开启声音提醒”。", true);
      return;
    }

    var now = Date.now();
    if (!force && now - lastSoundAt < 8000) return;
    lastSoundAt = now;

    if (soundBurstTimer) window.clearInterval(soundBurstTimer);
    soundBurstTimer = null;
    ensureAudioContext();
    vibrateReminder();
    playSingleNewOrderSound();
  }

  function enableSoundAlert() {
    soundEnabled = true;
    localStorage.setItem("dongkeSoundEnabled", "1");
    try {
      ensureAudioContext();
      vibrateReminder();
      playSingleNewOrderSound();
      setStatus("声音提醒已开启，已播放测试铃声。", false);
    } catch (error) {
      setStatus("浏览器限制自动播放，请再点一次“开启声音提醒”。", true);
    }
  }

  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - base64String.length % 4) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var rawData = window.atob(base64);
    var outputArray = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; i += 1) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function ensureServiceWorkerReady() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      return Promise.reject(new Error("push unsupported"));
    }
    return navigator.serviceWorker.ready;
  }

  function explainPushSupportProblem(error) {
    var message = String(error && error.message ? error.message : error);
    if (!window.isSecureContext) {
      return "当前不是安全网址，手机系统不会允许推送。请使用 https 线上地址。";
    }
    if (!("serviceWorker" in navigator)) {
      return "当前浏览器不支持后台推送，请换 Safari/Chrome，并从桌面图标打开。";
    }
    if (!("PushManager" in window)) {
      return "当前手机浏览器不支持网页后台推送。苹果手机请添加到主屏幕后从桌面图标打开。";
    }
    if (!("Notification" in window)) {
      return "当前手机浏览器不支持系统通知。";
    }
    if (Notification.permission === "denied") {
      return "通知权限已被拒绝，请到手机系统设置里允许此网页/应用通知。";
    }
    if (message.indexOf("permission") !== -1 || message.indexOf("denied") !== -1) {
      return "你没有允许通知权限，手机系统不会弹新订单消息。";
    }
    if (message.indexOf("unsupported") !== -1) {
      return "当前浏览器不支持网页后台推送，请换 Safari/Chrome 并从桌面图标打开。";
    }
    return "手机推送没有开启成功。请从桌面图标打开后台，允许通知后再试。";
  }

  function registerSubscription(subscription) {
    return fetch("/api/push-subscribe", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(subscription),
      cache: "no-store"
    }).then(function (response) {
      if (!response.ok) throw new Error("subscribe failed");
      return subscription;
    });
  }

  function enablePushNotifications() {
    setStatus("正在开启手机消息推送...", false);
    if (!("Notification" in window)) {
      setStatus(explainPushSupportProblem(new Error("notification unsupported")), true);
      return;
    }

    Notification.requestPermission()
      .then(function (permission) {
        notificationEnabled = permission === "granted";
        localStorage.setItem("dongkeNotificationEnabled", notificationEnabled ? "1" : "0");
        if (!notificationEnabled) throw new Error("notification denied");
        return Promise.all([
          ensureServiceWorkerReady(),
          fetch("/api/push-public-key", { cache: "no-store" }).then(function (response) {
            if (!response.ok) throw new Error("public key failed");
            return response.json();
          })
        ]);
      })
      .then(function (results) {
        var registration = results[0];
        var publicKey = results[1].publicKey;
        var options = {
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey)
        };
        return registration.pushManager.getSubscription().then(function (existing) {
          if (existing) return registerSubscription(existing);
          return registration.pushManager.subscribe(options).then(registerSubscription);
        }).catch(function () {
          return registration.pushManager.getSubscription()
            .then(function (existing) {
              if (existing) return existing.unsubscribe();
              return true;
            })
            .then(function () {
              return registration.pushManager.subscribe(options);
            })
            .then(registerSubscription);
        });
      })
      .then(function () {
        setStatus("手机消息推送已开启。新订单会发到手机通知栏；桌面角标是否显示取决于手机系统。", false);
      })
      .catch(function (error) {
        setStatus(explainPushSupportProblem(error), true);
      });
  }

  function sendServerTestPush() {
    return fetch("/api/push-test", {
      method: "POST",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      cache: "no-store"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("test push failed");
        return response.json();
      })
      .then(function (data) {
        if (data.sent > 0) {
          setStatus("已发送服务器测试推送，请看手机系统通知栏。", false);
        } else {
          setStatus("还没有可用的手机推送订阅，请先点“开启手机消息推送”。", true);
        }
      })
      .catch(function () {
        setStatus("服务器测试推送失败，请重新开启手机消息推送。", true);
      });
  }

  function showNewOrderNotification(order) {
    if (!notificationEnabled || !("Notification" in window) || Notification.permission !== "granted" || !order) {
      return;
    }

    var body = [order.customer_name, order.service_type, order.phone].filter(Boolean).join("｜");
    var options = {
      body: body,
      icon: "/static/icons/icon-192.png",
      badge: "/static/icons/icon-192.png",
      tag: "dongke-new-order-" + order.id,
      renotify: true,
      requireInteraction: true,
      data: { url: "/admin?status=待联系" }
    };

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.ready
        .then(function (registration) {
          return registration.showNotification("北京东科保洁有新订单", options);
        })
        .catch(function () {
          showPageNotification(body, order);
        });
      return;
    }

    showPageNotification(body, order);
  }

  function testReminder() {
    var testOrder = {
      id: "test-" + Date.now(),
      customer_name: "测试客户",
      service_type: "开荒保洁",
      phone: "13800000000"
    };
    var data = {
      pending_count: Number(qs("#waitingCount") ? qs("#waitingCount").textContent : 1) || 1,
      latest_order: testOrder
    };
    showMessageAlert(data);
    startTitleFlash();
    playNewOrderSound(true);
    showNewOrderNotification(testOrder);
    sendServerTestPush();
    setStatus("已发送测试：如果已开启手机消息推送，请看手机通知栏。", false);
  }

  function showPageNotification(body, order) {
    var notification = new Notification("北京东科保洁有新订单", {
      body: body,
      icon: "/static/icons/icon-192.png",
      tag: "dongke-new-order-" + order.id,
      renotify: true,
      requireInteraction: true
    });

    notification.onclick = function () {
      window.focus();
      window.location.href = "/admin?status=待联系";
      notification.close();
    };
  }

  function startTitleFlash() {
    if (titleTimer) return;
    titleFlashOn = true;
    document.title = newTitle;
    titleTimer = window.setInterval(function () {
      titleFlashOn = !titleFlashOn;
      document.title = titleFlashOn ? newTitle : normalTitle;
    }, 900);
  }

  function stopTitleFlash() {
    if (titleTimer) {
      window.clearInterval(titleTimer);
      titleTimer = null;
    }
    document.title = normalTitle;
  }

  function ensureFavicon() {
    var link = document.querySelector("link[rel='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    if (!defaultIconHref) {
      defaultIconHref = link.href || "/static/icons/icon-192.png";
    }
    return link;
  }

  function updateFaviconBadge(count) {
    var link = ensureFavicon();
    link.href = defaultIconHref;
  }

  function updateAppBadge(count) {
    var safeCount = Math.max(0, Number(count || 0));
    updateFaviconBadge(safeCount);
    if ("setAppBadge" in navigator && safeCount > 0) {
      navigator.setAppBadge(safeCount).catch(function () {});
    } else if ("clearAppBadge" in navigator && safeCount === 0) {
      navigator.clearAppBadge().catch(function () {});
    }
  }

  function showMessageAlert(data) {
    var box = qs("#newMessageAlert");
    if (!box) return;
    box.classList.remove("hidden");
    setText("#newMessageText", "当前有 " + (data.pending_count || 0) + " 个待联系客户");
  }

  function hideMessageAlert() {
    var box = qs("#newMessageAlert");
    if (box) box.classList.add("hidden");
  }

  function handleNewOrder(data) {
    showMessageAlert(data);
    startTitleFlash();
    playNewOrderSound(true);
    showNewOrderNotification(data.latest_order);
  }

  function maybeTriggerReminder(data) {
    var latestId = Number(data.latest_order_id || 0);
    var newCount = Number(data.new_count || 0);

    if (lastSeenOrderId === null) {
      lastSeenOrderId = latestId;
      lastSeenNewCount = newCount;
      return;
    }

    if (latestId > lastSeenOrderId || newCount > lastSeenNewCount) {
      handleNewOrder(data);
    }

    lastSeenOrderId = Math.max(lastSeenOrderId, latestId);
    lastSeenNewCount = newCount;
  }

  function refreshOrders() {
    var list = qs("#orderList");
    if (!list) return;
    fetch("/api/orders" + window.location.search, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      cache: "no-store"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("refresh failed");
        return response.json();
      })
      .then(function (data) {
        updateCounts(data);
        maybeTriggerReminder(data);
        if (!isEditing() && typeof data.html === "string") {
          list.innerHTML = data.html;
        }
      })
      .catch(function () {
        // 静默失败，避免临时网络波动打断老板操作。
      });
  }

  function viewPendingOrders() {
    hideMessageAlert();
    stopTitleFlash();
    var params = new URLSearchParams(window.location.search);
    if (params.get("status") !== "待联系") {
      window.location.href = "/admin?status=待联系";
      return;
    }
    var list = qs("#orderList");
    if (list) list.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function saveOrderField(orderId, payload) {
    return fetch("/orders/" + orderId + "/update", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify(payload),
      cache: "no-store"
    })
      .then(function (response) {
        if (!response.ok) throw new Error("save failed");
        return response.json();
      })
      .then(function () {
        setStatus("已保存。", false);
        refreshOrders();
      })
      .catch(function () {
        setStatus("保存失败，请稍后重试。", true);
      });
  }

  function saveAmountInput(input) {
    if (!input || !input.dataset.orderId) return;
    saveOrderField(input.dataset.orderId, { amount: input.value });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.title = normalTitle;
    ensureFavicon();
    updateFaviconBadge(0);

    var filterButton = qs(".filter-toggle");
    var filters = qs("#adminFilters");
    if (filterButton && filters) {
      filterButton.addEventListener("click", function () {
        var open = filters.classList.toggle("filters-open");
        filterButton.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    if (filters) {
      var customDate = filters.querySelector("input[name='custom_date']");
      var dateScope = filters.querySelector("input[name='date_scope']");
      if (customDate && dateScope) {
        customDate.addEventListener("change", function () {
          if (customDate.value) {
            dateScope.value = "custom";
            filters.submit();
          }
        });
      }
    }

    var settingsButton = qs("#reminderSettingsButton");
    var settingsPanel = qs("#reminderSettingsPanel");
    if (settingsButton && settingsPanel) {
      settingsButton.addEventListener("click", function () {
        var open = settingsPanel.classList.toggle("hidden") === false;
        settingsButton.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    var soundButton = qs("#enableSoundButton");
    if (soundButton) {
      soundButton.addEventListener("click", enableSoundAlert);
      if (soundEnabled) setStatus("声音提醒已开启，如不响请再点一次按钮。", false);
    }

    var testButton = qs("#testReminderButton");
    if (testButton) testButton.addEventListener("click", testReminder);

    var notificationButton = qs("#enableNotificationButton");
    if (notificationButton) {
      if (!("Notification" in window)) {
        notificationButton.hidden = true;
      } else {
        notificationButton.addEventListener("click", enablePushNotifications);
        if (notificationEnabled && Notification.permission !== "granted") {
          localStorage.setItem("dongkeNotificationEnabled", "0");
          notificationEnabled = false;
        }
      }
    }

    var dismissButton = qs("#dismissReminderButton");
    if (dismissButton) {
      dismissButton.addEventListener("click", function () {
        hideMessageAlert();
        stopTitleFlash();
      });
    }

    var viewButton = qs("#viewPendingButton");
    if (viewButton) viewButton.addEventListener("click", viewPendingOrders);

    document.addEventListener("change", function (event) {
      var target = event.target;
      if (target.classList.contains("status-select") && target.dataset.orderId) {
        saveOrderField(target.dataset.orderId, { status: target.value });
      }
    });

    document.addEventListener("click", function (event) {
      var button = event.target.closest(".tiny-save");
      if (!button) return;
      var wrapper = button.closest(".amount-edit");
      var input = wrapper ? wrapper.querySelector(".quick-amount") : document.querySelector(".quick-amount[data-order-id='" + button.dataset.orderId + "']");
      saveAmountInput(input);
    });

    document.addEventListener("blur", function (event) {
      if (event.target.classList && event.target.classList.contains("quick-amount")) {
        saveAmountInput(event.target);
      }
    }, true);

    if (qs("#orderList")) {
      refreshOrders();
      window.setInterval(refreshOrders, 5000);
    }
  });

  window.addEventListener("beforeunload", function () {
    if (titleTimer) window.clearInterval(titleTimer);
    if (soundBurstTimer) window.clearInterval(soundBurstTimer);
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && soundEnabled) ensureAudioContext();
  });
})();
