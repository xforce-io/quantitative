#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Portfolio Layer Unit Tests
组合层单元测试

Tests for:
- BasePortfolioConstructor
- EqualWeightConstructor
- RiskParityConstructor
- Rebalancer
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime


class TestEqualWeightConstructor:
    """等权重组合构建器测试"""
    
    def test_construct_basic(self):
        """测试基本的等权重构建"""
        from quant.portfolio import EqualWeightConstructor
        from quant.analysis.alpha import Insight
        
        constructor = EqualWeightConstructor()
        
        # 创建测试 Insights
        insights = [
            Insight(symbol='000001.SZ', direction=1, magnitude=0.8, confidence=0.9),
            Insight(symbol='000002.SZ', direction=1, magnitude=0.6, confidence=0.8),
            Insight(symbol='000003.SZ', direction=1, magnitude=0.7, confidence=0.85),
        ]
        
        positions = constructor.construct(insights)
        
        # 应该返回等权重仓位
        assert len(positions) == 3
        assert abs(sum(positions.values()) - 1.0) < 0.01  # 总权重接近1
        
        # 检查是否接近等权
        expected_weight = 1.0 / 3
        for symbol, weight in positions.items():
            assert abs(weight - expected_weight) < 0.01, f"{symbol} weight {weight} != {expected_weight}"
    
    def test_construct_with_direction_filter(self):
        """测试方向过滤"""
        from quant.portfolio import EqualWeightConstructor
        from quant.analysis.alpha import Insight
        
        constructor = EqualWeightConstructor()
        
        # 混合方向的 Insights
        insights = [
            Insight(symbol='000001.SZ', direction=1, magnitude=0.8, confidence=0.9),
            Insight(symbol='000002.SZ', direction=-1, magnitude=0.6, confidence=0.8),  # 做空
            Insight(symbol='000003.SZ', direction=0, magnitude=0.0, confidence=0.5),   # 中性
        ]
        
        positions = constructor.construct(insights)
        
        # 应该只有方向为正的仓位
        assert '000001.SZ' in positions
        assert positions.get('000002.SZ', 0) <= 0  # 空头或无仓位
    
    def test_empty_insights(self):
        """测试空 insights"""
        from quant.portfolio import EqualWeightConstructor
        
        constructor = EqualWeightConstructor()
        positions = constructor.construct([])
        
        assert positions == {}


class TestRiskParityConstructor:
    """风险平价组合构建器测试"""
    
    def test_construct_basic(self):
        """测试基本的风险平价构建 (不传入 returns_data)"""
        from quant.portfolio import RiskParityConstructor
        from quant.analysis.alpha import Insight
        
        constructor = RiskParityConstructor()
        
        # 创建测试 Insights
        insights = [
            Insight(symbol='000001.SZ', direction=1, magnitude=0.8, confidence=0.9),
            Insight(symbol='000002.SZ', direction=1, magnitude=0.6, confidence=0.8),
        ]
        
        # 不传入 returns_data，应该使用默认权重
        positions = constructor.construct(insights)
        
        # 应该返回有效的仓位
        assert len(positions) >= 0
        if positions:
            assert abs(sum(positions.values()) - 1.0) < 0.01


class TestRebalancer:
    """再平衡器测试"""
    
    def test_calculate_threshold(self):
        """测试阈值过滤"""
        from quant.portfolio import Rebalancer
        
        rebalancer = Rebalancer(threshold=0.05)  # 5% 阈值
        
        current = {'000001.SZ': 0.3, '000002.SZ': 0.3, '000003.SZ': 0.4}
        target = {'000001.SZ': 0.32, '000002.SZ': 0.28, '000003.SZ': 0.40}  # 小幅变化
        
        result = rebalancer.calculate(current, target)
        
        # 因为偏差都小于 5%，不应该生成交易
        assert len(result.orders) == 0
    
    def test_calculate_significant_change(self):
        """测试显著变化时生成订单"""
        from quant.portfolio import Rebalancer
        
        rebalancer = Rebalancer(threshold=0.05)
        
        current = {'000001.SZ': 0.3, '000002.SZ': 0.3, '000003.SZ': 0.4}
        target = {'000001.SZ': 0.5, '000002.SZ': 0.2, '000003.SZ': 0.3}  # 显著变化
        
        result = rebalancer.calculate(current, target)
        
        # 应该生成交易订单
        assert len(result.orders) > 0
        
        # 检查订单方向
        buy_symbols = [o.symbol for o in result.orders if o.direction == 'BUY']
        sell_symbols = [o.symbol for o in result.orders if o.direction == 'SELL']
        
        assert '000001.SZ' in buy_symbols  # 000001 应该买入
        assert '000002.SZ' in sell_symbols  # 000002 应该卖出


class TestPortfolioAnalyzer:
    """组合分析器测试"""
    
    def test_calculate_metrics(self):
        """测试收益分析"""
        from quant.portfolio import PortfolioAnalyzer
        
        analyzer = PortfolioAnalyzer()
        
        # 创建测试收益率数据
        np.random.seed(42)  # 固定随机种子
        returns = pd.Series(np.random.randn(252) * 0.01)  # 日收益率
        
        metrics = analyzer.calculate_metrics(returns)
        
        # 检查返回的指标结构
        assert hasattr(metrics, 'total_return')
        assert hasattr(metrics, 'volatility')
        assert hasattr(metrics, 'sharpe_ratio')
        assert hasattr(metrics, 'max_drawdown')
    
    def test_calculate_var(self):
        """测试VaR计算"""
        from quant.portfolio import PortfolioAnalyzer
        
        analyzer = PortfolioAnalyzer()
        
        # 创建测试收益率数据
        np.random.seed(42)
        returns = pd.Series(np.random.randn(252) * 0.02)  # 日收益率
        
        var = analyzer.calculate_var(returns, confidence=0.95)
        
        # VaR 应该是正数
        assert var >= 0
    
    def test_analyze_positions(self):
        """测试仓位分析"""
        from quant.portfolio import PortfolioAnalyzer
        
        analyzer = PortfolioAnalyzer()
        
        weights = {
            '000001.SZ': 0.4,
            '000002.SZ': 0.3,
            '000003.SZ': 0.3,
        }
        
        analysis = analyzer.analyze_positions(weights)
        
        assert 'n_positions' in analysis
        assert analysis['n_positions'] == 3
        assert 'max_single_weight' in analysis


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
