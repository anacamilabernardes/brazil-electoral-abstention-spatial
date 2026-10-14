import json
from pathlib import Path

import pandas as pd
import pytest

from abstention_spatial.pipeline import input_receipt
from abstention_spatial.reconciliation import reconcile
from abstention_spatial.sources import receipt


def reference(tmp_path, **overrides):
    row = dict(year=2026, round=1, scope="including_ZZ", eligible=110,
               turnout=87, absent=23, source_url="https://example.org/official.zip",
               published_date="2026-10-07", member="report.pdf", pages="2-3")
    row.update(overrides)
    path = tmp_path / "reference.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def report():
    return {"national_domestic_by_year_round": [dict(year=2026, round=1, eligible=100, turnout=80, absent=20)],
            "source_audit": {"2026": {"zz_totals_by_round": {"1": dict(eligible=10, turnout=7, absent=3)}}}}


def test_reconcile_adds_overseas_only_for_matching_universe(tmp_path):
    assert reconcile(report(), reference(tmp_path))["comparisons"][0]["status"] == "matched"
    result = reconcile(report(), reference(tmp_path, scope="domestic", eligible=100, turnout=80, absent=20))
    assert result["comparisons"][0]["difference"] == dict(eligible=0, turnout=0, absent=0)


def test_reconcile_retains_difference(tmp_path):
    result = reconcile(report(), reference(tmp_path, absent=22))
    assert result["status"] == "mismatch"
    assert result["comparisons"][0]["difference"]["absent"] == 1


@pytest.mark.parametrize("overrides, message", [
    ({"published_date": "2026-10-15"}, "cutoff"),
    ({"round": 2}, "Second-round"),
    ({"scope": "unknown"}, "universe"),
])
def test_reconcile_rejects_invalid_reference(tmp_path, overrides, message):
    with pytest.raises(ValueError, match=message):
        reconcile(report(), reference(tmp_path, **overrides))


def test_receipt_does_not_attribute_custom_input_to_official_url(tmp_path):
    path = tmp_path / "custom.csv"
    path.write_text("custom bytes")
    assert input_receipt(path)["source_url"] is None
    rec = receipt(path, source_url="https://example.org/input")
    path.with_suffix(".csv.receipt.json").write_text(json.dumps(rec))
    assert input_receipt(path)["source_url"] == rec["source_url"]
    path.write_text("changed bytes")
    with pytest.raises(ValueError, match="differs from its download receipt"):
        input_receipt(path)
