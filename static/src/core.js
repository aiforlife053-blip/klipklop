const $ = (id) => document.getElementById(id);

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
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }
function cssEscape(value) { return window.CSS && CSS.escape ? CSS.escape(value) : String(value).replace(/"/g, '\\"'); }
function youtubeUrl(videoId) { return videoId ? `https://youtu.be/${encodeURIComponent(videoId)}` : ''; }

function logActivity(action, detail = '') {
  api('/api/activity', { method: 'POST', body: JSON.stringify({ action, detail }) }).catch(() => {});
}
