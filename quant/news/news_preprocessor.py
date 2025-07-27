"""
News Preprocessor Module
新闻预处理模块 - 处理外部爬虫获取的原始新闻数据
"""

import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path
import yaml

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NewsPreprocessor:
    """External news data preprocessor"""
    
    def __init__(self, config_path: str = "config/news_analysis_config.yaml"):
        """Initialize preprocessor with configuration"""
        self.config = self._loadConfig(config_path)
        self.dataSourcePath = self.config['data_sources']['external_crawler']['path']
        self.scanDays = self.config['data_sources']['external_crawler']['scan_days']
        self.outputDir = self.config['data_processing']['structured_storage']['output_dir']
        self.qualityFilters = self.config['news_sources']['quality_filters']
        
        # Ensure output directory exists
        os.makedirs(self.outputDir, exist_ok=True)
        
    def _loadConfig(self, configPath: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(configPath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {configPath}")
            raise
            
    def scanRecentNews(self) -> List[Dict[str, Any]]:
        """Scan and process recent news from external crawler data"""
        newsArticles = []
        
        # Calculate date range to scan
        endDate = datetime.now()
        startDate = endDate - timedelta(days=self.scanDays)
        
        logger.info(f"Scanning news from {startDate.date()} to {endDate.date()}")
        
        # Scan date directories
        for dateDir in self._getDateDirectories(startDate, endDate):
            datePath = os.path.join(self.dataSourcePath, dateDir)
            if os.path.exists(datePath):
                logger.info(f"Processing news for date: {dateDir}")
                dailyNews = self._processDateDirectory(datePath, dateDir)
                newsArticles.extend(dailyNews)
                
        logger.info(f"Total news articles processed: {len(newsArticles)}")
        return newsArticles
    
    def _getDateDirectories(self, startDate: datetime, endDate: datetime) -> List[str]:
        """Get list of date directory names to scan"""
        dateList = []
        currentDate = startDate
        
        while currentDate <= endDate:
            dateStr = currentDate.strftime("%Y-%m-%d")
            dateList.append(dateStr)
            currentDate += timedelta(days=1)
            
        return dateList
    
    def _processDateDirectory(self, datePath: str, dateStr: str) -> List[Dict[str, Any]]:
        """Process all news sources for a specific date"""
        newsArticles = []
        
        # Scan all source directories
        if not os.path.exists(datePath):
            return newsArticles
            
        for sourceDir in os.listdir(datePath):
            sourcePath = os.path.join(datePath, sourceDir)
            
            if os.path.isdir(sourcePath):
                logger.debug(f"Processing source: {sourceDir}")
                sourceNews = self._processSourceDirectory(sourcePath, sourceDir, dateStr)
                newsArticles.extend(sourceNews)
                
        return newsArticles
    
    def _processSourceDirectory(self, sourcePath: str, sourceName: str, dateStr: str) -> List[Dict[str, Any]]:
        """Process all news files from a specific source"""
        newsArticles = []
        
        for filename in os.listdir(sourcePath):
            if filename.endswith('.txt'):
                filePath = os.path.join(sourcePath, filename)
                try:
                    article = self._parseNewsFile(filePath, sourceName, dateStr)
                    if article and self._passesQualityFilter(article):
                        newsArticles.append(article)
                except Exception as e:
                    logger.warning(f"Failed to parse {filePath}: {str(e)}")
                    
        return newsArticles
    
    def _parseNewsFile(self, filePath: str, sourceName: str, dateStr: str) -> Optional[Dict[str, Any]]:
        """Parse individual news file"""
        try:
            with open(filePath, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                
            if len(lines) < 4:
                logger.warning(f"Insufficient content in file: {filePath}")
                return None
                
            # Parse structured content
            title = lines[0].replace('标题：', '').strip()
            publishDate = lines[1].replace('发布日期：', '').strip()
            sourceUrl = lines[2].replace('来源：', '').strip()
            website = lines[3].replace('网站：', '').strip()
            
            # Extract content (remaining lines)
            content = ''.join(lines[4:]).strip()
            
            return {
                'timestamp': self._parseTimestamp(publishDate, dateStr),
                'source': sourceName,
                'title': title,
                'content': content,
                'url': sourceUrl,
                'website': website,
                'file_path': filePath,
                'processed_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error parsing file {filePath}: {str(e)}")
            return None
    
    def _parseTimestamp(self, publishDate: str, fallbackDate: str) -> str:
        """Parse and normalize timestamp"""
        try:
            # Try to parse the publish date
            if publishDate and publishDate != fallbackDate:
                # Handle various date formats
                for fmtStr in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d']:
                    try:
                        parsedDate = datetime.strptime(publishDate, fmtStr)
                        return parsedDate.isoformat()
                    except ValueError:
                        continue
            
            # Fallback to directory date
            fallbackDateTime = datetime.strptime(fallbackDate, '%Y-%m-%d')
            return fallbackDateTime.isoformat()
            
        except Exception as e:
            logger.warning(f"Failed to parse timestamp {publishDate}, using current time: {str(e)}")
            return datetime.now().isoformat()
    
    def _passesQualityFilter(self, article: Dict[str, Any]) -> bool:
        """Apply quality filters to news article"""
        # Check minimum content length
        if len(article['content']) < self.qualityFilters['min_content_length']:
            return False
            
        # Check for excluded keywords
        excludeKeywords = self.qualityFilters['exclude_keywords']
        content = article['content'].lower()
        title = article['title'].lower()
        
        for keyword in excludeKeywords:
            if keyword in content or keyword in title:
                logger.debug(f"Article filtered out due to keyword: {keyword}")
                return False
                
        return True
    
    def _cleanContent(self, content: str) -> str:
        """Clean and normalize news content"""
        # Remove HTML tags if any
        content = re.sub(r'<[^>]+>', '', content)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Remove common patterns that might be ads or footers
        patterns = [
            r'责任编辑：.*',
            r'声明：.*',
            r'免责声明.*',
            r'本文来源.*',
        ]
        
        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)
            
        return content.strip()
    
    def saveStructuredNews(self, newsArticles: List[Dict[str, Any]], filename: Optional[str] = None) -> str:
        """Save processed news in structured format"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"processed_news_{timestamp}.json"
            
        outputPath = os.path.join(self.outputDir, filename)
        
        # Create summary statistics
        sourceStats = {}
        for article in newsArticles:
            source = article['source']
            sourceStats[source] = sourceStats.get(source, 0) + 1
            
        metadata = {
            'total_articles': len(newsArticles),
            'processing_time': datetime.now().isoformat(),
            'source_statistics': sourceStats,
            'data_range': {
                'start_date': min(article['timestamp'] for article in newsArticles) if newsArticles else None,
                'end_date': max(article['timestamp'] for article in newsArticles) if newsArticles else None
            }
        }
        
        # Save data
        outputData = {
            'metadata': metadata,
            'articles': newsArticles
        }
        
        with open(outputPath, 'w', encoding='utf-8') as file:
            json.dump(outputData, file, ensure_ascii=False, indent=2)
            
        logger.info(f"Saved {len(newsArticles)} processed news articles to {outputPath}")
        return outputPath
    
    def loadProcessedNews(self, filename: str) -> Dict[str, Any]:
        """Load previously processed news data"""
        filePath = os.path.join(self.outputDir, filename)
        
        with open(filePath, 'r', encoding='utf-8') as file:
            return json.load(file)
    
    def getLatestProcessedNews(self) -> Optional[Dict[str, Any]]:
        """Get the most recently processed news file"""
        if not os.path.exists(self.outputDir):
            return None
            
        files = [f for f in os.listdir(self.outputDir) if f.startswith('processed_news_') and f.endswith('.json')]
        
        if not files:
            return None
            
        latestFile = max(files, key=lambda f: os.path.getctime(os.path.join(self.outputDir, f)))
        return self.loadProcessedNews(latestFile)


def main():
    """Test the preprocessor"""
    preprocessor = NewsPreprocessor()
    
    # Scan and process recent news
    newsArticles = preprocessor.scanRecentNews()
    
    # Save processed data
    outputPath = preprocessor.saveStructuredNews(newsArticles)
    
    print(f"Processing complete. Output saved to: {outputPath}")
    print(f"Total articles processed: {len(newsArticles)}")


if __name__ == "__main__":
    main() 