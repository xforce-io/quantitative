import os
import json
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """缓存管理器 - 支持不同provider和API类型的缓存"""
    
    def __init__(self, cacheRootDir: str = 'cache'):
        """
        初始化缓存管理器
        
        Args:
            cacheRootDir: 缓存根目录
        """
        self.cacheRootDir = cacheRootDir
        self._ensureCacheDirectories()
    
    def _ensureCacheDirectories(self):
        """确保缓存目录存在"""
        if not os.path.exists(self.cacheRootDir):
            os.makedirs(self.cacheRootDir)
    
    def _getCacheKey(self, provider: str, apiType: str, symbol: str, **kwargs) -> str:
        """
        生成缓存key
        
        Args:
            provider: 数据提供商 (如 'tushare', 'yahoo')
            apiType: API类型 (如 'stock_data', 'company_info', 'financial_data')
            symbol: 股票代码
            **kwargs: 其他参数
        
        Returns:
            缓存key的哈希值
        """
        # 创建唯一标识字符串
        keyData = {
            'provider': provider,
            'api_type': apiType,
            'symbol': symbol,
            **kwargs
        }
        
        # 按key排序，确保一致性
        sortedKeyData = json.dumps(keyData, sort_keys=True)
        
        # 生成MD5哈希
        return hashlib.md5(sortedKeyData.encode()).hexdigest()
    
    def _getCachePath(self, provider: str, apiType: str, cacheKey: str) -> str:
        """
        获取缓存文件路径
        
        Args:
            provider: 数据提供商
            apiType: API类型
            cacheKey: 缓存key
        
        Returns:
            缓存文件完整路径
        """
        providerDir = os.path.join(self.cacheRootDir, provider)
        if not os.path.exists(providerDir):
            os.makedirs(providerDir)
        
        apiDir = os.path.join(providerDir, apiType)
        if not os.path.exists(apiDir):
            os.makedirs(apiDir)
        
        return os.path.join(apiDir, f"{cacheKey}.pkl")
    
    def _getMetadataPath(self, provider: str, apiType: str, cacheKey: str) -> str:
        """获取元数据文件路径"""
        cachePath = self._getCachePath(provider, apiType, cacheKey)
        return cachePath.replace('.pkl', '_metadata.json')
    
    def get(self, provider: str, apiType: str, symbol: str, expiryHours: int = 240, **kwargs) -> Optional[Any]:
        """
        从缓存获取数据
        
        Args:
            provider: 数据提供商
            apiType: API类型
            symbol: 股票代码
            expiryHours: 缓存过期时间(小时)
            **kwargs: 其他参数
        
        Returns:
            缓存的数据，如果不存在或过期则返回None
        """
        try:
            cacheKey = self._getCacheKey(provider, apiType, symbol, **kwargs)
            cachePath = self._getCachePath(provider, apiType, cacheKey)
            metadataPath = self._getMetadataPath(provider, apiType, cacheKey)
            
            # 检查缓存文件是否存在
            if not os.path.exists(cachePath) or not os.path.exists(metadataPath):
                return None
            
            # 检查是否过期
            with open(metadataPath, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            createdTime = datetime.fromisoformat(metadata['created_time'])
            if datetime.now() - createdTime > timedelta(hours=expiryHours):
                logger.info(f"Cache expired for {provider}/{apiType}/{symbol}")
                return None
            
            # 读取缓存数据
            with open(cachePath, 'rb') as f:
                data = pickle.load(f)
            
            logger.info(f"Cache hit for {provider}/{apiType}/{symbol}")
            return data
            
        except Exception as e:
            logger.warning(f"Error reading cache for {provider}/{apiType}/{symbol}: {e}")
            return None
    
    def set(self, provider: str, apiType: str, symbol: str, data: Any, **kwargs):
        """
        设置缓存数据
        
        Args:
            provider: 数据提供商
            apiType: API类型
            symbol: 股票代码
            data: 要缓存的数据
            **kwargs: 其他参数
        """
        try:
            cacheKey = self._getCacheKey(provider, apiType, symbol, **kwargs)
            cachePath = self._getCachePath(provider, apiType, cacheKey)
            metadataPath = self._getMetadataPath(provider, apiType, cacheKey)
            
            # 保存数据
            with open(cachePath, 'wb') as f:
                pickle.dump(data, f)
            
            # 保存元数据
            metadata = {
                'provider': provider,
                'api_type': apiType,
                'symbol': symbol,
                'created_time': datetime.now().isoformat(),
                'parameters': kwargs
            }
            
            with open(metadataPath, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Cached data for {provider}/{apiType}/{symbol}")
            
        except Exception as e:
            logger.error(f"Error setting cache for {provider}/{apiType}/{symbol}: {e}")
    
    def invalidate(self, provider: str, apiType: str, symbol: str, **kwargs):
        """
        删除特定缓存
        
        Args:
            provider: 数据提供商
            apiType: API类型
            symbol: 股票代码
            **kwargs: 其他参数
        """
        try:
            cacheKey = self._getCacheKey(provider, apiType, symbol, **kwargs)
            cachePath = self._getCachePath(provider, apiType, cacheKey)
            metadataPath = self._getMetadataPath(provider, apiType, cacheKey)
            
            if os.path.exists(cachePath):
                os.remove(cachePath)
            
            if os.path.exists(metadataPath):
                os.remove(metadataPath)
            
            logger.info(f"Invalidated cache for {provider}/{apiType}/{symbol}")
            
        except Exception as e:
            logger.error(f"Error invalidating cache for {provider}/{apiType}/{symbol}: {e}")
    
    def clearProvider(self, provider: str):
        """清理特定provider的所有缓存"""
        try:
            providerDir = os.path.join(self.cacheRootDir, provider)
            if os.path.exists(providerDir):
                import shutil
                shutil.rmtree(providerDir)
                logger.info(f"Cleared all cache for provider: {provider}")
        except Exception as e:
            logger.error(f"Error clearing cache for provider {provider}: {e}")
    
    def clearAll(self):
        """清理所有缓存"""
        try:
            if os.path.exists(self.cacheRootDir):
                import shutil
                shutil.rmtree(self.cacheRootDir)
                self._ensureCacheDirectories()
                logger.info("Cleared all cache")
        except Exception as e:
            logger.error(f"Error clearing all cache: {e}")
    
    def getCacheStats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            'providers': {},
            'total_files': 0,
            'total_size_mb': 0
        }
        
        try:
            if not os.path.exists(self.cacheRootDir):
                return stats
            
            for provider in os.listdir(self.cacheRootDir):
                providerPath = os.path.join(self.cacheRootDir, provider)
                if not os.path.isdir(providerPath):
                    continue
                
                providerStats = {
                    'api_types': {},
                    'files': 0,
                    'size_mb': 0
                }
                
                for apiType in os.listdir(providerPath):
                    apiPath = os.path.join(providerPath, apiType)
                    if not os.path.isdir(apiPath):
                        continue
                    
                    files = [f for f in os.listdir(apiPath) if f.endswith('.pkl')]
                    fileCount = len(files)
                    
                    size = sum(os.path.getsize(os.path.join(apiPath, f)) for f in files)
                    sizeMb = size / 1024 / 1024
                    
                    providerStats['api_types'][apiType] = {
                        'files': fileCount,
                        'size_mb': round(sizeMb, 2)
                    }
                    
                    providerStats['files'] += fileCount
                    providerStats['size_mb'] += sizeMb
                
                providerStats['size_mb'] = round(providerStats['size_mb'], 2)
                stats['providers'][provider] = providerStats
                stats['total_files'] += providerStats['files']
                stats['total_size_mb'] += providerStats['size_mb']
            
            stats['total_size_mb'] = round(stats['total_size_mb'], 2)
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
        
        return stats

# 全局缓存管理器实例
_globalCacheManager = None

def getCacheManager() -> CacheManager:
    """获取全局缓存管理器实例"""
    global _globalCacheManager
    if _globalCacheManager is None:
        _globalCacheManager = CacheManager()
    return _globalCacheManager 