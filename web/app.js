/* ===================== Verdant app ===================== */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const GC = { A: 'var(--g-a)', B: 'var(--g-b)', C: 'var(--g-c)', D: 'var(--g-d)', E: 'var(--g-e)' };
const gradeColor = (g) => GC[g] || 'var(--g-c)';
const esc = (s) => (s || '').toString().replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let LAST = null;
const LS = {
  get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set: (k, v) => localStorage.setItem(k, JSON.stringify(v)),
};

/* ---------- views & theme ---------- */
function showView(name) {
  $$('.view').forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === name));
  if (name === 'history') renderHistory();
  if (name === 'favorites') renderFavorites();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
$$('.tab').forEach(t => t.onclick = () => showView(t.dataset.view));

(function initTheme() {
  const saved = LS.get('theme', 'light');
  document.documentElement.setAttribute('data-theme', saved);
  $('#themeToggle').textContent = saved === 'dark' ? '☀️' : '🌙';
})();
$('#themeToggle').onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme');
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  $('#themeToggle').textContent = next === 'dark' ? '☀️' : '🌙';
  LS.set('theme', next);
};

/* ---------- API status ---------- */
fetch('/api/health').then(r => r.json()).then(h => {
  if (h.ok) $('#apiDot').classList.add('live');
  $('#apiDot').title = `mode: ${h.mode} · Bright Data: ${h.brightdata ? 'live' : 'cached'} · RunPod: ${h.runpod ? 'set' : 'off'}`;
}).catch(() => {});

/* ---------- input methods ---------- */
const panels = { search: '#m-search', barcode: '#m-barcode', camera: '#m-capture', upload: '#m-capture' };
let currentMethod = 'search';
$$('.method').forEach(m => m.onclick = () => selectMethod(m.dataset.method));

function selectMethod(method) {
  currentMethod = method;
  $$('.method').forEach(x => x.classList.toggle('active', x.dataset.method === method));
  $$('.panel-method').forEach(p => p.classList.add('hidden'));
  $(panels[method]).classList.remove('hidden');
  stopCamera(); stopBarcode();
  if (method === 'barcode') startBarcode();
  if (method === 'camera') startCamera();
  if (method === 'upload') setupUpload();
}

/* ---------- analyze ---------- */
async function analyze({ barcode, name }) {
  loading(true, barcode ? 'Looking up the product…' : 'Searching the catalog…');
  try {
    const r = await fetch('/api/scan', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ barcode, name }),
    });
    handleResult(await r.json());
  } catch (e) { errorResult(e.message); }
  finally { loading(false); }
}

