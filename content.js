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

function scrapeCurrentPage() {
  const items = document.querySelectorAll('div[role="listitem"]');
  const questions = [];

  items.forEach((item, idx) => {
    const titleEl = item.querySelector('div[role="heading"]');
    if (!titleEl) return;
    const title = titleEl.innerText.replace(/\s*\*$/, '').trim();
    const required = !!item.querySelector(
      '[aria-label*="Required"], [aria-label*="required"]'
    );
    const id = `q${idx}`;

    let type, options, scaleLow, scaleHigh;

    if (item.querySelector('textarea')) {
      type = 'long_text';
    } else if (item.querySelector('input[type="date"]')) {
      type = 'date';
    } else if (item.querySelector('input[type="time"]')) {
      type = 'time';
    } else if (item.querySelector('[role="radiogroup"]')) {
      const radios = item.querySelectorAll('[role="radio"]');
      const labels = [...radios].map(
        r => r.getAttribute('aria-label') || r.dataset.value || ''
      );
      const allNumeric = labels.length >= 3 && labels.every(l => /^\d+$/.test(l.trim()));
      if (allNumeric) {
        type = 'scale';
        const nums = labels.map(Number);
        scaleLow = Math.min(...nums);
        scaleHigh = Math.max(...nums);
      } else {
        type = 'radio';
        options = labels.filter(Boolean);
      }
    } else if (item.querySelector('[role="checkbox"]')) {
      type = 'checkbox';
      options = [...item.querySelectorAll('[role="checkbox"]')]
        .map(c => c.getAttribute('aria-label')).filter(Boolean);
    } else if (item.querySelector('[role="listbox"]')) {
      type = 'dropdown';
      const listbox = item.querySelector('[role="listbox"]');
      listbox.click();
      options = [...document.querySelectorAll('[role="option"]')]
        .map(o => o.innerText.trim()).filter(t => t && t !== 'Choose');
      document.body.click();
    } else if (item.querySelector('input[type="text"]')) {
      type = 'short_text';
    } else {
      return;
    }

    questions.push({ id, domRef: item, title, type, options, required, scaleLow, scaleHigh });
  });

  return questions;
}

async function fillQuestion(q, answer) {
  const item = q.domRef;
  if (answer === undefined || answer === null) return;

  switch (q.type) {
    case 'short_text':
      setNativeValue(item.querySelector('input[type="text"]'), String(answer));
      break;
    case 'long_text':
      setNativeValue(item.querySelector('textarea'), String(answer));
      break;
    case 'radio':
    case 'scale': {
      const radios = item.querySelectorAll('[role="radio"]');
      const target = [...radios].find(r =>
        (r.getAttribute('aria-label') || r.dataset.value || '') === String(answer)
      );
      target?.click();
      break;
    }
    case 'checkbox': {
      const boxes = item.querySelectorAll('[role="checkbox"]');
      const wanted = new Set((answer || []).map(String));
      boxes.forEach(b => {
        if (wanted.has(b.getAttribute('aria-label'))) b.click();
      });
      break;
    }
    case 'dropdown': {
      const listbox = item.querySelector('[role="listbox"]');
      listbox.click();
      await sleep(300);
      const opt = [...document.querySelectorAll('[role="option"]')]
        .find(o => o.innerText.trim() === String(answer));
      if (opt) opt.click(); else document.body.click();
      break;
    }
    case 'date':
      setNativeValue(item.querySelector('input[type="date"]'), String(answer));
      break;
    case 'time':
      setNativeValue(item.querySelector('input[type="time"]'), String(answer));
      break;
  }
}

function status(text) {
  chrome.runtime.sendMessage({ type: 'STATUS', text }).catch(() => {});
  console.log('[formfeeder]', text);
}

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'RUN_FILL') runBatch(msg.count, msg.contextHint);
});
