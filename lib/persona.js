function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function weightedPick(values, weights) {
  if (!weights || weights.length !== values.length) return pick(values);
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < values.length; i++) {
    r -= weights[i];
    if (r <= 0) return values[i];
  }
  return values[values.length - 1];
}

function generatePersona(analysis) {
  const persona = {};

  for (const dim of analysis.persona_dimensions) {
    if (dim.type === 'numeric_range' && dim.sample_values.length >= 2) {
      const lo = Number(dim.sample_values[0]);
      const hi = Number(dim.sample_values[1]);
      persona[dim.name] = lo + Math.floor(Math.random() * (hi - lo + 1));
    } else {
      persona[dim.name] = weightedPick(dim.sample_values, dim.weights);
    }
  }

  persona._stances = {};
  for (const stance of (analysis.stance_dimensions || [])) {
    persona._stances[stance] = pick([
      'strong negative', 'mild negative', 'neutral', 'mild positive', 'strong positive',
    ]);
  }

  persona._traits = {
    verbosity: weightedPick(['terse', 'normal', 'wordy'], [0.3, 0.5, 0.2]),
    typo_tendency: Math.random() < 0.15,
    skips_optional: Math.random() < 0.2,
  };

  return persona;
}
