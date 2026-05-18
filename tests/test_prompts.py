import pytest
from formfeeder.prompts import build_responder_prompt, build_response_schema, _format_question


SAMPLE_ANALYSIS = {
    "topic": "AI reliance among UM students",
    "purpose": "measure dependency",
    "target_respondent": "UM undergraduates",
    "locale_hint": "Malaysia",
    "language_style": "casual English with occasional Malay",
    "response_guidelines": ["Be honest", "Use real tool names"],
    "stance_dimensions": ["ai_reliance"],
}

SAMPLE_PERSONA = {
    "gender": "Female",
    "age": 22,
    "_stances": {"ai_reliance": "mild positive"},
    "_traits": {"verbosity": "normal", "typo_tendency": False, "skips_optional": False},
}

SAMPLE_QUESTIONS = [
    {"id": "q0", "type": "short_text", "title": "Your name", "required": True,
     "options": None, "scale_low": None, "scale_high": None},
    {"id": "q1", "type": "radio", "title": "Gender", "required": True,
     "options": ["Male", "Female", "Prefer not to say"], "scale_low": None, "scale_high": None},
    {"id": "q2", "type": "scale", "title": "Rate satisfaction", "required": False,
     "options": None, "scale_low": 1, "scale_high": 5},
    {"id": "q3", "type": "checkbox", "title": "Tools used", "required": False,
     "options": ["ChatGPT", "Gemini", "Copilot", "Other"], "scale_low": None, "scale_high": None},
]


def test_build_responder_prompt_contains_topic():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "AI reliance among UM students" in prompt


def test_build_responder_prompt_contains_persona_fields():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "gender: Female" in prompt
    assert "age: 22" in prompt


def test_build_responder_prompt_excludes_private_keys():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "_stances" not in prompt.split("PERSONA")[1].split("STANCES")[0]


def test_build_responder_prompt_includes_previous_answers():
    prev = {"p1_Your name": "Alice"}
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, prev)
    assert "PREVIOUS ANSWERS" in prompt
    assert "Alice" in prompt


def test_build_responder_prompt_no_previous_block_when_empty():
    prompt = build_responder_prompt(SAMPLE_ANALYSIS, SAMPLE_PERSONA, SAMPLE_QUESTIONS, {})
    assert "PREVIOUS ANSWERS" not in prompt


def test_build_response_schema_radio_with_enum():
    qs = [{"id": "q0", "type": "radio", "options": ["A", "B", "C"],
           "required": True, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string", "enum": ["A", "B", "C"]}
    assert "q0" in schema["required"]


def test_build_response_schema_radio_with_other_option_allows_free_text():
    qs = [{"id": "q0", "type": "radio", "options": ["A", "B", "Other"],
           "required": False, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string"}
    assert "q0" not in schema["required"]


def test_build_response_schema_checkbox_with_other():
    qs = [{"id": "q0", "type": "checkbox", "options": ["X", "Y", "Other"],
           "required": False, "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "array", "items": {"type": "string"}}


def test_build_response_schema_scale_is_integer():
    qs = [{"id": "q0", "type": "scale", "options": None, "required": True,
           "scale_low": 1, "scale_high": 5, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "integer"}


def test_build_response_schema_default_is_string():
    qs = [{"id": "q0", "type": "short_text", "options": None, "required": False,
           "scale_low": None, "scale_high": None, "title": "Q"}]
    schema = build_response_schema(qs)
    assert schema["properties"]["q0"] == {"type": "string"}


def test_format_question_shows_options():
    q = {"id": "q1", "type": "radio", "title": "Fav color",
         "options": ["Red", "Blue"], "required": False,
         "scale_low": None, "scale_high": None}
    result = _format_question(q)
    assert '"Red"' in result
    assert '"Blue"' in result


def test_format_question_shows_scale_range():
    q = {"id": "q2", "type": "scale", "title": "Rate it",
         "options": None, "required": True, "scale_low": 1, "scale_high": 10}
    result = _format_question(q)
    assert "1-10" in result
    assert "[REQUIRED]" in result
