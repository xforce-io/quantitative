#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stock Valuation Analyzer
个股估值分析器

从每日基本面数据（PE/PB/PS）计算历史分位数和估值状态标签。
"""

import pandas as pd
from typing import Dict, Any


class StockValuationAnalyzer:
    """个股估值分析器"""

    # 分位数 → 估值状态映射
    VALUATION_THRESHOLDS = [
        (20, '低估'),
        (40, '偏低'),
        (60, '中性'),
        (80, '偏高'),
    ]
    DEFAULT_STATUS = '高估'

    VALUATION_METRICS = ['pe_ttm', 'pb', 'ps_ttm']

    @classmethod
    def compute_percentile_valuation(cls, df: pd.DataFrame, days: int = 250) -> Dict[str, Any]:
        """
        计算估值百分位和状态标签

        Args:
            df: 包含 trade_date, pe_ttm, pb, ps_ttm 等列的每日基本面数据
            days: 用于计算分位数的最近交易日数

        Returns:
            Dict with:
            - latest: 最新估值指标
            - percentile: 历史分位数 (0-100, 越低越便宜)
            - status: 估值状态标签
            - history: 历史数据 DataFrame
            - data_days: 实际数据天数
        """
        if df is None or df.empty:
            return {'error': '无估值数据'}

        # 排序
        df = df.sort_values('trade_date', ascending=True).reset_index(drop=True)
        df['trade_date'] = pd.to_datetime(df['trade_date'])

        # 只取最近 N 个交易日
        df = df.tail(days)

        if len(df) == 0:
            return {'error': '数据不足'}

        # 最新数据
        latest = df.iloc[-1].to_dict()

        # 计算历史分位数 (越低越便宜)
        percentile = {}
        for col in cls.VALUATION_METRICS:
            if col in df.columns:
                valid_data = df[col].dropna()
                if len(valid_data) > 10:
                    current = latest.get(col)
                    if pd.notna(current):
                        percentile[col] = round(
                            (valid_data < current).sum() / len(valid_data) * 100, 1
                        )

        # 计算估值状态标签
        valuation_status = {}
        for col, pct in percentile.items():
            valuation_status[col] = cls._percentile_to_status(pct)

        return {
            'latest': {
                'pe': latest.get('pe'),
                'pe_ttm': latest.get('pe_ttm'),
                'pb': latest.get('pb'),
                'ps': latest.get('ps'),
                'ps_ttm': latest.get('ps_ttm'),
                'dv_ratio': latest.get('dv_ratio'),
                'total_mv': latest.get('total_mv'),
                'circ_mv': latest.get('circ_mv'),
                'close': latest.get('close'),
                'trade_date': latest.get('trade_date'),
            },
            'percentile': percentile,
            'status': valuation_status,
            'history': df,
            'data_days': len(df),
        }

    @classmethod
    def _percentile_to_status(cls, pct: float) -> str:
        """将分位数映射为估值状态标签"""
        for threshold, label in cls.VALUATION_THRESHOLDS:
            if pct < threshold:
                return label
        return cls.DEFAULT_STATUS
