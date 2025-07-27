"""
Stock-specific configuration management system
股票特定配置管理系统
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import os

@dataclass
class GridStrategyConfig:
    """网格策略配置"""
    gridLevels: int = 10
    gridSpacing: float = 0.02  # 2%
    maxPosition: int = 100000
    baseRatio: float = 0.3  # 30% as base position
    commission: float = 0.0003
    slippage: float = 0.001
    stopLoss: Optional[float] = None  # Stop loss percentage
    takeProfit: Optional[float] = None  # Take profit percentage
    
@dataclass  
class DCAStrategyConfig:
    """定投策略配置"""
    interval: str = 'weekly'  # daily, weekly, monthly
    amount: float = 1000
    maxPosition: int = 100000
    baseRatio: float = 0.5
    commission: float = 0.0003
    
@dataclass
class MomentumStrategyConfig:
    """动量策略配置"""
    lookbackPeriod: int = 20
    threshold: float = 0.05
    maxPosition: int = 100000
    baseRatio: float = 0.2
    commission: float = 0.0003
    
@dataclass
class StockConfig:
    """股票特定配置"""
    symbol: str
    name: str
    industry: str
    market: str  # A股、港股、美股
    riskLevel: str  # low, medium, high
    
    # Different strategy configurations
    gridStrategy: GridStrategyConfig
    dcaStrategy: DCAStrategyConfig
    momentumStrategy: MomentumStrategyConfig
    
    # Market specific parameters
    minPriceUnit: float = 0.01  # Minimum price unit
    lotSize: int = 100  # Trading lot size
    tradingHours: Dict[str, str] = None
    
    def __post_init__(self):
        if self.tradingHours is None:
            if self.market == 'A股':
                self.tradingHours = {
                    'morning': '09:30-11:30',
                    'afternoon': '13:00-15:00'
                }
            elif self.market == '港股':
                self.tradingHours = {
                    'morning': '09:30-12:00',
                    'afternoon': '13:00-16:00'
                }
            elif self.market == '美股':
                self.tradingHours = {
                    'regular': '09:30-16:00'
                }

class StockConfigManager:
    """股票配置管理器"""
    
    def __init__(self, configDir: str = "config/stocks"):
        self.configDir = Path(configDir)
        self.configDir.mkdir(parents=True, exist_ok=True)
        self._configs: Dict[str, StockConfig] = {}
        self._loadConfigs()
    
    def _loadConfigs(self):
        """加载所有配置文件"""
        for configFile in self.configDir.glob("*.json"):
            try:
                with open(configFile, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    config = self._dictToStockConfig(data)
                    self._configs[config.symbol] = config
            except Exception as e:
                print(f"Failed to load config from {configFile}: {str(e)}")
    
    def _dictToStockConfig(self, data: Dict) -> StockConfig:
        """将字典转换为StockConfig对象"""
        # Convert nested dict to dataclass objects
        gridStrategy = GridStrategyConfig(**data.get('gridStrategy', {}))
        dcaStrategy = DCAStrategyConfig(**data.get('dcaStrategy', {}))
        momentumStrategy = MomentumStrategyConfig(**data.get('momentumStrategy', {}))
        
        return StockConfig(
            symbol=data['symbol'],
            name=data['name'],
            industry=data['industry'],
            market=data['market'],
            riskLevel=data['riskLevel'],
            gridStrategy=gridStrategy,
            dcaStrategy=dcaStrategy,
            momentumStrategy=momentumStrategy,
            minPriceUnit=data.get('minPriceUnit', 0.01),
            lotSize=data.get('lotSize', 100),
            tradingHours=data.get('tradingHours')
        )
    
    def getConfig(self, symbol: str) -> Optional[StockConfig]:
        """获取指定股票的配置"""
        return self._configs.get(symbol.upper())
    
    def saveConfig(self, config: StockConfig):
        """保存股票配置"""
        configPath = self.configDir / f"{config.symbol}.json"
        with open(configPath, 'w', encoding='utf-8') as f:
            json.dump(asdict(config), f, ensure_ascii=False, indent=2)
        self._configs[config.symbol] = config
    
    def createDefaultConfig(self, symbol: str, name: str, industry: str, 
                          market: str, riskLevel: str = 'medium') -> StockConfig:
        """创建默认配置"""
        # Adjust default parameters based on risk level
        if riskLevel == 'low':
            gridConfig = GridStrategyConfig(
                gridLevels=8, gridSpacing=0.025, baseRatio=0.5
            )
        elif riskLevel == 'high':
            gridConfig = GridStrategyConfig(
                gridLevels=15, gridSpacing=0.015, baseRatio=0.2
            )
        else:  # medium
            gridConfig = GridStrategyConfig()
        
        config = StockConfig(
            symbol=symbol.upper(),
            name=name,
            industry=industry,
            market=market,
            riskLevel=riskLevel,
            gridStrategy=gridConfig,
            dcaStrategy=DCAStrategyConfig(),
            momentumStrategy=MomentumStrategyConfig()
        )
        
        self.saveConfig(config)
        return config
    
    def listConfigs(self) -> List[str]:
        """列出所有已配置的股票"""
        return list(self._configs.keys())
    
    def generateVariants(self, symbol: str, strategyType: str = 'grid') -> List[Dict[str, Any]]:
        """为指定股票生成策略变体"""
        baseConfig = self.getConfig(symbol)
        if not baseConfig:
            raise ValueError(f"No configuration found for {symbol}")
        
        variants = []
        
        if strategyType == 'grid':
            # Generate grid strategy variants
            gridLevelsRange = [6, 8, 10, 12, 15]
            gridSpacingRange = [0.01, 0.015, 0.02, 0.025, 0.03]
            baseRatioRange = [0.1, 0.2, 0.3, 0.4, 0.5]
            
            for levels in gridLevelsRange:
                for spacing in gridSpacingRange:
                    for baseRatio in baseRatioRange:
                        variant = asdict(baseConfig.gridStrategy)
                        variant.update({
                            'gridLevels': levels,
                            'gridSpacing': spacing,
                            'baseRatio': baseRatio
                        })
                        variants.append({
                            'strategy': 'grid',
                            'symbol': symbol,
                            'config': variant
                        })
        
        elif strategyType == 'dca':
            # Generate DCA strategy variants
            intervalRange = ['daily', 'weekly', 'monthly']
            amountRange = [500, 1000, 2000, 5000]
            baseRatioRange = [0.3, 0.4, 0.5, 0.6]
            
            for interval in intervalRange:
                for amount in amountRange:
                    for baseRatio in baseRatioRange:
                        variant = asdict(baseConfig.dcaStrategy)
                        variant.update({
                            'interval': interval,
                            'amount': amount,
                            'baseRatio': baseRatio
                        })
                        variants.append({
                            'strategy': 'dca',
                            'symbol': symbol,
                            'config': variant
                        })
        
        return variants

# Global instance
_configManager = None

def getStockConfigManager() -> StockConfigManager:
    """获取全局配置管理器实例"""
    global _configManager
    if _configManager is None:
        _configManager = StockConfigManager()
    return _configManager 