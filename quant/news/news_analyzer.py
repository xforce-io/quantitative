#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
News Analyzer
资讯分析器

Analyze news data for sentiment, keywords, and market impact
分析资讯数据的情感、关键词和市场影响
"""

import re
import os
import json
import jieba
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import Counter
import logging

# LLM相关导入
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logging.warning("OpenAI library not available. LLM features will be disabled.")

logger = logging.getLogger(__name__)

class NewsAnalyzer:
    """资讯分析器 - 提供新闻内容分析功能，支持关键词和LLM混合分析"""
    
    # 扩展的情感词汇（根据quick_fixes.md优化）
    POSITIVE_KEYWORDS = {
        '上涨', '上升', '增长', '增加', '提升', '改善', '优化', '利好', '积极', '正面',
        '突破', '创新高', '盈利', '收益', '回升', '反弹', '向好', '强劲', '稳健', '乐观',
        '买入', '推荐', '看好', '涨停', '大涨', '飙升', '暴涨', '拉升', '井喷', '爆发',
        # 新增关键词
        '超预期', '强势', '领涨', '翻倍', '激增', '大幅上涨', '持续上涨', '加速上涨'
    }
    
    NEGATIVE_KEYWORDS = {
        '下跌', '下降', '减少', '下滑', '恶化', '下行', '利空', '消极', '负面', '担忧',
        '风险', '危机', '亏损', '损失', '暴跌', '大跌', '跌停', '崩盘', '抛售', '卖出',
        '警告', '困难', '压力', '挑战', '不确定', '悲观', '疲软', '低迷', '重挫', '血洗',
        # 新增关键词
        '腰斩', '恐慌', '急跌', '狂跌', '连续下跌', '持续下跌', '加速下跌', '深跌'
    }
    
    # 市场相关关键词（扩展版本）
    MARKET_KEYWORDS = {
        'stock': ['股票', '股价', '股市', 'A股', '港股', '美股', '创业板', '科创板', '主板', '中小板'],
        'finance': ['金融', '银行', '保险', '证券', '基金', '债券', '期货', '外汇', '信托', '租赁'],
        'economy': ['经济', 'GDP', 'CPI', 'PMI', '通胀', '通缩', '利率', '汇率', '货币政策', '财政政策'],
        'industry': ['制造业', '科技', '医药', '新能源', '房地产', '汽车', '消费', '互联网', '人工智能', '芯片']
    }
    
    # 扩展的投资品关键词（根据quick_fixes.md）
    EXPANDED_KEYWORDS = {
        'NASDAQ': [
            # 原有关键词
            'NASDAQ', '纳斯达克', '科技股', 'QQQ', 'TQQQ',
            # 新增相关词汇
            '美股', '道琼斯', 'S&P500', '标普500',
            '苹果', 'Apple', '微软', 'Microsoft', 
            '谷歌', 'Google', '亚马逊', 'Amazon',
            '特斯拉', 'Tesla', '英伟达', 'NVIDIA', 'Meta', 'Netflix'
        ],
        'GOLD': [
            '黄金', 'Gold', '贵金属', 'GLD', 'IAU',
            '黄金价格', '避险资产', '通胀对冲',
            '金价', '贵金属价格', '避险', '白银', '铂金'
        ],
        'INDIA_STOCKS': [
            '印度', 'India', '孟买', 'Mumbai',
            'NSE', 'BSE', '印度股市', '印度经济',
            'INDA', 'MINDX', '新兴市场', '印度指数'
        ]
    }
    
    # 权重配置（根据quick_fixes.md）
    TITLE_WEIGHT = 2.0    # 标题权重
    CONTENT_WEIGHT = 1.0  # 内容权重
    TIME_DECAY = 0.8      # 每天衰减20%
    
    def __init__(self, useLLM: bool = False, llmConfig: Dict = None):
        """
        初始化分析器
        
        Args:
            useLLM: 是否使用LLM分析
            llmConfig: LLM配置字典
        """
        self.useLLM = useLLM
        self.llmConfig = llmConfig or {}
        
        # 配置分析模式
        self.analysisMode = self.llmConfig.get('analysis_mode', 'keyword')  # keyword, llm, hybrid
        self.llmThreshold = self.llmConfig.get('llm_threshold', 0.3)  # 混合模式阈值
        
        # 初始化jieba
        self._initializeJieba()
        
        # 配置LLM
        if self.useLLM and HAS_OPENAI:
            self._configureLLM()
        elif self.useLLM and not HAS_OPENAI:
            logger.warning("LLM requested but OpenAI not available, falling back to keyword analysis")
            self.useLLM = False
    
    def _initializeJieba(self):
        """初始化jieba分词器"""
        # 添加自定义词汇
        for keywords in self.EXPANDED_KEYWORDS.values():
            for keyword in keywords:
                jieba.add_word(keyword, freq=1000)  # Add frequency parameter for jieba compatibility
    
    def _configureLLM(self):
        """配置LLM客户端"""
        apiKey = self.llmConfig.get('api_key') or os.getenv('LLM_API_KEY') or os.getenv('OPENAI_API_KEY')
        baseUrl = self.llmConfig.get('base_url') or os.getenv('LLM_BASE_URL')
        
        if not apiKey:
            logger.warning("No LLM API key found, disabling LLM features")
            self.useLLM = False
            return
        
        # 创建OpenAI客户端实例
        self.client = openai.OpenAI(
            api_key=apiKey,
            base_url=baseUrl
        )
        
        self.model = self.llmConfig.get('model', 'gpt-3.5-turbo')
    
    def extractTitleFromContent(self, content: str) -> str:
        """提取标题从内容（根据quick_fixes.md）"""
        if not content:
            return ""
        
        # 提取【】中的标题
        titleMatch = re.search(r'【([^】]+)】', content)
        if titleMatch:
            return titleMatch.group(1)
        
        # 或者取第一句话
        sentences = re.split(r'[。！？.!?]', content)
        return sentences[0][:50] if sentences else ""
    
    def cleanNewsContent(self, content: str) -> str:
        """清洗新闻内容（根据quick_fixes.md）"""
        if not content:
            return ""
        
        # 移除多余空格和换行
        content = re.sub(r'\s+', ' ', content)
        
        # 移除特殊字符，保留中文、英文、数字和基本标点
        content = re.sub(r'[^\u4e00-\u9fa5\w\s.,!?()（）]', '', content)
        
        return content.strip()
    
    def calculateSimpleTimeWeight(self, newsTime: str) -> float:
        """计算简单时间权重（根据quick_fixes.md）"""
        try:
            newsDate = datetime.strptime(newsTime, "%Y-%m-%d %H:%M:%S")
            hoursAgo = (datetime.now() - newsDate).total_seconds() / 3600
            
            if hoursAgo <= 24:
                return 1.0
            elif hoursAgo <= 72:
                return 0.8
            else:
                return 0.5
        except:
            return 0.7  # 默认权重
    
    def analyzeSentiment(self, text: str, newsTime: str = None, isTitle: bool = False) -> Dict:
        """
        分析文本情感 - 支持关键词和LLM混合方法，增加时间权重
        
        Args:
            text: 要分析的文本
            newsTime: 新闻时间（用于时间权重计算）
            isTitle: 是否为标题（用于权重调整）
            
        Returns:
            包含情感分析结果的字典
        """
        if not text or not isinstance(text, str):
            return {'sentiment': 'neutral', 'score': 0.0, 'confidence': 0.0, 'method': 'none'}
        
        # 清洗文本
        cleanedText = self.cleanNewsContent(text)
        
        # 首先使用关键词方法
        keywordResult = self._keywordSentimentAnalysis(cleanedText, newsTime, isTitle)
        
        # 根据分析模式决定是否使用LLM
        if self.analysisMode == 'keyword':
            return keywordResult
        elif self.analysisMode == 'llm' and self.useLLM:
            return self._llmSentimentAnalysis(cleanedText) or keywordResult
        elif self.analysisMode == 'hybrid' and self.useLLM:
            # 混合模式：如果关键词分析置信度低，使用LLM补充
            if keywordResult['confidence'] < self.llmThreshold:
                llmResult = self._llmSentimentAnalysis(cleanedText)
                if llmResult and llmResult['confidence'] > keywordResult['confidence']:
                    # 合并结果，以LLM为主，关键词为辅
                    llmResult['keyword_sentiment'] = keywordResult['sentiment']
                    llmResult['keyword_score'] = keywordResult['score']
                    return llmResult
            return keywordResult
        else:
            return keywordResult
    
    def _keywordSentimentAnalysis(self, text: str, newsTime: str = None, isTitle: bool = False) -> Dict:
        """基于关键词的情感分析（优化版本）"""
        # 分词
        words = jieba.cut(text)
        wordsList = [word.strip() for word in words if word.strip()]
        
        # 计算正面和负面词汇数量
        positiveCount = sum(1 for word in wordsList if word in self.POSITIVE_KEYWORDS)
        negativeCount = sum(1 for word in wordsList if word in self.NEGATIVE_KEYWORDS)
        
        # 计算情感得分和置信度
        totalWords = len(wordsList)
        if totalWords == 0:
            score = 0.0
            confidence = 0.0
        else:
            # 基础得分计算
            baseScore = (positiveCount - negativeCount) / totalWords
            
            # 调整阈值（根据quick_fixes.md）- 更敏感的阈值
            sentimentScore = baseScore * 10  # 放大系数：将得分乘以10倍
            
            # 应用权重
            if isTitle:
                sentimentScore *= self.TITLE_WEIGHT
            else:
                sentimentScore *= self.CONTENT_WEIGHT
            
            # 应用时间权重
            if newsTime:
                timeWeight = self.calculateSimpleTimeWeight(newsTime)
                sentimentScore *= timeWeight
            
            # 置信度基于情感词汇的比例
            sentimentWords = positiveCount + negativeCount
            confidence = min(sentimentWords / totalWords * 3, 1.0)  # 提高置信度计算
            
            score = sentimentScore
        
        # 确定情感倾向（更敏感的阈值）
        if score > 0.02:  # 从0.05降低到0.02
            sentiment = 'positive'
        elif score < -0.02:  # 从-0.05提高到-0.02
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'score': score,
            'confidence': confidence,
            'positive_count': positiveCount,
            'negative_count': negativeCount,
            'total_words': totalWords,
            'method': 'keyword'
        }
    
    def _llmSentimentAnalysis(self, text: str) -> Optional[Dict]:
        """基于LLM的情感分析"""
        prompt = f"""
