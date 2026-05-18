import random
import pytest
from formfeeder.persona import generate, _pick, _weighted_pick


def make_analysis(dimensions, stances=None):
    return {
        "persona_dimensions": dimensions,
        "stance_dimensions": stances or [],
    }


def test_pick_returns_element_from_array():
    result = _pick(["a", "b", "c"])
    assert result in ["a", "b", "c"]


def test_weighted_pick_falls_back_when_weights_mismatch():
    result = _weighted_pick(["x", "y"], [1.0])  # wrong length
    assert result in ["x", "y"]


def test_weighted_pick_falls_back_when_no_weights():
    result = _weighted_pick(["x", "y"], None)
    assert result in ["x", "y"]


def test_generate_categorical_dimension():
    analysis = make_analysis([
        {"name": "gender", "type": "categorical", "sample_values": ["Male", "Female"]}
    ])
    persona = generate(analysis)
    assert persona["gender"] in ["Male", "Female"]


def test_generate_numeric_range_dimension():
    analysis = make_analysis([
        {"name": "age", "type": "numeric_range", "sample_values": ["18", "25"]}
    ])
    persona = generate(analysis)
    assert isinstance(persona["age"], int)
    assert 18 <= persona["age"] <= 25


def test_generate_stances():
    analysis = make_analysis(
        dimensions=[],
        stances=["attitude_towards_ai", "reliance_level"],
    )
    persona = generate(analysis)
    assert set(persona["_stances"].keys()) == {"attitude_towards_ai", "reliance_level"}
    valid = {"strong negative", "mild negative", "neutral", "mild positive", "strong positive"}
    for v in persona["_stances"].values():
        assert v in valid


def test_generate_traits():
    analysis = make_analysis(dimensions=[])
    persona = generate(analysis)
    assert persona["_traits"]["verbosity"] in ["terse", "normal", "wordy"]
    assert isinstance(persona["_traits"]["typo_tendency"], bool)
    assert isinstance(persona["_traits"]["skips_optional"], bool)


def test_generate_handles_empty_stance_dimensions():
    analysis = make_analysis(dimensions=[])
    persona = generate(analysis)
    assert persona["_stances"] == {}


def test_generate_multiple_times_produces_variety():
    random.seed(None)
    analysis = make_analysis([
        {"name": "faculty", "type": "categorical",
         "sample_values": ["Engineering", "Science", "Arts", "Medicine", "Law"]}
    ])
    results = {generate(analysis)["faculty"] for _ in range(50)}
    assert len(results) > 1  # should not always return the same value
