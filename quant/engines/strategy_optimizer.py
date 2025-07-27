"""
Strategy Optimization Engine
策略优化引擎 - 用于测试和比较不同策略的性能
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
import concurrent.futures
from itertools import product
import random
import itertools
from scipy.optimize import differential_evolution
import time
import warnings
warnings.filterwarnings('ignore')

from ..environments.trading_environment import TradingEnvironment, PerformanceMetrics
from ..agents.strategy_agent import StrategyAgent, AgentConfig, createAgent
from ..data_providers.data_provider_factory import createDataProvider
from ..core.enhanced_report_generator import EnhancedReportGenerator

@dataclass
class ParameterSpace:
    """参数空间定义"""
    name: str
    minValue: Optional[float] = None
    maxValue: Optional[float] = None
    step: Optional[float] = None
    values: Optional[List] = None
    paramType: str = 'continuous'  # 'continuous', 'discrete', 'categorical'

@dataclass
class OptimizationResult:
    """优化结果"""
    agentName: str
    agentConfig: AgentConfig
    performance: PerformanceMetrics
    simulationDetails: Dict[str, Any]
    executionTime: float
    score: float = 0.0
    iteration: int = 0

@dataclass
class OptimizationSummary:
    """优化汇总"""
    symbol: str
    timeRange: str
    totalAgents: int
    bestAgent: OptimizationResult
    topAgents: List[OptimizationResult]
    performanceComparison: Dict[str, Any]
    recommendations: List[str]

class StrategyOptimizer:
    """策略优化引擎"""
    
    def __init__(self, dataProvider=None, maxWorkers: int = 4):
        self.dataProvider = dataProvider or createDataProvider('auto')
        self.maxWorkers = maxWorkers
        self.logger = logging.getLogger(__name__)
        
        # Results storage
        self.optimizationResults: List[OptimizationResult] = []
        self.lastOptimization: Optional[OptimizationSummary] = None
        
        # Advanced optimization settings
        self.parameterSpace: Dict[str, ParameterSpace] = {}
        self.bestResult: Optional[OptimizationResult] = None
    
    def generateAgentVariants(self, symbol: str, strategyTypes: List[str] = None, 
                            customConfigs: List[Dict] = None) -> List[AgentConfig]:
        """生成策略代理变体 - 调整参数范围减少交易频率"""
        if strategyTypes is None:
            strategyTypes = ['grid']
        
        agentConfigs = []
        
        # Add custom configurations if provided
        if customConfigs:
            for config in customConfigs:
                agentConfigs.append(AgentConfig(**config))
        
        # Generate standard variants for each strategy type
        for strategyType in strategyTypes:
            variants = self._generateStrategyVariants(strategyType, symbol)
            agentConfigs.extend(variants)
        
        self.logger.info(f"Generated {len(agentConfigs)} agent variants for {symbol}")
        return agentConfigs
    
    def _generateStrategyVariants(self, strategyType: str, symbol: str) -> List[AgentConfig]:
        """为特定策略类型生成变体 - 包含传统网格和自适应学习网格"""
        variants = []
        
        if strategyType == 'grid':
            # 减少参数组合，专注于低频交易策略
            gridLevels = [6, 8]                    # 减少网格层数选择
            gridSpacings = [0.015, 0.020, 0.025]  # 增大网格间距，减少交易频率
            baseRatios = [0.2, 0.3, 0.4]          # 提高基准仓位，减少小额交易
            
            # 传统动态调整参数组合
            traditional_configs = [
                # 保守调整
                {'dynamicEnabled': True, 'adjustmentThreshold': 0.15, 'minAdjustmentRatio': 0.08, 'adjustmentCooldown': 10, 'centerPricePeriod': 30, 'centerPriceMethod': 'sma'},
                # 适中调整（默认推荐）
                {'dynamicEnabled': True, 'adjustmentThreshold': 0.10, 'minAdjustmentRatio': 0.05, 'adjustmentCooldown': 5, 'centerPricePeriod': 20, 'centerPriceMethod': 'sma'},
                # 积极调整
                {'dynamicEnabled': True, 'adjustmentThreshold': 0.08, 'minAdjustmentRatio': 0.03, 'adjustmentCooldown': 3, 'centerPricePeriod': 15, 'centerPriceMethod': 'ema'},
                # 静态网格（不调整）
                {'dynamicEnabled': False, 'adjustmentThreshold': 0.10, 'minAdjustmentRatio': 0.05, 'adjustmentCooldown': 5, 'centerPricePeriod': 20, 'centerPriceMethod': 'sma'}
            ]
            
            for levels in gridLevels:
                for spacing in gridSpacings:
                    for ratio in baseRatios:
                        for i, dynamicConfig in enumerate(traditional_configs):
                            # 基础参数
                            params = {
                                'gridLevels': levels,
                                'gridSpacing': spacing,
                                'baseRatio': ratio,
                                'maxPosition': 100000,
                                'commission': 0.0003
                            }
                            # 添加动态调整参数
                            params.update(dynamicConfig)
                            
                            # 生成配置名称
                            dynamicSuffix = f"_{'Dyn' if dynamicConfig['dynamicEnabled'] else 'Static'}{i+1}"
                            
                            config = AgentConfig(
                                strategyType='grid',
                                parameters=params,
                                riskProfile='moderate',
                                name=f'Grid_L{levels}_S{spacing:.3f}_B{ratio:.1f}{dynamicSuffix}',
                                description=f'Grid trading with {levels} levels, {spacing:.1%} spacing, {ratio:.1%} base, {"dynamic" if dynamicConfig["dynamicEnabled"] else "static"} adjustment'
                            )
                            variants.append(config)
        
        return variants
    
    def runOptimization(self, symbol: str, startDate: str, endDate: str,
                       agentConfigs: List[AgentConfig] = None,
                       initialCapital: float = 100000,
                       parallelExecution: bool = False) -> OptimizationSummary:
        """运行策略优化"""
        self.logger.info(f"Starting optimization for {symbol} from {startDate} to {endDate}")
        
        # Generate agent configurations if not provided
        if agentConfigs is None:
            agentConfigs = self.generateAgentVariants(symbol)
        
        # Clear previous results
        self.optimizationResults = []
        
        # Run simulations
        if parallelExecution and self.maxWorkers > 1:
            results = self._runParallelSimulations(
                symbol, startDate, endDate, agentConfigs, initialCapital
            )
        else:
            results = self._runSequentialSimulations(
                symbol, startDate, endDate, agentConfigs, initialCapital
            )
        
        self.optimizationResults = results
        
        # Analyze results and create summary
        summary = self._createOptimizationSummary(symbol, startDate, endDate, results)
        self.lastOptimization = summary
        
        self.logger.info(f"Optimization completed. Tested {len(results)} strategies.")
        return summary
    
    def _runParallelSimulations(self, symbol: str, startDate: str, endDate: str,
                              agentConfigs: List[AgentConfig], 
                              initialCapital: float) -> List[OptimizationResult]:
        """并行运行模拟"""
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.maxWorkers) as executor:
            # Submit all simulation tasks
            futures = []
            for config in agentConfigs:
                future = executor.submit(
                    self._runSingleSimulation, 
                    symbol, startDate, endDate, config, initialCapital
                )
                futures.append(future)
            
            # Collect results
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except Exception as e:
                    self.logger.error(f"Simulation failed: {str(e)}")
        
        return results
    
    def _runSequentialSimulations(self, symbol: str, startDate: str, endDate: str,
                                agentConfigs: List[AgentConfig], 
                                initialCapital: float) -> List[OptimizationResult]:
        """顺序运行模拟"""
        results = []
        
        for i, config in enumerate(agentConfigs):
            self.logger.info(f"Running simulation {i+1}/{len(agentConfigs)}: {config.name}")
            
            result = self._runSingleSimulation(symbol, startDate, endDate, config, initialCapital)
            if result:
                results.append(result)
        
        return results
    
    def _runSingleSimulation(self, symbol: str, startDate: str, endDate: str,
                           config: AgentConfig, initialCapital: float) -> Optional[OptimizationResult]:
        """运行单个策略模拟 - 支持传统网格和自适应网格策略"""
        startTime = datetime.now()
        
        try:
            # 检查配置中指定的策略类型
            strategy_class = config.parameters.get('strategy_class', 'UnifiedGridTradingStrategy')
            
            if strategy_class == 'AdaptiveGridStrategy':
                # 使用自适应网格策略
                try:
                    from ..strategies.adaptive_grid_strategy import AdaptiveGridStrategy
                    
                    # 为自适应策略创建特殊的配置
                    adaptive_config = config.parameters.copy()
                    adaptive_config.pop('strategy_class', None)  # 移除策略类标识
                    
                    # 创建自适应策略实例
                    strategy = AdaptiveGridStrategy(symbol, adaptive_config)
                    
                    # 使用自适应策略运行回测
                    results = strategy.run_adaptive_backtest(
                        startDate=startDate,
                        endDate=endDate,
                        initialCapital=initialCapital
                    )
                    
                except ImportError as e:
                    self.logger.warning(f"AdaptiveGridStrategy not available: {e}, falling back to BacktestEngine")
                    # 回退到使用BacktestEngine
                    results = self._runWithBacktestEngine(symbol, startDate, endDate, config, initialCapital)
                    
            else:
                # 使用传统的BacktestEngine方式
                results = self._runWithBacktestEngine(symbol, startDate, endDate, config, initialCapital)
            
            # 处理结果格式统一
            return self._processSimulationResults(config, results, startTime, initialCapital)
                
        except Exception as e:
            self.logger.error(f"Simulation failed for {config.name}: {str(e)}")
            return None
    
    def _runWithBacktestEngine(self, symbol: str, startDate: str, endDate: str,
                             config: AgentConfig, initialCapital: float) -> Dict:
        """使用BacktestEngine运行回测"""
        from ..engines.backtest_engine import BacktestEngine
        
        # Create backtest engine
        backtestEngine = BacktestEngine(self.dataProvider)
        
        # 清理配置参数，移除自定义字段
        clean_config = config.parameters.copy()
        clean_config.pop('strategy_class', None)
        clean_config.pop('enable_learning', None)
        clean_config.pop('model_update_frequency', None)
        clean_config.pop('min_learning_samples', None)
        clean_config.pop('feature_window', None)
        
        # Run backtest using the tested and fixed engine
        results = backtestEngine.runBacktest(
            symbol=symbol,
            startDate=startDate,
            endDate=endDate,
            initialCapital=initialCapital,
            strategyConfig=clean_config
        )
        
        return results
    
    def _processSimulationResults(self, config: AgentConfig, results: Dict,
                                startTime: datetime, initialCapital: float) -> OptimizationResult:
        """处理仿真结果并创建优化结果对象"""
        
        # Extract performance metrics  
        performance_dict = results.get('performance', {})
        
        # Create performance object with validated data - ensure all required fields are present
        performance = PerformanceMetrics(
            totalReturn=performance_dict.get('totalReturn', 0.0),
            annualizedReturn=performance_dict.get('annualizedReturn', 0.0),
            sharpeRatio=performance_dict.get('sharpeRatio', 0.0),
            maxDrawdown=performance_dict.get('maxDrawdown', 0.0),
            winRate=performance_dict.get('winRate', 0.0),
            profitLossRatio=performance_dict.get('profitLossRatio', 0.0),  # 添加缺失的参数
            totalTrades=performance_dict.get('totalTrades', 0),
            volatility=performance_dict.get('volatility', 0.0),
            alpha=performance_dict.get('alpha', 0.0),  # 添加缺失的参数
            beta=performance_dict.get('beta', 1.0),   # 添加缺失的参数
            avgTradeReturn=performance_dict.get('avgTradeReturn', 0.0)
        )
        
        # Collect simulation details from backtest results
        simulationDetails = {
            'totalSteps': len(results.get('portfolio_values', [])),
            'totalTrades': performance.totalTrades,
            # 优先使用 performance 字典中的 finalValue，保证与回测报告一致
            'finalValue': results.get('final_value',
                                     results.get('performance', {}).get('finalValue', initialCapital)),
            'tradeHistory': results.get('trades', []),  # Keep all trades for detailed analysis
            'valueHistory': results.get('portfolio_values', []),  # Keep all portfolio values
            'gridAdjustments': results.get('gridAdjustments', []),  # Fixed: correct key name without underscore
            'strategy_summary': results.get('strategy_summary', {}),
            'strategy_type': config.parameters.get('strategy_class', 'UnifiedGridTradingStrategy'),
            'learning_enabled': config.parameters.get('enable_learning', False),
            'strategy': results.get('strategy'),  # 确保策略对象被保存
            'symbol': results.get('symbol', ''),
            'initialCapital': initialCapital,
            'stockData': results.get('stockData')
        }
        
        # Calculate execution time
        executionTime = (datetime.now() - startTime).total_seconds()
        
        # Calculate comprehensive score
        score = self.calculateScore(performance)
        
        # Create and return optimization result
        result = OptimizationResult(
            agentName=config.name,
            agentConfig=config,
            performance=performance,
            simulationDetails=simulationDetails,
            executionTime=executionTime,
            score=score
        )
        
        return result
    
    def _generateAgentName(self, config: AgentConfig) -> str:
        """Generate agent name based on config parameters"""
        params = config.parameters
        if config.strategyType == 'grid':
            levels = params.get('gridLevels', 0)
            spacing = params.get('gridSpacing', 0)
            baseRatio = params.get('baseRatio', 0)
            trendPeriod = params.get('centerPricePeriod', 20)  # Default trend period
            return f"TrendGrid_L{levels}_S{spacing:.0%}_B{baseRatio:.0%}_T{trendPeriod}"
        else:
            return config.name
    
    def _createOptimizationSummary(self, symbol: str, startDate: str, endDate: str,
                                 results: List[OptimizationResult]) -> OptimizationSummary:
        """创建优化汇总"""
        if not results:
            return OptimizationSummary(
                symbol=symbol,
                timeRange=f"{startDate} to {endDate}",
                totalAgents=0,
                bestAgent=None,
                topAgents=[],
                performanceComparison={},
                recommendations=["No valid results obtained"]
            )
        
        # FIXED: Sort by comprehensive score combining return, sharpe, and drawdown
        # Avoid selecting negative return strategies as "best"
        def calculate_comprehensive_score(result):
            perf = result.performance
            total_return = perf.totalReturn
            sharpe_ratio = perf.sharpeRatio
            max_drawdown = abs(perf.maxDrawdown)  # Convert to positive
            
            # Heavily penalize negative returns
            if total_return < 0:
                return -1000 + total_return  # Large negative penalty
            
            # Calculate weighted score: 40% return + 40% sharpe + 20% drawdown control
            return (total_return * 0.4 + 
                   min(sharpe_ratio, 3.0) * 0.4 +  # Cap sharpe at 3.0 to avoid outliers
                   max(0.2 - max_drawdown, -0.5) * 0.2)  # Reward low drawdown
        
        sortedResults = sorted(
            results, 
            key=calculate_comprehensive_score,
            reverse=True
        )
        
        bestAgent = sortedResults[0]
        topAgents = sortedResults[:10]  # Top 10 strategies
        
        # Create performance comparison
        performanceComparison = {
            'bestReturn': max(r.performance.totalReturn for r in results),
            'worstReturn': min(r.performance.totalReturn for r in results),
            'averageReturn': np.mean([r.performance.totalReturn for r in results]),
            'bestSharpe': max(r.performance.sharpeRatio for r in results),
            'averageSharpe': np.mean([r.performance.sharpeRatio for r in results]),
            'bestMaxDrawdown': min(r.performance.maxDrawdown for r in results),
            'averageMaxDrawdown': np.mean([r.performance.maxDrawdown for r in results]),
            'strategyTypePerformance': self._analyzeStrategyTypePerformance(results)
        }
        
        # Generate recommendations
        recommendations = self._generateRecommendations(results, bestAgent)
        
        return OptimizationSummary(
            symbol=symbol,
            timeRange=f"{startDate} to {endDate}",
            totalAgents=len(results),
            bestAgent=bestAgent,
            topAgents=topAgents,
            performanceComparison=performanceComparison,
            recommendations=recommendations
        )
    
    def _analyzeStrategyTypePerformance(self, results: List[OptimizationResult]) -> Dict[str, Dict]:
        """分析不同策略类型的性能"""
        strategyPerformance = {}
        
        for result in results:
            strategyType = result.agentConfig.strategyType
            if strategyType not in strategyPerformance:
                strategyPerformance[strategyType] = {
                    'count': 0,
                    'totalReturns': [],
                    'sharpeRatios': [],
                    'maxDrawdowns': []
                }
            
            strategyPerformance[strategyType]['count'] += 1
            strategyPerformance[strategyType]['totalReturns'].append(result.performance.totalReturn)
            strategyPerformance[strategyType]['sharpeRatios'].append(result.performance.sharpeRatio)
            strategyPerformance[strategyType]['maxDrawdowns'].append(result.performance.maxDrawdown)
        
        # Calculate averages for each strategy type
        for strategyType, data in strategyPerformance.items():
            data['avgReturn'] = np.mean(data['totalReturns'])
            data['avgSharpe'] = np.mean(data['sharpeRatios'])
            data['avgMaxDrawdown'] = np.mean(data['maxDrawdowns'])
            data['bestReturn'] = max(data['totalReturns'])
            data['bestSharpe'] = max(data['sharpeRatios'])
        
        return strategyPerformance
    
    def _generateRecommendations(self, results: List[OptimizationResult], 
                               bestAgent: OptimizationResult) -> List[str]:
        """生成投资建议"""
        recommendations = []
        
        # Best strategy recommendation
        recommendations.append(
            f"最佳策略: {bestAgent.agentName} "
            f"(收益率: {bestAgent.performance.totalReturn:.2%}, "
            f"夏普比率: {bestAgent.performance.sharpeRatio:.2f})"
        )
        
        # Risk assessment
        if bestAgent.performance.maxDrawdown > 0.15:
            recommendations.append(
                f"注意: 最佳策略的最大回撤较高 ({bestAgent.performance.maxDrawdown:.2%}), "
                "建议考虑风险控制措施"
            )
        
        # Strategy type analysis
        strategyTypePerf = self._analyzeStrategyTypePerformance(results)
        bestStrategyType = max(strategyTypePerf.keys(), 
                             key=lambda x: strategyTypePerf[x]['avgSharpe'])
        recommendations.append(
            f"表现最佳的策略类型: {bestStrategyType} "
            f"(平均夏普比率: {strategyTypePerf[bestStrategyType]['avgSharpe']:.2f})"
        )
        
        # Parameter insights
        if bestAgent.agentConfig.strategyType == 'grid':
            params = bestAgent.agentConfig.parameters
            recommendations.append(
                f"网格策略优化参数: 层数={params.get('gridLevels')}, "
                f"间距={params.get('gridSpacing'):.1%}, "
                f"基础仓位={params.get('baseRatio'):.1%}"
            )
        
        # Market condition insights
        avgVolatility = np.mean([r.performance.volatility for r in results])
        if avgVolatility > 0.3:
            recommendations.append("市场波动较大，建议采用较保守的参数设置")
        elif avgVolatility < 0.15:
            recommendations.append("市场波动较小，可以考虑更积极的策略参数")
        
        return recommendations
    
    def saveResults(self, outputDir: str = "reports") -> str:
        """保存优化结果"""
        if not self.lastOptimization:
            raise ValueError("No optimization results to save")
        
        # Create timestamped directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        reportDir = Path(outputDir) / timestamp / "strategy_optimization"
        reportDir.mkdir(parents=True, exist_ok=True)
        
        # Save original JSON reports for compatibility
        summaryPath = reportDir / "optimization_summary.json"
        with open(summaryPath, 'w', encoding='utf-8') as f:
            # Convert dataclasses to dict for JSON serialization
            summaryDict = asdict(self.lastOptimization)
            # Handle nested dataclasses
            if summaryDict['bestAgent']:
                summaryDict['bestAgent'] = self._convertResultToDict(summaryDict['bestAgent'])
            summaryDict['topAgents'] = [
                self._convertResultToDict(agent) for agent in summaryDict['topAgents']
            ]
            json.dump(summaryDict, f, ensure_ascii=False, indent=2, default=str)
        
        # Save detailed results
        detailsPath = reportDir / "detailed_results.json"
        with open(detailsPath, 'w', encoding='utf-8') as f:
            resultsDict = [self._convertResultToDict(result) for result in self.optimizationResults]
            json.dump(resultsDict, f, ensure_ascii=False, indent=2, default=str)
        
        # Create performance comparison DataFrame and save as Excel
        self._createPerformanceReport(reportDir)
        
        # Generate enhanced human-readable reports
        self._generateInterpretableReports(reportDir)
        
        self.logger.info(f"Optimization results saved to {reportDir}")
        return str(reportDir)
    
    def _convertResultToDict(self, result) -> dict:
        """转换OptimizationResult为字典"""
        if isinstance(result, OptimizationResult):
            result = asdict(result)
        elif isinstance(result, dict):
            # Already a dictionary, just ensure nested objects are converted
            pass
        else:
            # Try to convert to dict
            result = asdict(result)
        
        # Convert AgentConfig
        if 'agentConfig' in result and not isinstance(result['agentConfig'], dict):
            result['agentConfig'] = asdict(result['agentConfig'])
        
        # Convert PerformanceMetrics
        if 'performance' in result and not isinstance(result['performance'], dict):
            result['performance'] = asdict(result['performance'])
        
        return result
    
    def _createPerformanceReport(self, reportDir: Path):
        """创建性能对比报告"""
        # Create DataFrame from results
        data = []
        for result in self.optimizationResults:
            row = {
                'Strategy': result.agentName,
                'Type': result.agentConfig.strategyType,
                'Total Return (%)': result.performance.totalReturn * 100,
                'Annualized Return (%)': result.performance.annualizedReturn * 100,
                'Sharpe Ratio': result.performance.sharpeRatio,
                'Max Drawdown (%)': result.performance.maxDrawdown * 100,
                'Win Rate (%)': result.performance.winRate * 100,
                'Profit/Loss Ratio': result.performance.profitLossRatio,
                'Total Trades': result.performance.totalTrades,
                'Volatility (%)': result.performance.volatility * 100,
                'Alpha': result.performance.alpha,
                'Beta': result.performance.beta,
                'Execution Time (s)': result.executionTime
            }
            
            # Add strategy-specific parameters
            params = result.agentConfig.parameters
            if result.agentConfig.strategyType == 'grid':
                row['Grid Levels'] = params.get('gridLevels', '')
                row['Grid Spacing (%)'] = params.get('gridSpacing', 0) * 100
                row['Base Ratio (%)'] = params.get('baseRatio', 0) * 100
            elif result.agentConfig.strategyType == 'dca':
                row['Interval'] = params.get('interval', '')
                row['Amount'] = params.get('amount', '')
                row['Base Ratio (%)'] = params.get('baseRatio', 0) * 100
            elif result.agentConfig.strategyType == 'momentum':
                row['Lookback Period'] = params.get('lookbackPeriod', '')
                row['Threshold (%)'] = params.get('threshold', 0) * 100
                row['Base Ratio (%)'] = params.get('baseRatio', 0) * 100
            
            data.append(row)
        
        df = pd.DataFrame(data)
        
        # Check if we have data before sorting
        if df.empty:
            self.logger.warning("No optimization results available for performance report")
            return
        
        # Sort by Sharpe ratio
        df = df.sort_values('Sharpe Ratio', ascending=False)
        
        # Save as Excel
        excelPath = reportDir / "performance_comparison.xlsx"
        with pd.ExcelWriter(excelPath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='All Results', index=False)
            
            # Create summary sheet
            summary_data = {
                'Metric': ['Best Total Return', 'Best Sharpe Ratio', 'Best Max Drawdown', 
                          'Average Total Return', 'Average Sharpe Ratio', 'Average Max Drawdown'],
                'Value': [
                    f"{df['Total Return (%)'].max():.2f}%",
                    f"{df['Sharpe Ratio'].max():.2f}",
                    f"{df['Max Drawdown (%)'].min():.2f}%",
                    f"{df['Total Return (%)'].mean():.2f}%",
                    f"{df['Sharpe Ratio'].mean():.2f}",
                    f"{df['Max Drawdown (%)'].mean():.2f}%"
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
            
            # Create top 10 sheet
            df.head(10).to_excel(writer, sheet_name='Top 10', index=False)
    
    def _generateInterpretableReports(self, reportDir: Path):
        """Generate interpretable reports for the best strategy using enhanced report generator"""
        try:
            from quant.core.enhanced_report_generator import EnhancedReportGenerator
            
            if not hasattr(self, 'lastOptimization') or not self.lastOptimization:
                self.logger.warning("No optimization results available for report generation")
                return
                
            bestAgent = self.lastOptimization.bestAgent
            generator = EnhancedReportGenerator(reports_dir=str(reportDir))
            
            # CRITICAL FIX: Extract the original date range used in comprehensiveOptimization
            # The bestAgent contains BACKTEST period results, but we need the FULL period for consistent reporting
            
            # Find the full date range from the lastOptimization context
            time_range_parts = self.lastOptimization.timeRange.split(' to ')
            if len(time_range_parts) == 2:
                # This is the backtest period, we need to reconstruct the full period
                backtest_start = time_range_parts[0]
                backtest_end = time_range_parts[1]
                
                # Get the full period from the comprehensive optimization context
                # Store these during comprehensiveOptimization for consistency
                if hasattr(self, '_fullPeriodStart') and hasattr(self, '_fullPeriodEnd'):
                    full_start = self._fullPeriodStart
                    full_end = self._fullPeriodEnd
                    self.logger.info(f"Using stored full period: {full_start} to {full_end}")
                else:
                    # Fallback: use backtest period (may cause inconsistency but won't fail)
                    full_start = backtest_start
                    full_end = backtest_end
                    self.logger.warning(f"Full period not stored, using backtest period: {full_start} to {full_end}")
            else:
                # Fallback to whatever is in timeRange
                full_start = self.lastOptimization.timeRange.split(' to ')[0] if ' to ' in self.lastOptimization.timeRange else '2017-01-01'
                full_end = self.lastOptimization.timeRange.split(' to ')[1] if ' to ' in self.lastOptimization.timeRange else '2024-12-31'
                
            # CRITICAL FIX: Run backtest with the SAME CONFIG on the FULL period for consistent reporting
            try:
                from quant.engines.backtest_engine import BacktestEngine
                
                backtest_engine = BacktestEngine(self.dataProvider)
                
                self.logger.info(f"Running full period backtest for detailed report: {full_start} to {full_end}")
                
                fresh_results = backtest_engine.runBacktest(
                    symbol=self.lastOptimization.symbol,
                    startDate=full_start,
                    endDate=full_end,
                    initialCapital=100000,
                    strategyConfig=bestAgent.agentConfig.parameters
                )
                
                # Use the fresh results for the detailed report
                stock_data = fresh_results.get('stockData')
                
                # Override the performance metrics with fresh calculation
                fresh_performance = fresh_results.get('performance', {})
                
            except Exception as e:
                self.logger.error(f"Could not run fresh backtest for full period: {e}")
                # Fallback to using the backtest period results with strategy object if available
                fresh_results = {
                    'symbol': self.lastOptimization.symbol,
                    'startDate': backtest_start,
                    'endDate': backtest_end,
                    'performance': asdict(bestAgent.performance),
                    'trades': bestAgent.simulationDetails.get('tradeHistory', []),
                    'portfolioValues': bestAgent.simulationDetails.get('valueHistory', []),
                    'gridAdjustments': bestAgent.simulationDetails.get('gridAdjustments', []),
                    'initialCapital': 100000,
                    'stockData': None,
                    'strategy': bestAgent.simulationDetails.get('strategy')  # 确保策略对象在备用方案中也被包含
                }
                stock_data = None
                fresh_performance = asdict(bestAgent.performance)
            
            # Create backtest-like results structure with CORRECTED data sources
            backtest_results = {
                'symbol': self.lastOptimization.symbol,
                'startDate': full_start,
                'endDate': full_end,
                'performance': fresh_performance,
                'trades': fresh_results.get('trades', bestAgent.simulationDetails.get('tradeHistory', [])),
                'portfolioValues': fresh_results.get('portfolioValues', bestAgent.simulationDetails.get('valueHistory', [])),
                'gridAdjustments': fresh_results.get('gridAdjustments', bestAgent.simulationDetails.get('gridAdjustments', [])),
                'initialCapital': 100000,
                'stockData': stock_data,
                'strategy': fresh_results.get('strategy', bestAgent.simulationDetails.get('strategy'))  # 确保策略对象被包含
            }
            
            # Create experiment info
            experiment_info = {
                'strategy_name': bestAgent.agentName,
                'optimization_summary': {
                    'total_agents_tested': self.lastOptimization.totalAgents,
                    'best_score': bestAgent.score,
                    'optimization_methods': ['综合优化'],
                    'top_performers': len(self.lastOptimization.topAgents),
                    'data_split_info': f"优化期到回测期分离，确保无前瞻偏差"
                },
                'original_performance': bestAgent.agentConfig.parameters
            }
            
            # Generate comprehensive interpretable reports
            report_files = generator.generate_comprehensive_report(
                backtest_results=backtest_results,
                experiment_info=experiment_info,
                symbol=self.lastOptimization.symbol
            )
            
            # Generate optimization-specific interpretable summary
            self._generateOptimizationSummaryReport(reportDir)
            
            self.logger.info(f"Generated interpretable reports: {list(report_files.keys())}")
            
        except Exception as e:
            self.logger.error(f"Failed to generate interpretable reports: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't fail the entire save process if interpretable reports fail
    
    def _generateOptimizationSummaryReport(self, reportDir: Path):
        """生成优化过程总结报告"""
        try:
            summary_file = reportDir / "optimization_summary_readable.md"
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                # CRITICAL FIX: Display clear time range information
                time_range_info = self.lastOptimization.timeRange
                if hasattr(self, '_fullPeriodStart') and hasattr(self, '_fullPeriodEnd'):
                    time_range_info = f"{self._fullPeriodStart} to {self._fullPeriodEnd}"
                    optimization_info = f"优化期: {self._fullPeriodStart} to {self._optimizationPeriodEnd}, 回测期: {self._backtestPeriodStart} to {self._fullPeriodEnd}"
                else:
                    optimization_info = f"回测期间: {self.lastOptimization.timeRange}"
                
                f.write(f"""# 策略优化分析报告

