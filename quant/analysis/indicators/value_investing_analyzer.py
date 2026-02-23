#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
美股价值投资分析器 (Value Investing Analyzer)

五因子评分模型，每个因子独立打分，加权合计 0-100：

| 因子           | 权重  | 满分条件                              |
|---------------|-------|--------------------------------------|
| ROE 持续性     | 25分  | ROE > 15% 且持续 3 年+                |
| 负债率         | 20分  | Total Debt / Total Assets < 50%      |
| 自由现金流质量  | 20分  | FCF / Net Income > 80%              |
| 护城河(定量代理) | 15分  | 毛利率>40%(+5), 营业利润率>20%(+5), 市值>500亿(+5) |
| 估值合理性      | 20分  | Forward PE < 25 满分，线性递减至50得0  |

评级映射：A(80+), B(60-79), C(40-59), D(<40)

数据来源：yfinance (Yahoo Finance)
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from quant.core.logging_config import get_logger

logger = get_logger(__name__)

# 权重配置
WEIGHTS = {
    'roe': 25,
    'debt': 20,
    'fcf': 20,
    'moat': 15,
    'valuation': 20,
}

# 评级映射
RATING_MAP = [
    (80, 'A', '优秀 — 高质量价值股'),
    (60, 'B', '良好 — 可关注'),
    (40, 'C', '一般 — 存在风险'),
    (0, 'D', '较差 — 不建议'),
]


