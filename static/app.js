const $ = (id) => document.getElementById(id);
let pollTimer = null;
let savedInstruction = '';

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
  return data;
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
  try {
    const data = await api('/api/settings');
    applySettings(data, false);
  } catch (error) {
    setText('settings-status', error.message);
  }
}

function applySettings(data, keepApiKey) {
  setValue('base-url', data.base_url || 'https://generativelanguage.googleapis.com/v1beta/openai');
  if (!keepApiKey) setValue('api-key', '');
  const keyInput = $('api-key');
  if (keyInput) keyInput.placeholder = data.api_key_saved ? 'API key tersimpan' : 'Gemini API key';
  setValue('model', data.model || 'gemini-2.5-flash');
  setValue('subtitle-language', data.subtitle_language || 'id');
  setValue('output-dir', data.output_dir || '');
  const captions = $('captions');
  if (captions && !data.caption_key_saved) captions.checked = false;
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
  const apiKey = getValue('api-key');
  try {
    const result = await api('/api/settings', {
      method: 'POST',
      body: JSON.stringify({
        base_url: getValue('base-url'),
        api_key: apiKey,
        model: getValue('model'),
        subtitle_language: getValue('subtitle-language', 'id'),
        output_dir: getValue('output-dir'),
      }),
    });
    if (result.status !== 'saved') throw new Error(result.message || 'Gagal simpan');
    if (result.settings) applySettings(result.settings, false);
    setText('settings-status', apiKey ? 'Konfigurasi tersimpan. API key tersimpan.' : 'Konfigurasi tersimpan');
  } catch (error) {
    setText('settings-status', error.message);
  }
}

async function clearApiKey() {
  try {
    const result = await api('/api/settings', {
      method: 'POST',
      body: JSON.stringify({
        base_url: getValue('base-url'),
        model: getValue('model'),
        subtitle_language: getValue('subtitle-language', 'id'),
        output_dir: getValue('output-dir'),
        clear_api_key: true,
      }),
    });
    if (result.status !== 'saved') throw new Error(result.message || 'Gagal hapus API key');
    if (result.settings) applySettings(result.settings, false);
    setText('settings-status', 'API key dihapus');
  } catch (error) {
    setText('settings-status', error.message);
  }
}

function getScreenSize() {
  const selected = document.querySelector('input[name="screen_size"]:checked');
  return selected ? selected.value : '9:16';
}

function setScreenSize(value) {
  document.querySelectorAll('[data-screen-card]').forEach((card) => {
    const selected = card.dataset.screenCard === value;
    const title = card.querySelector('span:first-of-type');
    const subtitle = card.querySelector('span:last-of-type');
    card.className = selected
      ? 'border border-indigo-600 bg-indigo-50/30 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer text-center transition'
      : 'border border-gray-200 hover:border-gray-300 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer text-center transition';
    if (title) title.className = selected ? 'text-[14px] font-bold text-indigo-600 block' : 'text-[14px] font-bold text-gray-700 block';
    if (subtitle) subtitle.className = selected ? 'text-[11px] text-indigo-500' : 'text-[11px] text-gray-400';
    const input = card.querySelector('input');
    if (input) input.checked = selected;
  });
}

function updateInstructionCount() {
  const value = getValue('instruction');
  setText('instruction-count', `${value.length}/1000`);
}

function saveInstruction() {
  savedInstruction = getValue('instruction').slice(0, 1000);
  setValue('instruction', savedInstruction);
  updateInstructionCount();
  $('instruction-modal').classList.add('hidden');
}

function cancelInstruction() {
  setValue('instruction', savedInstruction);
  updateInstructionCount();
  $('instruction-modal').classList.add('hidden');
}

function toggleProfileMenu() {
  const menu = $('profile-menu');
  if (menu) menu.classList.toggle('hidden');
}

async function startProcessing() {
  const button = $('process-button');
  if (button) button.disabled = true;
  clearInterval(pollTimer);
  try {
    const result = await api('/api/start', {
      method: 'POST',
      body: JSON.stringify({
        url: getValue('youtube-url'),
        num_clips: Number(getValue('num-clips', '3') || 3),
        add_captions: getChecked('captions', true),
        add_hook: false,
        screen_size: getScreenSize(),
        subtitle_language: getValue('subtitle-language', 'id'),
        instruction: savedInstruction,
      }),
    });
    if (result.status !== 'started') throw new Error(result.message || 'Gagal mulai');
    pollTimer = setInterval(pollStatus, 800);
    pollStatus();
  } catch (error) {
    if (button) button.disabled = false;
    setText('status-text', error.message);
  }
}

