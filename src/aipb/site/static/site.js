// Small progressive enhancements. No dependencies; every page works without JavaScript.

// Click a column header to sort a .sortable table (headers marked .nosort are skipped).
document.querySelectorAll("table.sortable").forEach(function (table) {
  table.querySelectorAll("th").forEach(function (th, index) {
    if (th.classList.contains("nosort")) { return; }
    th.tabIndex = 0;
    function sort() {
      var numeric = th.dataset.type === "num";
      var ascending = th.getAttribute("aria-sort") !== "ascending";
      table.querySelectorAll("th").forEach(function (h) { h.removeAttribute("aria-sort"); });
      th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      var body = table.tBodies[0];
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var x = a.cells[index].textContent.trim();
        var y = b.cells[index].textContent.trim();
        var cmp = numeric ? (parseFloat(x) || 0) - (parseFloat(y) || 0) : x.localeCompare(y);
        return ascending ? cmp : -cmp;
      });
      rows.forEach(function (r) { body.appendChild(r); });
    }
    th.addEventListener("click", sort);
    th.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
    });
  });
});

// Status filter on company pages.
document.querySelectorAll(".filters").forEach(function (group) {
  var cards = document.querySelectorAll(".plist .pcard");
  var buttons = group.querySelectorAll(".filter");
  group.hidden = false;
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      var want = button.dataset.filter;
      buttons.forEach(function (b) {
        var on = b === button;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      cards.forEach(function (card) {
        card.hidden = want !== "all" && card.dataset.status !== want;
      });
    });
  });
});
