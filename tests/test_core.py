import pandas as pd
import pytest
from abstention_spatial.core import validate_municipal_panel, historical_round_change


def example():
    return pd.DataFrame([
        {"municipality_code": "3550308", "year": 2022, "round": 1, "eligible": 100, "turnout": 80, "absent": 20},
        {"municipality_code": "3550308", "year": 2022, "round": 2, "eligible": 100, "turnout": 76, "absent": 24},
        {"municipality_code": "3550308", "year": 2026, "round": 1, "eligible": 110, "turnout": 88, "absent": 22},
    ])


def test_rate():
    x = validate_municipal_panel(example())
    assert x.iloc[0]["abstention_rate"] == 0.2


def test_invalid_counts():
    x = example()
    x.loc[0, "absent"] = 21
    with pytest.raises(ValueError):
        validate_municipal_panel(x)


def test_duplicate_key():
    x = pd.concat([example(), example().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError):
        validate_municipal_panel(x)


def test_baseline():
    result = historical_round_change(example(), 2022, 2026)
    assert len(result) == 1
    assert result.iloc[0]["predicted_rate"] == pytest.approx(0.24)
