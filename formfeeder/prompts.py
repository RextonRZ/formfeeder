import json
import re

RESPONDER_PROMPT = """You are simulating a survey respondent. Stay completely in character. Do NOT mention you are an AI.

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
2. Likert / linear scales: cluster around your stance but vary realistically. Humans hedge.
3. Multiple choice & dropdowns: pick what fits the persona, never random.
4. Checkboxes: pick 2-4 realistic options unless your persona would obviously pick more/fewer.
5. Numbers/ages/hours: stay within plausible ranges given your persona.
6. Email: realistic format. NEVER use "test@test.com" or "example@example.com".
7. Specific tools/products/brands: use real ones a person like you would actually use.
8. Stay consistent with previous answers. No contradicting earlier statements.
9. For questions with an "Other" option: return any realistic answer. If it matches an available option exactly, that option is selected. Otherwise "Other" is selected and your text is written in.
10. Apply persona traits: {TRAITS}.

=== OUTPUT FORMAT ===
Return ONLY a JSON object mapping question ID to answer:
- "short_text" / "long_text" -> string
- "radio" / "dropdown" -> exact string from provided options (or custom text if Other available)
- "checkbox" -> array of strings (exact options, or custom text for Other)
- "scale" -> integer within the given range
- "date" -> "YYYY-MM-DD"
- "time" -> "HH:MM\""""


def _format_question(q):
    line = f"[{q['id']}] ({q['type']}) {q['title']}"
    if q.get("options"):
        line += "\n    Options: " + ", ".join(f'"{o}"' for o in q["options"])
    if q.get("type") == "scale" and q.get("scale_low") is not None:
        line += f"\n    Range: {q['scale_low']}-{q['scale_high']}"
    if q.get("required"):
        line += "  [REQUIRED]"
    return line


def build_responder_prompt(analysis, persona, questions, previous_answers):
    persona_block = "\n".join(
        f"- {k}: {v}"
        for k, v in persona.items()
        if not str(k).startswith("_")
    )

    stances_block = "\n".join(
        f"- {k}: {v}"
        for k, v in persona.get("_stances", {}).items()
    ) or "(none specified)"

    traits = persona.get("_traits", {})
    traits_block = (
        f"verbosity={traits.get('verbosity', 'normal')}, "
        f"occasional typos={traits.get('typo_tendency', False)}"
    )

    prev_block = ""
    if previous_answers:
        prev_block = (
            "\n=== YOUR PREVIOUS ANSWERS (stay consistent) ===\n"
            + json.dumps(previous_answers, indent=2, ensure_ascii=False)
            + "\n"
        )

    questions_block = "\n\n".join(_format_question(q) for q in questions)

    return (
        RESPONDER_PROMPT
        .replace("{TOPIC}", analysis.get("topic", ""))
        .replace("{PURPOSE}", analysis.get("purpose", "unspecified"))
        .replace("{TARGET}", analysis.get("target_respondent", ""))
        .replace("{LOCALE}", analysis.get("locale_hint", "unspecified"))
        .replace("{LANGUAGE_STYLE}", analysis.get("language_style", ""))
        .replace("{GUIDELINES}", "\n".join(f"- {g}" for g in analysis.get("response_guidelines", [])))
        .replace("{PERSONA_BLOCK}", persona_block)
        .replace("{STANCES_BLOCK}", stances_block)
        .replace("{VERBOSITY}", traits.get("verbosity", "normal"))
        .replace("{TRAITS}", traits_block)
        + prev_block
        + f"\n=== QUESTIONS TO ANSWER ===\n{questions_block}\n\nReturn ONLY valid JSON. No markdown."
    )


def build_response_schema(questions):
    properties = {}
    for q in questions:
        has_other = any(
            re.match(r"^other$", o, re.IGNORECASE)
            for o in (q.get("options") or [])
        )
        q_type = q["type"]

        if q_type == "checkbox":
            items_schema = (
                {"type": "string"} if has_other
                else {"type": "string", "enum": q["options"]}
            )
            cb_schema = {"type": "array", "items": items_schema}
            if q.get("required"):
                cb_schema["minItems"] = 1
            properties[q["id"]] = cb_schema
        elif q_type in ("radio", "dropdown"):
            properties[q["id"]] = (
                {"type": "string"}
                if has_other
                else {"type": "string", "enum": q["options"]}
            )
        elif q_type == "scale":
            properties[q["id"]] = {"type": "integer"}
        else:
            properties[q["id"]] = {"type": "string"}

    return {
        "type": "object",
        "properties": properties,
        "required": [q["id"] for q in questions if q.get("required")],
    }
