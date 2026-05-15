/* =========================================================
   HKEX Disclosure of Interest — frontend
   ========================================================= */

const DATA_URL = "data/filings.json";
const PAGE_SIZE = 50;

/* ---- state ---- */
let allFilings   = [];
let filtered     = [];
let currentPage  = 1;
let sortCol      = "filing_date";
let sortDir      = -1;   // -1 = desc, 1 = asc

/* ---- DOM refs ---- */
const tbody       = document.getElementById("tbl-body");
const pagination  = document.getElementById("pagination");
const statsTotal  = document.getElementById("stat-total");
const statsBuys   = document.getElementById("stat-buys");
const statsSells  = document.getElementById("stat-sells");
const lastUpdated = document.getElementById("last-updated");
const searchInput = document.getElementById("search");
const filterType  = document.getElementById("filter-type");
const filterDate  = document.getElementById("filter-date");

/* ---- bootstrap ---- */
async function init() {
  showLoading();
  try {
    const res = await fetch(`${DATA_URL}?_=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allFilings = data.filings || [];
    if (data.last_updated) {
      lastUpdated.textContent = `Last updated: ${formatTs(data.last_updated)}`;
    }
  } catch (err) {
    showError(err.message);
    return;
  }

  applyFilters();
  bindEvents();
}

/* ---- event wiring ---- */
function bindEvents() {
  searchInput.addEventListener("input",  () => { currentPage = 1; applyFilters(); });
  filterType .addEventListener("change", () => { currentPage = 1; applyFilters(); });
  filterDate .addEventListener("change", () => { currentPage = 1; applyFilters(); });

  document.querySelectorAll("th[data-col]").forEach(th => {
    th.addEventListener("click", () => {
      const col = th.dataset.col;
      if (sortCol === col) {
        sortDir *= -1;
      } else {
        sortCol = col;
        sortDir = -1;
      }
      updateSortUI();
      currentPage = 1;
      renderTable();
    });
  });
}

/* ---- filtering + sorting ---- */
function applyFilters() {
  const q    = searchInput.value.trim().toLowerCase();
  const type = filterType.value;
  const date = filterDate.value;   // YYYY-MM-DD from <input type="date">

  filtered = allFilings.filter(f => {
    if (type === "buy"  && f.is_disposal)        return false;
    if (type === "sell" && !f.is_disposal)        return false;
    if (date) {
      const fd = normalizeDate(f.filing_date);   // to YYYY-MM-DD
      if (fd !== date) return false;
    }
    if (q) {
      const hay = [
        f.stock_code, f.company_name, f.person_entity,
        f.capacity, f.nature_of_interest, f.serial,
      ].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  updateStats();
  renderTable();
}

/* ---- render ---- */
function renderTable() {
  const sorted = [...filtered].sort((a, b) => {
    let av = a[sortCol] ?? "";
    let bv = b[sortCol] ?? "";
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
    return String(av).localeCompare(String(bv)) * sortDir;
  });

  const start = (currentPage - 1) * PAGE_SIZE;
  const page  = sorted.slice(start, start + PAGE_SIZE);

  if (page.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12" class="state-msg">No filings found.</td></tr>`;
    renderPagination(0);
    return;
  }

  tbody.innerHTML = page.map(rowHTML).join("");
  renderPagination(sorted.length);
}

function rowHTML(f) {
  const chgPct   = f.pct_change_from_previous;
  const chgShares= f.share_change_from_previous;

  const chgPctStr = chgPct != null
    ? `<span class="${chgPct > 0 ? "chg-positive" : chgPct < 0 ? "chg-negative" : "chg-neutral"}">${chgPct > 0 ? "+" : ""}${chgPct.toFixed(2)}%</span>`
    : `<span class="chg-neutral">—</span>`;

  const chgSharesStr = chgShares != null
    ? `<span class="${chgShares > 0 ? "chg-positive" : chgShares < 0 ? "chg-negative" : "chg-neutral"}">${chgShares > 0 ? "+" : ""}${fmtNum(chgShares)}</span>`
    : `<span class="chg-neutral">—</span>`;

  const badge = f.is_disposal
    ? `<span class="badge-sell">SELL</span>`
    : (f.shares_acquired_disposed > 0 || (chgShares != null && chgShares > 0))
      ? `<span class="badge-buy">BUY</span>`
      : "";

  const newsQuery = encodeURIComponent(`${f.person_entity} ${f.company_name} shares`);
  const newsLink  = `https://www.google.com/search?q=${newsQuery}&tbm=nws`;
  const hkexQuery = encodeURIComponent(`site:hkexnews.hk ${f.company_name}`);

  const nature = f.nature_of_interest || f.capacity || "—";

  const reportCell = f.is_disposal
    ? `<a href="${newsLink}" target="_blank" rel="noopener">News ↗</a>`
    : `—`;

  return `
<tr>
  <td><a class="serial-link" href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.serial || "—")}</a></td>
  <td style="white-space:nowrap">${esc(f.filing_date || "")}</td>
  <td style="white-space:nowrap">${esc(f.event_date  || "")}</td>
  <td><span class="stock-code">${esc(f.stock_code || "")}</span></td>
  <td class="company-name">${esc(f.company_name || "")}</td>
  <td class="person-name">${esc(f.person_entity || "")}</td>
  <td>${f.capacity ? `<span class="capacity-tag">${esc(f.capacity)}</span>` : "—"}</td>
  <td style="text-align:right;white-space:nowrap">${fmtNum(f.shares_held_after || f.shares_held_before || 0)}</td>
  <td style="text-align:right;white-space:nowrap">${chgSharesStr}&nbsp;${badge}</td>
  <td style="text-align:right;white-space:nowrap">${chgPctStr}</td>
  <td class="nature-cell"><a href="https://www.google.com/search?q=${encodeURIComponent(f.person_entity + ' ' + f.company_name + ' director shareholder')}&num=10" target="_blank" rel="noopener" title="Search relationship">${esc(nature)}</a></td>
  <td class="report-cell">${reportCell}</td>
</tr>`;
}

/* ---- stats bar ---- */
function updateStats() {
  statsTotal.textContent = filtered.length;
  statsBuys .textContent = filtered.filter(f => !f.is_disposal).length;
  statsSells.textContent = filtered.filter(f =>  f.is_disposal).length;
}

/* ---- sort UI ---- */
function updateSortUI() {
  document.querySelectorAll("th[data-col]").forEach(th => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.col === sortCol) {
      th.classList.add(sortDir === 1 ? "sort-asc" : "sort-desc");
    }
  });
}

