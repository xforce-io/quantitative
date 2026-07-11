#!/usr/bin/env python3
"""
相对强弱分析器 - Relative Strength Analyzer
计算ETF相对于基准指数的相对强度评级
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class RelativeStrengthAnalyzer:
    """
    相对强弱分析器

    功能:
    1. 计算RS Rating (0-100)
    2. 计算多周期超额收益
    3. 相对强弱分类 (强势/同步/弱势)
    4. 评分调整建议
    """

    def __init__(self, default_benchmark: str = '000300.SH'):
        """
        初始化分析器

        Args:
            default_benchmark: 默认基准指数代码
        """
        self.default_benchmark = default_benchmark
        logger.info(f"✅ 相对强弱分析器初始化完成，默认基准: {default_benchmark}")

    def calculate_return(self, price_series: pd.Series, period: int) -> float:
        """
        计算收益率

        Args:
            price_series: 价格序列
            period: 周期（交易日数）

        Returns:
            收益率（小数形式，如0.05表示5%）
        """
        if len(price_series) <= period:
            return 0.0

        try:
            current_price = price_series.iloc[-1]
            past_price = price_series.iloc[-(period + 1)]

            if past_price == 0 or pd.isna(past_price) or pd.isna(current_price):
                return 0.0

            return (current_price - past_price) / past_price

        except Exception as e:
            logger.warning(f"计算收益率失败 (period={period}): {e}")
            return 0.0

    def calculate_percentile(self, value: float, historical_series: pd.Series) -> float:
        """
        计算历史百分位

        Args:
            value: 当前值
            historical_series: 历史序列

        Returns:
            百分位 (0-100)
        """
        if historical_series.empty:
            return 50.0

        try:
            # 去除NaN值
            valid_series = historical_series.dropna()
            if len(valid_series) == 0:
                return 50.0

            # 计算百分位
            percentile = (valid_series < value).sum() / len(valid_series) * 100
            return min(100.0, max(0.0, percentile))

        except Exception as e:
            logger.warning(f"计算百分位失败: {e}")
            return 50.0

    def calculate_rs_rating(
        self,
        etf_data: pd.DataFrame,
        benchmark_data: pd.DataFrame,
        benchmark_symbol: Optional[str] = None
    ) -> Dict:
        """
        计算RS Rating

        Args:
            etf_data: ETF价格数据 (必须包含 'close' 列)
            benchmark_data: 基准指数数据 (必须包含 'close' 列)
            benchmark_symbol: 基准指数代码（可选，用于记录）

        Returns:
            RS分析结果字典
        """
        if etf_data.empty or benchmark_data.empty:
            logger.warning("ETF或基准数据为空")
            return self._empty_result()

        if 'close' not in etf_data.columns or 'close' not in benchmark_data.columns:
            logger.warning("数据缺少 'close' 列")
            return self._empty_result()

        try:
            # 定义多个周期 (交易日数)
            periods = {
                '1M': 21,    # 约1个月
                '3M': 63,    # 约3个月
                '6M': 126,   # 约6个月
                '12M': 252   # 约12个月
            }

            rs_scores = []
            excess_returns = {}
            period_scores = {}

            etf_close = etf_data['close']
            benchmark_close = benchmark_data['close']

            # Align on common dates when both are date-indexed; otherwise use
            # positional length min so historical RS loop never indexes OOB.
            if (
                isinstance(etf_close.index, pd.DatetimeIndex)
                and isinstance(benchmark_close.index, pd.DatetimeIndex)
            ):
                common_idx = etf_close.index.intersection(benchmark_close.index)
                if len(common_idx) == 0:
                    logger.warning("No overlapping ETF/benchmark dates for RS rating")
                    return self._empty_result()
                etf_close = etf_close.loc[common_idx].sort_index()
                benchmark_close = benchmark_close.loc[common_idx].sort_index()

            n = min(len(etf_close), len(benchmark_close))
            if n == 0:
                logger.warning("No overlapping ETF/benchmark bars for RS rating")
                return self._empty_result()
            etf_close = etf_close.iloc[-n:]
            benchmark_close = benchmark_close.iloc[-n:]

            # 计算各周期的超额收益和RS分数
            for period_name, period_days in periods.items():
                # ETF收益率
                etf_return = self.calculate_return(etf_close, period_days)

                # 基准收益率
                benchmark_return = self.calculate_return(benchmark_close, period_days)

                # 超额收益
                excess_return = etf_return - benchmark_return
                excess_returns[period_name] = excess_return * 100  # 转换为百分比

                # 计算历史超额收益序列（滚动计算）
                if n >= period_days + 20:  # 至少需要20个历史点
                    historical_excess = []
                    for i in range(period_days + 20, n):
                        etf_prev = etf_close.iloc[i - period_days]
                        bm_prev = benchmark_close.iloc[i - period_days]
                        if etf_prev == 0 or bm_prev == 0:
                            continue
                        etf_ret_hist = (etf_close.iloc[i] - etf_prev) / etf_prev
                        bm_ret_hist = (benchmark_close.iloc[i] - bm_prev) / bm_prev
                        historical_excess.append(etf_ret_hist - bm_ret_hist)

                    # 计算当前超额收益的历史百分位
                    if historical_excess:
                        percentile = self.calculate_percentile(excess_return, pd.Series(historical_excess))
                        rs_scores.append(percentile)
                        period_scores[period_name] = {
                            'excess_return': excess_return * 100,
                            'percentile': percentile
                        }
                    else:
                        # Fall through to simple mapping when history is empty
                        if excess_return > 0.15:
                            percentile = 90
                        elif excess_return > 0.05:
                            percentile = 70
                        elif excess_return > -0.05:
                            percentile = 50
                        elif excess_return > -0.15:
                            percentile = 30
                        else:
                            percentile = 10
                        rs_scores.append(percentile)
                        period_scores[period_name] = {
                            'excess_return': excess_return * 100,
                            'percentile': percentile
                        }
                else:
                    # 数据不足，使用简单映射
                    if excess_return > 0.15:
                        percentile = 90
                    elif excess_return > 0.05:
                        percentile = 70
                    elif excess_return > -0.05:
                        percentile = 50
                    elif excess_return > -0.15:
                        percentile = 30
                    else:
                        percentile = 10

                    rs_scores.append(percentile)
                    period_scores[period_name] = {
                        'excess_return': excess_return * 100,
                        'percentile': percentile
                    }

            # 综合RS Rating (0-100)
            if rs_scores:
                # 加权平均，最近的周期权重更高
                weights = [0.4, 0.3, 0.2, 0.1]  # 1M, 3M, 6M, 12M
                rs_rating = sum(score * weight for score, weight in zip(rs_scores, weights))
            else:
                rs_rating = 50.0

            # 分类相对强弱
            status = self._classify_strength(rs_rating)

            # 评分调整建议
            score_adjustment = self._calc_score_adjustment(rs_rating)

            return {
                'rs_rating': round(rs_rating, 2),
                'status': status,
                'score_adjustment': score_adjustment,
                'period_analysis': period_scores,
                'excess_returns': {
                    '1M': round(excess_returns.get('1M', 0), 2),
                    '3M': round(excess_returns.get('3M', 0), 2),
                    '6M': round(excess_returns.get('6M', 0), 2),
                    '12M': round(excess_returns.get('12M', 0), 2)
                },
                'benchmark': benchmark_symbol or self.default_benchmark
            }

        except Exception as e:
            logger.error(f"计算RS Rating失败: {e}")
            import traceback
            traceback.print_exc()
            return self._empty_result()

    def _classify_strength(self, rs_rating: float) -> str:
        """
        分类相对强弱

        Args:
            rs_rating: RS Rating (0-100)

        Returns:
            强弱分类
        """
        if rs_rating >= 80:
            return "强势领涨"
        elif rs_rating >= 60:
            return "强势"
        elif rs_rating >= 40:
            return "同步"
        elif rs_rating >= 20:
            return "弱势"
        else:
            return "明显跑输"

    def _calc_score_adjustment(self, rs_rating: float) -> float:
        """
        计算评分调整系数

        Args:
            rs_rating: RS Rating (0-100)

        Returns:
            评分调整 (-0.15 到 +0.10)
        """
        if rs_rating >= 80:
            return 0.10  # 强势领涨，加分
        elif rs_rating >= 60:
            return 0.05  # 强势，小幅加分
        elif rs_rating >= 40:
            return 0.0   # 同步，不调整
        elif rs_rating >= 20:
            return -0.10  # 弱势，减分
        else:
            return -0.15  # 明显跑输，较大减分

    def _empty_result(self) -> Dict:
        """返回空结果"""
        return {
            'rs_rating': 50.0,
            'status': '数据不足',
            'score_adjustment': 0.0,
            'period_analysis': {},
            'excess_returns': {
                '1M': 0.0,
                '3M': 0.0,
                '6M': 0.0,
                '12M': 0.0
            },
            'benchmark': self.default_benchmark
        }

    def batch_calculate(
        self,
        etf_data_dict: Dict[str, pd.DataFrame],
        benchmark_data: pd.DataFrame,
        benchmark_symbol: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        批量计算多只ETF的RS Rating

        Args:
            etf_data_dict: ETF数据字典 {symbol: price_data}
            benchmark_data: 基准指数数据
            benchmark_symbol: 基准指数代码

        Returns:
            结果字典 {symbol: rs_result}
        """
        results = {}

        for symbol, etf_data in etf_data_dict.items():
            logger.info(f"计算 {symbol} 的RS Rating")
            rs_result = self.calculate_rs_rating(etf_data, benchmark_data, benchmark_symbol)
            results[symbol] = rs_result

        return results

    def generate_report(self, rs_result: Dict) -> str:
        """
        生成RS分析报告

        Args:
            rs_result: RS分析结果

        Returns:
            格式化的报告文本
        """
        report = []
        report.append("\n" + "="*60)
        report.append("📊 相对强弱分析报告")
        report.append("="*60)

        report.append(f"\n基准指数: {rs_result['benchmark']}")
        report.append(f"RS Rating: {rs_result['rs_rating']:.2f}/100")
        report.append(f"相对强弱: {rs_result['status']}")
        report.append(f"评分调整: {rs_result['score_adjustment']:+.3f}")

        report.append("\n📈 超额收益分析:")
        report.append("-"*60)
        excess = rs_result['excess_returns']
        report.append(f"1个月超额收益:  {excess['1M']:+7.2f}%")
        report.append(f"3个月超额收益:  {excess['3M']:+7.2f}%")
        report.append(f"6个月超额收益:  {excess['6M']:+7.2f}%")
        report.append(f"12个月超额收益: {excess['12M']:+7.2f}%")

        if rs_result['period_analysis']:
            report.append("\n📊 分周期分析:")
            report.append("-"*60)
            for period, analysis in rs_result['period_analysis'].items():
                report.append(f"{period:4s} - 超额: {analysis['excess_return']:+6.2f}% | "
                             f"百分位: {analysis['percentile']:.1f}%")

        report.append("="*60 + "\n")

        return "\n".join(report)


