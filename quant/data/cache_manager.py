#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Cache Manager

This module provides caching functionality for data providers.
Supports different providers and API types with configurable expiry.

Migrated from: quant/data_providers/cache_manager.py
"""

import os
import json
import pickle
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import pandas as pd

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


class CacheManager:
    """
    Cache Manager - supports caching for different providers and API types.
    
    Features:
        - Per-provider and per-API-type cache organization
        - Configurable TTL (time-to-live)
        - Metadata tracking for cache entries
        - Cache statistics and cleanup utilities
    
    Directory structure:
        cache_root/
        ├── tushare/
        │   ├── stock_data/
        │   ├── financial_data/
        │   └── company_info/
        └── yahoo/
            └── stock_data/
    """
    
    def __init__(self, cache_root_dir: str = 'cache'):
        """
        Initialize cache manager.
        
        Args:
            cache_root_dir: Root directory for cache files
        """
        self.cache_root_dir = cache_root_dir
        self._ensure_cache_directories()
    
    def _ensure_cache_directories(self):
        """Ensure cache root directory exists."""
        if not os.path.exists(self.cache_root_dir):
            os.makedirs(self.cache_root_dir)
    
    def _get_cache_key(
        self,
        provider: str,
        api_type: str,
        symbol: str,
        **kwargs
    ) -> str:
        """
        Generate cache key hash.
        
        Args:
            provider: Data provider name (e.g., 'tushare', 'yahoo')
            api_type: API type (e.g., 'stock_data', 'company_info')
            symbol: Stock symbol
            **kwargs: Additional parameters
        
        Returns:
            MD5 hash string as cache key
        """
        key_data = {
            'provider': provider,
            'api_type': api_type,
            'symbol': symbol,
            **kwargs
        }
        
        # Sort keys for consistency
        sorted_key_data = json.dumps(key_data, sort_keys=True)
        
        return hashlib.md5(sorted_key_data.encode()).hexdigest()
    
    def _get_cache_path(
        self,
        provider: str,
        api_type: str,
        cache_key: str
    ) -> str:
        """
        Get cache file path.
        
        Args:
            provider: Data provider name
            api_type: API type
            cache_key: Cache key hash
        
        Returns:
            Full path to cache file
        """
        provider_dir = os.path.join(self.cache_root_dir, provider)
        if not os.path.exists(provider_dir):
            os.makedirs(provider_dir)
        
        api_dir = os.path.join(provider_dir, api_type)
        if not os.path.exists(api_dir):
            os.makedirs(api_dir)
        
        return os.path.join(api_dir, f"{cache_key}.pkl")
    
    def _get_metadata_path(
        self,
        provider: str,
        api_type: str,
        cache_key: str
    ) -> str:
        """Get metadata file path."""
        cache_path = self._get_cache_path(provider, api_type, cache_key)
        return cache_path.replace('.pkl', '_metadata.json')
    
    def get(
        self,
        provider: str,
        api_type: str,
        symbol: str,
        expiry_hours: int = 240,
        **kwargs
    ) -> Optional[Any]:
        """
        Get data from cache.
        
        Args:
            provider: Data provider name
            api_type: API type
            symbol: Stock symbol
            expiry_hours: Cache expiry time in hours (default 10 days)
            **kwargs: Additional parameters for cache key
        
        Returns:
            Cached data if exists and not expired, None otherwise
        """
        try:
            cache_key = self._get_cache_key(provider, api_type, symbol, **kwargs)
            cache_path = self._get_cache_path(provider, api_type, cache_key)
            metadata_path = self._get_metadata_path(provider, api_type, cache_key)
            
            # Check if cache files exist
            if not os.path.exists(cache_path) or not os.path.exists(metadata_path):
                return None
            
            # Check expiry
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            created_time = datetime.fromisoformat(metadata['created_time'])
            if datetime.now() - created_time > timedelta(hours=expiry_hours):
                logger.debug(f"Cache expired for {provider}/{api_type}/{symbol}")
                return None
            
            # Read cached data
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            
            logger.debug(f"Cache hit for {provider}/{api_type}/{symbol}")
            return data
            
        except Exception as e:
            logger.warning(
                f"Error reading cache for {provider}/{api_type}/{symbol}: {e}"
            )
            return None
    
    def set(
        self,
        provider: str,
        api_type: str,
        symbol: str,
        data: Any,
        **kwargs
    ):
        """
        Set cache data.
        
        Args:
            provider: Data provider name
            api_type: API type
            symbol: Stock symbol
            data: Data to cache
            **kwargs: Additional parameters for cache key
        """
        try:
            cache_key = self._get_cache_key(provider, api_type, symbol, **kwargs)
            cache_path = self._get_cache_path(provider, api_type, cache_key)
            metadata_path = self._get_metadata_path(provider, api_type, cache_key)
            
            # Save data
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            
            # Save metadata
            metadata = {
                'provider': provider,
                'api_type': api_type,
                'symbol': symbol,
                'created_time': datetime.now().isoformat(),
                'parameters': kwargs
            }
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Cached data for {provider}/{api_type}/{symbol}")
            
        except Exception as e:
            logger.error(
                f"Error setting cache for {provider}/{api_type}/{symbol}: {e}"
            )
    
    def invalidate(
        self,
        provider: str,
        api_type: str,
        symbol: str,
        **kwargs
    ):
        """
        Invalidate (delete) specific cache entry.
        
        Args:
            provider: Data provider name
            api_type: API type
            symbol: Stock symbol
            **kwargs: Additional parameters for cache key
        """
        try:
            cache_key = self._get_cache_key(provider, api_type, symbol, **kwargs)
            cache_path = self._get_cache_path(provider, api_type, cache_key)
            metadata_path = self._get_metadata_path(provider, api_type, cache_key)
            
            if os.path.exists(cache_path):
                os.remove(cache_path)
            
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
            
            logger.debug(f"Invalidated cache for {provider}/{api_type}/{symbol}")
            
        except Exception as e:
            logger.error(
                f"Error invalidating cache for {provider}/{api_type}/{symbol}: {e}"
            )
    
    def clear_provider(self, provider: str):
        """
        Clear all cache for a specific provider.
        
        Args:
            provider: Data provider name
        """
        try:
            import shutil
            provider_dir = os.path.join(self.cache_root_dir, provider)
            if os.path.exists(provider_dir):
                shutil.rmtree(provider_dir)
                logger.info(f"Cleared all cache for provider: {provider}")
        except Exception as e:
            logger.error(f"Error clearing cache for provider {provider}: {e}")
    
    def clear_all(self):
        """Clear all cache."""
        try:
            import shutil
            if os.path.exists(self.cache_root_dir):
                shutil.rmtree(self.cache_root_dir)
                self._ensure_cache_directories()
                logger.info("Cleared all cache")
        except Exception as e:
            logger.error(f"Error clearing all cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache statistics including file counts and sizes
        """
        stats = {
            'providers': {},
            'total_files': 0,
            'total_size_mb': 0
        }
        
        try:
            if not os.path.exists(self.cache_root_dir):
                return stats
            
            for provider in os.listdir(self.cache_root_dir):
                provider_path = os.path.join(self.cache_root_dir, provider)
                if not os.path.isdir(provider_path):
                    continue
                
                provider_stats = {
                    'api_types': {},
                    'files': 0,
                    'size_mb': 0
                }
                
                for api_type in os.listdir(provider_path):
                    api_path = os.path.join(provider_path, api_type)
                    if not os.path.isdir(api_path):
                        continue
                    
                    files = [f for f in os.listdir(api_path) if f.endswith('.pkl')]
                    file_count = len(files)
                    
                    size = sum(
                        os.path.getsize(os.path.join(api_path, f))
                        for f in files
                    )
                    size_mb = size / 1024 / 1024
                    
                    provider_stats['api_types'][api_type] = {
                        'files': file_count,
                        'size_mb': round(size_mb, 2)
                    }
                    
                    provider_stats['files'] += file_count
                    provider_stats['size_mb'] += size_mb
                
                provider_stats['size_mb'] = round(provider_stats['size_mb'], 2)
                stats['providers'][provider] = provider_stats
                stats['total_files'] += provider_stats['files']
                stats['total_size_mb'] += provider_stats['size_mb']
            
            stats['total_size_mb'] = round(stats['total_size_mb'], 2)
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
        
        return stats


# Global cache manager instance
_global_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """
    Get global cache manager instance (singleton).
    
    Returns:
        CacheManager instance
    """
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = CacheManager()
    return _global_cache_manager


# Backward compatibility aliases
getCacheManager = get_cache_manager
