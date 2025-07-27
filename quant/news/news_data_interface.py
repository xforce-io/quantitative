#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
News Data Interface
新闻数据统一接口

Provides unified interface for news data from API and local files
为API和本地文件提供统一的新闻数据接口
"""

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any, Tuple
import logging
from pathlib import Path
import glob

logger = logging.getLogger(__name__)


class StandardNewsFormat:
    """标准新闻数据格式 - 统一数据结构"""
    
    @staticmethod
    def createStandardFormat() -> Dict[str, Any]:
        """创建标准新闻格式模板"""
        return {
            'id': '',                    # 新闻唯一标识
            'timestamp': '',             # 发布时间 (ISO format)
            'source': '',                # 新闻源标识 (sina, eastmoney, etc.)
            'source_name': '',           # 新闻源名称
            'title': '',                 # 标题
            'content': '',               # 正文内容
            'url': '',                   # 原文链接
            'author': '',                # 作者
            'category': '',              # 分类
            'keywords': [],              # 关键词列表
            'tags': [],                  # 标签列表
            'summary': '',               # 摘要
            'language': 'zh',            # 语言
            'sentiment': None,           # 情感分析结果
            'relevance_scores': {},      # 对各投资品的相关性评分
            'collected_time': '',        # 数据收集时间
            'data_source_type': '',      # 数据来源类型: 'api' or 'local_file'
            'raw_data': {}               # 原始数据备份
        }
    
    @staticmethod
    def validateFormat(newsData: Dict[str, Any]) -> bool:
        """验证新闻数据格式是否符合标准"""
        required_fields = ['id', 'timestamp', 'source', 'title', 'content']
        return all(field in newsData for field in required_fields)


class NewsDataInterface:
    """新闻数据统一接口"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化新闻数据接口
        
        Args:
            config: 配置字典，包含数据源和存储配置
        """
        self.config = config or {}
        self.outputDir = self._getOutputDir()
        self.standardFormat = StandardNewsFormat()
        
        # 确保输出目录存在
        os.makedirs(self.outputDir, exist_ok=True)
        
    def _getOutputDir(self) -> str:
        """获取统一的新闻数据输出目录"""
        return self.config.get('output_dir', 'data/news_unified')
    
    def loadFromAPI(self, apiData: pd.DataFrame, source: str) -> List[Dict[str, Any]]:
        """
        从API数据加载并转换为标准格式
        
        Args:
            apiData: 从API获取的DataFrame数据
            source: 数据源标识
            
        Returns:
            标准格式的新闻数据列表
        """
        logger.info(f"Loading {len(apiData)} articles from API source: {source}")
        
        standardNews = []
        
        for _, row in apiData.iterrows():
            newsItem = self._convertAPIToStandard(row, source)
            if self.standardFormat.validateFormat(newsItem):
                standardNews.append(newsItem)
            else:
                logger.warning(f"Invalid news format for article: {newsItem.get('title', 'Unknown')}")
        
        # 保存到统一存储
        self._saveStandardNews(standardNews, f"api_{source}")
        
        logger.info(f"Successfully converted {len(standardNews)} articles from API")
        return standardNews
    
    def loadFromLocalFiles(self, localPath: str, filePattern: str = "*.json") -> List[Dict[str, Any]]:
        """
        从本地文件加载并转换为标准格式
        
        Args:
            localPath: 本地文件路径
            filePattern: 文件匹配模式
            
        Returns:
            标准格式的新闻数据列表
        """
        logger.info(f"Loading news from local path: {localPath}")
        
        if not os.path.exists(localPath):
            logger.error(f"Local path does not exist: {localPath}")
            return []
        
        # 查找匹配的文件
        searchPattern = os.path.join(localPath, "**", filePattern)
        newsFiles = glob.glob(searchPattern, recursive=True)
        
        logger.info(f"Found {len(newsFiles)} news files")
        
        standardNews = []
        
        for filePath in newsFiles:
            try:
                fileNews = self._loadSingleFile(filePath)
                standardNews.extend(fileNews)
            except Exception as e:
                logger.error(f"Failed to load file {filePath}: {e}")
                continue
        
        # 保存到统一存储
        self._saveStandardNews(standardNews, "local_files")
        
        logger.info(f"Successfully loaded {len(standardNews)} articles from local files")
        return standardNews
    
    def _loadSingleFile(self, filePath: str) -> List[Dict[str, Any]]:
        """加载单个新闻文件"""
        fileExtension = Path(filePath).suffix.lower()
        
        if fileExtension == '.json':
            return self._loadJsonFile(filePath)
        elif fileExtension == '.csv':
            return self._loadCsvFile(filePath)
        else:
            logger.warning(f"Unsupported file format: {fileExtension}")
            return []
    
    def _loadJsonFile(self, filePath: str) -> List[Dict[str, Any]]:
        """加载JSON格式的新闻文件"""
        with open(filePath, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        # 处理不同的JSON结构
        if isinstance(data, list):
            # 新闻列表
            return [self._convertLocalToStandard(item, 'local_json') for item in data]
        elif isinstance(data, dict):
            if 'articles' in data:
                # 包含articles字段的结构
                return [self._convertLocalToStandard(item, 'local_json') for item in data['articles']]
            else:
                # 单个新闻对象
                return [self._convertLocalToStandard(data, 'local_json')]
        
        return []
    
    def _loadCsvFile(self, filePath: str) -> List[Dict[str, Any]]:
        """加载CSV格式的新闻文件"""
        df = pd.read_csv(filePath)
        return [self._convertLocalToStandard(row, 'local_csv') for _, row in df.iterrows()]
    
    def _convertAPIToStandard(self, apiRow: pd.Series, source: str) -> Dict[str, Any]:
        """将API数据转换为标准格式"""
        newsItem = self.standardFormat.createStandardFormat()
        
        # 获取基本字段
        title = apiRow.get('title', '')
        content = apiRow.get('content', '')
        timestamp = apiRow.get('datetime', '')
        
        # 基本字段映射 - 适配Tushare格式
        newsItem['id'] = self._generateId(title, content, timestamp)
        newsItem['timestamp'] = self._standardizeTimestamp(timestamp)
        newsItem['source'] = source
        newsItem['source_name'] = apiRow.get('source_name', source)
        newsItem['title'] = title
        newsItem['content'] = content
        newsItem['url'] = apiRow.get('url', '')
        newsItem['author'] = apiRow.get('author', '')
        newsItem['category'] = apiRow.get('category', '')
        newsItem['collected_time'] = datetime.now().isoformat()
        newsItem['data_source_type'] = 'api'
        newsItem['raw_data'] = apiRow.to_dict()
        
        return newsItem
    
    def _convertLocalToStandard(self, localItem: Union[Dict, pd.Series], source: str) -> Dict[str, Any]:
        """将本地文件数据转换为标准格式"""
        newsItem = self.standardFormat.createStandardFormat()
        
        # 转换为字典格式
        if isinstance(localItem, pd.Series):
            itemDict = localItem.to_dict()
        else:
            itemDict = localItem
        
        # 获取标题和内容用于ID生成
        title = itemDict.get('title') or itemDict.get('headline', '') or ''
        content = itemDict.get('content') or itemDict.get('text') or itemDict.get('body', '') or ''
        
        # 改进的时间戳获取 - 适配多种字段名
        timestamp_raw = (itemDict.get('datetime') or 
                        itemDict.get('timestamp') or 
                        itemDict.get('date') or 
                        itemDict.get('publish_time') or 
                        itemDict.get('news_time', ''))
        
        # 字段映射 - 支持多种可能的字段名
        newsItem['id'] = self._generateId(title, content, timestamp_raw)
        newsItem['timestamp'] = self._standardizeTimestamp(timestamp_raw)
        newsItem['source'] = itemDict.get('source') or source
        newsItem['source_name'] = itemDict.get('source_name') or itemDict.get('source_url', '')
        newsItem['title'] = title
        newsItem['content'] = content
        newsItem['url'] = itemDict.get('url') or itemDict.get('link', '')
        newsItem['author'] = itemDict.get('author') or itemDict.get('writer', '')
        newsItem['category'] = itemDict.get('category') or itemDict.get('section', '')
        newsItem['keywords'] = itemDict.get('keywords', [])
        newsItem['tags'] = itemDict.get('tags', [])
        newsItem['collected_time'] = datetime.now().isoformat()
        newsItem['data_source_type'] = 'local_file'
        newsItem['raw_data'] = itemDict
        
        return newsItem
    
    def _generateId(self, title: str, content: str, timestamp: str) -> str:
        """生成新闻唯一标识 - 改进版本"""
        import hashlib
        
        # 确保有内容用于生成ID
        if not title and not content:
            # 如果标题和内容都为空，使用时间戳和随机数
            import uuid
            content_for_id = f"empty_content_{timestamp}_{uuid.uuid4().hex[:8]}"
        else:
            # 使用标题+内容前100字符作为标识
            content_for_id = f"{title}_{content[:100]}_{timestamp}"
        
        return hashlib.md5(content_for_id.encode('utf-8')).hexdigest()[:16]
    
    def _standardizeTimestamp(self, timestamp: Union[str, datetime]) -> str:
        """标准化时间戳格式"""
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        
        if isinstance(timestamp, str):
            try:
                # 尝试解析常见的时间格式
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d']:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.isoformat()
                    except ValueError:
                        continue
                
                # 如果都失败了，尝试pandas的时间解析
                import pandas as pd
                dt = pd.to_datetime(timestamp)
                return dt.isoformat()
                
            except Exception as e:
                logger.warning(f"Failed to parse timestamp {timestamp}: {e}")
                return datetime.now().isoformat()
        
        return datetime.now().isoformat()
    
    def _saveStandardNews(self, newsData: List[Dict[str, Any]], sourceTag: str):
        """保存标准格式的新闻数据"""
        if not newsData:
            return
        
        # 按日期组织文件
        today = datetime.now().strftime('%Y%m%d')
        outputFile = os.path.join(self.outputDir, f"{sourceTag}_{today}.json")
        
        try:
            # 如果文件已存在，追加数据
            existingData = []
            if os.path.exists(outputFile):
                with open(outputFile, 'r', encoding='utf-8') as file:
                    existingData = json.load(file)
            
            # 去重：基于id字段
            existingIds = {item['id'] for item in existingData}
            newData = [item for item in newsData if item['id'] not in existingIds]
            
            # 合并数据
            allData = existingData + newData
            
            # 保存到文件
            with open(outputFile, 'w', encoding='utf-8') as file:
                json.dump(allData, file, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"Saved {len(newData)} new articles to {outputFile}")
            
        except Exception as e:
            logger.error(f"Failed to save news data: {e}")
    
    def loadUnifiedNews(self, 
                       dateRange: Optional[Tuple[str, str]] = None,
                       sources: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        从统一存储中加载新闻数据
        
        Args:
            dateRange: 日期范围 (start_date, end_date)
            sources: 指定的新闻源列表
            
        Returns:
            标准格式的新闻数据列表
        """
        allNews = []
        
        # 查找所有新闻文件
        newsFiles = glob.glob(os.path.join(self.outputDir, "*.json"))
        
        for filePath in newsFiles:
            try:
                with open(filePath, 'r', encoding='utf-8') as file:
                    fileNews = json.load(file)
                
                # 应用过滤条件
                filteredNews = self._applyFilters(fileNews, dateRange, sources)
                allNews.extend(filteredNews)
                
            except Exception as e:
                logger.error(f"Failed to load file {filePath}: {e}")
                continue
        
        logger.info(f"Loaded {len(allNews)} articles from unified storage")
        return allNews
    
    def _applyFilters(self, 
                     newsData: List[Dict[str, Any]], 
                     dateRange: Optional[Tuple[str, str]], 
                     sources: Optional[List[str]]) -> List[Dict[str, Any]]:
        """应用过滤条件"""
        filtered = newsData
        
        # 日期过滤
        if dateRange:
            startDate, endDate = dateRange
            filtered = [
                item for item in filtered
                if startDate <= item.get('timestamp', '') <= endDate
            ]
        
        # 新闻源过滤
        if sources:
            filtered = [
                item for item in filtered
                if item.get('source', '') in sources
            ]
        
        return filtered
    
    def getDataSummary(self) -> Dict[str, Any]:
        """获取数据汇总信息"""
        newsFiles = glob.glob(os.path.join(self.outputDir, "*.json"))
        
        summary = {
            'total_files': len(newsFiles),
            'total_articles': 0,
            'sources': set(),
            'date_range': {'earliest': None, 'latest': None},
            'data_source_types': {'api': 0, 'local_file': 0}
        }
        
        for filePath in newsFiles:
            try:
                with open(filePath, 'r', encoding='utf-8') as file:
                    fileNews = json.load(file)
                
                summary['total_articles'] += len(fileNews)
                
                for item in fileNews:
                    summary['sources'].add(item.get('source', 'unknown'))
                    
                    timestamp = item.get('timestamp', '')
                    if timestamp:
                        if summary['date_range']['earliest'] is None or timestamp < summary['date_range']['earliest']:
                            summary['date_range']['earliest'] = timestamp
                        if summary['date_range']['latest'] is None or timestamp > summary['date_range']['latest']:
                            summary['date_range']['latest'] = timestamp
                    
                    dataSourceType = item.get('data_source_type', 'unknown')
                    if dataSourceType in summary['data_source_types']:
                        summary['data_source_types'][dataSourceType] += 1
                        
            except Exception as e:
                logger.error(f"Failed to analyze file {filePath}: {e}")
                continue
        
        summary['sources'] = list(summary['sources'])
        return summary 