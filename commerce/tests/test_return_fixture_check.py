# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""scripts/check.py's merchant_returns.json validation, on the shipped fixtures and on
rows that break each rule."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("repo_check", REPO_ROOT / "scripts" / "check.py")
check = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = check  # dataclasses resolve their module while it executes
_spec.loader.exec_module(check)


def row(**overrides):
    return {
        "return_id": "R-1",
        "listing_id": "L-1",
        "returned_on": "2026-06-20",
        "reason": "runs_small",
    } | overrides


@pytest.mark.parametrize("vertical", check.VERTICALS)
def test_the_shipped_returns_validate(vertical):
    data = REPO_ROOT / "examples" / vertical / "data"
    raw = check.load_json(data / "merchant_returns.json")
    assert check.return_problems(raw, check.catalog_ids_of(data)) == []


def test_each_broken_rule_is_named():
    raw = {
        "dates_anchored_to": "2026-06-26",
        "returns": [
            row(),
            row(),
            row(return_id="R-2", listing_id="L-9"),
            row(return_id="R-3", reason="wrong_colour"),
            row(return_id="R-4", returned_on="2026-06-27"),
            row(return_id="R-5", returned_on="not a date"),
        ],
    }
    found = check.return_problems(raw, {"L-1"})
    assert found[0] == "duplicate return id R-1"
    assert "R-2: unknown listing L-9" in found
    assert "R-3: unknown reason 'wrong_colour'" in found
    assert "R-4: dated after dates_anchored_to" in found
    assert any(line.startswith("R-5: ") for line in found)
    assert len(found) == 5