class ValueInvestingAnalyzer:
    """
    美股价值投资分析器

    基于五因子模型的价值投资评分系统，使用 yfinance 获取财务数据。
    """

    def analyze(self, symbol: str) -> Dict[str, Any]:
        """
        分析单只美股的价值投资评分

        Args:
            symbol: 美股代码 (e.g. 'AAPL', 'MSFT')

        Returns:
            分析结果字典，包含 score/rating/criteria/signals/recommendation
        """
        try:
            fundamentals = self._fetch_fundamentals(symbol)
            if 'error' in fundamentals:
                return {'symbol': symbol, 'error': fundamentals['error']}

            # 五因子打分
            roe_result = self._score_roe(fundamentals)
            debt_result = self._score_debt(fundamentals)
            fcf_result = self._score_fcf(fundamentals)
            moat_result = self._score_moat(fundamentals)
            val_result = self._score_valuation(fundamentals)

            # 加权总分
            total_score = (
                roe_result['score'] * WEIGHTS['roe'] / 100
                + debt_result['score'] * WEIGHTS['debt'] / 100
                + fcf_result['score'] * WEIGHTS['fcf'] / 100
                + moat_result['score'] * WEIGHTS['moat'] / 100
                + val_result['score'] * WEIGHTS['valuation'] / 100
            )
            total_score = round(total_score, 1)

            # 评级
            rating, rating_desc = 'D', '较差 — 不建议'
            for threshold, r, desc in RATING_MAP:
                if total_score >= threshold:
                    rating, rating_desc = r, desc
                    break

            # 收集信号
            signals = []
            for result in [roe_result, debt_result, fcf_result, moat_result, val_result]:
                signals.extend(result.get('signals', []))

            # 生成建议
            recommendation = self._generate_recommendation(
                total_score, rating, fundamentals, roe_result, debt_result, fcf_result, val_result
            )

            info = fundamentals.get('info', {})

            return {
                'symbol': symbol,
                'name': info.get('shortName', symbol),
                'score': total_score,
                'rating': rating,
                'rating_desc': rating_desc,
                'criteria': {
                    'roe': roe_result,
                    'debt': debt_result,
                    'fcf': fcf_result,
                    'moat': moat_result,
                    'valuation': val_result,
                },
                'signals': signals,
                'recommendation': recommendation,
                'summary': {
                    'market_cap_b': round(info.get('marketCap', 0) / 1e9, 1),
                    'forward_pe': info.get('forwardPE'),
                    'trailing_pe': info.get('trailingPE'),
                    'sector': info.get('sector', ''),
                    'industry': info.get('industry', ''),
                    'currency': info.get('currency', 'USD'),
                    'current_price': info.get('currentPrice') or info.get('regularMarketPrice'),
                },
            }

        except Exception as e:
            logger.error(f"分析 {symbol} 价值投资失败: {e}")
            return {'symbol': symbol, 'error': str(e)}

    def scan_value_stocks(self, symbols: List[str], max_workers: int = 5) -> List[Dict[str, Any]]:
        """
        批量扫描美股价值投资评分

        Args:
            symbols: 美股代码列表
            max_workers: 并发线程数

        Returns:
            分析结果列表（按评分降序）
        """
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_symbol = {
                executor.submit(self.analyze, sym): sym for sym in symbols
            }
            for future in as_completed(future_to_symbol):
                sym = future_to_symbol[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"扫描 {sym} 失败: {e}")
                    results.append({'symbol': sym, 'error': str(e)})

        # 按评分降序排序（出错的放最后）
        results.sort(key=lambda x: x.get('score', -1), reverse=True)
        return results

    # ==================== 数据获取 ====================

    def _fetch_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        使用 yfinance 获取财务数据

        Returns:
            包含 info, balance_sheet, income_stmt, cashflow 的字典
        """
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)

            info = ticker.info
            if not info or info.get('regularMarketPrice') is None and info.get('currentPrice') is None:
                return {'error': f'无法获取 {symbol} 的基本信息，请检查代码是否正确'}

            balance_sheet = ticker.balance_sheet
            income_stmt = ticker.income_stmt
            cashflow = ticker.cashflow

            return {
                'info': info,
                'balance_sheet': balance_sheet if balance_sheet is not None else pd.DataFrame(),
                'income_stmt': income_stmt if income_stmt is not None else pd.DataFrame(),
                'cashflow': cashflow if cashflow is not None else pd.DataFrame(),
            }
        except Exception as e:
            return {'error': f'获取 {symbol} 数据失败: {e}'}

    # ==================== 五因子打分 ====================

    def _score_roe(self, fundamentals: Dict) -> Dict[str, Any]:
        """
        ROE 持续性评分 (满分 100，权重 25%)

        逻辑：
        - 逐年计算 ROE = Net Income / Stockholders Equity
        - ROE > 15% 的年份越多，分数越高
        - 3年以上持续 > 15% 得满分
        """
        result = {'factor': 'ROE持续性', 'weight': WEIGHTS['roe'], 'signals': []}

        try:
            bs = fundamentals['balance_sheet']
            inc = fundamentals['income_stmt']

            if bs.empty or inc.empty:
                result['score'] = 0
                result['detail'] = '财报数据不足'
                result['signals'].append('⚠️ 缺少财报数据，无法评估 ROE')
                return result

            # yfinance 返回的列是年份(datetime)，行是会计项
            roe_values = []
            years = []

            for col in bs.columns:
                try:
                    equity = self._get_row_value(bs, col, [
                        'Stockholders Equity', 'Total Stockholder Equity',
                        'StockholdersEquity', 'Stockholders\' Equity',
                        'Common Stock Equity',
                    ])
                    net_income = self._get_row_value(inc, col, [
                        'Net Income', 'NetIncome', 'Net Income Common Stockholders',
                    ])

                    if equity and equity > 0 and net_income is not None:
                        roe = net_income / equity * 100
                        roe_values.append(roe)
                        years.append(col.year if hasattr(col, 'year') else str(col))
                except Exception:
                    continue

            if not roe_values:
                result['score'] = 0
                result['detail'] = '无法计算 ROE'
                return result

            # 评分：持续 ROE > 15% 的年数
            good_years = sum(1 for r in roe_values if r > 15)
            total_years = len(roe_values)
            avg_roe = np.mean(roe_values)
            latest_roe = roe_values[0]  # yfinance 最新年份在前

            if good_years >= 3:
                score = 100
            elif good_years == 2:
                score = 75
            elif good_years == 1:
                score = 50
            elif avg_roe > 10:
                score = 30
            else:
                score = max(0, avg_roe / 15 * 30)

            result['score'] = round(score, 1)
            result['detail'] = {
                'roe_values': [round(r, 1) for r in roe_values],
                'years': years,
                'good_years': good_years,
                'avg_roe': round(avg_roe, 1),
                'latest_roe': round(latest_roe, 1),
            }

            if latest_roe > 20:
                result['signals'].append(f'✅ ROE 优秀 ({latest_roe:.1f}%)')
            elif latest_roe > 15:
                result['signals'].append(f'✅ ROE 良好 ({latest_roe:.1f}%)')
            elif latest_roe > 0:
                result['signals'].append(f'⚠️ ROE 偏低 ({latest_roe:.1f}%)')
            else:
                result['signals'].append(f'❌ ROE 为负 ({latest_roe:.1f}%)')

        except Exception as e:
            result['score'] = 0
            result['detail'] = f'计算异常: {e}'

        return result

    def _score_debt(self, fundamentals: Dict) -> Dict[str, Any]:
        """
        负债率评分 (满分 100，权重 20%)

        逻辑：
        - Total Debt / Total Assets < 30% → 100分
        - 30%-50% → 线性递减
        - > 50% → 低分
        """
        result = {'factor': '负债率', 'weight': WEIGHTS['debt'], 'signals': []}

        try:
            bs = fundamentals['balance_sheet']
            if bs.empty:
                result['score'] = 0
                result['detail'] = '无资产负债表数据'
                return result

            # 取最新一期
            col = bs.columns[0]
            total_debt = self._get_row_value(bs, col, [
                'Total Debt', 'TotalDebt', 'Long Term Debt',
                'Long Term Debt And Capital Lease Obligation',
            ]) or 0
            total_assets = self._get_row_value(bs, col, [
                'Total Assets', 'TotalAssets',
            ])

            if not total_assets or total_assets <= 0:
                result['score'] = 0
                result['detail'] = '无法获取总资产'
                return result

            debt_ratio = total_debt / total_assets * 100

            if debt_ratio < 30:
                score = 100
            elif debt_ratio < 50:
                score = 100 - (debt_ratio - 30) / 20 * 60  # 30%→100, 50%→40
            elif debt_ratio < 70:
                score = 40 - (debt_ratio - 50) / 20 * 30  # 50%→40, 70%→10
            else:
                score = max(0, 10 - (debt_ratio - 70) / 30 * 10)

            result['score'] = round(score, 1)
            result['detail'] = {
                'total_debt': total_debt,
                'total_assets': total_assets,
                'debt_ratio': round(debt_ratio, 1),
            }

            if debt_ratio < 30:
                result['signals'].append(f'✅ 负债率低 ({debt_ratio:.1f}%)')
            elif debt_ratio < 50:
                result['signals'].append(f'⚠️ 负债率中等 ({debt_ratio:.1f}%)')
            else:
                result['signals'].append(f'❌ 负债率偏高 ({debt_ratio:.1f}%)')

        except Exception as e:
            result['score'] = 0
            result['detail'] = f'计算异常: {e}'

        return result

    def _score_fcf(self, fundamentals: Dict) -> Dict[str, Any]:
        """
        自由现金流质量评分 (满分 100，权重 20%)

        逻辑：
        - FCF / Net Income > 100% → 100分
        - 80%-100% → 满分
        - 50%-80% → 线性递减
        - < 50% → 低分
        """
        result = {'factor': '自由现金流', 'weight': WEIGHTS['fcf'], 'signals': []}

        try:
            cf = fundamentals['cashflow']
            inc = fundamentals['income_stmt']

            if cf.empty or inc.empty:
                result['score'] = 0
                result['detail'] = '缺少现金流或利润表数据'
                return result

            col = cf.columns[0]

            fcf = self._get_row_value(cf, col, [
                'Free Cash Flow', 'FreeCashFlow',
            ])

            # 如果没有直接的 FCF，尝试 Operating Cash Flow - CapEx
            if fcf is None:
                operating_cf = self._get_row_value(cf, col, [
                    'Operating Cash Flow', 'Total Cash From Operating Activities',
                    'Cash Flow From Continuing Operating Activities',
                ])
                capex = self._get_row_value(cf, col, [
                    'Capital Expenditure', 'CapitalExpenditure',
                ])
                if operating_cf is not None and capex is not None:
                    fcf = operating_cf + capex  # capex 通常为负值

            net_income = self._get_row_value(inc, col, [
                'Net Income', 'NetIncome', 'Net Income Common Stockholders',
            ])

            if fcf is None or net_income is None:
                result['score'] = 0
                result['detail'] = '无法获取 FCF 或净利润'
                return result

            if net_income <= 0:
                # 亏损公司，看 FCF 是否为正
                if fcf > 0:
                    score = 50
                    result['signals'].append('⚠️ 公司亏损但 FCF 为正')
                else:
                    score = 0
                    result['signals'].append('❌ 公司亏损且 FCF 为负')
                result['score'] = score
                result['detail'] = {'fcf': fcf, 'net_income': net_income, 'ratio': None}
                return result

            fcf_ratio = fcf / net_income * 100

            if fcf_ratio >= 80:
                score = 100
            elif fcf_ratio >= 50:
                score = 60 + (fcf_ratio - 50) / 30 * 40  # 50%→60, 80%→100
            elif fcf_ratio >= 0:
                score = fcf_ratio / 50 * 60  # 0%→0, 50%→60
            else:
                score = 0

            result['score'] = round(score, 1)
            result['detail'] = {
                'fcf': fcf,
                'net_income': net_income,
                'ratio': round(fcf_ratio, 1),
            }

            if fcf_ratio >= 80:
                result['signals'].append(f'✅ 现金流优秀 (FCF/NI={fcf_ratio:.0f}%)')
            elif fcf_ratio >= 50:
                result['signals'].append(f'⚠️ 现金流一般 (FCF/NI={fcf_ratio:.0f}%)')
            else:
                result['signals'].append(f'❌ 现金流不足 (FCF/NI={fcf_ratio:.0f}%)')

        except Exception as e:
            result['score'] = 0
            result['detail'] = f'计算异常: {e}'

        return result

    def _score_moat(self, fundamentals: Dict) -> Dict[str, Any]:
        """
        护城河评分 (满分 100，权重 15%)

        三个子因子各贡献 ~33 分：
        - 毛利率 > 40% → +33
        - 营业利润率 > 20% → +33
        - 市值 > 500亿美元 → +34
        """
        result = {'factor': '护城河', 'weight': WEIGHTS['moat'], 'signals': []}

        try:
            info = fundamentals['info']
            score = 0

            # 毛利率
            gross_margins = info.get('grossMargins')
            if gross_margins is not None:
                gm_pct = gross_margins * 100
                if gm_pct > 40:
                    score += 33
                    result['signals'].append(f'✅ 毛利率高 ({gm_pct:.1f}%)')
                elif gm_pct > 25:
                    score += 20
                else:
                    result['signals'].append(f'⚠️ 毛利率偏低 ({gm_pct:.1f}%)')
            else:
                gm_pct = None

            # 营业利润率
            op_margins = info.get('operatingMargins')
            if op_margins is not None:
                om_pct = op_margins * 100
                if om_pct > 20:
                    score += 33
                    result['signals'].append(f'✅ 营业利润率高 ({om_pct:.1f}%)')
                elif om_pct > 10:
                    score += 20
                else:
                    result['signals'].append(f'⚠️ 营业利润率偏低 ({om_pct:.1f}%)')
            else:
                om_pct = None

            # 市值
            market_cap = info.get('marketCap', 0)
            market_cap_b = market_cap / 1e9
            if market_cap_b > 50:
                score += 34
                result['signals'].append(f'✅ 大市值 (${market_cap_b:.0f}B)')
            elif market_cap_b > 10:
                score += 20
            else:
                result['signals'].append(f'⚠️ 市值偏小 (${market_cap_b:.1f}B)')

            result['score'] = round(score, 1)
            result['detail'] = {
                'gross_margin': round(gm_pct, 1) if gm_pct is not None else None,
                'operating_margin': round(om_pct, 1) if om_pct is not None else None,
                'market_cap_b': round(market_cap_b, 1),
            }

        except Exception as e:
            result['score'] = 0
            result['detail'] = f'计算异常: {e}'

        return result

    def _score_valuation(self, fundamentals: Dict) -> Dict[str, Any]:
        """
        估值合理性评分 (满分 100，权重 20%)

        逻辑：
        - Forward PE < 25 → 100分
        - 25-50 → 线性递减
        - > 50 → 0分
        - 无 Forward PE 时使用 Trailing PE
        """
        result = {'factor': '估值合理性', 'weight': WEIGHTS['valuation'], 'signals': []}

        try:
            info = fundamentals['info']

            pe = info.get('forwardPE')
            pe_type = 'Forward'
            if pe is None or pe <= 0:
                pe = info.get('trailingPE')
                pe_type = 'Trailing'

            if pe is None or pe <= 0:
                result['score'] = 0
                result['detail'] = '无有效 PE 数据'
                result['signals'].append('⚠️ 无法评估估值（PE 不可用或为负）')
                return result

            if pe < 15:
                score = 100
            elif pe < 25:
                score = 100 - (pe - 15) / 10 * 20  # 15→100, 25→80
                score = max(score, 80)
            elif pe <= 50:
                score = 80 - (pe - 25) / 25 * 80  # 25→80, 50→0
            else:
                score = 0

            result['score'] = round(max(0, score), 1)
            result['detail'] = {
                'pe': round(pe, 1),
                'pe_type': pe_type,
                'forward_pe': info.get('forwardPE'),
                'trailing_pe': info.get('trailingPE'),
                'peg_ratio': info.get('pegRatio'),
            }

            if pe < 15:
                result['signals'].append(f'✅ 估值极低 ({pe_type} PE={pe:.1f})')
            elif pe < 25:
                result['signals'].append(f'✅ 估值合理 ({pe_type} PE={pe:.1f})')
            elif pe < 35:
                result['signals'].append(f'⚠️ 估值偏高 ({pe_type} PE={pe:.1f})')
            else:
                result['signals'].append(f'❌ 估值过高 ({pe_type} PE={pe:.1f})')

        except Exception as e:
            result['score'] = 0
            result['detail'] = f'计算异常: {e}'

        return result

    # ==================== 辅助方法 ====================

    @staticmethod
    def _get_row_value(df: pd.DataFrame, col, possible_names: List[str]) -> Optional[float]:
        """从财报 DataFrame 中按优先级尝试获取某行的值"""
        for name in possible_names:
            if name in df.index:
                val = df.loc[name, col]
                if pd.notna(val):
                    return float(val)
        return None

    @staticmethod
    def _generate_recommendation(
        score: float, rating: str, fundamentals: Dict,
        roe_result: Dict, debt_result: Dict, fcf_result: Dict, val_result: Dict,
    ) -> str:
        """生成投资建议文本"""
        info = fundamentals.get('info', {})
        name = info.get('shortName', '该公司')

        if rating == 'A':
            rec = f"{name} 综合评分 {score} (A级)，属于高质量价值股。"
            rec += "各项基本面指标表现优异，建议重点关注。"
            if val_result.get('score', 0) < 60:
                rec += " 但估值偏高，可等待回调建仓。"
        elif rating == 'B':
            rec = f"{name} 综合评分 {score} (B级)，基本面整体良好。"
            weak_areas = []
            if roe_result.get('score', 0) < 50:
                weak_areas.append('ROE')
            if debt_result.get('score', 0) < 50:
                weak_areas.append('负债率')
            if fcf_result.get('score', 0) < 50:
                weak_areas.append('现金流')
            if weak_areas:
                rec += f" 需关注{'、'.join(weak_areas)}方面的改善。"
        elif rating == 'C':
            rec = f"{name} 综合评分 {score} (C级)，基本面存在一定风险，建议谨慎。"
        else:
            rec = f"{name} 综合评分 {score} (D级)，基本面较弱，不建议当前买入。"

        return rec
