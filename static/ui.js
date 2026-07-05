(function () {
  document.addEventListener("DOMContentLoaded", function () {
    var menuButton = document.querySelector(".menu-toggle");
    var topbar = document.querySelector(".topbar");
    if (!menuButton || !topbar) return;
    menuButton.addEventListener("click", function () {
      var open = topbar.classList.toggle("menu-open");
      menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });
})();
