type ApiErrorBody = { message?: string };

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const text = await res.text();
  const data: unknown = text ? (() => { try { return JSON.parse(text); } catch { return { message: text }; } })() : {};
  if (!res.ok) {
    if (res.status === 401 && window.location.pathname !== '/login') window.location.href = '/login';
    throw new Error((data as ApiErrorBody).message || `HTTP ${res.status}`);
  }
  return data as T;
}

export function apiGet<T>(path: string, options: Omit<RequestInit, 'method' | 'body'> = {}): Promise<T> {
  return api<T>(path, { ...options, method: 'GET' });
}

export function apiPost<T, B = Record<string, unknown>>(path: string, body: B, options: Omit<RequestInit, 'method' | 'body'> = {}): Promise<T> {
  return api<T>(path, { ...options, method: 'POST', body: JSON.stringify(body) });
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