async function analyzeText(text) {
  loading(true, 'Matching the label to a product…');
  try {
    const r = await fetch('/api/analyze-text', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    handleResult(await r.json());
  } catch (e) { errorResult(e.message); }
  finally { loading(false); }
}

function handleResult(data) {
  if (data.error) { errorResult(`${data.error}${data.query ? ` (searched “${esc(data.query)}”)` : ''}`); return; }
  LAST = data;
  renderResult(data);
  pushHistory(data);
  showView('result');
}

function errorResult(msg) {
  $('#resultEmpty').classList.add('hidden');
  $('#resultBody').innerHTML = `<div class="glass empty">😕 ${esc(msg)}<br><small>Try a different name or a barcode.</small></div>`;
  showView('result');
}

function loading(on, text) {
  $('#loader').classList.toggle('hidden', !on);
  if (text) $('#loaderText').textContent = text;
}

/* ---------- search / chips ---------- */
$('#goBtn').onclick = () => {
  const v = $('#queryInput').value.trim();
  if (!v) return;
  /^\d{6,}$/.test(v) ? analyze({ barcode: v }) : analyze({ name: v });
};
$('#queryInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('#goBtn').click(); });
$$('.chip').forEach(c => c.onclick = () => { $('#queryInput').value = c.dataset.bc; analyze({ barcode: c.dataset.bc }); });

/* ===================== RESULT RENDER ===================== */
function ring(score, grade) {
  const R = 56, C = 2 * Math.PI * R, off = C * (1 - score / 100);
  return `<div class="score-ring">
    <svg width="132" height="132" viewBox="0 0 132 132">
      <circle class="ring-bg" cx="66" cy="66" r="${R}" fill="none" stroke-width="12"/>
      <circle class="ring-fg" cx="66" cy="66" r="${R}" fill="none" stroke-width="12"
        stroke="${gradeColor(grade)}" stroke-dasharray="${C}" stroke-dashoffset="${C}" data-off="${off}"/>
    </svg>
    <div class="ring-center"><span class="num" style="color:${gradeColor(grade)}">${score}</span><span class="lbl">Eco ${grade}</span></div>
  </div>`;
}
function badge(on, label) { return `<span class="badge ${on ? 'on' : 'off'}">${on ? '✓' : '✕'} ${label}</span>`; }
const scoreGrade = (n) => n >= 85 ? 'A' : n >= 70 ? 'B' : n >= 50 ? 'C' : n >= 30 ? 'D' : 'E';

function renderResult(d) {
  $('#resultEmpty').classList.add('hidden');
  const s = d.sustainability, f = s.flags, h = d.health;
  const isFav = LS.get('favs', []).some(x => x.barcode === d.barcode);

  const badges = [
    badge(f.vegan, 'Vegan'), badge(f.cruelty_free, 'Cruelty-free'),
    badge(!f.palm_oil, 'Palm-oil free'), badge(f.organic, 'Organic'),
    badge(!f.microplastics, 'No microplastics'), badge(f.recyclable_packaging, 'Recyclable pkg'),
  ].join('');

  const factors = s.factors.map(ft => `
    <div class="factor"><div class="f-top"><b>${ft.factor}</b><span>${ft.score}/100</span></div>
      <div class="track"><span data-w="${ft.score}" style="background:${gradeColor(scoreGrade(ft.score))}"></span></div></div>`).join('');

  const metrics = `
    <div class="metrics">
      <div class="metric"><div class="v" style="color:${gradeColor(h.grade)}">${h.grade}</div><div class="k">Health · Nutri-${h.nutriscore}</div></div>
      <div class="metric"><div class="v">${s.carbon.kg_co2e_per_kg}</div><div class="k">kg CO₂e/kg · ${s.carbon.band}</div></div>
      <div class="metric"><div class="v">${h.nova_group}</div><div class="k">NOVA processing</div></div>
      <div class="metric"><div class="v">${(d.ingredients || []).length}</div><div class="k">ingredients</div></div>
    </div>`;

  const ings = (d.ingredients || []).map(i => `
    <div class="ing"><span class="dot ${i.level}"></span>
      <div><div class="nm">${esc(i.name)}${i.percent ? `<span class="pct">${i.percent}%</span>` : ''}</div>
        <div class="why"><b>${esc(i.purpose)}</b> · ${esc(i.health_impact)} · 🌍 ${esc(i.env_impact)}</div>
        <div class="tags"><span class="tag">${i.level}</span>
          ${i.vegan === 'yes' ? '<span class="tag">vegan</span>' : i.vegan === 'no' ? '<span class="tag">non-vegan</span>' : ''}
        </div></div></div>`).join('') || '<div class="why">No parsed ingredient list available for this product.</div>';

  const swaps = (d.swaps || []).map(sw => `
    <div class="swap">
      ${sw.image ? `<img src="${esc(sw.image)}" onerror="this.style.visibility='hidden'"/>` : '<div></div>'}
      <div>
        <div class="s-name">${esc(sw.product_name)}</div>
        <div class="s-brand">${esc(sw.brand || '')} · ${(sw.key_ingredients || []).map(esc).join(', ')}</div>
        <div class="s-why">${(sw.why_better || []).map(w => `<span class="tag win">${esc(w)}</span>`).join('')}</div>
        <div class="s-actions">
          <button class="mini-btn" onclick="addToCart('${esc(sw.product_name).replace(/'/g, '')}')">🛒 Add to cart</button>
          <a class="mini-btn" href="${esc(sw.amazon_url)}" target="_blank" rel="noopener">Amazon ↗</a>
          <button class="mini-btn" onclick="doCompare('${d.barcode}','${sw.barcode}')">⇄ Compare</button>
        </div>
      </div>
      <div class="s-right">
        <div class="s-score" style="color:${gradeColor(sw.eco_grade)}">${sw.eco_score}</div>
        <div class="s-price" data-price="${esc(sw.product_name).replace(/"/g, '')}">checking price…</div>
        <div class="co2">${sw.co2_reduction_pct ? `−${sw.co2_reduction_pct}% CO₂` : ''}</div>
      </div>
    </div>`).join('') || '<div class="why">No clearly better swap found — this product is already a strong pick. 🌿</div>';

  const tips = (d.tips || []).map(t => `<div class="tip"><span class="ic">🌱</span><span>${esc(t)}</span></div>`).join('');

  $('#resultBody').innerHTML = `
    <div class="glass result-head">
      ${d.image ? `<img class="thumb" src="${esc(d.image)}" onerror="this.style.visibility='hidden'"/>` : '<div></div>'}
      <div>
        <h2>${esc(d.product_name)}</h2>
        <div class="brand-row">${esc(d.brand || 'Unknown brand')}${d.barcode ? ' · ' + esc(d.barcode) : ''}</div>
        ${d.ocr_text ? `<div class="brand-row">📷 OCR matched “${esc(d.matched_query || '')}”</div>` : ''}
        <div class="head-actions">
          <button class="mini-btn" id="favBtn">${isFav ? '💚 Saved' : '🤍 Save to favorites'}</button>
          <button class="mini-btn" onclick="window.print()">⤓ Export</button>
        </div>
      </div>
      ${ring(d.overall.score, d.overall.grade)}
    </div>

    <div class="glass"><div class="badge-row" style="padding:20px 26px">${badges}</div></div>

    <div class="grid-2" style="margin-top:18px">
      <div class="glass subcard"><h3>📊 Score breakdown</h3>${factors}</div>
      <div class="glass subcard"><h3>🌍 Impact metrics</h3>${metrics}
        <h3 style="margin-top:20px">💡 Sustainability tips</h3>${tips}</div>
      <div class="glass subcard full"><h3>🧪 Ingredient analysis</h3>${ings}</div>
      <div class="glass subcard full"><h3>🌿 Sustainable alternatives</h3>${swaps}</div>
    </div>`;

  requestAnimationFrame(() => {
    $$('#resultBody .ring-fg').forEach(c => c.style.strokeDashoffset = c.dataset.off);
    $$('#resultBody .track > span').forEach(b => b.style.width = b.dataset.w + '%');
  });
  $('#favBtn').onclick = () => toggleFav(d);
  loadPrices();
}

/* live prices stream in per swap (Bright Data ~10s each, fetched in parallel) */
function loadPrices() {
  $$('#resultBody .s-price[data-price]').forEach(el => {
    const name = el.getAttribute('data-price');
    fetch('/api/price', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) })
      .then(r => r.json())
      .then(p => { el.innerHTML = `${esc(p.price)} ${p.source === 'brightdata' ? '<span style="color:var(--g-a)">· live</span>' : ''}`; })
      .catch(() => { el.textContent = ''; });
  });
}

