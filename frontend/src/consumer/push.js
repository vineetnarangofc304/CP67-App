/**
 * Push notification helper.
 * - Registers the service worker.
 * - Requests Notification permission with a friendly UX.
 * - Subscribes to Web Push when a VAPID key is configured
 *   (process.env.REACT_APP_VAPID_PUBLIC_KEY).
 *   Without a VAPID key, we still register the SW + ask permission
 *   so local `Notification` toasts work; backend pushes are no-op until
 *   the VAPID key is added.
 */

const API_BASE = process.env.REACT_APP_BACKEND_URL + '/api/consumer';
const VAPID_PUBLIC_KEY = process.env.REACT_APP_VAPID_PUBLIC_KEY || '';
const PROMPT_FLAG = 'cp67_notif_prompt_v1';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

export async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
    return reg;
  } catch (e) {
    console.warn('SW registration failed', e);
    return null;
  }
}

export function shouldPromptForNotifications() {
  if (!('Notification' in window)) return false;
  if (Notification.permission !== 'default') return false;
  // Only prompt once per device install
  if (localStorage.getItem(PROMPT_FLAG)) return false;
  return true;
}

export function markPromptShown() {
  try { localStorage.setItem(PROMPT_FLAG, '1'); } catch { /* storage may be blocked */ }
}

export async function requestNotificationPermission() {
  if (!('Notification' in window)) return 'unsupported';
  try {
    const res = await Notification.requestPermission();
    markPromptShown();
    return res; // 'granted' | 'denied' | 'default'
  } catch {
    return 'denied';
  }
}

export async function subscribeUserToPush(token) {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return null;
  if (Notification.permission !== 'granted') return null;
  const reg = await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    if (!VAPID_PUBLIC_KEY) {
      // No VAPID key yet — record opt-in so backend knows; actual push
      // delivery will start working once VAPID is configured.
      console.info('No VAPID key configured; saving opt-in only.');
      try {
        await fetch(`${API_BASE}/push/subscribe`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            endpoint: `local-optin:${Date.now()}`,
            keys: {},
            user_agent: navigator.userAgent,
            platform: window.matchMedia('(display-mode: standalone)').matches ? 'pwa' : 'web'
          })
        });
      } catch { /* opt-in record best effort */ }
      return { optInOnly: true };
    }
    try {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY)
      });
    } catch (e) {
      console.warn('Push subscribe failed', e);
      return null;
    }
  }
  // POST subscription to backend
  try {
    const payload = sub.toJSON ? sub.toJSON() : sub;
    await fetch(`${API_BASE}/push/subscribe`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: payload.endpoint,
        keys: payload.keys || {},
        user_agent: navigator.userAgent,
        platform: window.matchMedia('(display-mode: standalone)').matches ? 'pwa' : 'web'
      })
    });
  } catch (e) {
    console.warn('Backend push subscribe upload failed', e);
  }
  return sub;
}
