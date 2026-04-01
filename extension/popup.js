function refresh() {
  chrome.runtime.sendMessage({ type: 'STATUS' }, (data) => {
    if (!data) return;

    const agentEl = document.getElementById('agent-status');
    const tokenEl = document.getElementById('token-status');
    const statsEl = document.getElementById('stats');

    agentEl.className = `status ${data.agentConnected ? 'connected' : 'disconnected'}`;
    agentEl.textContent = data.agentConnected ? '✅ Agent connected' : '❌ Agent disconnected';

    tokenEl.className = `status ${data.flowKeyPresent ? 'connected' : 'disconnected'}`;
    const age = data.tokenAge ? `${Math.round(data.tokenAge / 60000)}m ago` : '—';
    tokenEl.textContent = data.flowKeyPresent ? `🔑 Token captured (${age})` : '❌ No token — open Flow tab';

    const m = data.metrics || {};
    statsEl.innerHTML = `
      <div class="stat"><span class="label">State</span><span class="value">${data.state}</span></div>
      <div class="stat"><span class="label">Requests</span><span class="value">${m.requestCount || 0}</span></div>
      <div class="stat"><span class="label">Success</span><span class="value">${m.successCount || 0}</span></div>
      <div class="stat"><span class="label">Failed</span><span class="value">${m.failedCount || 0}</span></div>
      <div class="stat"><span class="label">Last error</span><span class="value">${m.lastError || '—'}</span></div>
    `;
  });
}

document.getElementById('btn-test').addEventListener('click', () => {
  const btn = document.getElementById('btn-test');
  btn.textContent = '⏳ Solving...';
  btn.disabled = true;
  chrome.runtime.sendMessage({ type: 'TEST_CAPTCHA' }, (r) => {
    btn.textContent = r?.token ? '✅ Token OK' : `❌ ${r?.error || 'Failed'}`;
    btn.disabled = false;
    setTimeout(() => { btn.textContent = '🧪 Test Captcha'; }, 3000);
  });
});

document.getElementById('btn-flow').addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'OPEN_FLOW_TAB' });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === 'STATUS_PUSH') refresh();
});

refresh();
