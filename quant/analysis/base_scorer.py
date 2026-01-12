#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
评分器基类 (Base Scorer)

定义标准化评分接口，所有分析器可选择性实现此接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ScorerMixin:
    """
    评分器混入类

    提供标准化的 score() 接口，返回 0-100 的分数
    分析器可以通过继承此类来提供评分功能
    """

    def score(self, symbol: str, **kwargs) -> Optional[float]:
        """
        计算标的的标准化分数

        Args:
            symbol: 股票/ETF代码
            **kwargs: 额外参数

        Returns:
            0-100 的标准化分数，None 表示无法计算
        """
        raise NotImplementedError("子类需要实现 score() 方法")

    @staticmethod
    def normalize_score(value: float, min_val: float, max_val: float,
                        inverse: bool = False) -> float:
        """
        将原始值标准化到 0-100 范围

        Args:
            value: 原始值
            min_val: 最小值
            max_val: 最大值
            inverse: 是否反转（True 表示越小越好）

        Returns:
            0-100 的标准化分数
        """
        if max_val == min_val:
            return 50.0

        normalized = (value - min_val) / (max_val - min_val) * 100
        normalized = max(0, min(100, normalized))

        if inverse:
            normalized = 100 - normalized

        return normalized

    @staticmethod
    def percentile_score(value: float, values_list: list, inverse: bool = False) -> float:
        """
        计算百分位分数

        Args:
            value: 当前值
            values_list: 所有值的列表
            inverse: 是否反转

        Returns:
            0-100 的百分位分数
        """
        if not values_list:
            return 50.0

        count_below = sum(1 for v in values_list if v < value)
        percentile = count_below / len(values_list) * 100

        if inverse:
            percentile = 100 - percentile

        return percentile
