#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
公司配置文件 (Company Configurations)
支持配置化的股票分析，便于扩展到不同公司
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any

class CompanyConfig:
    """单个公司的配置类"""
    
    def __init__(self, symbol: str, name: str, industry: str, **kwargs):
        self.symbol = symbol
        self.name = name
        self.industry = industry
        self.exchange = kwargs.get('exchange', self._extractExchange(symbol))
        self.currency = kwargs.get('currency', 'CNY')
        self.timezone = kwargs.get('timezone', 'Asia/Shanghai')
        
        # 分析配置
        self.analysisConfig = kwargs.get('analysisConfig', {})
        
        # 网格策略配置
        self.gridStrategyConfig = kwargs.get('gridStrategyConfig', {
            'gridLevels': 10,
            'gridSpacing': 0.02,
            'maxPosition': 80000,
            'commission': 0.0003,
            'slippage': 0.001,
        })
        
        # 时间配置
        self.timeConfig = kwargs.get('timeConfig', {
            'defaultPeriod': 365,  # 默认分析365天
            'startDate': None,
            'endDate': None
        })
        
        # 风险配置
        self.riskConfig = kwargs.get('riskConfig', {
            'riskFreeRate': 0.03,  # 无风险利率
            'confidenceLevels': [0.95, 0.99],  # VaR置信度
        })
    
    def _extractExchange(self, symbol: str) -> str:
        """从股票代码提取交易所"""
        if symbol.endswith('.SZ'):
            return '深圳证券交易所'
        elif symbol.endswith('.SH'):
            return '上海证券交易所'
        elif symbol.endswith('.HK'):
            return '香港证券交易所'
        else:
            return '未知交易所'
    
    def getTimeRange(self) -> tuple:
        """获取分析时间范围"""
        if self.timeConfig.get('startDate') and self.timeConfig.get('endDate'):
            return self.timeConfig['startDate'], self.timeConfig['endDate']
        
        endDate = datetime.now().strftime('%Y%m%d')
        startDate = (datetime.now() - timedelta(days=self.timeConfig['defaultPeriod'])).strftime('%Y%m%d')
        return startDate, endDate
    
    def getReportPath(self, analysisType: str) -> str:
        """获取报告输出路径"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        return f"reports/{timestamp}/{analysisType}/{self.symbol}_{self.name}"
    
    def toDict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'symbol': self.symbol,
            'name': self.name,
            'industry': self.industry,
            'exchange': self.exchange,
            'currency': self.currency,
            'timezone': self.timezone,
            'analysisConfig': self.analysisConfig,
            'gridStrategyConfig': self.gridStrategyConfig,
            'timeConfig': self.timeConfig,
            'riskConfig': self.riskConfig
        }

class CompanyConfigManager:
    """公司配置管理器"""
    
    def __init__(self):
        self.companies = {}
        self._loadDefaultConfigs()
    
    def _loadDefaultConfigs(self):
        """加载默认的公司配置"""
        
        # 比亚迪配置
        byd_config = CompanyConfig(
            symbol='002594.SZ',
            name='比亚迪',
            industry='汽车整车制造',
            analysisConfig={
                'includeBasicAnalysis': True,
                'includeTechnicalAnalysis': True,
                'includeRiskAnalysis': True,
                'includeGridStrategy': True,
                'includeParameterOptimization': True
            },
            gridStrategyConfig={
                'gridLevels': 10,
                'gridSpacing': 0.02,
                'maxPosition': 80000,
                'commission': 0.0003,
                'slippage': 0.001,
            },
            timeConfig={
                'defaultPeriod': 365,
            }
        )
        
        # 平安银行配置
        ping_an_config = CompanyConfig(
            symbol='000001.SZ',
            name='平安银行',
            industry='银行业',
            analysisConfig={
                'includeBasicAnalysis': True,
                'includeTechnicalAnalysis': True,
                'includeRiskAnalysis': True,
                'includeGridStrategy': True,
                'includeParameterOptimization': False  # 银行股波动较小，可能不适合网格策略
            },
            gridStrategyConfig={
                'gridLevels': 8,
                'gridSpacing': 0.015,  # 银行股波动较小，网格间距设小一些
                'maxPosition': 100000,
                'commission': 0.0003,
                'slippage': 0.0005,
            }
        )
        
        # 贵州茅台配置
        maotai_config = CompanyConfig(
            symbol='600519.SH',
            name='贵州茅台',
            industry='白酒制造',
            analysisConfig={
                'includeBasicAnalysis': True,
                'includeTechnicalAnalysis': True,
                'includeRiskAnalysis': True,
                'includeGridStrategy': True,
                'includeParameterOptimization': True
            },
            gridStrategyConfig={
                'gridLevels': 12,
                'gridSpacing': 0.025,  # 高价股，网格间距设大一些
                'maxPosition': 50000,  # 高价股，仓位设小一些
                'commission': 0.0003,
                'slippage': 0.001,
            }
        )
        
        # 注册公司配置
        self.registerCompany('BYD', byd_config)
        self.registerCompany('PING_AN', ping_an_config)
        self.registerCompany('MAOTAI', maotai_config)
    
    def registerCompany(self, companyId: str, config: CompanyConfig):
        """注册公司配置"""
        self.companies[companyId] = config
    
    def getCompany(self, companyId: str) -> CompanyConfig:
        """获取公司配置"""
        if companyId not in self.companies:
            raise ValueError(f"未找到公司配置: {companyId}")
        return self.companies[companyId]
    
    def getCompanyBySymbol(self, symbol: str) -> CompanyConfig:
        """根据股票代码获取公司配置"""
        for config in self.companies.values():
            if config.symbol == symbol:
                return config
        raise ValueError(f"未找到股票代码对应的公司配置: {symbol}")
    
    def listCompanies(self) -> List[str]:
        """列出所有可用的公司ID"""
        return list(self.companies.keys())
    
    def getCompanyInfo(self, companyId: str) -> Dict[str, str]:
        """获取公司基本信息"""
        config = self.getCompany(companyId)
        return {
            'companyId': companyId,
            'symbol': config.symbol,
            'name': config.name,
            'industry': config.industry,
            'exchange': config.exchange
        }
    
    def addCustomCompany(self, companyId: str, symbol: str, name: str, 
                        industry: str, **kwargs) -> CompanyConfig:
        """添加自定义公司配置"""
        config = CompanyConfig(symbol, name, industry, **kwargs)
        self.registerCompany(companyId, config)
        return config

# 全局配置管理器实例
companyManager = CompanyConfigManager()

# 便捷函数
def getCompanyConfig(companyId: str) -> CompanyConfig:
    """获取公司配置的便捷函数"""
    return companyManager.getCompany(companyId)

def listAvailableCompanies() -> List[Dict[str, str]]:
    """列出所有可用公司的便捷函数"""
    return [companyManager.getCompanyInfo(cid) for cid in companyManager.listCompanies()]

def addCompany(companyId: str, symbol: str, name: str, industry: str, **kwargs) -> CompanyConfig:
    """添加公司的便捷函数"""
    return companyManager.addCustomCompany(companyId, symbol, name, industry, **kwargs) 