"""
Two-Stage News Analyzer Module
两阶段新闻分析器 - 实现粗-细两阶段分析策略
"""

import os
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import logging
import yaml
import openai
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib

from .news_preprocessor import NewsPreprocessor
from .unified_news_collector import UnifiedNewsCollector

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TwoStageNewsAnalyzer:
    """Two-stage news analysis system with cheap and premium models"""
    
    def __init__(self, config_path: str = "config/news_analysis_config.yaml"):
        """Initialize analyzer with configuration"""
        self.config = self._loadConfig(config_path)
        self.preprocessor = NewsPreprocessor(config_path)
        self.newsCollector = UnifiedNewsCollector(config_path)
        
        # Load model configurations
        self.cheapModelConfig = self.config['llm_configs']['cheap_model']
        self.premiumModelConfig = self.config['llm_configs']['premium_model']
        
        # Load analysis configurations
        self.stage1Config = self.config['analysis_stages']['stage1_coarse']
        self.stage2Config = self.config['analysis_stages']['stage2_fine']
        
        # Load investment targets
        self.investmentTargets = self.config['investment_targets']
        
        # Cache setup
        self.cacheDir = self.config['cache_config']['cache_dir']
        os.makedirs(self.cacheDir, exist_ok=True)
        
        # Rate limiting setup
        self.lastRequestTime = {}
        
    def _loadConfig(self, configPath: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(configPath, 'r', encoding='utf-8') as file:
                return yaml.safe_load(file)
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {configPath}")
            raise
    
    def _initializeLLMClient(self, modelType: str) -> openai.OpenAI:
        """Initialize LLM client for specified model type"""
        if modelType == "cheap":
            config = self.cheapModelConfig
        elif modelType == "premium":
            config = self.premiumModelConfig
        else:
            raise ValueError(f"Unknown model type: {modelType}")
        
        # Get API key from environment
        apiKey = os.getenv(config['api_key'].replace('${', '').replace('}', ''))
        baseUrl = os.getenv(config['base_url'].replace('${', '').replace('}', ''))
        
        if not apiKey:
            raise ValueError(f"API key not found for {modelType} model")
        
        return openai.OpenAI(
            api_key=apiKey,
            base_url=baseUrl if baseUrl else None
        )
    
    def _enforceRateLimit(self, modelType: str):
        """Enforce rate limiting for API calls"""
        if modelType == "cheap":
            maxRpm = self.cheapModelConfig['max_requests_per_minute']
        else:
            maxRpm = self.premiumModelConfig['max_requests_per_minute']
        
        minInterval = 60.0 / maxRpm
        
        if modelType in self.lastRequestTime:
            timeSinceLastRequest = time.time() - self.lastRequestTime[modelType]
            if timeSinceLastRequest < minInterval:
                sleepTime = minInterval - timeSinceLastRequest
                logger.debug(f"Rate limiting: sleeping for {sleepTime:.2f} seconds")
                time.sleep(sleepTime)
        
        self.lastRequestTime[modelType] = time.time()
    
    def _getCacheKey(self, content: str, analysisType: str) -> str:
        """Generate cache key for content and analysis type"""
        contentHash = hashlib.md5(content.encode('utf-8')).hexdigest()
        return f"{analysisType}_{contentHash}"
    
    def _loadFromCache(self, cacheKey: str) -> Optional[Dict[str, Any]]:
        """Load analysis result from cache"""
        cachePath = os.path.join(self.cacheDir, f"{cacheKey}.json")
        
        if not os.path.exists(cachePath):
            return None
        
        try:
            with open(cachePath, 'r', encoding='utf-8') as file:
                data = json.load(file)
                
            # Check if cache is still valid
            cacheTime = datetime.fromisoformat(data['cached_at'])
            expiryHours = self.config['cache_config']['cache_expiry_hours']
            
            if (datetime.now() - cacheTime).total_seconds() > expiryHours * 3600:
                logger.debug(f"Cache expired for key: {cacheKey}")
                return None
                
            return data['result']
            
        except Exception as e:
            logger.warning(f"Failed to load from cache: {str(e)}")
            return None
    
    def _saveToCache(self, cacheKey: str, result: Dict[str, Any]):
        """Save analysis result to cache"""
        cachePath = os.path.join(self.cacheDir, f"{cacheKey}.json")
        
        cacheData = {
            'cached_at': datetime.now().isoformat(),
            'result': result
        }
        
        try:
            with open(cachePath, 'w', encoding='utf-8') as file:
                json.dump(cacheData, file, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save to cache: {str(e)}")
    
    def runStage1Analysis(self, newsArticles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run stage 1 coarse analysis using cheap model"""
        logger.info(f"Starting Stage 1 analysis for {len(newsArticles)} articles")
        
        if not self.stage1Config['enabled']:
            logger.warning("Stage 1 analysis is disabled")
            return newsArticles
        
        analyzedArticles = []
        client = self._initializeLLMClient("cheap")
        
        # Process articles in batches
        batchSize = self.stage1Config['batch_size']
        
        for i in range(0, len(newsArticles), batchSize):
            batch = newsArticles[i:i + batchSize]
            logger.info(f"Processing batch {i//batchSize + 1}/{(len(newsArticles) + batchSize - 1)//batchSize}")
            
            batchResults = self._processBatchStage1(batch, client)
            analyzedArticles.extend(batchResults)
            
            # Add delay between batches
            time.sleep(2)
        
        logger.info(f"Stage 1 analysis completed for {len(analyzedArticles)} articles")
        return analyzedArticles
    
    def _processBatchStage1(self, batch: List[Dict[str, Any]], client: openai.OpenAI) -> List[Dict[str, Any]]:
        """Process a batch of articles in stage 1"""
        results = []
        
        for article in batch:
            try:
                # Check cache first
                contentForCache = f"{article['title']}|{article['content'][:500]}"
                cacheKey = self._getCacheKey(contentForCache, "stage1")
                
                cachedResult = self._loadFromCache(cacheKey)
                if cachedResult:
                    article.update(cachedResult)
                    results.append(article)
                    continue
                
                # Perform analysis
                self._enforceRateLimit("cheap")
                analysis = self._analyzeArticleStage1(article, client)
                
                # Update article with analysis results
                article.update(analysis)
                results.append(article)
                
                # Save to cache
                self._saveToCache(cacheKey, analysis)
                
            except Exception as e:
                logger.error(f"Failed to analyze article {article.get('title', 'Unknown')}: {str(e)}")
                # Add empty analysis to continue processing
                article.update({
                    'sentiment_score': 0.0,
                    'relevance_scores': {},
                    'keywords': [],
                    'category': 'unknown',
                    'summary': article['title'],
                    'stage1_error': str(e)
                })
                results.append(article)
        
        return results
    
    def _analyzeArticleStage1(self, article: Dict[str, Any], client: openai.OpenAI) -> Dict[str, Any]:
        """Analyze single article in stage 1"""
        prompt = self._buildStage1Prompt(article)
        
        response = client.chat.completions.create(
            model=self.cheapModelConfig['model'],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.stage1Config['max_tokens'],
            temperature=self.stage1Config['temperature']
        )
        
        result = response.choices[0].message.content
        return self._parseStage1Result(result)
    
    def _buildStage1Prompt(self, article: Dict[str, Any]) -> str:
        """Build prompt for stage 1 analysis"""
        targetKeywords = []
        for target in self.investmentTargets:
            targetKeywords.extend(target['keywords'])
        
        prompt = f"""
请对以下新闻进行初步分析，返回JSON格式结果：

标题: {article['title']}
内容: {article['content'][:1000]}...
来源: {article['source']}

分析要求：
1. 情感分析：评估新闻的整体情感倾向，返回-1到1之间的数值（-1=极度负面，0=中性，1=极度正面）
2. 相关性评分：评估新闻与以下投资品的相关性（0-1分）：
   - 纳斯达克指数（关键词：{self.investmentTargets[0]['keywords']}）
   - 印度股票（关键词：{self.investmentTargets[1]['keywords']}）  
   - 黄金（关键词：{self.investmentTargets[2]['keywords']}）
3. 关键词提取：提取3-5个最重要的关键词
4. 分类：将新闻分类为以下之一：technology, finance, politics, international, commodity, other
5. 摘要：生成50字以内的新闻摘要

返回格式：
{{
  "sentiment_score": 0.0,
  "relevance_scores": {{
    "NASDAQ": 0.0,
    "INDIA_STOCKS": 0.0,
    "GOLD": 0.0
  }},
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "category": "分类",
  "summary": "新闻摘要"
}}
"""
        return prompt
    
    def _parseStage1Result(self, result: str) -> Dict[str, Any]:
        """Parse stage 1 analysis result"""
        try:
            # Extract JSON from response
            import re
            jsonMatch = re.search(r'\{.*\}', result, re.DOTALL)
            if jsonMatch:
                jsonStr = jsonMatch.group(0)
                return json.loads(jsonStr)
            else:
                logger.warning("No JSON found in stage 1 result")
                return self._getDefaultStage1Result()
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse stage 1 JSON: {str(e)}")
            return self._getDefaultStage1Result()
    
    def _getDefaultStage1Result(self) -> Dict[str, Any]:
        """Get default stage 1 result when parsing fails"""
        return {
            'sentiment_score': 0.0,
            'relevance_scores': {
                'NASDAQ': 0.0,
                'INDIA_STOCKS': 0.0,
                'GOLD': 0.0
            },
            'keywords': [],
            'category': 'other',
            'summary': 'Analysis failed'
        }
    
    def filterForStage2(self, analyzedArticles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter articles for stage 2 based on relevance threshold"""
        threshold = self.stage2Config['relevance_threshold']
        maxPerTarget = self.stage2Config['max_articles_per_target']
        
        # Group articles by investment target
        targetGroups = {target['symbol']: [] for target in self.investmentTargets}
        
        for article in analyzedArticles:
            relevanceScores = article.get('relevance_scores', {})
            
            for targetSymbol, score in relevanceScores.items():
                if score >= threshold:
                    targetGroups[targetSymbol].append((article, score))
        
        # Sort and limit articles per target
        selectedArticles = []
        for targetSymbol, articles in targetGroups.items():
            # Sort by relevance score (descending)
            articles.sort(key=lambda x: x[1], reverse=True)
            
            # Take top N articles
            topArticles = articles[:maxPerTarget]
            selectedArticles.extend([article[0] for article in topArticles])
            
            logger.info(f"Selected {len(topArticles)} articles for {targetSymbol} (threshold: {threshold})")
        
        # Remove duplicates
        uniqueArticles = []
        seenUrls = set()
        
        for article in selectedArticles:
            url = article.get('url', '')
            if url not in seenUrls:
                seenUrls.add(url)
                uniqueArticles.append(article)
        
        logger.info(f"Filtered {len(uniqueArticles)} articles for Stage 2 analysis")
        return uniqueArticles
    
    def runStage2Analysis(self, filteredArticles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run stage 2 fine analysis using premium model"""
        logger.info(f"Starting Stage 2 analysis for {len(filteredArticles)} articles")
        
        if not self.stage2Config['enabled']:
            logger.warning("Stage 2 analysis is disabled")
            return filteredArticles
        
        client = self._initializeLLMClient("premium")
        results = []
        
        for article in filteredArticles:
            try:
                # Check cache first
                contentForCache = f"{article['title']}|{article['content'][:500]}"
                cacheKey = self._getCacheKey(contentForCache, "stage2")
                
                cachedResult = self._loadFromCache(cacheKey)
                if cachedResult:
                    article.update(cachedResult)
                    results.append(article)
                    continue
                
                # Perform deep analysis
                self._enforceRateLimit("premium")
                deepAnalysis = self._analyzeArticleStage2(article, client)
                
                # Update article with analysis results
                article.update(deepAnalysis)
                results.append(article)
                
                # Save to cache
                self._saveToCache(cacheKey, deepAnalysis)
                
            except Exception as e:
                logger.error(f"Failed stage 2 analysis for {article.get('title', 'Unknown')}: {str(e)}")
                article['stage2_error'] = str(e)
                results.append(article)
        
        logger.info(f"Stage 2 analysis completed for {len(results)} articles")
        return results
    
    def _analyzeArticleStage2(self, article: Dict[str, Any], client: openai.OpenAI) -> Dict[str, Any]:
        """Analyze single article in stage 2"""
        prompt = self._buildStage2Prompt(article)
        
        response = client.chat.completions.create(
            model=self.premiumModelConfig['model'],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.stage2Config['max_tokens'],
            temperature=self.stage2Config['temperature']
        )
        
        result = response.choices[0].message.content
        return self._parseStage2Result(result)
    
    def _buildStage2Prompt(self, article: Dict[str, Any]) -> str:
        """Build prompt for stage 2 analysis"""
        relevanceScores = article.get('relevance_scores', {})
        mainTarget = max(relevanceScores, key=relevanceScores.get) if relevanceScores else 'UNKNOWN'
        
        prompt = f"""
作为专业的投资分析师，请对以下新闻进行深度分析：

新闻信息：
标题: {article['title']}
内容: {article['content']}
来源: {article['source']}
初步情感评分: {article.get('sentiment_score', 'N/A')}
主要相关投资品: {mainTarget}
相关性评分: {relevanceScores}

请进行以下深度分析并返回JSON格式结果：

1. 深度情感分析：
   - 细致的情感倾向分析（包含信心度）
   - 识别关键情感驱动因素

2. 市场影响评估：
   - 短期市场影响预测（1-7天）
   - 中期市场影响预测（1-4周）
   - 影响程度评级（1-5分）

3. 投资建议：
   - 具体的投资操作建议（买入/卖出/持有）
   - 建议的投资期限
   - 建议的仓位大小（百分比）

4. 风险分析：
   - 主要风险因素识别
   - 风险等级评估（1-5分）
   - 风险缓解建议

返回格式：
{{
  "deep_sentiment": {{
    "score": 0.0,
    "confidence": 0.0,
    "key_factors": ["因素1", "因素2"]
  }},
  "market_impact": {{
    "short_term": 0.0,
    "medium_term": 0.0,
    "impact_level": 3,
    "reasoning": "影响原因分析"
  }},
  "investment_recommendation": {{
    "action": "buy/sell/hold",
    "time_horizon": "short/medium/long",
    "position_size": 0.0,
    "reasoning": "投资建议理由"
  }},
  "risk_analysis": {{
    "risk_factors": ["风险1", "风险2"],
    "risk_level": 3,
    "mitigation": "风险缓解建议"
  }}
}}
"""
        return prompt
    
    def _parseStage2Result(self, result: str) -> Dict[str, Any]:
        """Parse stage 2 analysis result"""
        try:
            import re
            jsonMatch = re.search(r'\{.*\}', result, re.DOTALL)
            if jsonMatch:
                jsonStr = jsonMatch.group(0)
                return json.loads(jsonStr)
            else:
                logger.warning("No JSON found in stage 2 result")
                return self._getDefaultStage2Result()
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse stage 2 JSON: {str(e)}")
            return self._getDefaultStage2Result()
    
    def _getDefaultStage2Result(self) -> Dict[str, Any]:
        """Get default stage 2 result when parsing fails"""
        return {
            'deep_sentiment': {
                'score': 0.0,
                'confidence': 0.0,
                'key_factors': []
            },
            'market_impact': {
                'short_term': 0.0,
                'medium_term': 0.0,
                'impact_level': 3,
                'reasoning': 'Analysis failed'
            },
            'investment_recommendation': {
                'action': 'hold',
                'time_horizon': 'medium',
                'position_size': 0.0,
                'reasoning': 'Analysis failed'
            },
            'risk_analysis': {
                'risk_factors': [],
                'risk_level': 3,
                'mitigation': 'Analysis failed'
            }
        }
    
    def generateFinalReport(self, analyzedArticles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate final investment analysis report"""
        logger.info("Generating final investment report")
        
        report = {
            'report_timestamp': datetime.now().isoformat(),
            'total_articles_analyzed': len(analyzedArticles),
            'summary_statistics': self._calculateSummaryStats(analyzedArticles),
            'target_analysis': self._analyzeByTarget(analyzedArticles),
            'overall_recommendations': self._generateOverallRecommendations(analyzedArticles),
            'risk_assessment': self._assessOverallRisk(analyzedArticles),
            'articles_detail': analyzedArticles
        }
        
        # Save report
        reportDir = self.config['reporting']['report_dir']
        os.makedirs(reportDir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reportPath = os.path.join(reportDir, f"two_stage_analysis_{timestamp}.json")
        
        with open(reportPath, 'w', encoding='utf-8') as file:
            json.dump(report, file, ensure_ascii=False, indent=2)
        
        logger.info(f"Final report saved to: {reportPath}")
        return report
    
    def _calculateSummaryStats(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics"""
        if not articles:
            return {}
        
        sentimentScores = [article.get('sentiment_score', 0) for article in articles]
        
        return {
            'avg_sentiment': sum(sentimentScores) / len(sentimentScores),
            'sentiment_distribution': {
                'positive': len([s for s in sentimentScores if s > 0.2]),
                'neutral': len([s for s in sentimentScores if -0.2 <= s <= 0.2]),
                'negative': len([s for s in sentimentScores if s < -0.2])
            },
            'source_distribution': self._getSourceDistribution(articles),
            'category_distribution': self._getCategoryDistribution(articles)
        }
    
    def _getSourceDistribution(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of articles by source"""
        distribution = {}
        for article in articles:
            source = article.get('source', 'unknown')
            distribution[source] = distribution.get(source, 0) + 1
        return distribution
    
    def _getCategoryDistribution(self, articles: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get distribution of articles by category"""
        distribution = {}
        for article in articles:
            category = article.get('category', 'unknown')
            distribution[category] = distribution.get(category, 0) + 1
        return distribution
    
    def _analyzeByTarget(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze articles by investment target"""
        targetAnalysis = {}
        
        for target in self.investmentTargets:
            symbol = target['symbol']
            relevantArticles = [
                article for article in articles
                if article.get('relevance_scores', {}).get(symbol, 0) > 0.3
            ]
            
            if relevantArticles:
                avgSentiment = sum(
                    article.get('sentiment_score', 0) for article in relevantArticles
                ) / len(relevantArticles)
                
                recommendations = [
                    article.get('investment_recommendation', {})
                    for article in relevantArticles
                    if 'investment_recommendation' in article
                ]
                
                actionCounts = {}
                for rec in recommendations:
                    action = rec.get('action', 'hold')
                    actionCounts[action] = actionCounts.get(action, 0) + 1
                
                targetAnalysis[symbol] = {
                    'article_count': len(relevantArticles),
                    'avg_sentiment': avgSentiment,
                    'recommendation_distribution': actionCounts,
                    'avg_risk_level': sum(
                        article.get('risk_analysis', {}).get('risk_level', 3)
                        for article in relevantArticles
                    ) / len(relevantArticles) if relevantArticles else 3
                }
        
        return targetAnalysis
    
    def _generateOverallRecommendations(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate overall investment recommendations"""
        # This would implement sophisticated logic to combine individual recommendations
        # For now, providing a basic implementation
        
        recommendations = {}
        for target in self.investmentTargets:
            symbol = target['symbol']
            relevantArticles = [
                article for article in articles
                if article.get('relevance_scores', {}).get(symbol, 0) > 0.5
            ]
            
            if relevantArticles:
                # Simple majority vote logic
                actions = [
                    article.get('investment_recommendation', {}).get('action', 'hold')
                    for article in relevantArticles
                    if 'investment_recommendation' in article
                ]
                
                if actions:
                    mostCommonAction = max(set(actions), key=actions.count)
                    recommendations[symbol] = {
                        'recommended_action': mostCommonAction,
                        'confidence': actions.count(mostCommonAction) / len(actions),
                        'supporting_articles': len(relevantArticles)
                    }
        
        return recommendations
    
    def _assessOverallRisk(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Assess overall market risk"""
        riskLevels = [
            article.get('risk_analysis', {}).get('risk_level', 3)
            for article in articles
            if 'risk_analysis' in article
        ]
        
        if not riskLevels:
            return {'overall_risk_level': 3, 'confidence': 0.0}
        
        avgRisk = sum(riskLevels) / len(riskLevels)
        
        return {
            'overall_risk_level': round(avgRisk, 1),
            'confidence': len(riskLevels) / len(articles),
            'risk_distribution': {
                'low': len([r for r in riskLevels if r <= 2]),
                'medium': len([r for r in riskLevels if 2 < r <= 4]),
                'high': len([r for r in riskLevels if r > 4])
            }
        }
    
    def runFullAnalysis(self) -> Dict[str, Any]:
        """Run complete two-stage analysis pipeline"""
        logger.info("Starting full two-stage news analysis")
        
        try:
            # Step 1: Collect news data using unified collector
            logger.info("Step 1: Collecting news data from all sources")
            rawNews = self.newsCollector.collectForInvestmentTargets()
            
            # Flatten the target-based news into a single list
            allNews = []
            for targetName, targetNews in rawNews.items():
                allNews.extend(targetNews)
            
            if not allNews:
                logger.warning("No news articles found")
                return {'error': 'No news articles found'}
            
            logger.info(f"Collected {len(allNews)} articles for analysis")
            
            # Step 2: Stage 1 analysis (coarse)
            logger.info("Step 2: Running Stage 1 analysis")
            stage1Results = self.runStage1Analysis(allNews)
            
            # Step 3: Filter for Stage 2
            logger.info("Step 3: Filtering articles for Stage 2")
            filteredArticles = self.filterForStage2(stage1Results)
            
            # Step 4: Stage 2 analysis (fine)
            logger.info("Step 4: Running Stage 2 analysis")
            stage2Results = self.runStage2Analysis(filteredArticles)
            
            # Step 5: Generate final report
            logger.info("Step 5: Generating final report")
            finalReport = self.generateFinalReport(stage2Results)
            
            logger.info("Two-stage analysis completed successfully")
            return finalReport
            
        except Exception as e:
            logger.error(f"Full analysis failed: {str(e)}")
            raise


def main():
    """Test the two-stage analyzer"""
    analyzer = TwoStageNewsAnalyzer()
    
    # Run full analysis
    result = analyzer.runFullAnalysis()
    
    print("Analysis completed!")
    print(f"Total articles analyzed: {result.get('total_articles_analyzed', 0)}")
    print(f"Overall recommendations: {result.get('overall_recommendations', {})}")


if __name__ == "__main__":
    main() 