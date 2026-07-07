const $ = (id) => document.getElementById(id);
let pollTimer = null;
let savedInstruction = '';
let pendingConfirm = null;
let smoothProgress = 0;
let smoothProgressTarget = 0;
let smoothProgressTimer = null;
let processingActive = false;

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
  return data;
}

function setText(id, value) { const el = $(id); if (el) el.textContent = value; }
function setValue(id, value) {
  const el = $(id);
  if (el) {
    el.value = value;
    el.dispatchEvent(new Event('change'));
  }
}
function getValue(id, fallback = '') { const el = $(id); return el ? el.value : fallback; }
function getChecked(id, fallback = false) { const el = $(id); return el ? el.checked : fallback; }
function setChecked(id, value) { const el = $(id); if (el) el.checked = value; }

function initCustomSelects() {
  document.querySelectorAll('select').forEach(select => {
    if (select.nextElementSibling && select.nextElementSibling.classList.contains('custom-select-wrapper')) {
      return;
    }
    select.style.display = 'none';
    const wrapper = document.createElement('div');
    wrapper.className = 'relative w-full custom-select-wrapper';
    
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = select.className.replace('w-full', '') + ' w-full flex items-center justify-between text-left hover:bg-gray-50 focus:outline-none transition';
    
    const label = document.createElement('span');
    label.className = 'custom-select-label truncate';
    
    const updateLabel = () => {
      const selectedOpt = select.options[select.selectedIndex];
      label.textContent = selectedOpt ? selectedOpt.textContent : '';
    };
    updateLabel();
    
    const arrow = document.createElement('div');
    arrow.innerHTML = `
      <svg class="w-4 h-4 text-gray-400 ml-2 transition-transform duration-200 custom-select-arrow" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
      </svg>
    `;
    
    btn.appendChild(label);
    btn.appendChild(arrow.firstElementChild);
    wrapper.appendChild(btn);
    
    const menu = document.createElement('div');
    menu.className = 'hidden absolute left-0 right-0 mt-1 bg-white border border-gray-100 rounded-xl shadow-lg z-[100] max-h-60 overflow-y-auto p-1 space-y-0.5';
    
    const rebuildOptions = () => {
      menu.innerHTML = '';
      Array.from(select.options).forEach(opt => {
        const optBtn = document.createElement('button');
        optBtn.type = 'button';
        const isSelected = opt.value === select.value;
        optBtn.className = `w-full px-3 py-2 rounded-lg text-left text-[13px] transition font-medium ` + 
          (isSelected ? `bg-orange-50 text-[#ea580c]` : `text-gray-700 hover:bg-gray-50`);
        optBtn.textContent = opt.textContent;
        optBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          select.value = opt.value;
          select.dispatchEvent(new Event('change'));
          updateLabel();
          menu.classList.add('hidden');
          btn.querySelector('.custom-select-arrow').classList.remove('rotate-180');
          rebuildOptions();
        });
        menu.appendChild(optBtn);
      });
    };
    
    rebuildOptions();
    wrapper.appendChild(menu);
    
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      document.querySelectorAll('.custom-select-wrapper div').forEach(m => {
        if (m !== menu) {
          m.classList.add('hidden');
          const siblingBtn = m.previousElementSibling;
          if (siblingBtn) {
            const arrowIcon = siblingBtn.querySelector('.custom-select-arrow');
            if (arrowIcon) arrowIcon.classList.remove('rotate-180');
          }
        }
      });
      const isHidden = menu.classList.toggle('hidden');
      const arrowIcon = btn.querySelector('.custom-select-arrow');
      if (arrowIcon) {
        arrowIcon.classList.toggle('rotate-180', !isHidden);
      }
      if (!isHidden) rebuildOptions();
    });
    
    select.parentNode.insertBefore(wrapper, select.nextSibling);
    
    select.addEventListener('change', () => {
      updateLabel();
      rebuildOptions();
    });
  });
}

