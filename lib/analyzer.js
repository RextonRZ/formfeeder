const ANALYZER_PROMPT = `You are analyzing a Google Form survey to derive context for generating realistic mock responses.

Given the form's title, description, section header, and first-page questions, derive:
- What the survey is investigating
- Who the target respondents are
- What persona dimensions matter for realistic diversity
- Domain-specific guidance for how a real respondent would phrase answers

=== INPUT ===
Title: {TITLE}
Description: {DESCRIPTION}
Section: {SECTION}
First-page questions:
{QUESTIONS}
{HINT}

Return ONLY a JSON object matching the schema. No prose.`;

const ANALYZER_RESPONSE_SCHEMA = {
  type: 'object',
  required: ['topic', 'domain', 'target_respondent', 'persona_dimensions',
             'response_guidelines', 'stance_dimensions', 'language_style'],
  properties: {
    topic: { type: 'string' },
    domain: {
      type: 'string',
      enum: ['academic_research', 'market_research', 'customer_feedback', 'employee_survey',
             'event_registration', 'medical_health', 'education', 'political_opinion',
             'product_usability', 'general_feedback', 'other'],
    },
    purpose: { type: 'string' },
    target_respondent: { type: 'string' },
    locale_hint: { type: 'string' },
    persona_dimensions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'type', 'sample_values'],
        properties: {
          name: { type: 'string' },
          type: { type: 'string', enum: ['categorical', 'numeric_range', 'descriptive'] },
          sample_values: { type: 'array', items: { type: 'string' } },
          weights: { type: 'array', items: { type: 'number' } },
        },
      },
    },
    stance_dimensions: { type: 'array', items: { type: 'string' } },
    response_guidelines: { type: 'array', items: { type: 'string' } },
    language_style: { type: 'string' },
  },
};

async function analyzeForm(discovery, contextHint, apiKey, formUrl) {
  const cacheKey = `analysis:${await hashStr((formUrl || 'unknown').split('?')[0])}`;

  if (!contextHint) {
    const cached = await chrome.storage.local.get(cacheKey);
    if (cached[cacheKey]) return cached[cacheKey];
  }

  const questionsBlock = discovery.page1Questions
    .map((q, i) =>
      `${i + 1}. (${q.type}) ${q.title}` +
      (q.options?.length
        ? ` [options: ${q.options.slice(0, 5).join(', ')}${q.options.length > 5 ? '...' : ''}]`
        : '')
    )
    .join('\n') || '(none)';

  const prompt = ANALYZER_PROMPT
    .replace('{TITLE}', discovery.title)
    .replace('{DESCRIPTION}', discovery.description || '(none)')
    .replace('{SECTION}', discovery.sectionHeader || '(none)')
    .replace('{QUESTIONS}', questionsBlock)
    .replace('{HINT}', contextHint ? `\nUser-provided context hint: ${contextHint}` : '');

  const res = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.3,
          responseMimeType: 'application/json',
          responseSchema: ANALYZER_RESPONSE_SCHEMA,
        },
      }),
    }
  );

  const data = await res.json();
  if (!data.candidates) throw new Error(`Analyzer API error: ${JSON.stringify(data)}`);
  const analysis = JSON.parse(data.candidates[0].content.parts[0].text);
  await chrome.storage.local.set({ [cacheKey]: analysis });
  return analysis;
}

async function hashStr(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).slice(0, 8)
    .map(b => b.toString(16).padStart(2, '0')).join('');
}
