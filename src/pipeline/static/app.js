// Trang nạp dữ liệu: chọn file + cấu hình → POST /api/runs → hỏi lại GET /api/runs/{id} mỗi giây.
'use strict';

const STEPS = [
  ['clean', 'Làm sạch'], ['upsert', 'Nạp listings'], ['link', 'Gắn địa chỉ (FK)'],
  ['spatial', 'Tiện ích quanh nhà (POI)'], ['embed', 'Embedding (Kaggle)'], ['retrain', 'Retrain mô hình giá'],
];
const STEP_TEXT = { pending: 'Chờ', running: 'Đang chạy', done: 'Xong', error: 'Lỗi', skipped: 'Bỏ qua' };
const RUN_TEXT = { running: 'Đang chạy', done: 'Xong', error: 'Có bước lỗi', interrupted: 'Bị ngắt' };
const FLAG_NAMES = ['dry_run', 'upsert', 'link', 'spatial', 'embed', 'retrain'];
const POLL_MS = 1000;

const $ = (selector) => document.querySelector(selector);
const state = { settings: null, files: [], run: null, runs: [], timer: null };

// Tạo phần tử DOM; chữ luôn qua textContent (tên file do người dùng đặt, không chèn HTML).
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'text') node.textContent = value;
    else if (value !== undefined && value !== null && value !== false) node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`);
  return body;
}

function gearPath(teeth = 9, outer = 23, root = 17.5, hole = 7) {
  const step = (Math.PI * 2) / teeth;
  const points = [];
  for (let i = 0; i < teeth; i += 1) {
    const a = i * step;
    points.push([root, a], [outer, a + step * 0.14], [outer, a + step * 0.4], [root, a + step * 0.54]);
  }
  const xy = ([r, a]) => `${(24 + r * Math.cos(a)).toFixed(2)} ${(24 + r * Math.sin(a)).toFixed(2)}`;
  return `M${points.map(xy).join('L')}Z M${24 + hole} 24A${hole} ${hole} 0 1 0 ${24 - hole} 24`
    + `A${hole} ${hole} 0 1 0 ${24 + hole} 24Z`;
}

const megabytes = (bytes) => `${(bytes / 1024 / 1024).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} MB`;
const seconds = (value) => (value === null || value === undefined ? '' : `${value.toLocaleString('vi-VN')} s`);
const when = (iso) => new Date(iso).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'medium' });

function showMessage(text, isError = false) {
  const box = $('#message');
  box.textContent = text;
  box.className = isError ? 'message error' : 'message';
  box.setAttribute('role', isError ? 'alert' : 'status');
}

// ---- File ----------------------------------------------------------------------------------

function addFiles(list) {
  const skipped = [];
  for (const file of list) {
    if (!/\.jsonl?$/i.test(file.name)) skipped.push(file.name);
    else if (!state.files.some((f) => f.name === file.name && f.size === file.size)) state.files.push(file);
  }
  renderFiles();
  if (skipped.length) showMessage(`Bỏ qua (chỉ nhận .json/.jsonl): ${skipped.join(', ')}`, true);
}

function renderFiles() {
  const list = $('#file-list');
  list.replaceChildren(...state.files.map((file, index) => el('li', {},
    el('span', { class: 'name', text: file.name }),
    el('span', { class: 'size', text: megabytes(file.size) }),
    removeButton(index, file.name))));
  if (state.files.length) {
    const total = state.files.reduce((sum, file) => sum + file.size, 0);
    const max = state.settings ? state.settings.max_upload_mb : 100;
    list.append(el('li', { class: 'total', text: `${state.files.length} file · ${megabytes(total)} / tối đa ${max} MB` }));
  }
  $('#run-button').disabled = state.files.length === 0;
}

function removeButton(index, name) {
  const button = el('button', { type: 'button', class: 'link-button', 'aria-label': `Bỏ ${name}`, text: 'Bỏ' });
  button.addEventListener('click', () => { state.files.splice(index, 1); renderFiles(); });
  return button;
}

// ---- Cấu hình ------------------------------------------------------------------------------

function flag(name) { return $(`#config [name="${name}"]`); }

// Chạy thử khóa mọi bước ghi DB; tắt "Nạp listings" khóa 3–6 (không có gì mới để xử lý).
function syncLocks() {
  const dry = flag('dry_run').checked;
  $('#database').disabled = dry;
  flag('upsert').disabled = dry;
  for (const name of ['link', 'spatial', 'embed', 'retrain']) flag(name).disabled = dry || !flag('upsert').checked;
  if (!state.run) renderFlow(previewSteps());
}

