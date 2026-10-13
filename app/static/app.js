// 点格子取回当天的片段，就地展开；再点一次收起。
(() => {
  let openRow = null;
  let openDate = null;

  function close() {
    if (openRow) openRow.remove();
    if (openDate) {
      const cell = document.querySelector(`.day-cell[data-date="${openDate}"]`);
      if (cell) cell.classList.remove("is-selected");
    }
    openRow = null;
    openDate = null;
  }

  async function open(cell) {
    const date = cell.dataset.date;
    if (openDate === date) {
      close();
      return;
    }
    close();
    const response = await fetch(`/day/${date}`);
    const html = await response.text();
    const row = document.createElement("tr");
    row.className = "day-detail";
    row.innerHTML = `<td colspan="7"></td>`;
    row.firstElementChild.innerHTML = html;
    cell.closest("tr").after(row);
    cell.classList.add("is-selected");
    openRow = row;
    openDate = date;
  }

  document.addEventListener("click", (event) => {
    const cell = event.target.closest(".day-cell[data-date]");
    if (cell) open(cell);
  });
})();
