import random


def _pick(arr):
    return arr[random.randint(0, len(arr) - 1)]


def _weighted_pick(values, weights):
    if not weights or len(weights) != len(values):
        return _pick(values)
    total = sum(weights)
    r = random.random() * total
    for v, w in zip(values, weights):
        r -= w
        if r <= 0:
            return v
    return values[-1]


def generate(analysis):
    persona = {}

    for dim in analysis["persona_dimensions"]:
        if dim["type"] == "numeric_range" and len(dim["sample_values"]) >= 2:
            try:
                lo = int(dim["sample_values"][0])
                hi = int(dim["sample_values"][1])
                persona[dim["name"]] = random.randint(lo, hi)
            except (ValueError, TypeError):
                # sample_values aren't plain integers — treat as categorical
                persona[dim["name"]] = _weighted_pick(dim["sample_values"], dim.get("weights"))
        else:
            persona[dim["name"]] = _weighted_pick(
                dim["sample_values"], dim.get("weights")
            )

    persona["_stances"] = {
        stance: _pick([
            "strong negative", "mild negative", "neutral",
            "mild positive", "strong positive",
        ])
        for stance in analysis.get("stance_dimensions", [])
    }

    persona["_traits"] = {
        "verbosity": _weighted_pick(["terse", "normal", "wordy"], [0.3, 0.5, 0.2]),
        "typo_tendency": random.random() < 0.15,
        "skips_optional": random.random() < 0.2,
    }

    return persona
