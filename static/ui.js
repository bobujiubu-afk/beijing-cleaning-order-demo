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

    document.addEventListener("click", function (event) {
      if (!topbar.classList.contains("menu-open")) return;
      if (topbar.contains(event.target)) return;
      topbar.classList.remove("menu-open");
      menuButton.setAttribute("aria-expanded", "false");
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      topbar.classList.remove("menu-open");
      menuButton.setAttribute("aria-expanded", "false");
    });
  });
})();
