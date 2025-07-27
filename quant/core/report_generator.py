"""报告生成器 / Report Generator

这个模块提供统一的报告生成功能，支持：
- 多种报告格式
- 模板化报告
- 数据可视化
- 报告分发
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd

from .config_manager import ConfigManager
from .data_manager import DataManager

logger = logging.getLogger(__name__)


class ReportGenerator:
    """统一报告生成器"""
    
    def __init__(self, config_manager: ConfigManager, data_manager: DataManager):
        """Initialize report generator
        
        Args:
            config_manager: Configuration manager instance
            data_manager: Data manager instance
        """
        self.config_manager = config_manager
        self.data_manager = data_manager
        self.system_config = config_manager.get_system_config()
        
    def generate_news_analysis_report(self, 
                                     analysis_results: Dict[str, Any],
                                     format_type: str = "markdown") -> str:
        """Generate news analysis report
        
        Args:
            analysis_results: Analysis results data
            format_type: Report format (markdown, html, json)
            
        Returns:
            Path to generated report
        """
        report_data = {
            "title": "新闻投资分析报告",
            "generated_at": datetime.now().isoformat(),
            "executive_summary": self._create_executive_summary(analysis_results),
            "target_analysis": analysis_results.get("target_analysis", {}),
            "market_sentiment": analysis_results.get("market_sentiment", {}),
            "investment_recommendations": analysis_results.get("recommendations", []),
            "risk_assessment": analysis_results.get("risk_assessment", {}),
            "data_quality": analysis_results.get("data_quality", {})
        }
        
        return self.data_manager.save_report(
            report_data=report_data,
            report_type="news_analysis",
            target="comprehensive",
            format_type=format_type
        )
    
    def generate_trading_report(self,
                               backtest_results: Dict[str, Any],
                               format_type: str = "html") -> str:
        """Generate trading strategy report
        
        Args:
            backtest_results: Backtest results data
            format_type: Report format
            
        Returns:
            Path to generated report
        """
        report_data = {
            "title": "交易策略分析报告",
            "generated_at": datetime.now().isoformat(),
            "strategy_overview": backtest_results.get("strategy", {}),
            "performance_metrics": backtest_results.get("metrics", {}),
            "risk_metrics": backtest_results.get("risk", {}),
            "trade_analysis": backtest_results.get("trades", []),
            "optimization_results": backtest_results.get("optimization", {})
        }
        
        return self.data_manager.save_report(
            report_data=report_data,
            report_type="trading_analysis",
            target=backtest_results.get("symbol", "unknown"),
            format_type=format_type
        )
    
    def generate_daily_summary_report(self, date: Optional[str] = None) -> str:
        """Generate daily summary report
        
        Args:
            date: Date for report (YYYY-MM-DD), defaults to today
            
        Returns:
            Path to generated report
        """
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # Collect data for the day
        news_data = self.data_manager.get_news_data(days_back=1)
        investment_targets = self.config_manager.get_investment_targets()
        
        # Create summary
        report_data = {
            "title": f"每日投资分析总结 - {date}",
            "date": date,
            "generated_at": datetime.now().isoformat(),
            "news_summary": {
                "total_articles": len(news_data),
                "sources": list(set(article.get("source", "unknown") for article in news_data))
            },
            "target_summary": {},
            "market_overview": self._create_market_overview(news_data, investment_targets),
            "alerts": self._generate_alerts(news_data, investment_targets)
        }
        
        # Analyze each target
        for target in investment_targets:
            target_name = target.get("name", "")
            relevant_news = self._filter_news_by_target(news_data, target)
            
            report_data["target_summary"][target_name] = {
                "relevant_articles": len(relevant_news),
                "sentiment_trend": "neutral",  # Placeholder
                "key_events": [article.get("title", "")[:100] for article in relevant_news[:3]]
            }
        
        return self.data_manager.save_report(
            report_data=report_data,
            report_type="daily_summary",
            target=date.replace("-", ""),
            format_type="markdown"
        )
    
    def _create_executive_summary(self, analysis_results: Dict[str, Any]) -> str:
        """Create executive summary from analysis results"""
        target_count = len(analysis_results.get("target_analysis", {}))
        total_articles = analysis_results.get("data_quality", {}).get("total_articles", 0)
        
        summary = f"""
## 执行摘要

本报告分析了 {total_articles} 篇新闻文章，涵盖 {target_count} 个投资目标。

### 主要发现：
- 数据覆盖期间：过去7天
- 新闻来源数量：多个财经媒体
- 分析维度：情感分析、相关性评分、投资建议

### 总体市场情绪：
基于新闻内容分析，当前市场情绪整体偏向谨慎乐观。

