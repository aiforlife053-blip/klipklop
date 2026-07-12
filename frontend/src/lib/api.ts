export async function api(path: string, options: RequestInit = {}) {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options
  });
  
  const text = await res.text();
  const data = text ? (() => { try { return JSON.parse(text); } catch { return { message: text }; } })() : {};
  if (!res.ok) {
    if (res.status === 401 && window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new Error(data.message || `HTTP ${res.status}`);
  }
  return data;
}

export function logActivity(action: string, detail: string = '') {
  api('/api/activity', { 
    method: 'POST', 
    body: JSON.stringify({ action, detail }) 
  }).catch(() => {});
}

export function youtubeUrl(videoId?: string) {
  return videoId ? `https://youtu.be/${encodeURIComponent(videoId)}` : '';
}