/* ---------- dummy cart / compare ---------- */
window.addToCart = (name) => toast(`🛒 Added “${name}” to cart (demo)`);
window.doCompare = (origBc, altBc) => compare(origBc, altBc);

function toast(msg) {
  let t = $('#toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:var(--forest);color:#f4f7ee;padding:12px 22px;border-radius:30px;z-index:99;box-shadow:var(--shadow);font-size:14px;transition:opacity .3s';
    document.body.appendChild(t); }
  t.textContent = msg; t.style.opacity = '1';
  clearTimeout(t._t); t._t = setTimeout(() => t.style.opacity = '0', 2200);
}

async function compare(origBc, altBc) {
  showView('compare');
  const body = $('#compareBody');
  body.className = 'glass subcard';
  body.innerHTML = '<div class="loader"><div class="bloom"></div><p>Calculating the impact of switching…</p></div>';
  try {
    const r = await fetch('/api/compare', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ barcode: origBc, alt_barcode: altBc }) });
    const d = await r.json();
    if (d.error) { body.innerHTML = `<div class="empty">${esc(d.error)}</div>`; return; }
    renderCompare(d);
  } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

function renderCompare(d) {
  const im = d.impact;
  const bars = im.metrics.map(m => {
    const max = Math.max(m.orig, m.alt, 1);
    const ow = (m.orig / max) * 100, aw = (m.alt / max) * 100;
    const betterAlt = m.lower_better ? m.alt < m.orig : m.alt > m.orig;
    return `<div class="cmp-metric">
      <div class="cmp-top"><b>${m.label}</b><span style="color:var(--muted)">${m.unit}</span></div>
      <div class="cmp-pair"><span class="v">${esc(d.original.name).slice(0,14)}</span>
        <div class="col"><div class="barwrap"><span style="width:${ow}%;background:var(--g-d)"></span></div></div><span class="v">${m.orig}</span></div>
      <div class="cmp-pair"><span class="v">${esc(d.alternative.name).slice(0,14)}</span>
        <div class="col"><div class="barwrap"><span style="width:${aw}%;background:${betterAlt ? 'var(--g-a)' : 'var(--g-d)'}"></span></div></div><span class="v">${m.alt}</span></div>
    </div>`;
  }).join('');

  $('#compareBody').innerHTML = `
    <h3>⇄ <span class="gc" style="--gc:var(--g-d)">${esc(d.original.name)}</span> → <span class="gc" style="--gc:var(--g-a)">${esc(d.alternative.name)}</span></h3>
    <div class="cmp-bars">${bars}</div>
    <h3 style="margin-top:26px">🌍 Estimated yearly savings (1 unit/week)</h3>
    <div class="savings">
      <div class="saving"><div class="v">${im.carbon_saved_kg}</div><div class="k">kg CO₂e saved</div></div>
      <div class="saving"><div class="v">${im.plastic_saved_g}</div><div class="k">g plastic avoided</div></div>
      <div class="saving"><div class="v">${im.water_saved_l}</div><div class="k">L water saved</div></div>
      <div class="saving"><div class="v">${im.harmful_chemicals_cut}</div><div class="k">harmful additives cut</div></div>
      <div class="saving"><div class="v">+${im.eco_score_gain}</div><div class="k">eco-score gain</div></div>
    </div>`;
}

