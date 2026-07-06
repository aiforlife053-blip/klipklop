const $ = (id) => document.getElementById(id);
let pollTimer = null;
let savedInstruction = '';
let pendingConfirm = null;

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
  return data;
}

function setText(id, value) { const el = $(id); if (el) el.textContent = value; }
function setValue(id, value) { const el = $(id); if (el) el.value = value; }
function getValue(id, fallback = '') { const el = $(id); return el ? el.value : fallback; }
function getChecked(id, fallback = false) { const el = $(id); return el ? el.checked : fallback; }
function setChecked(id, value) { const el = $(id); if (el) el.checked = value; }

async function loadSettings() {
  try { applySettings(await api('/api/settings'), false); } catch (error) { setText('settings-status', error.message); }
}

function applySettings(data, keepApiKey) {
  setValue('base-url', data.base_url || 'https://generativelanguage.googleapis.com/v1beta/openai');
  if (!keepApiKey) setValue('api-key', '');
  const keyInput = $('api-key');
  if (keyInput) keyInput.placeholder = data.api_key_saved ? 'API key tersimpan' : 'Gemini API key';
  setValue('model', data.model || 'gemini-2.5-flash');
  setValue('subtitle-engine', data.subtitle_engine || 'local');
  setValue('local-whisper-model', data.local_whisper?.model || 'small');
  setValue('caption-base-url', data.caption_base_url || 'https://api.openai.com/v1');
  setValue('caption-model', data.caption_model || 'whisper-1');
  setValue('caption-api-key', '');
  const captionKey = $('caption-api-key');
  if (captionKey) captionKey.placeholder = data.caption_key_saved ? 'Caption API key tersimpan' : 'Whisper/OpenAI API key';
  setValue('subtitle-language', data.subtitle_language || 'id');
  setValue('video-quality', data.video_quality || '720');
  setValue('video-quality-main', data.video_quality || '720');
  setChecked('landscape-blur', !!data.landscape_blur);
  setValue('subtitle-font', data.subtitle_style?.font || 'Arial Black');
  setValue('subtitle-size', data.subtitle_style?.size || 65);
  setValue('subtitle-bottom-margin', data.subtitle_style?.bottom_margin || 400);
  setValue('output-dir', data.output_dir || '');
  setCookieStatus(data.cookies);
  toggleSubtitleEngineFields();
  updateCompactStatus('Idle');
}

function toggleSubtitleEngineFields() {
  const fields = $('api-whisper-fields');
  if (fields) fields.classList.toggle('hidden', getValue('subtitle-engine', 'local') !== 'api');
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
    const result = await api('/api/settings', { method: 'POST', body: JSON.stringify(settingsPayload({ api_key: apiKey })) });
    if (result.status !== 'saved') throw new Error(result.message || 'Gagal simpan');
    if (result.settings) applySettings(result.settings, false);
    setText('settings-status', apiKey ? 'Konfigurasi tersimpan. API key tersimpan.' : 'Konfigurasi tersimpan');
  } catch (error) { setText('settings-status', error.message); }
}

function settingsPayload(extra = {}) {
  return {
    base_url: getValue('base-url'),
    model: getValue('model'),
    subtitle_engine: getValue('subtitle-engine', 'local'),
    local_whisper: {
      enabled: true,
      model: getValue('local-whisper-model', 'small'),
      device: 'cpu',
      compute_type: 'int8',
    },
    caption_base_url: getValue('caption-base-url', 'https://api.openai.com/v1'),
    caption_api_key: getValue('caption-api-key'),
    caption_model: getValue('caption-model', 'whisper-1'),
    subtitle_language: getValue('subtitle-language', 'id'),
    video_quality: getValue('video-quality-main', getValue('video-quality', '720')),
    landscape_blur: getChecked('landscape-blur', false),
    subtitle_style: {
      font: getValue('subtitle-font', 'Arial Black'),
      size: Number(getValue('subtitle-size', '65') || 65),
      bottom_margin: Number(getValue('subtitle-bottom-margin', '400') || 400),
    },
    output_dir: getValue('output-dir'),
    ...extra,
  };
}

function updatePayloadJson() {
  const el = $('payload-json');
  if (!el || el.classList.contains('hidden')) return;
  const data = { settings: settingsPayload(), start: startPayload() };
  el.textContent = JSON.stringify(data, null, 2);
}

function showPayloadJson() {
  const el = $('payload-json');
  if (!el) return;
  el.classList.remove('hidden');
  updatePayloadJson();
}

