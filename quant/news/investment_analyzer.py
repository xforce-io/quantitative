#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Investment News Analyzer
投资新闻分析器

Analyze news for investment insights using LLM
使用大模型分析新闻以获得投资洞察
"""

import os
import yaml
import json
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from pathlib import Path

from .news_collector import NewsCollector
from .news_analyzer import NewsAnalyzer
from .news_data_interface import NewsDataInterface

logger = logging.getLogger(__name__)

class InvestmentAnalyzer:
    """投资新闻分析器 - 基于大模型的投资洞察分析"""
    
    def __init__(self, configPath: str = None):
        """
        初始化投资分析器
        
        Args:
            configPath: 配置文件路径
        """
        if configPath is None:
            # 自动检测配置文件路径
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            configPath = os.path.join(project_root, "config", "investment_analysis.yaml")
        
        self.configPath = configPath
        self.config = self._loadConfig()
        self.newsCollector = NewsCollector()
        self.newsAnalyzer = NewsAnalyzer()
        self.newsDataInterface = NewsDataInterface()
        
        # 初始化大模型配置
        self.llmConfig = self.config.get('llm_config', {})
        self.investmentTargets = self.config.get('investment_targets', [])
        self.analysisConfig = self.config.get('analysis_config', {})
        
        # 创建报告目录
        self.reportsDir = Path(self.config.get('output_config', {}).get('reports_dir', 'reports'))
        self.reportsDir.mkdir(exist_ok=True)
        
        logger.info(f"Initialized InvestmentAnalyzer with {len(self.investmentTargets)} investment targets")
    
    def _loadConfig(self) -> Dict:
        """加载配置文件"""
        try:
            with open(self.configPath, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 从环境变量替换配置
            config = self._replaceEnvVars(config)
            return config
        except Exception as e:
            logger.error(f"Failed to load config from {self.configPath}: {e}")
            return {}
    
    def _replaceEnvVars(self, config: Any) -> Any:
        """递归替换配置中的环境变量"""
        if isinstance(config, dict):
            return {k: self._replaceEnvVars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._replaceEnvVars(item) for item in config]
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            envVar = config[2:-1]
            return os.getenv(envVar, config)
        else:
            return config
    
    def collectInvestmentNews(self, 
                             targets: List[str] = None,
                             daysBack: int = None) -> Dict[str, pd.DataFrame]:
        """
        收集投资品相关新闻
        
        Args:
            targets: 指定的投资品，如果为None则分析所有配置的投资品
            daysBack: 回溯天数，如果为None则使用配置文件设置
            
        Returns:
            按投资品分组的新闻数据字典
        """
        if targets is None:
            targets = [target['symbol'] for target in self.investmentTargets]
        
        if daysBack is None:
            daysBack = self.config.get('news_sources', {}).get('search_config', {}).get('days_back', 2)
        
        startDate = datetime.now() - timedelta(days=daysBack)
        endDate = datetime.now()
        
        logger.info(f"Loading unified news data from {startDate.date()} to {endDate.date()}")
        
        # 从统一数据接口加载新闻
        dateRange = (startDate.strftime('%Y-%m-%d'), endDate.strftime('%Y-%m-%d'))
        allUnifiedNews = self.newsDataInterface.loadUnifiedNews(dateRange=dateRange)
        
        logger.info(f"Loaded {len(allUnifiedNews)} total news articles from unified data")
        
        # 转换为DataFrame格式
        if allUnifiedNews:
            allNewsDF = pd.DataFrame(allUnifiedNews)
        else:
            allNewsDF = pd.DataFrame()
        
        investmentNews = {}
        
        for target in self.investmentTargets:
            if target['symbol'] not in targets:
                continue
            
            logger.info(f"Filtering news for {target['name']} ({target['symbol']})")
            
            if not allNewsDF.empty:
                # 根据关键词过滤相关新闻
                relevantNews = self._filterRelevantNews(allNewsDF, target['keywords'])
                investmentNews[target['symbol']] = relevantNews
                logger.info(f"Found {len(relevantNews)} relevant news items for {target['name']}")
            else:
                investmentNews[target['symbol']] = pd.DataFrame()
                logger.warning(f"No news available for {target['name']}")
        
        return investmentNews
    
    def _filterRelevantNews(self, newsData: pd.DataFrame, keywords: List[str]) -> pd.DataFrame:
        """根据关键词过滤相关新闻"""
        if newsData.empty:
            return newsData
        
        # 创建搜索模式
        pattern = '|'.join(keywords)
        
        # 在标题和内容中搜索关键词
        titleMatch = newsData.get('title', pd.Series()).str.contains(pattern, case=False, na=False)
        contentMatch = newsData.get('content', pd.Series()).str.contains(pattern, case=False, na=False)
        
        relevantNews = newsData[titleMatch | contentMatch]
        return relevantNews
    
    def analyzeWithLLM(self, newsData: pd.DataFrame, target: Dict) -> Dict:
        """
        使用大模型分析新闻
        
        Args:
            newsData: 新闻数据
            target: 投资品配置
            
        Returns:
            分析结果字典
        """
        if newsData.empty:
            return {
                'target': target['name'],
                'analysis_time': datetime.now().isoformat(),
                'summary': '暂无相关新闻数据',
                'sentiment': 'neutral',
                'recommendation': 'hold',
                'confidence': 0.0,
                'key_points': [],
                'news_references': []
            }
        
        # 准备新闻摘要
        newsSummary, newsReferences = self._prepareNewsSummary(newsData)
        
        # 构建提示词
        prompt = self._buildAnalysisPrompt(target, newsSummary)
        
        # 调用大模型分析
        try:
            llmResponse = self._callLLM(prompt)
            analysisResult = self._parseLLMResponse(llmResponse, target)
            
            # 添加新闻引用信息
            analysisResult['news_references'] = newsReferences
            
            return analysisResult
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return {
                'target': target['name'],
                'analysis_time': datetime.now().isoformat(),
                'summary': f'分析失败: {str(e)}',
                'sentiment': 'neutral',
                'recommendation': 'hold',
                'confidence': 0.0,
                'key_points': [],
                'news_references': newsReferences  # 即使分析失败也保留引用信息
            }
    
    def _prepareNewsSummary(self, newsData: pd.DataFrame) -> Tuple[str, List[Dict]]:
        """准备新闻摘要用于大模型分析，同时返回新闻引用信息"""
        if newsData.empty:
            return "暂无新闻数据", []
        
        # 取最新的新闻进行分析
        maxArticles = self.config.get('news_sources', {}).get('search_config', {}).get('max_articles_per_target', 20)
        recentNews = newsData.head(maxArticles)
        
        summaryParts = []
        newsReferences = []
        
        for idx, row in recentNews.iterrows():
            newsId = f"N{idx+1:02d}"  # Create unique identifier like N01, N02, etc.
            
            # 优化标题提取逻辑
            title = row.get('title', '') or ''
            if not title or title.strip() == '':
                # 如果标题为空，从内容中提取
                content_text = row.get('content', '')
                if content_text:
                    # 提取【】中的标题
                    import re
                    title_match = re.search(r'【([^】]+)】', content_text)
                    if title_match:
                        title = title_match.group(1)
                    else:
                        # 取内容的前50个字符作为标题
                        title = content_text[:50].replace('\n', ' ').strip()
                        if len(content_text) > 50:
                            title += '...'
                if not title:
                    title = '无标题'
            
            content = row.get('content', '')[:200] if row.get('content') else ''  # 限制内容长度
            
            # 优化时间提取逻辑
            time = row.get('timestamp') or row.get('datetime') or row.get('news_time', '未知时间')
            if time and time != '未知时间':
                # 如果时间是datetime对象，转换为字符串
                if hasattr(time, 'strftime'):
                    time = time.strftime('%Y-%m-%d %H:%M:%S')
                elif isinstance(time, str) and 'T' in time:
                    # 处理ISO格式时间
                    time = time.replace('T', ' ')[:19]
            
            source_name = row.get('source_name', row.get('source', '未知来源'))
            url = row.get('url', row.get('link', ''))
            
            # Add news summary with ID for LLM reference
            newsItem = f"[{newsId}] 时间: {time}\n来源: {source_name}\n标题: {title}\n内容摘要: {content}\n---"
            summaryParts.append(newsItem)
            
            # Store reference information
            newsReferences.append({
                'id': newsId,
                'title': title,
                'source': source_name,
                'time': str(time),
                'url': url,
                'sentiment': row.get('sentiment', 'neutral') if hasattr(row, 'sentiment') else 'neutral'
            })
        
        return '\n'.join(summaryParts), newsReferences
    
    def _buildAnalysisPrompt(self, target: Dict, newsSummary: str) -> str:
        """构建分析提示词，要求在关键要点中引用新闻来源"""
        targetName = target['name']
        category = target['category']
        
        prompt = f"""
