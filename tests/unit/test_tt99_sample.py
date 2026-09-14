from __future__ import annotations

import copy
from pathlib import Path

import pytest
from letron_api.control.tt99_sample import load_sample, validate_sample


def test_tt99_sample_is_utf8_json_and_balanced() -> None:
    sample = load_sample(
        str(Path(__file__).parents[2] / "config" / "fixtures" / "tt99" / "tt99-vnd-realistic.json")
    )
    assert sample["currency"] == "VND"
    assert len(sample["journal_entries"]) >= 8
    assert set(sample["b09_inputs"]) == {"N08", "N09", "N10"}


def test_tt99_sample_rejects_unbalanced_entry() -> None:
    sample = load_sample(
        str(Path(__file__).parents[2] / "config" / "fixtures" / "tt99" / "tt99-vnd-realistic.json")
    )
    invalid = copy.deepcopy(sample)
    invalid["journal_entries"][0]["lines"][0]["debit"] = 1
    with pytest.raises(ValueError, match="not balanced"):
        validate_sample(invalid)
