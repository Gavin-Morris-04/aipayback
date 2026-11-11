// Click a column header to sort a .sortable table. No dependencies.
document.querySelectorAll("table.sortable").forEach(function (table) {
  table.querySelectorAll("th").forEach(function (th, index) {
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
        var cmp = numeric ? parseFloat(x) - parseFloat(y) : x.localeCompare(y);
        return ascending ? cmp : -cmp;
      });
      rows.forEach(function (r) { body.appendChild(r); });
    }
    th.addEventListener("click", sort);
    th.addEventListener("keydown", function (e) { if (e.key === "Enter") { sort(); } });
  });
});
