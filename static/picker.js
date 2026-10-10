function initPicker(cfg) {
  const products = cfg.products;      // [{id, name, category, unit, price, stock, low}]
  const byId = new Map(products.map(p => [p.id, p]));
  const $ = id => document.getElementById(id);
  const search = $('pk-search'), clearBtn = $('pk-clear'), results = $('pk-results');
  const foundEl = $('pk-found'), selAllBtn = $('pk-select-all'), browseBtn = $('pk-browse'), addBtn = $('pk-add-selected');
  const listEl = $('pk-list'), emptyEl = $('pk-empty'), countEl = $('pk-count');
  const totalEl = $('pk-total'), submitBtn = $('pk-submit');
  const selected = new Set();
  const added = new Map();            // id -> qty
  const unitPrice = id => byId.get(id).price;
  const money = n => '₱' + Number(n).toFixed(2);
  const maxQty = p => cfg.capToStock ? p.stock : 999999;
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

  function stockPill(p) {
    const cls = p.stock <= 0 ? 'pk-pill-red' : (p.stock <= p.low ? 'pk-pill-yellow' : 'pk-pill-green');
    const txt = p.stock <= 0 ? 'Out of stock' : `${p.stock} ${p.unit}`;
    return el('span', 'pk-pill ' + cls, txt);
  }
  function matches() {
    const q = search.value.trim().toLowerCase();
    return products.filter(p => !q || p.name.toLowerCase().includes(q) || (p.category || '').toLowerCase().includes(q));
  }

  const PAGE = 8;                      // matches shown at a time (keeps the page short with hundreds of products)
  let limit = PAGE, browse = false;

  function renderResults() {
    const q = search.value.trim();
    const open = q !== '' || browse;
    clearBtn.hidden = !q;
    results.hidden = !open;
    selAllBtn.hidden = !open;
    browseBtn.textContent = browse ? 'Hide list' : 'Browse all';
    results.innerHTML = '';
    if (!open) {
      foundEl.textContent = `${products.length} products. Type a name or category to find one.`;
      updateAddBtn();
      return;
    }
    const list = matches();
    const shown = list.slice(0, limit);
    foundEl.textContent = list.length > shown.length
      ? `Showing ${shown.length} of ${list.length} matches`
      : `${list.length} match${list.length === 1 ? '' : 'es'}`;
    if (!list.length) results.appendChild(el('div', 'pk-none', 'No product found. Try another name.'));
    shown.forEach(p => {
      const inList = added.has(p.id);
      const row = el('label', 'pk-result' + (inList ? ' pk-in-list' : '') + (selected.has(p.id) ? ' pk-checked' : ''));
      const cb = el('input'); cb.type = 'checkbox'; cb.checked = selected.has(p.id); cb.disabled = inList;
      cb.addEventListener('change', () => { cb.checked ? selected.add(p.id) : selected.delete(p.id); row.classList.toggle('pk-checked', cb.checked); updateAddBtn(); });
      const box = el('span', 'pk-box'); box.innerHTML = '<i class="bi bi-check-lg"></i>';
      const info = el('div', 'pk-info');
      info.append(el('span', 'pk-name', p.name), el('span', 'pk-meta', p.category || ''));
      const right = el('div', 'pk-right');
      if (cfg.showPrice) right.appendChild(el('span', 'pk-price', money(p.price)));
      right.appendChild(inList ? el('span', 'pk-pill pk-pill-blue', 'In list') : stockPill(p));
      row.append(cb, box, info, right);
      results.appendChild(row);
    });
    if (list.length > shown.length) {
      const more = el('button', 'pk-more', `Show ${Math.min(PAGE, list.length - shown.length)} more`);
      more.type = 'button';
      more.addEventListener('click', () => { limit += PAGE; renderResults(); });
      results.appendChild(more);
    }
    updateAddBtn();
  }

  function updateAddBtn() {
    const n = selected.size;
    addBtn.disabled = n === 0;
    addBtn.innerHTML = n ? `<i class="bi bi-plus-lg"></i> Add ${n} selected to list` : '<i class="bi bi-plus-lg"></i> Add selected to list';
  }

  function addProduct(id, qty) {
    const p = byId.get(id);
    if (!p || maxQty(p) < 1) return;
    added.set(id, Math.min((added.get(id) || 0) + (qty || 1), maxQty(p)));
    renderList(); renderResults();
  }
  function addSelected() {
    selected.forEach(id => addProduct(id, 1));
    selected.clear(); search.value = ''; renderResults(); search.focus();
  }

  function setQty(id, v, input) {
    const p = byId.get(id);
    v = Math.max(1, Math.min(v, maxQty(p)));
    added.set(id, v);
    if (input) input.value = v;
    updateTotals();
  }

  function renderList() {
    listEl.innerHTML = '';
    added.forEach((qty, id) => {
      const p = byId.get(id);
      const row = el('div', 'pk-line');
      const hid = el('input'); hid.type = 'hidden'; hid.name = 'item_id'; hid.value = id;
      const info = el('div', 'pk-info');
      info.append(el('span', 'pk-name', p.name),
        el('span', 'pk-meta', (cfg.showPrice ? money(p.price) + ' each · ' : '') + `${p.stock} ${p.unit} in stock`));

      const stepper = el('div', 'pk-stepper');
      const minus = el('button', '', '−'); minus.type = 'button'; minus.title = 'Less';
      const q = el('input'); q.type = 'number'; q.name = 'quantity'; q.min = 1; q.value = qty; q.required = true;
      if (cfg.capToStock) q.max = p.stock;
      const plus = el('button', '', '+'); plus.type = 'button'; plus.title = 'More';
      minus.addEventListener('click', () => setQty(id, (added.get(id) || 1) - 1, q));
      plus.addEventListener('click', () => setQty(id, (added.get(id) || 1) + 1, q));
      q.addEventListener('input', () => { const v = parseInt(q.value, 10); if (v >= 1) setQty(id, v, v > maxQty(p) ? q : null); });
      stepper.append(minus, q, plus);

      const sub = el('span', 'pk-sub', cfg.showPrice ? money(unitPrice(id) * qty) : '');
      sub.dataset.id = id;
      const del = el('button', 'pk-del'); del.type = 'button'; del.title = 'Remove from list';
      del.innerHTML = '<i class="bi bi-trash3"></i>';
      del.addEventListener('click', () => { added.delete(id); renderList(); renderResults(); });
      row.append(hid, info, stepper, sub, del);
      listEl.appendChild(row);
    });
    emptyEl.style.display = added.size ? 'none' : 'flex';
    submitBtn.disabled = added.size === 0;
    updateTotals();
  }

  function updateTotals() {
    let total = 0;
    added.forEach((qty, id) => { total += unitPrice(id) * qty; });
    listEl.querySelectorAll('.pk-sub').forEach(s => {
      if (cfg.showPrice) { const id = parseInt(s.dataset.id, 10); s.textContent = money(unitPrice(id) * added.get(id)); }
    });
    countEl.textContent = added.size;
    if (totalEl) totalEl.textContent = money(total);
  }

  addBtn.addEventListener('click', addSelected);
  search.addEventListener('input', () => { limit = PAGE; renderResults(); });
  browseBtn.addEventListener('click', () => { browse = !browse; limit = PAGE; renderResults(); });
  clearBtn.addEventListener('click', () => { search.value = ''; limit = PAGE; renderResults(); search.focus(); });
  selAllBtn.addEventListener('click', () => {
    const vis = matches().slice(0, limit).filter(p => !added.has(p.id) && maxQty(p) >= 1);
    const allOn = vis.length && vis.every(p => selected.has(p.id));
    vis.forEach(p => allOn ? selected.delete(p.id) : selected.add(p.id));
    renderResults();
  });
  search.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (selected.size) { addSelected(); return; }
    const m = matches().filter(p => !added.has(p.id));
    if (search.value.trim() && m.length === 1) { addProduct(m[0].id, 1); search.value = ''; renderResults(); }
  });
  $(cfg.formId).addEventListener('submit', e => { if (!added.size) { e.preventDefault(); search.focus(); } });

  renderResults(); renderList();
  return { addProduct };
}