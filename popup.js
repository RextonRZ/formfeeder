const $ = id => document.getElementById(id);

function showScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  $(`screen-${name}`).classList.add('active');
}

function appendLog(text) {
  const log = $('log');
  log.textContent += text + '\n';
  log.scrollTop = log.scrollHeight;
}

// Show correct screen on open
chrome.storage.sync.get('apiKey', ({ apiKey }) => {
  showScreen(apiKey ? 'run' : 'settings');
});

$('saveKey').addEventListener('click', () => {
  const key = $('apiKey').value.trim();
  if (!key.startsWith('AIza')) {
    $('keyError').textContent = 'Key must start with AIza';
    return;
  }
  $('keyError').textContent = '';
  chrome.storage.sync.set({ apiKey: key }, () => showScreen('run'));
});

$('toSettings').addEventListener('click', () => showScreen('settings'));

$('clearCache').addEventListener('click', () => {
  chrome.storage.local.get(null, items => {
    const keys = Object.keys(items).filter(k => k.startsWith('analysis:'));
    chrome.storage.local.remove(keys, () => appendLog(`Cleared ${keys.length} cached analysis(es).`));
  });
});

$('exportLog').addEventListener('click', () => {
  chrome.storage.local.get('runLog', ({ runLog = [] }) => {
    const blob = new Blob([JSON.stringify(runLog, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `formfeeder-log-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });
});

$('runBtn').addEventListener('click', async () => {
  const count = parseInt($('count').value) || 5;
  const contextHint = $('hint').value.trim();
  if (count > 5 && !confirm(`Run ${count} responses? This will make ${count + 1} Gemini API calls.`)) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) { appendLog('Error: no active tab found.'); return; }
  if (!tab.url?.includes('docs.google.com/forms')) {
    appendLog('Error: open a Google Form first.');
    return;
  }
  chrome.tabs.sendMessage(tab.id, { type: 'RUN_FILL', count, contextHint }, () => {
    if (chrome.runtime.lastError) {
      appendLog(`Error: ${chrome.runtime.lastError.message}`);
      return;
    }
    appendLog(`Starting ${count} response(s)...`);
  });
});

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'STATUS') appendLog(msg.text);
});
