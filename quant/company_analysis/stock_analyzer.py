#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
通用股票分析器 (Universal Stock Analyzer)
支持配置化的股票分析，可以分析任何配置的公司
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import warnings
warnings.filterwarnings('ignore')

# 导入系统模块
from ..data_providers.data_provider_factory import createDataProvider
from ..engines.backtest_engine import BacktestEngine
from .company_configs import CompanyConfig, getCompanyConfig

class UniversalStockAnalyzer:
    """通用股票分析器"""
    
    def __init__(self, dataProviderType: str = 'tushare'):
        """
        初始化分析器
        
        Args:
            dataProviderType: 数据提供者类型
        """
        self.dataProviderType = dataProviderType
        self.dataProvider = createDataProvider(dataProviderType)
        self.backtestEngine = BacktestEngine(dataProviderType)
        
        # 设置matplotlib
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['axes.unicode_minus'] = False
    
    def analyzeCompany(self, companyId: str, saveReports: bool = True) -> Dict[str, Any]:
        """
        分析指定公司
        
        Args:
            companyId: 公司ID（在配置中定义）
            saveReports: 是否保存报告
            
        Returns:
            分析结果字典
        """
        print(f"=== 开始分析公司: {companyId} ===")
        
        # 获取公司配置
        config = getCompanyConfig(companyId)
        print(f"公司名称: {config.name}")
        print(f"股票代码: {config.symbol}")
        print(f"所属行业: {config.industry}")
        print(f"交易所: {config.exchange}")
        print("-" * 60)
        
        # 获取时间范围
        startDate, endDate = config.getTimeRange()
        print(f"分析时间范围: {startDate} 到 {endDate}")
        
        # 获取股票数据
        print("正在获取股票数据...")
        stockData = self.dataProvider.getStockData(config.symbol, startDate, endDate)
        
        if stockData.empty:
            print(f"❌ 无法获取 {config.symbol} 的数据")
            return {}
        
        print(f"✓ 成功获取 {len(stockData)} 条数据记录")
        print("-" * 60)
        
        # 执行各种分析
        results = {
            'companyInfo': config.toDict(),
            'dataInfo': {
                'dataCount': len(stockData),
                'startDate': stockData.index[0].strftime('%Y-%m-%d'),
                'endDate': stockData.index[-1].strftime('%Y-%m-%d'),
                'analysisTimestamp': datetime.now().isoformat()
            }
        }
        
        # 基础分析
        if config.analysisConfig.get('includeBasicAnalysis', True):
            print("正在执行基础分析...")
            results['basicAnalysis'] = self._performBasicAnalysis(stockData, config)
            if saveReports:
                self._saveBasicAnalysisReport(results['basicAnalysis'], config)
        
        # 技术分析
        if config.analysisConfig.get('includeTechnicalAnalysis', True):
            print("正在执行技术分析...")
            results['technicalAnalysis'] = self._performTechnicalAnalysis(stockData, config)
            if saveReports:
                self._saveTechnicalAnalysisReport(results['technicalAnalysis'], config)
        
        # 风险分析
        if config.analysisConfig.get('includeRiskAnalysis', True):
            print("正在执行风险分析...")
            results['riskAnalysis'] = self._performRiskAnalysis(stockData, config)
            if saveReports:
                self._saveRiskAnalysisReport(results['riskAnalysis'], config)
        
        # 基于代理的策略分析
        if config.analysisConfig.get('includeAgentStrategy', True):
            print("🤖 正在执行基于代理的策略分析...")
            results['agentBasedAnalysis'] = self._performAgentBasedAnalysis(
                stockData, config, startDate, endDate
            )
            if saveReports:
                self._saveAgentAnalysisReport(results['agentBasedAnalysis'], config)
        
        # 参数优化
        if config.analysisConfig.get('includeParameterOptimization', False):
            print("正在执行参数优化...")
            results['parameterOptimization'] = self._performParameterOptimization(
                config, startDate, endDate
            )
            if saveReports:
                self._saveOptimizationReport(results['parameterOptimization'], config)
        
        # 生成综合报告
        if saveReports:
            self._saveComprehensiveReport(results, config)
        
        print(f"✓ 公司 {companyId} 分析完成")
        return results
    
    def _performBasicAnalysis(self, stockData: pd.DataFrame, config: CompanyConfig) -> Dict[str, Any]:
        """执行基础分析"""
        
        latestPrice = stockData['close'].iloc[-1]
        firstPrice = stockData['close'].iloc[0]
        maxPrice = stockData['close'].max()
        minPrice = stockData['close'].min()
        avgPrice = stockData['close'].mean()
        medianPrice = stockData['close'].median()
        
        # 找到最高价和最低价的日期
        maxDate = stockData[stockData['close'] == maxPrice].index[0].strftime('%Y-%m-%d')
        minDate = stockData[stockData['close'] == minPrice].index[0].strftime('%Y-%m-%d')
        
        # 收益率分析
        totalReturn = (latestPrice - firstPrice) / firstPrice * 100
        dailyReturns = stockData['returns'].dropna()
        annualizedReturn = (latestPrice / firstPrice) ** (252 / len(stockData)) - 1
        
        # 交易量分析
        avgVolume = stockData['volume'].mean()
        maxVolume = stockData['volume'].max()
        avgAmount = stockData['amount'].mean() * 1000  # 转换为元
        
        return {
            'priceStatistics': {
                'latestPrice': float(latestPrice),
                'firstPrice': float(firstPrice),
                'maxPrice': float(maxPrice),
                'minPrice': float(minPrice),
                'avgPrice': float(avgPrice),
                'medianPrice': float(medianPrice),
                'maxDate': maxDate,
                'minDate': minDate,
                'priceRange': float((maxPrice - minPrice) / minPrice * 100)
            },
            'returnStatistics': {
                'totalReturn': float(totalReturn),
                'annualizedReturn': float(annualizedReturn * 100),
                'maxDailyGain': float(dailyReturns.max() * 100),
                'maxDailyLoss': float(dailyReturns.min() * 100),
                'avgDailyReturn': float(dailyReturns.mean() * 100),
                'volatility': float(dailyReturns.std() * np.sqrt(252) * 100)
            },
            'volumeStatistics': {
                'avgVolume': float(avgVolume),
                'maxVolume': float(maxVolume),
                'avgAmount': float(avgAmount)
            }
        }
    
    def _performTechnicalAnalysis(self, stockData: pd.DataFrame, config: CompanyConfig) -> Dict[str, Any]:
        """执行技术分析"""
        
        latestPrice = stockData['close'].iloc[-1]
        ma5 = stockData['ma5'].iloc[-1] if 'ma5' in stockData.columns else None
        ma20 = stockData['ma20'].iloc[-1] if 'ma20' in stockData.columns else None
        ma60 = stockData['ma60'].iloc[-1] if 'ma60' in stockData.columns else None
        
        # 趋势判断
        trend = "横盘整理"
        if ma5 and ma20 and ma60:
            if latestPrice > ma5 > ma20 > ma60:
                trend = "强势上涨趋势"
            elif latestPrice > ma5 > ma20:
                trend = "上涨趋势"
            elif latestPrice < ma5 < ma20 < ma60:
                trend = "下跌趋势"
            elif latestPrice < ma5:
                trend = "短期调整"
        
        return {
            'movingAverages': {
                'currentPrice': float(latestPrice),
                'ma5': float(ma5) if ma5 else None,
                'ma20': float(ma20) if ma20 else None,
                'ma60': float(ma60) if ma60 else None,
            },
            'trendAnalysis': {
                'trend': trend,
                'aboveMa5': bool(latestPrice > ma5) if ma5 else None,
                'aboveMa20': bool(latestPrice > ma20) if ma20 else None,
                'aboveMa60': bool(latestPrice > ma60) if ma60 else None,
            }
        }
    
    def _performRiskAnalysis(self, stockData: pd.DataFrame, config: CompanyConfig) -> Dict[str, Any]:
        """执行风险分析"""
        
        returns = stockData['returns'].dropna()
        
        # 计算最大回撤
        cumulative = (1 + returns).cumprod()
        maxDrawdown = ((cumulative / cumulative.expanding().max()) - 1).min()
        
        # VaR计算
        confidenceLevels = config.riskConfig.get('confidenceLevels', [0.95, 0.99])
        var_results = {}
        for level in confidenceLevels:
            var_value = np.percentile(returns * 100, (1 - level) * 100)
            var_results[f'VaR_{int(level*100)}'] = float(var_value)
        
        # 夏普比率
        riskFreeRate = config.riskConfig.get('riskFreeRate', 0.03)
        excessReturn = returns.mean() * 252 - riskFreeRate
        sharpeRatio = excessReturn / (returns.std() * np.sqrt(252))
        
        # 风险等级评估
        if abs(maxDrawdown) > 0.25:
            riskLevel = "高风险"
        elif abs(maxDrawdown) > 0.15:
            riskLevel = "中等风险"
        else:
            riskLevel = "相对低风险"
        
        return {
            'riskMetrics': {
                'maxDrawdown': float(maxDrawdown),
                'sharpeRatio': float(sharpeRatio),
                'volatility': float(returns.std() * np.sqrt(252)),
                'riskLevel': riskLevel
            },
            'valueAtRisk': var_results
        }
    
    def _performAgentBasedAnalysis(self, stockData: pd.DataFrame, config: CompanyConfig, 
                                 startDate: str, endDate: str) -> Dict[str, Any]:
        """执行基于代理的策略分析"""
        
        try:
            from ..agents.agent_manager import AgentManager, AgentOptimizationConfig
            
            # Initialize agent manager
            agentManager = AgentManager(self.dataProviderType)
            
            # Generate agent variants for different strategy types
            allAgentConfigs = []
            
            # Grid agents
            gridOptConfig = AgentOptimizationConfig(
                agentType='grid',
                parameterRanges={
                    'gridLevels': [8, 10, 12],
                    'gridSpacing': [0.015, 0.02, 0.025],
                    'baseRatio': [0.2, 0.3, 0.4],
                    'maxPosition': [100000]
                },
                riskProfile='moderate',
                maxVariants=20
            )
            gridAgents = agentManager.generateAgentVariants('grid', config.symbol, gridOptConfig)
            allAgentConfigs.extend(gridAgents)
            
            # DCA agents
            dcaOptConfig = AgentOptimizationConfig(
                agentType='dca',
                parameterRanges={
                    'interval': ['weekly', 'monthly'],
                    'amount': [1000, 2000],
                    'baseRatio': [0.3, 0.4, 0.5]
                },
                riskProfile='conservative',
                maxVariants=10
            )
            dcaAgents = agentManager.generateAgentVariants('dca', config.symbol, dcaOptConfig)
            allAgentConfigs.extend(dcaAgents)
            
            # Momentum agents
            momentumOptConfig = AgentOptimizationConfig(
                agentType='momentum',
                parameterRanges={
                    'lookbackPeriod': [10, 20, 30],
                    'threshold': [0.03, 0.05, 0.07],
                    'baseRatio': [0.1, 0.2, 0.3]
                },
                riskProfile='aggressive',
                maxVariants=15
            )
            momentumAgents = agentManager.generateAgentVariants('momentum', config.symbol, momentumOptConfig)
            allAgentConfigs.extend(momentumAgents)
            
            # Optimize all agents
            optimizationResults = agentManager.optimizeAgents(
                symbol=config.symbol,
                startDate=startDate,
                endDate=endDate,
                agentConfigs=allAgentConfigs,
                initialCapital=100000
            )
            
            # Generate comprehensive report
            report = agentManager.generateOptimizationReport(config.symbol, optimizationResults)
            
            return {
                'agentOptimization': report,
                'totalAgentsTested': len(allAgentConfigs),
                'bestAgent': report.get('bestOverall', {}),
                'bestByStrategy': report.get('bestByStrategy', {}),
                'performanceStats': report.get('performanceStats', {}),
                'recommendations': report.get('recommendations', [])
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'agentOptimization': None
            }
    
    def _performParameterOptimization(self, config: CompanyConfig, 
                                    startDate: str, endDate: str) -> Dict[str, Any]:
        """执行参数优化"""
        
        try:
            # 定义参数搜索范围
            parameterRanges = {
                'gridLevels': [8, 10, 12],
                'gridSpacing': [0.015, 0.02, 0.025],
                'maxPosition': [60000, 80000, 100000]
            }
            
            result = self.backtestEngine.optimizeParameters(
                symbol=config.symbol,
                startDate=startDate,
                endDate=endDate,
                parameterRanges=parameterRanges
            )
            
            return {
                'searchSpace': parameterRanges,
                'bestParameters': result.get('bestParameters', {}),
                'bestPerformance': result.get('bestPerformance', {}),
                'optimizationResults': result.get('allResults', [])
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'searchSpace': {}
            }
    
    def _ensureReportDir(self, reportPath: str):
        """确保报告目录存在"""
        os.makedirs(reportPath, exist_ok=True)
    
    def _saveBasicAnalysisReport(self, analysis: Dict[str, Any], config: CompanyConfig):
        """保存基础分析报告"""
        reportPath = config.getReportPath('basic_analysis')
        self._ensureReportDir(reportPath)
        
        with open(f"{reportPath}/basic_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    def _saveTechnicalAnalysisReport(self, analysis: Dict[str, Any], config: CompanyConfig):
        """保存技术分析报告"""
        reportPath = config.getReportPath('technical_analysis')
        self._ensureReportDir(reportPath)
        
        with open(f"{reportPath}/technical_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    def _saveRiskAnalysisReport(self, analysis: Dict[str, Any], config: CompanyConfig):
        """保存风险分析报告"""
        reportPath = config.getReportPath('risk_analysis')
        self._ensureReportDir(reportPath)
        
        with open(f"{reportPath}/risk_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    def _saveAgentAnalysisReport(self, analysis: Dict[str, Any], config: CompanyConfig):
        """保存代理分析报告"""
        reportPath = config.getReportPath('agent_analysis')
        self._ensureReportDir(reportPath)
        
        with open(f"{reportPath}/agent_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
    
    def _saveOptimizationReport(self, analysis: Dict[str, Any], config: CompanyConfig):
        """保存优化报告"""
        reportPath = config.getReportPath('parameter_optimization')
        self._ensureReportDir(reportPath)
        
        with open(f"{reportPath}/parameter_optimization.json", 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    
    def _saveComprehensiveReport(self, results: Dict[str, Any], config: CompanyConfig):
        """保存综合报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        reportPath = f"reports/{timestamp}/comprehensive/{config.symbol}_{config.name}"
        self._ensureReportDir(reportPath)
        
        # 保存完整结果
        with open(f"{reportPath}/comprehensive_analysis.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # 生成markdown报告
        self._generateMarkdownReport(results, config, reportPath)
    
    def _generateMarkdownReport(self, results: Dict[str, Any], config: CompanyConfig, reportPath: str):
        """生成markdown格式的报告"""
        
        basic = results.get('basicAnalysis', {})
        technical = results.get('technicalAnalysis', {})
        risk = results.get('riskAnalysis', {})
        grid = results.get('gridStrategyAnalysis', {})
        
        report = f"""# {config.name} 股票分析报告

## 📊 基本信息
- **股票代码**: {config.symbol}
- **公司名称**: {config.name}
- **所属行业**: {config.industry}
- **交易所**: {config.exchange}
- **分析时间**: {results['dataInfo']['analysisTimestamp']}

## 📈 价格分析
"""
        
        if basic:
            priceStats = basic.get('priceStatistics', {})
            returnStats = basic.get('returnStatistics', {})
            
            report += f"""
- **当前价格**: ¥{priceStats.get('latestPrice', 0):.2f}
- **期间最高**: ¥{priceStats.get('maxPrice', 0):.2f} ({priceStats.get('maxDate', 'N/A')})
- **期间最低**: ¥{priceStats.get('minPrice', 0):.2f} ({priceStats.get('minDate', 'N/A')})
- **期间总收益率**: {returnStats.get('totalReturn', 0):.2f}%
- **年化收益率**: {returnStats.get('annualizedReturn', 0):.2f}%
- **年化波动率**: {returnStats.get('volatility', 0):.2f}%
"""
        
        if technical:
            trend = technical.get('trendAnalysis', {})
            report += f"""
## 📊 技术分析
- **趋势判断**: {trend.get('trend', 'N/A')}
"""
        
        if risk:
            riskMetrics = risk.get('riskMetrics', {})
            report += f"""
## ⚠️ 风险分析
- **最大回撤**: {riskMetrics.get('maxDrawdown', 0):.2%}
- **夏普比率**: {riskMetrics.get('sharpeRatio', 0):.3f}
- **风险等级**: {riskMetrics.get('riskLevel', 'N/A')}
"""
        
        if grid and 'performance' in grid:
            gridPerf = grid['performance']
            report += f"""
## 🔄 网格策略表现
- **策略收益率**: {gridPerf.get('totalReturn', 0):.2%}
- **基准收益率**: {gridPerf.get('benchmarkReturn', 0):.2%}
- **交易次数**: {gridPerf.get('totalTrades', 0)}
- **胜率**: {gridPerf.get('winRate', 0):.2%}
"""
        
        report += f"""
---
*本报告由量化交易系统自动生成，仅供参考，不构成投资建议*
"""
        
        with open(f"{reportPath}/report.md", 'w', encoding='utf-8') as f:
            f.write(report) 