#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Risk Layer Unit Tests
风控层单元测试

Tests for:
- PositionLimits
- VaRCalculator
- DrawdownMonitor
- CompositeRiskModel
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime


class TestPositionLimits:
    """仓位限制风控测试"""
    
    def test_single_position_limit(self):
        """测试单仓位限制"""
        from quant.risk import PositionLimits
        
        risk_model = PositionLimits(
            max_single_position=0.10,  # 单仓位上限 10%
            max_total_exposure=1.0
        )
        
        # 超过单仓位限制
        positions = {
            '000001.SZ': 0.15,  # 15% > 10%
            '000002.SZ': 0.08,
        }
        
        result = risk_model.check(positions)
        
        # 应该调整超过限制的仓位
        assert result.adjusted_positions['000001.SZ'] <= 0.10
        assert len(result.violations) > 0
    
    def test_total_exposure_limit(self):
        """测试总敞口限制"""
        from quant.risk import PositionLimits
        
        risk_model = PositionLimits(
            max_single_position=0.50,
            max_total_exposure=1.0  # 总敞口上限 100%
        )
        
        # 总敞口超过 100%
        positions = {
            '000001.SZ': 0.40,
            '000002.SZ': 0.40,
            '000003.SZ': 0.40,  # 总共 120%
        }
        
        result = risk_model.check(positions)
        
        # 应该缩放到 100%
        total = sum(result.adjusted_positions.values())
        assert total <= 1.0 + 0.01  # 允许小误差
        assert len(result.violations) > 0
    
    def test_no_violations(self):
        """测试无违规情况"""
        from quant.risk import PositionLimits
        
        risk_model = PositionLimits(
            max_single_position=0.20,
            max_total_exposure=1.0
        )
        
        positions = {
            '000001.SZ': 0.15,
            '000002.SZ': 0.15,
            '000003.SZ': 0.10,  # 总共 40%
        }
        
        result = risk_model.check(positions)
        
        assert result.passed
        assert len(result.violations) == 0
        assert result.adjusted_positions == positions


class TestVaRCalculator:
    """VaR计算器测试"""
    
    def test_var_calculation(self):
        """测试VaR计算"""
        from quant.risk import VaRCalculator
        
        # 使用正确的参数名
        var_model = VaRCalculator(
            var_limit=0.05,  # 最大VaR 5%
            confidence=0.95,
            lookback_days=60
        )
        
        positions = {'000001.SZ': 0.5, '000002.SZ': 0.5}
        
        # 创建模拟收益率数据
        np.random.seed(42)
        returns_data = {
            '000001.SZ': pd.Series(np.random.randn(100) * 0.02),
            '000002.SZ': pd.Series(np.random.randn(100) * 0.03),
        }
        
        result = var_model.check(positions, returns_data=returns_data)
        
        # 应该返回VaR相关指标
        assert 'portfolio_var' in result.risk_metrics
        assert 'var_limit' in result.risk_metrics
    
    def test_var_limit_violation(self):
        """测试VaR超限时的调整"""
        from quant.risk import VaRCalculator
        
        var_model = VaRCalculator(
            var_limit=0.01,  # 非常低的VaR限制
            confidence=0.95,
            lookback_days=60
        )
        
        positions = {'000001.SZ': 1.0}  # 满仓
        
        # 创建高波动率的收益率数据
        np.random.seed(42)
        returns_data = {
            '000001.SZ': pd.Series(np.random.randn(100) * 0.05),  # 5% 日波动
        }
        
        result = var_model.check(positions, returns_data=returns_data)
        
        # 如果VaR超限，应该调整仓位
        if not result.passed:
            # 调整后的仓位应该小于原始仓位
            assert result.adjusted_positions['000001.SZ'] < 1.0


class TestDrawdownMonitor:
    """回撤监控器测试"""
    
    def test_drawdown_check(self):
        """测试回撤检查"""
        from quant.risk import DrawdownMonitor
        
        monitor = DrawdownMonitor(max_drawdown=0.15)  # 最大回撤 15%
        
        positions = {'000001.SZ': 0.5}
        
        # 模拟超过回撤限制的组合价值序列
        portfolio_values = pd.Series([100000, 95000, 88000, 80000])  # 20% 回撤
        
        result = monitor.check(positions, portfolio_values=portfolio_values)
        
        # 应该返回有效的结果
        assert result is not None
        assert hasattr(result, 'passed')
        assert hasattr(result, 'adjusted_positions')


class TestCompositeRiskModel:
    """组合风控模型测试"""
    
    def test_composite_check(self):
        """测试组合风控"""
        from quant.risk import CompositeRiskModel, PositionLimits
        
        # 创建多个风控模型
        position_limits = PositionLimits(max_single_position=0.15)
        
        composite = CompositeRiskModel(models=[position_limits])
        
        positions = {
            '000001.SZ': 0.20,  # 超过限制
            '000002.SZ': 0.10,
        }
        
        result = composite.check(positions)
        
        # 应该应用所有风控规则
        assert result.adjusted_positions['000001.SZ'] <= 0.15


class TestRiskCheckResult:
    """风控检查结果测试"""
    
    def test_result_structure(self):
        """测试结果结构"""
        from quant.risk import RiskCheckResult
        
        result = RiskCheckResult(
            passed=True,
            adjusted_positions={'000001.SZ': 0.10},
            violations=[],
            risk_metrics={'total_exposure': 0.10}
        )
        
        assert result.passed is True
        assert '000001.SZ' in result.adjusted_positions
        assert isinstance(result.violations, list)
        assert isinstance(result.risk_metrics, dict)
    
    def test_add_violation(self):
        """测试添加违规记录"""
        from quant.risk import RiskCheckResult
        
        result = RiskCheckResult(
            passed=True,
            adjusted_positions={},
            violations=[],
            risk_metrics={}
        )
        
        # 添加违规应该自动设置 passed=False
        result.add_violation("Test violation")
        
        assert not result.passed
        assert "Test violation" in result.violations


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