async function clearApiKey() {
  try {
    const result = await api('/api/settings', { method: 'POST', body: JSON.stringify(settingsPayload({ clear_api_key: true })) });
    if (result.status !== 'saved') throw new Error(result.message || 'Gagal hapus API key');
    if (result.settings) applySettings(result.settings, false);
    setText('settings-status', 'API key dihapus');
  } catch (error) { setText('settings-status', error.message); }
}

function getScreenSize() { const selected = document.querySelector('input[name="screen_size"]:checked'); return selected ? selected.value : '9:16'; }
function setScreenSize(value) {
  document.querySelectorAll('[data-screen-card]').forEach((card) => {
    const selected = card.dataset.screenCard === value;
    const title = card.querySelector('span:first-of-type');
    const subtitle = card.querySelector('span:last-of-type');
    card.className = selected ? 'border border-indigo-600 bg-indigo-50/30 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer text-center transition' : 'border border-gray-200 hover:border-gray-300 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer text-center transition';
    if (title) title.className = selected ? 'text-[14px] font-bold text-indigo-600 block' : 'text-[14px] font-bold text-gray-700 block';
    if (subtitle) subtitle.className = selected ? 'text-[11px] text-indigo-500' : 'text-[11px] text-gray-400';
    const input = card.querySelector('input');
    if (input) input.checked = selected;
  });
}

function updateInstructionCount() { setText('instruction-count', `${getValue('instruction').length}/1000`); }
function saveInstruction() { savedInstruction = getValue('instruction').slice(0, 1000); setValue('instruction', savedInstruction); updateInstructionCount(); $('instruction-modal').classList.add('hidden'); }
function cancelInstruction() { setValue('instruction', savedInstruction); updateInstructionCount(); $('instruction-modal').classList.add('hidden'); }
function toggleProfileMenu() { const menu = $('profile-menu'); if (menu) menu.classList.toggle('hidden'); }

function startPayload(captionsOn = getChecked('captions', true)) {
  return {
    url: getValue('youtube-url'),
    num_clips: Number(getValue('num-clips', '3') || 3),
    add_captions: captionsOn,
    enable_captions: captionsOn,
    add_hook: false,
    screen_size: getScreenSize(),
    subtitle_language: getValue('subtitle-language', 'id'),
    landscape_blur: getChecked('landscape-blur', false),
    instruction: savedInstruction,
  };
}

