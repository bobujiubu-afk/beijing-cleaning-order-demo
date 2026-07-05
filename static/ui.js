(function () {
  document.addEventListener("DOMContentLoaded", function () {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/static/sw.js").catch(function () {});
    }

    var menuButton = document.querySelector(".menu-toggle");
    var topbar = document.querySelector(".topbar");
    if (!menuButton || !topbar) return;
    menuButton.addEventListener("click", function () {
      var open = topbar.classList.toggle("menu-open");
      menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
})();