def main():
    """测试函数"""
    import sys
    from pathlib import Path

    # 添加项目根目录到路径
    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))

    from quant.data import create_data_provider
    from datetime import datetime, timedelta

    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*80)
    logger.info("📊 相对强弱分析器测试")
    print("="*80)

    # 初始化数据提供器
    try:
        import os
        token = os.getenv('TUSHARE_TOKEN')
        if token:
            provider = create_data_provider('tushare', {'token': token})
        else:
            provider = create_data_provider('yahoo', {})
    except Exception as e:
        logger.info("❌ 数据提供器初始化失败: {e}")
        return

    # 初始化RS分析器
    analyzer = RelativeStrengthAnalyzer(default_benchmark='000300.SH')

    # 测试ETF
    test_symbol = '512480.SH'  # 半导体ETF
    benchmark_symbol = '000300.SH'  # 沪深300

    logger.info("\n测试标的: {test_symbol}")
    logger.info("基准指数: {benchmark_symbol}")

    # 获取数据
    end_date = datetime.now()
    start_date = end_date - timedelta(days=400)  # 获取更多历史数据

    logger.info("\n正在获取数据...")

    try:
        etf_data = provider.get_stock_data(
            test_symbol,
            start_date.strftime('%Y%m%d'),
            end_date.strftime('%Y%m%d'),
            'D'
        )

        benchmark_data = provider.get_index_data(
            benchmark_symbol,
            start_date.strftime('%Y%m%d'),
            end_date.strftime('%Y%m%d'),
            'D'
        )

        if etf_data.empty or benchmark_data.empty:
            logger.info("❌ 数据获取失败或为空")
            return

        logger.info("✅ ETF数据: {len(etf_data)} 行")
        logger.info("✅ 基准数据: {len(benchmark_data)} 行")

        # 计算RS Rating
        rs_result = analyzer.calculate_rs_rating(etf_data, benchmark_data, benchmark_symbol)

        # 打印报告
        report = analyzer.generate_report(rs_result)
        logger.info("%s", report)

        # 解释
        logger.info("💡 解释:")
        logger.info("  - RS Rating {rs_result['rs_rating']:.0f} 表示该ETF在历史上超越基准的能力")
        logger.info("  - 当前状态: {rs_result['status']}")
        logger.info("  - 建议在筛选评分中调整: {rs_result['score_adjustment']:+.3f}")

    except Exception as e:
        logger.info("❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
