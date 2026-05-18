const RESPONDER_PROMPT = `You are simulating a survey respondent. Stay completely in character. Do NOT mention you are an AI.

=== SURVEY CONTEXT (derived from form analysis) ===
Topic: {TOPIC}
Purpose: {PURPOSE}
Target respondent: {TARGET}
Locale: {LOCALE}
Language style: {LANGUAGE_STYLE}

Domain-specific guidelines for this survey:
{GUIDELINES}

=== YOUR PERSONA (stay consistent across ALL answers) ===
{PERSONA_BLOCK}

Your stances on relevant topics:
{STANCES_BLOCK}

=== UNIVERSAL RESPONSE RULES ===
1. Open-ended text: 1-3 sentences. Match the language style and your verbosity trait ({VERBOSITY}). Sound human, not like a survey AI.
2. Likert / linear scales: cluster around your stance but vary realistically. Humans hedge. Don't pick max/min on every related item.
3. Multiple choice & dropdowns: pick what fits the persona, never random.
4. Checkboxes: pick 2-4 realistic options unless your persona would obviously pick more/fewer.
5. Numbers/ages/hours: stay within plausible ranges given your persona.
6. Email: realistic format matching your persona (school email if a student, work domain if professional). NEVER use "test@test.com" or "example@example.com".
7. Specific tools/products/brands: use real ones a person like you would actually use.
8. Matrix/grid questions: each row independent but consistent with your stance.
9. Stay consistent with previous answers (provided below). No contradicting earlier statements.
10. Apply persona traits: {TRAITS}.

=== OUTPUT FORMAT ===
Return ONLY a JSON object mapping question ID to answer:
- "short_text" / "long_text" → string
- "radio" / "dropdown" → exact string from provided options
- "checkbox" → array of exact strings from options
- "scale" → integer within the given range
- "date" → "YYYY-MM-DD"
- "time" → "HH:MM"`;

function buildResponderPrompt(analysis, persona, questions, previousAnswers) {
  const personaBlock = Object.entries(persona)
    .filter(([k]) => !k.startsWith('_'))
    .map(([k, v]) => `- ${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
    .join('\n');

  const stancesBlock = Object.entries(persona._stances || {})
    .map(([k, v]) => `- ${k}: ${v}`).join('\n') || '(none specified)';

  const traitsBlock = `verbosity=${persona._traits?.verbosity}, occasional typos=${persona._traits?.typo_tendency}`;

  const prevBlock = Object.keys(previousAnswers).length
    ? `\n=== YOUR PREVIOUS ANSWERS (stay consistent) ===\n${JSON.stringify(previousAnswers, null, 2)}\n`
    : '';

  const questionsBlock = questions.map(q => {
    let line = `[${q.id}] (${q.type}) ${q.title}`;
    if (q.options?.length) line += `\n    Options: ${q.options.map(o => `"${o}"`).join(', ')}`;
    if (q.type === 'scale') line += `\n    Range: ${q.scaleLow}-${q.scaleHigh}`;
    if (q.required) line += '  [REQUIRED]';
    return line;
  }).join('\n\n');

  return RESPONDER_PROMPT
    .replace('{TOPIC}', analysis.topic)
    .replace('{PURPOSE}', analysis.purpose || 'unspecified')
    .replace('{TARGET}', analysis.target_respondent)
    .replace('{LOCALE}', analysis.locale_hint || 'unspecified')
    .replace('{LANGUAGE_STYLE}', analysis.language_style)
    .replace('{GUIDELINES}', analysis.response_guidelines.map(g => `- ${g}`).join('\n'))
    .replace('{PERSONA_BLOCK}', personaBlock)
    .replace('{STANCES_BLOCK}', stancesBlock)
    .replace('{VERBOSITY}', persona._traits?.verbosity || 'normal')
    .replace('{TRAITS}', traitsBlock)
    + prevBlock
    + `\n=== QUESTIONS TO ANSWER ===\n${questionsBlock}\n\nReturn ONLY valid JSON. No markdown.`;
}

function buildResponseSchema(questions) {
  const properties = {};
  for (const q of questions) {
    switch (q.type) {
      case 'checkbox':
        properties[q.id] = { type: 'array', items: { type: 'string', enum: q.options } };
        break;
      case 'radio':
      case 'dropdown':
        properties[q.id] = { type: 'string', enum: q.options };
        break;
      case 'scale':
        properties[q.id] = { type: 'integer' };
        break;
      default:
        properties[q.id] = { type: 'string' };
    }
  }
  return {
    type: 'object',
    properties,
    required: questions.filter(q => q.required).map(q => q.id),
  };
}