请分析以下新闻文本的市场情感倾向。请从投资者和市场的角度来评估。

新闻内容：
{text}

请按以下JSON格式回答：
{{
    "sentiment": "positive/negative/neutral",
    "score": <数值，范围-1到1，正数表示积极，负数表示消极>,
    "confidence": <置信度，范围0到1>,
    "reasoning": "<简要说明分析理由>"
}}

只回答JSON，不要添加其他内容。
"""
        
        response = self._callLLM(prompt, maxTokens=200, temperature=0.2)
        if not response:
            return None
        
        try:
            # 提取JSON部分
            jsonStart = response.find('{')
            jsonEnd = response.rfind('}') + 1
            if jsonStart >= 0 and jsonEnd > jsonStart:
                jsonStr = response[jsonStart:jsonEnd]
                result = json.loads(jsonStr)
                
                # 验证结果格式
                requiredFields = ['sentiment', 'score', 'confidence']
                if all(field in result for field in requiredFields):
                    result['method'] = 'llm'
                    return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM sentiment result: {e}")
        
        return None
    
    def _callLLM(self, prompt: str, maxTokens: int = 1000, temperature: float = 0.3) -> Optional[str]:
        """
        调用LLM API
        
        Args:
            prompt: 输入提示
            maxTokens: 最大token数
            temperature: 温度参数
            
        Returns:
            LLM响应文本
        """
        if not self.useLLM or not self.model or not hasattr(self, 'client'):
            return None
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=maxTokens,
                temperature=temperature
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return None
    
    def analyzeMarketImpact(self, text: str, targetAssets: List[str] = None) -> Dict:
        """
        分析新闻对市场的潜在影响
        
        Args:
            text: 新闻文本
            targetAssets: 目标资产列表
            
        Returns:
            市场影响分析结果
        """
        if not self.useLLM:
            # 降级到关键词分析
            return self._keywordMarketImpactAnalysis(text, targetAssets)
        
        targetAssetsStr = ', '.join(targetAssets) if targetAssets else '股票市场'
        
        prompt = f"""