作为一名专业的金融分析师，请基于以下新闻信息分析 {targetName} 的投资前景。

投资品信息:
- 名称: {targetName}
- 类别: {category}
- 权重: {target.get('weight', 0)}

新闻信息:
{newsSummary}

请从以下维度进行分析，并以JSON格式返回结果。特别注意：在关键要点中必须引用相关新闻ID（如[N01]、[N02]等）作为支撑：

1. market_sentiment: 市场情绪 (positive/negative/neutral)
2. price_impact: 价格影响预期 (strong_positive/positive/neutral/negative/strong_negative)
3. risk_assessment: 风险评估 (low/medium/high)
4. investment_recommendation: 投资建议 (strong_buy/buy/hold/sell/strong_sell)
5. confidence: 置信度 (0.0-1.0)
6. summary: 分析总结 (150字以内)
7. key_points: 关键要点列表，每个要点必须包含支撑的新闻引用ID

请确保返回的JSON格式正确，关键要点格式示例:
{{
  "market_sentiment": "positive",
  "price_impact": "positive", 
  "risk_assessment": "medium",
  "investment_recommendation": "buy",
  "confidence": 0.8,
  "summary": "基于当前新闻分析...",
  "key_points": [
    "科技股表现强劲，多家公司业绩超预期 [N01][N03]",
    "市场对AI概念股持续看好，资金流入明显 [N02]",
    "但需关注利率政策变化对估值的影响 [N04]"
  ]
}}
"""
        return prompt
    
    def _callLLM(self, prompt: str) -> str:
        """调用大模型API"""
        apiKey = self.llmConfig.get('api_key')
        baseUrl = self.llmConfig.get('base_url', 'https://api.openai.com/v1')
        model = self.llmConfig.get('model', 'gpt-4')
        
        if not apiKey:
            raise ValueError("LLM API key not configured")
        
        headers = {
            'Authorization': f'Bearer {apiKey}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.llmConfig.get('temperature', 0.3),
            'max_tokens': self.llmConfig.get('max_tokens', 2000)
        }
        
        response = requests.post(
            f"{baseUrl}/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"LLM API call failed: {response.status_code} - {response.text}")
        
        result = response.json()
        return result['choices'][0]['message']['content']
    
    def _parseLLMResponse(self, response: str, target: Dict) -> Dict:
        """解析大模型响应"""
        try:
            # 尝试从响应中提取JSON
            jsonStart = response.find('{')
            jsonEnd = response.rfind('}') + 1
            
            if jsonStart >= 0 and jsonEnd > jsonStart:
                jsonStr = response[jsonStart:jsonEnd]
                analysisData = json.loads(jsonStr)
            else:
                # 如果没有找到JSON，创建默认结构
                analysisData = {
                    'market_sentiment': 'neutral',
                    'price_impact': 'neutral',
                    'risk_assessment': 'medium',
                    'investment_recommendation': 'hold',
                    'confidence': 0.5,
                    'summary': response[:300],  # 取前300字符作为摘要
                    'key_points': []
                }
            
            # 添加元数据
            analysisData.update({
                'target': target['name'],
                'symbol': target['symbol'],
                'analysis_time': datetime.now().isoformat(),
                'raw_response': response
            })
            
            return analysisData
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                'target': target['name'],
                'symbol': target['symbol'],
                'analysis_time': datetime.now().isoformat(),
                'summary': response[:300],
                'sentiment': 'neutral',
                'recommendation': 'hold',
                'confidence': 0.0,
                'key_points': [],
                'error': str(e)
            }
    
    def generateDailyReport(self, 
                          targets: List[str] = None,
                          daysBack: int = None) -> Dict:
        """
        生成每日投资分析报告
        
        Args:
            targets: 指定的投资品，如果为None则分析所有配置的投资品
            daysBack: 回溯天数
            
        Returns:
            完整的分析报告字典
        """
        logger.info("Starting daily investment analysis report generation")
        
        # 收集新闻
        investmentNews = self.collectInvestmentNews(targets, daysBack)
        
        # 分析每个投资品
        analysisResults = {}
        for target in self.investmentTargets:
            if targets and target['symbol'] not in targets:
                continue
            
            newsData = investmentNews.get(target['symbol'], pd.DataFrame())
            logger.info(f"Analyzing {target['name']} with {len(newsData)} news items")
            
            # 基础分析
            if not newsData.empty:
                analyzedNews = self.newsAnalyzer.analyzeNewsDataFrame(newsData)
            else:
                analyzedNews = pd.DataFrame()
            
            # 大模型分析
            llmAnalysis = self.analyzeWithLLM(newsData, target)
            
            analysisResults[target['symbol']] = {
                'target_info': target,
                'news_count': len(newsData),
                'news_data': analyzedNews,
                'llm_analysis': llmAnalysis
            }
        
        # 生成综合报告
        report = {
            'report_date': datetime.now().strftime('%Y-%m-%d'),
            'report_time': datetime.now().isoformat(),
            'analysis_period': f"最近 {daysBack or 2} 天",
            'targets_analyzed': len(analysisResults),
            'individual_analysis': analysisResults,
            'summary': self._generateReportSummary(analysisResults)
        }
        
        # 保存报告
        self._saveReport(report)
        
        logger.info(f"Generated daily investment report for {len(analysisResults)} targets")
        return report
    
    def _generateReportSummary(self, analysisResults: Dict) -> Dict:
        """生成报告总结"""
        totalTargets = len(analysisResults)
        recommendations = {}
        sentiments = {}
        
        for symbol, result in analysisResults.items():
            llmAnalysis = result.get('llm_analysis', {})
            rec = llmAnalysis.get('investment_recommendation', 'hold')
            sentiment = llmAnalysis.get('market_sentiment', 'neutral')
            
            recommendations[rec] = recommendations.get(rec, 0) + 1
            sentiments[sentiment] = sentiments.get(sentiment, 0) + 1
        
        return {
            'total_targets': totalTargets,
            'recommendation_distribution': recommendations,
            'sentiment_distribution': sentiments,
            'market_outlook': self._determineMarketOutlook(sentiments, recommendations)
        }
    
    def _determineMarketOutlook(self, sentiments: Dict, recommendations: Dict) -> str:
        """确定市场展望"""
        positiveSignals = sentiments.get('positive', 0) + recommendations.get('buy', 0) + recommendations.get('strong_buy', 0)
        negativeSignals = sentiments.get('negative', 0) + recommendations.get('sell', 0) + recommendations.get('strong_sell', 0)
        
        if positiveSignals > negativeSignals:
            return 'optimistic'
        elif negativeSignals > positiveSignals:
            return 'pessimistic'
        else:
            return 'neutral'
    
    def _saveReport(self, report: Dict):
        """保存报告到文件"""
        try:
            reportDate = report['report_date']
            
            # 创建日期目录
            dateDir = self.reportsDir / reportDate
            dateDir.mkdir(exist_ok=True)
            
            # 保存JSON格式
            jsonPath = dateDir / 'investment_analysis.json'
            with open(jsonPath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            # 保存Markdown格式
            markdownPath = dateDir / 'investment_analysis.md'
            self._saveMarkdownReport(report, markdownPath)
            
            logger.info(f"Report saved to {dateDir}")
            
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
    
    def _saveMarkdownReport(self, report: Dict, filepath: Path):
        """保存Markdown格式报告"""
        markdown = f"""# 投资分析日报

