#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
宏观流动性监控分析器 (Macro Liquidity Analyzer)

八维度监控，每个维度有明确的触发阈值：

| 维度       | 数据源                             | 预警条件                          | 权重 |
|-----------|----------------------------------|----------------------------------|------|
| 净流动性   | FRED: WALCL - WTREGEN - RRPONTSYD | 单周下降 > 5%                     | 25%  |
| SOFR      | FRED: SOFR                        | 突破 5.5%                        | 12%  |
| MOVE指数   | Yahoo: ^MOVE                      | 超过 130                         | 12%  |
| 日元套利   | Yahoo: JPY=X + FRED: DGS2        | USD/JPY急跌+利差收窄               | 8%   |
| 黄金异动   | Yahoo: GC=F + DX-Y.NYB, FRED: DFII10 | 连跌3天/破MA20/RSI弱势/周跌>3%   | 8%   |
| 流动性趋势 | GlobalUsdLiquidityAnalyzer         | 百分位置信度转风险分               | 15%  |
| 铜金比率   | Yahoo: HG=F + GC=F               | 铜金比低百分位/急跌                | 10%  |
| 原油       | Yahoo: CL=F                       | 周涨>10%/暴跌>10%/高价位           | 10%  |

状态输出：充裕(Abundant) / 正常(Normal) / 偏紧(Tight) / 危机(Crisis)
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import yfinance as yf

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# 阈值配置
THRESHOLDS = {
    'net_liquidity_drop_pct': 5.0,     # 单周净流动性下降超 5%
    'sofr_high': 5.5,                   # SOFR 超过 5.5%
    'move_high': 130,                   # MOVE 指数超 130
    'yen_drop_weekly_pct': 3.0,        # USD/JPY 周跌幅超 3%
    'yield_spread_narrow': 1.0,         # 美日利差收窄至 1% 以下
    # Gold anomaly thresholds
    'gold_weekly_drop_pct': 3.0,
    'gold_weekly_drop_severe_pct': 5.0,
    'gold_consecutive_down_days': 3,
    'gold_rsi_weak': 40,
    'gold_usd_divergence_gold_drop': 2.0,
    'gold_usd_divergence_usd_max': 0.5,
    'real_yield_spike_bp': 30,
    'real_yield_spike_moderate_bp': 15,
    # Copper/Gold ratio thresholds
    'copper_gold_percentile_extreme': 10,
    'copper_gold_percentile_high': 20,
    'copper_gold_percentile_elevated': 40,
    'copper_gold_weekly_drop_pct': 5.0,
    # Crude oil thresholds
    'crude_weekly_surge_pct': 10.0,
    'crude_weekly_rise_pct': 5.0,
    'crude_weekly_crash_pct': 10.0,
    'crude_high_price': 100,
    'crude_elevated_price': 90,
}

# 维度权重
DIMENSION_WEIGHTS = {
    'net_liquidity': 0.25,
    'sofr': 0.12,
    'move': 0.12,
    'yen_carry': 0.08,
    'gold': 0.08,
    'liquidity_trend': 0.15,
    'copper_gold': 0.10,
    'crude_oil': 0.10,
}

# 状态映射 (基于风险分数)
STATUS_MAP = [
    (75, 'Crisis', '危机', '🔴'),
    (50, 'Tight', '偏紧', '🟠'),
    (25, 'Normal', '正常', '🟡'),
    (0, 'Abundant', '充裕', '🟢'),
]


