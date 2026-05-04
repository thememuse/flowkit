/**
 * Content script — bridge between background.js and injected.js
 * Injects injected.js into MAIN world to access window.grecaptcha
 */
(function () {
  const s = document.createElement('script');
  s.src = chrome.runtime.getURL('injected.js');
  s.onload = () => s.remove();
  (document.head || document.documentElement).appendChild(s);
})();

chrome.runtime.onMessage.addListener((msg, _, reply) => {
  if (msg.type === 'GET_FLOW_API') {
    const requestId = msg.requestId || `flow-api-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const method = String(msg.method || 'GET').toUpperCase();
    const handler = (e) => {
      if (e.detail?.requestId !== requestId) return;
      window.removeEventListener('FLOW_API_RESULT', handler);
      clearTimeout(timer);
      reply({
        status: Number(e.detail?.status) || 0,
        text: typeof e.detail?.text === 'string' ? e.detail.text : '',
        error: e.detail?.error || null,
      });
    };

    const timer = setTimeout(() => {
      window.removeEventListener('FLOW_API_RESULT', handler);
      reply({ error: 'FLOW_API_TIMEOUT' });
    }, 35000);

    window.addEventListener('FLOW_API_RESULT', handler);
    window.dispatchEvent(new CustomEvent('FLOW_API_REQUEST', {
      detail: {
        requestId,
        url: msg.url,
        method,
        headers: msg.headers || {},
        body: msg.body ?? null,
      },
    }));

    return true;
  }

  if (msg.type !== 'GET_CAPTCHA') return;

  const { requestId, pageAction } = msg;

  const handler = (e) => {
    if (e.detail?.requestId === requestId) {
      window.removeEventListener('CAPTCHA_RESULT', handler);
      clearTimeout(timer);
      reply({ token: e.detail.token, error: e.detail.error });
    }
  };

  const timer = setTimeout(() => {
    window.removeEventListener('CAPTCHA_RESULT', handler);
    reply({ error: 'CONTENT_TIMEOUT' });
  }, 25000);

  window.addEventListener('CAPTCHA_RESULT', handler);

  window.dispatchEvent(new CustomEvent('GET_CAPTCHA', {
    detail: { requestId, pageAction },
  }));

  return true; // keep channel open for async reply
});

// ─── TRPC Media URL Monitor ─────────────────────────────────
// Forward intercepted TRPC responses with media URLs to background.js
window.addEventListener('TRPC_MEDIA_URLS', (e) => {
  const { url, body } = e.detail || {};
  if (!body) return;
  chrome.runtime.sendMessage({
    type: 'TRPC_MEDIA_URLS',
    trpcUrl: url,
    body,
  }).catch(() => {});
});

window.addEventListener('FLOW_AUTH_TOKEN', (e) => {
  const token = e.detail?.token;
  if (!token) return;
  chrome.runtime.sendMessage({
    type: 'FLOW_AUTH_TOKEN',
    token,
  }).catch(() => {});
});

function sendFlowHeartbeat() {
  chrome.runtime.sendMessage({
    type: 'FLOW_TAB_HEARTBEAT',
    url: window.location.href,
  }).catch(() => {});
}

sendFlowHeartbeat();
window.addEventListener('focus', sendFlowHeartbeat);
window.addEventListener('visibilitychange', sendFlowHeartbeat);
setInterval(sendFlowHeartbeat, 15000);