请分析以下新闻对{targetAssetsStr}的潜在市场影响。

新闻内容：
{text}

请从以下几个维度分析：
1. 短期影响（1-7天）
2. 中期影响（1-3个月）
3. 影响强度（1-10分）
4. 影响类型（价格、成交量、投资者情绪等）

请按以下JSON格式回答：
{{
    "short_term_impact": "positive/negative/neutral",
    "medium_term_impact": "positive/negative/neutral", 
    "impact_intensity": <1-10分>,
    "impact_types": ["price", "volume", "sentiment"],
    "confidence": <置信度0-1>,
    "summary": "<简要总结>"
}}

只回答JSON，不要添加其他内容。
"""
        
        response = self._callLLM(prompt, maxTokens=300, temperature=0.2)
        if not response:
            return self._keywordMarketImpactAnalysis(text, targetAssets)
        
        try:
            jsonStart = response.find('{')
            jsonEnd = response.rfind('}') + 1
            if jsonStart >= 0 and jsonEnd > jsonStart:
                jsonStr = response[jsonStart:jsonEnd]
                result = json.loads(jsonStr)
                result['method'] = 'llm'
                return result
        except json.JSONDecodeError:
            pass
        
        return self._keywordMarketImpactAnalysis(text, targetAssets)
    
    def _keywordMarketImpactAnalysis(self, text: str, targetAssets: List[str] = None) -> Dict:
        """基于关键词的市场影响分析"""
        sentiment = self._keywordSentimentAnalysis(text)
        
        # 分析影响强度
        impactWords = ['重大', '重要', '关键', '突破', '暴涨', '暴跌', '历史', '首次', '创新高', '创新低']
        words = jieba.cut(text)
        impactCount = sum(1 for word in words if word in impactWords)
        
        # 简单的影响强度评估
        intensity = min(impactCount * 2 + abs(sentiment['score']) * 5, 10)
        
        return {
            'short_term_impact': sentiment['sentiment'],
            'medium_term_impact': sentiment['sentiment'],
            'impact_intensity': intensity,
            'impact_types': ['sentiment'],
            'confidence': sentiment['confidence'],
            'summary': f"基于关键词分析，情感倾向为{sentiment['sentiment']}",
            'method': 'keyword'
        }
    
    def extractKeywords(self, text: str, topN: int = 10, useLLMExtraction: bool = None) -> List[Tuple[str, int]]:
        """
        提取关键词 - 支持传统分词和LLM语义提取
        
        Args:
            text: 要分析的文本
            topN: 返回前N个关键词
            useLLMExtraction: 是否使用LLM提取，None时根据配置决定
            
        Returns:
            关键词及其频次的列表
        """
        if not text or not isinstance(text, str):
            return []
        
        # 决定是否使用LLM
        shouldUseLLM = useLLMExtraction if useLLMExtraction is not None else (
            self.useLLM and self.analysisMode in ['llm', 'hybrid']
        )
        
        # 获取传统关键词
        traditionalKeywords = self._extractTraditionalKeywords(text, topN)
        
        if shouldUseLLM:
            # 尝试LLM关键词提取
            llmKeywords = self._extractLLMKeywords(text, topN)
            if llmKeywords:
                # 合并LLM和传统关键词
                return self._mergeKeywords(traditionalKeywords, llmKeywords, topN)
        
        return traditionalKeywords
    
    def _extractTraditionalKeywords(self, text: str, topN: int) -> List[Tuple[str, int]]:
        """传统基于分词的关键词提取"""
        # 分词
        words = jieba.cut(text)
        
        # 过滤停用词和短词
        stopWords = {'的', '是', '在', '有', '和', '与', '及', '或', '但', '等', '了', '将', '已', '被', '把'}
        validWords = [word.strip() for word in words 
                     if word.strip() and len(word.strip()) > 1 and word.strip() not in stopWords]
        
        # 统计词频
        wordCounts = Counter(validWords)
        
        return wordCounts.most_common(topN)
    
    def _extractLLMKeywords(self, text: str, topN: int) -> Optional[List[Tuple[str, int]]]:
        """基于LLM的语义关键词提取"""
        prompt = f"""