function showError(message) {
  let container = $('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed bottom-6 right-6 z-[200] flex flex-col gap-2 pointer-events-none';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = 'pointer-events-auto bg-red-50 text-red-800 border border-red-100 rounded-xl px-4 py-3 shadow-lg flex items-center gap-3 max-w-sm transition-all duration-300 transform translate-y-4 opacity-0';
  toast.innerHTML = `
    <svg class="w-[18px] h-[18px] text-red-500 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
    </svg>
    <span class="text-[13px] font-semibold leading-normal">${escapeHtml(message)}</span>
  `;
  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.className = toast.className.replace('translate-y-4 opacity-0', 'translate-y-0 opacity-100');
  });
  setTimeout(() => {
    toast.className = toast.className.replace('translate-y-0 opacity-100', 'translate-y-4 opacity-0');
    setTimeout(() => {
      toast.remove();
      if (container.children.length === 0) container.remove();
    }, 300);
  }, 1500);
}

async function loadSettings() {
  try { applySettings(await api('/api/settings'), false); } catch (error) { showError(error.message); }
}

function applySettings(data, keepApiKey) {
  setValue('base-url', data.base_url || 'https://generativelanguage.googleapis.com/v1beta/openai');
  if (!keepApiKey) setValue('api-key', '');
  const keyInput = $('api-key');
  if (keyInput) keyInput.placeholder = data.api_key_saved ? 'API key tersimpan' : 'Gemini API key';
  setValue('model', data.model || 'gemini-2.5-flash');
  setValue('subtitle-engine', data.subtitle_engine || 'local');
  setValue('local-whisper-model', data.local_whisper?.model || 'medium');
  setValue('caption-base-url', data.caption_base_url || 'https://api.openai.com/v1');
  setValue('caption-model', data.caption_model || 'whisper-1');
  setValue('caption-api-key', '');
  const captionKey = $('caption-api-key');
  if (captionKey) captionKey.placeholder = data.caption_key_saved ? 'Caption API key tersimpan' : 'Whisper/OpenAI API key';
  setValue('subtitle-language', data.subtitle_language || 'id');
  setValue('video-quality', data.video_quality || '720');
  setValue('video-quality-main', data.video_quality || '720');
  setChecked('landscape-blur', !!data.landscape_blur);
  setValue('subtitle-font', data.subtitle_style?.font || 'Plus Jakarta Sans');
  setValue('subtitle-size', data.subtitle_style?.size || 65);
  setValue('subtitle-position', data.subtitle_position || 'auto');
  setValue('subtitle-bottom-margin', data.subtitle_style?.bottom_margin || 400);
  setValue('output-dir', data.output_dir || '');
  setCookieStatus(data.cookies);
  toggleSubtitleEngineFields();
  updateCompactStatus('Idle');
}

function toggleSubtitleEngineFields() {
  const fields = $('api-whisper-fields');
  if (fields) fields.classList.toggle('hidden', getValue('subtitle-engine', 'local') === 'local');
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
  } catch (error) { showError(error.message); }
}

function settingsPayload(extra = {}) {
  return {
    base_url: getValue('base-url'),
    model: getValue('model'),
    subtitle_engine: getValue('subtitle-engine', 'local'),
    local_whisper: {
      enabled: true,
      model: getValue('local-whisper-model', 'medium'),
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
      font: getValue('subtitle-font', 'Plus Jakarta Sans'),
      size: Number(getValue('subtitle-size', '65') || 65),
      bottom_margin: Number(getValue('subtitle-bottom-margin', '400') || 400),
    },
    subtitle_position: getValue('subtitle-position', 'auto'),
    output_dir: getValue('output-dir'),
    ...extra,
  };
}

function previewPayload() {
  const settings = settingsPayload();
  const engine = settings.subtitle_engine;
  const apiChanged = settings.caption_api_key || settings.caption_model !== 'whisper-1' || settings.caption_base_url !== 'https://api.openai.com/v1';
  if (engine === 'local' || (engine === 'auto' && !apiChanged)) {
    delete settings.caption_base_url;
    delete settings.caption_model;
    delete settings.caption_api_key;
  }
  return settings;
}

function updatePayloadJson() {
  const el = $('payload-json');
  if (!el || $('json-modal')?.classList.contains('hidden')) return;
  el.textContent = JSON.stringify({ settings: previewPayload(), start: startPayload() }, null, 2);
}

