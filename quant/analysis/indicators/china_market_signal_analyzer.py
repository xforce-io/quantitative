#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A股/港股市场信号分析器 (China & HK Market Signal Analyzer)

四维度监控:

| 维度       | 数据源                    | 预警条件                       | 权重 |
|-----------|--------------------------|-------------------------------|------|
| 北向资金   | Tushare moneyflow_hsgt   | 单日净流出>50亿 或 连续3日净流出  | 30%  |
| 两市成交额 | Tushare daily             | 低于8000亿(冷) / 超2万亿(热)    | 25%  |
| 融资融券   | Tushare margin            | 余额周变化>5% 或 急降           | 25%  |
| 南向资金   | Tushare moneyflow_hsgt   | 单日净流出>30亿 或 连续3日净流出  | 20%  |

状态输出: 积极(Bullish) / 中性(Neutral) / 谨慎(Cautious) / 防御(Defensive)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# 阈值配置
THRESHOLDS = {
    'north_outflow_single_day': -50,   # 北向单日净流出超50亿(百万元 → -5000)
    'north_consecutive_outflow': 3,     # 北向连续流出天数
    'south_outflow_single_day': -30,   # 南向单日净流出超30亿
    'south_consecutive_outflow': 3,
    'turnover_cold': 8000,              # 两市成交额冷淡线(亿元)
    'turnover_hot': 20000,              # 两市成交额过热线(亿元)
    'margin_weekly_change_pct': 5.0,    # 融资余额周变化超5%
}

DIMENSION_WEIGHTS = {
    'northbound': 0.30,
    'turnover': 0.25,
    'margin': 0.25,
    'southbound': 0.20,
}

STATUS_MAP = [
    (75, 'Defensive', '防御', '🔴'),
    (50, 'Cautious', '谨慎', '🟠'),
    (25, 'Neutral', '中性', '🟡'),
    (0, 'Bullish', '积极', '🟢'),
]