async function startProcessing() {
  const button = $('process-button');
  if (button) button.disabled = true;
  refreshLogPanel();
  clearInterval(pollTimer);
  try {
    const captionsOn = getChecked('captions', true);
    await saveSettings();
    setChecked('captions', captionsOn);
    const result = await api('/api/start', { method: 'POST', body: JSON.stringify(startPayload(captionsOn)) });
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
    const message = data.error || data.message || data.status;
    setText('status-text', message);
    updateCompactStatus(message);
    updateLogPanel(data);
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

function updateCompactStatus(message) {
  const el = $('compact-status');
  if (!el) return;
  const clip = (String(message || '').match(/Clip (\d+\/\d+)/) || [])[1]?.replace('/', ' dari ') || '-';
  el.innerHTML = `Status: ${escapeHtml(message || 'Idle')}<br />Clip: ${escapeHtml(clip)} | Quality: ${escapeHtml(getValue('video-quality-main', '720'))}p | Mode: ${getChecked('landscape-blur', false) ? 'Blur' : 'Crop'}`;
}

function updateLogPanel(data) {
  const lines = $('log-lines');
  const summary = $('log-summary');
  if (!lines || !summary) return;
  const logs = data.logs || [];
  summary.textContent = `${data.status || 'idle'} · ${Math.round((data.progress || 0) * 100)}%`;
  lines.innerHTML = logs.length ? logs.map(renderLogLine).join('') : '<div class="text-gray-500">Belum ada log.</div>';
  lines.scrollTop = lines.scrollHeight;
}

function renderLogLine(line) {
  const safe = escapeHtml(line);
  if (line.includes('[Task]')) return `<div class="mt-4 mb-2 rounded-lg bg-indigo-600 px-3 py-2 font-sans text-[13px] font-bold text-white">${safe}</div>`;
  if (line.includes('[Error]')) return `<div class="text-red-300">${safe}</div>`;
  if (line.includes('[Done]')) return `<div class="text-green-300">${safe}</div>`;
  return `<div>${safe}</div>`;
}

async function refreshLogPanel() { try { updateLogPanel(await api('/api/status')); } catch (error) { const lines = $('log-lines'); if (lines) lines.innerHTML = `<div class="text-red-300">[Error] ${escapeHtml(error.message)}</div>`; } }
async function clearLogPanel() {
  const lines = $('log-lines');
  if (lines) lines.innerHTML = '<div class="text-gray-500">Belum ada log.</div>';
  setText('log-summary', 'cleared · 0%');
  try { await api('/api/logs/clear', { method: 'POST', body: '{}' }); } catch (error) { try { await api('/api/clear-logs', { method: 'POST', body: '{}' }); } catch (inner) {} }
}

async function renderOutputs() {
  const historyPanel = $('history-panel');
  const homePanel = $('home-results-panel');
  let groups = [];
  try { groups = (await api('/api/outputs')).groups || []; } catch (error) { if (historyPanel) historyPanel.innerHTML = `<p class="text-[13px] text-red-500">${escapeHtml(error.message)}</p>`; return; }
  const savedGroups = groups.filter((group) => group.saved);
  if (historyPanel) historyPanel.innerHTML = savedGroups.length ? savedGroups.map(renderSessionRow).join('') : '<p class="text-[13px] text-gray-500">Belum ada riwayat tersimpan.</p>';
  if (!homePanel) return;
  const pendingGroups = groups.map(withPendingClips).filter((group) => group.clips.length);
  homePanel.className = 'space-y-5 py-10 w-full';
  homePanel.innerHTML = pendingGroups.length ? pendingGroups.map(renderExportSession).join('') : renderEmptyHome();
}

function renderEmptyHome() {
  return `<div class="text-left max-w-md mx-auto text-[13px] text-gray-500 leading-relaxed"><h3 class="text-[18px] font-bold text-black mb-2">Belum ada hasil klip.</h3><p>Paste link YouTube di sebelah kiri dan mulai proses.</p><div class="mt-4 font-bold text-black">Tips:</div><ul class="list-disc pl-5 mt-1 space-y-1"><li>Video 5-60 menit paling optimal</li><li>Subtitle harus tersedia (Indonesia atau Inggris)</li><li>Gunakan Blur untuk video landscape</li></ul></div>`;
}

function withPendingClips(group) { const saved = new Set(group.saved_clips || []); return { ...group, clips: (group.clips || []).filter((clip) => !saved.has(clip.path)) }; }
function metaLine(group, count) { return `${count} klip tersedia | ${group.video_quality || '720'}p | ${group.landscape_blur ? 'Blur Background' : 'Crop'} | ${formatTime(group.timestamp)}`; }
function clipDuration(clip) { return clip.duration_seconds ? `Durasi: ${Math.round(clip.duration_seconds)}s` : 'Durasi: -'; }

function renderSessionRow(group) {
  const saved = new Set(group.saved_clips || []);
  const allClips = group.clips && group.clips.length ? group.clips : group.files || [];
  const clips = saved.size ? allClips.filter((clip) => saved.has(clip.path)) : allClips;
  return `<article class="border border-gray-200 rounded-2xl p-4 hover:bg-gray-50 transition-colors mb-3"><div class="flex items-start gap-4"><button class="text-left flex-1 min-w-0" type="button" data-session-toggle="${escapeAttr(group.path)}"><h3 class="font-bold text-[16px] text-black truncate">${escapeHtml(group.title)}</h3><p class="text-[12px] text-gray-400">${clips.length} klip tersimpan | ${escapeHtml(group.video_quality || '720')}p | ${formatTime(group.timestamp)}</p></button><button class="rounded-xl border border-red-100 px-3 py-2 text-[12px] font-bold text-red-600 hover:bg-red-50" type="button" data-delete-output="${escapeAttr(group.path)}" data-delete-kind="session">Hapus Session</button></div><div class="hidden mt-4 space-y-2" data-session-files="${escapeAttr(group.path)}">${clips.map(renderFileLink).join('')}</div></article>`;
}

function renderFileLink(file) {
  return `<div class="border border-gray-100 rounded-xl p-3 bg-white space-y-3"><video class="w-full max-h-[420px] rounded-lg bg-black" src="/api/download?path=${encodeURIComponent(file.path)}" controls preload="metadata"></video><div class="flex items-center justify-between gap-3"><div class="min-w-0"><div class="font-bold text-[14px] text-black truncate pr-3">${escapeHtml(file.title || file.name)}</div><div class="text-[12px] text-gray-400">${clipDuration(file)}</div></div><a class="text-[12px] text-gray-400" href="/api/download?path=${encodeURIComponent(file.path)}">Download</a></div></div>`;
}

function renderExportSession(group) {
  const clips = group.clips || [];
  return `<section class="border border-gray-200 rounded-2xl p-5 bg-white"><div class="flex items-start justify-between gap-4 mb-4"><div class="min-w-0"><h3 class="font-bold text-[20px] leading-tight text-gray-950 truncate">${escapeHtml(group.title)}</h3><p class="text-[13px] text-gray-500">${escapeHtml(metaLine(group, clips.length))}</p></div><div class="flex gap-2 shrink-0"><button class="rounded-xl bg-gray-950 text-white px-4 py-3 text-[13px] font-bold" type="button" data-save-output="${escapeAttr(group.path)}">Simpan yang dipilih</button><button class="rounded-xl border border-red-100 px-4 py-3 text-[13px] font-bold text-red-600 hover:bg-red-50" type="button" data-delete-output="${escapeAttr(group.path)}" data-delete-kind="session">Hapus Session</button></div></div><div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">${clips.map((clip, index) => renderExportCard(group, clip, index)).join('')}</div></section>`;
}

function renderExportCard(group, clip, index = 0) {
  if (!clip || !clip.path) return '';
  const href = `/api/download?path=${encodeURIComponent(clip.path)}`;
  return `<article class="bg-white border border-gray-200 rounded-2xl p-4"><div class="relative bg-gray-100 rounded-xl aspect-[9/12] overflow-hidden mb-3"><video class="w-full h-full object-cover" src="${href}" controls preload="metadata"></video></div><label class="flex items-center gap-2 text-[12px] font-bold text-gray-600 mb-3"><input type="checkbox" class="clip-select" data-clip-path="${escapeAttr(clip.path)}" data-session-path="${escapeAttr(group.path)}" checked> Pilih klip ${index + 1}</label><h3 class="font-bold text-[16px] leading-tight text-gray-950 mb-1 line-clamp-2">${escapeHtml(clip.title || `Klip ${index + 1}`)}</h3><p class="text-[13px] text-gray-500 mb-1 line-clamp-2">${escapeHtml(clip.description || group.caption)}</p><p class="text-[12px] text-gray-400 mb-4">${clipDuration(clip)}</p><div class="grid grid-cols-[1fr_auto_auto] gap-2"><a class="flex items-center justify-center rounded-xl bg-gray-950 text-white px-4 py-3 text-[13px] font-bold" href="${href}">Download</a><button class="rounded-xl border border-gray-200 px-4 py-3 text-[13px] font-bold text-gray-700 hover:bg-gray-50" type="button" data-save-output="${escapeAttr(group.path)}" data-save-one="${escapeAttr(clip.path)}">Simpan</button><button class="rounded-xl border border-red-100 px-4 py-3 text-[13px] font-bold text-red-600 hover:bg-red-50" type="button" data-delete-output="${escapeAttr(clip.path)}" data-delete-kind="clip">Hapus</button></div></article>`;
}

function confirmDelete(message) {
  const modal = $('confirm-modal');
  setText('confirm-message', message);
  if (modal) modal.classList.remove('hidden');
  return new Promise((resolve) => { pendingConfirm = resolve; });
}

async function deleteOutput(path, kind = 'clip') {
  if (!path || !(await confirmDelete(kind === 'session' ? 'Session dan semua klip di dalamnya akan dihapus permanen.' : 'Klip ini akan dihapus permanen.'))) return;
  try { await api('/api/delete', { method: 'POST', body: JSON.stringify({ path }) }); await renderOutputs(); } catch (error) { setText('status-text', error.message); }
}

async function saveOutput(path, oneClip) {
  if (!path) return;
  const inputs = [...document.querySelectorAll(`.clip-select[data-session-path="${cssEscape(path)}"]`)];
  const selected = oneClip ? [oneClip] : inputs.filter((input) => input.checked).map((input) => input.dataset.clipPath);
  if (!selected.length) { setText('status-text', 'Pilih minimal 1 klip'); return; }
  try { await api('/api/save', { method: 'POST', body: JSON.stringify({ path, clips: selected }) }); await renderOutputs(); } catch (error) { setText('status-text', error.message); }
}

function toggleSession(path) { document.querySelectorAll('[data-session-files]').forEach((el) => el.classList.toggle('hidden', el.dataset.sessionFiles !== path || !el.classList.contains('hidden'))); }
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? (value || '') : date.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }); }
function showPage(name) {
  const home = $('page-home'); const history = $('page-history'); const consolePage = $('page-console');
  if (!home || !history || !consolePage) return;
  home.classList.toggle('hidden', name !== 'home');
  history.classList.toggle('hidden', name !== 'history');
  consolePage.classList.toggle('hidden', name !== 'console');
  setNavActive('nav-home', name === 'home');
  setNavActive('nav-history', name === 'history');
  setNavActive('nav-console', name === 'console');
  if (name === 'history') renderOutputs();
  if (name === 'console') refreshLogPanel();
}

