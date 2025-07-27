"""统一数据管理器 / Unified Data Manager

这个模块提供统一的数据管理功能，支持：
- 多数据源统一接口
- 数据缓存管理
- 数据格式标准化
- 数据验证和清洗
"""

import os
import json
import logging
import pandas as pd
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from datetime import datetime, timedelta
import hashlib

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


class DataManager:
    """统一数据管理器"""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize data manager
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.system_config = config_manager.get_system_config()
        self.data_sources_config = config_manager.get_data_sources_config()
        
        # Setup directories
        self.data_dir = Path(self.system_config.get("environment", {}).get("data_dir", "data"))
        self.cache_dir = Path(self.system_config.get("environment", {}).get("cache_dir", "cache"))
        self.reports_dir = Path(self.system_config.get("environment", {}).get("reports_dir", "reports"))
        
        # Create directories if they don't exist
        for directory in [self.data_dir, self.cache_dir, self.reports_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_news_data(self, 
                     sources: Optional[List[str]] = None,
                     days_back: int = 7,
                     use_cache: bool = True) -> List[Dict[str, Any]]:
        """Get news data from various sources
        
        Args:
            sources: List of news sources to use
            days_back: Number of days to look back
            use_cache: Whether to use cached data
            
        Returns:
            List of news articles
        """
        news_data = []
        
        # Get news from file-based sources
        file_news = self._get_news_from_files(days_back)
        news_data.extend(file_news)
        
        # Get news from API sources (if configured)
        if sources:
            api_news = self._get_news_from_api(sources, days_back, use_cache)
            news_data.extend(api_news)
        
        # Standardize and deduplicate
        news_data = self._standardize_news_data(news_data)
        news_data = self._deduplicate_news(news_data)
        
        logger.info(f"Retrieved {len(news_data)} news articles")
        return news_data
    
    def save_news_data(self, 
                      news_data: List[Dict[str, Any]], 
                      filename: Optional[str] = None) -> str:
        """Save news data to file
        
        Args:
            news_data: News data to save
            filename: Optional filename, auto-generated if None
            
        Returns:
            Path of saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"news_data_{timestamp}.json"
        
        file_path = self.data_dir / "news" / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(news_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(news_data)} news articles to {file_path}")
        return str(file_path)
    
    def get_cache_key(self, data_type: str, **kwargs) -> str:
        """Generate cache key for data
        
        Args:
            data_type: Type of data being cached
            **kwargs: Additional parameters for cache key
            
        Returns:
            Cache key string
        """
        # Create a deterministic cache key
        key_data = {"type": data_type, **kwargs}
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def get_cached_data(self, cache_key: str) -> Optional[Any]:
        """Get data from cache
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached data or None if not found/expired
        """
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            cache_time = datetime.fromisoformat(cache_data.get("timestamp", ""))
            cache_config = self.data_sources_config.get("cache", {})
            ttl_hours = cache_config.get("strategies", {}).get("news_data", {}).get("ttl_hours", 24)
            
            if datetime.now() - cache_time > timedelta(hours=ttl_hours):
                cache_file.unlink()  # Remove expired cache
                return None
            
            return cache_data.get("data")
            
        except Exception as e:
            logger.warning(f"Failed to read cache {cache_key}: {e}")
            return None
    
    def save_to_cache(self, cache_key: str, data: Any) -> None:
        """Save data to cache
        
        Args:
            cache_key: Cache key
            data: Data to cache
        """
        cache_file = self.cache_dir / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        cache_data = {
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"Saved data to cache: {cache_key}")
            
        except Exception as e:
            logger.warning(f"Failed to save cache {cache_key}: {e}")
    
    def _get_news_from_files(self, days_back: int) -> List[Dict[str, Any]]:
        """Get news data from local files
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            List of news articles
        """
        news_data = []
        news_dir = self.data_dir / "news"
        
        if not news_dir.exists():
            logger.warning(f"News directory not found: {news_dir}")
            return news_data
        
        # Get files from the last N days
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        for file_path in news_dir.rglob("*.json"):
            try:
                # Check file modification time
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    continue
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    news_data.extend(data)
                elif isinstance(data, dict):
                    news_data.append(data)
                    
            except Exception as e:
                logger.warning(f"Failed to read news file {file_path}: {e}")
        
        logger.info(f"Loaded {len(news_data)} articles from local files")
        return news_data
    
    def _get_news_from_api(self, 
                          sources: List[str], 
                          days_back: int, 
                          use_cache: bool) -> List[Dict[str, Any]]:
        """Get news data from API sources
        
        Args:
            sources: List of API sources
            days_back: Number of days to look back
            use_cache: Whether to use cached data
            
        Returns:
            List of news articles
        """
        # This would implement API calls to various news sources
        # For now, return empty list as APIs are not implemented
        logger.info("API news fetching not implemented yet")
        return []
    
    def _standardize_news_data(self, news_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Standardize news data format
        
        Args:
            news_data: Raw news data
            
        Returns:
            Standardized news data
        """
        standardized = []
        
        for article in news_data:
            try:
                # Convert to standard format
                standard_article = {
                    "title": article.get("title", ""),
                    "content": article.get("content", ""),
                    "url": article.get("url", ""),
                    "source": article.get("source", "unknown"),
                    "timestamp": self._standardize_timestamp(article.get("timestamp", "")),
                    "keywords": article.get("keywords", []),
                    "category": article.get("category", ""),
                    "sentiment_score": article.get("sentiment_score"),
                    "relevance_scores": article.get("relevance_scores", {}),
                    "summary": article.get("summary", "")
                }
                
                # Validate required fields
                if standard_article["title"] and standard_article["content"]:
                    standardized.append(standard_article)
                    
            except Exception as e:
                logger.warning(f"Failed to standardize article: {e}")
        
        return standardized
    
    def _standardize_timestamp(self, timestamp: Union[str, datetime]) -> str:
        """Standardize timestamp format
        
        Args:
            timestamp: Input timestamp
            
        Returns:
            Standardized timestamp string
        """
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        
        if isinstance(timestamp, str):
            try:
                # Try to parse common formats
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S"]:
                    try:
                        dt = datetime.strptime(timestamp, fmt)
                        return dt.isoformat()
                    except ValueError:
                        continue
                
                # If parsing fails, return as is
                return timestamp
                
            except Exception:
                return timestamp
        
        # Default to current time
        return datetime.now().isoformat()
    
    def _deduplicate_news(self, news_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate news articles
        
        Args:
            news_data: News data to deduplicate
            
        Returns:
            Deduplicated news data
        """
        news_config = self.config_manager.get_news_analysis_config()
        dedup_config = news_config.get("data_processing", {}).get("deduplication", {}) if news_config else {}
        
        if not dedup_config.get("enabled", True):
            return news_data
        
        seen_titles = set()
        unique_news = []
        
        for article in news_data:
            title = article.get("title", "").strip().lower()
            
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(article)
        
        removed_count = len(news_data) - len(unique_news)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} duplicate articles")
        
        return unique_news
    
    def save_report(self, 
                   report_data: Dict[str, Any], 
                   report_type: str,
                   target: str = "general",
                   format_type: str = "json") -> str:
        """Save analysis report
        
        Args:
            report_data: Report data to save
            report_type: Type of report
            target: Target asset/investment
            format_type: Output format (json, markdown, html)
            
        Returns:
            Path of saved report
        """
        # Create report directory structure
        date_str = datetime.now().strftime("%Y%m%d")
        report_dir = self.reports_dir / date_str / report_type
        report_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"{target}_{timestamp}.{format_type}"
        file_path = report_dir / filename
        
        # Save report based on format
        if format_type == "json":
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)
        elif format_type == "markdown":
            self._save_markdown_report(file_path, report_data)
        elif format_type == "html":
            self._save_html_report(file_path, report_data)
        
        logger.info(f"Saved {report_type} report to {file_path}")
        return str(file_path)
    
    def _save_markdown_report(self, file_path: Path, report_data: Dict[str, Any]):
        """Save report in markdown format"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(f"# {report_data.get('title', 'Analysis Report')}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for section, content in report_data.items():
                if section != 'title':
                    f.write(f"## {section.replace('_', ' ').title()}\n\n")
                    if isinstance(content, str):
                        f.write(f"{content}\n\n")
                    elif isinstance(content, (list, dict)):
                        f.write(f"```json\n{json.dumps(content, ensure_ascii=False, indent=2)}\n```\n\n")
    
    def _save_html_report(self, file_path: Path, report_data: Dict[str, Any]):
        """Save report in HTML format"""
        # Simple HTML template - can be enhanced
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{report_data.get('title', 'Analysis Report')}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ border-bottom: 2px solid #ccc; padding-bottom: 10px; }}
                .section {{ margin: 20px 0; }}
                pre {{ background: #f5f5f5; padding: 10px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{report_data.get('title', 'Analysis Report')}</h1>
                <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
        """
        
        for section, content in report_data.items():
            if section != 'title':
                html_content += f'<div class="section"><h2>{section.replace("_", " ").title()}</h2>'
                if isinstance(content, str):
                    html_content += f'<p>{content}</p>'
                elif isinstance(content, (list, dict)):
                    html_content += f'<pre>{json.dumps(content, ensure_ascii=False, indent=2)}</pre>'
                html_content += '</div>'
        
        html_content += "</body></html>"
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content) 