class ChinaMarketSignalAnalyzer:
    """
    A股/港股市场信号分析器

    监控北向资金、两市成交额、融资融券、南向资金，多条件触发预警。
    """

    def __init__(self):
        self._provider = None

    def _get_provider(self):
        """懒加载 TushareProvider"""
        if self._provider is None:
            from quant.data.implementations.tushare_provider import TushareProvider
            self._provider = TushareProvider()
        return self._provider

    def analyze(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        全量分析 A 股/港股市场信号

        Args:
            lookback_days: 回溯天数

        Returns:
            分析结果
        """
        signals = []
        dimension_scores = {}
        dimensions = {}

        # 1. 北向资金
        try:
            nb_result = self._fetch_northbound(lookback_days)
            dimensions['northbound'] = nb_result
            dimension_scores['northbound'] = nb_result.get('risk_score', 50)
            signals.extend(nb_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取北向资金数据失败: {e}")
            dimensions['northbound'] = {'error': str(e)}
            dimension_scores['northbound'] = 50

        # 2. 两市成交额
        try:
            tv_result = self._fetch_turnover(lookback_days)
            dimensions['turnover'] = tv_result
            dimension_scores['turnover'] = tv_result.get('risk_score', 50)
            signals.extend(tv_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取成交额数据失败: {e}")
            dimensions['turnover'] = {'error': str(e)}
            dimension_scores['turnover'] = 50

        # 3. 融资融券
        try:
            mg_result = self._fetch_margin(lookback_days)
            dimensions['margin'] = mg_result
            dimension_scores['margin'] = mg_result.get('risk_score', 50)
            signals.extend(mg_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取融资融券数据失败: {e}")
            dimensions['margin'] = {'error': str(e)}
            dimension_scores['margin'] = 50

        # 4. 南向资金
        try:
            sb_result = self._fetch_southbound(lookback_days)
            dimensions['southbound'] = sb_result
            dimension_scores['southbound'] = sb_result.get('risk_score', 50)
            signals.extend(sb_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取南向资金数据失败: {e}")
            dimensions['southbound'] = {'error': str(e)}
            dimension_scores['southbound'] = 50

        # 加权风险分数
        total_risk_score = sum(
            dimension_scores.get(dim, 50) * weight
            for dim, weight in DIMENSION_WEIGHTS.items()
        )
        total_risk_score = round(total_risk_score, 1)

        # 状态判定
        status_en, status_cn, status_icon = 'Neutral', '中性', '🟡'
        for threshold, en, cn, icon in STATUS_MAP:
            if total_risk_score >= threshold:
                status_en, status_cn, status_icon = en, cn, icon
                break

        return {
            'status': status_en,
            'status_cn': status_cn,
            'status_icon': status_icon,
            'risk_score': total_risk_score,
            'dimensions': dimensions,
            'dimension_scores': dimension_scores,
            'signals': signals,
            'thresholds': THRESHOLDS,
            'analyzed_at': datetime.now().isoformat(),
        }

    # ==================== 数据获取 ====================

    def _fetch_northbound(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        获取北向资金数据 (沪股通+深股通)

        北向 = hk2sh + hk2sz
        """
        provider = self._get_provider()
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=lookback_days + 10)).strftime('%Y%m%d')

        df = provider.get_hsgt_flow(start, end)

        if df is None or df.empty:
            return {'error': '北向资金数据为空', 'risk_score': 50}

        # 确保索引是日期
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df = df.set_index('trade_date')
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')

        df = df.sort_index()

        # 计算北向净流入 (百万元)
        north_net = None
        if 'north_money' in df.columns:
            north_net = df['north_money']
        elif 'hk2sh_net' in df.columns and 'hk2sz_net' in df.columns:
            north_net = df['hk2sh_net'] + df['hk2sz_net']
        elif 'hk2sh_buy' in df.columns:
            north_net = (df.get('hk2sh_buy', 0) - df.get('hk2sh_sell', 0) +
                        df.get('hk2sz_buy', 0) - df.get('hk2sz_sell', 0))

        if north_net is None or north_net.empty:
            return {'error': '无法计算北向净流入', 'risk_score': 50}

        # 确保数值类型
        north_net = pd.to_numeric(north_net, errors='coerce').dropna()
        if north_net.empty:
            return {'error': '北向净流入数据无有效数值', 'risk_score': 50}

        # 转为亿元
        north_net_yi = north_net / 100  # 百万→亿

        latest = float(north_net_yi.iloc[-1]) if len(north_net_yi) > 0 else 0
        recent_5 = north_net_yi.tail(5)
        recent_5_sum = float(recent_5.sum())
        consecutive_outflow = 0
        for val in reversed(north_net_yi.values):
            if val < 0:
                consecutive_outflow += 1
            else:
                break

        # 累计
        cumsum = north_net_yi.cumsum()

        # 风险评分
        risk_score = 0
        signals = []

        if latest < THRESHOLDS['north_outflow_single_day']:
            risk_score += 50
            signals.append(f'🔴 北向单日大幅流出 {latest:.1f}亿（阈值 {THRESHOLDS["north_outflow_single_day"]}亿）')
        elif latest < -20:
            risk_score += 30
            signals.append(f'🟠 北向净流出 {latest:.1f}亿')
        elif latest > 50:
            signals.append(f'🟢 北向大幅净流入 {latest:.1f}亿')
        else:
            signals.append(f'🟢 北向资金 {latest:+.1f}亿')

        if consecutive_outflow >= THRESHOLDS['north_consecutive_outflow']:
            risk_score += 40
            signals.append(f'🔴 北向连续 {consecutive_outflow} 日净流出')
        elif consecutive_outflow >= 2:
            risk_score += 15

        risk_score = min(risk_score, 100)

        series = pd.DataFrame({
            'north_net': north_net_yi,
            'north_cumsum': cumsum,
        })

        return {
            'latest': round(latest, 1),
            'recent_5d_sum': round(recent_5_sum, 1),
            'consecutive_outflow': consecutive_outflow,
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_turnover(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        获取两市成交额

        使用上证指数+深证成指的成交额合计
        """
        provider = self._get_provider()
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=lookback_days + 10)).strftime('%Y%m%d')

        # 获取上证和深证指数数据
        try:
            sh_df = provider.pro.index_daily(ts_code='000001.SH', start_date=start, end_date=end,
                                              fields='trade_date,amount')
            sz_df = provider.pro.index_daily(ts_code='399001.SZ', start_date=start, end_date=end,
                                              fields='trade_date,amount')
        except Exception as e:
            return {'error': f'获取指数数据失败: {e}', 'risk_score': 50}

        if sh_df is None or sh_df.empty or sz_df is None or sz_df.empty:
            return {'error': '指数成交额数据为空', 'risk_score': 50}

        sh_df['trade_date'] = pd.to_datetime(sh_df['trade_date'])
        sz_df['trade_date'] = pd.to_datetime(sz_df['trade_date'])

        merged = pd.merge(sh_df, sz_df, on='trade_date', suffixes=('_sh', '_sz'))
        merged = merged.sort_values('trade_date').set_index('trade_date')

        # amount 单位: 千元 → 亿元
        merged['total_amount'] = (merged['amount_sh'] + merged['amount_sz']) / 1e5

        latest = float(merged['total_amount'].iloc[-1])
        avg_20 = float(merged['total_amount'].tail(20).mean())
        avg_5 = float(merged['total_amount'].tail(5).mean())

        # 风险评分 (成交低迷 = 高风险)
        risk_score = 0
        signals = []

        if latest < THRESHOLDS['turnover_cold']:
            risk_score = 70
            signals.append(f'🔴 两市成交额萎缩至 {latest:.0f}亿（低于{THRESHOLDS["turnover_cold"]}亿冷淡线）')
        elif latest < 10000:
            risk_score = 40
            signals.append(f'🟠 两市成交额偏低 {latest:.0f}亿')
        elif latest > THRESHOLDS['turnover_hot']:
            risk_score = 30  # 过热也有风险
            signals.append(f'🟠 两市成交额过热 {latest:.0f}亿（超{THRESHOLDS["turnover_hot"]}亿）')
        else:
            risk_score = 10
            signals.append(f'🟢 两市成交额 {latest:.0f}亿（正常）')

        series = merged[['total_amount']].copy()

        return {
            'latest': round(latest, 0),
            'avg_5d': round(avg_5, 0),
            'avg_20d': round(avg_20, 0),
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_margin(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        获取融资融券数据

        Tushare: margin (exchange_id='SSE'/'SZSE')
        """
        provider = self._get_provider()
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=lookback_days + 10)).strftime('%Y%m%d')

        try:
            # 上交所 + 深交所
            sse = provider.pro.margin(exchange_id='SSE', start_date=start, end_date=end)
            szse = provider.pro.margin(exchange_id='SZSE', start_date=start, end_date=end)
        except Exception as e:
            return {'error': f'获取融资融券数据失败: {e}', 'risk_score': 50}

        frames = []
        for df in [sse, szse]:
            if df is not None and not df.empty:
                frames.append(df)

        if not frames:
            return {'error': '融资融券数据为空', 'risk_score': 50}

        combined = pd.concat(frames)
        combined['trade_date'] = pd.to_datetime(combined['trade_date'])

        # 按日期汇总 (rzye=融资余额, rqye=融券余额, rzmre=融资买入额)
        daily = combined.groupby('trade_date').agg({
            'rzye': 'sum',    # 融资余额
            'rqye': 'sum',    # 融券余额
            'rzmre': 'sum',   # 融资买入额
        }).sort_index()

        # 转为亿元
        daily['rzye_yi'] = daily['rzye'] / 1e8
        daily['rqye_yi'] = daily['rqye'] / 1e8
        daily['total_yi'] = daily['rzye_yi'] + daily['rqye_yi']

        latest_rz = float(daily['rzye_yi'].iloc[-1])
        latest_total = float(daily['total_yi'].iloc[-1])

        # 周变化
        if len(daily) >= 5:
            week_ago = float(daily['rzye_yi'].iloc[-5])
            weekly_change_pct = (latest_rz - week_ago) / week_ago * 100 if week_ago != 0 else 0
        else:
            weekly_change_pct = 0

        # 风险评分
        risk_score = 0
        signals = []

        if weekly_change_pct > THRESHOLDS['margin_weekly_change_pct']:
            risk_score = 40  # 杠杆急增，有过热风险
            signals.append(f'🟠 融资余额周增 {weekly_change_pct:.1f}%（杠杆上行）')
        elif weekly_change_pct < -THRESHOLDS['margin_weekly_change_pct']:
            risk_score = 70  # 杠杆急降，恐慌
            signals.append(f'🔴 融资余额周降 {weekly_change_pct:.1f}%（去杠杆信号）')
        elif weekly_change_pct < -2:
            risk_score = 40
            signals.append(f'🟠 融资余额小幅下降 {weekly_change_pct:.1f}%')
        else:
            risk_score = 10
            signals.append(f'🟢 融资余额稳定 {latest_rz:.0f}亿 (周变化{weekly_change_pct:+.1f}%)')

        series = daily[['rzye_yi', 'rqye_yi', 'total_yi']].copy()

        return {
            'rz_balance': round(latest_rz, 0),
            'total_balance': round(latest_total, 0),
            'weekly_change_pct': round(weekly_change_pct, 2),
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_southbound(self, lookback_days: int = 60) -> Dict[str, Any]:
        """
        获取南向资金数据 (港股通: sh2hk + sz2hk)
        """
        provider = self._get_provider()
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=lookback_days + 10)).strftime('%Y%m%d')

        df = provider.get_hsgt_flow(start, end)

        if df is None or df.empty:
            return {'error': '南向资金数据为空', 'risk_score': 50}

        if not isinstance(df.index, pd.DatetimeIndex):
            if 'trade_date' in df.columns:
                df['trade_date'] = pd.to_datetime(df['trade_date'])
                df = df.set_index('trade_date')
            elif 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')

        df = df.sort_index()

        # 南向净流入 (百万元)
        south_net = None
        if 'south_money' in df.columns:
            south_net = df['south_money']
        elif 'sh2hk_net' in df.columns and 'sz2hk_net' in df.columns:
            south_net = df['sh2hk_net'] + df['sz2hk_net']
        elif 'sh2hk_buy' in df.columns:
            south_net = (df.get('sh2hk_buy', 0) - df.get('sh2hk_sell', 0) +
                        df.get('sz2hk_buy', 0) - df.get('sz2hk_sell', 0))

        if south_net is None or south_net.empty:
            return {'error': '无法计算南向净流入', 'risk_score': 50}

        south_net_yi = south_net / 100  # 百万→亿

        latest = float(south_net_yi.iloc[-1]) if len(south_net_yi) > 0 else 0
        recent_5_sum = float(south_net_yi.tail(5).sum())
        consecutive_outflow = 0
        for val in reversed(south_net_yi.values):
            if val < 0:
                consecutive_outflow += 1
            else:
                break

        cumsum = south_net_yi.cumsum()

        # 风险评分
        risk_score = 0
        signals = []

        if latest < THRESHOLDS['south_outflow_single_day']:
            risk_score += 50
            signals.append(f'🔴 南向单日大幅流出 {latest:.1f}亿')
        elif latest < -10:
            risk_score += 25
            signals.append(f'🟠 南向净流出 {latest:.1f}亿')
        elif latest > 30:
            signals.append(f'🟢 南向大幅净流入 {latest:.1f}亿')
        else:
            signals.append(f'🟢 南向资金 {latest:+.1f}亿')

        if consecutive_outflow >= THRESHOLDS['south_consecutive_outflow']:
            risk_score += 40
            signals.append(f'🔴 南向连续 {consecutive_outflow} 日净流出')
        elif consecutive_outflow >= 2:
            risk_score += 15

        risk_score = min(risk_score, 100)

        series = pd.DataFrame({
            'south_net': south_net_yi,
            'south_cumsum': cumsum,
        })

        return {
            'latest': round(latest, 1),
            'recent_5d_sum': round(recent_5_sum, 1),
            'consecutive_outflow': consecutive_outflow,
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }
