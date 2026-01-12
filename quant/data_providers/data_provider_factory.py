#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Data Provider Factory
数据提供者工厂

This module provides a factory pattern for creating different data providers
此模块提供工厂模式来创建不同的数据提供者
"""

from typing import Dict, Type, List
from .base_data_provider import BaseDataProvider
from .data_provider import TushareDataProvider
from .yahoo_data_provider import YahooDataProvider
from .cached_provider import CachedDataProvider

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


class DataProviderFactory:
    """Factory class for creating data providers"""
    
    # Registry of available providers
    _providers: Dict[str, Type[BaseDataProvider]] = {
        'tushare': TushareDataProvider,
        'yahoo': YahooDataProvider,
    }
    
    @classmethod
    def create(cls, providerName: str, config: Dict = None, enableCache: bool = True) -> BaseDataProvider:
        """
        Create a data provider instance
        
        Args:
            providerName (str): Name of the provider ('tushare', 'yahoo', etc.)
            config (Dict): Provider-specific configuration
            enableCache (bool): Whether to enable caching
            
        Returns:
            BaseDataProvider: Data provider instance
            
        Raises:
            ValueError: If provider name is not supported
        """
        providerName = providerName.lower().strip()
        
        if providerName not in cls._providers:
            available = ', '.join(cls._providers.keys())
            raise ValueError(f"Unsupported provider '{providerName}'. Available providers: {available}")
        
        providerClass = cls._providers[providerName]
        
        try:
            provider = providerClass(config)
            
            # Wrap with cache if enabled
            if enableCache:
                return CachedDataProvider(provider, providerName)
            else:
                return provider
                
        except Exception as e:
            raise RuntimeError(f"Failed to create {providerName} provider: {str(e)}")
    
    @classmethod
    def getAvailableProviders(cls) -> List[str]:
        """
        Get list of available provider names
        
        Returns:
            List[str]: List of provider names
        """
        return list(cls._providers.keys())
    
    @classmethod
    def registerProvider(cls, name: str, providerClass: Type[BaseDataProvider]):
        """
        Register a new data provider
        
        Args:
            name (str): Provider name
            providerClass (Type[BaseDataProvider]): Provider class
        """
        if not issubclass(providerClass, BaseDataProvider):
            raise ValueError("Provider class must inherit from BaseDataProvider")
        
        cls._providers[name.lower()] = providerClass
    
    @classmethod
    def getProviderInfo(cls, providerName: str = None) -> Dict:
        """
        Get information about providers
        
        Args:
            providerName (str, optional): Specific provider name
            
        Returns:
            Dict: Provider information
        """
        if providerName:
            providerName = providerName.lower()
            if providerName not in cls._providers:
                raise ValueError(f"Provider '{providerName}' not found")
            
            try:
                # Create a temporary instance to get info
                provider = cls._providers[providerName]()
                return provider.getProviderInfo()
            except:
                return {
                    'name': providerName,
                    'class': cls._providers[providerName].__name__,
                    'status': 'Not available (configuration required)'
                }
        else:
            # Return info for all providers
            info = {}
            for name in cls._providers:
                try:
                    info[name] = cls.getProviderInfo(name)
                except:
                    info[name] = {
                        'name': name,
                        'status': 'Error getting info'
                    }
            return info

class AutoDataProvider:
    """
    Automatic data provider that chooses the best available provider
    自动数据提供者，选择最佳可用的数据源
    """
    
    def __init__(self, preferredProviders: List[str] = None, config: Dict = None, enableCache: bool = True):
        """
        Initialize auto data provider
        
        Args:
            preferredProviders (List[str]): Ordered list of preferred providers
            config (Dict): Configuration for providers
            enableCache (bool): Whether to enable caching
        """
        self.preferredProviders = preferredProviders or ['tushare', 'yahoo']
        self.config = config or {}
        self.enableCache = enableCache
        self.activeProvider = None
        self._initializeProvider()
    
    def _initializeProvider(self):
        """Initialize the first available provider"""
        for providerName in self.preferredProviders:
            try:
                providerConfig = self.config.get(providerName, {})
                self.activeProvider = DataProviderFactory.create(providerName, providerConfig, self.enableCache)
                cacheStatus = "with cache" if self.enableCache else "without cache"
                logger.info("Initialized data provider: {providerName} ({cacheStatus})")
                return
            except Exception as e:
                logger.info("Failed to initialize {providerName}: {str(e)}")
                continue
        
        raise RuntimeError(f"No data providers could be initialized from: {self.preferredProviders}")
    
    def getStockData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D'):
        """Get stock data using the active provider"""
        if not self.activeProvider:
            raise RuntimeError("No active data provider")
        
        # Try to format symbol for the active provider
        formattedSymbol = self.activeProvider.formatSymbol(symbol)
        return self.activeProvider.getStockData(formattedSymbol, startDate, endDate, freq)
    
    def getStockInfo(self, symbol: str):
        """Get stock info using the active provider"""
        if not self.activeProvider:
            raise RuntimeError("No active data provider")
        
        formattedSymbol = self.activeProvider.formatSymbol(symbol)
        return self.activeProvider.getStockInfo(formattedSymbol)
    
    def searchStock(self, keyword: str):
        """Search stocks using the active provider"""
        if not self.activeProvider:
            raise RuntimeError("No active data provider")
        
        return self.activeProvider.searchStock(keyword)
    
    def getIndexData(self, symbol: str, startDate: str, endDate: str, freq: str = 'D'):
        """Get index data using the active provider (if supported)"""
        if not self.activeProvider:
            raise RuntimeError("No active data provider")
        
        # Check if the active provider supports getIndexData
        if hasattr(self.activeProvider, 'getIndexData'):
            return self.activeProvider.getIndexData(symbol, startDate, endDate, freq)
        else:
            # Fallback to getStockData for providers that don't support index data
            logger.info("Provider does not support getIndexData, falling back to getStockData for {symbol}")
            formattedSymbol = self.activeProvider.formatSymbol(symbol)
            return self.activeProvider.getStockData(formattedSymbol, startDate, endDate, freq)
    
    def switchProvider(self, providerName: str):
        """Switch to a different provider"""
        try:
            providerConfig = self.config.get(providerName, {})
            newProvider = DataProviderFactory.create(providerName, providerConfig, self.enableCache)
            self.activeProvider = newProvider
            cacheStatus = "with cache" if self.enableCache else "without cache"
            logger.info("Switched to data provider: {providerName} ({cacheStatus})")
        except Exception as e:
            logger.info("Failed to switch to {providerName}: {str(e)}")
            raise
    
    def getActiveProviderInfo(self):
        """Get information about the active provider"""
        if not self.activeProvider:
            return None
        return self.activeProvider.getProviderInfo()

# Convenience function for quick provider creation
def createDataProvider(providerName: str = 'auto', config: Dict = None, enableCache: bool = True) -> BaseDataProvider:
    """
    Convenience function to create a data provider
    
    Args:
        providerName (str): Provider name or 'auto' for automatic selection
        config (Dict): Provider configuration
        enableCache (bool): Whether to enable caching
        
    Returns:
        BaseDataProvider: Data provider instance
    """
    if providerName.lower() == 'auto':
        return AutoDataProvider(config=config, enableCache=enableCache)
    else:
        return DataProviderFactory.create(providerName, config, enableCache) 