## 基本信息
- **股票代码**: {self.lastOptimization.symbol}
- **数据期间**: {time_range_info}
- **数据分割**: {optimization_info}
- **测试策略数量**: {self.lastOptimization.totalAgents}个
- **报告生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 优化结果概览

### 🏆 最佳策略 (样本外回测结果)
- **策略名称**: {self.lastOptimization.bestAgent.agentName}
- **策略类型**: {self.lastOptimization.bestAgent.agentConfig.strategyType}
- **总收益率**: {self.lastOptimization.bestAgent.performance.totalReturn:.2%}
- **夏普比率**: {self.lastOptimization.bestAgent.performance.sharpeRatio:.3f}
- **最大回撤**: {self.lastOptimization.bestAgent.performance.maxDrawdown:.2%}
- **胜率**: {self.lastOptimization.bestAgent.performance.winRate:.1%}
- **总交易次数**: {self.lastOptimization.bestAgent.performance.totalTrades}
- **综合评分**: {self.lastOptimization.bestAgent.score:.2f}

> **说明**: 以上指标基于样本外回测期间的表现，避免了过拟合风险。详细报告显示完整数据期间的表现。

### 📊 参数配置
""")
                
                # Add strategy-specific parameters
                params = self.lastOptimization.bestAgent.agentConfig.parameters
                for param_name, param_value in params.items():
                    if isinstance(param_value, float):
                        if param_name in ['baseRatio', 'gridSpacing']:
                            f.write(f"- **{param_name}**: {param_value:.1%}\n")
                        else:
                            f.write(f"- **{param_name}**: {param_value:.4f}\n")
                    else:
                        f.write(f"- **{param_name}**: {param_value}\n")
                
                f.write(f"""