async function pollStatus() {
  try {
    const data = await api('/api/status');
    setText('status-text', data.error || data.message || data.status);
    const bar = $('progress-bar');
    if (bar) bar.style.width = `${Math.round((data.progress || 0) * 100)}%`;
    if (data.status === 'complete' || data.status === 'error') {
      clearInterval(pollTimer);
      $('process-button').disabled = false;
      await renderOutputs();
    }
  } catch (error) {
    clearInterval(pollTimer);
    $('process-button').disabled = false;
    setText('status-text', error.message);
  }
}

async function renderOutputs() {
  const historyPanel = $('history-panel');
  const homePanel = $('home-results-panel');
  let files = [];
  let groups = [];
  try {
    const data = await api('/api/outputs');
    files = data.files || [];
    groups = data.groups || [];
  } catch (error) {
    if (historyPanel) historyPanel.innerHTML = `<p class="text-[13px] text-red-500">${escapeHtml(error.message)}</p>`;
    return;
  }
  if (!files.length && !groups.length) {
    if (historyPanel) historyPanel.innerHTML = '<p class="text-[13px] text-gray-500">Belum ada riwayat klip.</p>';
    if (homePanel) homePanel.innerHTML = '<p class="text-[13px] text-gray-500">Belum ada hasil export.</p>';
    return;
  }
  const savedGroups = groups.filter((group) => group.saved);
  if (historyPanel) historyPanel.innerHTML = savedGroups.length ? savedGroups.map(renderSessionRow).join('') : '<p class="text-[13px] text-gray-500">Belum ada riwayat tersimpan.</p>';
  if (homePanel) {
    homePanel.className = 'space-y-5 py-10 w-full';
    homePanel.innerHTML = groups.length ? groups.map(renderExportSession).join('') : '<p class="text-[13px] text-gray-500">Belum ada hasil export.</p>';
  }
}

function renderSessionRow(group) {
  const saved = new Set(group.saved_clips || []);
  const allClips = group.clips && group.clips.length ? group.clips : group.files || [];
  const clips = saved.size ? allClips.filter((clip) => saved.has(clip.path)) : allClips;
  return `
    <article class="group border border-gray-200 rounded-2xl p-4 hover:bg-gray-50 transition-colors mb-3">
      <div class="flex items-start gap-4">
        <div class="w-14 h-14 rounded-xl bg-gray-950 text-white flex items-center justify-center font-bold shrink-0">9:16</div>
        <button class="text-left flex-1 min-w-0" type="button" data-session-toggle="${escapeAttr(group.path)}">
          <h3 class="font-bold text-[16px] text-black truncate">${escapeHtml(group.title)}</h3>
          <p class="text-[13px] text-gray-500 truncate">${escapeHtml(group.caption)}</p>
          <p class="text-[12px] text-gray-400">${formatTime(group.timestamp)} · ${clips.length} klip</p>
        </button>
        <button class="rounded-xl border border-red-100 px-3 py-2 text-[12px] font-bold text-red-600 hover:bg-red-50" type="button" data-delete-output="${escapeAttr(group.path)}">Hapus</button>
      </div>
      <div class="hidden mt-4 pl-[72px] space-y-2" data-session-files="${escapeAttr(group.path)}">
        ${clips.map(renderFileLink).join('')}
      </div>
    </article>
  `;
}

function renderFileLink(file) {
  return `
    <a class="w-full flex items-center justify-between border border-gray-100 rounded-xl px-4 py-3 text-left hover:bg-white" href="/api/download?path=${encodeURIComponent(file.path)}">
      <span class="font-bold text-[14px] text-black truncate pr-3">${escapeHtml(file.title || file.name)}</span>
      <span class="text-[12px] text-gray-400">Download</span>
    </a>
  `;
}

function renderExportSession(group) {
  const clips = group.clips || [];
  return `
    <section class="border border-gray-200 rounded-2xl p-5 bg-white">
      <div class="flex items-start justify-between gap-4 mb-4">
        <div class="min-w-0">
          <p class="text-[12px] font-semibold text-gray-500 mb-1">${formatTime(group.timestamp)}</p>
          <h3 class="font-bold text-[20px] leading-tight text-gray-950 truncate">${escapeHtml(group.title)}</h3>
          <p class="text-[13px] text-gray-500 line-clamp-2">${escapeHtml(group.caption)}</p>
        </div>
        <button class="rounded-xl bg-gray-950 text-white px-4 py-3 text-[13px] font-bold shrink-0" type="button" data-save-output="${escapeAttr(group.path)}" data-save-all="1">Simpan semua</button>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
        ${clips.map((clip, index) => renderExportCard(group, clip, index)).join('')}
      </div>
    </section>
  `;
}