请分析以下新闻文本，提取最重要的{topN}个关键词。请关注：
1. 与金融市场相关的术语
2. 公司名称、产品名称
3. 重要的数字和指标
4. 行业相关词汇

新闻内容：
{text}

请按以下JSON格式回答，提供关键词及其重要性评分（1-10）：
{{
    "keywords": [
        {{"term": "关键词1", "score": 8}},
        {{"term": "关键词2", "score": 7}}
    ]
}}

只回答JSON，不要添加其他内容。
"""
        
        response = self._callLLM(prompt, maxTokens=300, temperature=0.1)
        if not response:
            return None
        
        try:
            jsonStart = response.find('{')
            jsonEnd = response.rfind('}') + 1
            if jsonStart >= 0 and jsonEnd > jsonStart:
                jsonStr = response[jsonStart:jsonEnd]
                result = json.loads(jsonStr)
                
                if 'keywords' in result:
                    # 转换为 (term, score) 元组列表
                    keywords = []
                    for item in result['keywords']:
                        if 'term' in item and 'score' in item:
                            keywords.append((item['term'], item['score']))
                    return keywords[:topN]
        
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _mergeKeywords(self, traditional: List[Tuple[str, int]], 
                      llm: List[Tuple[str, int]], topN: int) -> List[Tuple[str, int]]:
        """合并传统关键词和LLM关键词"""
        # 创建合并字典
        merged = {}
        
        # 添加传统关键词（权重0.4）
        for term, freq in traditional:
            merged[term] = freq * 0.4
        
        # 添加LLM关键词（权重0.6）
        for term, score in llm:
            if term in merged:
                merged[term] += score * 0.6
            else:
                merged[term] = score * 0.6
        
        # 排序并返回前N个
        sortedKeywords = sorted(merged.items(), key=lambda x: x[1], reverse=True)
        return [(term, int(score)) for term, score in sortedKeywords[:topN]]
    
    def categorizeNews(self, text: str) -> Dict[str, List[str]]:
        """
        新闻分类 - 支持关键词匹配和LLM语义分类
        
        Args:
            text: 要分析的文本
            
        Returns:
            按类别分组的关键词字典，包含置信度信息
        """
        if not text or not isinstance(text, str):
            return {}
        
        # 传统关键词分类
        traditionalCategories = self._traditionalCategorization(text)
        
        # 如果启用LLM，尝试语义分类
        if self.useLLM and self.analysisMode in ['llm', 'hybrid']:
            llmCategories = self._llmCategorization(text)
            if llmCategories:
                # 合并结果
                return self._mergeCategories(traditionalCategories, llmCategories)
        
        return traditionalCategories
    
    def _traditionalCategorization(self, text: str) -> Dict[str, List[str]]:
        """传统基于关键词的分类"""
        # 分词
        words = jieba.cut(text)
        words_list = [word.strip() for word in words if word.strip()]
        
        categories = {}
        for category, keywords in self.MARKET_KEYWORDS.items():
            matchedKeywords = [word for word in words_list if word in keywords]
            if matchedKeywords:
                categories[category] = {
                    'keywords': list(set(matchedKeywords)),
                    'confidence': min(len(matchedKeywords) / 3.0, 1.0),
                    'method': 'keyword'
                }
        
        return categories
    
    def _llmCategorization(self, text: str) -> Optional[Dict[str, Dict]]:
        """基于LLM的语义分类"""
        categories = list(self.MARKET_KEYWORDS.keys())
        categoriesDesc = {
            'stock': '股票市场相关',
            'finance': '金融行业相关', 
            'economy': '宏观经济相关',
            'industry': '特定行业相关'
        }
        
        prompt = f"""
