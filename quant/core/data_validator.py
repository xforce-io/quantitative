"""
Trading Data Validator - 交易数据验证器
验证交易数据的一致性，发现并标记异常交易
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    position_after: float
    cash_after: float
    error_message: str = ""
    warning_message: str = ""


@dataclass
class ValidationSummary:
    """验证总结"""
    total_trades: int
    valid_trades: int
    invalid_trades: int
    critical_errors: int
    warnings_count: int
    final_position: float
    final_cash: float
    errors: List[str]
    warnings: List[str]


class TradingDataValidator:
    """交易数据验证器"""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.tolerance = 1e-6  # Floating point tolerance
        
    def validate_trade_sequence(self, trades: List[Any]) -> Tuple[List[ValidationResult], ValidationSummary]:
        """
        验证交易序列的一致性
        
        Args:
            trades: 交易记录列表
            
        Returns:
            Tuple[List[ValidationResult], ValidationSummary]: 验证结果和总结
        """
        results = []
        errors = []
        warnings = []
        
        # Initialize tracking variables
        current_position = 0.0
        current_cash = float(self.initial_capital)
        
        for i, trade in enumerate(trades):
            # Extract trade information
            trade_info = self._extract_trade_info(trade)
            
            # Validate individual trade
            validation_result = self._validate_single_trade(
                trade_info, current_position, current_cash, i + 1
            )
            
            # Update position and cash only for valid trades
            if validation_result.is_valid:
                current_position = validation_result.position_after
                current_cash = validation_result.cash_after
            
            # Collect errors and warnings
            if validation_result.error_message:
                errors.append(f"Trade {i+1}: {validation_result.error_message}")
            if validation_result.warning_message:
                warnings.append(f"Trade {i+1}: {validation_result.warning_message}")
            
            results.append(validation_result)
        
        # Generate summary
        valid_count = sum(1 for r in results if r.is_valid)
        invalid_count = len(results) - valid_count
        critical_count = sum(1 for error in errors if "CRITICAL" in error)
        
        summary = ValidationSummary(
            total_trades=len(trades),
            valid_trades=valid_count,
            invalid_trades=invalid_count,
            critical_errors=critical_count,
            warnings_count=len(warnings),
            final_position=current_position,
            final_cash=current_cash,
            errors=errors,
            warnings=warnings
        )
        
        return results, summary
    
    def _extract_trade_info(self, trade: Any) -> Dict[str, Any]:
        """提取交易信息"""
        if isinstance(trade, dict):
            return {
                'type': trade.get('type', trade.get('side', 'unknown')),
                'price': float(trade.get('price', 0)),
                'quantity': float(trade.get('quantity', trade.get('shares', 0))),
                'timestamp': trade.get('timestamp', 'unknown')
            }
        else:
            # Handle object-style trades
            return {
                'type': getattr(trade, 'side', getattr(trade, 'type', 'unknown')),
                'price': float(getattr(trade, 'price', 0)),
                'quantity': float(getattr(trade, 'quantity', getattr(trade, 'shares', 0))),
                'timestamp': getattr(trade, 'timestamp', 'unknown')
            }
    
    def _validate_single_trade(self, trade_info: Dict[str, Any], 
                              current_position: float, current_cash: float, 
                              trade_number: int) -> ValidationResult:
        """验证单个交易"""
        trade_type = trade_info['type'].lower()
        price = trade_info['price']
        quantity = trade_info['quantity']
        
        # Initialize result
        result = ValidationResult(
            is_valid=True,
            position_after=current_position,
            cash_after=current_cash
        )
        
        # Basic validation
        if price <= 0:
            result.is_valid = False
            result.error_message = f"CRITICAL: Invalid price {price}"
            return result
        
        if quantity <= 0:
            result.is_valid = False
            result.error_message = f"CRITICAL: Invalid quantity {quantity}"
            return result
        
        # Validate 100-share minimum trading unit
        if quantity % 100 != 0:
            result.warning_message = f"WARNING: Quantity {quantity} not multiple of 100 shares"
        
        # Validate trade type specific logic
        if 'buy' in trade_type:
            return self._validate_buy_trade(trade_info, current_position, current_cash)
        elif 'sell' in trade_type:
            return self._validate_sell_trade(trade_info, current_position, current_cash)
        else:
            result.is_valid = False
            result.error_message = f"CRITICAL: Unknown trade type '{trade_type}'"
            return result
    
    def _validate_buy_trade(self, trade_info: Dict[str, Any], 
                           current_position: float, current_cash: float) -> ValidationResult:
        """验证买入交易"""
        price = trade_info['price']
        quantity = trade_info['quantity']
        
        # Calculate required cash (simplified, no commission)
        required_cash = price * quantity
        
        result = ValidationResult(
            is_valid=True,
            position_after=current_position + quantity,
            cash_after=current_cash - required_cash
        )
        
        # Check if sufficient cash
        if current_cash < required_cash:
            result.is_valid = False
            result.error_message = (f"CRITICAL: Insufficient cash for buy. "
                                  f"Need ¥{required_cash:,.2f}, have ¥{current_cash:,.2f}")
            result.position_after = current_position  # No change
            result.cash_after = current_cash  # No change
        
        # Check for negative cash after trade
        elif result.cash_after < -self.tolerance:
            result.warning_message = f"WARNING: Cash would become negative: ¥{result.cash_after:,.2f}"
        
        return result
    
    def _validate_sell_trade(self, trade_info: Dict[str, Any], 
                            current_position: float, current_cash: float) -> ValidationResult:
        """验证卖出交易"""
        price = trade_info['price']
        quantity = trade_info['quantity']
        
        # Calculate proceeds (simplified, no commission)
        proceeds = price * quantity
        
        result = ValidationResult(
            is_valid=True,
            position_after=current_position - quantity,
            cash_after=current_cash + proceeds
        )
        
        # CRITICAL CHECK: Sufficient position
        if current_position < quantity - self.tolerance:
            result.is_valid = False
            result.error_message = (f"CRITICAL: Insufficient position for sell. "
                                  f"Need {quantity:.0f} shares, have {current_position:.0f} shares")
            result.position_after = current_position  # No change
            result.cash_after = current_cash  # No change
        
        # Check for negative position after trade
        elif result.position_after < -self.tolerance:
            result.is_valid = False
            result.error_message = (f"CRITICAL: Position would become negative: "
                                  f"{result.position_after:.2f} shares")
            result.position_after = current_position  # No change
            result.cash_after = current_cash  # No change
        
        return result
    
    def generate_validation_report(self, results: List[ValidationResult], 
                                 summary: ValidationSummary) -> str:
        """生成验证报告"""
        report = "# 交易数据验证报告\n\n"
        
        # Summary section
        report += "## 📊 验证总结\n\n"
        report += f"- **总交易数**: {summary.total_trades} 笔\n"
        report += f"- **有效交易**: {summary.valid_trades} 笔 ✅\n"
        report += f"- **无效交易**: {summary.invalid_trades} 笔 ❌\n"
        report += f"- **严重错误**: {summary.critical_errors} 个 🚨\n"
        report += f"- **警告**: {summary.warnings_count} 个 ⚠️\n"
        report += f"- **最终持仓**: {summary.final_position:.2f} 股\n"
        report += f"- **最终现金**: ¥{summary.final_cash:,.2f}\n\n"
        
        # Data quality assessment
        quality_score = summary.valid_trades / summary.total_trades if summary.total_trades > 0 else 0
        if quality_score >= 0.95:
            quality_status = "🟢 优秀"
        elif quality_score >= 0.80:
            quality_status = "🟡 良好"
        elif quality_score >= 0.60:
            quality_status = "🟠 一般"
        else:
            quality_status = "🔴 差"
        
        report += f"## 📈 数据质量评估\n\n"
        report += f"- **数据质量得分**: {quality_score:.1%} {quality_status}\n\n"
        
        # Errors section
        if summary.errors:
            report += "## 🚨 错误详情\n\n"
            for error in summary.errors:
                report += f"- {error}\n"
            report += "\n"
        
        # Warnings section
        if summary.warnings:
            report += "## ⚠️ 警告详情\n\n"
            for warning in summary.warnings:
                report += f"- {warning}\n"
            report += "\n"
        
        # Recommendations
        report += "## 💡 建议\n\n"
        if summary.critical_errors > 0:
            report += "- 🚨 **立即修复**: 发现严重错误，建议立即修复策略代码\n"
            report += "- ⛔ **暂停实盘**: 在修复错误之前不建议进行实盘交易\n"
        if summary.invalid_trades > 0:
            report += "- 🔧 **改进策略**: 优化交易执行逻辑，减少无效交易\n"
        if summary.warnings_count > 0:
            report += "- ⚠️ **关注警告**: 检查并优化交易参数设置\n"
        if quality_score >= 0.95:
            report += "- ✅ **数据质量良好**: 交易数据基本可信\n"
        
        return report


def validate_backtest_results(backtest_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证回测结果的完整性和一致性
    
    Args:
        backtest_results: 回测结果字典
        
    Returns:
        Dict[str, Any]: 验证结果和修正建议
    """
    validator = TradingDataValidator(backtest_results.get('initialCapital', 100000))
    
    trades = backtest_results.get('trades', [])
    validation_results, summary = validator.validate_trade_sequence(trades)
    
    # Generate report
    report = validator.generate_validation_report(validation_results, summary)
    
    return {
        'validation_results': validation_results,
        'summary': summary,
        'report': report,
        'data_quality_score': summary.valid_trades / summary.total_trades if summary.total_trades > 0 else 0,
        'is_reliable': summary.critical_errors == 0 and summary.invalid_trades < summary.total_trades * 0.1
    } 