## 🔍 性能分析

### 收益能力
""")
                total_return = self.lastOptimization.bestAgent.performance.totalReturn
                if total_return > 0.15:
                    f.write("✅ **优秀**: 总收益率超过15%，表现优异\n")
                elif total_return > 0.05:
                    f.write("✅ **良好**: 总收益率超过5%，表现良好\n")
                elif total_return > 0:
                    f.write("⚠️ **一般**: 总收益率为正，但收益有限\n")
                else:
                    f.write("❌ **较差**: 总收益率为负，存在亏损\n")
                
                f.write(f"""
### 风险控制
""")
                max_drawdown = abs(self.lastOptimization.bestAgent.performance.maxDrawdown)
                if max_drawdown < 0.1:
                    f.write("✅ **优秀**: 最大回撤小于10%，风险控制良好\n")
                elif max_drawdown < 0.2:
                    f.write("✅ **良好**: 最大回撤小于20%，风险可控\n")
                elif max_drawdown < 0.3:
                    f.write("⚠️ **一般**: 最大回撤20-30%，需要注意风险\n")
                else:
                    f.write("❌ **较差**: 最大回撤超过30%，风险较高\n")
                
                f.write(f"""
### 策略稳定性
""")
                sharpe_ratio = self.lastOptimization.bestAgent.performance.sharpeRatio
                if sharpe_ratio > 2:
                    f.write("✅ **优秀**: 夏普比率大于2，风险调整后收益优异\n")
                elif sharpe_ratio > 1:
                    f.write("✅ **良好**: 夏普比率大于1，风险调整后收益良好\n")
                elif sharpe_ratio > 0:
                    f.write("⚠️ **一般**: 夏普比率为正，但收益质量有限\n")
                else:
                    f.write("❌ **较差**: 夏普比率为负，收益质量差\n")
                
                # Add top performers
                f.write(f"""
