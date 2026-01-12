#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF基本面分析器 (ETF Fundamental Analyzer)

提供ETF基本面分析，包括：
1. ETF持仓成分股分析
2. 加权平均PE/PB/ROE计算
3. 盈利能力和增长率分析
4. 技术面+基本面综合评估
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timedelta
import warnings
import time
warnings.filterwarnings('ignore')

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class ETFFundamentalAnalyzer:
    """ETF基本面分析器"""

    def __init__(self, tushare_pro=None):
        """
        初始化ETF基本面分析器

        Args:
            tushare_pro: Tushare Pro API对象
        """
        if tushare_pro is None:
            import tushare as ts
            from quant.core.legacy_config import Config
            token = Config.TUSHARE_TOKEN
            if not token:
                raise ValueError("需要设置TUSHARE_TOKEN环境变量")
            ts.set_token(token)
            self.pro = ts.pro_api()
        else:
            self.pro = tushare_pro

    def get_etf_portfolio(self, symbol: str, end_date: str = None) -> pd.DataFrame:
        """
        获取ETF持仓明细

        Args:
            symbol: ETF代码（如 '510300.SH'）
            end_date: 截止日期（YYYYMMDD），默认最新

        Returns:
            持仓DataFrame，包含成分股代码、市值、占比等
        """
        try:
            logger.info(f"获取ETF持仓: {symbol}")

            # 获取持仓数据（季度更新）
            if end_date:
                portfolio = self.pro.fund_portfolio(ts_code=symbol, end_date=end_date)
            else:
                portfolio = self.pro.fund_portfolio(ts_code=symbol)

            if portfolio.empty:
                logger.warning(f"未获取到 {symbol} 的持仓数据")
                return pd.DataFrame()

            # 获取最新一期数据
            latest_date = portfolio['end_date'].max()
            portfolio_latest = portfolio[portfolio['end_date'] == latest_date].copy()

            # 重命名列
            portfolio_latest.rename(columns={
                'symbol': 'stock_code',
                'mkv': 'market_value',
                'amount': 'shares',
                'stk_mkv_ratio': 'weight_pct'
            }, inplace=True)

            logger.info(f"成功获取 {len(portfolio_latest)} 只成分股持仓（截止 {latest_date}）")

            return portfolio_latest

        except Exception as e:
            logger.error(f"获取ETF持仓失败: {e}")
            return pd.DataFrame()

    def get_stock_valuation(self, stock_code: str, trade_date: str = None) -> Dict:
        """
        获取个股估值指标（PE、PB、PS等）

        Args:
            stock_code: 股票代码（如 '600036.SH'）
            trade_date: 交易日期（YYYYMMDD），默认最近交易日

        Returns:
            估值指标字典
        """
        try:
            # 如果没有指定日期，使用最近一个交易日
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

            # 尝试获取指定日期的数据，如果失败则尝试往前推几天
            for i in range(10):
                try_date = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=i)).strftime('%Y%m%d')

                basic_data = self.pro.daily_basic(
                    ts_code=stock_code,
                    trade_date=try_date,
                    fields='ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,total_mv,circ_mv'
                )

                if not basic_data.empty:
                    result = basic_data.iloc[0].to_dict()
                    return result

            logger.warning(f"未获取到 {stock_code} 的估值数据")
            return {}

        except Exception as e:
            logger.error(f"获取 {stock_code} 估值数据失败: {e}")
            return {}

    def get_stock_financials(self, stock_code: str, period: str = None) -> Dict:
        """
        获取个股财务指标（ROE、净利润率等）

        Args:
            stock_code: 股票代码
            period: 报告期（YYYYMMDD），默认最新

        Returns:
            财务指标字典
        """
        try:
            # 获取最新财务指标
            if period:
                fina_data = self.pro.fina_indicator(ts_code=stock_code, period=period)
            else:
                fina_data = self.pro.fina_indicator(ts_code=stock_code)

            if fina_data.empty:
                return {}

            # 获取最新一期数据
            latest = fina_data.sort_values('end_date', ascending=False).iloc[0]

            result = {
                'end_date': latest.get('end_date'),
                'roe': latest.get('roe'),
                'roe_waa': latest.get('roe_waa'),
                'roa': latest.get('roa'),
                'gross_margin': latest.get('grossprofit_margin'),
                'net_margin': latest.get('netprofit_margin'),
                'debt_ratio': latest.get('debt_to_assets'),
                'current_ratio': latest.get('current_ratio'),
            }

            return result

        except Exception as e:
            logger.error(f"获取 {stock_code} 财务数据失败: {e}")
            return {}

    def calculate_weighted_metrics(self, portfolio: pd.DataFrame) -> Dict:
        """
        计算ETF的加权平均财务指标（批量优化版）

        Args:
            portfolio: ETF持仓DataFrame（必须包含stock_code和weight_pct）

        Returns:
            加权平均指标字典
        """
        if portfolio.empty:
            return {}

        logger.info(f"计算 {len(portfolio)} 只成分股的加权指标...")

        # 标准化股票代码格式
        stock_codes = []
        for code in portfolio['stock_code']:
            if '.' not in code:
                if code.startswith('6'):
                    stock_codes.append(f"{code}.SH")
                elif code.startswith(('0', '3')):
                    stock_codes.append(f"{code}.SZ")
                else:
                    stock_codes.append(code)
            else:
                stock_codes.append(code)
        
        portfolio = portfolio.copy()
        portfolio['stock_code_std'] = stock_codes

        # 🚀 批量获取估值数据
        valuations_df = self._batch_get_valuations(stock_codes)
        
        # 🚀 批量获取财务数据
        financials_df = self._batch_get_financials(stock_codes)
        
        # 初始化累计值
        weighted_pe = 0
        weighted_pb = 0
        weighted_ps = 0
        weighted_roe = 0
        weighted_net_margin = 0
        valid_count = 0
        total_weight = 0

        # 计算加权指标
        for idx, row in portfolio.iterrows():
            stock_code = row['stock_code_std']
            weight = float(row.get('weight_pct', 0)) / 100

            if weight <= 0:
                continue

            # 从批量结果中获取数据
            if not valuations_df.empty and stock_code in valuations_df['ts_code'].values:
                val_row = valuations_df[valuations_df['ts_code'] == stock_code].iloc[0]
                pe = val_row.get('pe_ttm') or val_row.get('pe')
                pb = val_row.get('pb')
                ps = val_row.get('ps_ttm') or val_row.get('ps')

                if pe and pe > 0:
                    weighted_pe += pe * weight
                if pb and pb > 0:
                    weighted_pb += pb * weight
                if ps and ps > 0:
                    weighted_ps += ps * weight

                valid_count += 1
                total_weight += weight

            # 从财务数据中获取
            if not financials_df.empty and stock_code in financials_df['ts_code'].values:
                fin_row = financials_df[financials_df['ts_code'] == stock_code].iloc[0]
                roe = fin_row.get('roe')
                net_margin = fin_row.get('netprofit_margin')

                if roe:
                    weighted_roe += roe * weight
                if net_margin:
                    weighted_net_margin += net_margin * weight

        # 归一化处理：当覆盖率 < 100%时，需要归一化到100%
        # 假设未覆盖部分的PE/PB分布与已覆盖部分相似
        if total_weight > 0 and total_weight < 1.0:
            normalization_factor = 1.0 / total_weight
            logger.info(f"覆盖率为 {total_weight*100:.1f}%，应用归一化系数 {normalization_factor:.2f}")

            if weighted_pe > 0:
                weighted_pe = weighted_pe * normalization_factor
            if weighted_pb > 0:
                weighted_pb = weighted_pb * normalization_factor
            if weighted_ps > 0:
                weighted_ps = weighted_ps * normalization_factor
            if weighted_roe > 0:
                weighted_roe = weighted_roe * normalization_factor
            if weighted_net_margin > 0:
                weighted_net_margin = weighted_net_margin * normalization_factor

        result = {
            'weighted_pe': weighted_pe if weighted_pe > 0 else None,
            'weighted_pb': weighted_pb if weighted_pb > 0 else None,
            'weighted_ps': weighted_ps if weighted_ps > 0 else None,
            'weighted_roe': weighted_roe if weighted_roe > 0 else None,
            'weighted_net_margin': weighted_net_margin if weighted_net_margin > 0 else None,
            'valid_stocks': valid_count,
            'total_weight_analyzed': total_weight * 100,  # 转换回百分比
            'is_normalized': total_weight < 1.0,  # 标记是否进行了归一化
        }

        logger.info(f"成功分析 {valid_count} 只成分股（占比 {total_weight*100:.1f}%）")

        return result
    
    def _batch_get_valuations(self, stock_codes: List[str], trade_date: str = None) -> pd.DataFrame:
        """
        批量获取估值数据
        
        Args:
            stock_codes: 股票代码列表
            trade_date: 交易日期
        
        Returns:
            估值数据DataFrame
        """
        if not stock_codes:
            return pd.DataFrame()
        
        try:
            # 使用逗号分隔的代码列表
            codes_str = ','.join(stock_codes[:50])  # Tushare最多支持50个
            
            if not trade_date:
                trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            
            # 尝试获取最近10天内的数据
            for i in range(10):
                try_date = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=i)).strftime('%Y%m%d')
                
                df = self.pro.daily_basic(
                    ts_code=codes_str,
                    trade_date=try_date,
                    fields='ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm'
                )
                
                if not df.empty:
                    logger.info(f"批量获取了 {len(df)} 只股票的估值数据")
                    return df
            
            logger.warning("未能批量获取估值数据")
            return pd.DataFrame()
        
        except Exception as e:
            logger.error(f"批量获取估值数据失败: {e}")
            return pd.DataFrame()
    
    def _batch_get_financials(self, stock_codes: List[str]) -> pd.DataFrame:
        """
        批量获取财务数据
        
        Args:
            stock_codes: 股票代码列表
        
        Returns:
            财务数据DataFrame
        """
        if not stock_codes:
            return pd.DataFrame()
        
        try:
            # 注意: fina_indicator 不支持多代码查询，需要逐个获取但可以优化
            # 这里使用缓存和批处理逻辑
            all_financials = []
            
            # 每次10个一批
            batch_size = 10
            for i in range(0, len(stock_codes), batch_size):
                batch_codes = stock_codes[i:i+batch_size]
                
                for code in batch_codes:
                    try:
                        df = self.pro.fina_indicator(
                            ts_code=code,
                            fields='ts_code,end_date,roe,roe_waa,roa,grossprofit_margin,netprofit_margin'
                        )
                        
                        if not df.empty:
                            # 只取最新一期
                            latest = df.sort_values('end_date', ascending=False).iloc[0:1]
                            all_financials.append(latest)
                    
                    except Exception as e:
                        logger.debug(f"获取 {code} 财务数据失败: {e}")
                        continue
                
                # 批次间隔
                if i + batch_size < len(stock_codes):
                    time.sleep(0.5)
            
            if all_financials:
                result = pd.concat(all_financials, ignore_index=True)
                logger.info(f"批量获取了 {len(result)} 只股票的财务数据")
                return result
            
            return pd.DataFrame()
        
        except Exception as e:
            logger.error(f"批量获取财务数据失败: {e}")
            return pd.DataFrame()

    def analyze_etf_fundamentals(self, symbol: str, symbol_name: str = "") -> Dict:
        """
        综合分析ETF基本面

        Args:
            symbol: ETF代码
            symbol_name: ETF名称

        Returns:
            综合分析结果
        """
        logger.info(f"开始分析ETF基本面: {symbol_name} ({symbol})")

        result = {
            'symbol': symbol,
            'name': symbol_name,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'portfolio': None,
            'weighted_metrics': None,
            'fundamental_assessment': None,
            'error': None
        }

        try:
            # 1. 获取持仓
            portfolio = self.get_etf_portfolio(symbol)

            if portfolio.empty:
                result['error'] = '无法获取持仓数据（可能不是ETF或数据未公布）'
                return result

            result['portfolio'] = portfolio
            result['portfolio_date'] = portfolio['end_date'].iloc[0] if not portfolio.empty else None
            result['top_holdings_count'] = len(portfolio)

            # 2. 计算加权指标
            weighted_metrics = self.calculate_weighted_metrics(portfolio)
            result['weighted_metrics'] = weighted_metrics

            # 3. 基本面评估
            assessment = self._assess_fundamentals(weighted_metrics)
            result['fundamental_assessment'] = assessment

            logger.info(f"完成ETF基本面分析: {symbol}")

        except Exception as e:
            logger.error(f"分析ETF基本面时出错: {e}")
            result['error'] = str(e)

        return result

    def _assess_fundamentals(self, metrics: Dict) -> Dict:
        """
        基于加权指标进行基本面评估

        Args:
            metrics: 加权平均指标

        Returns:
            评估结果
        """
        if not metrics:
            return {'level': '无数据', 'signals': []}

        signals = []
        score = 0  # 评分：-3（极度低估）到+3（极度高估）

        # PE评估
        pe = metrics.get('weighted_pe')
        if pe:
            if pe > 50:
                score += 2
                signals.append(f"⚠️ 加权PE={pe:.1f}倍，估值偏高")
            elif pe > 30:
                score += 1
                signals.append(f"📊 加权PE={pe:.1f}倍，估值中等偏高")
            elif pe > 15:
                signals.append(f"✅ 加权PE={pe:.1f}倍，估值合理")
            else:
                score -= 1
                signals.append(f"💎 加权PE={pe:.1f}倍，估值偏低")

        # PB评估
        pb = metrics.get('weighted_pb')
        if pb:
            if pb > 5:
                score += 1
                signals.append(f"⚠️ 加权PB={pb:.1f}倍，估值偏高")
            elif pb < 2:
                score -= 1
                signals.append(f"💎 加权PB={pb:.1f}倍，估值偏低")

        # ROE评估（盈利能力）
        roe = metrics.get('weighted_roe')
        if roe:
            if roe > 20:
                signals.append(f"✅ 加权ROE={roe:.1f}%，盈利能力强")
                score -= 1  # 高ROE支撑估值，降低高估风险
            elif roe > 10:
                signals.append(f"📊 加权ROE={roe:.1f}%，盈利能力中等")
            else:
                signals.append(f"⚠️ 加权ROE={roe:.1f}%，盈利能力较弱")
                score += 1  # 低ROE增加风险

        # 综合评级
        if score >= 2:
            level = "基本面高估"
            recommendation = "基本面显示估值偏高"
        elif score >= 1:
            level = "基本面偏高"
            recommendation = "基本面显示估值略高"
        elif score <= -2:
            level = "基本面低估"
            recommendation = "基本面显示估值偏低"
        elif score <= -1:
            level = "基本面偏低"
            recommendation = "基本面显示估值略低"
        else:
            level = "基本面合理"
            recommendation = "基本面估值合理"

        return {
            'level': level,
            'score': score,
            'signals': signals,
            'recommendation': recommendation
        }

    def format_fundamental_report(self, analysis: Dict) -> str:
        """
        格式化基本面分析报告

        Args:
            analysis: 分析结果

        Returns:
            格式化的文本报告
        """
        if 'error' in analysis and analysis['error']:
            return f"❌ 分析失败: {analysis['error']}"

        lines = [
            f"📊 ETF基本面分析报告 - {analysis.get('name', '')} ({analysis.get('symbol', '')})",
            "=" * 70,
            f"📅 分析时间: {analysis.get('analysis_date', 'N/A')}",
            ""
        ]

        # 持仓信息
        if analysis.get('portfolio') is not None:
            lines.append("📦 持仓信息:")
            lines.append(f"  持仓数据日期: {analysis.get('portfolio_date', 'N/A')}")
            lines.append(f"  前十大成分股数量: {analysis.get('top_holdings_count', 0)} 只")
            lines.append("")

        # 加权指标
        metrics = analysis.get('weighted_metrics')
        if metrics:
            lines.append("📈 加权平均估值指标:")

            if metrics.get('weighted_pe'):
                lines.append(f"  加权PE: {metrics['weighted_pe']:.2f} 倍")
            if metrics.get('weighted_pb'):
                lines.append(f"  加权PB: {metrics['weighted_pb']:.2f} 倍")
            if metrics.get('weighted_ps'):
                lines.append(f"  加权PS: {metrics['weighted_ps']:.2f} 倍")
            if metrics.get('weighted_roe'):
                lines.append(f"  加权ROE: {metrics['weighted_roe']:.2f}%")
            if metrics.get('weighted_net_margin'):
                lines.append(f"  加权净利润率: {metrics['weighted_net_margin']:.2f}%")

            lines.append(f"  分析覆盖率: {metrics.get('total_weight_analyzed', 0):.1f}%")
            lines.append("")

        # 基本面评估
        assessment = analysis.get('fundamental_assessment')
        if assessment:
            lines.append("🎯 基本面评估:")
            lines.append(f"  估值水平: {assessment.get('level', 'N/A')}")
            lines.append(f"  评分: {assessment.get('score', 0):+d} (-3低估 ~ +3高估)")
            lines.append(f"  建议: {assessment.get('recommendation', 'N/A')}")
            lines.append("")
            lines.append("  关键信号:")
            for signal in assessment.get('signals', []):
                lines.append(f"    • {signal}")

        lines.extend([
            "",
            "=" * 70,
        ])

        return "\n".join(lines)

# Backward compatibility alias
FundamentalValuationAnalyzer = ETFFundamentalAnalyzer
