#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Symbol Resolver
股票代码解析器

提供股票代码格式化、名称解析、最近交易日判断等纯逻辑功能。
不依赖 Streamlit，可在任何层复用。
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd


class SymbolResolver:
    """股票代码解析与格式化"""

    @staticmethod
    def format_symbol(code: str) -> str:
        """
        将纯数字代码转为带后缀格式: 300033 -> 300033.SZ

        Args:
            code: 股票代码（可能已含后缀）

        Returns:
            标准化代码
        """
        code = str(code).strip()
        if '.' in code:
            return code
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith('0') or code.startswith('3'):
            return f"{code}.SZ"
        elif code.startswith('8') or code.startswith('4'):
            return f"{code}.BJ"
        return code

    @staticmethod
    def resolve(query: str, stock_list: Optional[List[str]] = None) -> str:
        """
        将用户输入（名称/简称/代码）解析为标准股票代码

        Args:
            query: 用户输入（如 "002594.SZ"、"002594"、"比亚迪"）
            stock_list: 全量股票列表，格式 ["000001.SZ 平安银行", ...]

        Returns:
            标准股票代码，未找到则返回原值
        """
        query = query.strip()

        # 已是标准代码格式
        if '.' in query:
            suffix = query.split('.')[-1].upper()
            if suffix in ('SZ', 'SH', 'BJ', 'HK'):
                return query.upper()

        # 纯数字代码，补充后缀
        if query.isdigit() and len(query) == 6:
            return SymbolResolver.format_symbol(query)

        # 从股票列表搜索名称
        if stock_list:
            # 精确匹配
            for item in stock_list:
                parts = item.split(' ', 1)
                if len(parts) == 2 and query == parts[1]:
                    return parts[0]
            # 模糊匹配
            for item in stock_list:
                parts = item.split(' ', 1)
                if len(parts) == 2 and query in parts[1]:
                    return parts[0]

        return query

    @staticmethod
    def get_latest_trading_day() -> datetime:
        """
        获取最近的交易日（智能回溯）

        周末回溯到周五，盘前（15:00 之前）看前一天。
        """
        today = datetime.now()

        if today.weekday() >= 5:
            today = today - timedelta(days=(today.weekday() - 4))
        elif today.hour < 15:
            today = today - timedelta(days=1)

        return today


class IndustryMapper:
    """行业名称映射与模糊匹配"""

    # 候选池行业 → API 行业关键词列表
    INDUSTRY_MAPPING: Dict[str, List[str]] = {
        '交通运输': ['铁路公路', '航空机场', '物流行业', '船舶制造', '港口航运'],
        '家电零售': ['家电行业', '零售'],
        '计算机及软件': ['软件开发', '计算机设备', 'IT设备', '通信设备'],
        '汽车相关': ['汽车零部件', '汽车整车', '汽车服务'],
        '养殖农产品': ['养殖业', '农牧饲渔', '农业综合'],
        '食品饮料': ['食品饮料', '酿酒行业'],
        '医药': ['医药制造', '医疗器械', '中药', '生物制品', '化学制药'],
        '金融': ['银行', '保险', '证券', '多元金融'],
        '半导体': ['半导体', '电子元件'],
        '房地产': ['房地产', '房地产服务', '房地产开发'],
        '基建': ['工程建设', '建筑材料', '钢铁行业', '工程机械'],
        '资源': ['贵金属', '小金属', '有色金属', '采掘行业', '煤炭行业'],
        '能源': ['石油行业', '电力行业', '煤炭行业', '燃气'],
        '化工': ['化学制品', '化工行业', '化肥行业'],
        '军工': ['航天航空', '船舶制造', '国防军工'],
        '消费电子': ['消费电子', '电子元件'],
        '光伏': ['光伏设备', '电源设备'],
        '通信': ['通信设备', '通信服务'],
    }

    @classmethod
    def match_industry(cls, ind_name: str, df_agg: pd.DataFrame) -> pd.DataFrame:
        """
        智能匹配行业名称：直接包含 → 映射表 → 前两字匹配

        Args:
            ind_name: 候选池中的行业名称
            df_agg: 含 'name' 列的行业聚合 DataFrame

        Returns:
            匹配到的行
        """
        api_names = df_agg['name']

        # 1. 直接包含匹配
        matched = df_agg[api_names.str.contains(ind_name, na=False)]
        if not matched.empty:
            return matched

        # 2. 映射表匹配
        keywords = cls.INDUSTRY_MAPPING.get(ind_name, [])
        for kw in keywords:
            matched = df_agg[api_names.str.contains(kw, na=False)]
            if not matched.empty:
                return matched

        # 3. 前两字匹配
        if len(ind_name) >= 2:
            matched = df_agg[api_names.str.contains(ind_name[:2], na=False)]
            if not matched.empty:
                return matched

        return pd.DataFrame()
