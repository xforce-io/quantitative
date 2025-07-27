#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified News Collector
统一新闻收集器

Collects news from multiple sources: API and local files
从多种来源收集新闻：API和本地文件
"""

import os
import yaml
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
import logging

from .news_collector import NewsCollector
from .news_data_interface import NewsDataInterface, StandardNewsFormat

logger = logging.getLogger(__name__)


class UnifiedNewsCollector:
    """统一新闻收集器 - 整合API和本地文件数据源"""
    
    def __init__(self, configPath: str = "config/news_analysis_config.yaml"):
        """
        初始化统一新闻收集器
        
        Args:
            configPath: 配置文件路径
        """
        self.config = self._loadConfig(configPath)
        self.dataInterface = NewsDataInterface(self.config.get('data_processing', {}))
        
        # 初始化API收集器
        self.apiCollector = None
        if self.config.get('data_sources', {}).get('tushare_api', {}).get('enabled', False):
            self.apiCollector = NewsCollector(cacheEnabled=True)
        
        # 本地文件配置
        self.externalPath = self.config.get('data_sources', {}).get('external_crawler', {}).get('path', '')
        self.scanDays = self.config.get('data_sources', {}).get('external_crawler', {}).get('scan_days', 7)
        
    def _loadConfig(self, configPath: str) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(configPath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {configPath}")
            return {}
    
    def collectAllNews(self, 
                      startDate: Optional[str] = None,
                      endDate: Optional[str] = None,
                      forceRefresh: bool = False) -> List[Dict[str, Any]]:
        """
        从所有配置的数据源收集新闻
        
        Args:
            startDate: 开始日期 (YYYY-MM-DD format)
            endDate: 结束日期 (YYYY-MM-DD format)
            forceRefresh: 强制刷新，忽略缓存
            
        Returns:
            统一格式的新闻数据列表
        """
        logger.info("Starting unified news collection")
        
        allNews = []
        
        # 设置默认日期范围
        if not startDate:
            startDate = (datetime.now() - timedelta(days=self.scanDays)).strftime('%Y-%m-%d')
        if not endDate:
            endDate = datetime.now().strftime('%Y-%m-%d')
        
        # 1. 从API收集新闻
        apiNews = self._collectFromAPI(startDate, endDate, forceRefresh)
        if apiNews:
            allNews.extend(apiNews)
            logger.info(f"Collected {len(apiNews)} articles from API sources")
        
        # 2. 从本地文件收集新闻
        localNews = self._collectFromLocalFiles()
        if localNews:
            allNews.extend(localNews)
            logger.info(f"Collected {len(localNews)} articles from local files")
        
        # 3. 去重和排序
        uniqueNews = self._deduplicateNews(allNews)
        sortedNews = self._sortNewsByTime(uniqueNews)
        
        logger.info(f"Total collected: {len(sortedNews)} unique articles")
        return sortedNews
    
    def _collectFromAPI(self, 
                       startDate: str, 
                       endDate: str, 
                       forceRefresh: bool) -> List[Dict[str, Any]]:
        """从API收集新闻"""
        if not self.apiCollector:
            logger.info("API collector not enabled")
            return []
        
        apiConfig = self.config.get('data_sources', {}).get('tushare_api', {})
        if not apiConfig.get('enabled', False):
            logger.info("Tushare API disabled, checking fallback")
            if not apiConfig.get('fallback_to_external', False):
                return []
        
        apiNews = []
        
        # 支持的新闻源
        supportedSources = ['sina', 'eastmoney', 'wallstreetcn']
        
        for source in supportedSources:
            try:
                logger.info(f"Collecting from API source: {source}")
                
                # 调用API收集器
                sourceData = self.apiCollector.collectNews(
                    source=source,
                    startDate=f"{startDate} 00:00:00",
                    endDate=f"{endDate} 23:59:59",
                    forceRefresh=forceRefresh
                )
                
                if sourceData is not None and not sourceData.empty:
                    # 转换为标准格式
                    standardNews = self.dataInterface.loadFromAPI(sourceData, source)
                    apiNews.extend(standardNews)
                    logger.info(f"Collected {len(standardNews)} articles from {source}")
                else:
                    logger.warning(f"No data collected from {source}")
                    
            except Exception as e:
                logger.error(f"Failed to collect from API source {source}: {e}")
                continue
        
        return apiNews
    
    def _collectFromLocalFiles(self) -> List[Dict[str, Any]]:
        """从本地文件收集新闻"""
        externalConfig = self.config.get('data_sources', {}).get('external_crawler', {})
        if not externalConfig.get('enabled', False):
            logger.info("External crawler data source not enabled")
            return []
        
        if not self.externalPath or not os.path.exists(self.externalPath):
            logger.warning(f"External path not found: {self.externalPath}")
            return []
        
        logger.info(f"Collecting from local files: {self.externalPath}")
        
        try:
            # 使用数据接口加载本地文件
            localNews = self.dataInterface.loadFromLocalFiles(
                localPath=self.externalPath,
                filePattern="*.json"  # 可以根据需要调整
            )
            
            # 过滤最近几天的新闻
            recentNews = self._filterRecentNews(localNews, self.scanDays)
            
            logger.info(f"Collected {len(recentNews)} recent articles from local files")
            return recentNews
            
        except Exception as e:
            logger.error(f"Failed to collect from local files: {e}")
            return []
    
    def _filterRecentNews(self, newsData: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
        """过滤最近几天的新闻"""
        cutoffDate = datetime.now() - timedelta(days=days)
        cutoffIso = cutoffDate.isoformat()
        
        recentNews = []
        
        for item in newsData:
            timestamp = item.get('timestamp', '')
            if timestamp and timestamp >= cutoffIso:
                recentNews.append(item)
        
        return recentNews
    
    def _deduplicateNews(self, newsData: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去除重复新闻"""
        seen = set()
        uniqueNews = []
        
        for item in newsData:
            newsId = item.get('id', '')
            title = item.get('title', '')
            
            # 使用id或title作为去重标识
            identifier = newsId if newsId else title
            
            if identifier and identifier not in seen:
                seen.add(identifier)
                uniqueNews.append(item)
        
        logger.info(f"Deduplicated: {len(newsData)} -> {len(uniqueNews)} articles")
        return uniqueNews
    
    def _sortNewsByTime(self, newsData: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按时间排序新闻（最新的在前）"""
        try:
            sortedNews = sorted(
                newsData,
                key=lambda x: x.get('timestamp', ''),
                reverse=True
            )
            return sortedNews
        except Exception as e:
            logger.warning(f"Failed to sort news by time: {e}")
            return newsData
    
    def collectByKeywords(self, 
                         keywords: List[str],
                         startDate: Optional[str] = None,
                         endDate: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        根据关键词收集相关新闻
        
        Args:
            keywords: 关键词列表
            startDate: 开始日期
            endDate: 结束日期
            
        Returns:
            与关键词相关的新闻列表
        """
        allNews = self.collectAllNews(startDate, endDate)
        
        relevantNews = []
        
        for item in allNews:
            title = item.get('title', '') or ''
            content = item.get('content', '') or ''
            title_lower = title.lower()
            content_lower = content.lower()
            
            # 检查标题和内容是否包含关键词
            for keyword in keywords:
                if keyword.lower() in title_lower or keyword.lower() in content_lower:
                    relevantNews.append(item)
                    break
        
        logger.info(f"Found {len(relevantNews)} articles matching keywords: {keywords}")
        return relevantNews
    
    def collectForInvestmentTargets(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        根据投资品配置收集相关新闻
        
        Returns:
            按投资品分组的新闻字典
        """
        investmentTargets = self.config.get('investment_targets', [])
        
        if not investmentTargets:
            logger.warning("No investment targets configured")
            return {}
        
        targetNews = {}
        
        for target in investmentTargets:
            targetName = target.get('name', '')
            keywords = target.get('keywords', [])
            
            if not keywords:
                logger.warning(f"No keywords configured for target: {targetName}")
                continue
            
            logger.info(f"Collecting news for target: {targetName}")
            
            # 收集相关新闻
            relevantNews = self.collectByKeywords(keywords)
            
            # 添加相关性评分
            for item in relevantNews:
                if 'relevance_scores' not in item:
                    item['relevance_scores'] = {}
                item['relevance_scores'][target.get('symbol', targetName)] = self._calculateRelevance(
                    item, keywords
                )
            
            targetNews[targetName] = relevantNews
            logger.info(f"Collected {len(relevantNews)} articles for {targetName}")
        
        return targetNews
    
    def _calculateRelevance(self, newsItem: Dict[str, Any], keywords: List[str]) -> float:
        """
        计算新闻与关键词的相关性评分
        
        Args:
            newsItem: 新闻项
            keywords: 关键词列表
            
        Returns:
            相关性评分 (0-1)
        """
        title = (newsItem.get('title', '') or '').lower()
        content = (newsItem.get('content', '') or '').lower()
        
        totalMatches = 0
        titleMatches = 0
        
        for keyword in keywords:
            keywordLower = keyword.lower()
            
            # 标题匹配权重更高
            if keywordLower in title:
                titleMatches += 1
                totalMatches += 2  # 标题匹配权重为2
            
            # 内容匹配
            if keywordLower in content:
                totalMatches += 1
        
        # 标准化评分
        maxPossibleScore = len(keywords) * 3  # 每个关键词最高可得3分（标题2分+内容1分）
        relevanceScore = min(totalMatches / maxPossibleScore, 1.0) if maxPossibleScore > 0 else 0.0
        
        return relevanceScore
    
    def getCollectionSummary(self) -> Dict[str, Any]:
        """获取收集汇总信息"""
        summary = {
            'config': {
                'api_enabled': self.config.get('data_sources', {}).get('tushare_api', {}).get('enabled', False),
                'local_enabled': self.config.get('data_sources', {}).get('external_crawler', {}).get('enabled', False),
                'external_path': self.externalPath,
                'scan_days': self.scanDays
            },
            'data_summary': self.dataInterface.getDataSummary()
        }
        
        return summary 