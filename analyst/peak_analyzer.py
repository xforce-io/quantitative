#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Index Peak Analyzer - 指数见顶信号分析工具

特性:
- 威廉·欧奈尔分布日/停滞日 (Distribution/Stalling) 统计
- 技术面顶背离：RSI顶背离、MACD顶背离
- 过度扩张：价格偏离长均线(EMA200)过大
- 假突破/向上失败：20日新高后回落
- 放量小实体: 高成交量但实体很小(潜在派发)
- 基本面代理: 对指数使用价格动量/扩张做代理（若无估值数据）
- 综合评分与风险分级 + 操作建议

用法:
  python analyst/peak_analyzer.py --symbol 000300.SH --days 260
  python analyst/peak_analyzer.py --symbol IXIC --days 260 --json-out results/ixic_peak.json
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import json
import logging

# 项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.data_providers.data_provider_factory import DataProviderFactory

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """优化的RSI计算：使用标准的Wilder's smoothing"""
    delta = series.diff()
    up = delta.where(delta > 0, 0)
    down = -delta.where(delta < 0, 0)
    
    # 使用Wilder's smoothing方法（更准确）
    alpha = 1.0 / period
    up_ma = up.ewm(alpha=alpha, adjust=False).mean()
    down_ma = down.ewm(alpha=alpha, adjust=False).mean()
    
    rs = up_ma / (down_ma + 1e-10)  # 避免除零
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - macd_signal
    return macd, macd_signal, hist


def _rolling_max_idx(series: pd.Series, window: int) -> pd.Series:
    """返回滚动窗口内最大值的索引位置(相对窗口开始的偏移)。"""
    return series.rolling(window).apply(lambda x: int(np.argmax(x)), raw=True)


def _find_local_peaks(series: pd.Series, distance: int = 5, prominence: float = 0.02) -> pd.Index:
    """改进的局部峰值检测：添加重要性过滤，避免噪声峰值"""
    vals = series.values
    peaks = []
    
    # 使用滑动窗口检测局部最大值
    for i in range(distance, len(vals) - distance):
        current_val = vals[i]
        left_window = vals[i-distance:i]
        right_window = vals[i+1:i+1+distance]
        
        # 检查是否为局部最大值
        is_peak = (np.all(current_val > left_window) and 
                  np.all(current_val >= right_window))
        
        if is_peak:
            # 计算峰值的重要性（相对于周围最低值的比例）
            local_min = min(np.min(left_window), np.min(right_window))
            if local_min > 0:  # 避免除零
                peak_prominence = (current_val - local_min) / local_min
                if peak_prominence >= prominence:  # 只保留重要的峰值
                    peaks.append(series.index[i])
    
    return pd.Index(peaks)


@dataclass
class PeakSignals:
    distribution_days_25: int
    stalling_days_25: int
    rsi_bearish_divergence: bool
    macd_bearish_divergence: bool
    overextension_pct: float
    false_breakout_recent: bool
    volume_spike_small_body: bool
    # 新增的技术信号
    volatility_expansion: bool
    money_flow_divergence: bool
    exhaustion_gap: bool


