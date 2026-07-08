let pollTimer = null;
let savedInstruction = '';
let pendingConfirm = null;
let smoothProgress = 0;
let smoothProgressTarget = 0;
let smoothProgressTimer = null;
let processingActive = false;
let completionNotified = false;
let latestProgress = 0;
let latestMessage = 'Menyiapkan AI...';
let currentSettings = {};

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
        optBtn.dataset.selected = isSelected ? 'true' : 'false';
        optBtn.className = `w-full px-3 py-2 rounded-lg text-left text-[13px] transition font-medium custom-select-option ` +
          (isSelected ? `custom-select-option-selected` : `custom-select-option-idle`);
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

    if (!btn || typeof btn.addEventListener !== 'function') return;

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

function showToast(message, type = 'error') {
  let container = $('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed top-6 right-6 z-[200] flex flex-col gap-2 pointer-events-none';
    document.body.appendChild(container);
  }
  const ok = type === 'success';
  const toast = document.createElement('div');
  toast.className = `pointer-events-auto ${ok ? 'bg-green-50 text-green-800 border-green-100' : 'bg-red-50 text-red-800 border-red-100'} border rounded-xl px-4 py-3 shadow-lg flex items-center gap-3 max-w-sm transition-all duration-300 transform translate-y-4 opacity-0`;
  toast.innerHTML = `<span class="text-[13px] font-semibold leading-normal">${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  requestAnimationFrame(() => { toast.className = toast.className.replace('translate-y-4 opacity-0', 'translate-y-0 opacity-100'); });
  setTimeout(() => {
    toast.className = toast.className.replace('translate-y-0 opacity-100', 'translate-y-4 opacity-0');
    setTimeout(() => { toast.remove(); if (container.children.length === 0) container.remove(); }, 300);
  }, 5000);
}

function showError(message) { showToast(message, 'error'); }
function showSuccess(message) { showToast(message, 'success'); }

async function loadSettings() {
  try { applySettings(await api('/api/settings'), false); } catch (error) { showError(error.message); }
}

function applySettings(data, keepApiKey) {
  currentSettings = data || {};
  setValue('base-url', data.base_url || 'https://generativelanguage.googleapis.com/v1beta/openai');
  if (!keepApiKey) setValue('api-key', '');
  const keyInput = $('api-key');
  if (keyInput) keyInput.placeholder = data.api_key_saved ? 'API key tersimpan' : 'Gemini API key';
  setValue('model', data.model || 'gemini-2.5-flash');
  setValue('subtitle-engine', 'local');
  setValue('local-whisper-model', 'small');
  setValue('caption-base-url', data.caption_base_url || 'https://api.openai.com/v1');
  setValue('caption-model', data.caption_model || 'whisper-1');
  setValue('caption-api-key', '');
  const captionKey = $('caption-api-key');
  if (captionKey) captionKey.placeholder = data.caption_key_saved ? 'Caption API key tersimpan' : 'Whisper/OpenAI API key';
  setValue('subtitle-language', data.subtitle_language || 'id');
  setValue('video-quality', data.video_quality || '720');
  setValue('video-quality-main', data.video_quality || '720');
  setChecked('landscape-blur', data.landscape_blur ?? true);
  setValue('subtitle-font', data.subtitle_style?.font || 'Plus Jakarta Sans');
  setValue('subtitle-size', data.subtitle_style?.size || 65);
  setValue('output-dir', data.output_dir || '');
  setChecked('watermark-enabled', !!data.watermark?.enabled);
  setValue('watermark-image', data.watermark?.image_path || '');
  setValue('watermark-opacity', Math.round((data.watermark?.opacity ?? 0.8) * 100));
  setValue('watermark-scale', Math.round((data.watermark?.scale ?? 0.15) * 100));
  setChecked('credit-enabled', data.credit_watermark?.enabled ?? true);
  setValue('credit-text', data.credit_watermark?.text || 'sc : {channel}');
  setValue('credit-color', data.credit_watermark?.color || '#ffffff');
  setValue('credit-opacity', Math.round((data.credit_watermark?.opacity ?? 0.55) * 100));
  setValue('credit-size', Math.round((data.credit_watermark?.size ?? 0.032) * 1000));
  setChecked('hook-enabled', data.hook_style?.enabled ?? true);
  setValue('hook-text-color', data.hook_style?.text_color || '#0033ff');
  setValue('hook-bg-color', data.hook_style?.background_color || '#ffffff');
  setValue('hook-font-size', Math.round((data.hook_style?.font_size ?? 0.054) * 1000));
  setValue('hook-radius', data.hook_style?.corner_radius ?? 28);
  setValue('hook-duration', data.hook_style?.duration ?? 5);
  setChecked('blur-enabled', data.blur_background?.enabled ?? true);
  setValue('blur-zoom', Math.round((data.blur_background?.zoom ?? 1.08) * 100));
  setValue('blur-strength', data.blur_background?.strength ?? 30);
  updateWatermarkLabels();
  setCookieStatus(data.cookies);
  toggleSubtitleEngineFields();
  updateCompactStatus('Idle');
}

function toggleSubtitleEngineFields() {
  const fields = $('api-whisper-fields');
  if (fields) fields.classList.toggle('hidden', getValue('subtitle-engine', 'local') === 'local');
}

function updateWatermarkLabels() {
  setText('watermark-opacity-label', `${getValue('watermark-opacity', '80')}%`);
  setText('watermark-scale-label', `${getValue('watermark-scale', '15')}%`);
  setText('credit-opacity-label', `${getValue('credit-opacity', '55')}%`);
  setText('credit-size-label', `${getValue('credit-size', '32')}`);
  const image = getValue('watermark-image');
  const name = image ? image.split(/[\\/]/).pop() : 'Belum ada gambar';
  setText('watermark-file-name', name);
}

async function uploadWatermarkFile(file) {
  if (!file) return;
  const content = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
  const result = await api('/api/watermark/upload', { method: 'POST', body: JSON.stringify({ name: file.name, content }) });
  if (result.status !== 'ok') throw new Error(result.message || 'Gagal upload watermark');
  setValue('watermark-image', result.path);
  updateWatermarkLabels();
  updateConfigPreview('watermark');
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
    showSuccess('Pengaturan berhasil disimpan');
  } catch (error) { showError(error.message); }
}

function settingsPayload(extra = {}) {
  return {
    base_url: getValue('base-url'),
    model: getValue('model'),
    subtitle_engine: 'local',
    local_whisper: {
      enabled: true,
      model: 'small',
      device: 'cpu',
      compute_type: 'int8',
    },
    caption_base_url: getValue('caption-base-url', 'https://api.openai.com/v1'),
    caption_api_key: getValue('caption-api-key'),
    caption_model: getValue('caption-model', 'whisper-1'),
    subtitle_language: 'id',
    video_quality: getValue('video-quality-main', getValue('video-quality', '720')),
    landscape_blur: getChecked('landscape-blur', true) && getChecked('blur-enabled', true),
    subtitle_style: {
      font: 'Plus Jakarta Sans',
      size: 58,
    },
    output_dir: getValue('output-dir'),
    watermark: {
      enabled: getChecked('watermark-enabled', false),
      image_path: getValue('watermark-image'),
      opacity: Number(getValue('watermark-opacity', '80')) / 100,
      scale: Number(getValue('watermark-scale', '15')) / 100,
      position_x: Number($('preview-target')?.dataset.x || 85) / 100,
      position_y: Number($('preview-target')?.dataset.y || 5) / 100,
    },
    credit_watermark: {
      enabled: getChecked('credit-enabled', true),
      text: getValue('credit-text', 'sc : {channel}'),
      color: getValue('credit-color', '#ffffff'),
      opacity: Number(getValue('credit-opacity', '55')) / 100,
      size: Number(getValue('credit-size', '32')) / 1000,
      position_x: Number($('preview-target')?.dataset.x || 6) / 100,
      position_y: Number($('preview-target')?.dataset.y || 23) / 100,
    },
    hook_style: {
      enabled: getChecked('hook-enabled', true),
      text_color: getValue('hook-text-color', '#0033ff'),
      background_color: getValue('hook-bg-color', '#ffffff'),
      font_size: Number(getValue('hook-font-size', '54')) / 1000,
      corner_radius: Number(getValue('hook-radius', '28')),
      duration: Number(getValue('hook-duration', '5')),
      position_x: Number($('preview-target')?.dataset.x || 50) / 100,
      position_y: Number($('preview-target')?.dataset.y || 20) / 100,
    },
    blur_background: {
      enabled: getChecked('blur-enabled', true),
      zoom: Number(getValue('blur-zoom', '108')) / 100,
      strength: Number(getValue('blur-strength', '30')),
    },
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

function getScreenSize() { return '9:16'; }
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

function startPayload() {
  return {
    url: getValue('youtube-url'),
    num_clips: 1,
    add_captions: true,
    enable_captions: true,
    add_hook: true,
    hook_mode: true,
    screen_size: '9:16',
    subtitle_language: 'id',
    landscape_blur: getChecked('landscape-blur', true) && getChecked('blur-enabled', true),
    source_credit: true,
    instruction: savedInstruction,
  };
}

async function startProcessing() {
  const button = $('process-button');
  if (button) button.disabled = true;
  updateProcessingUi(true);
  refreshLogPanel();
  clearInterval(pollTimer);
  smoothProgress = 0;
  setProgressTarget(0);
  processingActive = true;
  completionNotified = false;
  await renderOutputs();
  try {
    await saveSettings();
    const result = await api('/api/start', { method: 'POST', body: JSON.stringify(startPayload()) });
    if (result.status !== 'started') throw new Error(result.message || 'Gagal mulai');
    showSuccess('Generate dimulai');
    pollTimer = setInterval(pollStatus, 800);
    pollStatus();
  } catch (error) {
    processingActive = false;
    if (button) button.disabled = false;
    updateProcessingUi(false);
    showError(error.message);
    setText('status-text', 'Gagal memproses');
    await renderOutputs();
  }
}

async function pollStatus() {
  try {
    const data = await api('/api/status');
    const progressPct = Math.round((data.progress || 0) * 100);
    latestProgress = data.progress || 0;
    if (data.status === 'error') {
      processingActive = false;
      showError(data.error || data.message || 'Terjadi kesalahan');
      setText('status-text', 'Gagal');
      updateCompactStatus('Gagal');
    } else {
      const wasProcessing = processingActive;
      processingActive = ['started', 'processing', 'running', 'stopping'].includes(data.status);
      const rawMsg = data.error || data.message || data.status;
      const message = cleanStatusText(rawMsg);
      latestMessage = message;

      let displayMsg = message;
      if (processingActive) {
        displayMsg = `${message} (${progressPct}%)`;
      }
      setText('status-text', displayMsg);
      updateCompactStatus(message);

      if (processingActive) await renderOutputs();
      if (wasProcessing && !processingActive && data.status === 'idle') {
        clearInterval(pollTimer);
        $('process-button').disabled = false;
        updateProcessingUi(false);
        await renderOutputs();
      }
    }
    updateLogPanel(data);
    setProgressTarget(data.progress || 0);
    if (data.status === 'complete' || data.status === 'error') {
      if (data.status === 'complete' && !completionNotified) {
        completionNotified = true;
        showSuccess('Video selesai diproses');
      }
      processingActive = false;
      clearInterval(pollTimer);
      $('process-button').disabled = false;
      updateProcessingUi(false);
      await renderOutputs();
    }
  } catch (error) {
    processingActive = false;
    clearInterval(pollTimer);
    $('process-button').disabled = false;
    updateProcessingUi(false);
    showError(error.message);
    setText('status-text', 'Error koneksi');
    await renderOutputs();
  }
}

function updateProcessingUi(active) {
  const button = $('process-button');
  const stop = $('stop-button');
  if (button) {
    button.textContent = active ? 'Generating' : 'Proses Klip';
    button.disabled = !!active;
  }
  if (stop) stop.classList.toggle('hidden', !active);
}

async function stopProcessing() {
  const stop = $('stop-button');
  if (stop) stop.disabled = true;
  try {
    await api('/api/stop', { method: 'POST', body: '{}' });
    setText('status-text', 'Menghentikan...');
    await pollStatus();
  } catch (error) {
    showError(error.message);
  } finally {
    if (stop) stop.disabled = false;
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
  el.innerHTML = `Status: ${escapeHtml(message || 'Idle')}<br />Clip: ${escapeHtml(clip)} | Quality: ${escapeHtml(getValue('video-quality-main', '720'))}p | 9:16 ${getChecked('landscape-blur', true) ? '+ Blur' : '+ Crop'}`;
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
async function logout() {
  await fetch('/api/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  sessionStorage.setItem('klipklop_toast', 'Berhasil logout');
  location.href = '/login';
}

async function clearLogPanel() {
  const lines = $('log-lines');
  if (lines) lines.innerHTML = '<div class="text-gray-500">Belum ada log.</div>';
  setText('log-summary', 'cleared · 0%');
  try { await api('/api/logs/clear', { method: 'POST', body: '{}' }); showSuccess('Konsol dibersihkan'); } catch (error) { try { await api('/api/clear-logs', { method: 'POST', body: '{}' }); showSuccess('Konsol dibersihkan'); } catch (inner) {} }
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
  const savedClips = groups.flatMap((group) => {
    const saved = new Set(group.saved_clips || []);
    return (group.clips || []).filter((clip) => saved.has(clip.path)).map((clip) => ({ ...clip, group }));
  });
  if (historyPanel) historyPanel.innerHTML = renderHistoryBoard(savedClips);
  if (!homePanel) return;

  const pendingGroups = groups.map(withPendingClips).filter((group) => group.clips.length);
  if (processingActive) {
    homePanel.className = pendingGroups.length ? 'space-y-5 w-full' : 'flex h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full';
    homePanel.innerHTML = pendingGroups.length ? `${renderInlineProcessingLoader(latestProgress, latestMessage)}${pendingGroups.map(renderExportSession).join('')}` : renderProcessingLoader(latestProgress, latestMessage);
    return;
  }

  if (pendingGroups.length) {
    homePanel.className = 'space-y-5 w-full';
    homePanel.innerHTML = pendingGroups.map(renderExportSession).join('');
  } else {
    homePanel.className = 'flex h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full';
    homePanel.innerHTML = renderEmptyHome();
  }
}

function renderInlineProcessingLoader(progress = 0, message = 'Menyiapkan AI...') {
  return `<section class="mb-4 rounded-2xl border border-[#3a4558] bg-[#111827] p-4 text-center">${renderProcessingLoader(progress, message)}</section>`;
}

function renderEmptyHome() {
  return `<div class="w-14 h-14 bg-[#fff7ed] text-[#ea580c] rounded-2xl flex items-center justify-center mb-5 mx-auto">
    <svg class="w-6 h-6 text-[#ea580c]" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
    </svg>
  </div>
  <h3 class="text-[19px] font-semibold text-black mb-2.5 tracking-tight">Siap Membuat Klip Viral Terbaik?</h3>
  <p class="text-[13px] text-gray-500 leading-relaxed max-w-md mx-auto">
    Tempel link YouTube di panel kiri. AI akan memilih 1 momen dengan potensi viral tertinggi.
  </p>`;
}

function withPendingClips(group) { const saved = new Set(group.saved_clips || []); return { ...group, clips: (group.clips || []).filter((clip) => !saved.has(clip.path)) }; }
function metaLine(group, count) { return `${count} klip tersedia | ${group.video_quality || '720'}p | 9:16 ${group.landscape_blur ? '+ Blur' : '+ Crop'} | ${formatTime(group.timestamp)}`; }
function clipDuration(clip) { return clip.duration_seconds ? `Durasi: ${Math.round(clip.duration_seconds)}s` : 'Durasi: -'; }
function uploadDescription(clip, group) { const source = clip.channel_name || group.channel_name || ''; return `${clip.description || group.caption || ''}${source ? `\n\nsc: ${source}` : ''}`.trim(); }

function uploadStates() { try { return JSON.parse(localStorage.getItem('youtubeUploadStates') || '{}'); } catch (_) { return {}; } }
function saveUploadStates(states) { localStorage.setItem('youtubeUploadStates', JSON.stringify(states)); }
function setUploadState(path, patch) { const states = uploadStates(); states[path] = { ...(states[path] || {}), ...patch }; saveUploadStates(states); renderOutputs(); }

async function syncYoutubeDeleted() {
  const states = uploadStates();
  const entries = Object.entries(states).filter(([, state]) => state.status === 'success' && state.video_id);
  if (!entries.length) return;
  try {
    const data = await api('/api/social/youtube/check', { method: 'POST', body: JSON.stringify({ video_ids: entries.map(([, state]) => state.video_id) }) });
    const existing = new Set(data.existing || []);
    let changed = false;
    for (const [path, state] of entries) {
      if (!existing.has(state.video_id)) {
        states[path] = { ...state, status: 'deleted' };
        changed = true;
      }
    }
    if (changed) { saveUploadStates(states); renderOutputs(); }
  } catch (error) {
    logActivity('youtube_check_failed', error.message);
  }
}

function renderHistoryBoard(clips) {
  const warning = '<div class="gallery-warning-badge">Galeri maksimal 10 video tersimpan.</div>';
  return warning + (clips.length ? `<div class="flex flex-wrap gap-3">${clips.map(renderHistoryClip).join('')}</div>` : '<p class="text-[13px] text-gray-500">Galeri kosong. Simpan klip dari Beranda dulu.</p>');
}

function renderHistoryClip(file) {
  const href = `/api/download?path=${encodeURIComponent(file.path)}`;
  const state = uploadStates()[file.path] || {};
  const url = state.url || youtubeUrl(state.video_id);
  const label = state.status === 'uploading' ? 'Mengunggah...' : state.status === 'failed' ? 'Coba lagi' : state.status === 'success' ? 'Buka' : 'Unggah';
  const deleteAttr = `data-delete-output="${escapeAttr(file.path)}" data-delete-kind="clip"`;
  const status = state.status === 'failed' ? `<p class="text-[10px] text-red-400 mt-1">${escapeHtml(state.error || 'Upload gagal')}</p>` : url ? `<a class="text-[10px] text-green-400 mt-1 truncate" href="${escapeAttr(url)}" target="_blank">${escapeHtml(url)}</a>` : '';
  return `<article class="bg-white border border-gray-200 rounded-xl p-2 flex flex-col w-full max-w-[210px] overflow-hidden">
    <button type="button" class="relative bg-gray-100 rounded-lg aspect-[4/3] overflow-hidden mb-2 cursor-zoom-in" data-video-open="${escapeAttr(href)}" data-title="${escapeAttr(file.title || file.name)}" data-description="${escapeAttr(uploadDescription(file, file.group || {}))}" data-duration="${escapeAttr(clipDuration(file))}" data-youtube-upload="${escapeAttr(file.path)}" data-delete-output="${escapeAttr(file.path)}" data-delete-kind="clip">
      <video class="w-full h-full object-cover pointer-events-none" src="${href}" muted preload="metadata"></video>
    </button>
    <h3 class="font-semibold text-[12px] leading-snug text-gray-950 mb-1 whitespace-normal break-words">${escapeHtml(file.title || file.name)}</h3>
    <p class="text-[10px] text-gray-400 mb-2">${clipDuration(file)}</p>
    ${status}
    <div class="grid grid-cols-3 gap-1.5 mt-auto pt-2">
      <a class="flex items-center justify-center rounded-lg bg-[#ea580c] text-white py-1.5 text-[10px] font-semibold hover:bg-[#c2410c] transition" href="${href}" data-download-output="${escapeAttr(file.path)}">Download</a>
      <button class="rounded-lg bg-white border border-gray-200 py-1.5 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-youtube-upload="${escapeAttr(file.path)}" data-youtube-url="${escapeAttr(url)}" data-title="${escapeAttr(file.title || file.name)}" data-description="${escapeAttr(uploadDescription(file, file.group || {}))}">${label}</button>
      <button class="rounded-lg bg-white border border-gray-200 py-1.5 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" ${deleteAttr}>Hapus</button>
    </div>
  </article>`;
}

function renderSessionRow(group) {
  const saved = new Set(group.saved_clips || []);
  const allClips = group.clips && group.clips.length ? group.clips : group.files || [];
  const clips = saved.size ? allClips.filter((clip) => saved.has(clip.path)) : allClips;
  return `<article class="border border-gray-200 rounded-2xl p-4 mb-3"><button class="text-left w-full min-w-0" style="background: transparent; background-color: transparent;" type="button" data-session-toggle="${escapeAttr(group.path)}"><h3 class="font-semibold text-[16px] text-white truncate">${escapeHtml(group.title)}</h3><p class="text-[12px] text-gray-400">${clips.length} klip tersimpan | ${escapeHtml(group.video_quality || '720')}p | ${formatTime(group.timestamp)}</p></button><div class="hidden mt-4 flex flex-wrap gap-4 justify-center" data-session-files="${escapeAttr(group.path)}">${clips.map(renderFileLink).join('')}</div></article>`;
}

function renderFileLink(file) {
  const href = `/api/download?path=${encodeURIComponent(file.path)}`;
  return `<article class="bg-white border border-gray-200 rounded-xl p-3 flex flex-col w-[260px] shrink-0 overflow-hidden">
    <button type="button" class="relative bg-gray-100 rounded-lg aspect-[4/3] overflow-hidden mb-2 cursor-zoom-in" data-video-open="${escapeAttr(href)}" data-title="${escapeAttr(file.title || file.name)}" data-description="${escapeAttr(uploadDescription(file, file.group || {}))}" data-duration="${escapeAttr(clipDuration(file))}" data-youtube-upload="${escapeAttr(file.path)}" data-delete-output="${escapeAttr(file.path)}" data-delete-kind="clip">
      <video class="w-full h-full object-cover pointer-events-none" src="${href}" muted preload="metadata"></video>
    </button>
    <div class="flex flex-col flex-1 min-h-0">
      <h3 class="font-semibold text-[13px] leading-snug text-gray-950 mb-1 whitespace-normal break-words">${escapeHtml(file.title || file.name)}</h3>
      <p class="text-[11px] text-gray-400 mb-3 mt-auto">${clipDuration(file)}</p>
      <div class="grid grid-cols-3 gap-1.5">
        <a class="flex items-center justify-center rounded-lg bg-[#ea580c] hover:bg-[#c2410c] text-white py-2 text-[10px] font-semibold transition text-center" href="${href}" data-download-output="${escapeAttr(file.path)}">Unduh</a>
        <button class="rounded-lg bg-white border border-gray-200 py-2 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-youtube-upload="${escapeAttr(file.path)}" data-title="${escapeAttr(file.title || file.name)}" data-description="${escapeAttr(uploadDescription(file, file.group || {}))}">Upload YT</button>
        <button class="rounded-lg bg-white border border-gray-200 py-2 text-[10px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-delete-output="${escapeAttr(file.path)}" data-delete-kind="clip">Hapus</button>
      </div>
    </div>
  </article>`;
}

function renderExportSession(group) {
  const clips = group.clips || [];
  const status = $('compact-status')?.innerHTML || 'Status: Idle<br>Clip: - | Quality: 480p | 9:16';
  return `<section class="border-0 p-6 bg-transparent w-full max-w-full min-h-[calc(100vh-90px)] overflow-hidden flex flex-col"><div class="mb-8"><h2 class="text-[20px] font-semibold text-black mb-2 tracking-tight">Hasil Klip</h2><p class="text-[13px] text-gray-500 leading-relaxed mb-4 max-w-3xl">Klip yang sudah selesai akan muncul di sini satu per satu saat proses masih berjalan.</p><div class="gallery-warning-badge">Simpan klip ke Galeri dulu untuk mengaktifkan download. Hapus atau simpan semua klip sebelum generate baru.</div></div><div class="flex flex-wrap gap-4 justify-center">${clips.map((clip, index) => renderExportCard(group, clip, index)).join('')}</div><div class="mt-10 text-left w-full max-w-5xl mx-auto"><h3 class="font-semibold text-[16px] leading-snug text-gray-950 whitespace-normal break-words">${escapeHtml(group.title)}</h3><p class="text-[12px] text-gray-500 whitespace-normal break-words mt-2">${escapeHtml(metaLine(group, clips.length))}</p></div><div class="flex items-end justify-between gap-4 text-[13px] text-gray-500 mt-auto pt-10"><div>${status}</div><button class="border border-gray-200 px-4 py-2.5 rounded-xl text-[13px] font-semibold text-gray-700 hover:bg-gray-50 bg-white" type="button" data-show-json="true">JSON Payload</button></div></section>`;
}

function renderExportCard(group, clip, index = 0) {
  if (!clip || !clip.path) return '';
  const href = `/api/download?path=${encodeURIComponent(clip.path)}`;
  return `<article class="bg-white border border-gray-200 rounded-xl p-2 flex flex-col w-full max-w-[210px] overflow-hidden">
    <button type="button" class="relative bg-gray-100 rounded-lg aspect-[4/3] overflow-hidden mb-2 cursor-zoom-in" data-video-open="${escapeAttr(href)}" data-title="${escapeAttr(clip.title || `Klip ${index + 1}`)}" data-description="${escapeAttr(uploadDescription(clip, group))}" data-duration="${escapeAttr(clipDuration(clip))}" data-save-output="${escapeAttr(group.path)}" data-save-one="${escapeAttr(clip.path)}" data-youtube-upload="${escapeAttr(clip.path)}" data-save-session="${escapeAttr(group.path)}" data-delete-output="${escapeAttr(clip.path)}" data-delete-kind="clip">
      <video class="w-full h-full object-cover pointer-events-none" src="${href}" muted preload="metadata"></video>
    </button>
    <div class="flex flex-col flex-1 min-h-0">
      <h3 class="font-semibold text-[13px] leading-snug text-gray-950 mb-1 whitespace-normal break-words">${escapeHtml(clip.title || `Klip ${index + 1}`)}</h3>
      <p class="text-[12px] text-gray-500 mb-2 leading-relaxed whitespace-normal break-words overflow-hidden" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">${escapeHtml(clip.description || group.caption)}</p>
      <p class="text-[11px] text-gray-400 mb-3 mt-auto">${clipDuration(clip)}</p>
      <button class="rounded-lg border border-gray-200 bg-white py-2 text-[11px] font-semibold text-gray-900 hover:bg-gray-50 transition" type="button" data-video-open="${escapeAttr(href)}" data-title="${escapeAttr(clip.title || `Klip ${index + 1}`)}" data-description="${escapeAttr(uploadDescription(clip, group))}" data-duration="${escapeAttr(clipDuration(clip))}" data-save-output="${escapeAttr(group.path)}" data-save-one="${escapeAttr(clip.path)}" data-youtube-upload="${escapeAttr(clip.path)}" data-save-session="${escapeAttr(group.path)}" data-delete-output="${escapeAttr(clip.path)}" data-delete-kind="clip">Lihat detail</button>
    </div>
  </article>`;
}

async function uploadYoutube(button) {
  const path = button.dataset.youtubeUpload;
  if (button.dataset.youtubeUrl) { window.open(button.dataset.youtubeUrl, '_blank'); return; }
  if (!(await confirmDelete('Upload klip ini ke YouTube sebagai private?', 'Ya, Upload'))) return;
  setUploadState(path, { status: 'uploading', error: '', url: '' });
  try {
    if (button.dataset.saveSession) await api('/api/save', { method: 'POST', body: JSON.stringify({ path: button.dataset.saveSession, clips: [button.dataset.saveOne || path] }) });
    const data = await api('/api/social/youtube/upload', { method: 'POST', body: JSON.stringify({ path, title: button.dataset.title, description: button.dataset.description, privacy: 'private' }) });
    const url = data.url || youtubeUrl(data.video_id);
    setUploadState(path, { status: 'success', video_id: data.video_id, url, error: '' });
    logActivity('youtube_upload', data.video_id || path);
    showSuccess(`Upload sukses: ${url || data.video_id || path}`);
    if (url) window.open(url, '_blank');
  } catch (error) {
    setUploadState(path, { status: 'failed', error: error.message });
    showError(error.message);
  }
}

async function deleteYoutube(button) {
  const path = button.dataset.youtubeDelete;
  const videoId = button.dataset.videoId;
  if (!path || !videoId || !(await confirmDelete('Video YouTube dan klip lokal ini akan dihapus dari Galeri.', 'Ya, Hapus'))) return;
  try {
    await api('/api/social/youtube/delete', { method: 'POST', body: JSON.stringify({ video_id: videoId }) });
    setUploadState(path, { ...(uploadStates()[path] || {}), status: 'deleted' });
    logActivity('youtube_delete', videoId);
    showSuccess('Video YouTube berhasil dihapus');
    await renderOutputs();
  } catch (error) { showError(error.message); }
}

function confirmDelete(message, okText = 'Lanjut') {
  const modal = $('confirm-modal');
  setText('confirm-message', message);
  setText('confirm-ok', okText);
  if (modal) modal.classList.remove('hidden');
  return new Promise((resolve) => { pendingConfirm = resolve; });
}

async function deleteOutput(path, kind = 'clip') {
  if (!path || !(await confirmDelete(kind === 'session' ? 'Session dan semua klip di dalamnya akan dihapus permanen.' : 'Klip ini akan dihapus permanen.', 'Ya, Hapus'))) return;
  try { await api('/api/delete', { method: 'POST', body: JSON.stringify({ path }) }); logActivity('local_delete', path.split(/[\\/]/).pop()); showSuccess('Klip berhasil dihapus'); await renderOutputs(); } catch (error) { showError(error.message); }
}

async function saveOutput(path, oneClip) {
  if (!path) return;
  const inputs = [...document.querySelectorAll(`.clip-select[data-session-path="${cssEscape(path)}"]`)];
  const selected = oneClip ? [oneClip] : inputs.filter((input) => input.checked).map((input) => input.dataset.clipPath);
  if (!selected.length) { showError('Pilih minimal 1 klip'); return; }
  try { await api('/api/save', { method: 'POST', body: JSON.stringify({ path, clips: selected }) }); logActivity('gallery_save', `${selected.length} klip`); showSuccess('Tersimpan ke Galeri. Download tersedia di Galeri.'); await renderOutputs(); } catch (error) { showError(error.message); }
}

function toggleSession(path) { document.querySelectorAll('[data-session-files]').forEach((el) => el.classList.toggle('hidden', el.dataset.sessionFiles !== path || !el.classList.contains('hidden'))); }
function formatTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? (value || '') : date.toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }); }
function showPage(name) {
  if (!['home', 'history', 'console', 'settings'].includes(name)) name = 'home';
  if (location.hash !== `#${name}`) window.history.replaceState(null, '', `#${name}`);
  const home = $('page-home'); const history = $('page-history'); const consolePage = $('page-console'); const settings = $('page-settings');
  if (!home || !history || !consolePage || !settings) return;
  home.classList.toggle('hidden', name !== 'home');
  history.classList.toggle('hidden', name !== 'history');
  consolePage.classList.toggle('hidden', name !== 'console');
  settings.classList.toggle('hidden', name !== 'settings');
  setNavActive('nav-home', name === 'home');
  setNavActive('nav-history', name === 'history');
  setNavActive('nav-console', name === 'console');
  setNavActive('nav-settings', name === 'settings');

  if (name === 'home') { pollStatus(); renderOutputs(); }
  if (name === 'history') { renderOutputs(); syncYoutubeDeleted(); }
  if (name === 'console') refreshLogPanel();
  if (name === 'settings') { loadSettings(); loadSocialStatus(); }
}

