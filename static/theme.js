// Dark / light mode switch. The choice is remembered in this browser.
(function () {
  var root = document.documentElement;
  function refreshLabels() {
    var dark = root.getAttribute("data-theme") === "dark";
    document.querySelectorAll(".theme-toggle").forEach(function (button) {
      button.setAttribute("title", dark ? "Switch to light mode" : "Switch to dark mode");
      button.setAttribute("aria-pressed", dark ? "true" : "false");
    });
  }
  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest(".theme-toggle") : null;
    if (!button) { return; }
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (error) { /* storage may be blocked */ }
    refreshLabels();
    if (window.Chart && window.initCharts) {
      Object.keys(Chart.instances).forEach(function (id) { Chart.instances[id].destroy(); });
      window.initCharts();
    }
  });
  refreshLabels();
})();