class IndexPeakAnalyzer:
    def __init__(self, provider: str = 'auto', use_cache: bool = True):
        self.provider_name = provider
        self.use_cache = use_cache
        self.dp = self._init_provider(provider, use_cache)

    def _init_provider(self, provider: str, use_cache: bool):
        name = provider.lower()
        if name == 'auto':
            try:
                return DataProviderFactory.create('tushare', enableCache=use_cache)
            except Exception as e:
                logger.warning(f"初始化Tushare失败，回退Yahoo: {e}")
                return DataProviderFactory.create('yahoo', enableCache=use_cache)
        return DataProviderFactory.create(name, enableCache=use_cache)

    @staticmethod
    def _is_global_index(symbol: str) -> bool:
        symbol = symbol.upper()
        return (symbol.startswith('^') or symbol in {'IXIC','NDX','NASDAQ','SPX','DJI','HSI','HKTECH','HSCEI'})

    @staticmethod
    def _is_domestic_index(symbol: str) -> bool:
        symbol = symbol.upper()
        return symbol.endswith('.SH') or symbol.endswith('.SZ')

    def _load_data(self, symbol: str, days: int = 260) -> pd.DataFrame:
        """加载数据并进行清洗和验证"""
        end = datetime.now()
        start = end - timedelta(days=days + 60)  # 额外加载60天用于指标计算
        start_str = start.strftime('%Y%m%d')
        end_str = end.strftime('%Y%m%d')

        df = None
        data_type = None
        
        try:
            if self._is_global_index(symbol):
                df = self.dp.getGlobalIndexData(symbol, start_str, end_str, 'D')
                data_type = '全球指数'
            else:
                # 优先尝试指数接口
                if hasattr(self.dp, 'getIndexData'):
                    try:
                        df = self.dp.getIndexData(symbol, start_str, end_str, 'D')
                        data_type = '国内指数'
                    except Exception as e:
                        logger.warning(f"指数接口失败，尝试股票接口: {e}")
                        df = self.dp.getStockData(symbol, start_str, end_str, 'D')
                        data_type = '股票数据'
                else:
                    df = self.dp.getStockData(symbol, start_str, end_str, 'D')
                    data_type = '股票数据'
        except Exception as e:
            raise ValueError(f"无法获取 {symbol} 的行情数据: {e}")
            
        if df is None or df.empty:
            raise ValueError(f"获取的 {symbol} 数据为空")
            
        # 数据清洗和验证
        df = self._clean_and_validate_data(df, symbol)
        
        logger.info(f"获取{data_type}数据: {symbol} 共{len(df)}条")
        return df.sort_index()
    
    def _clean_and_validate_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """清洗和验证数据"""
        # 标准化列名
        column_mapping = {
            'Close': 'close', 'Open': 'open', 'High': 'high', 'Low': 'low',
            'Volume': 'volume', 'Vol': 'vol', 'Amount': 'amount'
        }
        df = df.rename(columns=column_mapping)
        
        # 确保必需的列存在
        required_cols = ['close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"缺少必需的数据列: {col}")
        
        # 处理缺失值
        df = df.dropna(subset=['close'])
        
        # 处理异常值（价格为0或负数）
        df = df[df['close'] > 0]
        
        # 统一成交量列名
        if 'volume' not in df.columns:
            if 'vol' in df.columns:
                df['volume'] = df['vol']
            elif 'amount' in df.columns and 'close' in df.columns:
                # 用成交额估算成交量（粗略）
                df['volume'] = df['amount'] / df['close']
            else:
                logger.warning(f"未找到成交量数据，某些分析可能不准确")
                df['volume'] = pd.Series(index=df.index, data=np.nan)
        
        if len(df) < 50:
            raise ValueError(f"数据量不足({len(df)}条)，至少需要50条数据进行分析")
            
        return df

    def _compute_distribution_and_stalling(self, df: pd.DataFrame) -> Dict[str, Any]:
        close = df['close']
        vol = df.get('vol') if 'vol' in df.columns else df.get('volume')
        if vol is None:
            # 尝试根据成交额或其他字段估计
            vol = df.get('amount', pd.Series(index=df.index, data=np.nan))
        ret = close.pct_change()
        vol_up = vol > vol.shift(1)

        # O'Neil: 分布日 = 当日跌幅<=-0.2% 且 成交量大于前一日
        distribution = (ret <= -0.002) & vol_up

        # 停滞日：涨跌幅介于[-0.2%, 0.2%]，且接近阶段高位(21日新高的97%以内)，且放量
        high_21 = close.rolling(21).max()
        near_high = close >= (high_21 * 0.97)
        stalling = (ret.between(-0.002, 0.002, inclusive='both')) & vol_up & near_high

        window = 25  # 约5周
        dist_25 = int(distribution.tail(window).sum())
        stall_25 = int(stalling.tail(window).sum())
        return {
            'distribution_days_25': dist_25,
            'stalling_days_25': stall_25,
            'distribution_mask': distribution,
            'stalling_mask': stalling,
        }

    def _compute_divergences(self, df: pd.DataFrame) -> Dict[str, bool]:
        close = df['close']
        rsi = _rsi(close, 14)
        macd, macd_sig, hist = _macd(close)

        # 找最近两个价格峰值
        peaks_idx = _find_local_peaks(close, distance=5)
        peaks_idx = peaks_idx[-5:]  # 最近5个里取后两个
        rsi_div = False
        macd_div = False
        if len(peaks_idx) >= 2:
            p1, p2 = peaks_idx[-2], peaks_idx[-1]
            # 价格更高高点
            price_higher_high = close.loc[p2] > close.loc[p1] * 1.001  # 容忍微小噪声
            # RSI更低高点
            rsi_lower_high = rsi.loc[p2] < rsi.loc[p1] - 0.5
            macd_lower_high = macd.loc[p2] < macd.loc[p1] - 0.0  # 不强制阈值
            rsi_div = bool(price_higher_high and rsi_lower_high)
            macd_div = bool(price_higher_high and macd_lower_high)
        return {
            'rsi_bearish_divergence': rsi_div,
            'macd_bearish_divergence': macd_div,
        }

    def _compute_overextension(self, df: pd.DataFrame) -> Dict[str, Any]:
        close = df['close']
        ema200 = close.ewm(span=200, adjust=False).mean()
        overext = (close.iloc[-1] / (ema200.iloc[-1] + 1e-9)) - 1.0
        return {
            'overextension_pct': float(overext)
        }

    def _compute_false_breakout(self, df: pd.DataFrame) -> Dict[str, Any]:
        close = df['close']
        recent_high = close.rolling(20).max()
        made_high_recently = recent_high.shift(1).iloc[-1] < close.rolling(20).max().iloc[-1]
        # 假突破：最近5天内创20日新高后，收盘回落到新高的-1%以下
        last5 = close.tail(5)
        high20 = recent_high.iloc[-1]
        false_break = (last5.max() >= high20 * 0.999) and (close.iloc[-1] < high20 * 0.99)
        return {
            'false_breakout_recent': bool(false_break)
        }

    def _compute_volume_spike_small_body(self, df: pd.DataFrame) -> Dict[str, Any]:
        if not {'open','close'}.issubset(df.columns):
            return {'volume_spike_small_body': False}
        close = df['close']
        open_ = df['open']
        vol = df.get('vol') if 'vol' in df.columns else df.get('volume')
        if vol is None:
            return {'volume_spike_small_body': False}
        body = (close - open_).abs() / close.replace(0, np.nan)
        vol_thr = vol.rolling(60).quantile(0.9)
        cond = (body.tail(1).iloc[0] <= 0.005) and (vol.tail(1).iloc[0] >= (vol_thr.tail(1).iloc[0] or 0))
        return {'volume_spike_small_body': bool(cond)}
    
    def _compute_volatility_expansion(self, df: pd.DataFrame) -> Dict[str, Any]:
        """波动率异常扩张信号：高位波动率突然扩张常预示见顶"""
        close = df['close']
        returns = close.pct_change()
        
        # 计算20日波动率
        volatility_20 = returns.rolling(20).std() * np.sqrt(252)
        # 计算60日波动率均值
        vol_avg_60 = volatility_20.rolling(60).mean()
        
        # 波动率扩张：当前波动率显著高于历史均值
        current_vol = volatility_20.iloc[-1]
        avg_vol = vol_avg_60.iloc[-1]
        
        vol_expansion = False
        if not pd.isna(current_vol) and not pd.isna(avg_vol) and avg_vol > 0:
            vol_ratio = current_vol / avg_vol
            vol_expansion = vol_ratio > 1.5  # 波动率超过均值50%
            
        return {'volatility_expansion': bool(vol_expansion)}
    
    def _compute_money_flow_divergence(self, df: pd.DataFrame) -> Dict[str, Any]:
        """资金流背离：价格上涨但成交量衰竭"""
        if not {'high', 'low', 'close'}.issubset(df.columns):
            return {'money_flow_divergence': False}
            
        close = df['close']
        high = df['high']
        low = df['low']
        vol = df.get('volume', df.get('vol'))
        
        if vol is None or vol.isna().all():
            return {'money_flow_divergence': False}
            
        # 计算简化的Money Flow Index
        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * vol
        
        # 计算14日MFI
        positive_flow = raw_money_flow.where(typical_price > typical_price.shift(1), 0)
        negative_flow = raw_money_flow.where(typical_price < typical_price.shift(1), 0)
        
        pos_mf = positive_flow.rolling(14).sum()
        neg_mf = negative_flow.rolling(14).sum()
        
        # 避免除零
        mfi = 100 - (100 / (1 + pos_mf / (neg_mf + 1e-10)))
        
        # 检查背离：价格创新高但MFI下降
        price_peaks = _find_local_peaks(close, distance=5)
        mfi_divergence = False
        
        if len(price_peaks) >= 2:
            p1, p2 = price_peaks[-2], price_peaks[-1]
            if (close.loc[p2] > close.loc[p1] * 1.01 and  # 价格明显新高
                not pd.isna(mfi.loc[p1]) and not pd.isna(mfi.loc[p2]) and
                mfi.loc[p2] < mfi.loc[p1] - 5):  # MFI显著下降
                mfi_divergence = True
                
        return {'money_flow_divergence': bool(mfi_divergence)}
    
    def _compute_exhaustion_gap(self, df: pd.DataFrame) -> Dict[str, Any]:
        """竭竭缺口：高位向上缺口后快速回补"""
        if not {'open', 'high', 'low', 'close'}.issubset(df.columns):
            return {'exhaustion_gap': False}
            
        close = df['close']
        open_price = df['open']
        high = df['high']
        low = df['low']
        
        exhaustion_gap = False
        
        # 检查最近10天内是否有竭竭缺口
        for i in range(max(1, len(df) - 10), len(df)):
            if i >= len(df) - 1:  # 避免超出范围
                continue
                
            # 向上缺口：今日最低 > 昨日最高
            gap_up = low.iloc[i] > high.iloc[i-1] * 1.005  # 至少间隙0.5%
            
            if gap_up:
                # 检查是否在高位（近20日高点钀90%以上）
                high_20 = high.rolling(20).max().iloc[i]
                near_high = close.iloc[i] >= high_20 * 0.9
                
                if near_high:
                    # 检查缺口后是否快速回补（后续3天内最低价跌破缺口区间）
                    gap_low = low.iloc[i-1]  # 缺口低点
                    for j in range(i+1, min(i+4, len(df))):
                        if low.iloc[j] <= gap_low:
                            exhaustion_gap = True
                            break
                            
        return {'exhaustion_gap': bool(exhaustion_gap)}

    def _score(self, signals: PeakSignals) -> Dict[str, Any]:
        """改进的评分系统：更精细的权重分配和风险等级划分"""
        score = 0.0
        details = []
        weight_details = []
        
        # 1. 分布日权重：威廉·欧奈尔最重要的指标
        # 根据分布日密度分级计分
        dd_count = signals.distribution_days_25
        if dd_count >= 6:  # 密集分布日，极高风险
            dd_score = 5.0
            details.append(f"分布日密集(极高风险): 近5周{dd_count}天")
        elif dd_count >= 4:  # 较多分布日
            dd_score = 3.5 
            details.append(f"分布日较多: 近5周{dd_count}天")
        elif dd_count >= 2:  # 一般分布日
            dd_score = 2.0
            details.append(f"分布日出现: 近5周{dd_count}天")
        elif dd_count == 1:
            dd_score = 0.5
            details.append(f"少量分布日: 近5周{dd_count}天")
        else:
            dd_score = 0
        score += dd_score
        weight_details.append(f"分布日: {dd_score:.1f}")
        
        # 2. 停滞日权重：高位量价背离的重要信号
        st_count = signals.stalling_days_25
        if st_count >= 3:
            st_score = 2.0
            details.append(f"停滞日频繁: 近5周{st_count}天")
        elif st_count >= 2:
            st_score = 1.5
            details.append(f"停滞日明显: 近5周{st_count}天")
        elif st_count == 1:
            st_score = 0.8
            details.append(f"停滞日出现: 近5周{st_count}天")
        else:
            st_score = 0
        score += st_score
        weight_details.append(f"停滞日: {st_score:.1f}")
        
        # 3. 技术指标背离：动能衰竭的重要信号
        div_score = 0
        if signals.rsi_bearish_divergence:
            div_score += 2.5  # RSI背离权重提高
            details.append("RSI顶背离(动能减弱)")
        if signals.macd_bearish_divergence:
            div_score += 2.0  # MACD背离
            details.append("MACD顶背离(趋势转弱)")
        score += div_score
        if div_score > 0:
            weight_details.append(f"技术背离: {div_score:.1f}")
        
        # 4. 过度扩张：回归风险
        ext_pct = signals.overextension_pct
        if ext_pct >= 0.25:  # 极度扩张
            ext_score = 3.0
            details.append(f"极度扩张(回归风险极高): {ext_pct:.1%}")
        elif ext_pct >= 0.20:  # 严重扩张
            ext_score = 2.5
            details.append(f"严重扩张: {ext_pct:.1%}")
        elif ext_pct >= 0.15:  # 明显扩张
            ext_score = 2.0
            details.append(f"明显扩张: {ext_pct:.1%}")
        elif ext_pct >= 0.10:  # 适度扩张
            ext_score = 1.0
            details.append(f"适度扩张: {ext_pct:.1%}")
        else:
            ext_score = 0
        score += ext_score
        if ext_score > 0:
            weight_details.append(f"扩张风险: {ext_score:.1f}")
        
        # 5. 假突破：短期技术失败
        if signals.false_breakout_recent:
            fb_score = 2.5
            score += fb_score
            details.append("近期假突破/上攻失败")
            weight_details.append(f"假突破: {fb_score:.1f}")
        
        # 6. 放量小实体：可能的派发信号
        if signals.volume_spike_small_body:
            vs_score = 1.5
            score += vs_score
            details.append("放量小实体(可能派发)")
            weight_details.append(f"放量小实体: {vs_score:.1f}")
        
        # 7. 新增的高级技术信号
        advanced_score = 0
        
        # 波动率异常扩张
        if signals.volatility_expansion:
            vol_score = 1.8
            advanced_score += vol_score
            details.append("波动率异常扩张(市场恭慌情绪)")
            weight_details.append(f"波动扩张: {vol_score:.1f}")
        
        # 资金流背离
        if signals.money_flow_divergence:
            mf_score = 2.2
            advanced_score += mf_score
            details.append("资金流背离(成交量衰竭)")
            weight_details.append(f"资金流背离: {mf_score:.1f}")
        
        # 竭竭缺口
        if signals.exhaustion_gap:
            gap_score = 2.0
            advanced_score += gap_score
            details.append("竭竭缺口(高位向上缺口后回补)")
            weight_details.append(f"竭竭缺口: {gap_score:.1f}")
        
        score += advanced_score
        
        # 综合风险等级判断（更精细的阈值）
        if score >= 14:
            level = '极高见顶风险'
            advice = '强烈建议大幅减仓或清仓；严格止损；考虑对冲策略'
            risk_color = '🔴'
        elif score >= 10:
            level = '高见顶风险'
            advice = '建议减仓至2-3成；设置紧密止损；避免追高操作'
            risk_color = '🟠'
        elif score >= 7:
            level = '较高见顶风险'
            advice = '控制仓位在5成以下；提高警惕；准备减仓预案'
            risk_color = '🟡'
        elif score >= 4:
            level = '中等观察风险'
            advice = '密切跟踪量价变化；谨慎参与突破；做好风控准备'
            risk_color = '🟢'
        elif score >= 1:
            level = '低见顶风险'
            advice = '保持关注但暂无明显见顶迹象；可正常操作但注意风控'
            risk_color = '🔵'
        else:
            level = '极低见顶风险'
            advice = '当前见顶风险很低；可正常投资但仍需关注市场变化'
            risk_color = '⚪'
            
        return {
            'peak_risk_score': float(round(score, 1)),
            'risk_level': level,
            'risk_color': risk_color,
            'advice': advice,
            'contributors': details,
            'weight_breakdown': weight_details
        }

    def analyze(self, symbol: str, days: int = 260) -> Dict[str, Any]:
        df = self._load_data(symbol, days)
        # 规范列名
        for c in list(df.columns):
            if c.lower() in {'open','close','high','low','vol','volume','amount'}:
                continue
        # 计算所有信号
        dist = self._compute_distribution_and_stalling(df)
        divs = self._compute_divergences(df)
        over = self._compute_overextension(df)
        fb = self._compute_false_breakout(df)
        vs = self._compute_volume_spike_small_body(df)
        # 新增的技术信号
        vol_exp = self._compute_volatility_expansion(df)
        mf_div = self._compute_money_flow_divergence(df)
        ex_gap = self._compute_exhaustion_gap(df)

        sig = PeakSignals(
            distribution_days_25=dist['distribution_days_25'],
            stalling_days_25=dist['stalling_days_25'],
            rsi_bearish_divergence=divs['rsi_bearish_divergence'],
            macd_bearish_divergence=divs['macd_bearish_divergence'],
            overextension_pct=over['overextension_pct'],
            false_breakout_recent=fb['false_breakout_recent'],
            volume_spike_small_body=vs['volume_spike_small_body'],
            # 新增信号
            volatility_expansion=vol_exp['volatility_expansion'],
            money_flow_divergence=mf_div['money_flow_divergence'],
            exhaustion_gap=ex_gap['exhaustion_gap'],
        )
        scored = self._score(sig)

        latest = df.iloc[-1]
        result = {
            'symbol': symbol,
            'as_of': str(df.index[-1]),
            'price': float(latest['close']),
            'signals': {
                'distribution_days_25': sig.distribution_days_25,
                'stalling_days_25': sig.stalling_days_25,
                'rsi_bearish_divergence': sig.rsi_bearish_divergence,
                'macd_bearish_divergence': sig.macd_bearish_divergence,
                'overextension_pct': sig.overextension_pct,
                'false_breakout_recent': sig.false_breakout_recent,
                'volume_spike_small_body': sig.volume_spike_small_body,
                # 新增信号
                'volatility_expansion': sig.volatility_expansion,
                'money_flow_divergence': sig.money_flow_divergence,
                'exhaustion_gap': sig.exhaustion_gap,
            },
            'assessment': scored
        }
        return result

    @staticmethod
    def print_report(analysis: Dict[str, Any]):
        sym = analysis['symbol']
        print("="*100)
        print(f"📈 指数见顶风险分析 | {sym}")
        print("="*100)
        print(f"⏱️ 截止: {analysis['as_of']}  |  现价: {analysis['price']:.2f}")
        s = analysis['signals']
        print("\n🔎 关键信号：")
        print(f"  • 分布日(近5周): {s['distribution_days_25']} 天")
        print(f"  • 停滞日(近5周): {s['stalling_days_25']} 天")
        print(f"  • RSI顶背离: {'是' if s['rsi_bearish_divergence'] else '否'}")
        print(f"  • MACD顶背离: {'是' if s['macd_bearish_divergence'] else '否'}")
        print(f"  • 相对EMA200扩张: {s['overextension_pct']:.1%}")
        print(f"  • 近期假突破: {'是' if s['false_breakout_recent'] else '否'}")
        print(f"  • 放量小实体(日线): {'是' if s['volume_spike_small_body'] else '否'}")
        a = analysis['assessment']
        print("\n🎯 结论：")
        print(f"  • 风险评分: {a['peak_risk_score']:.1f}  |  等级: {a['risk_level']}")
        print(f"  • 建议: {a['advice']}")
        if a.get('contributors'):
            print("  • 主要依据:")
            for c in a['contributors']:
                print(f"    - {c}")
        print("\n📘 说明：")
        print("  - 分布日: 指数下跌≥0.2%且放量；短期(约5周)内分布日累计较多时，见顶风险增大")
        print("  - 停滞日: 高位放量但涨幅很小(±0.2%)，常见于上升末端(威廉·欧奈尔)")
        print("  - 顶背离: 价格创新高但RSI/MACD未创新高，动能减弱")
        print("  - 过度扩张: 价格显著高于EMA200，回归风险上升")
        print("  - 假突破: 刚创阶段新高不久便回落至新高下方，突破失败")
        print("  - 放量小实体: 成交量处高位分位，但K线实体极小，可能为筹码交换/派发")


def _parse_args():
    import argparse
    parser = argparse.ArgumentParser(description='指数见顶风险分析工具 (William O\'Neil + 技术综合)')
    parser.add_argument('--symbol', required=True, help='指数代码，如 000300.SH / IXIC / HSI')
    parser.add_argument('--days', type=int, default=260, help='载入的历史天数，默认260')
    parser.add_argument('--provider', default='auto', choices=['auto','tushare','yahoo'], help='数据提供者')
    parser.add_argument('--json-out', help='将结果保存为JSON到指定路径')
    return parser.parse_args()


def main():
    args = _parse_args()
    analyzer = IndexPeakAnalyzer(provider=args.provider, use_cache=True)
    result = analyzer.analyze(args.symbol, days=args.days)
    IndexPeakAnalyzer.print_report(result)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n💾 已保存JSON: {out_path}")


if __name__ == '__main__':
    main()

