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
  var watchModeEnabled = localStorage.getItem("dongkeWatchModeEnabled") === "1" || new URLSearchParams(window.location.search).get("reminder_mode") === "1";
  var audioContext = null;
  var defaultIconHref = null;
  var soundFile = "/static/sounds/new-order.wav";
  var alarmRepeatTimer = null;
  var wakeLock = null;

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

  function acquireWakeLock() {
    if (!("wakeLock" in navigator) || !navigator.wakeLock.request) return;
    navigator.wakeLock.request("screen")
      .then(function (lock) {
        wakeLock = lock;
        wakeLock.addEventListener("release", function () {
          wakeLock = null;
        });
      })
      .catch(function () {});
  }

  function enableWatchMode() {
    watchModeEnabled = true;
    localStorage.setItem("dongkeWatchModeEnabled", "1");
    soundEnabled = true;
    localStorage.setItem("dongkeSoundEnabled", "1");
    ensureAudioContext();
    acquireWakeLock();
    playSingleNewOrderSound();
    updateWatchButton();
    setStatus("手机值守模式已开启：请保持此后台页面打开，来单会全屏提醒并重复响铃。", false);
  }

  function updateWatchButton() {
    var button = qs("#watchModeButton");
    if (!button) return;
    button.textContent = watchModeEnabled ? "手机值守模式已开启" : "开启手机值守模式";
    button.classList.toggle("secondary-action", watchModeEnabled);
  }

  function requestNotificationPermission() {
    if (!("Notification" in window)) {
      setStatus("当前浏览器不支持系统通知。", true);
      var button = qs("#enableNotificationButton");
      if (button) button.hidden = true;
      return;
    }

    Notification.requestPermission().then(function (permission) {
      notificationEnabled = permission === "granted";
      localStorage.setItem("dongkeNotificationEnabled", notificationEnabled ? "1" : "0");
      if (notificationEnabled && "serviceWorker" in navigator) {
        navigator.serviceWorker.ready.catch(function () {});
      }
      setStatus(notificationEnabled ? "手机/系统通知提醒已开启。" : "系统通知未授权。", !notificationEnabled);
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
    showWatchOverlay(data);
    startTitleFlash();
    playNewOrderSound(true);
    showNewOrderNotification(testOrder);
    setStatus("已触发测试提醒：应出现提示音、震动、标题闪烁和通知。", false);
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

  function drawBadgeIcon(count) {
    var canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    var context = canvas.getContext("2d");
    context.fillStyle = "#176f5c";
    context.fillRect(0, 0, 64, 64);
    context.fillStyle = "#ffffff";
    context.font = "bold 26px Microsoft YaHei, Arial";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("东", 32, 34);

    if (count > 0) {
      context.fillStyle = "#d42121";
      context.beginPath();
      context.arc(49, 15, 14, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#ffffff";
      context.font = "bold 15px Arial";
      context.fillText(count > 9 ? "9+" : String(count), 49, 16);
    }

    return canvas.toDataURL("image/png");
  }

  function updateFaviconBadge(count) {
    var link = ensureFavicon();
    link.href = count > 0 ? drawBadgeIcon(count) : defaultIconHref;
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

  function showWatchOverlay(data) {
    var overlay = qs("#watchOverlay");
    if (!overlay) return;
    var order = data && data.latest_order ? data.latest_order : {};
    var text = [order.customer_name || "新客户", order.service_type || "预约服务", order.phone || ""].filter(Boolean).join("｜");
    setText("#watchOrderText", text || "请尽快联系客户");
    overlay.classList.remove("hidden");
    document.body.classList.add("watch-alerting");
    startRepeatingAlarm();
  }

  function hideWatchOverlay() {
    var overlay = qs("#watchOverlay");
    if (overlay) overlay.classList.add("hidden");
    document.body.classList.remove("watch-alerting");
    stopRepeatingAlarm();
  }

  function startRepeatingAlarm() {
    if (!watchModeEnabled || alarmRepeatTimer) return;
    alarmRepeatTimer = window.setInterval(function () {
      playNewOrderSound(true);
      vibrateReminder();
    }, 10000);
  }

  function stopRepeatingAlarm() {
    if (alarmRepeatTimer) {
      window.clearInterval(alarmRepeatTimer);
      alarmRepeatTimer = null;
    }
  }

  function handleNewOrder(data) {
    showMessageAlert(data);
    showWatchOverlay(data);
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

    var watchButton = qs("#watchModeButton");
    if (watchButton) {
      watchButton.addEventListener("click", enableWatchMode);
      updateWatchButton();
      if (watchModeEnabled) {
        acquireWakeLock();
        setStatus("手机值守模式已开启，请保持后台页面打开。", false);
      }
    }

    var notificationButton = qs("#enableNotificationButton");
    if (notificationButton) {
      if (!("Notification" in window)) {
        notificationButton.hidden = true;
      } else {
        notificationButton.addEventListener("click", requestNotificationPermission);
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
        hideWatchOverlay();
        stopTitleFlash();
      });
    }

    var viewButton = qs("#viewPendingButton");
    if (viewButton) viewButton.addEventListener("click", viewPendingOrders);

    var watchDismissButton = qs("#watchDismissButton");
    if (watchDismissButton) {
      watchDismissButton.addEventListener("click", function () {
        hideWatchOverlay();
        hideMessageAlert();
        stopTitleFlash();
      });
    }

    var watchViewButton = qs("#watchViewButton");
    if (watchViewButton) watchViewButton.addEventListener("click", viewPendingOrders);

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
    stopRepeatingAlarm();
  });

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && soundEnabled) ensureAudioContext();
    if (!document.hidden && watchModeEnabled) acquireWakeLock();
  });
})();