/* ===================== history & favorites ===================== */
function pushHistory(d) {
  const h = LS.get('history', []).filter(x => x.barcode !== d.barcode);
  h.unshift({ barcode: d.barcode, name: d.product_name, brand: d.brand, image: d.image, grade: d.overall.grade, score: d.overall.score });
  LS.set('history', h.slice(0, 24));
}
function miniCard(x) {
  return `<div class="glass mini-card" data-bc="${esc(x.barcode)}">
    <div class="mc-top">${x.image ? `<img src="${esc(x.image)}" onerror="this.style.visibility='hidden'"/>` : '<div></div>'}
      <div><div class="mc-name">${esc(x.name)}</div><div class="brand-row" style="font-size:12px;color:var(--muted)">${esc(x.brand || '')}</div></div>
      <div class="mc-grade" style="color:${gradeColor(x.grade)}">${x.grade}</div></div></div>`;
}
function bindMini(grid) { $$('.mini-card', grid).forEach(c => c.onclick = () => analyze({ barcode: c.dataset.bc })); }
function renderHistory() {
  const h = LS.get('history', []);
  $('#historyGrid').innerHTML = h.length ? h.map(miniCard).join('') : '<div class="empty glass">No scans yet. 🌱</div>';
  bindMini($('#historyGrid'));
}
function renderFavorites() {
  const f = LS.get('favs', []);
  $('#favGrid').innerHTML = f.length ? f.map(miniCard).join('') : '<div class="empty glass">No favorites yet — tap 💚 on a result. 🌿</div>';
  bindMini($('#favGrid'));
}
function toggleFav(d) {
  let f = LS.get('favs', []);
  const exists = f.some(x => x.barcode === d.barcode);
  f = exists ? f.filter(x => x.barcode !== d.barcode)
             : [{ barcode: d.barcode, name: d.product_name, brand: d.brand, image: d.image, grade: d.overall.grade, score: d.overall.score }, ...f];
  LS.set('favs', f);
  $('#favBtn').textContent = exists ? '🤍 Save to favorites' : '💚 Saved';
  toast(exists ? 'Removed from favorites' : '💚 Saved to favorites');
}

/* ===================== camera + OCR ===================== */
let camStream = null;
async function startCamera() {
  $('#dropzone').classList.add('hidden'); $('#preview').classList.add('hidden');
  const cam = $('#cam'), shutter = $('#shutterBtn'), stop = $('#stopCamBtn');
  try {
    camStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
    cam.srcObject = camStream; cam.classList.remove('hidden');
    shutter.classList.remove('hidden'); stop.classList.remove('hidden');
  } catch (e) {
    $('#ocrStatus').classList.remove('hidden');
    $('#ocrStatus').innerHTML = `Camera unavailable (${esc(e.name)}). Try “Upload image”.`;
  }
}
function stopCamera() {
  if (camStream) { camStream.getTracks().forEach(t => t.stop()); camStream = null; }
  $('#cam')?.classList.add('hidden'); $('#shutterBtn')?.classList.add('hidden'); $('#stopCamBtn')?.classList.add('hidden');
}
$('#stopCamBtn').onclick = stopCamera;
$('#shutterBtn').onclick = () => {
  const cam = $('#cam'), canvas = $('#canvas');
  canvas.width = cam.videoWidth; canvas.height = cam.videoHeight;
  canvas.getContext('2d').drawImage(cam, 0, 0);
  const url = canvas.toDataURL('image/png');
  $('#preview').src = url; $('#preview').classList.remove('hidden');
  stopCamera();
  runOCR(url);
};