function setNavActive(id, active) {
  const el = $(id);
  if (!el) return;
  el.className = active
    ? 'px-3 py-2 rounded-xl bg-[#fff0e6] text-[#ea580c] transition'
    : 'px-3 py-2 rounded-xl text-gray-500 hover:bg-gray-50 hover:text-gray-900 transition';
}

function openVideoModal(src, trigger) {
  const modal = $('video-modal');
  const player = $('video-modal-player');
  if (!modal || !player) return;
  player.src = src;
  setText('video-modal-title', trigger?.dataset.title || 'Klip');
  setText('video-modal-description', trigger?.dataset.description || '-');
  setText('video-modal-duration', trigger?.dataset.duration || 'Durasi: -');
  copyDataset('video-modal-save', trigger, ['saveOutput', 'saveOne']);
  copyDataset('video-modal-upload', trigger, ['youtubeUpload', 'saveSession', 'saveOne', 'title', 'description']);
  copyDataset('video-modal-delete', trigger, ['deleteOutput', 'deleteKind']);
  modal.classList.remove('hidden');
  player.play().catch(() => {});
}

function copyDataset(targetId, source, keys) {
  const target = $(targetId);
  if (!target) return;
  Object.keys(target.dataset).forEach((key) => delete target.dataset[key]);
  keys.forEach((key) => { if (source?.dataset[key]) target.dataset[key] = source.dataset[key]; });
  target.classList.toggle('hidden', !source || !keys.some((key) => source.dataset[key]));
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

function openConfigModal(name) {
  const titles = { watermark: 'Configure Watermark', credit: 'Configure SC', hook: 'Configure Hook', blur: 'Configure BG Blur' };
  const positions = {
    watermark: currentSettings.watermark,
    credit: currentSettings.credit_watermark,
    hook: currentSettings.hook_style,
  };
  const target = $('preview-target');
  if (target) {
    target.dataset.x = String(Math.round((positions[name]?.position_x ?? 0.32) * 100));
    target.dataset.y = String(Math.round((positions[name]?.position_y ?? 0.17) * 100));
  }
  setText('config-title', titles[name] || 'Configure');
  document.querySelectorAll('[data-config-panel]').forEach((panel) => panel.classList.toggle('hidden', panel.dataset.configPanel !== name));
  $('config-modal')?.classList.remove('hidden');
  updateConfigPreview(name);
}

function updateConfigPreview(name = document.querySelector('[data-config-panel]:not(.hidden)')?.dataset.configPanel || 'credit') {
  const target = $('preview-target');
  if (!target) return;
  target.style.left = `${Number(target.dataset.x || 32)}%`;
  target.style.top = `${Number(target.dataset.y || 17)}%`;
  target.style.opacity = '1';
  target.style.background = 'transparent';
  target.style.backgroundImage = '';
  target.style.backgroundSize = '';
  target.style.backgroundPosition = '';
  target.style.width = '';
  target.style.height = '';
  target.style.display = '';
  target.style.borderRadius = '0';
  target.style.padding = '0';
  target.textContent = '9:16 Video';
  if (name === 'watermark') { 
    const image = getValue('watermark-image'); 
    target.textContent = image ? '' : 'Watermark'; 
    target.style.color = '#ffffff'; 
    target.style.display = 'grid'; 
    target.style.placeItems = 'center'; 
    target.style.background = '#ffffff55'; 
    target.style.backgroundImage = image ? `url("${image.replace(/\\/g, '/')}")` : ''; 
    target.style.backgroundSize = 'contain'; 
    target.style.backgroundPosition = 'center'; 
    target.style.backgroundRepeat = 'no-repeat'; 
    const scale = Number(getValue('watermark-scale', '15'));
    target.style.width = `${scale * 2}px`; 
    target.style.height = `${scale * 2}px`; 
    target.style.opacity = String(Number(getValue('watermark-opacity', '80')) / 100); 
    target.style.fontSize = `${Math.max(6, scale * 0.4)}px`;
    target.style.overflow = 'hidden';
  }
  if (name === 'credit') { target.textContent = getValue('credit-text', 'sc : {channel}'); target.style.color = getValue('credit-color', '#ffffff'); target.style.opacity = String(Number(getValue('credit-opacity', '55')) / 100); target.style.fontSize = `${Number(getValue('credit-size', '32')) / 2}px`; }
  if (name === 'hook') { target.textContent = getValue('hook-sample', 'HOOK'); target.style.color = getValue('hook-text-color', '#0033ff'); target.style.background = getValue('hook-bg-color', '#ffffff'); target.style.borderRadius = `${getValue('hook-radius', '28')}px`; target.style.fontSize = `${Number(getValue('hook-font-size', '54')) / 2}px`; target.style.padding = '8px 12px'; }
  if (name === 'blur') { target.textContent = `${getValue('blur-zoom', '108')}% zoom / blur ${getValue('blur-strength', '30')}`; target.style.fontSize = '13px'; }
}

function enablePreviewDrag() {
  const preview = $('config-preview');
  const target = $('preview-target');
  if (!preview || !target) return;
  target.addEventListener('pointerdown', (event) => {
    const targetRect = target.getBoundingClientRect();
    const offsetX = event.clientX - targetRect.left;
    const offsetY = event.clientY - targetRect.top;
    target.setPointerCapture(event.pointerId);
    const move = (moveEvent) => {
      const rect = preview.getBoundingClientRect();
      const width = (target.offsetWidth / rect.width) * 100;
      const height = (target.offsetHeight / rect.height) * 100;
      target.dataset.x = String(Math.max(0, Math.min(100 - width, ((moveEvent.clientX - offsetX - rect.left) / rect.width) * 100)));
      target.dataset.y = String(Math.max(0, Math.min(100 - height, ((moveEvent.clientY - offsetY - rect.top) / rect.height) * 100)));
      updateConfigPreview();
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', () => target.removeEventListener('pointermove', move), { once: true });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const pendingToast = sessionStorage.getItem('klipklop_toast');
  if (pendingToast) {
    sessionStorage.removeItem('klipklop_toast');
    showSuccess(pendingToast);
  }
  const save = $('save-settings'); const showJson = $('show-json'); const stop = $('stop-button'); const jsonClose = $('json-close'); const videoClose = $('video-modal-close'); const clearKey = $('clear-api-key'); const start = $('process-button'); const profile = $('profile-button'); const logoutButton = $('logout-button'); const logClear = $('log-clear'); const instruction = $('instruction'); const instructionSave = $('instruction-save'); const instructionCancel = $('instruction-cancel'); const qualityMain = $('video-quality-main'); const qualitySettings = $('video-quality'); const blur = $('landscape-blur');
  if (save) save.addEventListener('click', saveSettings);
  $('config-save')?.addEventListener('click', saveSettings);
  $('config-close')?.addEventListener('click', () => $('config-modal')?.classList.add('hidden'));
  if (showJson) showJson.addEventListener('click', showPayloadJson);
  if (stop) stop.addEventListener('click', stopProcessing);
  if (jsonClose) jsonClose.addEventListener('click', () => $('json-modal')?.classList.add('hidden'));
  if (videoClose) videoClose.addEventListener('click', closeVideoModal);
  if (clearKey) clearKey.addEventListener('click', clearApiKey);
  if (start) start.addEventListener('click', startProcessing);
  if (profile) profile.addEventListener('click', toggleProfileMenu);
  if (logoutButton) logoutButton.addEventListener('click', logout);
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
  ['instruction-modal', 'settings-modal', 'config-modal', 'json-modal', 'confirm-modal'].forEach((id) => {
    const modal = $(id);
    if (modal) modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(id); });
  });
  $('video-modal')?.addEventListener('click', (event) => { if (event.target === $('video-modal')) closeVideoModal(); });
  document.addEventListener('click', (event) => {
    const configButton = event.target.closest('[data-config-open]');
    const videoButton = event.target.closest('[data-video-open]');
    const deleteButton = event.target.closest('[data-delete-output]');
    const saveButton = event.target.closest('[data-save-output]');
    const youtubeButton = event.target.closest('[data-youtube-upload]');
    const youtubeDeleteButton = event.target.closest('[data-youtube-delete]');
    const sessionButton = event.target.closest('[data-session-toggle]');
    const downloadLink = event.target.closest('[data-download-output]');
    const jsonButton = event.target.closest('[data-show-json]');
    if (configButton) { openConfigModal(configButton.dataset.configOpen); return; }
    if (jsonButton) { showPayloadJson(); return; }
    if (videoButton) { openVideoModal(videoButton.dataset.videoOpen, videoButton); return; }
    if (deleteButton) deleteOutput(deleteButton.dataset.deleteOutput, deleteButton.dataset.deleteKind);
    if (saveButton) saveOutput(saveButton.dataset.saveOutput, saveButton.dataset.saveOne);
    if (youtubeButton) uploadYoutube(youtubeButton);
    if (youtubeDeleteButton) deleteYoutube(youtubeDeleteButton);
    if (downloadLink) { logActivity('download_click', downloadLink.dataset.downloadOutput); showSuccess('Download dimulai'); }
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
  enablePreviewDrag();
  document.querySelectorAll('#config-modal input').forEach((input) => input.addEventListener('input', () => { updateWatermarkLabels(); updateConfigPreview(); }));
  $('watermark-file-button')?.addEventListener('click', () => $('watermark-file')?.click());
  $('watermark-file')?.addEventListener('change', async (event) => { try { await uploadWatermarkFile(event.target.files?.[0]); } catch (error) { showError(error.message); } });

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
  showPage((location.hash || '#home').slice(1));
  setInterval(() => { if (location.hash === '#history') syncYoutubeDeleted(); }, 30000);
});

async function loadSocialStatus() {
  const badge = $('yt-status-badge');
  const info = $('yt-info');
  const connectBtn = $('yt-connect-btn');
  const disconnectBtn = $('yt-disconnect-btn');
  if (!badge) return;

  try {
    const res = await fetch('/api/social/status');
    const data = await res.json();
    if (data.connected) {
      badge.textContent = 'Connected';
      badge.className = 'rounded-full border border-green-300 bg-green-50 px-3 py-1 text-[11px] font-semibold text-green-700';
      info.classList.remove('hidden');
      connectBtn.classList.add('hidden');
      disconnectBtn.classList.remove('hidden');
    } else {
      badge.textContent = 'Belum connect';
      badge.className = 'rounded-full border border-gray-200 px-3 py-1 text-[11px] font-semibold text-gray-500';
      info.classList.add('hidden');
      connectBtn.classList.remove('hidden');
      disconnectBtn.classList.add('hidden');
    }
  } catch (_) {}

  disconnectBtn.onclick = async () => {
    if (!(await confirmDelete('Disconnect YouTube? Token lokal akan dihapus.', 'Disconnect'))) return;
    await fetch('/api/social/youtube/disconnect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    showSuccess('YouTube berhasil disconnect');
    loadSocialStatus();
  };

  connectBtn.onclick = async () => {
    connectBtn.disabled = true;
    connectBtn.textContent = 'Membuka Google Login...';

    try {
      // Start OAuth flow
      const res = await fetch('/api/social/youtube/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
      });
      const data = await res.json();

      if (data.status === 'error') throw new Error(data.message || 'Gagal start OAuth');

      if (data.status === 'waiting' && data.auth_url) {
        // Open auth URL in new tab
        window.open(data.auth_url, '_blank');

        // Poll for completion
        connectBtn.textContent = 'Menunggu authorization...';
        let attempts = 0;
        const maxAttempts = 60; // 2 minutes max

        const pollInterval = setInterval(async () => {
          attempts++;
          try {
            const statusRes = await fetch('/api/social/youtube/oauth-status', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const statusData = await statusRes.json();
            if (!statusRes.ok) throw new Error(statusData.message || `HTTP ${statusRes.status}`);

            if (statusData.status === 'connected') {
              clearInterval(pollInterval);
              connectBtn.textContent = 'Connected!';
              showSuccess('YouTube berhasil terhubung');
              setTimeout(() => {
                loadSocialStatus();
                connectBtn.disabled = false;
                connectBtn.textContent = 'Connect YouTube';
              }, 1500);
            } else if (statusData.status === 'error') {
              clearInterval(pollInterval);
              throw new Error(statusData.error || 'OAuth failed');
            } else if (attempts >= maxAttempts) {
              clearInterval(pollInterval);
              throw new Error('Timeout: OAuth tidak selesai dalam 2 menit');
            }
          } catch (err) {
            clearInterval(pollInterval);
            showError(err.message);
            connectBtn.disabled = false;
            connectBtn.textContent = 'Connect YouTube';
          }
        }, 2000);
      } else if (data.status === 'ok') {
        // Already connected
        loadSocialStatus();
      }
    } catch (error) {
      showError(error.message || 'Gagal menyambungkan YouTube');
    } finally {
      // Reset button if not in polling state
      if (connectBtn.textContent === 'Membuka Google Login...') {
        connectBtn.disabled = false;
        connectBtn.textContent = 'Connect YouTube';
      }
    }
  };
}
