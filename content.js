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

async function runBatch(count, contextHint) {
  showBadge(`formfeeder: starting…`);
  try {
    status('Discovering form...');
    const discovery = discoverForm();
    status(`Form: "${discovery.title}"`);

    status('Analyzing form context (cached after first run)...');
    const analysis = await chrome.runtime.sendMessage({
      type: 'ANALYZE_FORM',
      discovery,
      contextHint,
      formUrl: location.href,
    });
    if (analysis?.error) throw new Error(analysis.error);
    status(`Topic: ${analysis.topic}`);
    status(`Target: ${analysis.target_respondent}`);

    for (let i = 1; i <= count; i++) {
      const persona = generatePersona(analysis);
      showBadge(`formfeeder: ${i}/${count}`);
      status(`Run ${i}/${count} — persona: ${summarizePersona(persona)}`);

      try {
        await runFill(analysis, persona, i, count);
        logResult({ runIndex: i, persona, timestamp: Date.now() });
      } catch (e) {
        status(`Run ${i} failed: ${e.message}`);
      }

      if (i < count) {
        await sleep(jitter(1500));
        const link = [...document.querySelectorAll('a, [role="link"]')]
          .find(a => /submit another|hantar respons lain/i.test(a.innerText));
        if (link) {
          link.click();
          await sleep(jitter(1500));
        } else {
          status('No "Submit another" link — stopping');
          break;
        }
      }
    }

    status(`Batch complete: ${count} response(s) submitted`);
  } finally {
    hideBadge();
  }
}

async function runFill(analysis, persona, runIndex, totalRuns) {
  const allAnswers = {};
  let pageNum = 1;
  let pagesWithoutProgress = 0;

  while (true) {
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: scraping`);
    const questions = scrapeCurrentPage();

    if (!questions.length) {
      pagesWithoutProgress++;
      if (pagesWithoutProgress >= 2) {
        status('No questions found for 2 consecutive pages — stopping run');
        break;
      }
      break;
    }
    pagesWithoutProgress = 0;

    const cleaned = questions.map(({ domRef, ...rest }) => rest);
    status(`Run ${runIndex}/${totalRuns} — page ${pageNum}: generating ${cleaned.length} answer(s)`);

    const answers = await chrome.runtime.sendMessage({
      type: 'GENERATE_ANSWERS',
      analysis,
      persona,
      questions: cleaned,
      previousAnswers: allAnswers,
    });
    if (answers?.error) throw new Error(answers.error);

    for (const q of questions) {
      await fillQuestion(q, answers[q.id]);
      allAnswers[`p${pageNum}_${q.title}`] = answers[q.id];
      await sleep(jitter(140));
    }

    const allButtons = [...document.querySelectorAll('div[role="button"]')];
    const submitBtn = allButtons.find(b => /^(submit|hantar)$/i.test(b.innerText.trim()));
    const nextBtn = allButtons.find(b => /^(next|seterusnya)$/i.test(b.innerText.trim()));

    if (submitBtn) {
      submitBtn.click();
      await sleep(jitter(1500));
      break;
    }
    if (!nextBtn) {
      status('No Next or Submit button found — stopping run');
      break;
    }
    nextBtn.click();
    pageNum++;
    await sleep(jitter(900));
  }
}

function summarizePersona(p) {
  return Object.entries(p)
    .filter(([k]) => !k.startsWith('_'))
    .slice(0, 3)
    .map(([k, v]) => `${k}=${v}`)
    .join(', ');
}

function logResult(entry) {
  chrome.storage.local.get('runLog', ({ runLog = [] }) => {
    runLog.push(entry);
    chrome.storage.local.set({ runLog });
  });
}

function showBadge(text) {
  let badge = document.getElementById('_ff_badge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = '_ff_badge';
    badge.style.cssText = [
      'position:fixed', 'bottom:16px', 'right:16px',
      'background:#4f46e5', 'color:#fff', 'padding:8px 14px',
      'border-radius:20px', 'font:600 13px system-ui', 'z-index:999999',
      'box-shadow:0 2px 8px rgba(0,0,0,.3)',
    ].join(';');
    document.body.appendChild(badge);
  }
  badge.textContent = text;
}

function hideBadge() {
  document.getElementById('_ff_badge')?.remove();
}

chrome.runtime.onMessage.addListener(msg => {
  if (msg.type === 'RUN_FILL') runBatch(msg.count, msg.contextHint);
});
