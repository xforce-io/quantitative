"""
Agent Manager System
代理管理系统 - 统一管理不同类型的交易代理
"""
from typing import Dict, List, Any, Optional, Type
from dataclasses import dataclass
import logging
from abc import ABC, abstractmethod

from .strategy_agent import StrategyAgent, AgentConfig, createAgent
from ..engines.backtest_engine import BacktestEngine
from ..data_providers.data_provider_factory import createDataProvider

@dataclass
class AgentOptimizationConfig:
    """代理优化配置"""
    agentType: str
    parameterRanges: Dict[str, List[Any]]
    riskProfile: str
    maxVariants: int = 50
    
@dataclass
class AgentPerformanceResult:
    """代理性能结果"""
    agentName: str
    agentConfig: AgentConfig
    performance: Dict[str, Any]
    rank: int
    
class AgentManager:
    """代理管理器 - 统一管理和优化不同类型的交易代理"""
    
    def __init__(self, dataProviderType: str = 'tushare'):
        self.dataProviderType = dataProviderType
        self.dataProvider = createDataProvider(dataProviderType)
        self.backtestEngine = BacktestEngine(dataProviderType)
        self.logger = logging.getLogger(__name__)
        
        # Agent registry
        self.registeredAgents: Dict[str, Type[StrategyAgent]] = {}
        self.activeAgents: List[StrategyAgent] = []
        
    def registerAgentType(self, agentType: str, agentClass: Type[StrategyAgent]):
        """注册新的代理类型"""
        self.registeredAgents[agentType] = agentClass
        self.logger.info(f"Registered agent type: {agentType}")
        
    def generateAgentVariants(self, agentType: str, symbol: str, 
                            optimizationConfig: AgentOptimizationConfig) -> List[AgentConfig]:
        """为指定代理类型生成参数变体"""
        variants = []
        
        if agentType == 'grid':
            variants = self._generateGridAgentVariants(symbol, optimizationConfig)
        elif agentType == 'dca':
            variants = self._generateDCAAgentVariants(symbol, optimizationConfig)
        elif agentType == 'momentum':
            variants = self._generateMomentumAgentVariants(symbol, optimizationConfig)
        elif agentType == 'hybrid':
            variants = self._generateHybridAgentVariants(symbol, optimizationConfig)
        else:
            self.logger.warning(f"Unknown agent type: {agentType}")
            
        # Limit variants if needed
        if len(variants) > optimizationConfig.maxVariants:
            variants = variants[:optimizationConfig.maxVariants]
            
        self.logger.info(f"Generated {len(variants)} variants for {agentType} agent")
        return variants
    
    def _generateGridAgentVariants(self, symbol: str, config: AgentOptimizationConfig) -> List[AgentConfig]:
        """生成网格代理变体"""
        variants = []
        paramRanges = config.parameterRanges
        
        gridLevels = paramRanges.get('gridLevels', [8, 10, 12])
        gridSpacing = paramRanges.get('gridSpacing', [0.015, 0.02, 0.025])
        baseRatio = paramRanges.get('baseRatio', [0.2, 0.3, 0.4])
        maxPosition = paramRanges.get('maxPosition', [100000])
        
        for levels in gridLevels:
            for spacing in gridSpacing:
                for ratio in baseRatio:
                    for position in maxPosition:
                        agentConfig = AgentConfig(
                            strategyType='grid',
                            parameters={
                                'gridLevels': levels,
                                'gridSpacing': spacing,
                                'baseRatio': ratio,
                                'maxPosition': position,
                                'commission': 0.0003,
                                'slippage': 0.001
                            },
                            riskProfile=config.riskProfile,
                            name=f'GridAgent_L{levels}_S{spacing:.3f}_B{ratio:.1f}',
                            description=f'Grid agent: {levels} levels, {spacing:.1%} spacing, {ratio:.1%} base ratio'
                        )
                        variants.append(agentConfig)
        
        return variants
    
    def _generateDCAAgentVariants(self, symbol: str, config: AgentOptimizationConfig) -> List[AgentConfig]:
        """生成定投代理变体"""
        variants = []
        paramRanges = config.parameterRanges
        
        intervals = paramRanges.get('interval', ['weekly', 'monthly'])
        amounts = paramRanges.get('amount', [1000, 2000])
        baseRatios = paramRanges.get('baseRatio', [0.3, 0.4, 0.5])
        
        for interval in intervals:
            for amount in amounts:
                for ratio in baseRatios:
                    agentConfig = AgentConfig(
                        strategyType='dca',
                        parameters={
                            'interval': interval,
                            'amount': amount,
                            'baseRatio': ratio,
                            'maxPosition': 100000,
                            'commission': 0.0003
                        },
                        riskProfile=config.riskProfile,
                        name=f'DCAAgent_{interval}_{amount}_B{ratio:.1f}',
                        description=f'DCA agent: {interval} {amount}, {ratio:.1%} base ratio'
                    )
                    variants.append(agentConfig)
        
        return variants
    
    def _generateMomentumAgentVariants(self, symbol: str, config: AgentOptimizationConfig) -> List[AgentConfig]:
        """生成动量代理变体"""
        variants = []
        paramRanges = config.parameterRanges
        
        lookbackPeriods = paramRanges.get('lookbackPeriod', [10, 20, 30])
        thresholds = paramRanges.get('threshold', [0.03, 0.05, 0.07])
        baseRatios = paramRanges.get('baseRatio', [0.1, 0.2, 0.3])
        
        for period in lookbackPeriods:
            for threshold in thresholds:
                for ratio in baseRatios:
                    agentConfig = AgentConfig(
                        strategyType='momentum',
                        parameters={
                            'lookbackPeriod': period,
                            'threshold': threshold,
                            'baseRatio': ratio,
                            'maxPosition': 100000,
                            'commission': 0.0003
                        },
                        riskProfile=config.riskProfile,
                        name=f'MomentumAgent_{period}d_{threshold:.3f}_B{ratio:.1f}',
                        description=f'Momentum agent: {period}d lookback, {threshold:.1%} threshold, {ratio:.1%} base'
                    )
                    variants.append(agentConfig)
        
        return variants
    
    def _generateHybridAgentVariants(self, symbol: str, config: AgentOptimizationConfig) -> List[AgentConfig]:
        """生成混合代理变体"""
        variants = []
        
        # 预定义的权重组合
        weightCombinations = [
            {'grid': 0.6, 'momentum': 0.3, 'meanReversion': 0.1},
            {'grid': 0.4, 'momentum': 0.4, 'meanReversion': 0.2},
            {'grid': 0.3, 'momentum': 0.2, 'meanReversion': 0.5},
            {'grid': 0.33, 'momentum': 0.33, 'meanReversion': 0.34}
        ]
        
        for i, weights in enumerate(weightCombinations):
            agentConfig = AgentConfig(
                strategyType='hybrid',
                parameters={
                    'strategyWeights': weights,
                    'gridParams': {
                        'gridLevels': 10,
                        'gridSpacing': 0.02,
                        'baseRatio': 0.3
                    },
                    'momentumParams': {
                        'lookbackPeriod': 20,
                        'threshold': 0.05,
                        'baseRatio': 0.2
                    },
                    'meanReversionParams': {
                        'period': 20,
                        'deviationThreshold': 2.0,
                        'baseRatio': 0.3
                    },
                    'maxPosition': 100000,
                    'commission': 0.0003
                },
                riskProfile=config.riskProfile,
                name=f'HybridAgent_Combo{i+1}',
                description=f'Hybrid agent: Grid{weights["grid"]:.1%}, Momentum{weights["momentum"]:.1%}, MeanRev{weights["meanReversion"]:.1%}'
            )
            variants.append(agentConfig)
        
        return variants
    
    def optimizeAgents(self, symbol: str, startDate: str, endDate: str,
                      agentConfigs: List[AgentConfig], 
                      initialCapital: float = 100000) -> List[AgentPerformanceResult]:
        """优化多个代理的性能"""
        results = []
        
        self.logger.info(f"Starting optimization for {len(agentConfigs)} agents on {symbol}")
        
        for i, config in enumerate(agentConfigs):
            try:
                # Create agent instance
                agent = createAgent(config.strategyType, config)
                
                # Run backtest for this agent
                backtestResult = self.backtestEngine.runBacktest(
                    symbol=symbol,
                    startDate=startDate,
                    endDate=endDate,
                    initialCapital=initialCapital,
                    strategyConfig=config.parameters
                )
                
                performance = backtestResult.get('performance', {})
                
                result = AgentPerformanceResult(
                    agentName=config.name,
                    agentConfig=config,
                    performance=performance,
                    rank=0  # Will be set after sorting
                )
                
                results.append(result)
                
                self.logger.info(f"Completed optimization {i+1}/{len(agentConfigs)}: {config.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to optimize agent {config.name}: {str(e)}")
                continue
        
        # Rank results by Sharpe ratio (primary) and total return (secondary)
        results.sort(key=lambda x: (
            x.performance.get('sharpeRatio', 0),
            x.performance.get('totalReturn', 0)
        ), reverse=True)
        
        # Assign ranks
        for i, result in enumerate(results):
            result.rank = i + 1
        
        self.logger.info(f"Optimization completed. Best agent: {results[0].agentName if results else 'None'}")
        
        return results
    
    def getBestAgentByStrategy(self, results: List[AgentPerformanceResult]) -> Dict[str, AgentPerformanceResult]:
        """获取每种策略类型的最佳代理"""
        bestByStrategy = {}
        
        for result in results:
            strategyType = result.agentConfig.strategyType
            if (strategyType not in bestByStrategy or 
                result.performance.get('sharpeRatio', 0) > bestByStrategy[strategyType].performance.get('sharpeRatio', 0)):
                bestByStrategy[strategyType] = result
        
        return bestByStrategy
    
    def generateOptimizationReport(self, symbol: str, results: List[AgentPerformanceResult]) -> Dict[str, Any]:
        """生成优化报告"""
        if not results:
            return {'error': 'No optimization results available'}
        
        bestAgent = results[0]
        bestByStrategy = self.getBestAgentByStrategy(results)
        
        # Performance statistics
        allReturns = [r.performance.get('totalReturn', 0) for r in results]
        allSharpes = [r.performance.get('sharpeRatio', 0) for r in results]
        
        report = {
            'symbol': symbol,
            'totalAgents': len(results),
            'bestOverall': {
                'name': bestAgent.agentName,
                'strategyType': bestAgent.agentConfig.strategyType,
                'performance': bestAgent.performance
            },
            'bestByStrategy': {
                strategyType: {
                    'name': result.agentName,
                    'performance': result.performance
                }
                for strategyType, result in bestByStrategy.items()
            },
            'performanceStats': {
                'avgReturn': sum(allReturns) / len(allReturns),
                'maxReturn': max(allReturns),
                'minReturn': min(allReturns),
                'avgSharpe': sum(allSharpes) / len(allSharpes),
                'maxSharpe': max(allSharpes)
            },
            'recommendations': self._generateRecommendations(results, bestAgent)
        }
        
        return report
    
    def _generateRecommendations(self, results: List[AgentPerformanceResult], 
                               bestAgent: AgentPerformanceResult) -> List[str]:
        """生成投资建议"""
        recommendations = []
        
        # Best agent recommendation
        recommendations.append(
            f"推荐使用 {bestAgent.agentName} "
            f"(收益率: {bestAgent.performance.get('totalReturn', 0):.2%}, "
            f"夏普比率: {bestAgent.performance.get('sharpeRatio', 0):.2f})"
        )
        
        # Risk assessment
        maxDrawdown = bestAgent.performance.get('maxDrawdown', 0)
        if maxDrawdown > 0.15:
            recommendations.append(
                f"注意: 最佳代理的最大回撤较高 ({maxDrawdown:.2%}), "
                "建议考虑风险控制措施"
            )
        
        # Strategy type analysis
        bestByStrategy = self.getBestAgentByStrategy(results)
        if len(bestByStrategy) > 1:
            recommendations.append(
                f"可考虑组合策略: 结合 {', '.join(bestByStrategy.keys())} 类型的代理"
            )
        
        return recommendations

    def saveExperimentResults(self, symbol: str, experimentName: str, results: List[AgentPerformanceResult], 
                            report: Dict[str, Any], metadata: Dict[str, Any] = None) -> str:
        """保存实验结果到指定目录结构
        
        Args:
            symbol: 股票代码
            experimentName: 实验名称  
            results: 优化结果列表
            report: 优化报告
            metadata: 实验元数据
            
        Returns:
            实验目录路径
        """
        from pathlib import Path
        import json
        from datetime import datetime
        from dataclasses import asdict
        
        # 创建实验目录 data/expr/StrategyType_YYMMDDHHNN
        bestAgent = report['bestOverall']
        strategyType = bestAgent['strategyType'].capitalize()
        timestamp = datetime.now().strftime('%y%m%d%H%M')
        
        experimentDir = Path('data') / 'expr' / f"{strategyType}Trading_{timestamp}"
        experimentDir.mkdir(parents=True, exist_ok=True)
        
        # 获取最佳代理的详细配置
        bestResult = results[0] if results else None
        if not bestResult:
            raise ValueError("No valid results to save")
        
        # 保存最佳策略配置文件
        strategyConfigFile = experimentDir / 'best_strategy_config.json'
        strategyConfig = {
            'strategy_type': bestResult.agentConfig.strategyType,
            'strategy_name': bestResult.agentName,
            'parameters': bestResult.agentConfig.parameters,
            'risk_profile': bestResult.agentConfig.riskProfile,
            'symbol': symbol,
            'performance': bestResult.performance,
            'backtest_config': {
                'initial_capital': metadata.get('initial_capital', 100000) if metadata else 100000,
                'commission': bestResult.agentConfig.parameters.get('commission', 0.0003),
                'slippage': 0.001,
                'start_date': metadata.get('start_date') if metadata else None,
                'end_date': metadata.get('end_date') if metadata else None
            }
        }
        
        with open(strategyConfigFile, 'w', encoding='utf-8') as f:
            json.dump(strategyConfig, f, ensure_ascii=False, indent=2, default=str)
        
        # 保存实验描述文件
        experimentMetaFile = experimentDir / 'experiment_meta.json'
        experimentMeta = {
            'experiment_name': experimentName,
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'total_agents_tested': report['totalAgents'],
            'strategy_types': list(report['bestByStrategy'].keys()),
            'best_overall_strategy': {
                'name': bestResult.agentName,
                'type': bestResult.agentConfig.strategyType,
                'return': bestResult.performance.get('totalReturn', 0),
                'sharpe_ratio': bestResult.performance.get('sharpeRatio', 0),
                'max_drawdown': bestResult.performance.get('maxDrawdown', 0)
            },
            'all_strategy_results': {
                strategyType: {
                    'best_agent': info['name'],
                    'performance': info['performance']
                }
                for strategyType, info in report['bestByStrategy'].items()
            },
            'recommendations': report['recommendations'],
            'performance_stats': report.get('performanceStats', {})
        }
        
        # 添加用户提供的元数据
        if metadata:
            experimentMeta.update(metadata)
            
        with open(experimentMetaFile, 'w', encoding='utf-8') as f:
            json.dump(experimentMeta, f, ensure_ascii=False, indent=2, default=str)
        
        # 保存详细的所有结果
        allResultsFile = experimentDir / 'all_results.json'
        allResults = []
        for result in results:
            allResults.append({
                'agent_name': result.agentName,
                'strategy_type': result.agentConfig.strategyType,
                'config': asdict(result.agentConfig) if hasattr(result.agentConfig, '__dict__') else result.agentConfig.__dict__,
                'performance': result.performance,
                'rank': result.rank
            })
        
        with open(allResultsFile, 'w', encoding='utf-8') as f:
            json.dump(allResults, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"实验结果已保存到: {experimentDir}")
        print(f"\n💾 实验结果已保存:")
        print(f"📁 实验目录: {experimentDir}")
        print(f"📋 策略配置: {strategyConfigFile.name}")
        print(f"📄 实验描述: {experimentMetaFile.name}")
        print(f"📊 详细结果: {allResultsFile.name}")
        
        return str(experimentDir)

    @staticmethod
    def loadExperimentConfig(experimentPath: str) -> Dict[str, Any]:
        """从实验目录加载策略配置
        
        Args:
            experimentPath: 实验目录路径
            
        Returns:
            策略配置字典
        """
        from pathlib import Path
        import json
        
        expDir = Path(experimentPath)
        if not expDir.exists():
            raise FileNotFoundError(f"实验目录不存在: {experimentPath}")
        
        configFile = expDir / 'best_strategy_config.json'
        if not configFile.exists():
            raise FileNotFoundError(f"策略配置文件不存在: {configFile}")
        
        with open(configFile, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return config 