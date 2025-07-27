#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
今日投资品新闻分析报告生成器
Daily Investment News Analysis Report Generator

用于生成今天的投资品新闻分析报告
Generate daily investment news analysis report
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
projectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(projectRoot))

# 加载环境变量
load_dotenv(dotenv_path=projectRoot / '.env')

from quant.news.investment_analyzer import InvestmentAnalyzer

def setupLogging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/daily_report_{datetime.now().strftime("%Y%m%d")}.log')
        ]
    )

def checkEnvironmentVariables():
    """检查必要的环境变量配置"""
    requiredEnvVars = [
        'LLM_API_KEY',
        'LLM_BASE_URL', 
        'LLM_MODEL'
    ]
    
    missingVars = []
    for var in requiredEnvVars:
        if not os.getenv(var):
            missingVars.append(var)
    
    if missingVars:
        logging.warning(f"Missing environment variables: {missingVars}")
        logging.info("Please set up .env file based on env_example_unified.txt")
        return False
    
    return True

def generateDailyReport():
    """生成今日投资分析报告"""
    try:
        logging.info("Starting daily investment news analysis report generation")
        
        # 创建必要的目录
        os.makedirs('logs', exist_ok=True)
        os.makedirs('reports', exist_ok=True)
        
        # 检查环境变量
        if not checkEnvironmentVariables():
            logging.error("Environment variables not properly configured")
            return None
        
        # 初始化投资分析器
        analyzer = InvestmentAnalyzer()
        
        # 生成分析报告 (分析最近2天的新闻)
        report = analyzer.generateDailyReport(daysBack=2)
        
        if report:
            reportDate = report['report_date']
            logging.info(f"Daily investment report generated successfully for {reportDate}")
            
            # 打印报告摘要
            printReportSummary(report)
            
            return report
        else:
            logging.error("Failed to generate daily report")
            return None
            
    except Exception as e:
        logging.error(f"Error generating daily report: {str(e)}")
        return None

def printReportSummary(report):
    """打印报告摘要到控制台"""
    print("\n" + "="*60)
    print(f"📊 投资品新闻分析日报 - {report['report_date']}")
    print("="*60)
    
    summary = report.get('summary', {})
    print(f"📈 市场展望: {summary.get('market_outlook', 'neutral')}")
    print(f"🎯 分析标的: {summary.get('total_targets', 0)} 个")
    
    # 显示投资建议分布
    recommendations = summary.get('recommendation_distribution', {})
    if recommendations:
        print("\n💡 投资建议分布:")
        for rec, count in recommendations.items():
            print(f"   {rec}: {count}")
    
    # 显示情绪分布
    sentiments = summary.get('sentiment_distribution', {})
    if sentiments:
        print("\n😊 市场情绪分布:")
        for sentiment, count in sentiments.items():
            print(f"   {sentiment}: {count}")
    
    # 显示个股亮点
    print("\n🔍 个股分析亮点:")
    for symbol, analysis in report.get('individual_analysis', {}).items():
        targetInfo = analysis['target_info']
        llmAnalysis = analysis['llm_analysis']
        newsCount = analysis['news_count']
        
        sentiment = llmAnalysis.get('market_sentiment', 'neutral')
        recommendation = llmAnalysis.get('investment_recommendation', 'hold')
        confidence = llmAnalysis.get('confidence', 0)
        
        print(f"   📄 {targetInfo['name']} ({symbol})")
        print(f"      新闻数: {newsCount} | 情绪: {sentiment} | 建议: {recommendation} | 置信度: {confidence:.2f}")
    
    print("\n" + "="*60)
    print(f"📁 详细报告已保存至: reports/{report['report_date']}/")
    print("="*60 + "\n")

def main():
    """主函数"""
    setupLogging()
    
    print("🚀 启动投资品新闻分析报告生成器...")
    
    # 生成报告
    report = generateDailyReport()
    
    if report:
        print("✅ 投资品新闻分析报告生成完成!")
    else:
        print("❌ 投资品新闻分析报告生成失败!")
        sys.exit(1)

if __name__ == "__main__":
    main() 