function showPayloadJson() {
  const modal = $('json-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  updatePayloadJson();
}

async function clearApiKey() {
  try {
    const result = await api('/api/settings', { method: 'POST', body: JSON.stringify(settingsPayload({ clear_api_key: true })) });
    if (result.status !== 'saved') throw new Error(result.message || 'Gagal hapus API key');
    if (result.settings) applySettings(result.settings, false);
    setText('settings-status', 'API key dihapus');
  } catch (error) { showError(error.message); }
}

function getScreenSize() { const selected = document.querySelector('input[name="screen_size"]:checked'); return selected ? selected.value : '9:16'; }
function setScreenSize(value) {
  if (!['9:16', '16:9'].includes(value)) value = '9:16';
  document.querySelectorAll('[data-screen-card]').forEach((card) => {
    const selected = card.dataset.screenCard === value;
    const title = card.querySelector('span:first-of-type');
    const subtitle = card.querySelector('span:last-of-type');
    const supported = ['9:16', '16:9'].includes(card.dataset.screenCard);
    card.className = selected ? 'border border-orange-600 bg-orange-50/30 rounded-xl p-3 flex flex-col items-center justify-center cursor-pointer text-center transition' : `border border-gray-200 rounded-xl p-3 flex flex-col items-center justify-center text-center transition ${supported ? 'hover:border-gray-300 cursor-pointer' : 'opacity-50 cursor-not-allowed'}`;
    if (title) title.className = selected ? 'text-[14px] font-semibold text-white block' : 'text-[14px] font-semibold text-gray-700 block';
    if (subtitle) subtitle.className = selected ? 'text-[11px] text-white' : 'text-[11px] text-gray-400';
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
    add_hook: getChecked('add-hook', false),
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
  smoothProgress = 0;
  setProgressTarget(0);
  processingActive = true;
  await renderOutputs();
  try {
    const captionsOn = getChecked('captions', true);
    await saveSettings();
    setChecked('captions', captionsOn);
    const result = await api('/api/start', { method: 'POST', body: JSON.stringify(startPayload(captionsOn)) });
    if (result.status !== 'started') throw new Error(result.message || 'Gagal mulai');
    pollTimer = setInterval(pollStatus, 800);
    pollStatus();
  } catch (error) {
    processingActive = false;
    if (button) button.disabled = false;
    showError(error.message);
    setText('status-text', 'Gagal memproses');
    await renderOutputs();
  }
}

async function pollStatus() {
  try {
    const data = await api('/api/status');
    const progressPct = Math.round((data.progress || 0) * 100);
    if (data.status === 'error') {
      processingActive = false;
      showError(data.error || data.message || 'Terjadi kesalahan');
      setText('status-text', 'Gagal');
      updateCompactStatus('Gagal');
    } else {
      processingActive = ['started', 'processing', 'running'].includes(data.status);
      const rawMsg = data.error || data.message || data.status;
      const message = cleanStatusText(rawMsg);
      
      let displayMsg = message;
      if (processingActive) {
        displayMsg = `${message} (${progressPct}%)`;
      }
      setText('status-text', displayMsg);
      updateCompactStatus(message);

      if (processingActive) {
        const homePanel = $('home-results-panel');
        if (homePanel) {
          const loaderPct = homePanel.querySelector('.loader-percentage');
          if (!loaderPct) {
            homePanel.className = 'flex h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full';
            homePanel.innerHTML = renderProcessingLoader(data.progress || 0, message);
          } else {
            loaderPct.textContent = `${progressPct}%`;
            const loaderMsg = $('loading-status-text');
            if (loaderMsg) loaderMsg.textContent = message;
          }
        }
      }
    }
    updateLogPanel(data);
    setProgressTarget(data.progress || 0);
    if (data.status === 'complete' || data.status === 'error') {
      processingActive = false;
      clearInterval(pollTimer);
      $('process-button').disabled = false;
      await renderOutputs();
    }
  } catch (error) {
    processingActive = false;
    clearInterval(pollTimer);
    $('process-button').disabled = false;
    showError(error.message);
    setText('status-text', 'Error koneksi');
    await renderOutputs();
  }
}

function cleanStatusText(message) {
  const text = String(message || '');
  if (/api_key|config|using api/i.test(text)) return 'Menyiapkan AI...';
  if (/ffmpeg\.exe|-progress pipe|^"[A-Z]:\\/i.test(text)) return 'Memproses video...';
  if (/subtitle|caption/i.test(text)) return 'Menambahkan subtitle...';
  if (/portrait|crop|blur/i.test(text)) return 'Membuat portrait...';
  if (/cut|trim|clip/i.test(text)) return 'Memotong video...';
  if (/final/i.test(text)) return 'Finalizing...';
  if (/started|processing/i.test(text)) return 'Memproses...';
  return text;
}

function setProgressTarget(value) {
  smoothProgressTarget = Math.max(0, Math.min(1, Number(value) || 0));
  if (smoothProgressTimer) return;
  smoothProgressTimer = setInterval(() => {
    smoothProgress += (smoothProgressTarget - smoothProgress) * 0.35;
    if (Math.abs(smoothProgressTarget - smoothProgress) < 0.002) smoothProgress = smoothProgressTarget;
    const bar = $('progress-bar');
    if (bar) bar.style.width = `${Math.round(smoothProgress * 100)}%`;
    if (smoothProgress === smoothProgressTarget) { clearInterval(smoothProgressTimer); smoothProgressTimer = null; }
  }, 80);
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
  const nearBottom = lines.scrollHeight - lines.scrollTop - lines.clientHeight < 80;
  lines.innerHTML = logs.length ? logs.map(renderLogLine).join('') : '<div class="text-gray-500">Belum ada log.</div>';
  if (nearBottom) lines.scrollTop = lines.scrollHeight;
}

function renderLogLine(line) {
  const safe = escapeHtml(line);
  if (line.includes('[Task]')) {
    const body = line.split('] ').pop().replace(/^Task /, '');
    const [time, url] = body.split(' | ');
    return `<div>${'='.repeat(60)}</div><div>TASK ${escapeHtml(time || '')}</div><div>URL: ${escapeHtml(url || '')}</div><div>${'='.repeat(60)}</div>`;
  }
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

function renderProcessingLoader(progress = 0, message = 'Menyiapkan AI...') {
  const pct = Math.round(progress * 100);
  return `<div class="w-14 h-14 relative mb-5 mx-auto flex items-center justify-center">
    <div class="absolute inset-0 rounded-full border-[3.5px] border-orange-100 border-t-orange-600 animate-spin"></div>
    <span class="text-[11px] font-semibold text-orange-600 loader-percentage">${pct}%</span>
  </div>
  <h3 class="text-[19px] font-semibold text-black mb-2.5 tracking-tight animate-pulse">AI Sedang Memproses</h3>
  <p class="text-[13px] text-gray-500 leading-relaxed max-w-md mx-auto" id="loading-status-text">
    ${escapeHtml(message)}
  </p>`;
}

async function renderOutputs() {
  const historyPanel = $('history-panel');
  const homePanel = $('home-results-panel');
  let groups = [];
  try { groups = (await api('/api/outputs')).groups || []; } catch (error) { if (historyPanel) historyPanel.innerHTML = `<p class="text-[13px] text-red-500">${escapeHtml(error.message)}</p>`; return; }
  const savedGroups = groups.filter((group) => group.saved);
  if (historyPanel) historyPanel.innerHTML = savedGroups.length ? savedGroups.map(renderSessionRow).join('') : '<p class="text-[13px] text-gray-500">Belum ada riwayat tersimpan.</p>';
  if (!homePanel) return;
  
  if (processingActive) {
    homePanel.className = 'flex h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full';
    homePanel.innerHTML = renderProcessingLoader(0, 'Menyiapkan AI...');
    return;
  }
  
  const pendingGroups = groups.map(withPendingClips).filter((group) => group.clips.length);
  if (pendingGroups.length) {
    homePanel.className = 'space-y-5 w-full';
    homePanel.innerHTML = pendingGroups.map(renderExportSession).join('');
  } else {
    homePanel.className = 'flex h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full';
    homePanel.innerHTML = renderEmptyHome();
  }
}

function renderEmptyHome() {
  return `<div class="w-14 h-14 bg-[#fff7ed] text-[#ea580c] rounded-2xl flex items-center justify-center mb-5 mx-auto">
    <svg class="w-6 h-6 text-[#ea580c]" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
    </svg>
  </div>
  <h3 class="text-[19px] font-semibold text-black mb-2.5 tracking-tight">Siap Membuat Klip Viral Pertamamu?</h3>
  <p class="text-[13px] text-gray-500 leading-relaxed max-w-md mx-auto">
    Tempel link YouTube di atas, dan biarkan AI kami menemukan 3 momen emas terbaik dari videomu. Proses otomatis, hasil profesional.
  </p>`;
}

function withPendingClips(group) { const saved = new Set(group.saved_clips || []); return { ...group, clips: (group.clips || []).filter((clip) => !saved.has(clip.path)) }; }
function metaLine(group, count) { return `${count} klip tersedia | ${group.video_quality || '720'}p | ${group.landscape_blur ? 'Blur Background' : 'Crop'} | ${formatTime(group.timestamp)}`; }
function clipDuration(clip) { return clip.duration_seconds ? `Durasi: ${Math.round(clip.duration_seconds)}s` : 'Durasi: -'; }

function renderSessionRow(group) {
  const saved = new Set(group.saved_clips || []);
  const allClips = group.clips && group.clips.length ? group.clips : group.files || [];
  const clips = saved.size ? allClips.filter((clip) => saved.has(clip.path)) : allClips;
  return `<article class="border border-gray-200 rounded-2xl p-4 hover:bg-gray-50 transition-colors mb-3"><button class="text-left w-full min-w-0" type="button" data-session-toggle="${escapeAttr(group.path)}"><h3 class="font-semibold text-[16px] text-black truncate">${escapeHtml(group.title)}</h3><p class="text-[12px] text-gray-400">${clips.length} klip tersimpan | ${escapeHtml(group.video_quality || '720')}p | ${formatTime(group.timestamp)}</p></button><div class="hidden mt-4 flex flex-wrap gap-4 justify-center" data-session-files="${escapeAttr(group.path)}">${clips.map(renderFileLink).join('')}</div></article>`;
}

function renderFileLink(file) {
  const href = `/api/download?path=${encodeURIComponent(file.path)}`;
  return `<article class="bg-white border border-gray-200 rounded-xl p-3 flex flex-col w-[260px] shrink-0 overflow-hidden">
    <button type="button" class="relative bg-gray-100 rounded-lg aspect-[4/3] overflow-hidden mb-2 cursor-zoom-in" data-video-open="${escapeAttr(href)}">
      <video class="w-full h-full object-cover pointer-events-none" src="${href}" muted preload="metadata"></video>
    </button>
    <div class="flex flex-col flex-1 min-h-0">
      <h3 class="font-semibold text-[13px] leading-snug text-gray-950 mb-1 whitespace-normal break-words">${escapeHtml(file.title || file.name)}</h3>
      <p class="text-[11px] text-gray-400 mb-3 mt-auto">${clipDuration(file)}</p>
      <a class="flex items-center justify-center rounded-lg bg-[#ea580c] hover:bg-[#c2410c] text-white py-2 text-[10px] font-semibold transition text-center" href="${href}">Download</a>
    </div>
  </article>`;
}

function renderExportSession(group) {
  const clips = group.clips || [];
  const status = $('compact-status')?.innerHTML || 'Status: Idle<br>Clip: - | Quality: 480p | Mode: Blur';
  return `<section class="border-0 p-6 bg-transparent w-full max-w-full h-full overflow-hidden flex flex-col"><div class="mb-6"><h2 class="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Hasil Klip</h2><p class="text-[13px] text-gray-500">Lihat klip yang sudah jadi dan pantau progress yang sedang diproses.</p></div><div class="flex flex-wrap gap-4 justify-center">${clips.map((clip, index) => renderExportCard(group, clip, index)).join('')}</div><div class="mt-4 text-center"><h3 class="font-semibold text-[16px] leading-snug text-gray-950 whitespace-normal break-words">${escapeHtml(group.title)}</h3><p class="text-[12px] text-gray-500 whitespace-normal break-words mt-1">${escapeHtml(metaLine(group, clips.length))}</p></div><div class="text-[13px] text-gray-500 mt-auto pt-6">${status}</div></section>`;
}

function renderExportCard(group, clip, index = 0) {
  if (!clip || !clip.path) return '';
  const href = `/api/download?path=${encodeURIComponent(clip.path)}`;
  return `<article class="bg-white border border-gray-200 rounded-xl p-3 flex flex-col w-[260px] shrink-0 overflow-hidden">
    <button type="button" class="relative bg-gray-100 rounded-lg aspect-[4/3] overflow-hidden mb-2 cursor-zoom-in" data-video-open="${escapeAttr(href)}">
      <video class="w-full h-full object-cover pointer-events-none" src="${href}" muted preload="metadata"></video>
    </button>
    <div class="flex flex-col flex-1 min-h-0">
      <h3 class="font-semibold text-[13px] leading-snug text-gray-950 mb-1 whitespace-normal break-words">${escapeHtml(clip.title || `Klip ${index + 1}`)}</h3>
      <p class="text-[12px] text-gray-500 mb-2 leading-relaxed whitespace-normal break-words overflow-hidden" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">${escapeHtml(clip.description || group.caption)}</p>
      <p class="text-[11px] text-gray-400 mb-3 mt-auto">${clipDuration(clip)}</p>
      <div class="grid grid-cols-3 gap-1.5">
        <a class="flex items-center justify-center rounded-lg bg-[#ea580c] hover:bg-[#c2410c] text-white py-2 text-[10px] font-semibold transition text-center" href="${href}">Download</a>
        <button class="rounded-lg bg-white border border-gray-200 py-2 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-save-output="${escapeAttr(group.path)}" data-save-one="${escapeAttr(clip.path)}">Simpan</button>
        <button class="rounded-lg bg-white border border-gray-200 py-2 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-delete-output="${escapeAttr(clip.path)}" data-delete-kind="clip">Hapus</button>
      </div>
    </div>
  </article>`;
}

function confirmDelete(message) {
  const modal = $('confirm-modal');
  setText('confirm-message', message);
  if (modal) modal.classList.remove('hidden');
  return new Promise((resolve) => { pendingConfirm = resolve; });
}

async function deleteOutput(path, kind = 'clip') {
  if (!path || !(await confirmDelete(kind === 'session' ? 'Session dan semua klip di dalamnya akan dihapus permanen.' : 'Klip ini akan dihapus permanen.'))) return;
  try { await api('/api/delete', { method: 'POST', body: JSON.stringify({ path }) }); await renderOutputs(); } catch (error) { showError(error.message); }
}

async function saveOutput(path, oneClip) {
  if (!path) return;
  const inputs = [...document.querySelectorAll(`.clip-select[data-session-path="${cssEscape(path)}"]`)];
  const selected = oneClip ? [oneClip] : inputs.filter((input) => input.checked).map((input) => input.dataset.clipPath);
  if (!selected.length) { showError('Pilih minimal 1 klip'); return; }
  try { await api('/api/save', { method: 'POST', body: JSON.stringify({ path, clips: selected }) }); await renderOutputs(); } catch (error) { showError(error.message); }
}

function toggleSession(path) { document.querySelectorAll('[data-session-files]').forEach((el) => el.classList.toggle('hidden', el.dataset.sessionFiles !== path || !el.classList.contains('hidden'))); }
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? (value || '') : date.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }); }
function showPage(name) {
  const home = $('page-home'); const history = $('page-history'); const consolePage = $('page-console'); const social = $('page-social'); const settings = $('page-settings');
  if (!home || !history || !consolePage || !social || !settings) return;
  home.classList.toggle('hidden', name !== 'home');
  history.classList.toggle('hidden', name !== 'history');
  consolePage.classList.toggle('hidden', name !== 'console');
  social.classList.toggle('hidden', name !== 'social');
  settings.classList.toggle('hidden', name !== 'settings');
  setNavActive('nav-home', name === 'home');
  setNavActive('nav-history', name === 'history');
  setNavActive('nav-console', name === 'console');
  setNavActive('nav-social', name === 'social');
  setNavActive('nav-settings', name === 'settings');

  if (name === 'home') pollStatus();
  if (name === 'history') renderOutputs();
  if (name === 'console') refreshLogPanel();
  if (name === 'settings') loadSettings();
}

function setNavActive(id, active) {
  const el = $(id);
  if (!el) return;
  el.className = active
    ? 'px-3 py-2 rounded-xl bg-[#2a3446] text-[#f15a24] transition'
    : 'px-3 py-2 rounded-xl text-gray-500 hover:bg-gray-50 hover:text-gray-900 transition';
}

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }
function cssEscape(value) { return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/"/g, '\\"'); }
function openVideoModal(src) {
  const modal = $('video-modal');
  const player = $('video-modal-player');
  if (!modal || !player) return;
  player.src = src;
  modal.classList.remove('hidden');
  player.play().catch(() => {});
}
function closeVideoModal() {
  const modal = $('video-modal');
  const player = $('video-modal-player');
  if (!modal || !player) return;
  player.pause();
  player.removeAttribute('src');
  player.load();
  modal.classList.add('hidden');
}
function closeModal(id) {
  const modal = $(id);
  if (!modal) return;
  modal.classList.add('hidden');
  if (id === 'confirm-modal' && pendingConfirm) pendingConfirm(false);
}

document.addEventListener('DOMContentLoaded', () => {
  const save = $('save-settings'); const showJson = $('show-json'); const jsonClose = $('json-close'); const videoClose = $('video-modal-close'); const clearKey = $('clear-api-key'); const start = $('process-button'); const profile = $('profile-button'); const logClear = $('log-clear'); const instruction = $('instruction'); const instructionSave = $('instruction-save'); const instructionCancel = $('instruction-cancel'); const qualityMain = $('video-quality-main'); const qualitySettings = $('video-quality'); const blur = $('landscape-blur');
  if (save) save.addEventListener('click', saveSettings);
  if (showJson) showJson.addEventListener('click', showPayloadJson);
  if (jsonClose) jsonClose.addEventListener('click', () => $('json-modal')?.classList.add('hidden'));
  if (videoClose) videoClose.addEventListener('click', closeVideoModal);
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
  ['instruction-modal', 'settings-modal', 'json-modal', 'confirm-modal'].forEach((id) => {
    const modal = $(id);
    if (modal) modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(id); });
  });
  $('video-modal')?.addEventListener('click', (event) => { if (event.target === $('video-modal')) closeVideoModal(); });
  document.addEventListener('click', (event) => {
    const videoButton = event.target.closest('[data-video-open]');
    const deleteButton = event.target.closest('[data-delete-output]');
    const saveButton = event.target.closest('[data-save-output]');
    const sessionButton = event.target.closest('[data-session-toggle]');
    if (videoButton) openVideoModal(videoButton.dataset.videoOpen);
    if (deleteButton) deleteOutput(deleteButton.dataset.deleteOutput, deleteButton.dataset.deleteKind);
    if (saveButton) saveOutput(saveButton.dataset.saveOutput, saveButton.dataset.saveOne);
    if (sessionButton) toggleSession(sessionButton.dataset.sessionToggle);
  });
  const confirmCancel = $('confirm-cancel'); const confirmOk = $('confirm-ok');
  if (confirmCancel) confirmCancel.addEventListener('click', () => { $('confirm-modal').classList.add('hidden'); if (pendingConfirm) pendingConfirm(false); });
  if (confirmOk) confirmOk.addEventListener('click', () => { $('confirm-modal').classList.add('hidden'); if (pendingConfirm) pendingConfirm(true); });
  document.querySelectorAll('[data-page]').forEach((nav) => nav.addEventListener('click', (event) => {
    event.preventDefault();
    showPage(nav.dataset.page);
  }));

  const contentToggle = $('nav-content-toggle');
  const contentSubmenu = $('nav-content-submenu');
  if (contentToggle && contentSubmenu) {
    contentToggle.addEventListener('click', (event) => {
      event.preventDefault();
      const isHidden = contentSubmenu.classList.toggle('hidden');
      const arrow = contentToggle.querySelector('.submenu-arrow');
      if (arrow) arrow.classList.toggle('rotate-180', !isHidden);
    });
  }
  const instructionModal = $('instruction-modal');
  if (instructionModal) {
    instructionModal.addEventListener('click', (e) => {
      if (e.target === instructionModal) cancelInstruction();
    });
  }
  const jsonModal = $('json-modal');
  if (jsonModal) {
    jsonModal.addEventListener('click', (e) => {
      if (e.target === jsonModal) jsonModal.classList.add('hidden');
    });
  }
  const confirmModal = $('confirm-modal');
  if (confirmModal) {
    confirmModal.addEventListener('click', (e) => {
      if (e.target === confirmModal) {
        confirmModal.classList.add('hidden');
        if (pendingConfirm) pendingConfirm(false);
      }
    });
  }
  document.addEventListener('click', (e) => {
    const profileMenu = $('profile-menu');
    const profileButton = $('profile-button');
    if (profileMenu && profileButton && !profileMenu.classList.contains('hidden')) {
      if (!profileButton.contains(e.target) && !profileMenu.contains(e.target)) {
        profileMenu.classList.add('hidden');
      }
    }
  });
  initCustomSelects();

  document.addEventListener('click', () => {
    document.querySelectorAll('.custom-select-wrapper div').forEach(menu => {
      menu.classList.add('hidden');
    });
    document.querySelectorAll('.custom-select-arrow').forEach(arrow => {
      arrow.classList.remove('rotate-180');
    });
  });

  setScreenSize(getScreenSize());
  updateInstructionCount();
  loadSettings();
  renderOutputs();
});