## 🏅 优秀策略排行榜

| 排名 | 策略名称 | 总收益率 | 夏普比率 | 最大回撤 | 胜率 | 综合评分 |
|------|----------|----------|----------|----------|------|----------|
""")
                for i, agent in enumerate(self.lastOptimization.topAgents[:10], 1):
                    f.write(f"| {i} | {agent.agentName} | {agent.performance.totalReturn:.2%} | "
                           f"{agent.performance.sharpeRatio:.3f} | {agent.performance.maxDrawdown:.2%} | "
                           f"{agent.performance.winRate:.1%} | {agent.score:.2f} |\n")
                
                # Add recommendations
                f.write(f"""
## 💡 投资建议

{chr(10).join(f"- {rec}" for rec in self.lastOptimization.recommendations)}

## ⚠️ 风险提示

1. **历史表现不代表未来**: 回测结果基于历史数据，实际投资可能面临不同的市场环境
2. **交易成本**: 实际投资中需要考虑更多交易成本，包括手续费、滑点、税费等
3. **市场风险**: 股票投资存在市场风险，请根据个人风险承受能力进行投资
4. **流动性风险**: 某些时段可能存在流动性不足的情况，影响策略执行
5. **模型局限性**: 量化模型有其局限性，建议结合基本面分析进行投资决策