### 投资建议概览：
建议投资者关注以下重点领域和风险因素...
        """.strip()
        
        return summary
    
    def _create_market_overview(self, 
                               news_data: List[Dict[str, Any]], 
                               investment_targets: List[Dict[str, Any]]) -> str:
        """Create market overview section"""
        if not news_data:
            return "今日无重大市场新闻。"
        
        # Simple market overview based on news keywords
        market_keywords = ["市场", "经济", "央行", "政策", "通胀", "利率"]
        market_news = []
        
        for article in news_data:
            title = article.get("title", "").lower()
            content = article.get("content", "").lower()
            
            for keyword in market_keywords:
                if keyword in title or keyword in content:
                    market_news.append(article)
                    break
        
        if market_news:
            return f"今日市场焦点：发现 {len(market_news)} 条重要市场新闻，主要关注经济政策和市场动态。"
        else:
            return "今日市场相对平静，无重大政策或经济消息。"
    
    def _generate_alerts(self, 
                        news_data: List[Dict[str, Any]], 
                        investment_targets: List[Dict[str, Any]]) -> List[str]:
        """Generate alerts based on news analysis"""
        alerts = []
        
        # Check for high-impact keywords
        high_impact_keywords = ["暴跌", "大涨", "突发", "紧急", "重大", "危机"]
        
        for article in news_data:
            title = article.get("title", "")
            for keyword in high_impact_keywords:
                if keyword in title:
                    alerts.append(f"⚠️ 发现高影响新闻: {title[:50]}...")
                    break
        
        # Limit alerts to avoid spam
        return alerts[:5]
    
    def _filter_news_by_target(self, 
                              news_data: List[Dict[str, Any]], 
                              target: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Filter news articles relevant to a specific target"""
        target_keywords = target.get("keywords", [])
        relevant_news = []
        
        for article in news_data:
            title = article.get("title", "").lower()
            content = article.get("content", "").lower()
            
            for keyword in target_keywords:
                if keyword.lower() in title or keyword.lower() in content:
                    relevant_news.append(article)
                    break
        
        return relevant_news
    
    def create_visualization(self, 
                           data: Dict[str, Any], 
                           chart_type: str = "bar",
                           title: str = "数据可视化") -> str:
        """Create data visualization
        
        Args:
            data: Data to visualize
            chart_type: Type of chart (bar, line, pie)
            title: Chart title
            
        Returns:
            Path to saved chart image
        """
        try:
            plt.figure(figsize=(10, 6))
            plt.rcParams['font.sans-serif'] = ['SimHei']  # Support Chinese characters
            plt.rcParams['axes.unicode_minus'] = False
            
            if chart_type == "bar" and isinstance(data, dict):
                plt.bar(data.keys(), data.values())
                plt.xlabel("类别")
                plt.ylabel("数值")
                
            elif chart_type == "pie" and isinstance(data, dict):
                plt.pie(data.values(), labels=data.keys(), autopct='%1.1f%%')
                
            plt.title(title)
            plt.tight_layout()
            
            # Save chart
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            chart_path = self.data_manager.reports_dir / "charts" / f"{chart_type}_{timestamp}.png"
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"Chart saved to: {chart_path}")
            return str(chart_path)
            
        except Exception as e:
            logger.error(f"Failed to create visualization: {e}")
            return ""
    
    def generate_comparison_report(self, 
                                  data_sets: List[Dict[str, Any]], 
                                  comparison_type: str = "performance") -> str:
        """Generate comparison report for multiple data sets
        
        Args:
            data_sets: List of data sets to compare
            comparison_type: Type of comparison
            
        Returns:
            Path to generated report
        """
        report_data = {
            "title": f"{comparison_type.title()} 比较报告",
            "generated_at": datetime.now().isoformat(),
            "comparison_type": comparison_type,
            "data_sets": data_sets,
            "summary": self._create_comparison_summary(data_sets, comparison_type),
            "detailed_analysis": self._create_detailed_comparison(data_sets)
        }
        
        return self.data_manager.save_report(
            report_data=report_data,
            report_type="comparison",
            target="multi_target",
            format_type="html"
        )
    
    def _create_comparison_summary(self, 
                                  data_sets: List[Dict[str, Any]], 
                                  comparison_type: str) -> str:
        """Create summary for comparison report"""
        return f"比较了 {len(data_sets)} 个数据集的 {comparison_type} 表现。"
    
    def _create_detailed_comparison(self, data_sets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create detailed comparison analysis"""
        return {
            "methodology": "基于统计指标进行量化比较",
            "results": [f"数据集 {i+1}: 详细分析结果" for i in range(len(data_sets))],
            "conclusions": "基于比较结果的结论和建议"
        } 