/* ---- pagination ---- */
function renderPagination(total) {
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) { pagination.innerHTML = ""; return; }

  let html = `<span class="pg-info">Page ${currentPage} of ${pages}&nbsp;&nbsp;</span>`;
  html += `<button ${currentPage === 1 ? "disabled" : ""} onclick="goPage(${currentPage - 1})">‹ Prev</button>`;

  const windowSize = 5;
  let start = Math.max(1, currentPage - 2);
  let end   = Math.min(pages, start + windowSize - 1);
  if (end - start < windowSize - 1) start = Math.max(1, end - windowSize + 1);

  if (start > 1)     html += `<button onclick="goPage(1)">1</button>${start > 2 ? '<span>…</span>' : ""}`;
  for (let p = start; p <= end; p++) {
    html += `<button class="${p === currentPage ? "active" : ""}" onclick="goPage(${p})">${p}</button>`;
  }
  if (end < pages)   html += `${end < pages - 1 ? '<span>…</span>' : ""}<button onclick="goPage(${pages})">${pages}</button>`;

  html += `<button ${currentPage === pages ? "disabled" : ""} onclick="goPage(${currentPage + 1})">Next ›</button>`;
  pagination.innerHTML = html;
}

window.goPage = function(p) {
  currentPage = p;
  renderTable();
  window.scrollTo({ top: 0, behavior: "smooth" });
};

/* ---- helpers ---- */
function fmtNum(n) {
  if (!n && n !== 0) return "—";
  return Number(n).toLocaleString("en-US");
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normalizeDate(s) {
  if (!s) return "";
  // DD/MM/YYYY -> YYYY-MM-DD
  const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return s;  // already YYYY-MM-DD or unknown
}

function formatTs(iso) {
  try {
    return new Date(iso).toLocaleString("en-HK", {
      timeZone: "Asia/Hong_Kong",
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    }) + " HKT";
  } catch {
    return iso;
  }
}

/* ---- loading / error states ---- */
function showLoading() {
  tbody.innerHTML = `
    <tr>
      <td colspan="12" class="state-msg">
        <div class="spinner"></div>
        Loading filings…
      </td>
    </tr>`;
}

function showError(msg) {
  tbody.innerHTML = `
    <tr>
      <td colspan="12" class="state-msg">
        Failed to load data: ${esc(msg)}<br>
        <small>Run the scraper first or check the <code>data/filings.json</code> file.</small>
      </td>
    </tr>`;
}

/* ---- kick off ---- */
init();
