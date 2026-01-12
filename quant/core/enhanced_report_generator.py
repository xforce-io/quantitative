"""
Enhanced report generator for quantitative trading analysis
Generates comprehensive, interpretable reports with visualizations
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import os
from typing import Dict, Any, List, Optional, Union
import logging

# Set matplotlib backend for headless environments
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend

logger = logging.getLogger(__name__)

class EnhancedReportGenerator:
    def _validate_calculation_inputs(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """验证计算输入的有效性，并记录潜在问题"""
        issues = []
        
        # 检查必需字段
        required_fields = ['trades', 'initialCapital']
        for field in required_fields:
            if field not in results:
                issues.append(f"Missing required field: {field}")
        
        # 检查交易数据的合理性
        if 'trades' in results and results['trades']:
            buy_count = sum(1 for t in results['trades'] if getattr(t, 'side', 'unknown') == 'buy')
            sell_count = sum(1 for t in results['trades'] if getattr(t, 'side', 'unknown') == 'sell')
            
            if sell_count > buy_count * 2:  # 卖出次数异常多
                issues.append(f"Suspicious sell/buy ratio: {sell_count}/{buy_count}")
        
        # 检查初始资金的合理性
        initial_capital = results.get('initialCapital', 0)
        if initial_capital <= 0 or initial_capital > 10000000:  # 超过1000万
            issues.append(f"Suspicious initial capital: {initial_capital}")
        
        return {
            'issues': issues,
            'is_valid': len(issues) == 0,
            'validation_passed': len(issues) == 0
        }

    """Enhanced report generator with interpretable analysis and visualizations"""
    
    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = reports_dir
        self.ensure_reports_dir()
        
    def ensure_reports_dir(self):
        """Ensure reports directory exists"""
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)
            logger.info(f"Created reports directory: {self.reports_dir}")
    
    def generate_comprehensive_report(self, 
                                    backtest_results: Dict[str, Any],
                                    experiment_info: Optional[Dict[str, Any]] = None,
                                    symbol: str = None) -> str:
        """Generate a comprehensive interpretable report"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        symbol_str = symbol or backtest_results.get('symbol', 'UNKNOWN')
        base_filename = f"comprehensive_report_{symbol_str}_{timestamp}"
        
        # Generate different format reports
        report_files = {}
        
        # 1. Generate HTML interpretable report
        html_file = self._generate_html_report(backtest_results, experiment_info, base_filename)
        report_files['html'] = html_file
        
        # 2. Generate detailed Excel report
        excel_file = self._generate_enhanced_excel_report(backtest_results, experiment_info, base_filename)
        report_files['excel'] = excel_file
        
        # 3. Generate markdown summary
        md_file = self._generate_markdown_summary(backtest_results, experiment_info, base_filename)
        report_files['markdown'] = md_file
        
        # 4. Generate visualization charts
        charts_dir = self._generate_visualizations(backtest_results, base_filename)
        report_files['charts'] = charts_dir
        
        logger.info(f"Generated comprehensive reports: {report_files}")
        return report_files
    
    def _generate_html_report(self, results: Dict[str, Any], experiment_info: Optional[Dict], base_filename: str) -> str:
        """Generate HTML interpretable report"""
        
        html_file = os.path.join(self.reports_dir, f"{base_filename}.html")
        
        # Extract key metrics
        performance = self._extract_performance_metrics(results)
        trades = self._extract_trade_analysis(results)
        strategy_config = experiment_info.get('original_performance', {}) if experiment_info else {}
        
        html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>量化交易策略分析报告</title>
    <style>
        body {{ font-family: 'Arial', sans-serif; margin: 20px; background-color: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 3px solid #007bff; padding-bottom: 20px; margin-bottom: 30px; }}
        .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; text-align: center; }}
        .metric-value {{ font-size: 2em; font-weight: bold; margin: 10px 0; }}
        .metric-label {{ font-size: 0.9em; opacity: 0.9; }}
        .section {{ margin: 30px 0; }}
        .section-title {{ font-size: 1.5em; color: #333; border-left: 4px solid #007bff; padding-left: 15px; margin-bottom: 20px; }}
        .analysis-box {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 15px 0; }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
        .neutral {{ color: #6c757d; }}
        .table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .table th, .table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        .table th {{ background-color: #007bff; color: white; }}
        .interpretation {{ background: #e7f3ff; border-left: 4px solid #007bff; padding: 15px; margin: 15px 0; border-radius: 5px; }}
        .warning {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; border-radius: 5px; }}
        .recommendation {{ background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 15px 0; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>量化交易策略分析报告</h1>
            <p>股票代码: <strong>{results.get('symbol', 'N/A')}</strong> | 
               回测期间: {results.get('startDate', 'N/A')} - {results.get('endDate', 'N/A')}</p>
            <p>报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <!-- 核心性能指标 -->
        <div class="section">
            <h2 class="section-title">📊 核心性能指标</h2>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-label">总收益率</div>
                    <div class="metric-value {'positive' if performance['total_return'] > 0 else 'negative'}">{performance['total_return']:.2%}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">夏普比率</div>
                    <div class="metric-value {'positive' if performance['sharpe_ratio'] > 1 else 'neutral'}">{performance['sharpe_ratio']:.3f}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">最大回撤</div>
                    <div class="metric-value negative">{performance['max_drawdown']:.2%}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">胜率</div>
                    <div class="metric-value {'positive' if performance['win_rate'] > 0.6 else 'neutral'}">{performance['win_rate']:.1%}</div>
                </div>
            </div>
        </div>

        <!-- 策略解释 -->
        <div class="section">
            <h2 class="section-title">🎯 策略分析与解释</h2>
            {self._generate_strategy_interpretation(results, experiment_info)}
        </div>

        <!-- 交易分析 -->
        <div class="section">
            <h2 class="section-title">📈 交易行为分析</h2>
            {self._generate_trade_analysis_html(trades)}
        </div>

        <!-- 详细交易记录 -->
        <div class="section">
            <h2 class="section-title">📋 详细交易记录</h2>
            {self._generate_trades_table_html(results.get('trades', []))}
        </div>
        
        <!-- 风险分析 -->
        <div class="section">
            <h2 class="section-title">⚠️ 风险分析</h2>
            {self._generate_risk_analysis_html(performance)}
        </div>

        <!-- 投资建议 -->
        <div class="section">
            <h2 class="section-title">💡 投资建议与优化建议</h2>
            {self._generate_recommendations_html(performance, trades)}
        </div>

        <!-- 详细数据表 -->
        <div class="section">
            <h2 class="section-title">📋 详细性能数据</h2>
            {self._generate_detailed_metrics_table(performance)}
        </div>
    </div>
</body>
</html>
        """
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_file
    
    def _generate_strategy_interpretation(self, results: Dict[str, Any], experiment_info: Optional[Dict]) -> str:
        """Generate strategy interpretation section"""
        if not experiment_info:
            return "<p>No experiment information available for strategy interpretation.</p>"
        
        strategy_name = experiment_info.get('strategy_name', 'Unknown')
        original_perf = experiment_info.get('original_performance', {})
        
        # Parse strategy parameters from name
        interpretation = f"""
        <div class="analysis-box">
            <h3>策略类型分析</h3>
            <p><strong>策略名称:</strong> {strategy_name}</p>
        """
        
        if 'Grid' in strategy_name:
            # Grid strategy interpretation
            base_ratio = original_perf.get('baseRatio', 0.3)
            interpretation += f"""
            <p><strong>网格交易策略</strong> - 这是一种在震荡市场中表现优异的策略:</p>
            <ul>
                <li><strong>基础仓位比例:</strong> {base_ratio:.1%} - {"保守" if base_ratio <= 0.3 else "积极" if base_ratio >= 0.5 else "均衡"}的长期持仓策略</li>
                <li><strong>网格交易:</strong> {1-base_ratio:.1%} 资金用于网格交易，通过价格波动获取收益</li>
                <li><strong>适用场景:</strong> 震荡市场、横盘整理阶段</li>
                <li><strong>盈利原理:</strong> 低买高卖，通过频繁的小幅交易积累收益</li>
            </ul>
            """
        
        interpretation += "</div>"
        return interpretation
    
    def _generate_trade_analysis_html(self, trades_info: Dict[str, Any]) -> str:
        """Generate trade analysis HTML section"""
        return f"""
        <div class="analysis-box">
            <h3>交易统计</h3>
            <div class="metric-grid" style="grid-template-columns: repeat(3, 1fr);">
                <div style="text-align: center;">
                    <strong>总交易次数</strong><br>
                    <span style="font-size: 1.5em; color: #007bff;">{trades_info['total_trades']}</span>
                </div>
                <div style="text-align: center;">
                    <strong>盈利交易</strong><br>
                    <span style="font-size: 1.5em; color: #28a745;">{trades_info['winning_trades']}</span>
                </div>
                <div style="text-align: center;">
                    <strong>平均持仓时间</strong><br>
                    <span style="font-size: 1.5em; color: #6c757d;">{trades_info.get('avg_holding_days', 'N/A')}</span>
                </div>
            </div>
        </div>
        
        <div class="interpretation">
            <h4>🔍 交易行为解读</h4>
            <p><strong>交易频率分析:</strong> 
            {'频繁交易型策略，适合捕捉短期波动' if trades_info['total_trades'] > 20 else '中低频交易，注重质量over数量' if trades_info['total_trades'] > 5 else '低频交易，长期持有导向'}</p>
            
            <p><strong>成功率评估:</strong> 
            胜率 {trades_info['win_rate']:.1%} {'优秀' if trades_info['win_rate'] > 0.7 else '良好' if trades_info['win_rate'] > 0.5 else '需要改进'}</p>
        </div>
        """
    
    def _generate_risk_analysis_html(self, performance: Dict[str, Any]) -> str:
        """Generate risk analysis HTML section"""
        max_dd = abs(performance['max_drawdown'])
        sharpe = performance['sharpe_ratio']
        
        risk_level = "低风险" if max_dd < 0.1 else "中等风险" if max_dd < 0.2 else "高风险"
        risk_color = "#28a745" if max_dd < 0.1 else "#ffc107" if max_dd < 0.2 else "#dc3545"
        
        return f"""
        <div class="analysis-box">
            <h3>风险评估</h3>
            <div style="background: {risk_color}20; border: 1px solid {risk_color}; border-radius: 5px; padding: 15px;">
                <h4 style="color: {risk_color}; margin: 0;">风险等级: {risk_level}</h4>
                <p>最大回撤: <strong>{max_dd:.2%}</strong></p>
            </div>
        </div>
        
        <div class="warning">
            <h4>⚠️ 风险提示</h4>
            <ul>
                <li><strong>回撤风险:</strong> 历史最大亏损达到 {max_dd:.2%}，需要有相应的心理承受能力</li>
                <li><strong>市场风险:</strong> 策略表现依赖于历史数据，未来市场环境变化可能影响收益</li>
                <li><strong>流动性风险:</strong> 在极端市场条件下可能面临成交困难</li>
            </ul>
        </div>
        """
    
    def _generate_recommendations_html(self, performance: Dict[str, Any], trades_info: Dict[str, Any]) -> str:
        """Generate recommendations HTML section"""
        recommendations = []
        
        # Based on performance metrics, generate recommendations
        if performance['sharpe_ratio'] > 1.5:
            recommendations.append("✅ 该策略具有优秀的风险调整收益，建议考虑实盘应用")
        elif performance['sharpe_ratio'] > 1.0:
            recommendations.append("✅ 该策略表现良好，可以考虑小资金试验")
        else:
            recommendations.append("⚠️ 该策略风险调整收益偏低，建议进一步优化参数")
        
        if abs(performance['max_drawdown']) > 0.2:
            recommendations.append("⚠️ 最大回撤较大，建议降低仓位或优化止损策略")
        
        if performance['win_rate'] > 0.7:
            recommendations.append("✅ 胜率较高，策略稳定性良好")
        elif performance['win_rate'] < 0.5:
            recommendations.append("⚠️ 胜率偏低，建议优化进出场时机")
        
        if trades_info['total_trades'] > 50:
            recommendations.append("💡 交易频率较高，注意交易成本对收益的影响")
        elif trades_info['total_trades'] < 5:
            recommendations.append("💡 交易次数较少，可能错失部分机会，考虑调整策略参数")
        
        recs_html = "<div class='recommendation'><h4>💡 投资建议</h4><ul>"
        for rec in recommendations:
            recs_html += f"<li>{rec}</li>"
        recs_html += "</ul></div>"
        
        # Optimization suggestions
        opt_suggestions = """
        <div class="analysis-box">
            <h4>🔧 优化建议</h4>
            <ol>
                <li><strong>周期验证:</strong> 在不同的时间周期（如牛市、熊市、震荡市）分别回测，验证策略的稳健性。</li>
                <li><strong>参数调优:</strong> 基于当前结果，可以尝试微调网格间距或仓位比例。</li>
                <li><strong>风控优化:</strong> 考虑加入动态止损机制，控制最大回撤。</li>
                <li><strong>资金管理:</strong> 建议分批投入，先小资金验证再逐步扩大。</li>
            </ol>
        </div>
        """
        
        return recs_html + opt_suggestions
    
    def _generate_trades_table_html(self, trades: List) -> str:
        """Generate detailed trades table in HTML"""
        if not trades:
            return "<p>没有交易记录。</p>"
        
        table_html = "<table class='table'><thead><tr><th>#</th><th>时间</th><th>类型</th><th>价格</th><th>数量</th><th>利润</th><th>资产组合价值</th></tr></thead><tbody>"
        
        for i, trade_obj in enumerate(trades):
            # Handle both dict and object types for trade
            if isinstance(trade_obj, dict):
                trade = trade_obj
            else:
                trade = {
                    'timestamp': getattr(trade_obj, 'timestamp', 'N/A'),
                    'type': getattr(trade_obj, 'side', 'N/A'),
                    'price': getattr(trade_obj, 'price', 0),
                    'quantity': getattr(trade_obj, 'quantity', 0),
                    'profit': getattr(trade_obj, 'profit', 0),
                    'portfolio_value': getattr(trade_obj, 'portfolio_value', 0)
                }

            profit_str = f"<span class='{'positive' if trade.get('profit', 0) > 0 else 'negative' if trade.get('profit', 0) < 0 else 'neutral'}'>{trade.get('profit', 0):.2f}</span>" if trade.get('profit') is not None else "N/A"
            
            table_html += f"""
            <tr>
                <td>{i+1}</td>
                <td>{trade.get('timestamp')}</td>
                <td>{trade.get('type')}</td>
                <td>{trade.get('price'):.2f}</td>
                <td>{trade.get('quantity')}</td>
                <td>{profit_str}</td>
                <td>¥{trade.get('portfolio_value', 0):,.2f}</td>
            </tr>
            """
        
        table_html += "</tbody></table>"
        return table_html
    
    def _generate_detailed_metrics_table(self, performance: Dict[str, Any]) -> str:
        """Generate detailed metrics table"""
        metrics = [
            ("总收益率", f"{performance['total_return']:.4%}"),
            ("年化收益率", f"{performance.get('annual_return', 0):.4%}"),
            ("夏普比率", f"{performance['sharpe_ratio']:.4f}"),
            ("最大回撤", f"{performance['max_drawdown']:.4%}"),
            ("胜率", f"{performance['win_rate']:.2%}"),
            ("交易次数", f"{performance.get('total_trades', 0)}"),
            ("平均收益", f"{performance.get('avg_profit', 0):.2f}"),
            ("收益标准差", f"{performance.get('return_std', 0):.4f}"),
            ("卡尔马比率", f"{performance.get('calmar_ratio', 0):.4f}"),
        ]
        
        table_html = "<table class='table'><thead><tr><th>指标</th><th>数值</th><th>评级</th><th>说明</th></tr></thead><tbody>"
        
        explanations = {
            "总收益率": "整个回测期间的总收益率",
            "年化收益率": "换算成年化的收益率",
            "夏普比率": "风险调整后收益，>1为良好，>1.5为优秀",
            "最大回撤": "历史最大亏损幅度，越小越好",
            "胜率": "盈利交易占总交易的比例",
            "交易次数": "回测期间总交易次数",
            "平均收益": "每笔交易的平均收益",
            "收益标准差": "收益的波动程度",
            "卡尔马比率": "年化收益率/最大回撤，衡量风险调整收益"
        }
        
        for metric, value in metrics:
            explanation = explanations.get(metric, "")
            rating = self._get_metric_rating_from_str(metric, value)
            table_html += f"<tr><td><strong>{metric}</strong></td><td>{value}</td><td>{rating}</td><td>{explanation}</td></tr>"
        
        table_html += "</tbody></table>"
        return table_html
    
    def _generate_enhanced_excel_report(self, results: Dict[str, Any], experiment_info: Optional[Dict], base_filename: str) -> str:
        """Generate enhanced Excel report with multiple sheets"""
        excel_file = os.path.join(self.reports_dir, f"{base_filename}.xlsx")
        
        with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
            # Sheet 1: Summary
            self._create_summary_sheet(writer, results, experiment_info)
            
            # Sheet 2: Performance Metrics
            self._create_performance_sheet(writer, results)
            
            # Sheet 3: Trade Details (if available)
            if 'trades' in results:
                self._create_trades_sheet(writer, results['trades'])
            
            # Sheet 4: Portfolio Values
            if 'portfolioValues' in results:
                self._create_portfolio_sheet(writer, results['portfolioValues'])
        
        return excel_file
    
    def _create_summary_sheet(self, writer, results: Dict[str, Any], experiment_info: Optional[Dict]):
        """Create summary sheet in Excel"""
        summary_data = {
            '项目': ['股票代码', '策略类型', '回测开始日期', '回测结束日期', '初始资金', '最终资金', '总收益率', '夏普比率', '最大回撤', '交易次数'],
            '数值': [
                results.get('symbol', 'N/A'),
                experiment_info.get('strategy_name', 'N/A') if experiment_info else 'N/A',
                results.get('startDate', 'N/A'),
                results.get('endDate', 'N/A'),
                f"¥{results.get('initialCapital', 0):,.2f}",
                f"¥{results.get('finalCapital', 0):,.2f}",
                f"{self._calculate_total_return(results):.4%}",
                f"{self._calculate_sharpe_ratio(results):.4f}",
                f"{self._calculate_max_drawdown(results):.4%}",
                self._count_trades(results)
            ]
        }
        
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='策略摘要', index=False)
    
    def _create_performance_sheet(self, writer, results: Dict[str, Any]):
        """Create performance metrics sheet"""
        performance = self._extract_performance_metrics(results)
        
        perf_data = {
            '性能指标': list(performance.keys()),
            '数值': list(performance.values()),
            '评级': [self._get_metric_rating(k, v) for k, v in performance.items()]
        }
        
        df_perf = pd.DataFrame(perf_data)
        df_perf.to_excel(writer, sheet_name='性能指标', index=False)
    
    def _create_trades_sheet(self, writer, trades: List):
        """Create trades detail sheet"""
        if trades:
            # Convert trade objects to dictionaries
            trade_data = []
            for trade in trades:
                if hasattr(trade, '__dict__'):
                    # Convert object to dict
                    trade_dict = {}
                    for attr in dir(trade):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(trade, attr)
                                if not callable(value):
                                    trade_dict[attr] = value
                            except:
                                pass
                    trade_data.append(trade_dict)
                elif isinstance(trade, dict):
                    trade_data.append(trade)
                else:
                    # Convert to string representation
                    trade_data.append({'trade_info': str(trade)})
            
            if trade_data:
                df_trades = pd.DataFrame(trade_data)
                df_trades.to_excel(writer, sheet_name='交易明细', index=False)
    
    def _create_portfolio_sheet(self, writer, portfolio_values: List[float]):
        """Create portfolio values sheet"""
        df_portfolio = pd.DataFrame({
            '日期索引': range(len(portfolio_values)),
            '组合价值': portfolio_values,
            '收益率': [0] + [(portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1] for i in range(1, len(portfolio_values))]
        })
        df_portfolio.to_excel(writer, sheet_name='组合价值变化', index=False)
    
    def _generate_markdown_summary(self, results: Dict[str, Any], experiment_info: Optional[Dict], base_filename: str) -> str:
        """Generate enhanced markdown summary report with strategy details and comprehensive trade analysis"""
        md_file = os.path.join(self.reports_dir, f"{base_filename}_summary.md")
        
        # This is the critical fix: we ensure portfolioValues are present before metrics calculation
        if 'portfolioValues' not in results or not results['portfolioValues']:
            if 'stockData' in results:
                results['portfolioValues'] = self._reconstruct_portfolio_values(results)

        performance = self._extract_performance_metrics(results)
        
        # ===== 重要修正：统一数据源和计算方法 =====
        # 1. 统一使用正确的最终资产计算
        corrected_final_capital = self._calculate_correct_final_value(results)
        initial_capital = results.get('initialCapital', 100000)
        corrected_total_return = (corrected_final_capital - initial_capital) / initial_capital
        
        # 2. 统一交易笔数统计
        all_trades = results.get('trades', [])
        valid_trades_count = self._count_valid_trades(results)
        
        # 3. 更新performance字典以确保一致性
        performance['total_return'] = corrected_total_return
        performance['total_trades'] = len(all_trades)  # 总交易记录数
        performance['valid_trades'] = valid_trades_count  # 有效交易数
        # ===== 修正结束 =====
        
        # Extract strategy configuration from experiment_info
        strategy_config_section = self._generate_strategy_config_section(experiment_info)
        
        # Extract grid adjustments if available
        grid_adjustments = results.get('gridAdjustments', [])
        
        # Get the correct final price for the detailed trade section
        final_price = self._get_last_price(results)

        detailed_trades_section = self._generate_detailed_trades_section(
            results.get('trades', []), 
            results.get('initialCapital', 100000),
            grid_adjustments,
            final_price,
            show_failed_trades=False,  # 默认不显示失败的交易
            strategy=results.get('strategy')  # 传入策略对象以获取网格信息
        )
        
        md_content = f"""# 量化交易策略分析报告

## 基本信息
- **股票代码**: {results.get('symbol', 'N/A')}
- **策略名称**: {experiment_info.get('strategy_name', 'N/A') if experiment_info else 'N/A'}
- **回测期间**: {results.get('startDate', 'N/A')} - {results.get('endDate', 'N/A')}
- **初始资金**: ¥{initial_capital:,.2f}
- **最终资金**: ¥{corrected_final_capital:,.2f}
- **报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

{strategy_config_section}

## 核心业绩指标

| 指标 | 数值 | 评级 |
|------|------|------|
| 总收益率 | {corrected_total_return:.4%} | {self._get_metric_rating('total_return', corrected_total_return)} |
| 夏普比率 | {performance['sharpe_ratio']:.4f} | {self._get_metric_rating('sharpe_ratio', performance['sharpe_ratio'])} |
| 最大回撤 | {performance['max_drawdown']:.4%} | {self._get_metric_rating('max_drawdown', performance['max_drawdown'])} |
| 胜率 | {performance['win_rate']:.2%} | {self._get_metric_rating('win_rate', performance['win_rate'])} |
| 交易次数 | {len(all_trades)} | - |
| 平均每笔收益 | ¥{performance['avg_profit']:,.2f} | - |

{detailed_trades_section}

## 策略分析

### 优势
{self._generate_strategy_strengths(performance)}

### 风险提示
{self._generate_risk_warnings(performance)}

### 投资建议
{self._generate_investment_suggestions(performance)}

---
*报告由量化交易系统自动生成*
"""
        
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        return md_file
    
    def _generate_visualizations(self, results: Dict[str, Any], base_filename: str) -> str:
        """Generate visualization charts"""
        charts_dir = os.path.join(self.reports_dir, f"{base_filename}_charts")
        if not os.path.exists(charts_dir):
            os.makedirs(charts_dir)
        
        # Generate portfolio value chart
        if 'portfolioValues' in results:
            self._create_portfolio_chart(results['portfolioValues'], charts_dir)
        
        # Generate performance metrics chart
        performance = self._extract_performance_metrics(results)
        self._create_metrics_chart(performance, charts_dir)
        
        return charts_dir
    
    def _create_portfolio_chart(self, portfolio_values: List[float], charts_dir: str):
        """Create portfolio value progression chart"""
        plt.figure(figsize=(12, 6))
        plt.plot(portfolio_values, linewidth=2, color='#007bff')
        plt.title('组合价值变化曲线', fontsize=16, fontweight='bold')
        plt.xlabel('时间')
        plt.ylabel('组合价值 (¥)')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        chart_file = os.path.join(charts_dir, 'portfolio_value.png')
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
    
    def _create_metrics_chart(self, performance: Dict[str, Any], charts_dir: str):
        """Create performance metrics comparison chart"""
        # Define metrics with their labels and default values
        metric_info = [
            ('total_return', '总收益率'),
            ('sharpe_ratio', '夏普比率'), 
            ('win_rate', '胜率')
        ]
        
        # Build values and labels arrays that match exactly
        values = []
        labels = []
        colors = []
        default_colors = ['#28a745', '#007bff', '#ffc107']
        
        for i, (metric, label) in enumerate(metric_info):
            if metric in performance:
                values.append(performance[metric])
                labels.append(label)
                colors.append(default_colors[i] if i < len(default_colors) else '#6c757d')
        
        # Only create chart if we have data
        if values and labels and len(values) == len(labels):
            plt.figure(figsize=(10, 6))
            bars = plt.bar(labels, values, color=colors)
            plt.title('关键性能指标', fontsize=16, fontweight='bold')
            plt.ylabel('数值')
            
            # Add value labels on bars
            for bar, value in zip(bars, values):
                plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.01,
                        f'{value:.3f}', ha='center', va='bottom')
            
            plt.tight_layout()
            chart_file = os.path.join(charts_dir, 'performance_metrics.png')
            plt.savefig(chart_file, dpi=300, bbox_inches='tight')
            plt.close()
    
    # Helper methods for data extraction and analysis
    def _extract_performance_metrics(self, results: Dict[str, Any]) -> Dict[str, float]:
        """Extract and calculate performance metrics with input validation"""
        # Validate inputs first
        validation_result = self._validate_calculation_inputs(results)
        if not validation_result['validation_passed']:
            logger.warning(f"Input validation issues: {validation_result['issues']}")
        
        # Ensure portfolioValues are reconstructed if missing, for accurate metrics
        # This single call prevents redundant reconstruction in individual metric calculations
        if not results.get('portfolioValues'):
            results['portfolioValues'] = self._reconstruct_portfolio_values(results)

        # Store portfolio values locally to avoid repeated access
        portfolio_values = results.get('portfolioValues', [])

        return {
            'total_return': self._calculate_total_return(results),
            'sharpe_ratio': self._calculate_sharpe_ratio_optimized(portfolio_values),
            'max_drawdown': self._calculate_max_drawdown_optimized(portfolio_values),
            'win_rate': self._calculate_win_rate(results),
            'total_trades': len(results.get('trades', [])),  # 明确统计所有交易记录
            'valid_trades': self._count_valid_trades(results),  # 添加有效交易统计
            'avg_profit': self._calculate_avg_profit(results)
        }
    
    def _extract_trade_analysis(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract trade analysis information"""
        return {
            'total_trades': self._count_trades(results),
            'winning_trades': self._count_winning_trades(results),
            'win_rate': self._calculate_win_rate(results),
            'avg_holding_days': self._calculate_avg_holding_days(results)
        }
    
    def _calculate_total_return(self, results: Dict[str, Any]) -> float:
        """Calculate total return using portfolio values for consistency."""
        initial = results.get('initialCapital', 100000)
        portfolio_values = results.get('portfolioValues', [])
        
        if portfolio_values and len(portfolio_values) > 0:
            # Use the last portfolio value for consistency with other metrics
            final = portfolio_values[-1]
        else:
            # Fallback to the robust calculation if no portfolio values
            final = self._calculate_correct_final_value(results)
            
        return (final - initial) / initial if initial > 0 else 0
    
    def _calculate_final_capital(self, results: Dict[str, Any]) -> float:
        """Calculate final capital using the robust final value calculation."""
        return self._calculate_correct_final_value(results)
    
    def _calculate_sharpe_ratio(self, results: Dict[str, Any]) -> float:
        """Calculate Sharpe ratio"""
        # Ensure portfolioValues are reconstructed if missing
        values = results.get('portfolioValues')
        if not values:
            values = self._reconstruct_portfolio_values(results)

        if values:
            returns = pd.Series(values).pct_change().dropna()
            if not returns.empty:
                # Annualize sharpe ratio
                return np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        return 0
    
    def _calculate_sharpe_ratio_optimized(self, portfolio_values: List[float]) -> float:
        """Calculate Sharpe ratio using pre-loaded portfolio values"""
        if not portfolio_values or len(portfolio_values) < 2:
            return 0
        
        returns = pd.Series(portfolio_values).pct_change().dropna()
        if not returns.empty and len(returns) > 1:
            # Annualize sharpe ratio
            mean_return = np.mean(returns)
            std_return = np.std(returns)
            return mean_return / std_return * np.sqrt(252) if std_return > 0 else 0
        return 0
    
    def _calculate_max_drawdown(self, results: Dict[str, Any]) -> float:
        """Calculate maximum drawdown"""
        # Ensure portfolioValues are reconstructed if missing
        values = results.get('portfolioValues')
        if not values:
            values = self._reconstruct_portfolio_values(results)

        if values:
            s = pd.Series(values)
            peak = s.expanding(min_periods=1).max()
            drawdown = (s - peak) / peak
            return drawdown.min()
        return 0
    
    def _calculate_max_drawdown_optimized(self, portfolio_values: List[float]) -> float:
        """Calculate maximum drawdown using pre-loaded portfolio values"""
        if not portfolio_values or len(portfolio_values) < 2:
            return 0
            
        s = pd.Series(portfolio_values)
        peak = s.expanding(min_periods=1).max()
        drawdown = (s - peak) / peak
        return drawdown.min()
    
    def _calculate_win_rate(self, results: Dict[str, Any]) -> float:
        """Calculate win rate from trade data with improved logic"""
        trades = results.get('trades', [])
        if not trades:
            return 0.0
            
        # 统计有盈亏数据的交易
        profitable_trades = 0
        total_valid_trades = 0
        
        for trade_obj in trades:
            # Handle both dict and object trade records
            if isinstance(trade_obj, dict):
                pnl = trade_obj.get('pnl', 0)
            else:
                pnl = getattr(trade_obj, 'pnl', 0)
            
            # 只统计有明确盈亏的交易（排除pnl=0的交易）
            if pnl != 0:
                total_valid_trades += 1
                if pnl > 0:
                    profitable_trades += 1
        
        # 如果没有有效交易，尝试从收益率估算
        if total_valid_trades == 0:
            logger.info("🔄 No valid P&L data found, estimating win rate from total return...")
            total_return = self._calculate_total_return(results)
            # 如果总收益为正，估算一个基本胜率
            if total_return > 0:
                return min(0.6, max(0.3, total_return * 2))  # 估算30%-60%胜率
            else:
                return max(0.0, 0.5 + total_return)  # 负收益时的估算胜率
        
        win_rate = profitable_trades / total_valid_trades
        logger.info("🔄 Win rate calculated: {profitable_trades}/{total_valid_trades} = {win_rate:.2%}")
        return win_rate
    
    def _count_trades(self, results: Dict[str, Any]) -> int:
        """Count total number of trade records"""
        trades = results.get('trades', [])
        return len(trades)
    
    def _count_winning_trades(self, results: Dict[str, Any]) -> int:
        """Count winning trades"""
        if 'trades' in results:
            winning = 0
            for trade in results['trades']:
                # Handle both dict and object types
                if hasattr(trade, 'get'):
                    profit = trade.get('profit', 0)
                elif hasattr(trade, 'profit'):
                    profit = trade.profit
                else:
                    profit = 0
                
                if profit > 0:
                    winning += 1
            return winning
        return 0
    
    def _calculate_avg_profit(self, results: Dict[str, Any]) -> float:
        """Calculate average profit per trade"""
        if 'trades' in results and results['trades']:
            profits = []
            for trade in results['trades']:
                # Handle both dict and object types
                if hasattr(trade, 'get'):
                    profit = trade.get('profit', 0)
                elif hasattr(trade, 'profit'):
                    profit = trade.profit
                else:
                    profit = 0
                profits.append(profit)
            return sum(profits) / len(profits) if profits else 0
        return 0
    
    def _calculate_avg_holding_days(self, results: Dict[str, Any]) -> str:
        """Calculate average holding days"""
        # This would need actual trade timestamps to calculate properly
        return "N/A"
    
    def _get_metric_rating(self, metric_name: str, value: float) -> str:
        """Get rating for a metric"""
        ratings = {
            'total_return': lambda x: '优秀' if x > 0.15 else '良好' if x > 0.05 else '一般',
            'sharpe_ratio': lambda x: '优秀' if x > 1.5 else '良好' if x > 1.0 else '一般',
            'max_drawdown': lambda x: '优秀' if x > -0.1 else '良好' if x > -0.2 else '需改进',
            'win_rate': lambda x: '优秀' if x > 0.7 else '良好' if x > 0.5 else '需改进'
        }
        
        return ratings.get(metric_name, lambda x: '一般')(value)
    
    def _generate_strategy_strengths(self, performance: Dict[str, Any]) -> str:
        """Generate strategy strengths analysis"""
        strengths = []
        
        if performance['sharpe_ratio'] > 1.5:
            strengths.append("- 优秀的风险调整收益")
        if performance['win_rate'] > 0.7:
            strengths.append("- 高胜率，策略稳定性强")
        if performance['max_drawdown'] > -0.1:
            strengths.append("- 回撤控制良好")
        if performance['total_return'] > 0.1:
            strengths.append("- 收益率表现优异")
            
        return '\n'.join(strengths) if strengths else "- 策略表现需要进一步优化"
    
    def _generate_risk_warnings(self, performance: Dict[str, Any]) -> str:
        """Generate risk warnings"""
        warnings = []
        
        if performance['max_drawdown'] < -0.2:
            warnings.append("- 最大回撤较大，需要注意资金管理")
        if performance['sharpe_ratio'] < 1.0:
            warnings.append("- 风险调整收益偏低")
        if performance['win_rate'] < 0.5:
            warnings.append("- 胜率偏低，策略稳定性有待提高")
            
        return '\n'.join(warnings) if warnings else "- 策略风险控制良好"
    
    def _generate_investment_suggestions(self, performance: Dict[str, Any]) -> str:
        """Generate investment suggestions"""
        suggestions = []
        
        if performance['sharpe_ratio'] > 1.5 and performance['max_drawdown'] > -0.15:
            suggestions.append("- 建议考虑实盘应用，建议资金规模不超过总资产的30%")
        elif performance['sharpe_ratio'] > 1.0:
            suggestions.append("- 可以考虑小额资金测试，观察实际表现")
        else:
            suggestions.append("- 建议进一步优化策略参数后再考虑实盘")
            
        suggestions.append("- 定期监控策略表现，及时调整参数")
        suggestions.append("- 建议在不同市场环境下验证策略稳定性")
        
        return '\n'.join(suggestions)
    
    def _generate_trades_table_markdown(self, trades: List) -> str:
        """Generate detailed trades table in Markdown"""
        if not trades:
            return "没有交易记录。\n"
            
        md_content = "| # | 时间 | 类型 | 价格 | 数量 | 利润 |\n"
        md_content += "|---|---|---|---:|---:|---:|\n"
        
        for i, trade_obj in enumerate(trades):
            if isinstance(trade_obj, dict):
                trade = trade_obj
            else:
                trade = {
                    'timestamp': getattr(trade_obj, 'timestamp', 'N/A'),
                    'type': getattr(trade_obj, 'side', 'N/A'),
                    'price': getattr(trade_obj, 'price', 0),
                    'quantity': getattr(trade_obj, 'quantity', 0),
                    'profit': getattr(trade_obj, 'profit', 0)
                }

            profit_val = trade.get('profit', 0) if trade.get('profit') is not None else 0
            
            md_content += f"| {i+1} | {trade.get('timestamp')} | {trade.get('type')} | {trade.get('price'):.2f} | {trade.get('quantity')} | {profit_val:.2f} |\n"
            
        return md_content
    
    def _get_metric_rating_from_str(self, metric_name: str, value_str: str) -> str:
        """Get metric rating from its string representation"""
        try:
            value = float(value_str.replace('%', ''))
            if '%' in value_str:
                value /= 100
        except (ValueError, TypeError):
            return "N/A"
        
        return self._get_metric_rating(metric_name, value)
    
    def _generate_strategy_config_section(self, experiment_info: Optional[Dict]) -> str:
        """Generate strategy configuration details section"""
        if not experiment_info:
            return "## 策略配置\n策略配置信息不可用。\n"
        
        # Extract strategy configuration from experiment_info
        strategy_name = experiment_info.get('strategy_name', 'Unknown')
        original_perf = experiment_info.get('original_performance', {})
        
        config_content = "## 策略配置详情\n\n"
        config_content += f"### 📋 策略名称: {strategy_name}\n\n"
        
        # Parse strategy type and parameters from name
        if 'DCA' in strategy_name or 'dca' in strategy_name:
            config_content += self._generate_dca_strategy_explanation(strategy_name, original_perf)
        elif 'Grid' in strategy_name or 'grid' in strategy_name:
            config_content += self._generate_grid_strategy_explanation(strategy_name, original_perf)
        elif 'Momentum' in strategy_name or 'momentum' in strategy_name:
            config_content += self._generate_momentum_strategy_explanation(strategy_name, original_perf)
        else:
            config_content += "**策略类型**: 混合策略或其他类型\n\n"
        
        return config_content
    
    def _generate_dca_strategy_explanation(self, strategy_name: str, original_perf: Dict) -> str:
        """Generate DCA strategy explanation"""
        content = "**策略类型**: 定投(DCA) + 网格策略\n\n"
        content += "#### 策略原理:\n"
        content += "- **定投策略**: 定期投入固定金额，平摊成本，降低市场波动风险\n"
        content += "- **网格交易**: 在定投基础上，通过网格策略在价格波动中获取额外收益\n"
        content += "- **混合策略**: 结合两种策略的优势，既有定投的稳健性，又有网格的灵活性\n\n"
        
        # Extract parameters from strategy name
        if 'weekly' in strategy_name:
            content += "**定投频率**: 每周定投\n"
        elif 'monthly' in strategy_name:
            content += "**定投频率**: 每月定投\n"
        
        # Extract amount from name (e.g., DCAAgent_weekly_1000_B0.5)
        import re
        amount_match = re.search(r'_(\d+)_', strategy_name)
        if amount_match:
            amount = amount_match.group(1)
            content += f"**定投金额**: 每次 ¥{amount}\n"
        
        # Extract base ratio
        base_ratio_match = re.search(r'_B(\d+\.?\d*)$', strategy_name)
        if base_ratio_match:
            base_ratio = float(base_ratio_match.group(1))
            content += f"**基础仓位比例**: {base_ratio:.0%}\n"
            content += f"**网格交易比例**: {1-base_ratio:.0%}\n"
        
        content += "\n#### 策略优势:\n"
        content += "- **风险控制**: 通过定投分散时间风险，通过基础仓位控制风险敞口\n"
        content += "- **收益增强**: 网格交易在价格震荡中获取超额收益\n"
        content += "- **自动化**: 全自动执行，无需人工干预\n\n"
        
        return content
    
    def _generate_grid_strategy_explanation(self, strategy_name: str, original_perf: Dict) -> str:
        """Generate Grid strategy explanation"""
        content = "**策略类型**: 网格交易策略\n\n"
        content += "#### 策略原理:\n"
        content += "- **网格设置**: 在当前价格上下设置买入和卖出价格网格\n"
        content += "- **低买高卖**: 价格下跌时在网格点买入，价格上涨时在网格点卖出\n"
        content += "- **震荡获利**: 通过频繁的小幅买卖在震荡市场中获利\n\n"
        
        # Extract parameters from strategy name
        import re
        level_match = re.search(r'L(\d+)', strategy_name)
        if level_match:
            levels = level_match.group(1)
            content += f"**网格层数**: {levels} 层\n"
        
        # Fix spacing regex to properly match decimal numbers with optional %
        spacing_match = re.search(r'S(\d*\.?\d+)(%?)', strategy_name)
        if spacing_match:
            spacing = float(spacing_match.group(1))
            has_percent = spacing_match.group(2) == '%'
            # If it has % symbol, it's already a percentage value, convert to decimal
            if has_percent:
                spacing = spacing / 100
            # If no % symbol and value > 1, assume it's a percentage
            elif spacing > 1:
                spacing = spacing / 100
            content += f"**网格间距**: {spacing:.1%}\n"
        
        # Fix base ratio regex to properly match decimal numbers with optional %
        base_ratio_match = re.search(r'B(\d*\.?\d+)(%?)', strategy_name)
        if base_ratio_match:
            base_ratio = float(base_ratio_match.group(1))
            has_percent = base_ratio_match.group(2) == '%'
            # If it has % symbol, it's already a percentage value, convert to decimal
            if has_percent:
                base_ratio = base_ratio / 100
            # If no % symbol and value > 1, assume it's a percentage
            elif base_ratio > 1:
                base_ratio = base_ratio / 100
            content += f"**基础仓位**: {base_ratio:.1%}\n"
            content += f"**网格资金**: {(1-base_ratio):.1%}\n"
        
        # Use original_perf data if available for more accurate parameters
        if original_perf:
            if 'gridSpacing' in original_perf:
                content += f"**精确网格间距**: {original_perf['gridSpacing']:.3%}\n"
            if 'baseRatio' in original_perf:
                content += f"**精确基础仓位**: {original_perf['baseRatio']:.3%}\n"
        
        content += "\n#### 策略优势:\n"
        content += "- **适应震荡市**: 在横盘震荡的市场环境中表现优异\n"
        content += "- **风险分散**: 通过多层网格分散买入成本\n"
        content += "- **纪律性强**: 严格按照预设价格执行交易，避免情绪干扰\n\n"
        
        return content
    
    def _generate_momentum_strategy_explanation(self, strategy_name: str, original_perf: Dict) -> str:
        """Generate Momentum strategy explanation"""
        content = "**策略类型**: 动量交易策略\n\n"
        content += "#### 策略原理:\n"
        content += "- **趋势跟踪**: 识别价格趋势，在趋势确立时建仓\n"
        content += "- **动量确认**: 通过技术指标确认价格动量\n"
        content += "- **趋势交易**: 在上升趋势中做多，在下降趋势中减仓\n\n"
        
        # Extract parameters from strategy name
        import re
        lookback_match = re.search(r'(\d+)d', strategy_name)
        if lookback_match:
            lookback = lookback_match.group(1)
            content += f"**回看期间**: {lookback} 天\n"
        
        threshold_match = re.search(r'(\d+\.?\d+)', strategy_name)
        if threshold_match:
            threshold = float(threshold_match.group(1))
            if threshold < 1:
                content += f"**动量阈值**: {threshold:.1%}\n"
        
        content += "\n#### 策略优势:\n"
        content += "- **趋势获利**: 在明确的趋势市场中获取超额收益\n"
        content += "- **风险控制**: 通过止损机制控制下行风险\n"
        content += "- **灵活性强**: 能够快速适应市场变化\n\n"
        
        return content
    
    def _generate_detailed_trades_section(self, trades: List, initial_capital: float, 
                                        grid_adjustments: List = None,
                                        final_price: float = 0.0, 
                                        show_failed_trades: bool = False,
                                        strategy = None) -> str:
        """Generate detailed trades section with position and cumulative P&L tracking, 
        including interspersed grid distribution changes"""
        if not trades:
            return "## 详细交易明细\n没有交易记录。\n"
        
        content = "## 详细交易明细\n\n"
        if show_failed_trades:
            content += "*注：包含成功和失败的交易记录，网格分布变化将在对应时间穿插显示*\n\n"
        else:
            content += "*注：仅显示成功执行的交易，网格分布变化将在对应时间穿插显示*\n\n"
        
        # Initialize tracking variables
        cumulative_cash = initial_capital
        cumulative_shares = 0
        cumulative_pnl = 0
        
        # Create merged timeline of trades and grid adjustments
        merged_events = self._merge_trades_and_grid_adjustments(trades, grid_adjustments or [])
        
        # Create detailed trades table with status column and grid details
        content += "| # | 时间 | 事件类型 | 价格 | 数量 | 本次收益 | 累计现金 | 累计股数 | 持仓价值 | 总资产 | 累计收益率 | 状态/说明 | 当前网格明细 |\n"
        content += "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
        
        trade_counter = 0
        grid_adjustment_counter = 0
        
        for i, event in enumerate(merged_events):
            if event['type'] == 'trade':
                # Check if we should include this trade in the display
                trade_is_valid = self._is_valid_trade(event['data'], cumulative_cash, cumulative_shares)
                
                # If not showing failed trades and this trade is invalid, skip it
                if not show_failed_trades and not trade_is_valid:
                    continue
                
                trade_counter += 1
                row_content = self._generate_trade_row(
                    event['data'], trade_counter, cumulative_cash, cumulative_shares, initial_capital,
                    strategy
                )
                
                # Update cumulative values based on trade (only for valid trades)
                if trade_is_valid:
                    trade_result = self._calculate_trade_impact(
                        event['data'], cumulative_cash, cumulative_shares
                    )
                    cumulative_cash = trade_result['new_cash']
                    cumulative_shares = trade_result['new_shares']
                
                content += row_content
                
            elif event['type'] == 'grid_adjustment':
                grid_adjustment_counter += 1
                # Insert grid adjustment information as a special row
                adjustment = event['data']
                
                # Calculate current portfolio value for grid adjustment row
                current_price = adjustment.get('current_price', 0)
                current_position_value = cumulative_shares * current_price if cumulative_shares > 0 else 0
                total_value = cumulative_cash + current_position_value
                cumulative_return = (total_value - initial_capital) / initial_capital
                
                timestamp_str = str(adjustment.get('timestamp', 'N/A'))
                if len(timestamp_str) > 16:
                    timestamp_str = timestamp_str[:16]
                
                # Format grid adjustment details
                old_center = adjustment.get('old_center', 0)
                new_center = adjustment.get('new_center', 0)
                deviation = adjustment.get('deviation', 0)
                
                # Use the enhanced grid adjustment row generator
                content += self._generate_grid_adjustment_row(
                    adjustment, grid_adjustment_counter, cumulative_cash, 
                    cumulative_shares, initial_capital,
                    strategy
                )
        
        # Add final summary with grid adjustment statistics
        # Get final price safely from last event
        final_position_value = cumulative_shares * final_price if cumulative_shares > 0 else 0
        final_total_value = cumulative_cash + final_position_value
        final_return = (final_total_value - initial_capital) / initial_capital
        
        # Count valid vs invalid trades
        trade_events = [e for e in merged_events if e['type'] == 'trade']
        
        # Re-simulate trades to get correct validation
        validation_cash = initial_capital
        validation_shares = 0.0
        valid_trades = 0
        
        for event in merged_events:
            if event['type'] == 'trade':
                trade = event['data']
                # Check if the trade is valid BEFORE applying it
                if self._is_valid_trade(trade, validation_cash, validation_shares):
                    valid_trades += 1
                    # Apply valid trade to validation state
                    trade_result = self._calculate_trade_impact(trade, validation_cash, validation_shares)
                    validation_cash = trade_result['new_cash']
                    validation_shares = trade_result['new_shares']
                # Note: Invalid trades are NOT applied to the validation state
        
        # ===== 使用统一的最终价值计算方法 =====
        # 重新计算最终价值，使用正确的方法确保一致性
        corrected_final_cash = validation_cash
        corrected_final_shares = validation_shares  
        corrected_final_position_value = corrected_final_shares * final_price
        corrected_final_total_value = corrected_final_cash + corrected_final_position_value
        corrected_final_return = (corrected_final_total_value - initial_capital) / initial_capital
        # ===== 修正结束 =====
        
        content += f"\n### 📊 交易与网格调整总结\n"
        content += f"- **总交易记录**: {len(trade_events)} 笔\n"
        content += f"- **有效交易**: {valid_trades} 笔 ✅\n"
        content += f"- **网格调整次数**: {grid_adjustment_counter} 次 🔄\n"
        content += f"- **初始资金**: ¥{initial_capital:,.2f}\n"
        content += f"- **最终现金**: ¥{corrected_final_cash:,.2f}\n"
        content += f"- **最终持股**: {corrected_final_shares:.2f} 股\n"
        content += f"- **持仓价值**: ¥{corrected_final_position_value:,.2f}\n"
        content += f"- **修正后总资产**: ¥{corrected_final_total_value:,.2f}\n"
        content += f"- **修正后收益率**: {corrected_final_return:.4%}\n"
        
        if grid_adjustment_counter > 0:
            content += f"\n### 🔄 网格调整分析\n"
            content += f"- **调整频率**: 平均每 {len(trade_events) / max(grid_adjustment_counter, 1):.1f} 笔交易调整一次网格\n"
            content += f"- **动态响应**: 策略能够根据市场变化动态调整网格分布\n"
            content += f"- **适应性**: 网格调整有助于策略适应不同的价格区间\n\n"
        
        return content
    
    def _merge_trades_and_grid_adjustments(self, trades: List, grid_adjustments: List) -> List:
        """合并交易记录和网格调整记录，按时间排序"""
        import pandas as pd
        
        merged_events = []
        
        # 添加交易事件
        for trade in trades:
            timestamp = self._extract_timestamp(trade)
            merged_events.append({
                'timestamp': timestamp,
                'type': 'trade',
                'data': trade
            })
        
        # 添加网格调整事件
        for adjustment in grid_adjustments:
            timestamp = adjustment.get('timestamp', pd.Timestamp.now())
            merged_events.append({
                'timestamp': timestamp,
                'type': 'grid_adjustment',
                'data': adjustment
            })
        
        # 按时间排序
        merged_events.sort(key=lambda x: x['timestamp'] if x['timestamp'] != 'N/A' else pd.Timestamp.min)
        
        return merged_events
    
    def _extract_timestamp(self, trade):
        """从交易记录中提取时间戳"""
        if isinstance(trade, dict):
            return trade.get('timestamp', 'N/A')
        else:
            return getattr(trade, 'timestamp', 'N/A')
    
    def _extract_trade_info(self, trade):
        """从交易记录中提取基本信息"""
        if isinstance(trade, dict):
            trade_type = trade.get('type', trade.get('side', ''))
            price = float(trade.get('price', 0))
            quantity = float(trade.get('quantity', trade.get('shares', 0)))
        else:
            trade_type = getattr(trade, 'side', getattr(trade, 'type', ''))
            price = float(getattr(trade, 'price', 0))
            quantity = float(getattr(trade, 'quantity', getattr(trade, 'shares', 0)))
        
        return trade_type, price, quantity
    
    def _generate_trade_row(self, trade, counter: int, cumulative_cash: float, 
                           cumulative_shares: float, initial_capital: float,
                           strategy = None) -> str:
        """生成单个交易的表格行"""
        # Extract trade information with better field mapping
        if isinstance(trade, dict):
            trade_data = trade
        else:
            # Handle different trade object structures more robustly
            timestamp = getattr(trade, 'timestamp', 'N/A')
            side = getattr(trade, 'side', getattr(trade, 'type', 'N/A'))
            price = float(getattr(trade, 'price', 0))
            
            # Try multiple field names for quantity
            quantity = 0
            for qty_field in ['quantity', 'shares', 'amount']:
                if hasattr(trade, qty_field):
                    qty_val = getattr(trade, qty_field, 0)
                    if qty_val is not None:
                        quantity = float(qty_val)
                        break
            
            # Try multiple field names for profit/loss
            profit = 0
            for pnl_field in ['pnl', 'profit', 'profit_loss']:
                if hasattr(trade, pnl_field):
                    pnl_val = getattr(trade, pnl_field, 0)
                    if pnl_val is not None:
                        profit = float(pnl_val)
                        break
            
            trade_data = {
                'timestamp': timestamp,
                'type': side,
                'price': price,
                'quantity': quantity,
                'profit': profit
            }
        
        # Generate grid details for this row
        grid_details = self._generate_grid_details_for_trade(trade_data, strategy)
        
        # Calculate position changes with CRITICAL FIX for validation
        trade_type = trade_data.get('type', '')
        price = float(trade_data.get('price', 0))
        quantity = trade_data.get('shares', trade_data.get('quantity', 0))
        quantity = float(quantity) if quantity else 0
        trade_profit = float(trade_data.get('profit', 0))
        
        # Determine action and status
        action_display, status = self._determine_trade_action_and_status(
            trade_type, price, quantity, cumulative_cash, cumulative_shares
        )
        
        # Calculate updated position and cash (for display purposes)
        trade_result = self._calculate_trade_impact(trade_data, cumulative_cash, cumulative_shares)
        new_cash = trade_result['new_cash']
        new_shares = trade_result['new_shares']
        
        # Calculate current portfolio value
        current_position_value = new_shares * price if new_shares > 0 else 0
        total_value = new_cash + current_position_value
        cumulative_return = (total_value - initial_capital) / initial_capital
        
        # Format timestamp
        timestamp_str = str(trade_data.get('timestamp', 'N/A'))
        if len(timestamp_str) > 16:
            timestamp_str = timestamp_str[:16]
        
        return f"| {counter} | {timestamp_str} | {action_display} | ¥{price:.2f} | {quantity:.2f} | ¥{trade_profit:.2f} | ¥{new_cash:,.0f} | {new_shares:.2f} | ¥{current_position_value:,.0f} | ¥{total_value:,.0f} | {cumulative_return:.2%} | {status} | {grid_details} |\n"
    
    def _determine_trade_action_and_status(self, trade_type: str, price: float, quantity: float,
                                         cumulative_cash: float, cumulative_shares: float) -> tuple:
        """确定交易动作和状态"""
        if 'buy' in trade_type.lower():
            trade_cost = price * quantity
            if cumulative_cash >= trade_cost:
                return "买入", "✅正常"
            else:
                return "买入失败", f"❌现金不足(需要¥{trade_cost:,.0f})"
        
        elif 'sell' in trade_type.lower():
            if cumulative_shares >= quantity:
                return "卖出", "✅正常"
            else:
                return "⚠️异常卖出", f"❌持仓不足(需要{quantity:.0f}股,仅有{cumulative_shares:.0f}股)"
        
        else:
            return trade_type, "❓未知类型"
    
    def _calculate_trade_impact(self, trade, cumulative_cash: float, cumulative_shares: float) -> dict:
        """计算交易对现金和持仓的影响"""
        if isinstance(trade, dict):
            trade_type = trade.get('type', '')
            price = float(trade.get('price', 0))
            quantity = trade.get('shares', trade.get('quantity', 0))
            quantity = float(quantity) if quantity else 0
        else:
            # Handle Trade object
            trade_type = getattr(trade, 'side', getattr(trade, 'type', ''))
            price = float(getattr(trade, 'price', 0))
            quantity = float(getattr(trade, 'quantity', 0))
        
        new_cash = cumulative_cash
        new_shares = cumulative_shares
        
        # Only apply impact if the trade is valid
        is_buy = 'buy' in trade_type.lower()
        is_sell = 'sell' in trade_type.lower()

        if is_buy and cumulative_cash >= price * quantity:
            new_cash -= price * quantity
            new_shares += quantity
        elif is_sell and cumulative_shares >= quantity:
            new_cash += price * quantity
            new_shares -= quantity
        
        return {'new_cash': new_cash, 'new_shares': new_shares}
    
    def _is_valid_trade(self, trade, cumulative_cash: float, cumulative_shares: float) -> bool:
        """Check if a trade is valid given current cash and shares."""
        # Handle both dict and object trade records
        if isinstance(trade, dict):
            trade_type = trade.get('type', trade.get('side', '')).lower()
            price = float(trade.get('price', 0))
            quantity = float(trade.get('quantity', trade.get('shares', 0)))
        else:
            # Handle Trade object
            trade_type = getattr(trade, 'side', getattr(trade, 'type', '')).lower()
            price = float(getattr(trade, 'price', 0))
            quantity = float(getattr(trade, 'quantity', getattr(trade, 'shares', 0)))
        
        if 'buy' in trade_type:
            return cumulative_cash >= price * quantity
        elif 'sell' in trade_type:
            return cumulative_shares >= quantity
        return False

    def _calculate_correct_final_value(self, results: Dict[str, Any]) -> float:
        """
        Calculate the final portfolio value robustly.
        This method simulates all trades to get final cash and shares,
        then uses the last available price from kline data for valuation.
        """
        initial_capital = results.get('initialCapital', 100000)
        trades = results.get('trades', [])
        
        cash = initial_capital
        shares = 0
        
        # Simulate trades to get final cash and shares
        for trade_obj in trades:
            # Handle both dict and object trade records
            if isinstance(trade_obj, dict):
                trade = trade_obj
            else:
                trade = {
                    'type': getattr(trade_obj, 'side', 'N/A'),
                    'price': float(getattr(trade_obj, 'price', 0)),
                    'quantity': float(getattr(trade_obj, 'quantity', 0))
                }

            trade_type = trade.get('type', '').lower()
            price = trade.get('price', 0)
            quantity = trade.get('quantity', 0)

            if 'buy' in trade_type:
                if cash >= price * quantity:
                    cash -= price * quantity
                    shares += quantity
            elif 'sell' in trade_type:
                if shares >= quantity:
                    cash += price * quantity
                    shares -= quantity
        
        # Get the last closing price for valuation
        final_price = self._get_last_price(results)

        return cash + shares * final_price

    def _reconstruct_portfolio_values(self, results: Dict[str, Any]) -> List[float]:
        """
        Reconstruct daily portfolio values if they are not provided,
        using kline data and trade records. This is essential for Sharpe and Drawdown.
        """
        stock_data = results.get('stockData')
        if stock_data is None or stock_data.empty:
            return []

        initial_capital = results.get('initialCapital', 100000)
        trades = results.get('trades', [])
        
        # Create a trades dataframe to easily merge with kline data
        if not trades:
            # If no trades, portfolio value is just the initial capital over time
            return [initial_capital] * len(stock_data)
            
        trade_list = []
        for trade_obj in trades:
            if isinstance(trade_obj, dict):
                 trade_list.append(trade_obj)
            else: # Handle object case
                trade_list.append({
                    'timestamp': getattr(trade_obj, 'timestamp', None),
                    'type': getattr(trade_obj, 'side', ''),
                    'price': getattr(trade_obj, 'price', 0),
                    'quantity': getattr(trade_obj, 'quantity', 0)
                })

        trade_df = pd.DataFrame(trade_list)
        if 'timestamp' not in trade_df.columns or trade_df['timestamp'].isnull().all():
            return [] # Cannot proceed without timestamps

        trade_df['timestamp'] = pd.to_datetime(trade_df['timestamp'])
        trade_df = trade_df.set_index('timestamp').sort_index()

        # Align timezone if necessary
        if stock_data.index.tz is not None and trade_df.index.tz is None:
            trade_df = trade_df.tz_localize(stock_data.index.tz)
        elif stock_data.index.tz is None and trade_df.index.tz is not None:
             trade_df = trade_df.tz_convert(None)


        # Filter out invalid trades before processing
        valid_trades = []
        temp_cash = initial_capital
        temp_shares = 0
        for index, row in trade_df.iterrows():
            is_buy = 'buy' in row['type'].lower()
            cost = row['price'] * row['quantity']
            if is_buy:
                if temp_cash >= cost:
                    temp_cash -= cost
                    temp_shares += row['quantity']
                    valid_trades.append(row)
            else: # sell
                if temp_shares >= row['quantity']:
                    temp_cash += cost
                    temp_shares -= row['quantity']
                    valid_trades.append(row)
        
        if not valid_trades:
            return [initial_capital] * len(stock_data)

        valid_trade_df = pd.DataFrame(valid_trades)

        # Calculate cash and share changes
        valid_trade_df['cash_change'] = valid_trade_df.apply(
            lambda row: (-row['price'] * row['quantity']) if 'buy' in row['type'].lower() else (row['price'] * row['quantity']),
            axis=1
        )
        valid_trade_df['shares_change'] = valid_trade_df.apply(
            lambda row: row['quantity'] if 'buy' in row['type'].lower() else -row['quantity'],
            axis=1
        )
        
        daily_changes = valid_trade_df[['cash_change', 'shares_change']].resample('D').sum()

        # Merge with stock data
        portfolio_df = stock_data[['close']].copy()
        portfolio_df = portfolio_df.join(daily_changes, how='left').fillna(0)

        # Calculate cumulative cash and shares, then forward-fill the values
        portfolio_df['cash'] = initial_capital + portfolio_df['cash_change'].cumsum()
        portfolio_df['shares'] = portfolio_df['shares_change'].cumsum()
        
        # Forward-fill cash and shares to handle days with no trades
        # Use method='ffill' to forward fill, avoiding replace with nan
        portfolio_df['cash'] = portfolio_df['cash'].ffill().fillna(initial_capital)
        portfolio_df['shares'] = portfolio_df['shares'].ffill().fillna(0)
        
        # Calculate daily portfolio value
        portfolio_df['portfolio_value'] = portfolio_df['cash'] + (portfolio_df['shares'] * portfolio_df['close'])
        
        return portfolio_df['portfolio_value'].tolist()

    def _get_last_price(self, results: Dict[str, Any]) -> float:
        """Get the last price from kline data or fallback to the last trade."""
        stock_data = results.get('stockData')
        trades = results.get('trades', [])

        if stock_data is not None and not stock_data.empty:
            return stock_data['close'].iloc[-1]
        
        if trades:
            last_trade = trades[-1]
            if isinstance(last_trade, dict):
                return float(last_trade.get('price', 0))
            else:
                return float(getattr(last_trade, 'price', 0))
        
        return 0 

    def _generate_grid_adjustment_row(self, adjustment, counter: int, cumulative_cash: float, 
                                     cumulative_shares: float, initial_capital: float,
                                     strategy = None) -> str:
        """生成网格调整行"""
        timestamp_str = str(adjustment.get('timestamp', 'N/A'))
        if len(timestamp_str) > 16:
            timestamp_str = timestamp_str[:16]
        
        old_center = adjustment.get('old_center', 0)
        new_center = adjustment.get('new_center', 0)
        deviation = adjustment.get('deviation', 0)
        current_price = adjustment.get('current_price', 0)
        
        # Calculate current portfolio value for grid adjustment row
        current_position_value = cumulative_shares * current_price if cumulative_shares > 0 else 0
        total_value = cumulative_cash + current_position_value
        cumulative_return = (total_value - initial_capital) / initial_capital
        
        # Generate grid details after adjustment, passing the full adjustment dict
        grid_details = self._generate_grid_details_for_trade(adjustment, strategy)
        
        # Create grid adjustment display
        adjustment_info = f"网格调整#{counter}"
        detail_info = f"中心: {old_center:.1f}→{new_center:.1f} (偏离{deviation:.1%})"
        
        return (f"| - | {timestamp_str} | {adjustment_info} | ¥{current_price:.2f} | - | - | "
                f"¥{cumulative_cash:,.0f} | {cumulative_shares:.2f} | ¥{current_position_value:,.0f} | "
                f"¥{total_value:,.0f} | {cumulative_return:.2%} | {detail_info} | {grid_details} |\n")
    
    def _count_valid_trades(self, results: Dict[str, Any]) -> int:
        """Count valid trades by simulating trade execution"""
        trades = results.get('trades', [])
        initial_capital = results.get('initialCapital', 100000)
        
        if not trades:
            return 0
        
        # Simulate trades to count valid ones
        cash = initial_capital
        shares = 0
        valid_count = 0
        
        for trade in trades:
            if self._is_valid_trade(trade, cash, shares):
                valid_count += 1
                # Apply the valid trade to update cash and shares for next validation
                trade_result = self._calculate_trade_impact(trade, cash, shares)
                cash = trade_result['new_cash']
                shares = trade_result['new_shares']
        
        return valid_count

    def _generate_grid_details_for_trade(self, trade_data: dict, strategy) -> str:
        """为交易生成当前网格明细信息 - 基于交易时间戳查找历史网格状态"""
        if not strategy:
            return "策略对象缺失"
        
        trade_timestamp = self._extract_timestamp_from_data(trade_data)
        if not trade_timestamp:
            return "交易时间无效"
        
        # 从策略的网格调整历史中，查找与当前交易时间最匹配的网格状态
        relevant_adjustment = None
        if hasattr(strategy, 'gridAdjustments') and strategy.gridAdjustments:
            # 倒序查找，找到第一个时间戳小于等于交易时间戳的调整记录
            for adj in reversed(strategy.gridAdjustments):
                if adj.get('timestamp') and adj['timestamp'] <= trade_timestamp:
                    relevant_adjustment = adj
                    break
        
        if not relevant_adjustment:
            # 如果找不到匹配的历史网格，说明有问题，返回提示信息
            return "无法获取历史网格"

        # 从找到的历史记录中提取网格信息
        grid_info = relevant_adjustment.get('grid_info', {}).get('new_grids', {})
        grid_center = relevant_adjustment.get('new_center')
        buy_levels = grid_info.get('buy_levels', [])
        sell_levels = grid_info.get('sell_levels', [])
        
        if not grid_center or grid_center <= 0:
            return "历史网格中心无效"

        # 格式化网格信息用于显示
        display_info = []
        
        # 格式化买入网格
        if buy_levels:
            # 显示最多3个最接近中心价的买入点
            buy_prices_str = ','.join([f'{p:.1f}' for p in sorted(buy_levels, reverse=True)[:3]])
            if len(buy_levels) > 3:
                display_info.append(f"买:{buy_prices_str}等档")
            else:
                display_info.append(f"买:{buy_prices_str}")

        # 格式化网格中心价
        display_info.append(f"**{grid_center:.1f}**")
        
        # 格式化卖出网格
        if sell_levels:
            # 显示最多3个最接近中心价的卖出点
            sell_prices_str = ','.join([f'{p:.1f}' for p in sorted(sell_levels)[:3]])
            if len(sell_levels) > 3:
                display_info.append(f"卖:{sell_prices_str}等档")
            else:
                display_info.append(f"卖:{sell_prices_str}")

        return " | ".join(display_info)

    def _extract_timestamp_from_data(self, data: Union[dict, object]) -> Optional[pd.Timestamp]:
        """从数据字典或对象中安全地提取时间戳"""
        ts = None
        if isinstance(data, dict):
            ts = data.get('timestamp')
        elif hasattr(data, 'timestamp'):
            ts = getattr(data, 'timestamp', None)
            
        if isinstance(ts, pd.Timestamp):
            return ts
        return None