/* upload */
function setupUpload() {
  $('#cam').classList.add('hidden'); $('#shutterBtn').classList.add('hidden'); $('#stopCamBtn').classList.add('hidden');
  $('#dropzone').classList.remove('hidden');
  const dz = $('#dropzone'), fi = $('#fileInput');
  dz.onclick = () => fi.click();
  fi.onchange = () => { if (fi.files[0]) loadImage(fi.files[0]); };
  dz.ondragover = e => { e.preventDefault(); dz.style.background = 'var(--beige)'; };
  dz.ondragleave = () => dz.style.background = '';
  dz.ondrop = e => { e.preventDefault(); dz.style.background = ''; if (e.dataTransfer.files[0]) loadImage(e.dataTransfer.files[0]); };
}
function loadImage(file) {
  const reader = new FileReader();
  reader.onload = () => { $('#preview').src = reader.result; $('#preview').classList.remove('hidden'); $('#dropzone').classList.add('hidden'); runOCR(reader.result); };
  reader.readAsDataURL(file);
}

async function runOCR(imageUrl) {
  const st = $('#ocrStatus'); st.classList.remove('hidden');
  st.innerHTML = 'Reading the label with the vision model…<div class="bar"><span id="ocrBar" style="width:35%"></span></div>';
  // 1) preferred: accurate server-side OCR (RapidOCR / GPU EasyOCR on Flash)
  try {
    const r = await fetch('/api/ocr', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: imageUrl }),
    });
    const data = await r.json();
    if (!data.error) {
      st.innerHTML = `📷 Read: “${esc((data.matched_query || '').slice(0, 70))}”`;
      handleResult(data);
      return;
    }
    st.innerHTML = `${esc(data.error)}${data.product_guess ? ` — read “${esc(data.product_guess)}”` : ''}. Trying browser OCR…`;
  } catch (_) {
    st.innerHTML = 'Server OCR unavailable — using browser OCR…';
  }
  // 2) fallback: in-browser Tesseract.js with preprocessing
  try {
    const prepped = await preprocess(imageUrl);
    const { data } = await Tesseract.recognize(prepped, 'eng', {
      logger: m => { if (m.status === 'recognizing text' && $('#ocrBar')) $('#ocrBar').style.width = Math.round(m.progress * 100) + '%'; }
    });
    const text = (data.text || '').trim();
    if (text) analyzeText(text);
    else st.innerHTML = 'No readable text found — try a clearer, closer photo.';
  } catch (e) { st.innerHTML = `OCR failed: ${esc(e.message)}`; }
}

/* upscale + grayscale + contrast to help browser OCR fallback */
function preprocess(imageUrl) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(2, 1600 / Math.max(img.width, img.height)) || 1;
      const c = document.createElement('canvas');
      c.width = img.width * scale; c.height = img.height * scale;
      const x = c.getContext('2d');
      x.drawImage(img, 0, 0, c.width, c.height);
      const d = x.getImageData(0, 0, c.width, c.height), p = d.data;
      for (let i = 0; i < p.length; i += 4) {
        let g = 0.3 * p[i] + 0.59 * p[i + 1] + 0.11 * p[i + 2];
        g = (g - 128) * 1.5 + 128;            // contrast
        g = Math.max(0, Math.min(255, g));
        p[i] = p[i + 1] = p[i + 2] = g;
      }
      x.putImageData(d, 0, 0);
      resolve(c.toDataURL('image/png'));
    };
    img.onerror = () => resolve(imageUrl);
    img.src = imageUrl;
  });
}

/* ===================== barcode scanner ===================== */
let qr = null;
function startBarcode() {
  qr = new Html5Qrcode('reader');
  qr.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 260, height: 160 } },
    (text) => { stopBarcode(); $('#queryInput') && ($('#queryInput').value = text); analyze({ barcode: text }); },
    () => {}
  ).catch(e => { $('#reader').innerHTML = `<div class="empty">Camera unavailable: ${esc(e)}</div>`; });
}
function stopBarcode() { if (qr) { qr.stop().then(() => { qr.clear(); qr = null; }).catch(() => qr = null); } }

selectMethod('search');