function renderExportCard(group, clip, index = 0) {
  if (!clip || !clip.path) return '';
  const href = `/api/download?path=${encodeURIComponent(clip.path)}`;
  return `
    <article class="bg-white border border-gray-200 rounded-2xl p-4">
      <label class="flex items-center gap-2 text-[12px] font-bold text-gray-600 mb-3">
        <input type="checkbox" class="clip-select" data-clip-path="${escapeAttr(clip.path)}" data-session-path="${escapeAttr(group.path)}" checked>
        Pilih klip ${index + 1}
      </label>
      <div class="relative bg-gray-100 rounded-xl aspect-[9/12] overflow-hidden mb-4">
        <video class="w-full h-full object-cover" src="/api/download?path=${encodeURIComponent(clip.path)}" muted preload="metadata"></video>
        <span class="absolute left-3 top-3 bg-gray-950 text-white rounded-md px-2 py-1 text-[12px] font-bold">9:16</span>
      </div>
      <h3 class="font-bold text-[16px] leading-tight text-gray-950 mb-1 line-clamp-2">${escapeHtml(clip.title || `Klip ${index + 1}`)}</h3>
      <p class="text-[13px] text-gray-500 mb-4 line-clamp-2">${escapeHtml(clip.description || group.caption)}</p>
      <div class="grid grid-cols-[1fr_auto] gap-2">
        <a class="flex items-center justify-center rounded-xl bg-gray-950 text-white px-4 py-3 text-[13px] font-bold" href="${href}">Download</a>
        <button class="rounded-xl border border-gray-200 px-4 py-3 text-[13px] font-bold text-gray-700 hover:bg-gray-50" type="button" data-save-output="${escapeAttr(group.path)}" data-save-one="${escapeAttr(clip.path)}">Simpan</button>
      </div>
    </article>
  `;
}

async function deleteOutput(path) {
  if (!path) return;
  try {
    await api('/api/delete', { method: 'POST', body: JSON.stringify({ path }) });
    await renderOutputs();
  } catch (error) {
    setText('status-text', error.message);
  }
}

async function saveOutput(path, oneClip, all) {
  if (!path) return;
  const inputs = [...document.querySelectorAll(`.clip-select[data-session-path="${cssEscape(path)}"]`)];
  const selected = oneClip ? [oneClip] : inputs.filter((input) => all || input.checked).map((input) => input.dataset.clipPath);
  try {
    await api('/api/save', { method: 'POST', body: JSON.stringify({ path, clips: selected }) });
    await renderOutputs();
  } catch (error) {
    setText('status-text', error.message);
  }
}

function toggleSession(path) {
  document.querySelectorAll('[data-session-files]').forEach((el) => {
    el.classList.toggle('hidden', el.dataset.sessionFiles !== path || !el.classList.contains('hidden'));
  });
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || '';
  return date.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' });
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

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#96;');
}

function cssEscape(value) {
  return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/"/g, '\\"');
}

document.addEventListener('DOMContentLoaded', () => {
  const save = $('save-settings');
  const clearKey = $('clear-api-key');
  const start = $('process-button');
  const navHome = $('nav-home');
  const navHistory = $('nav-history');
  const profile = $('profile-button');
  const instruction = $('instruction');
  const instructionSave = $('instruction-save');
  const instructionCancel = $('instruction-cancel');
  if (save) save.addEventListener('click', saveSettings);
  if (clearKey) clearKey.addEventListener('click', clearApiKey);
  if (start) start.addEventListener('click', startProcessing);
  if (profile) profile.addEventListener('click', toggleProfileMenu);
  if (instruction) instruction.addEventListener('input', updateInstructionCount);
  if (instructionSave) instructionSave.addEventListener('click', saveInstruction);
  if (instructionCancel) instructionCancel.addEventListener('click', cancelInstruction);
  document.querySelectorAll('[data-screen-card]').forEach((card) => card.addEventListener('click', () => setScreenSize(card.dataset.screenCard)));
  document.addEventListener('click', (event) => {
    const deleteButton = event.target.closest('[data-delete-output]');
    const saveButton = event.target.closest('[data-save-output]');
    const sessionButton = event.target.closest('[data-session-toggle]');
    if (deleteButton) deleteOutput(deleteButton.dataset.deleteOutput);
    if (saveButton) saveOutput(saveButton.dataset.saveOutput, saveButton.dataset.saveOne, saveButton.dataset.saveAll === '1');
    if (sessionButton) toggleSession(sessionButton.dataset.sessionToggle);
  });
  if (navHome) navHome.addEventListener('click', (event) => { event.preventDefault(); showPage('home'); });
  if (navHistory) navHistory.addEventListener('click', (event) => { event.preventDefault(); showPage('history'); });
  setScreenSize(getScreenSize());
  updateInstructionCount();
  loadSettings();
  renderOutputs();
});