## 📈 使用建议

1. **参数调优**: 可以基于最佳参数进行微调，寻找更优配置
2. **止损设置**: 建议设置合理的止损线，控制单次亏损
3. **资金管理**: 不要将全部资金投入单一策略，做好资金配置
4. **定期复评**: 定期重新评估策略表现，根据市场变化调整参数
5. **组合策略**: 考虑使用多策略组合，降低单一策略风险

---
*本报告由量化交易系统自动生成，仅供参考，投资决策请谨慎*
""")
            
            self.logger.info(f"Generated optimization summary report: {summary_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to generate optimization summary report: {str(e)}")
    
    # ============================================================================
    # Advanced Optimization Methods
    # ============================================================================
    
    def defineParameterSpace(self, parameterSpace: Dict[str, ParameterSpace]):
        """定义参数搜索空间"""
        self.parameterSpace = parameterSpace
        self.logger.info(f"Parameter space defined with {len(parameterSpace)} parameters")
    
    def generateParameterSpaceForStrategy(self, strategyType: str) -> Dict[str, ParameterSpace]:
        """为特定策略生成参数空间"""
        if strategyType == 'grid' or strategyType == 'adaptive_grid':
            return {
                'baseRatio': ParameterSpace(
                    name='基础仓位比例',
                    minValue=0.1,
                    maxValue=0.6,
                    step=0.05,
                    paramType='continuous'
                ),
                'gridSpacing': ParameterSpace(
                    name='网格间距',
                    minValue=0.008,
                    maxValue=0.035,
                    step=0.002,
                    paramType='continuous'
                ),
                'gridLevels': ParameterSpace(
                    name='网格层数',
                    values=[6, 8, 10, 12, 15, 20],
                    paramType='discrete'
                ),
                'maxPosition': ParameterSpace(
                    name='最大仓位',
                    values=[50000, 100000, 200000],
                    paramType='discrete'
                ),
                'commission': ParameterSpace(
                    name='手续费率',
                    values=[0.0001, 0.0003, 0.0005],
                    paramType='discrete'
                ),
                # 动态网格调整参数
                'dynamicEnabled': ParameterSpace(
                    name='动态调整开关',
                    values=[True, False],
                    paramType='categorical'
                ),
                'adjustmentThreshold': ParameterSpace(
                    name='调整触发阈值',
                    minValue=0.05,
                    maxValue=0.20,
                    step=0.025,
                    paramType='continuous'
                ),
                'minAdjustmentRatio': ParameterSpace(
                    name='最小调整幅度',
                    minValue=0.03,
                    maxValue=0.10,
                    step=0.01,
                    paramType='continuous'
                ),
                'adjustmentCooldown': ParameterSpace(
                    name='调整冷却期',
                    values=[1, 3, 5, 7, 10, 15],
                    paramType='discrete'
                ),
                'centerPricePeriod': ParameterSpace(
                    name='中心价格计算周期',
                    values=[10, 15, 20, 25, 30],
                    paramType='discrete'
                ),
                'centerPriceMethod': ParameterSpace(
                    name='中心价格计算方法',
                    values=['sma', 'ema', 'vwap'],
                    paramType='categorical'
                )
            }
        elif strategyType == 'dca':
            return {
                'interval': ParameterSpace(
                    name='投资间隔',
                    values=['daily', 'weekly', 'monthly'],
                    paramType='categorical'
                ),
                'amount': ParameterSpace(
                    name='投资金额',
                    values=[500, 1000, 2000, 5000],
                    paramType='discrete'
                ),
                'baseRatio': ParameterSpace(
                    name='基础仓位比例',
                    minValue=0.2,
                    maxValue=0.6,
                    step=0.1,
                    paramType='continuous'
                )
            }
        else:
            # Default parameter space
            return {
                'baseRatio': ParameterSpace(
                    name='基础仓位比例',
                    minValue=0.1,
                    maxValue=0.5,
                    step=0.1,
                    paramType='continuous'
                )
            }
    
    def calculateScore(self, performance: PerformanceMetrics) -> float:
        """
        基于业界标准的简化评分函数
        
        业界最常用的评分指标：
        1. 夏普比率 (Sharpe Ratio) - 风险调整收益的黄金标准
        2. 最大回撤 (Max Drawdown) - 风险控制指标
        3. 卡尔玛比率 (Calmar Ratio) - 年化收益/最大回撤
        
        评分逻辑：
        - 主要使用夏普比率 (业界标准，诺贝尔奖得主William Sharpe发明)
        - 回撤控制作为约束条件
        - 简单、可解释、符合业界实践
        """
        try:
            totalReturn = performance.totalReturn
            maxDrawdown = abs(performance.maxDrawdown)
            sharpeRatio = performance.sharpeRatio
            totalTrades = performance.totalTrades
            
            # 基础有效性检查
            if totalTrades < 1:
                return -100
            
            # 1. 夏普比率作为主要评分 (权重80%)
            # 业界标准：>0.75良好，>1.0优秀，>1.5卓越
            sharpeScore = sharpeRatio * 100  # 夏普1.0 = 100分
            
            # 2. 卡尔玛比率 (Calmar Ratio = 年化收益 / 最大回撤)
            # 业界常用的风险调整收益指标
            if maxDrawdown > 0.001:  # 避免除零
                # 估算年化收益率 (简化处理)
                annualizedReturn = performance.annualizedReturn if hasattr(performance, 'annualizedReturn') and performance.annualizedReturn != 0 else totalReturn
                calmarRatio = annualizedReturn / maxDrawdown
                calmarScore = calmarRatio * 20  # 卡尔玛1.0 = 20分
            else:
                calmarScore = 50  # 无回撤给予奖励分
            
            # 3. 回撤控制 (权重20%)
            # 业界经验：回撤<20%可接受，<15%良好，<10%优秀
            if maxDrawdown < 0.10:
                drawdownScore = 30   # 优秀
            elif maxDrawdown < 0.15:
                drawdownScore = 20   # 良好
            elif maxDrawdown < 0.20:
                drawdownScore = 10   # 可接受
            elif maxDrawdown < 0.30:
                drawdownScore = 0    # 一般
            else:
                drawdownScore = -20  # 较差
            
            # 4. 综合评分 (简单加权)
            # 夏普比率70% + 卡尔玛比率20% + 回撤控制10%
            finalScore = (sharpeScore * 0.7 + 
                         calmarScore * 0.2 + 
                         drawdownScore * 0.1)
            
            # 5. 边界处理 - 避免极端值
            finalScore = max(-500, min(500, finalScore))
            
            return finalScore
            
        except Exception as e:
            self.logger.error(f"Error calculating score: {e}")
            return -500
    
    def randomSearchOptimization(self, symbol: str, startDate: str, endDate: str,
                                strategyType: str, nIterations: int = 100,
                                initialCapital: float = 100000) -> OptimizationResult:
        """随机搜索优化"""
        self.logger.info(f"Starting random search optimization for {strategyType} strategy")
        
        # Define parameter space if not set
        if not self.parameterSpace:
            self.parameterSpace = self.generateParameterSpaceForStrategy(strategyType)
        
        bestScore = float('-inf')
        bestResult = None
        
        for i in range(nIterations):
            self.logger.info(f"Random search iteration {i+1}/{nIterations}")
            
            # Random sample parameters
            params = self._randomSampleParameters()
            
            # Create agent config
            agentConfig = AgentConfig(
                strategyType=strategyType,
                parameters=params,
                riskProfile='moderate',
                name=f'RandomSearch_{strategyType}_{i+1}',
                description=f'Random search iteration {i+1}'
            )
            
            # Evaluate parameters
            result = self._runSingleSimulation(symbol, startDate, endDate, agentConfig, initialCapital)
            if result:
                result.score = self.calculateScore(result.performance)
                result.iteration = i + 1
                self.optimizationResults.append(result)
                
                if result.score > bestScore:
                    bestScore = result.score
                    bestResult = result
                    self.logger.info(f"Found better parameters! Score: {bestScore:.2f}")
        
        self.bestResult = bestResult
        self.logger.info(f"Random search optimization completed")
        return bestResult
    
    def geneticAlgorithmOptimization(self, symbol: str, startDate: str, endDate: str,
                                   strategyType: str, populationSize: int = 30, generations: int = 15,
                                   initialCapital: float = 100000) -> OptimizationResult:
        """遗传算法优化"""
        self.logger.info(f"Starting genetic algorithm optimization for {strategyType} strategy")
        
        # Define parameter space if not set
        if not self.parameterSpace:
            self.parameterSpace = self.generateParameterSpaceForStrategy(strategyType)
        
        # Initialize population
        population = []
        for i in range(populationSize):
            params = self._randomSampleParameters()
            agentConfig = AgentConfig(
                strategyType=strategyType,
                parameters=params,
                riskProfile='moderate',
                name=f'GA_Gen0_Ind{i+1}',
                description=f'Genetic algorithm generation 0, individual {i+1}'
            )
            
            result = self._runSingleSimulation(symbol, startDate, endDate, agentConfig, initialCapital)
            if result:
                result.score = self.calculateScore(result.performance)
                result.iteration = i + 1
                self.optimizationResults.append(result)
                population.append(result)
        
        bestResult = max(population, key=lambda x: x.score) if population else None
        
        # Handle case where no valid results were found in initial population
        if not population:
            self.logger.error("No valid results found in initial population")
            return None
        
        # Track convergence
        no_improvement_count = 0
        improvement_threshold = 1e-6
        max_no_improvement = 3  # Early stopping after 3 generations without improvement
        
        # Evolution loop
        for gen in range(generations):
            previous_best_score = bestResult.score if bestResult else float('-inf')
            
            self.logger.info(f"Generation {gen+1}/{generations} - Best score: {previous_best_score:.2f}")
            
            newPopulation = []
            
            # Elite selection with diversity maintenance
            population.sort(key=lambda x: x.score, reverse=True)
            eliteCount = max(2, populationSize // 8)  # At least 2 elites, max 12.5%
            
            # Add elites
            elites = population[:eliteCount]
            newPopulation.extend(elites)
            
            # Generate new individuals through crossover and mutation
            while len(newPopulation) < populationSize:
                # Adaptive selection pressure - higher pressure in later generations
                tournament_size = min(5, 2 + gen // 3)
                parent1, parent2 = self._tournamentSelection(population, tournament_size)
                
                # Crossover
                childParams = self._crossover(parent1.agentConfig.parameters, parent2.agentConfig.parameters)
                
                # Adaptive mutation rate - higher in early generations, lower in later
                adaptive_mutation_rate = 0.3 * (1 - gen / generations) + 0.05
                childParams = self._mutate(childParams, adaptive_mutation_rate)
                
                # Create child agent config
                childConfig = AgentConfig(
                    strategyType=strategyType,
                    parameters=childParams,
                    riskProfile='moderate',
                    name=f'GA_Gen{gen+1}_Child{len(newPopulation)+1}',
                    description=f'Genetic algorithm generation {gen+1}'
                )
                
                # Evaluate child
                childResult = self._runSingleSimulation(symbol, startDate, endDate, childConfig, initialCapital)
                if childResult:
                    childResult.score = self.calculateScore(childResult.performance)
                    childResult.iteration = gen * populationSize + len(newPopulation) + 1
                    self.optimizationResults.append(childResult)
                    newPopulation.append(childResult)
                    
                    # Update best result
                    if childResult.score > bestResult.score:
                        bestResult = childResult
                        self.logger.info(f"Found better parameters in generation {gen+1}! Score: {bestResult.score:.2f}")
            
            population = newPopulation
            
            # Check for convergence and early stopping
            current_best_score = bestResult.score
            improvement = current_best_score - previous_best_score
            
            if improvement < improvement_threshold:
                no_improvement_count += 1
                if no_improvement_count >= max_no_improvement:
                    self.logger.info(f"Early stopping: No significant improvement for {max_no_improvement} generations")
                    break
            else:
                no_improvement_count = 0
        
        self.bestResult = bestResult
        self.logger.info(f"Genetic algorithm optimization completed")
        return bestResult
    
    def particleSwarmOptimization(self, symbol: str, startDate: str, endDate: str,
                                strategyType: str, nParticles: int = 20, nIterations: int = 30,
                                initialCapital: float = 100000) -> OptimizationResult:
        """粒子群优化"""
        self.logger.info(f"Starting particle swarm optimization for {strategyType} strategy")
        
        # Define parameter space if not set
        if not self.parameterSpace:
            self.parameterSpace = self.generateParameterSpaceForStrategy(strategyType)
        
        # Initialize particle swarm
        particles = []
        globalBest = None
        globalBestScore = float('-inf')
        
        # Create initial particles
        for i in range(nParticles):
            particle = {
                'position': self._randomSampleParameters(),
                'velocity': self._initializeVelocity(),
                'personalBest': None,
                'personalBestScore': float('-inf')
            }
            
            # Evaluate initial position
            agentConfig = AgentConfig(
                strategyType=strategyType,
                parameters=particle['position'],
                riskProfile='moderate',
                name=f'PSO_Particle{i+1}_Init',
                description=f'PSO particle {i+1} initial position'
            )
            
            result = self._runSingleSimulation(symbol, startDate, endDate, agentConfig, initialCapital)
            if result:
                result.score = self.calculateScore(result.performance)
                result.iteration = i + 1
                self.optimizationResults.append(result)
                
                particle['personalBest'] = particle['position'].copy()
                particle['personalBestScore'] = result.score
                
                if result.score > globalBestScore:
                    globalBest = result
                    globalBestScore = result.score
                
                particles.append(particle)
        
        # Handle case where no valid particles were created
        if not particles:
            self.logger.error("No valid particles found in initial population")
            return None
        
        # PSO main loop with adaptive parameters
        w_start = 0.9   # initial inertia weight
        w_end = 0.4     # final inertia weight
        c1_start = 2.5  # initial cognitive learning factor
        c1_end = 0.5    # final cognitive learning factor
        c2_start = 0.5  # initial social learning factor
        c2_end = 2.5    # final social learning factor
        
        no_improvement_count = 0
        improvement_threshold = 1e-6
        max_no_improvement = 5  # Early stopping after 5 iterations without improvement
        
        for iteration in range(nIterations):
            # Adaptive parameter adjustment
            progress = iteration / nIterations
            w = w_start - (w_start - w_end) * progress
            c1 = c1_start - (c1_start - c1_end) * progress
            c2 = c2_start - (c2_start - c2_end) * progress
            
            self.logger.info(f"PSO iteration {iteration+1}/{nIterations} - Best score: {globalBestScore:.2f} (w={w:.2f}, c1={c1:.2f}, c2={c2:.2f})")
            
            previous_best_score = globalBestScore
            
            for j, particle in enumerate(particles):
                # Update velocity and position
                self._updateParticleVelocity(particle, globalBest.agentConfig.parameters, w, c1, c2)
                self._updateParticlePosition(particle)
                
                # Evaluate new position
                agentConfig = AgentConfig(
                    strategyType=strategyType,
                    parameters=particle['position'],
                    riskProfile='moderate',
                    name=f'PSO_Iter{iteration+1}_Particle{j+1}',
                    description=f'PSO iteration {iteration+1}, particle {j+1}'
                )
                
                result = self._runSingleSimulation(symbol, startDate, endDate, agentConfig, initialCapital)
                if result:
                    result.score = self.calculateScore(result.performance)
                    result.iteration = iteration * nParticles + j + 1
                    self.optimizationResults.append(result)
                    
                    # Update personal best
                    if result.score > particle['personalBestScore']:
                        particle['personalBest'] = particle['position'].copy()
                        particle['personalBestScore'] = result.score
                    
                    # Update global best
                    if result.score > globalBestScore:
                        globalBest = result
                        globalBestScore = result.score
                        self.logger.info(f"Found better parameters! Score: {globalBestScore:.2f}")
            
            # Check for improvement and early stopping
            improvement = globalBestScore - previous_best_score
            if improvement < improvement_threshold:
                no_improvement_count += 1
                if no_improvement_count >= max_no_improvement:
                    self.logger.info(f"Early stopping: No significant improvement for {max_no_improvement} iterations")
                    break
            else:
                no_improvement_count = 0
        
        self.bestResult = globalBest
        self.logger.info(f"Particle swarm optimization completed")
        return globalBest
    
    def comprehensiveOptimization(self, symbol: str, startDate: str, endDate: str,
                                strategyType: str, initialCapital: float = 100000,
                                optimizationRatio: float = 0.7, minOptimizationYears: int = 5, 
                                minBacktestYears: int = 2) -> Dict[str, OptimizationResult]:
        """
        综合优化: 运行多种优化算法并比较结果
        
        Args:
            symbol: 股票代码
            startDate: 总体开始日期
            endDate: 总体结束日期  
            strategyType: 策略类型
            initialCapital: 初始资金
            optimizationRatio: 优化期占总数据的比例 (默认0.7即70%)
            minOptimizationYears: 最小优化期年数 (默认5年)
            minBacktestYears: 最小回测期年数 (默认2年)
        """
        self.logger.info(f"Starting comprehensive optimization for {strategyType} strategy")
        
        # Calculate data split dates
        start_dt = datetime.strptime(startDate, '%Y-%m-%d')
        end_dt = datetime.strptime(endDate, '%Y-%m-%d')
        total_days = (end_dt - start_dt).days
        total_years = total_days / 365.25
        
        # Check if we have enough data
        min_total_years = minOptimizationYears + minBacktestYears
        if total_years < min_total_years:
            raise ValueError(f"Insufficient data: {total_years:.1f} years available, "
                           f"but need at least {min_total_years} years "
                           f"({minOptimizationYears} for optimization + {minBacktestYears} for backtest)")
        
        # Calculate split point
        optimization_days = int(total_days * optimizationRatio)
        
        # Ensure minimum optimization period
        min_optimization_days = int(minOptimizationYears * 365.25)
        if optimization_days < min_optimization_days:
            optimization_days = min_optimization_days
            
        # Ensure minimum backtest period  
        remaining_days = total_days - optimization_days
        min_backtest_days = int(minBacktestYears * 365.25)
        if remaining_days < min_backtest_days:
            optimization_days = total_days - min_backtest_days
            
        # Calculate actual dates
        optimization_end_dt = start_dt + timedelta(days=optimization_days)
        optimization_end_date = optimization_end_dt.strftime('%Y-%m-%d')
        backtest_start_date = (optimization_end_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        
        optimization_years = optimization_days / 365.25
        backtest_years = (total_days - optimization_days) / 365.25
        
        self.logger.info(f"Data split configuration:")
        self.logger.info(f"  Total period: {startDate} to {endDate} ({total_years:.1f} years)")
        self.logger.info(f"  Optimization period: {startDate} to {optimization_end_date} ({optimization_years:.1f} years)")
        self.logger.info(f"  Backtest period: {backtest_start_date} to {endDate} ({backtest_years:.1f} years)")
        
        # CRITICAL FIX: Store the full period for consistent report generation
        self._fullPeriodStart = startDate
        self._fullPeriodEnd = endDate
        self._optimizationPeriodEnd = optimization_end_date
        self._backtestPeriodStart = backtest_start_date
        
        # Define parameter space
        self.parameterSpace = self.generateParameterSpaceForStrategy(strategyType)
        
        # Clear previous results
        self.optimizationResults = []
        
        optimizationMethods = {
            'Random Search': lambda: self.randomSearchOptimization(
                symbol, startDate, optimization_end_date, strategyType, nIterations=100, initialCapital=initialCapital
            ),
            'Genetic Algorithm': lambda: self.geneticAlgorithmOptimization(
                symbol, startDate, optimization_end_date, strategyType, populationSize=20, generations=10, initialCapital=initialCapital
            ),
            'Particle Swarm': lambda: self.particleSwarmOptimization(
                symbol, startDate, optimization_end_date, strategyType, nParticles=15, nIterations=20, initialCapital=initialCapital
            )
        }
        
        results = {}
        
        # Run optimization on optimization period
        for i, (methodName, methodFunc) in enumerate(optimizationMethods.items()):
            self.logger.info(f"Running {methodName} optimization on optimization period...")
            startTime = time.time()
            
            # Set different random seed for each method to ensure diversity
            random.seed(42 + i * 1000)  # Different seeds: 42, 1042, 2042
            np.random.seed(42 + i * 1000)
            
            try:
                result = methodFunc()
                
                # Now run backtest on out-of-sample data
                if result:
                    self.logger.info(f"Testing {methodName} best result on backtest period...")
                    backtest_result = self._runSingleSimulation(
                        symbol, backtest_start_date, endDate, result.agentConfig, initialCapital
                    )
                    
                    if backtest_result:
                        # Update result with out-of-sample performance
                        backtest_result.agentName = f"{result.agentName}_Backtest"
                        backtest_result.score = self.calculateScore(backtest_result.performance)
                        results[methodName] = backtest_result
                        
                        self.logger.info(f"{methodName} backtest results:")
                        self.logger.info(f"  Optimization Return: {result.performance.totalReturn:.2%}")
                        self.logger.info(f"  Backtest Return: {backtest_result.performance.totalReturn:.2%}")
                        self.logger.info(f"  Backtest Sharpe: {backtest_result.performance.sharpeRatio:.3f}")
                
                elapsedTime = time.time() - startTime
                self.logger.info(f"{methodName} completed in {elapsedTime:.1f}s")
                
            except Exception as e:
                self.logger.error(f"{methodName} failed: {str(e)}")
        
        # Find overall best result based on backtest performance
        if results:
            self.bestResult = max(results.values(), key=lambda x: x.score)
            bestMethodName = [k for k, v in results.items() if v.score == self.bestResult.score][0]
            self.logger.info(f"Overall best backtest result from: {bestMethodName}")
            
            # Create optimization summary
            summary = self._createOptimizationSummary(
                symbol, backtest_start_date, endDate, list(results.values())
            )
            self.lastOptimization = summary
        
        return results
    
    # ============================================================================
    # Helper Methods for Advanced Optimization
    # ============================================================================
    
    def _randomSampleParameters(self) -> Dict:
        """随机采样参数"""
        params = {}
        
        for paramName, paramSpace in self.parameterSpace.items():
            if paramSpace.paramType == 'discrete' or paramSpace.paramType == 'categorical':
                params[paramName] = random.choice(paramSpace.values)
            else:  # continuous
                params[paramName] = random.uniform(paramSpace.minValue, paramSpace.maxValue)
        
        return params
    
    def _tournamentSelection(self, population: List[OptimizationResult], tournamentSize: int) -> Tuple[OptimizationResult, OptimizationResult]:
        """锦标赛选择"""
        def tournament():
            candidates = random.sample(population, min(tournamentSize, len(population)))
            return max(candidates, key=lambda x: x.score)
        
        return tournament(), tournament()
    
    def _crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """改进的交叉操作 - 使用blend crossover for continuous parameters"""
        child = {}
        alpha = 0.1  # blend factor
        
        for paramName in parent1.keys():
            paramSpace = self.parameterSpace[paramName]
            
            if paramSpace.paramType == 'continuous':
                # Blend crossover for continuous parameters
                val1, val2 = parent1[paramName], parent2[paramName]
                min_val, max_val = min(val1, val2), max(val1, val2)
                range_val = max_val - min_val
                
                # Extend range by alpha on both sides
                lower_bound = max(paramSpace.minValue, min_val - alpha * range_val)
                upper_bound = min(paramSpace.maxValue, max_val + alpha * range_val)
                
                child[paramName] = random.uniform(lower_bound, upper_bound)
            
            elif paramSpace.paramType == 'discrete':
                # Weighted selection for discrete parameters
                if random.random() < 0.7:  # 70% chance to inherit from better parent
                    # Assume parent1 is better (should be ensured in selection)
                    child[paramName] = parent1[paramName]
                else:
                    child[paramName] = parent2[paramName]
                    
            else:  # categorical
                # Simple random selection for categorical
                child[paramName] = random.choice([parent1[paramName], parent2[paramName]])
        
        return child
    
    def _mutate(self, params: Dict, mutationRate: float = 0.1) -> Dict:
        """改进的变异操作 - 使用Gaussian mutation for continuous parameters"""
        mutated = params.copy()
        
        for paramName, paramSpace in self.parameterSpace.items():
            if random.random() < mutationRate:
                if paramSpace.paramType == 'continuous':
                    # Gaussian mutation with adaptive step size
                    current_val = mutated[paramName]
                    range_val = paramSpace.maxValue - paramSpace.minValue
                    
                    # Step size is 5% of parameter range
                    step_size = range_val * 0.05
                    mutation_val = random.gauss(0, step_size)
                    
                    new_val = current_val + mutation_val
                    new_val = max(paramSpace.minValue, min(paramSpace.maxValue, new_val))
                    mutated[paramName] = new_val
                    
                elif paramSpace.paramType == 'discrete':
                    # Smart mutation for discrete parameters
                    current_val = mutated[paramName]
                    values = paramSpace.values
                    current_idx = values.index(current_val) if current_val in values else 0
                    
                    # Prefer nearby values
                    if len(values) > 1:
                        if current_idx == 0:
                            new_idx = random.choice([0, 1])
                        elif current_idx == len(values) - 1:
                            new_idx = random.choice([current_idx - 1, current_idx])
                        else:
                            new_idx = random.choice([current_idx - 1, current_idx, current_idx + 1])
                        mutated[paramName] = values[new_idx]
                        
                else:  # categorical
                    # Random selection for categorical
                    mutated[paramName] = random.choice(paramSpace.values)
        
        return mutated
    
    def _initializeVelocity(self) -> Dict:
        """初始化粒子速度"""
        velocity = {}
        
        for paramName, paramSpace in self.parameterSpace.items():
            if paramSpace.paramType == 'continuous':
                rangeSize = paramSpace.maxValue - paramSpace.minValue
                velocity[paramName] = random.uniform(-rangeSize * 0.1, rangeSize * 0.1)
            else:
                velocity[paramName] = 0  # 离散参数速度为0
        
        return velocity
    
    def _updateParticleVelocity(self, particle: Dict, globalBestPosition: Dict, w: float, c1: float, c2: float):
        """更新粒子速度 - 改进版"""
        for paramName in particle['velocity'].keys():
            paramSpace = self.parameterSpace[paramName]
            
            if paramSpace.paramType == 'continuous':
                r1, r2 = random.random(), random.random()
                
                inertia = w * particle['velocity'][paramName]
                cognitive = c1 * r1 * (particle['personalBest'][paramName] - particle['position'][paramName])
                social = c2 * r2 * (globalBestPosition[paramName] - particle['position'][paramName])
                
                new_velocity = inertia + cognitive + social
                
                # Velocity clamping to prevent explosion
                max_velocity = (paramSpace.maxValue - paramSpace.minValue) * 0.2
                new_velocity = max(-max_velocity, min(max_velocity, new_velocity))
                
                particle['velocity'][paramName] = new_velocity
                
            elif paramSpace.paramType == 'discrete':
                # Probability-based update for discrete parameters
                r1, r2 = random.random(), random.random()
                
                # Calculate attraction probabilities
                prob_personal = c1 * r1 * 0.1  # 10% base probability
                prob_global = c2 * r2 * 0.1
                
                current_val = particle['position'][paramName]
                personal_best_val = particle['personalBest'][paramName]
                global_best_val = globalBestPosition[paramName]
                
                # Store probabilities for position update
                particle['velocity'][paramName] = {
                    'prob_personal': prob_personal if personal_best_val != current_val else 0,
                    'prob_global': prob_global if global_best_val != current_val else 0,
                    'personal_target': personal_best_val,
                    'global_target': global_best_val
                }
    
    def _updateParticlePosition(self, particle: Dict):
        """更新粒子位置 - 改进版"""
        for paramName, paramSpace in self.parameterSpace.items():
            if paramSpace.paramType == 'continuous':
                newPosition = particle['position'][paramName] + particle['velocity'][paramName]
                
                # Reflective boundary handling instead of clamping
                if newPosition < paramSpace.minValue:
                    newPosition = paramSpace.minValue + (paramSpace.minValue - newPosition)
                    particle['velocity'][paramName] *= -0.5  # Reverse and dampen velocity
                elif newPosition > paramSpace.maxValue:
                    newPosition = paramSpace.maxValue - (newPosition - paramSpace.maxValue)
                    particle['velocity'][paramName] *= -0.5
                
                # Final clamp if still out of bounds
                newPosition = max(paramSpace.minValue, min(paramSpace.maxValue, newPosition))
                particle['position'][paramName] = newPosition
                
            elif paramSpace.paramType == 'discrete':
                # Probability-based position update for discrete parameters
                velocity_info = particle['velocity'][paramName]
                
                if isinstance(velocity_info, dict):
                    prob_personal = velocity_info['prob_personal']
                    prob_global = velocity_info['prob_global']
                    
                    rand_val = random.random()
                    
                    if rand_val < prob_global:
                        particle['position'][paramName] = velocity_info['global_target']
                    elif rand_val < prob_global + prob_personal:
                        particle['position'][paramName] = velocity_info['personal_target']
                    # else: stay at current position
                else:
                    # Fallback to old method
                    if random.random() < 0.1:
                        particle['position'][paramName] = random.choice(paramSpace.values)
                        
            else:  # categorical
                # Similar probability-based update for categorical
                velocity_info = particle['velocity'].get(paramName, 0)
                if isinstance(velocity_info, dict):
                    prob_personal = velocity_info.get('prob_personal', 0)
                    prob_global = velocity_info.get('prob_global', 0)
                    
                    rand_val = random.random()
                    
                    if rand_val < prob_global:
                        particle['position'][paramName] = velocity_info['global_target']
                    elif rand_val < prob_global + prob_personal:
                        particle['position'][paramName] = velocity_info['personal_target']
                else:
                    if random.random() < 0.1:
                        particle['position'][paramName] = random.choice(paramSpace.values)
        
        return particle
        
    def getBestStrategyBacktestResults(self) -> Optional[Dict[str, Any]]:
        """获取最优策略的完整回测结果，用于生成详细报告"""
        if not self.bestResult:
            self.logger.warning("No best result available. Run optimization first.")
            return None
            
        try:
            # 从最优结果中获取完整的模拟详情
            simulationDetails = self.bestResult.simulationDetails
            
            # 构建与BacktestEngine兼容的结果格式
            backtest_results = {
                # 基本信息
                'symbol': simulationDetails.get('symbol', 'Unknown'),
                'initialCapital': simulationDetails.get('initialCapital', 100000),
                'finalCapital': simulationDetails.get('finalCapital', 0),
                
                # 性能指标
                'performance': {
                    'totalReturn': self.bestResult.performance.totalReturn,
                    'annualizedReturn': self.bestResult.performance.annualizedReturn,
                    'maxDrawdown': self.bestResult.performance.maxDrawdown,
                    'sharpeRatio': self.bestResult.performance.sharpeRatio,
                    'winRate': self.bestResult.performance.winRate,
                    'totalTrades': self.bestResult.performance.totalTrades,
                    'avgTradeReturn': self.bestResult.performance.avgTradeReturn,
                    'volatility': self.bestResult.performance.volatility
                },
                
                # 交易记录
                'trades': simulationDetails.get('tradeHistory', []),
                
                # 网格调整记录
                'gridAdjustments': simulationDetails.get('gridAdjustments', []),
                
                # 每日资产价值序列
                'portfolioValues': simulationDetails.get('valueHistory', []),
                
                # 股价数据
                'stockData': simulationDetails.get('stockData'),
                
                # 策略对象 - 确保网格明细可以正确显示
                'strategy': simulationDetails.get('strategy'),
                
                # 策略参数
                'parameters': self.bestResult.agentConfig.parameters,
                
                # 时间信息
                'actualStartDate': simulationDetails.get('startDate', 'N/A'),
                'actualEndDate': simulationDetails.get('endDate', 'N/A'),
                
                # 优化相关信息
                'optimizationScore': self.bestResult.score,
                'optimizationMethod': simulationDetails.get('optimizationMethod', 'comprehensive'),
                
                # 策略配置
                'strategyConfig': self.bestResult.agentConfig.parameters
            }
            
            self.logger.info(f"Retrieved backtest results for best strategy: {self.bestResult.agentName}")
            return backtest_results
            
        except Exception as e:
            self.logger.error(f"Error retrieving best strategy backtest results: {e}")
            return None 