**报告日期**: {report['report_date']}  
**分析时间**: {report['report_time']}  
**分析周期**: {report['analysis_period']}  
**分析标的**: {report['targets_analyzed']} 个

## 整体概览

"""
        
        summary = report.get('summary', {})
        markdown += f"- **市场展望**: {summary.get('market_outlook', 'neutral')}\n"
        markdown += f"- **投资建议分布**: {summary.get('recommendation_distribution', {})}\n"
        markdown += f"- **市场情绪分布**: {summary.get('sentiment_distribution', {})}\n\n"
        
        markdown += "## 个股分析\n\n"
        
        # 收集所有新闻引用信息，用于后续引用部分
        allNewsReferences = {}
        
        for symbol, analysis in report.get('individual_analysis', {}).items():
            targetInfo = analysis['target_info']
            llmAnalysis = analysis['llm_analysis']
            newsReferences = llmAnalysis.get('news_references', [])
            
            markdown += f"### {targetInfo['name']} ({symbol})\n\n"
            markdown += f"- **类别**: {targetInfo.get('category', 'unknown')}\n"
            markdown += f"- **新闻数量**: {analysis['news_count']}\n"
            markdown += f"- **市场情绪**: {llmAnalysis.get('market_sentiment', 'neutral')}\n"
            markdown += f"- **投资建议**: {llmAnalysis.get('investment_recommendation', 'hold')}\n"
            markdown += f"- **置信度**: {llmAnalysis.get('confidence', 0):.2f}\n\n"
            
            markdown += f"**分析摘要**: {llmAnalysis.get('summary', '暂无分析')}\n\n"
            
            keyPoints = llmAnalysis.get('key_points', [])
            if keyPoints:
                markdown += "**关键要点**:\n"
                for point in keyPoints:
                    markdown += f"- {point}\n"
                markdown += "\n"
            
            # 为每个标的添加新闻引用到全局字典
            for ref in newsReferences:
                refId = f"{symbol}_{ref['id']}"  # 为避免重复，加上标的前缀
                allNewsReferences[refId] = {
                    'target': targetInfo['name'],
                    'original_id': ref['id'],
                    **ref
                }
            
            markdown += "---\n\n"
        
        # 添加新闻来源引用部分
        if allNewsReferences:
            markdown += "## 📰 新闻来源引用\n\n"
            markdown += "以下是报告中引用的新闻来源，增强分析的可解释性和可信度：\n\n"
            
            # 按标的分组显示新闻引用
            currentTarget = None
            for refId, ref in allNewsReferences.items():
                if currentTarget != ref['target']:
                    currentTarget = ref['target']
                    markdown += f"#### {currentTarget}\n\n"
                
                # 格式化新闻引用
                timeStr = ref['time'][:19] if len(ref['time']) > 19 else ref['time']  # 截断时间字符串
                markdown += f"**[{ref['original_id']}]** {ref['title']}\n"
                markdown += f"- 来源: {ref['source']}\n"
                markdown += f"- 时间: {timeStr}\n"
                if ref.get('url'):
                    markdown += f"- 链接: {ref['url']}\n"
                if ref.get('sentiment') and ref['sentiment'] != 'neutral':
                    sentimentMap = {'positive': '积极', 'negative': '消极', 'neutral': '中性'}
                    markdown += f"- 情感倾向: {sentimentMap.get(ref['sentiment'], ref['sentiment'])}\n"
                markdown += "\n"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown) 