importScripts('lib/analyzer.js', 'lib/prompts.js', 'lib/persona.js');

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handlers = {
    ANALYZE_FORM: () => handleAnalyze(msg),
    GENERATE_ANSWERS: () => handleAnswers(msg),
  };
  const fn = handlers[msg.type];
  if (!fn) return;
  fn().then(sendResponse).catch(err => sendResponse({ error: err.message }));
  return true;
});

async function handleAnalyze({ discovery, contextHint, formUrl }) {
  const { apiKey } = await chrome.storage.sync.get('apiKey');
  if (!apiKey) throw new Error('Gemini API key not set.');
  return analyzeForm(discovery, contextHint, apiKey, formUrl || 'unknown');
}

async function handleAnswers({ analysis, persona, questions, previousAnswers }) {
  const { apiKey } = await chrome.storage.sync.get('apiKey');
  if (!apiKey) throw new Error('Gemini API key not set.');

  const prompt = buildResponderPrompt(analysis, persona, questions, previousAnswers || {});
  const schema = buildResponseSchema(questions);

  const res = await fetchWithRetry(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.9,
          responseMimeType: 'application/json',
          responseSchema: schema,
        },
        safetySettings: [
          { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_ONLY_HIGH' },
          { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_ONLY_HIGH' },
        ],
      }),
    }
  );

  const data = await res.json();
  if (!data.candidates) throw new Error(`Gemini error: ${JSON.stringify(data)}`);
  return JSON.parse(data.candidates[0].content.parts[0].text);
}

async function fetchWithRetry(url, options, retries = 3) {
  for (let attempt = 0; attempt < retries; attempt++) {
    const res = await fetch(url, options);
    if (res.status !== 429) return res;
    const wait = 30000 * (attempt + 1);
    console.log(`[formfeeder] Rate limited — waiting ${wait / 1000}s (attempt ${attempt + 1}/${retries})`);
    await new Promise(r => setTimeout(r, wait));
  }
  throw new Error('Rate limit: failed after 3 retries');
}