class MacroLiquidityAnalyzer:
    """
    宏观流动性监控分析器

    监控美联储资产负债表净流动性、SOFR、MOVE指数和日元套利交易，
    多条件触发预警。
    """

    def __init__(self, fred_api_key: Optional[str] = None):
        """
        初始化分析器

        Args:
            fred_api_key: FRED API Key，不传则从环境变量 FRED_API_KEY 读取
        """
        self._fred = None
        self._fred_api_key = fred_api_key

    def _get_fred(self):
        """懒加载 FRED 客户端"""
        if self._fred is None:
            from fredapi import Fred
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = self._fred_api_key or os.environ.get('FRED_API_KEY')
            if not api_key:
                raise ValueError(
                    "需要 FRED API Key，请设置环境变量 FRED_API_KEY 或传入参数。"
                    "免费申请: https://fred.stlouisfed.org/docs/api/api_key.html"
                )
            self._fred = Fred(api_key=api_key)
        return self._fred

    def analyze(
        self,
        lookback_days: int = 365,
        liquidity_confidence: Optional[float] = None,
        liquidity_velocity: Optional[float] = None,
        liquidity_acceleration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        全量分析宏观流动性状态

        Args:
            lookback_days: 回溯天数（用于趋势图表）

        Returns:
            分析结果字典，包含四个维度的数据 + 时间序列 + 触发信号列表
        """
        signals = []
        dimension_scores = {}  # 每个维度的风险分数 (0=安全, 100=危险)
        dimensions = {}

        # 1. 净流动性
        try:
            nl_result = self._fetch_net_liquidity(lookback_days)
            dimensions['net_liquidity'] = nl_result
            dimension_scores['net_liquidity'] = nl_result.get('risk_score', 50)
            signals.extend(nl_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取净流动性数据失败: {e}")
            dimensions['net_liquidity'] = {'error': str(e)}
            dimension_scores['net_liquidity'] = 50

        # 2. SOFR
        try:
            sofr_result = self._fetch_sofr(lookback_days)
            dimensions['sofr'] = sofr_result
            dimension_scores['sofr'] = sofr_result.get('risk_score', 50)
            signals.extend(sofr_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取 SOFR 数据失败: {e}")
            dimensions['sofr'] = {'error': str(e)}
            dimension_scores['sofr'] = 50

        # 3. MOVE 指数
        try:
            move_result = self._fetch_move_index(lookback_days)
            dimensions['move'] = move_result
            dimension_scores['move'] = move_result.get('risk_score', 50)
            signals.extend(move_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取 MOVE 指数失败: {e}")
            dimensions['move'] = {'error': str(e)}
            dimension_scores['move'] = 50

        # 4. 日元套利
        try:
            yen_result = self._fetch_yen_carry(lookback_days)
            dimensions['yen_carry'] = yen_result
            dimension_scores['yen_carry'] = yen_result.get('risk_score', 50)
            signals.extend(yen_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取日元套利数据失败: {e}")
            dimensions['yen_carry'] = {'error': str(e)}
            dimension_scores['yen_carry'] = 50

        # 5. 黄金异动
        try:
            gold_result = self._fetch_gold_anomaly(lookback_days)
            dimensions['gold'] = gold_result
            dimension_scores['gold'] = gold_result.get('risk_score', 50)
            signals.extend(gold_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取黄金异动数据失败: {e}")
            dimensions['gold'] = {'error': str(e)}
            dimension_scores['gold'] = 50

        # 6. 流动性趋势（全球美元流动性置信度）
        try:
            trend_result = self._fetch_liquidity_trend(
                liquidity_confidence, liquidity_velocity, liquidity_acceleration,
            )
            dimensions['liquidity_trend'] = trend_result
            dimension_scores['liquidity_trend'] = trend_result.get('risk_score', 50)
            signals.extend(trend_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取流动性趋势数据失败: {e}")
            dimensions['liquidity_trend'] = {'error': str(e)}
            dimension_scores['liquidity_trend'] = 50

        # 7. 铜金比率
        try:
            copper_gold_result = self._fetch_copper_gold_ratio(lookback_days)
            dimensions['copper_gold'] = copper_gold_result
            dimension_scores['copper_gold'] = copper_gold_result.get('risk_score', 50)
            signals.extend(copper_gold_result.get('signals', []))
        except Exception as e:
            logger.error(f"获取铜金比率数据失败: {e}")
            dimensions['copper_gold'] = {'error': str(e)}
            dimension_scores['copper_gold'] = 50

        # 加权风险分数
        total_risk_score = sum(
            dimension_scores.get(dim, 50) * weight
            for dim, weight in DIMENSION_WEIGHTS.items()
        )
        total_risk_score = round(total_risk_score, 1)

        # 状态判定
        status_en, status_cn, status_icon = 'Normal', '正常', '🟡'
        for threshold, en, cn, icon in STATUS_MAP:
            if total_risk_score >= threshold:
                status_en, status_cn, status_icon = en, cn, icon
                break

        # 合并所有时间序列
        series = self._merge_series(dimensions)

        return {
            'status': status_en,
            'status_cn': status_cn,
            'status_icon': status_icon,
            'risk_score': total_risk_score,
            'dimensions': dimensions,
            'dimension_scores': dimension_scores,
            'signals': signals,
            'series': series,
            'thresholds': THRESHOLDS,
            'analyzed_at': datetime.now().isoformat(),
        }

    # ==================== 数据获取 ====================

    def _fetch_net_liquidity(self, lookback_days: int = 365) -> Dict[str, Any]:
        """
        获取净流动性数据

        净流动性 = Fed 总资产 (WALCL) - 财政部一般账户 (WTREGEN) - 隔夜逆回购 (RRPONTSYD)
        """
        fred = self._get_fred()
        start = datetime.now() - timedelta(days=lookback_days + 30)

        # 获取三个序列
        walcl = fred.get_series('WALCL', observation_start=start)    # Fed 总资产 (周频)
        tga = fred.get_series('WTREGEN', observation_start=start)     # 财政部一般账户 (周频)
        rrp = fred.get_series('RRPONTSYD', observation_start=start)   # 隔夜逆回购 (日频)

        # 对齐到日频并前向填充
        df = pd.DataFrame({
            'walcl': walcl,
            'tga': tga,
            'rrp': rrp,
        })
        df = df.asfreq('D').ffill()
        df = df.dropna()

        if df.empty:
            return {'error': '净流动性数据为空', 'risk_score': 50}

        # 计算净流动性 (百万美元)
        df['net_liquidity'] = df['walcl'] - df['tga'] - df['rrp']

        # 取最近数据
        latest = df.iloc[-1]
        net_liq = latest['net_liquidity']

        # 周变化
        if len(df) >= 7:
            week_ago = df.iloc[-7]['net_liquidity']
            weekly_change_pct = (net_liq - week_ago) / abs(week_ago) * 100 if week_ago != 0 else 0
        else:
            weekly_change_pct = 0

        # 风险评分
        risk_score = 0
        signals = []

        if weekly_change_pct < -THRESHOLDS['net_liquidity_drop_pct']:
            risk_score = 90
            signals.append(f'🔴 净流动性单周暴跌 {weekly_change_pct:.1f}%（阈值 -{THRESHOLDS["net_liquidity_drop_pct"]}%）')
        elif weekly_change_pct < -2:
            risk_score = 60
            signals.append(f'🟠 净流动性周降 {weekly_change_pct:.1f}%')
        elif weekly_change_pct < 0:
            risk_score = 30
        else:
            risk_score = 10
            signals.append(f'🟢 净流动性稳定/增长 ({weekly_change_pct:+.1f}%)')

        # 截取到回溯期
        cutoff = datetime.now() - timedelta(days=lookback_days)
        series = df[df.index >= cutoff][['net_liquidity']].copy()

        return {
            'current': round(net_liq / 1e6, 2),  # 转为万亿
            'current_raw': net_liq,
            'weekly_change_pct': round(weekly_change_pct, 2),
            'components': {
                'fed_assets': round(latest['walcl'] / 1e6, 2),
                'tga': round(latest['tga'] / 1e6, 2),
                'rrp': round(latest['rrp'] / 1e6, 2),
            },
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_sofr(self, lookback_days: int = 365) -> Dict[str, Any]:
        """获取 SOFR 利率数据"""
        fred = self._get_fred()
        start = datetime.now() - timedelta(days=lookback_days + 30)

        sofr = fred.get_series('SOFR', observation_start=start)

        if sofr is None or sofr.empty:
            return {'error': 'SOFR 数据为空', 'risk_score': 50}

        sofr = sofr.dropna()
        current_sofr = float(sofr.iloc[-1])

        # 风险评分
        risk_score = 0
        signals = []

        if current_sofr >= THRESHOLDS['sofr_high']:
            risk_score = 80
            signals.append(f'🔴 SOFR 突破 {THRESHOLDS["sofr_high"]}%（当前 {current_sofr:.2f}%）')
        elif current_sofr >= 5.0:
            risk_score = 50
            signals.append(f'🟠 SOFR 偏高 ({current_sofr:.2f}%)')
        elif current_sofr >= 4.0:
            risk_score = 25
        else:
            risk_score = 10
            signals.append(f'🟢 SOFR 水平正常 ({current_sofr:.2f}%)')

        cutoff = datetime.now() - timedelta(days=lookback_days)
        series = sofr[sofr.index >= cutoff].to_frame(name='sofr')

        return {
            'current': current_sofr,
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_move_index(self, lookback_days: int = 365) -> Dict[str, Any]:
        """获取 MOVE 指数（债市波动率指数）"""
        end = datetime.now()
        start = end - timedelta(days=lookback_days + 30)

        move = yf.download('^MOVE', start=start, end=end, progress=False)

        if move is None or move.empty:
            return {'error': 'MOVE 指数数据为空', 'risk_score': 50}

        # 处理多级列索引
        if isinstance(move.columns, pd.MultiIndex):
            move.columns = move.columns.get_level_values(0)

        close_col = 'Close' if 'Close' in move.columns else 'close'
        if close_col not in move.columns:
            return {'error': 'MOVE 数据缺少 Close 列', 'risk_score': 50}

        current_move = float(move[close_col].iloc[-1])

        # 风险评分
        risk_score = 0
        signals = []

        if current_move >= THRESHOLDS['move_high']:
            risk_score = 80
            signals.append(f'🔴 MOVE 指数超 {THRESHOLDS["move_high"]}（当前 {current_move:.1f}）')
        elif current_move >= 110:
            risk_score = 50
            signals.append(f'🟠 MOVE 指数偏高 ({current_move:.1f})')
        elif current_move >= 90:
            risk_score = 25
        else:
            risk_score = 10
            signals.append(f'🟢 MOVE 指数平稳 ({current_move:.1f})')

        cutoff = end - timedelta(days=lookback_days)
        series = move[move.index >= cutoff][[close_col]].copy()
        series.columns = ['move']

        return {
            'current': round(current_move, 1),
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    def _fetch_yen_carry(self, lookback_days: int = 365) -> Dict[str, Any]:
        """
        获取日元套利交易数据

        监控 USD/JPY 汇率 + 美日利差 (US 2Y - JP 2Y)
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_days + 30)

        # USD/JPY 汇率
        usdjpy = yf.download('JPY=X', start=start, end=end, progress=False)

        if usdjpy is None or usdjpy.empty:
            return {'error': 'USD/JPY 数据为空', 'risk_score': 50}

        if isinstance(usdjpy.columns, pd.MultiIndex):
            usdjpy.columns = usdjpy.columns.get_level_values(0)

        close_col = 'Close' if 'Close' in usdjpy.columns else 'close'
        usdjpy_series = usdjpy[close_col]
        current_usdjpy = float(usdjpy_series.iloc[-1])

        # 周变化
        if len(usdjpy_series) >= 5:
            week_ago_jpy = float(usdjpy_series.iloc[-5])
            jpy_weekly_change = (current_usdjpy - week_ago_jpy) / week_ago_jpy * 100
        else:
            jpy_weekly_change = 0

        # 美国 2 年期国债收益率 (FRED)
        us_2y = None
        yield_spread = None
        try:
            fred = self._get_fred()
            dgs2 = fred.get_series('DGS2', observation_start=start)
            if dgs2 is not None and not dgs2.empty:
                dgs2 = dgs2.dropna()
                us_2y = float(dgs2.iloc[-1])
                # 日本 2Y 近似 0，利差 ≈ US 2Y
                yield_spread = us_2y
        except Exception as e:
            logger.warning(f"获取 DGS2 失败: {e}")

        # 风险评分
        risk_score = 0
        signals = []

        # USD/JPY 急跌 = 日元升值 = 套利平仓压力
        if jpy_weekly_change < -THRESHOLDS['yen_drop_weekly_pct']:
            risk_score += 50
            signals.append(f'🔴 USD/JPY 周跌 {jpy_weekly_change:.1f}%（日元套利平仓风险）')
        elif jpy_weekly_change < -1:
            risk_score += 25
            signals.append(f'🟠 USD/JPY 走弱 ({jpy_weekly_change:+.1f}%)')
        else:
            signals.append(f'🟢 USD/JPY 稳定 ({current_usdjpy:.1f}, 周变化{jpy_weekly_change:+.1f}%)')

        # 利差收窄
        if yield_spread is not None:
            if yield_spread < THRESHOLDS['yield_spread_narrow']:
                risk_score += 40
                signals.append(f'🔴 美日利差收窄至 {yield_spread:.2f}%（套利动机减弱）')
            elif yield_spread < 2.0:
                risk_score += 20
                signals.append(f'🟠 美日利差 {yield_spread:.2f}%')
            else:
                signals.append(f'🟢 美日利差充足 ({yield_spread:.2f}%)')

        risk_score = min(risk_score, 100)

        # 构建时间序列
        cutoff = end - timedelta(days=lookback_days)
        jpy_df = usdjpy[usdjpy.index >= cutoff][[close_col]].copy()
        jpy_df.columns = ['usdjpy']

        series = jpy_df
        if us_2y is not None:
            try:
                spread_df = dgs2[dgs2.index >= cutoff].to_frame(name='yield_spread')
                series = jpy_df.join(spread_df, how='outer').ffill()
            except Exception:
                pass

        return {
            'current_usdjpy': round(current_usdjpy, 2),
            'jpy_weekly_change': round(jpy_weekly_change, 2),
            'us_2y': round(us_2y, 2) if us_2y is not None else None,
            'yield_spread': round(yield_spread, 2) if yield_spread is not None else None,
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    # ==================== 黄金异动早期预警层 ====================

    @staticmethod
    def _calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI using Wilder smoothing."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta.where(delta < 0, 0.0))
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calc_early_warning(self, gold_close: pd.Series) -> dict:
        """
        Calculate early warning layer (max 40 points).

        Signals:
        - Consecutive down days >= 3: +15
        - First MA20 crossover (close drops below MA20): +15
        - RSI(14) < 40: +10
        """
        score = 0
        result = {
            'consecutive_down': False,
            'below_ma20': False,
            'rsi_weak': False,
            'triple_resonance': False,
            'consecutive_down_days': 0,
            'rsi': None,
            'score': 0,
        }

        if len(gold_close) < 22:
            return result

        # 1. Consecutive down days
        daily_ret = gold_close.pct_change()
        streak = 0
        for ret in reversed(daily_ret.dropna().values):
            if ret < 0:
                streak += 1
            else:
                break
        result['consecutive_down_days'] = streak
        if streak >= THRESHOLDS['gold_consecutive_down_days']:
            result['consecutive_down'] = True
            score += 15

        # 2. MA20 crossover (first-cross only)
        ma20 = gold_close.rolling(20).mean()
        if len(gold_close) >= 22 and not pd.isna(ma20.iloc[-1]) and not pd.isna(ma20.iloc[-2]):
            today_below = gold_close.iloc[-1] < ma20.iloc[-1]
            yesterday_above = gold_close.iloc[-2] >= ma20.iloc[-2]
            if today_below and yesterday_above:
                result['below_ma20'] = True
                score += 15

        # 3. RSI
        rsi = self._calc_rsi(gold_close)
        current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
        result['rsi'] = round(current_rsi, 1) if current_rsi is not None else None
        if current_rsi is not None and current_rsi < THRESHOLDS['gold_rsi_weak']:
            result['rsi_weak'] = True
            score += 10

        # Triple resonance
        if result['consecutive_down'] and result['below_ma20'] and result['rsi_weak']:
            result['triple_resonance'] = True

        result['score'] = min(score, 40)
        return result

    def _calc_confirmation(
        self,
        gold_weekly_change_pct: float,
        usd_weekly_change_pct: 'float | None',
        real_yield_weekly_change_bp: 'float | None',
    ) -> dict:
        """
        Calculate confirmation layer (max 60 points).

        Signals:
        - Weekly gold drop: >5% → 40, >3% → 25, >1% → 10
        - Gold-USD divergence: gold down >2% + USD <+0.5% → +10
        - Real yield spike: >30bp → +10, >15bp → +5
        """
        score = 0
        result = {
            'weekly_drop': False,
            'gold_usd_divergence': False,
            'real_rate_spike': False,
            'score': 0,
        }

        # 1. Weekly gold drop
        if gold_weekly_change_pct < -THRESHOLDS['gold_weekly_drop_severe_pct']:
            result['weekly_drop'] = True
            score += 40
        elif gold_weekly_change_pct <= -THRESHOLDS['gold_weekly_drop_pct']:
            result['weekly_drop'] = True
            score += 25
        elif gold_weekly_change_pct < -1.0:
            score += 10

        # 2. Gold-USD divergence
        if (
            usd_weekly_change_pct is not None
            and gold_weekly_change_pct < -THRESHOLDS['gold_usd_divergence_gold_drop']
            and usd_weekly_change_pct < THRESHOLDS['gold_usd_divergence_usd_max']
        ):
            result['gold_usd_divergence'] = True
            score += 10

        # 3. Real yield spike
        if real_yield_weekly_change_bp is not None:
            if real_yield_weekly_change_bp > THRESHOLDS['real_yield_spike_bp']:
                result['real_rate_spike'] = True
                score += 10
            elif real_yield_weekly_change_bp > THRESHOLDS['real_yield_spike_moderate_bp']:
                result['real_rate_spike'] = True
                score += 5

        result['score'] = min(score, 60)
        return result

    def _fetch_gold_anomaly(self, lookback_days: int = 365) -> Dict[str, Any]:
        """
        Fetch gold anomaly data and calculate dual-layer risk score.

        Data sources:
        - GC=F (COMEX gold futures) via Yahoo Finance
        - DX-Y.NYB (USD index) via Yahoo Finance
        - DFII10 (10Y TIPS real yield) via FRED
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_days + 60)

        # === Gold price (required) ===
        gold = yf.download('GC=F', start=start, end=end, progress=False)
        if gold is None or gold.empty:
            return {'error': '黄金数据为空', 'risk_score': 50}

        if isinstance(gold.columns, pd.MultiIndex):
            gold.columns = gold.columns.get_level_values(0)

        close_col = 'Close' if 'Close' in gold.columns else 'close'
        if close_col not in gold.columns:
            return {'error': '黄金数据缺少 Close 列', 'risk_score': 50}

        gold_close = gold[close_col].dropna()
        if len(gold_close) < 25:
            return {'error': '黄金数据不足', 'risk_score': 50}

        current_price = float(gold_close.iloc[-1])
        ma20 = gold_close.rolling(20).mean()
        current_ma20 = float(ma20.iloc[-1]) if not pd.isna(ma20.iloc[-1]) else None

        # Weekly change (5 trading days)
        gold_weekly_change_pct = (
            (gold_close.iloc[-1] - gold_close.iloc[-5]) / gold_close.iloc[-5] * 100
            if len(gold_close) >= 5 else 0
        )

        # === USD index (optional) ===
        usd_weekly_change_pct = None
        usd_current = None
        try:
            usd = yf.download('DX-Y.NYB', start=start, end=end, progress=False)
            if usd is not None and not usd.empty:
                if isinstance(usd.columns, pd.MultiIndex):
                    usd.columns = usd.columns.get_level_values(0)
                usd_col = 'Close' if 'Close' in usd.columns else 'close'
                if usd_col in usd.columns:
                    usd_close = usd[usd_col].dropna()
                    if len(usd_close) >= 5:
                        usd_current = float(usd_close.iloc[-1])
                        usd_weekly_change_pct = (
                            (usd_close.iloc[-1] - usd_close.iloc[-5]) / usd_close.iloc[-5] * 100
                        )
        except Exception as e:
            logger.warning(f"获取美元指数失败: {e}")

        # === Real yield (optional) ===
        real_yield = None
        real_yield_weekly_change_bp = None
        try:
            fred = self._get_fred()
            tips = fred.get_series('DFII10', observation_start=start)
            if tips is not None and not tips.empty:
                tips = tips.dropna()
                if len(tips) >= 5:
                    real_yield = float(tips.iloc[-1])
                    real_yield_weekly_change_bp = (tips.iloc[-1] - tips.iloc[-5]) * 100
        except Exception as e:
            logger.warning(f"获取 TIPS 实际利率失败: {e}")

        # === Scoring ===
        early_warning = self._calc_early_warning(gold_close)
        confirmation = self._calc_confirmation(
            gold_weekly_change_pct=gold_weekly_change_pct,
            usd_weekly_change_pct=usd_weekly_change_pct,
            real_yield_weekly_change_bp=real_yield_weekly_change_bp,
        )
        risk_score = min(early_warning['score'] + confirmation['score'], 100)

        # === Signal messages ===
        signals = []

        if early_warning['triple_resonance']:
            signals.append(
                f'🔴 黄金三重前兆共振：连跌{early_warning["consecutive_down_days"]}天'
                f'+破MA20+RSI弱势({early_warning["rsi"]})，高度警惕'
            )
        else:
            if early_warning['consecutive_down']:
                cum_ret = (gold_close.iloc[-1] / gold_close.iloc[-early_warning['consecutive_down_days']] - 1) * 100
                signals.append(
                    f'🟠 黄金连跌{early_warning["consecutive_down_days"]}天'
                    f' (累计{cum_ret:.1f}%)，趋势转弱'
                )
            if early_warning['below_ma20']:
                signals.append(
                    f'🟠 黄金跌破20日均线 ({current_price:.0f} < MA20 {current_ma20:.0f})'
                )
            if early_warning['rsi_weak']:
                signals.append(f'🟠 黄金RSI跌入弱势区间 ({early_warning["rsi"]})')

        if confirmation['weekly_drop']:
            if gold_weekly_change_pct < -THRESHOLDS['gold_weekly_drop_severe_pct']:
                signals.append(f'🔴 黄金周暴跌 {gold_weekly_change_pct:.1f}%（阈值 -{THRESHOLDS["gold_weekly_drop_pct"]}%）')
            else:
                signals.append(f'🟠 黄金周跌 {gold_weekly_change_pct:.1f}%')

        if confirmation['gold_usd_divergence']:
            signals.append('🔴 黄金-美元背离：金跌但美元未涨，非美元驱动的抛售')

        if confirmation['real_rate_spike']:
            signals.append(f'🟠 实际利率周升{real_yield_weekly_change_bp:.0f}bp，压制黄金')

        # Data staleness check
        latest_date = gold_close.index[-1]
        days_stale = (datetime.now() - latest_date.to_pydatetime().replace(tzinfo=None)).days
        if days_stale > 3:
            signals.append(f'⚠️ 黄金数据延迟 {days_stale} 天（最新: {latest_date.strftime("%m-%d")}）')

        if not signals:
            signals.append(f'🟢 黄金走势平稳 (${current_price:.0f}, 周变化{gold_weekly_change_pct:+.1f}%)')

        # === Time series ===
        cutoff = end - timedelta(days=lookback_days)
        gold_df = gold_close[gold_close.index >= cutoff].to_frame(name='gold_price')
        gold_df['gold_ma20'] = ma20[ma20.index >= cutoff]

        series = gold_df
        if usd_current is not None:
            try:
                usd_series = usd[usd_col][usd[usd_col].index >= cutoff].to_frame(name='usd_index')
                series = gold_df.join(usd_series, how='outer').ffill()
            except Exception:
                pass

        return {
            'current_price': round(current_price, 2),
            'weekly_change_pct': round(gold_weekly_change_pct, 2),
            'consecutive_down_days': early_warning['consecutive_down_days'],
            'ma20': round(current_ma20, 2) if current_ma20 else None,
            'rsi': early_warning['rsi'],
            'usd_index': round(usd_current, 2) if usd_current else None,
            'usd_weekly_change_pct': round(usd_weekly_change_pct, 2) if usd_weekly_change_pct is not None else None,
            'real_yield': round(real_yield, 2) if real_yield is not None else None,
            'real_yield_weekly_change': round(real_yield_weekly_change_bp, 1) if real_yield_weekly_change_bp is not None else None,
            'early_warning': early_warning,
            'confirmation': confirmation,
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    # ==================== 铜金比率 ====================

    def _fetch_copper_gold_ratio(self, lookback_days: int = 365) -> Dict[str, Any]:
        """
        获取铜金比率数据，作为经济周期与流动性压力的前瞻指标。

        铜金比 = 铜价 (HG=F) / 金价 (GC=F)
        低比率（历史低百分位）预示经济下行压力和流动性收紧。

        Data sources:
        - HG=F (COMEX copper futures) via Yahoo Finance
        - GC=F (COMEX gold futures) via Yahoo Finance
        """
        end = datetime.now()
        start = end - timedelta(days=lookback_days + 60)

        # === Copper price ===
        copper = yf.download('HG=F', start=start, end=end, progress=False)
        if copper is None or copper.empty:
            return {'error': '铜价数据为空', 'risk_score': 50, 'signals': [], 'series': None}

        if isinstance(copper.columns, pd.MultiIndex):
            copper.columns = copper.columns.get_level_values(0)

        copper_col = 'Close' if 'Close' in copper.columns else 'close'
        if copper_col not in copper.columns:
            return {'error': '铜价数据缺少 Close 列', 'risk_score': 50, 'signals': [], 'series': None}

        copper_close = copper[copper_col].dropna()
        if len(copper_close) < 10:
            return {'error': '铜价数据不足', 'risk_score': 50, 'signals': [], 'series': None}

        # === Gold price ===
        gold = yf.download('GC=F', start=start, end=end, progress=False)
        if gold is None or gold.empty:
            return {'error': '黄金数据为空（铜金比）', 'risk_score': 50, 'signals': [], 'series': None}

        if isinstance(gold.columns, pd.MultiIndex):
            gold.columns = gold.columns.get_level_values(0)

        gold_col = 'Close' if 'Close' in gold.columns else 'close'
        if gold_col not in gold.columns:
            return {'error': '黄金数据缺少 Close 列（铜金比）', 'risk_score': 50, 'signals': [], 'series': None}

        gold_close = gold[gold_col].dropna()
        if len(gold_close) < 10:
            return {'error': '黄金数据不足（铜金比）', 'risk_score': 50, 'signals': [], 'series': None}

        # === Compute ratio ===
        # Align on common dates
        ratio_series = (copper_close / gold_close).dropna()
        if ratio_series.empty:
            return {'error': '铜金比数据对齐后为空', 'risk_score': 50, 'signals': [], 'series': None}

        # 60-day rolling percentile
        window = min(60, len(ratio_series))
        current_ratio = float(ratio_series.iloc[-1])
        rolling_window = ratio_series.iloc[-window:]
        rank = (rolling_window < current_ratio).sum()
        percentile = float(rank) / len(rolling_window) * 100

        # Weekly change (5 trading days)
        if len(ratio_series) >= 5:
            weekly_change_pct = float(
                (ratio_series.iloc[-1] - ratio_series.iloc[-5]) / ratio_series.iloc[-5] * 100
            )
        else:
            weekly_change_pct = 0.0

        # === Risk scoring ===
        if percentile < THRESHOLDS['copper_gold_percentile_extreme']:
            risk_score = 90
        elif percentile < THRESHOLDS['copper_gold_percentile_high']:
            risk_score = 70
        elif percentile < THRESHOLDS['copper_gold_percentile_elevated']:
            risk_score = 45
        else:
            risk_score = 15

        # Weekly drop bonus
        if weekly_change_pct < -THRESHOLDS['copper_gold_weekly_drop_pct']:
            risk_score = min(risk_score + 15, 100)

        # === Signals ===
        signals = []
        if percentile < THRESHOLDS['copper_gold_percentile_extreme']:
            signals.append(
                f'🔴 铜金比处于历史极低百分位 ({percentile:.1f}%)，经济下行压力严重'
            )
        elif percentile < THRESHOLDS['copper_gold_percentile_high']:
            signals.append(
                f'🟠 铜金比偏低 (百分位 {percentile:.1f}%)，经济预期走弱'
            )
        elif percentile < THRESHOLDS['copper_gold_percentile_elevated']:
            signals.append(
                f'🟡 铜金比低于历史中位 (百分位 {percentile:.1f}%)'
            )
        else:
            signals.append(
                f'🟢 铜金比正常 (百分位 {percentile:.1f}%, 当前 {current_ratio:.4f})'
            )

        if weekly_change_pct < -THRESHOLDS['copper_gold_weekly_drop_pct']:
            signals.append(
                f'🔴 铜金比周跌 {weekly_change_pct:.1f}%，铜价相对黄金快速下滑'
            )

        # === Time series ===
        cutoff = end - timedelta(days=lookback_days)
        series = ratio_series[ratio_series.index >= cutoff].to_frame(name='copper_gold_ratio')

        return {
            'ratio': round(current_ratio, 6),
            'percentile': round(percentile, 1),
            'weekly_change_pct': round(weekly_change_pct, 2),
            'risk_score': risk_score,
            'signals': signals,
            'series': series,
        }

    # ==================== 流动性趋势 ====================

    def _fetch_liquidity_trend(
        self,
        precomputed_confidence: Optional[float] = None,
        precomputed_velocity: Optional[float] = None,
        precomputed_acceleration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        获取全球美元流动性置信度 + 导数，映射为风险分数。

        基础分: risk = 50 - confidence / 2
        导数调整:
          - 一阶导 < -5 → +15, < -2 → +10
          - 一阶导 > 0  → -5 (改善减分)
          - 二阶导 < -2 → +10 (恶化加速), < 0 → +5
        """
        wow_change = None
        velocity = precomputed_velocity
        acceleration = precomputed_acceleration

        if precomputed_confidence is not None:
            confidence = precomputed_confidence
        else:
            from quant.analysis.indicators.global_usd_liquidity import (
                GlobalUsdLiquidityAnalyzer,
            )
            analyzer = GlobalUsdLiquidityAnalyzer(fred_api_key=self._fred_api_key)
            result = analyzer.analyze()
            confidence = result.get('confidence')
            wow_change = result.get('wow_change')
            velocity = result.get('velocity')
            acceleration = result.get('acceleration')

        if confidence is None:
            return {'error': '流动性置信度不可用', 'risk_score': 50}

        # 基础分: 置信度 → 风险分 (-100→100, 0→50, +100→0)
        base_risk = 50 - confidence / 2

        # 一阶导调整
        velocity_adj = 0
        if velocity is not None:
            if velocity < -5:
                velocity_adj = 15
            elif velocity < -2:
                velocity_adj = 10
            elif velocity > 0:
                velocity_adj = -5

        # 二阶导调整
        acceleration_adj = 0
        if acceleration is not None:
            if acceleration < -2:
                acceleration_adj = 10
            elif acceleration < 0:
                acceleration_adj = 5

        risk_score = max(0, min(100, round(base_risk + velocity_adj + acceleration_adj)))

        # 信号生成
        signals = []
        if confidence <= -50:
            signals.append(f'🔴 流动性趋势显著收紧（置信度 {confidence:+.1f}%）')
        elif confidence <= -20:
            signals.append(f'🟠 流动性趋势偏紧（置信度 {confidence:+.1f}%）')
        elif confidence <= 20:
            signals.append(f'🟡 流动性趋势中性（置信度 {confidence:+.1f}%）')
        else:
            signals.append(f'🟢 流动性趋势宽松（置信度 {confidence:+.1f}%）')

        if velocity is not None and velocity < -5:
            signals.append(f'🔴 流动性快速恶化（月度变化 {velocity:+.1f}pp）')
        if acceleration is not None and acceleration < -2:
            signals.append(f'🟠 恶化在加速（加速度 {acceleration:+.1f}）')
        elif acceleration is not None and acceleration > 2 and velocity is not None and velocity < 0:
            signals.append(f'🟡 恶化速度放缓，关注拐点（加速度 {acceleration:+.1f}）')

        return {
            'confidence': confidence,
            'velocity': velocity,
            'acceleration': acceleration,
            'wow_change': wow_change,
            'risk_score': risk_score,
            'signals': signals,
        }

    # ==================== 辅助方法 ====================

    @staticmethod
    def _merge_series(dimensions: Dict) -> Optional[pd.DataFrame]:
        """合并所有维度的时间序列"""
        all_series = []
        for dim_name, dim_data in dimensions.items():
            if isinstance(dim_data, dict) and 'series' in dim_data:
                s = dim_data['series']
                if isinstance(s, pd.DataFrame) and not s.empty:
                    all_series.append(s)

        if not all_series:
            return None

        try:
            merged = all_series[0]
            for s in all_series[1:]:
                merged = merged.join(s, how='outer')
            return merged.ffill()
        except Exception:
            return None
