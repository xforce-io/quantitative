#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
News Collector
资讯收集器

Collect news data from various sources including Tushare Pro
从各种数据源收集资讯数据，包括Tushare Pro
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import logging

try:
    import tushare as ts
except ImportError:
    ts = None

from ..data_providers.cache_manager import getCacheManager

logger = logging.getLogger(__name__)

class NewsCollector:
    """资讯收集器 - 支持多种资讯源和缓存"""
    
    # 支持的新闻源
    SUPPORTED_SOURCES = {
        'sina': '新浪财经',
        'wallstreetcn': '华尔街见闻',
        '10jqka': '同花顺',
        'eastmoney': '东方财富',
        'yuncaijing': '云财经',
        'fenghuang': '凤凰新闻',
        'jinrongjie': '金融界'
    }
    
    def __init__(self, tusharePro=None, cacheEnabled: bool = True, cacheExpiryHours: int = 6):
        """
        初始化资讯收集器
        
        Args:
            tusharePro: Tushare Pro实例，如果为None会尝试初始化
            cacheEnabled: 是否启用缓存
            cacheExpiryHours: 缓存过期时间(小时)，新闻数据建议6小时
        """
        self.tusharePro = tusharePro
        self.cacheEnabled = cacheEnabled
        self.cacheExpiryHours = cacheExpiryHours
        self.cacheManager = getCacheManager() if cacheEnabled else None
        self.dataDir = os.path.join('data', 'news')
        
        # 确保数据目录存在
        if not os.path.exists(self.dataDir):
            os.makedirs(self.dataDir)
        
        # 初始化tushare pro
        if self.tusharePro is None and ts is not None:
            try:
                self.tusharePro = ts.pro_api()
                logger.info("Initialized Tushare Pro API")
            except Exception as e:
                logger.warning(f"Failed to initialize Tushare Pro API: {e}")
    
    def collectNews(self, 
                   source: str = 'sina',
                   startDate: Union[str, datetime] = None,
                   endDate: Union[str, datetime] = None,
                   forceRefresh: bool = False) -> pd.DataFrame:
        """
        收集新闻数据
        
        Args:
            source: 新闻源，支持的源见SUPPORTED_SOURCES
            startDate: 开始日期，支持字符串'2024-01-01 00:00:00'或datetime对象
            endDate: 结束日期，支持字符串'2024-01-01 23:59:59'或datetime对象
            forceRefresh: 强制刷新，忽略缓存
            
        Returns:
            包含新闻数据的DataFrame
        """
        if source not in self.SUPPORTED_SOURCES:
            raise ValueError(f"Unsupported news source: {source}. Supported sources: {list(self.SUPPORTED_SOURCES.keys())}")
        
        # 处理日期参数
        if startDate is None:
            startDate = datetime.now() - timedelta(days=1)
        elif isinstance(startDate, str):
            startDate = datetime.strptime(startDate, '%Y-%m-%d %H:%M:%S')
        
        if endDate is None:
            endDate = datetime.now()
        elif isinstance(endDate, str):
            endDate = datetime.strptime(endDate, '%Y-%m-%d %H:%M:%S')
        
        startDateStr = startDate.strftime('%Y-%m-%d %H:%M:%S')
        endDateStr = endDate.strftime('%Y-%m-%d %H:%M:%S')
        
        logger.info(f"Collecting news from {self.SUPPORTED_SOURCES[source]} ({source}) from {startDateStr} to {endDateStr}")
        
        # 尝试从缓存获取数据
        if self.cacheEnabled and not forceRefresh:
            cacheData = self._getCachedNews(source, startDateStr, endDateStr)
            if cacheData is not None:
                logger.info(f"Retrieved {len(cacheData)} news items from cache")
                return cacheData
        
        # 从API获取数据
        newsData = self._fetchNewsFromAPI(source, startDateStr, endDateStr)
        
        if newsData is not None and not newsData.empty:
            # 保存到缓存
            if self.cacheEnabled:
                self._cacheNews(source, startDateStr, endDateStr, newsData)
            
            # 保存到本地文件
            self._saveNewsToFile(source, startDateStr, endDateStr, newsData)
            
            logger.info(f"Successfully collected {len(newsData)} news items from {self.SUPPORTED_SOURCES[source]}")
            return newsData
        else:
            logger.warning(f"No news data collected from {self.SUPPORTED_SOURCES[source]}")
            return pd.DataFrame()
    
    def _fetchNewsFromAPI(self, source: str, startDate: str, endDate: str) -> Optional[pd.DataFrame]:
        """从API获取新闻数据"""
        if self.tusharePro is None:
            logger.error("Tushare Pro API not available")
            return None
        
        try:
            # 调用tushare pro新闻接口
            newsData = self.tusharePro.news(
                src=source,
                start_date=startDate,
                end_date=endDate
            )
            
            if newsData is not None and not newsData.empty:
                # 添加一些额外信息
                newsData['source'] = source
                newsData['source_name'] = self.SUPPORTED_SOURCES[source]
                newsData['collected_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 标准化时间格式
                if 'datetime' in newsData.columns:
                    newsData['news_time'] = newsData['datetime']
                    newsData['news_date'] = pd.to_datetime(newsData['datetime']).dt.date
                
                return newsData
            
        except Exception as e:
            logger.error(f"Error fetching news from {source}: {e}")
            return None
    
    def _getCachedNews(self, source: str, startDate: str, endDate: str) -> Optional[pd.DataFrame]:
        """从缓存获取新闻数据"""
        if self.cacheManager is None:
            return None
        
        try:
            return self.cacheManager.get(
                provider='tushare',
                apiType='news',
                symbol=source,  # 使用source作为symbol
                expiryHours=self.cacheExpiryHours,
                start_date=startDate,
                end_date=endDate
            )
        except Exception as e:
            logger.warning(f"Error getting cached news: {e}")
            return None
    
    def _cacheNews(self, source: str, startDate: str, endDate: str, data: pd.DataFrame):
        """缓存新闻数据"""
        if self.cacheManager is None:
            return
        
        try:
            self.cacheManager.set(
                provider='tushare',
                apiType='news',
                symbol=source,
                data=data,
                start_date=startDate,
                end_date=endDate
            )
        except Exception as e:
            logger.error(f"Error caching news: {e}")
    
    def _saveNewsToFile(self, source: str, startDate: str, endDate: str, data: pd.DataFrame):
        """保存新闻数据到本地文件"""
        try:
            # 创建文件名
            startDateFormatted = datetime.strptime(startDate, '%Y-%m-%d %H:%M:%S').strftime('%Y%m%d_%H%M')
            endDateFormatted = datetime.strptime(endDate, '%Y-%m-%d %H:%M:%S').strftime('%Y%m%d_%H%M')
            filename = f"news_{source}_{startDateFormatted}_to_{endDateFormatted}.csv"
            filepath = os.path.join(self.dataDir, filename)
            
            # 保存为CSV文件
            data.to_csv(filepath, index=False, encoding='utf-8')
            logger.info(f"Saved news data to {filepath}")
            
            # 同时保存为JSON文件（更好支持中文）
            jsonFilepath = filepath.replace('.csv', '.json')
            data.to_json(jsonFilepath, orient='records', force_ascii=False, indent=2)
            logger.info(f"Saved news data to {jsonFilepath}")
            
        except Exception as e:
            logger.error(f"Error saving news to file: {e}")
    
    def getBatchNews(self, 
                    sources: List[str] = None,
                    startDate: Union[str, datetime] = None,
                    endDate: Union[str, datetime] = None,
                    forceRefresh: bool = False) -> Dict[str, pd.DataFrame]:
        """
        批量收集多个源的新闻数据
        
        Args:
            sources: 新闻源列表，如果为None则使用所有支持的源
            startDate: 开始日期
            endDate: 结束日期
            forceRefresh: 强制刷新
            
        Returns:
            包含各个源新闻数据的字典
        """
        if sources is None:
            sources = list(self.SUPPORTED_SOURCES.keys())
        
        newsData = {}
        for source in sources:
            try:
                data = self.collectNews(source, startDate, endDate, forceRefresh)
                if not data.empty:
                    newsData[source] = data
            except Exception as e:
                logger.error(f"Error collecting news from {source}: {e}")
                
        return newsData
    
    def searchNews(self, 
                  keywords: List[str],
                  sources: List[str] = None,
                  startDate: Union[str, datetime] = None,
                  endDate: Union[str, datetime] = None) -> pd.DataFrame:
        """
        搜索包含特定关键词的新闻
        
        Args:
            keywords: 关键词列表
            sources: 搜索的新闻源列表
            startDate: 开始日期
            endDate: 结束日期
            
        Returns:
            包含关键词的新闻数据
        """
        # 收集新闻数据
        newsData = self.getBatchNews(sources, startDate, endDate)
        
        # 合并所有源的数据
        allNews = pd.DataFrame()
        for source, data in newsData.items():
            allNews = pd.concat([allNews, data], ignore_index=True)
        
        if allNews.empty:
            return pd.DataFrame()
        
        # 搜索关键词
        keywordPattern = '|'.join(keywords)
        matchedNews = allNews[
            allNews['title'].str.contains(keywordPattern, case=False, na=False) |
            allNews['content'].str.contains(keywordPattern, case=False, na=False)
        ]
        
        return matchedNews
    
    def getNewsSummary(self, 
                      sources: List[str] = None,
                      startDate: Union[str, datetime] = None,
                      endDate: Union[str, datetime] = None) -> Dict:
        """
        获取新闻摘要统计信息
        
        Returns:
            包含新闻统计信息的字典
        """
        newsData = self.getBatchNews(sources, startDate, endDate)
        
        summary = {
            'total_sources': len(newsData),
            'total_news': sum(len(data) for data in newsData.values()),
            'sources_detail': {}
        }
        
        for source, data in newsData.items():
            summary['sources_detail'][source] = {
                'source_name': self.SUPPORTED_SOURCES[source],
                'news_count': len(data),
                'date_range': {
                    'earliest': data['datetime'].min() if not data.empty else None,
                    'latest': data['datetime'].max() if not data.empty else None
                }
            }
        
        return summary
    
    @classmethod
    def getSupportedSources(cls) -> Dict[str, str]:
        """获取支持的新闻源列表"""
        return cls.SUPPORTED_SOURCES.copy() 