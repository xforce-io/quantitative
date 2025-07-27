from functools import wraps
from typing import Any, Optional, Dict, List, Callable
import logging
from .cache_manager import getCacheManager
from .base_data_provider import BaseDataProvider

logger = logging.getLogger(__name__)

def cacheApiCall(apiType: str, expiryHours: int = 240):
    """
    API调用缓存装饰器
    
    Args:
        apiType: API类型标识
        expiryHours: 缓存过期时间（小时）
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, symbol: str, *args, **kwargs) -> Any:
            # 获取缓存管理器
            cacheManager = getCacheManager()
            
            # 构建缓存参数
            cacheParams = {
                'args': args,
                'kwargs': kwargs
            }
            
            # 尝试从缓存获取数据
            cachedData = cacheManager.get(
                provider=self.providerName,
                apiType=apiType,
                symbol=symbol,
                expiryHours=expiryHours,
                **cacheParams
            )
            
            if cachedData is not None:
                return cachedData
            
            # 缓存未命中，调用原始函数
            try:
                result = func(self, symbol, *args, **kwargs)
                
                # 如果结果不为空，缓存结果
                if result is not None:
                    cacheManager.set(
                        provider=self.providerName,
                        apiType=apiType,
                        symbol=symbol,
                        data=result,
                        **cacheParams
                    )
                
                return result
                
            except Exception as e:
                logger.error(f"Error in {func.__name__} for {symbol}: {e}")
                raise
        
        return wrapper
    return decorator

class CachedDataProvider:
    """缓存数据提供者代理类"""
    
    def __init__(self, provider: BaseDataProvider, providerName: str):
        """
        初始化缓存代理
        
        Args:
            provider: 原始数据提供者
            providerName: 提供者名称（用于缓存标识）
        """
        self.provider = provider
        self.providerName = providerName
        self.cacheManager = getCacheManager()
    
    def getStockData(self, symbol: str, startDate: str, endDate: str, 
                    frequency: str = 'D', expiryHours: int = 240) -> Optional[Any]:
        """
        获取股票数据（带缓存）
        
        Args:
            symbol: 股票代码
            startDate: 开始日期
            endDate: 结束日期
            frequency: 数据频率
            expiryHours: 缓存过期时间
        """
        # 构建缓存参数
        cacheParams = {
            'start_date': startDate,
            'end_date': endDate,
            'frequency': frequency
        }
        
        # 尝试从缓存获取
        cachedData = self.cacheManager.get(
            provider=self.providerName,
            apiType='stock_data',
            symbol=symbol,
            expiryHours=expiryHours,
            **cacheParams
        )
        
        if cachedData is not None:
            return cachedData
        
        # 缓存未命中，调用原始方法
        try:
            result = self.provider.getStockData(symbol, startDate, endDate, frequency)
            
            if result is not None:
                self.cacheManager.set(
                    provider=self.providerName,
                    apiType='stock_data',
                    symbol=symbol,
                    data=result,
                    **cacheParams
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting stock data for {symbol}: {e}")
            raise
    
    def getCompanyInfo(self, symbol: str, expiryHours: int = 168) -> Optional[Dict]:
        """
        获取公司信息（带缓存，默认7天过期）
        
        Args:
            symbol: 股票代码
            expiryHours: 缓存过期时间（默认168小时=7天）
        """
        # 尝试从缓存获取
        cachedData = self.cacheManager.get(
            provider=self.providerName,
            apiType='company_info',
            symbol=symbol,
            expiryHours=expiryHours
        )
        
        if cachedData is not None:
            return cachedData
        
        # 缓存未命中，调用原始方法
        try:
            result = self.provider.getCompanyInfo(symbol)
            
            if result is not None:
                self.cacheManager.set(
                    provider=self.providerName,
                    apiType='company_info',
                    symbol=symbol,
                    data=result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting company info for {symbol}: {e}")
            raise
    
    def getFinancialData(self, symbol: str, expiryHours: int = 72) -> Optional[Dict]:
        """
        获取财务数据（带缓存，默认3天过期）
        
        Args:
            symbol: 股票代码
            expiryHours: 缓存过期时间（默认72小时=3天）
        """
        # 尝试从缓存获取
        cachedData = self.cacheManager.get(
            provider=self.providerName,
            apiType='financial_data',
            symbol=symbol,
            expiryHours=expiryHours
        )
        
        if cachedData is not None:
            return cachedData
        
        # 缓存未命中，调用原始方法
        try:
            result = self.provider.getFinancialData(symbol)
            
            if result is not None:
                self.cacheManager.set(
                    provider=self.providerName,
                    apiType='financial_data',
                    symbol=symbol,
                    data=result
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting financial data for {symbol}: {e}")
            raise

    def getIndexData(self, symbol: str, startDate: str, endDate: str, 
                    frequency: str = 'D', expiryHours: int = 240) -> Optional[Any]:
        """
        获取指数数据（带缓存）
        
        Args:
            symbol: 指数代码
            startDate: 开始日期
            endDate: 结束日期
            frequency: 数据频率
            expiryHours: 缓存过期时间
        """
        # 构建缓存参数
        cacheParams = {
            'start_date': startDate,
            'end_date': endDate,
            'frequency': frequency
        }
        
        # 尝试从缓存获取
        cachedData = self.cacheManager.get(
            provider=self.providerName,
            apiType='index_data',
            symbol=symbol,
            expiryHours=expiryHours,
            **cacheParams
        )
        
        if cachedData is not None:
            return cachedData
        
        # 缓存未命中，调用原始方法
        try:
            # 检查原始提供者是否支持getIndexData方法
            if hasattr(self.provider, 'getIndexData'):
                logger.info(f"Using dedicated getIndexData method for {symbol}")
                result = self.provider.getIndexData(symbol, startDate, endDate, frequency)
            else:
                logger.warning(f"Provider {self.providerName} does not support getIndexData, using getStockData as fallback for {symbol}")
                # 如果不支持，回退到getStockData方法（但要注意这可能不适用于所有指数）
                result = self.provider.getStockData(symbol, startDate, endDate, frequency)
            
            if result is not None:
                self.cacheManager.set(
                    provider=self.providerName,
                    apiType='index_data',
                    symbol=symbol,
                    data=result,
                    **cacheParams
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting index data for {symbol}: {e}")
            # 对于指数数据，不要回退到getStockData，因为可能会导致"No data found"错误
            # 直接抛出异常，让上层处理
            raise
    
    def clearCache(self):
        """清理该provider的所有缓存"""
        self.cacheManager.clearProvider(self.providerName)
    
    def getCacheStats(self) -> Dict:
        """获取缓存统计信息"""
        return self.cacheManager.getCacheStats()
    
    def __getattr__(self, name):
        """代理其他方法到原始provider"""
        return getattr(self.provider, name) 