function previewSteps() {
  const config = Object.fromEntries(FLAG_NAMES.map((name) => [name, flag(name).checked]));
  return STEPS.map(([key, name]) => {
    let error = null;
    if (key === 'clean') error = null;
    else if (config.dry_run) error = 'Chạy thử: không ghi DB';
    else if (key !== 'upsert' && !config.upsert) error = 'Bước nạp listings đang tắt';
    else if (!config[key]) error = 'Đã tắt';
    return { key, name, status: error ? 'skipped' : 'pending', error, numbers: null, seconds: null };
  });
}

async function loadSettings() {
  try {
    const settings = await api('/api/settings');
    state.settings = settings;
    const select = $('#database');
    select.replaceChildren(...settings.databases.map((name) => el('option', { value: name, text: name })));
    if (settings.default_database) select.value = settings.default_database;
    $('#max-mb').textContent = settings.max_upload_mb;
    $('#embed-note').textContent = settings.embedding_configured
      ? 'cần notebook Kaggle đang bật' : 'chưa có EMBEDDING_API_URL/KEY trong .env';
    $('#retrain-note').textContent = settings.retrain_configured
      ? 'gửi yêu cầu tới Prediction Server' : 'chưa có PREDICTION_SERVER_URL/KEY trong .env';
    return settings;
  } catch (error) {
    $('#database').replaceChildren(el('option', { text: 'không đọc được' }));
    showMessage(error.message, true);
    return null;
  }
}

async function startRun() {
  const form = new FormData();
  for (const file of state.files) form.append('files', file, file.name);
  for (const name of FLAG_NAMES) form.append(name, String(flag(name).checked));
  form.append('database', $('#database').value);
  $('#run-button').disabled = true;
  showMessage('Đang tải file lên…');
  try {
    const run = await api('/api/runs', { method: 'POST', body: form });
    state.files = [];
    renderFiles();
    showMessage(`Đã nhận, lần chạy ${run.id} đang chạy.`);
    selectRun(run);
    loadHistory();
  } catch (error) {
    showMessage(error.message, true);
    $('#run-button').disabled = state.files.length === 0;
  }
}

// ---- Tiến độ -------------------------------------------------------------------------------

function selectRun(run) {
  state.run = run;
  renderRun();
  clearTimeout(state.timer);
  if (run.status === 'running') state.timer = setTimeout(poll, POLL_MS);
}

async function poll() {
  try {
    const run = await api(`/api/runs/${encodeURIComponent(state.run.id)}`);
    if (run.id !== state.run.id) return;
    state.run = run;
    renderRun();
    if (run.status === 'running') state.timer = setTimeout(poll, POLL_MS);
    else loadHistory();
  } catch (error) {
    showMessage(`Mất kết nối server: ${error.message}`, true);
    state.timer = setTimeout(poll, POLL_MS * 3);
  }
}

function renderRun() {
  const run = state.run;
  const meta = $('#run-meta');
  const db = run.database ? `DB ${run.database}` : 'chạy thử';
  meta.replaceChildren(
    el('strong', { text: RUN_TEXT[run.status] || run.status }),
    ` · ${run.id} · ${db} · ${run.files.map((f) => f.name).join(', ')}`,
    run.seconds !== null ? ` · ${seconds(run.seconds)}` : '');
  renderFlow(run.steps);
  $('#downloads').replaceChildren(...run.downloads.map((name) => el('a', {
    class: 'button', href: `/api/runs/${encodeURIComponent(run.id)}/files/${name}`, download: '', text: `Tải ${name}`,
  })));
  if (run.error) $('#downloads').append(el('p', { class: 'step-error', text: run.error }));
  for (const row of document.querySelectorAll('#history tr')) row.classList.toggle('selected', row.dataset.id === run.id);
}

function renderFlow(steps) {
  if (!state.run) $('#run-meta').textContent = 'Chưa chạy — xem trước theo cấu hình';
  $('#flow').replaceChildren(...steps.map((step, index) => el('li', { class: 'step', 'data-status': step.status },
    el('div', { class: 'gear-col' }, gearIcon()),
    el('div', { class: 'step-body' },
      el('div', { class: 'step-head' },
        el('span', { class: 'step-no', text: `${index + 1}` }),
        el('strong', { text: step.name }),
        el('span', { class: 'badge', text: [STEP_TEXT[step.status], seconds(step.seconds)].filter(Boolean).join(' · ') })),
      numbersList(step.numbers),
      step.error ? el('p', { class: step.status === 'error' ? 'step-error' : 'step-note', text: step.error }) : null))));
}