function setNavActive(id, active) {
  const el = $(id);
  if (!el) return;
  el.className = active ? 'flex items-center space-x-3.5 px-4 py-3 rounded-xl bg-[#eaeaea] text-black font-bold text-[15px]' : 'flex items-center space-x-3.5 px-4 py-3 rounded-xl text-gray-600 hover:bg-gray-100 hover:text-black font-semibold text-[15px] transition-colors';
}

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }
function cssEscape(value) { return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/"/g, '\\"'); }

document.addEventListener('DOMContentLoaded', () => {
  const save = $('save-settings'); const showJson = $('show-json'); const clearKey = $('clear-api-key'); const start = $('process-button'); const navHome = $('nav-home'); const navHistory = $('nav-history'); const navConsole = $('nav-console'); const profile = $('profile-button'); const logClear = $('log-clear'); const instruction = $('instruction'); const instructionSave = $('instruction-save'); const instructionCancel = $('instruction-cancel'); const qualityMain = $('video-quality-main'); const qualitySettings = $('video-quality'); const blur = $('landscape-blur');
  if (save) save.addEventListener('click', saveSettings);
  if (showJson) showJson.addEventListener('click', showPayloadJson);
  if (clearKey) clearKey.addEventListener('click', clearApiKey);
  if (start) start.addEventListener('click', startProcessing);
  if (profile) profile.addEventListener('click', toggleProfileMenu);
  if (logClear) logClear.addEventListener('click', clearLogPanel);
  if (instruction) instruction.addEventListener('input', updateInstructionCount);
  if (instructionSave) instructionSave.addEventListener('click', saveInstruction);
  if (instructionCancel) instructionCancel.addEventListener('click', cancelInstruction);
  if (qualityMain && qualitySettings) qualityMain.addEventListener('change', () => { qualitySettings.value = qualityMain.value; updateCompactStatus($('status-text')?.textContent || 'Idle'); });
  if (qualitySettings && qualityMain) qualitySettings.addEventListener('change', () => { qualityMain.value = qualitySettings.value; updateCompactStatus($('status-text')?.textContent || 'Idle'); });
  const subtitleEngine = $('subtitle-engine');
  if (subtitleEngine) subtitleEngine.addEventListener('change', toggleSubtitleEngineFields);
  if (blur) blur.addEventListener('change', () => updateCompactStatus($('status-text')?.textContent || 'Idle'));
  document.querySelectorAll('[data-screen-card]').forEach((card) => card.addEventListener('click', () => setScreenSize(card.dataset.screenCard)));
  document.addEventListener('input', updatePayloadJson);
  document.addEventListener('change', updatePayloadJson);
  document.addEventListener('click', (event) => {
    const deleteButton = event.target.closest('[data-delete-output]');
    const saveButton = event.target.closest('[data-save-output]');
    const sessionButton = event.target.closest('[data-session-toggle]');
    if (deleteButton) deleteOutput(deleteButton.dataset.deleteOutput, deleteButton.dataset.deleteKind);
    if (saveButton) saveOutput(saveButton.dataset.saveOutput, saveButton.dataset.saveOne);
    if (sessionButton) toggleSession(sessionButton.dataset.sessionToggle);
  });
  const confirmCancel = $('confirm-cancel'); const confirmOk = $('confirm-ok');
  if (confirmCancel) confirmCancel.addEventListener('click', () => { $('confirm-modal').classList.add('hidden'); if (pendingConfirm) pendingConfirm(false); });
  if (confirmOk) confirmOk.addEventListener('click', () => { $('confirm-modal').classList.add('hidden'); if (pendingConfirm) pendingConfirm(true); });
  if (navHome) navHome.addEventListener('click', (event) => { event.preventDefault(); showPage('home'); });
  if (navHistory) navHistory.addEventListener('click', (event) => { event.preventDefault(); showPage('history'); });
  if (navConsole) navConsole.addEventListener('click', (event) => { event.preventDefault(); showPage('console'); });
  setScreenSize(getScreenSize());
  updateInstructionCount();
  loadSettings();
  renderOutputs();
});
