"""
Momentum Delta Engine — 变化率检测

纯计算模块，不依赖任何数据源。对任意时间序列计算：
- velocity:     一阶导（N日变化率）
- acceleration:  二阶导（velocity 的变化率）
- zscore:        velocity 相对历史的标准差偏离
- streak:        连续同方向变化天数
- status:        人可读的状态标签
- alert:         异动时的人话描述
"""

from typing import Dict

import numpy as np
import pandas as pd


_STABLE_THRESHOLD = 0.5
_ZSCORE_ALERT_THRESHOLD = 2.0

_STATUS_LABELS = {
    "accelerating_up": "加速上行",
    "decelerating_up": "减速上行",
    "accelerating_down": "加速下行",
    "decelerating_down": "减速下行",
    "stable": "平稳",
}


class MomentumDelta:
    """对任意时间序列计算变化率指标。"""

    @staticmethod
    def compute(
        series: pd.Series,
        velocity_window: int = 5,
        zscore_window: int = 60,
    ) -> dict:
        if len(series) < velocity_window + 1:
            return {
                "velocity": 0.0,
                "acceleration": 0.0,
                "zscore": 0.0,
                "streak": 0,
                "velocity_series": pd.Series(np.nan, index=series.index),
                "status": "stable",
                "status_cn": _STATUS_LABELS["stable"],
                "alert": None,
            }

        vel_series = series.diff(velocity_window)
        velocity = float(vel_series.iloc[-1]) if not pd.isna(vel_series.iloc[-1]) else 0.0

        acc_series = vel_series.diff(1)
        acceleration = float(acc_series.iloc[-1]) if not pd.isna(acc_series.iloc[-1]) else 0.0

        if len(vel_series.dropna()) >= zscore_window:
            lookback = vel_series.dropna().iloc[-zscore_window:]
            mean = lookback.mean()
            std = lookback.std()
            zscore = float((velocity - mean) / std) if std > 0 else 0.0
        else:
            zscore = 0.0

        diffs = series.diff().dropna()
        streak = 0
        if len(diffs) > 0:
            last_sign = np.sign(diffs.iloc[-1])
            if last_sign != 0:
                for val in reversed(diffs.values):
                    if np.sign(val) == last_sign:
                        streak += 1
                    else:
                        break
                streak = int(streak * last_sign)

        if abs(velocity) < _STABLE_THRESHOLD:
            status = "stable"
        elif velocity > 0:
            status = "accelerating_up" if acceleration > 0 else "decelerating_up"
        else:
            status = "accelerating_down" if acceleration < 0 else "decelerating_down"

        alert = None
        if abs(zscore) >= _ZSCORE_ALERT_THRESHOLD:
            direction = "加速" if zscore > 0 else "减速"
            alert = f"异常{direction}，偏离均值 {abs(zscore):.1f} 个标准差"

        return {
            "velocity": round(velocity, 4),
            "acceleration": round(acceleration, 4),
            "zscore": round(zscore, 2),
            "streak": streak,
            "velocity_series": vel_series,
            "status": status,
            "status_cn": _STATUS_LABELS[status],
            "alert": alert,
        }

    @staticmethod
    def compute_batch(
        series_dict: Dict[str, pd.Series],
        velocity_window: int = 5,
        zscore_window: int = 60,
    ) -> Dict[str, dict]:
        return {
            name: MomentumDelta.compute(s, velocity_window, zscore_window)
            for name, s in series_dict.items()
        }