function gearIcon() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'gear');
  svg.setAttribute('viewBox', '0 0 48 48');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#gear');
  svg.append(use);
  return svg;
}

// Số liệu giống dòng CLI: key=value; lý do loại (dict) gộp một ô; status_url thành link.
function numbersList(numbers) {
  if (!numbers) return null;
  return el('ul', { class: 'numbers' }, ...Object.entries(numbers).map(([key, value]) => {
    if (key === 'status_url') return el('li', {}, 'xem: ', el('a', { href: value, text: value }));
    if (value && typeof value === 'object') {
      const parts = Object.entries(value).map(([k, v]) => `${k}=${v}`).join(', ');
      return el('li', { text: `${key}: ${parts || '—'}` });
    }
    return el('li', { text: `${key}=${value}` });
  }));
}

// ---- Lịch sử -------------------------------------------------------------------------------

function configText(run) {
  if (run.config.dry_run) return 'chạy thử';
  const names = { upsert: 'nạp', link: 'FK', spatial: 'POI', embed: 'embed', retrain: 'retrain' };
  return Object.entries(names).filter(([key]) => run.config[key]).map(([, name]) => name).join(' · ') || '—';
}

async function loadHistory() {
  try {
    state.runs = await api('/api/runs');
  } catch (error) {
    showMessage(error.message, true);
    return;
  }
  const body = $('#history');
  if (!state.runs.length) {
    body.replaceChildren(el('tr', {}, el('td', { colspan: 8, class: 'empty', text: 'Chưa có lần chạy nào.' })));
    return;
  }
  body.replaceChildren(...state.runs.map((run) => {
    const view = el('button', { type: 'button', class: 'link-button', text: 'Xem', 'aria-label': `Xem lần chạy ${run.id}` });
    view.addEventListener('click', () => { selectRun(run); $('#flow-title').scrollIntoView({ block: 'nearest' }); });
    const summary = run.steps.map((s, i) => `${i + 1} ${STEP_TEXT[s.status]}`).join(', ');
    const cell = (label, attrs, ...children) => el('td', { 'data-label': label, ...attrs }, ...children);
    return el('tr', { 'data-id': run.id, class: state.run && state.run.id === run.id ? 'selected' : null },
      cell('Thời điểm', { class: 'mono', text: when(run.created_at) }),
      cell('File', { class: 'files-cell', text: run.files.map((f) => f.name).join(', ') }),
      cell('DB đích', { text: run.database || '—' }),
      cell('Cấu hình', { text: configText(run) }),
      cell('Bước', {}, el('div', {},
        el('div', { class: 'dots', role: 'img', 'aria-label': summary, title: summary },
          ...run.steps.map((s) => el('span', { class: `dot ${s.status}` }))),
        el('span', { class: `run-status ${run.status}`, text: RUN_TEXT[run.status] || run.status }))),
      cell('Thời lượng', { class: 'mono', text: run.status === 'running' ? '…' : seconds(run.seconds) }),
      cell('Báo cáo', {}, el('div', { class: 'cell-links' }, ...run.downloads.map((name) => el('a', {
        href: `/api/runs/${encodeURIComponent(run.id)}/files/${name}`, download: '', text: name,
      })))),
      cell('', {}, view));
  }));
}

// ---- Khởi động -----------------------------------------------------------------------------

function bindEvents() {
  const drop = $('#drop');
  $('#file-input').addEventListener('change', (event) => { addFiles(event.target.files); event.target.value = ''; });
  for (const type of ['dragenter', 'dragover']) {
    drop.addEventListener(type, (event) => { event.preventDefault(); drop.classList.add('over'); });
  }
  for (const type of ['dragleave', 'drop']) drop.addEventListener(type, () => drop.classList.remove('over'));
  drop.addEventListener('drop', (event) => { event.preventDefault(); addFiles(event.dataTransfer.files); });
  $('#config').addEventListener('change', syncLocks);
  $('#run-button').addEventListener('click', startRun);
}

async function init() {
  $('#gear-path').setAttribute('d', gearPath());
  bindEvents();
  renderFiles();
  syncLocks();
  const [settings] = await Promise.all([loadSettings(), loadHistory()]);
  // Reload trang khi đang chạy: mở lại đúng lần chạy đó; không thì hiện lần gần nhất.
  const active = settings && settings.active_run_id && state.runs.find((run) => run.id === settings.active_run_id);
  if (active || state.runs.length) selectRun(active || state.runs[0]);
}

init();
