function discoverForm() {
  const titleEl =
    document.querySelector('div[role="heading"][aria-level="1"]') ||
    document.querySelector('.freebirdFormviewerViewHeaderTitle') ||
    document.querySelector('div[role="heading"]');
  const title = titleEl?.innerText?.trim() || 'Untitled Form';

  let description = '';
  const descCandidates = document.querySelectorAll(
    'div[role="heading"] ~ div, .freebirdFormviewerViewHeaderDescription'
  );
  for (const el of descCandidates) {
    const text = el.innerText?.trim();
    if (text && text.length > 20 && text.length < 2000) { description = text; break; }
  }

  const sectionHeader =
    document.querySelector('div[role="heading"][aria-level="2"]')?.innerText?.trim();

  const page1Questions = scrapeCurrentPage().map(q => ({
    title: q.title, type: q.type, options: q.options,
    scaleLow: q.scaleLow, scaleHigh: q.scaleHigh,
  }));

  return { title, description, sectionHeader, page1Questions };
}

// Stub — replaced in Phase 6
function scrapeCurrentPage() { return []; }

function status(text) {
  chrome.runtime.sendMessage({ type: 'STATUS', text }).catch(() => {});
  console.log('[formfeeder]', text);
}

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'RUN_FILL') runBatch(msg.count, msg.contextHint);
});
