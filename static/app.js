const $ = (id) => document.getElementById(id);
let pollTimer = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return res.json();
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function setValue(id, value) {
  const el = $(id);
  if (el) el.value = value;
}

function getValue(id, fallback = '') {
  const el = $(id);
  return el ? el.value : fallback;
}

function getChecked(id, fallback = false) {
  const el = $(id);
  return el ? el.checked : fallback;
}

async function loadSettings() {
  const data = await api('/api/settings');
  setValue('base-url', data.base_url || 'https://generativelanguage.googleapis.com/v1beta/openai');
  setValue('api-key', '');
  setValue('model', data.model || 'gemini-2.0-flash');
  setValue('subtitle-language', data.subtitle_language || 'id');
  setValue('output-dir', data.output_dir || '');
  setCookieStatus(data.cookies);
}

function setCookieStatus(cookies) {
  const el = $('cookie-status');
  if (!el) return;
  const exists = cookies && cookies.exists;
  el.textContent = exists ? `cookies.txt aktif: ${cookies.path}` : `cookies.txt belum ada: ${cookies ? cookies.path : ''}`;
  el.className = exists ? 'text-[12px] text-green-600' : 'text-[12px] text-amber-600';
}

async function saveSettings() {
  const result = await api('/api/settings', {
    method: 'POST',
    body: JSON.stringify({
      base_url: getValue('base-url'),
      api_key: getValue('api-key'),
      model: getValue('model'),
      subtitle_language: getValue('subtitle-language', 'id'),
      output_dir: getValue('output-dir'),
    }),
  });
  setText('settings-status', result.status === 'saved' ? 'Tersimpan' : 'Gagal simpan');
  if (result.status === 'saved') await loadSettings();
}

async function saveCookies() {
  const text = getValue('cookies-text');
  if (!text) return;
  const result = await api('/api/cookies', {
    method: 'POST',
    body: JSON.stringify({ content: text }),
  });
  setText('settings-status', result.status === 'saved' ? 'Cookies tersimpan' : result.message || 'Gagal simpan cookies');
  if (result.cookies) setCookieStatus(result.cookies);
  if (result.status === 'saved') setValue('cookies-text', '');
}

async function startProcessing() {
  const result = await api('/api/start', {
    method: 'POST',
    body: JSON.stringify({
      url: getValue('youtube-url'),
      num_clips: Number(getValue('num-clips', '3') || 3),
      add_captions: getChecked('captions', true),
      add_hook: getChecked('hook', false),
      subtitle_language: getValue('subtitle-language', 'id'),
      instruction: getValue('instruction'),
    }),
  });
  if (result.status !== 'started') {
    setText('status-text', result.message || 'Gagal mulai');
    return;
  }
  $('process-button').disabled = true;
  pollTimer = setInterval(pollStatus, 800);
  pollStatus();
}

async function pollStatus() {
  const data = await api('/api/status');
  setText('status-text', data.error || data.message || data.status);
  const bar = $('progress-bar');
  if (bar) bar.style.width = `${Math.round((data.progress || 0) * 100)}%`;
  if (data.status === 'complete' || data.status === 'error') {
    clearInterval(pollTimer);
    $('process-button').disabled = false;
    renderOutputs();
  }
}

async function renderOutputs() {
  const panel = $('history-panel');
  if (!panel) return;
  const data = await api('/api/outputs');
  const files = data.files || [];
  if (!files.length) {
    panel.innerHTML = '<p class="text-[13px] text-gray-500">Belum ada riwayat klip.</p>';
    return;
  }
  panel.innerHTML = files.map((file) => `
    <a class="w-full flex items-center justify-between border border-gray-100 rounded-xl px-4 py-3 text-left hover:bg-gray-50" href="/api/download?path=${encodeURIComponent(file.path)}">
      <span class="font-bold text-[14px] text-black">${escapeHtml(file.name)}</span>
      <span class="text-[12px] text-gray-400">Download</span>
    </a>
  `).join('');
}

function showPage(name) {
  const home = $('page-home');
  const history = $('page-history');
  const navHome = $('nav-home');
  const navHistory = $('nav-history');
  if (!home || !history) return;
  home.classList.toggle('hidden', name !== 'home');
  history.classList.toggle('hidden', name !== 'history');
  navHome.className = name === 'home'
    ? 'flex items-center space-x-3.5 px-4 py-3 rounded-xl bg-[#eaeaea] text-black font-bold text-[15px]'
    : 'flex items-center space-x-3.5 px-4 py-3 rounded-xl text-gray-600 hover:bg-gray-100 hover:text-black font-semibold text-[15px] transition-colors';
  navHistory.className = name === 'history'
    ? 'flex items-center space-x-3.5 px-4 py-3 rounded-xl bg-[#eaeaea] text-black font-bold text-[15px]'
    : 'flex items-center space-x-3.5 px-4 py-3 rounded-xl text-gray-600 hover:bg-gray-100 hover:text-black font-semibold text-[15px] transition-colors';
  if (name === 'history') renderOutputs();
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

document.addEventListener('DOMContentLoaded', () => {
  const save = $('save-settings');
  const cookies = $('save-cookies');
  const start = $('process-button');
  const navHome = $('nav-home');
  const navHistory = $('nav-history');
  if (save) save.addEventListener('click', saveSettings);
  if (cookies) cookies.addEventListener('click', saveCookies);
  if (start) start.addEventListener('click', startProcessing);
  if (navHome) navHome.addEventListener('click', (event) => { event.preventDefault(); showPage('home'); });
  if (navHistory) navHistory.addEventListener('click', (event) => { event.preventDefault(); showPage('history'); });
  loadSettings();
  renderOutputs();
});