请分析以下新闻文本属于哪些类别，并为每个类别提供置信度评分。

类别说明：
- stock: 股票市场相关（股价、交易、上市等）
- finance: 金融行业相关（银行、保险、基金等）
- economy: 宏观经济相关（GDP、通胀、货币政策等）
- industry: 特定行业相关（制造业、科技、医药等）

新闻内容：
{text}

请按以下JSON格式回答：
{{
    "categories": {{
        "stock": {{"confidence": 0.8, "reasoning": "涉及股价变动"}},
        "finance": {{"confidence": 0.3, "reasoning": "略有提及金融"}}
    }}
}}

只包含置信度 > 0.3 的类别。只回答JSON，不要添加其他内容。
"""
        
        response = self._callLLM(prompt, maxTokens=200, temperature=0.1)
        if not response:
            return None
        
        try:
            jsonStart = response.find('{')
            jsonEnd = response.rfind('}') + 1
            if jsonStart >= 0 and jsonEnd > jsonStart:
                jsonStr = response[jsonStart:jsonEnd]
                result = json.loads(jsonStr)
                
                if 'categories' in result:
                    categorized = {}
                    for category, info in result['categories'].items():
                        if category in categories and info.get('confidence', 0) > 0.3:
                            categorized[category] = {
                                'confidence': info['confidence'],
                                'reasoning': info.get('reasoning', ''),
                                'method': 'llm'
                            }
                    return categorized
        
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _mergeCategories(self, traditional: Dict, llm: Dict) -> Dict:
        """合并传统分类和LLM分类结果"""
        merged = {}
        
        # 合并所有类别
        allCategories = set(traditional.keys()) | set(llm.keys())
        
        for category in allCategories:
            tradInfo = traditional.get(category, {})
            llmInfo = llm.get(category, {})
            
            if tradInfo and llmInfo:
                # 两种方法都检测到该类别
                merged[category] = {
                    'keywords': tradInfo.get('keywords', []),
                    'confidence': (tradInfo.get('confidence', 0) + llmInfo.get('confidence', 0)) / 2,
                    'reasoning': llmInfo.get('reasoning', ''),
                    'method': 'hybrid'
                }
            elif tradInfo:
                merged[category] = tradInfo
            elif llmInfo:
                merged[category] = llmInfo
        
        return merged
    
    def analyzeNewsDataFrame(self, newsData: pd.DataFrame) -> pd.DataFrame:
        """
        批量分析新闻DataFrame
        
        Args:
            newsData: 包含新闻数据的DataFrame
            
        Returns:
            添加了分析结果的DataFrame
        """
        if newsData.empty:
            return newsData
        
        # 创建副本避免修改原数据
        analyzedData = newsData.copy()
        
        # 确保有必要的列
        if 'title' not in analyzedData.columns and 'content' not in analyzedData.columns:
            logger.warning("No title or content column found in news data")
            return analyzedData
        
        # 合并标题和内容进行分析
        if 'title' in analyzedData.columns and 'content' in analyzedData.columns:
            analyzedData['full_text'] = analyzedData['title'].fillna('') + ' ' + analyzedData['content'].fillna('')
        elif 'title' in analyzedData.columns:
            analyzedData['full_text'] = analyzedData['title'].fillna('')
        else:
            analyzedData['full_text'] = analyzedData['content'].fillna('')
        
        # 情感分析
        sentimentResults = analyzedData['full_text'].apply(self.analyzeSentiment)
        analyzedData['sentiment'] = sentimentResults.apply(lambda x: x['sentiment'])
        analyzedData['sentiment_score'] = sentimentResults.apply(lambda x: x['score'])
        analyzedData['sentiment_confidence'] = sentimentResults.apply(lambda x: x.get('confidence', 0.0))
        analyzedData['sentiment_method'] = sentimentResults.apply(lambda x: x.get('method', 'keyword'))
        
        # 保持向后兼容
        analyzedData['positive_words'] = sentimentResults.apply(lambda x: x.get('positive_count', 0))
        analyzedData['negative_words'] = sentimentResults.apply(lambda x: x.get('negative_count', 0))
        
        # 关键词提取
        keywordResults = analyzedData['full_text'].apply(lambda x: self.extractKeywords(x, topN=5))
        analyzedData['keywords'] = keywordResults.apply(lambda x: [kw[0] for kw in x])
        analyzedData['keyword_scores'] = keywordResults.apply(lambda x: dict(x))
        
        # 新闻分类
        categorizeResults = analyzedData['full_text'].apply(self.categorizeNews)
        analyzedData['categories'] = categorizeResults
        
        # 提取分类置信度信息
        if self.useLLM:
            analyzedData['category_confidence'] = categorizeResults.apply(
                lambda x: {k: v.get('confidence', 0) for k, v in x.items()} if x else {}
            )
            analyzedData['category_methods'] = categorizeResults.apply(
                lambda x: {k: v.get('method', 'keyword') for k, v in x.items()} if x else {}
            )
        
        # 如果启用了LLM，添加市场影响分析
        if self.useLLM:
            logger.info("Running market impact analysis with LLM")
            marketImpacts = analyzedData['full_text'].apply(
                lambda x: self.analyzeMarketImpact(x)
            )
            analyzedData['market_impact'] = marketImpacts
            analyzedData['impact_intensity'] = marketImpacts.apply(lambda x: x.get('impact_intensity', 0))
            analyzedData['impact_confidence'] = marketImpacts.apply(lambda x: x.get('confidence', 0))
        
        # 删除临时列
        analyzedData.drop('full_text', axis=1, inplace=True)
        
        logger.info(f"Analyzed {len(analyzedData)} news items")
        return analyzedData
    
    def getSentimentTrend(self, newsData: pd.DataFrame, timeColumn: str = 'datetime') -> pd.DataFrame:
        """
        获取情感趋势
        
        Args:
            newsData: 包含分析结果的新闻数据
            timeColumn: 时间列名
            
        Returns:
            按时间聚合的情感趋势DataFrame
        """
        if newsData.empty or 'sentiment_score' not in newsData.columns:
            return pd.DataFrame()
        
        # 确保时间列存在
        if timeColumn not in newsData.columns:
            logger.warning(f"Time column '{timeColumn}' not found")
            return pd.DataFrame()
        
        # 转换时间格式
        newsData[timeColumn] = pd.to_datetime(newsData[timeColumn])
        newsData['date'] = newsData[timeColumn].dt.date
        
        # 按日期聚合情感数据
        sentimentTrend = newsData.groupby('date').agg({
            'sentiment_score': ['mean', 'std', 'count'],
            'positive_words': 'sum',
            'negative_words': 'sum'
        }).round(4)
        
        # 展平多级列名
        sentimentTrend.columns = ['_'.join(col).strip() for col in sentimentTrend.columns]
        sentimentTrend = sentimentTrend.reset_index()
        
        # 重命名列
        sentimentTrend.rename(columns={
            'sentiment_score_mean': 'avg_sentiment',
            'sentiment_score_std': 'sentiment_volatility',
            'sentiment_score_count': 'news_count',
            'positive_words_sum': 'total_positive_words',
            'negative_words_sum': 'total_negative_words'
        }, inplace=True)
        
        return sentimentTrend
    
    def getTopKeywords(self, newsData: pd.DataFrame, topN: int = 20) -> List[Tuple[str, int]]:
        """
        获取热门关键词
        
        Args:
            newsData: 新闻数据
            topN: 返回前N个关键词
            
        Returns:
            关键词及其频次的列表
        """
        if newsData.empty or 'keywords' not in newsData.columns:
            return []
        
        # 收集所有关键词
        allKeywords = []
        for keywords in newsData['keywords']:
            if isinstance(keywords, list):
                allKeywords.extend(keywords)
        
        # 统计词频
        keywordCounts = Counter(allKeywords)
        
        return keywordCounts.most_common(topN)
    
    def filterNewsByKeywords(self, newsData: pd.DataFrame, keywords: List[str], 
                           searchColumns: List[str] = None) -> pd.DataFrame:
        """
        按关键词过滤新闻
        
        Args:
            newsData: 新闻数据
            keywords: 关键词列表
            searchColumns: 搜索的列名列表，默认搜索title和content
            
        Returns:
            包含关键词的新闻数据
        """
        if newsData.empty:
            return newsData
        
        if searchColumns is None:
            searchColumns = ['title', 'content']
        
        # 过滤存在的列
        availableColumns = [col for col in searchColumns if col in newsData.columns]
        if not availableColumns:
            logger.warning("No searchable columns found")
            return pd.DataFrame()
        
        # 创建搜索模式
        keywordPattern = '|'.join(keywords)
        
        # 在所有可搜索列中查找
        mask = pd.Series([False] * len(newsData))
        for col in availableColumns:
            mask |= newsData[col].str.contains(keywordPattern, case=False, na=False)
        
        return newsData[mask]
    
    def generateNewsReport(self, newsData: pd.DataFrame, title: str = "新闻分析报告") -> Dict:
        """
        生成新闻分析报告
        
        Args:
            newsData: 已分析的新闻数据
            title: 报告标题
            
        Returns:
            包含分析报告的字典
        """
        if newsData.empty:
            return {'title': title, 'summary': 'No news data available'}
        
        # 基础统计
        totalNews = len(newsData)
        
        # 情感统计
        sentimentCounts = newsData['sentiment'].value_counts() if 'sentiment' in newsData.columns else {}
        avgSentiment = newsData['sentiment_score'].mean() if 'sentiment_score' in newsData.columns else 0
        
        # 时间范围
        if 'datetime' in newsData.columns:
            timeRange = {
                'start': newsData['datetime'].min(),
                'end': newsData['datetime'].max()
            }
        else:
            timeRange = {'start': None, 'end': None}
        
        # 热门关键词
        topKeywords = self.getTopKeywords(newsData, topN=10)
        
        # 来源统计
        sourceCounts = newsData['source'].value_counts() if 'source' in newsData.columns else {}
        
        report = {
            'title': title,
            'generated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {
                'total_news': totalNews,
                'time_range': timeRange,
                'avg_sentiment': round(avgSentiment, 4),
                'sentiment_distribution': sentimentCounts.to_dict(),
                'top_keywords': topKeywords[:10],
                'source_distribution': sourceCounts.to_dict()
            }
        }
        
        return report 