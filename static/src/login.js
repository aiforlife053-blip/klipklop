let mode = 'login';
const $ = (id) => document.getElementById(id);
const toast = (message) => {
  let el = document.getElementById('toast-container');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast-container';
    el.className = 'fixed top-6 right-6 z-[200] flex flex-col gap-2 pointer-events-none';
    document.body.appendChild(el);
  }
  const item = document.createElement('div');
  item.className = 'pointer-events-auto rounded-xl border border-green-400/20 bg-green-500/15 px-4 py-3 text-sm font-semibold text-green-100 shadow-lg';
  item.textContent = message;
  el.appendChild(item);
  setTimeout(() => item.remove(), 4000);
};
const pendingToast = sessionStorage.getItem('klipklop_toast');
if (pendingToast) {
  sessionStorage.removeItem('klipklop_toast');
  toast(pendingToast);
}
const setMode = (next) => {
  mode = next;
  $('title').textContent = mode === 'login' ? 'Masuk' : 'Daftar';
  $('subtitle').textContent = mode === 'login' ? 'Lanjutkan ke dashboard KlipKlop.' : 'Buat akun baru KlipKlop.';
  $('submit').textContent = mode === 'login' ? 'Masuk' : 'Daftar';
  $('tab-login').className = mode === 'login' ? 'auth-tab-active rounded-xl px-3 py-2.5 transition' : 'auth-tab-inactive rounded-xl px-3 py-2.5 transition';
  $('tab-signup').className = mode === 'signup' ? 'auth-tab-active rounded-xl px-3 py-2.5 transition' : 'auth-tab-inactive rounded-xl px-3 py-2.5 transition';
  $('error').textContent = '';
};
$('tab-login').onclick = () => setMode('login');
$('tab-signup').onclick = () => setMode('signup');
$('form').onsubmit = async (event) => {
  event.preventDefault();
  $('submit').disabled = true;
  $('error').textContent = '';
  try {
    const res = await fetch(mode === 'login' ? '/api/login' : '/api/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: $('email').value, password: $('password').value })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || 'Gagal');
    sessionStorage.setItem('klipklop_toast', mode === 'login' ? 'Berhasil login' : 'Berhasil daftar');
    location.href = '/';
  } catch (error) {
    $('error').textContent = error.message;
  } finally {
    $('submit').disabled = false;
  }
};
