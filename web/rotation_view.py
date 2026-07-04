"""Web view helpers for A-share industry rotation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
import streamlit as st

from quant.analysis.rotation import RankerConfig
from quant.services import RotationRequest, RotationService


_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_UNIVERSE = _PROJECT_ROOT / "config" / "rotation_universe.yaml"


@dataclass(frozen=True)
class RotationViewModel:
    available: bool
    as_of: str = ""
    multiplier_label: str = ""
    top_targets_label: str = ""
    summary_rows: list[dict[str, str]] | None = None
    momentum_rows: list[dict[str, str]] | None = None
    error: str = ""

    def __post_init__(self) -> None:
        if self.summary_rows is None:
            object.__setattr__(self, "summary_rows", [])
        if self.momentum_rows is None:
            object.__setattr__(self, "momentum_rows", [])


def load_rotation_symbol_names(universe_path: str | Path = _DEFAULT_UNIVERSE) -> dict[str, str]:
    """Load display names for rotation ETF symbols."""
    path = Path(universe_path)
    if not path.exists():
        return {}

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names: dict[str, str] = {}
    for section in ("industry_etfs", "style_etfs", "defensive_global_etfs"):
        for item in data.get(section, []) or []:
            symbol = item.get("symbol")
            name = item.get("name")
            if symbol and name:
                names[str(symbol)] = str(name)
    return names


def get_latest_rotation_targets(
    *,
    start: str = "20180101",
    end: str | None = None,
    universe_path: str | Path = _DEFAULT_UNIVERSE,
    top_k: int = 8,
) -> dict[str, Any]:
    """Fetch latest rotation targets through the backend service."""
    end = end or datetime.now().strftime("%Y%m%d")
    request = RotationRequest(
        start=start,
        end=end,
        universe_path=str(universe_path),
        ranker_config=RankerConfig(top_k=top_k),
    )
    return RotationService().latest_targets(request)


@st.cache_data(ttl=3600, show_spinner=False)
def get_latest_rotation_view_model() -> RotationViewModel:
    """Return the current rotation decision as a display model."""
    try:
        payload = get_latest_rotation_targets()
        return build_rotation_view_model(payload, symbol_names=load_rotation_symbol_names())
    except Exception as exc:
        return RotationViewModel(available=False, error=f"行业轮动数据暂不可用：{exc}")


def render_rotation_summary(model: RotationViewModel | None = None) -> None:
    """Render the compact Dashboard rotation summary."""
    model = model or get_latest_rotation_view_model()

    st.markdown("### 🔁 行业轮动")
    if not model.available:
        st.caption(model.error or "暂无行业轮动数据")
        return

    col_date, col_risk, col_targets = st.columns([1, 1, 3])
    col_date.metric("最新月末", model.as_of)
    col_risk.metric("风险乘数", model.multiplier_label)
    col_targets.metric("目标方向", model.top_targets_label)


def render_rotation_details(model: RotationViewModel | None = None) -> None:
    """Render Scanner-level rotation details."""
    model = model or get_latest_rotation_view_model()

    st.subheader("🔁 行业 ETF 轮动")
    if not model.available:
        st.warning(model.error or "暂无行业轮动数据")
        return

    m1, m2 = st.columns(2)
    m1.metric("最新月末", model.as_of)
    m2.metric("风险乘数", model.multiplier_label)
    st.caption(f"当前目标方向：{model.top_targets_label}")

    st.markdown("#### 目标仓位")
    if model.summary_rows:
        st.dataframe(
            model.summary_rows,
            column_config={
                "symbol": "代码",
                "name": "名称",
                "target_weight": "策略权重",
                "final_position": "最终仓位",
            },
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("暂无目标仓位")

    st.markdown("#### 动量排名")
    if model.momentum_rows:
        st.dataframe(
            model.momentum_rows,
            column_config={
                "symbol": "代码",
                "name": "名称",
                "momentum": "动量",
            },
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("暂无动量排名")


def build_rotation_view_model(
    latest_targets: dict[str, Any] | None,
    *,
    symbol_names: dict[str, str] | None = None,
) -> RotationViewModel:
    """Convert RotationService.latest_targets output into UI-ready rows."""
    if latest_targets is None:
        return RotationViewModel(available=False, error="暂无行业轮动数据")

    required = {"as_of", "multiplier", "weights", "final_positions", "top_momentum"}
    missing = required - set(latest_targets)
    if missing:
        missing_s = ", ".join(sorted(missing))
        raise ValueError(f"latest_targets payload missing: {missing_s}")

    names = symbol_names or {}
    weights = _coerce_number_map(latest_targets["weights"])
    final_positions = _coerce_number_map(latest_targets["final_positions"])

    ordered_symbols = sorted(
        set(weights) | set(final_positions),
        key=lambda symbol: final_positions.get(symbol, weights.get(symbol, 0.0)),
        reverse=True,
    )
    summary_rows = [
        {
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "target_weight": _format_pct(weights.get(symbol, 0.0)),
            "final_position": _format_pct(final_positions.get(symbol, 0.0)),
        }
        for symbol in ordered_symbols
    ]

    momentum_rows = [
        {
            "symbol": str(row.get("symbol", "")),
            "name": names.get(str(row.get("symbol", "")), str(row.get("symbol", ""))),
            "momentum": _format_pct(float(row.get("momentum", 0.0))),
        }
        for row in latest_targets.get("top_momentum", [])
        if isinstance(row, dict) and row.get("symbol")
    ]

    top_targets = [f"{row['name']} {row['final_position']}" for row in summary_rows[:3]]

    return RotationViewModel(
        available=True,
        as_of=str(latest_targets["as_of"]),
        multiplier_label=_format_pct(float(latest_targets["multiplier"])),
        top_targets_label=", ".join(top_targets) if top_targets else "暂无目标仓位",
        summary_rows=summary_rows,
        momentum_rows=momentum_rows,
    )


def _coerce_number_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    return {str(key): float(val) for key, val in value.items()}


def _format_pct(value: float) -> str:
    pct = value * 100
    if abs(pct - round(pct)) < 0.05:
        return f"{pct:.0f}%"
    return f"{pct:.1f}%"
