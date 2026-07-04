"""Tests for web-facing industry rotation view models."""

from __future__ import annotations

import pytest

from web.rotation_view import (
    RotationViewModel,
    build_rotation_view_model,
    render_rotation_details,
    render_rotation_summary,
)


def _latest_targets_payload() -> dict:
    return {
        "as_of": "2026-06-30",
        "multiplier": 0.75,
        "weights": {
            "512800.SH": 0.6,
            "512000.SH": 0.4,
        },
        "final_positions": {
            "512800.SH": 0.45,
            "512000.SH": 0.30,
        },
        "top_momentum": [
            {"symbol": "512800.SH", "momentum": 0.1823},
            {"symbol": "512000.SH", "momentum": 0.091},
            {"symbol": "515000.SH", "momentum": -0.014},
        ],
    }


def test_rotation_view_model_summarizes_latest_targets() -> None:
    model = build_rotation_view_model(
        _latest_targets_payload(),
        symbol_names={
            "512800.SH": "银行ETF",
            "512000.SH": "券商ETF",
            "515000.SH": "科技ETF",
        },
    )

    assert model.available is True
    assert model.as_of == "2026-06-30"
    assert model.multiplier_label == "75%"
    assert model.top_targets_label == "银行ETF 45%, 券商ETF 30%"
    assert model.summary_rows == [
        {"symbol": "512800.SH", "name": "银行ETF", "target_weight": "60%", "final_position": "45%"},
        {"symbol": "512000.SH", "name": "券商ETF", "target_weight": "40%", "final_position": "30%"},
    ]
    assert model.momentum_rows[0] == {
        "symbol": "512800.SH",
        "name": "银行ETF",
        "momentum": "18.2%",
    }


def test_rotation_view_model_handles_missing_payload() -> None:
    model = build_rotation_view_model(None)

    assert model.available is False
    assert model.error == "暂无行业轮动数据"
    assert model.summary_rows == []
    assert model.momentum_rows == []


def test_rotation_view_model_rejects_malformed_payload() -> None:
    with pytest.raises(ValueError, match="latest_targets payload"):
        build_rotation_view_model({"as_of": "2026-06-30"})


class _FakeColumn:
    def __init__(self, calls: list[tuple]) -> None:
        self.calls = calls

    def metric(self, *args) -> None:
        self.calls.append(("metric", args))


class _FakeStreamlit:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def markdown(self, text: str) -> None:
        self.calls.append(("markdown", text))

    def subheader(self, text: str) -> None:
        self.calls.append(("subheader", text))

    def caption(self, text: str) -> None:
        self.calls.append(("caption", text))

    def warning(self, text: str) -> None:
        self.calls.append(("warning", text))

    def info(self, text: str) -> None:
        self.calls.append(("info", text))

    def columns(self, count_or_spec):
        count = count_or_spec if isinstance(count_or_spec, int) else len(count_or_spec)
        return [_FakeColumn(self.calls) for _ in range(count)]

    def dataframe(self, data, **kwargs) -> None:
        self.calls.append(("dataframe", data, kwargs))


def test_render_rotation_summary_uses_compact_dashboard_copy(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr("web.rotation_view.st", fake_st)

    render_rotation_summary(
        RotationViewModel(
            available=True,
            as_of="2026-06-30",
            multiplier_label="75%",
            top_targets_label="银行ETF 45%, 券商ETF 30%",
        )
    )

    assert ("markdown", "### 🔁 行业轮动") in fake_st.calls
    assert ("metric", ("最新月末", "2026-06-30")) in fake_st.calls
    assert ("metric", ("目标方向", "银行ETF 45%, 券商ETF 30%")) in fake_st.calls


def test_render_rotation_details_shows_tables(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr("web.rotation_view.st", fake_st)

    render_rotation_details(
        RotationViewModel(
            available=True,
            as_of="2026-06-30",
            multiplier_label="75%",
            top_targets_label="银行ETF 45%",
            summary_rows=[{"symbol": "512800.SH", "name": "银行ETF"}],
            momentum_rows=[{"symbol": "512800.SH", "name": "银行ETF", "momentum": "18.2%"}],
        )
    )

    assert ("subheader", "🔁 行业 ETF 轮动") in fake_st.calls
    dataframe_calls = [call for call in fake_st.calls if call[0] == "dataframe"]
    assert len(dataframe_calls) == 2
