(function () {
  function qs(selector) {
    return document.querySelector(selector);
  }

  function setText(selector, value) {
    var node = qs(selector);
    if (node) node.textContent = value;
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
  }

  function isEditing() {
    var active = document.activeElement;
    if (active && ["INPUT", "TEXTAREA", "SELECT"].indexOf(active.tagName) !== -1) {
      return true;
    }
    return Boolean(document.querySelector(".order-detail[open]"));
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
        if (!isEditing() && typeof data.html === "string") {
          list.innerHTML = data.html;
        }
      })
      .catch(function () {
        // 静默失败，避免临时网络波动打断老板操作。
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var filterButton = qs(".filter-toggle");
    var filters = qs("#adminFilters");
    if (filterButton && filters) {
      filterButton.addEventListener("click", function () {
        var open = filters.classList.toggle("filters-open");
        filterButton.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }

    if (qs("#orderList")) {
      window.setInterval(refreshOrders, 5000);
    }
  });
})();
