#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Investment News Analysis CLI Tool
投资新闻分析命令行工具

统一的投资新闻分析入口脚本，支持多种新闻分析功能
Unified investment news analysis entry script supporting various analysis functions
"""

import os
import sys
import argparse
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
from quant.news.news_collector import NewsCollector
from quant.news.news_analyzer import NewsAnalyzer
from quant.news.news_data_interface import NewsDataInterface
from quant.news.unified_news_collector import UnifiedNewsCollector

def setupLogging(level: str = 'INFO'):
    """设置日志配置"""
    logLevel = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=logLevel,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/investment_news_{datetime.now().strftime("%Y%m%d")}.log')
        ]
    )

def listTargets():
    """列出可用的投资分析目标"""
    analyzer = InvestmentAnalyzer()
    targets = analyzer.investmentTargets
    
    print("🎯 可用的投资分析目标:")
    print("=" * 70)
    for target in targets:
        print(f"  📊 {target['name']:<20} ({target['symbol']:<15}) - {target['category']}")
        keywords = ', '.join(target['keywords'][:5])  # 显示前5个关键词
        print(f"      关键词: {keywords}...")
        print()
    print("=" * 70)

def generateDailyReport(args):
    """生成投资分析日报"""
    print("📊 开始生成投资分析日报")
    print(f"📅 分析周期: 最近 {args.days_back} 天")
    
    if args.targets:
        print(f"🎯 指定目标: {', '.join(args.targets)}")
    
    try:
        analyzer = InvestmentAnalyzer()
        
        # 生成报告
        report = analyzer.generateDailyReport(
            targets=args.targets,
            daysBack=args.days_back
        )
        
        if report:
            # 显示摘要
            summary = report.get('summary', {})
            print("\n📈 报告生成完成!")
            print("=" * 60)
            print(f"报告日期: {report['report_date']}")
            print(f"分析标的: {summary.get('total_targets', 0)} 个")
            print(f"市场展望: {summary.get('market_outlook', 'neutral')}")
            
            # 显示投资建议分布
            recommendations = summary.get('recommendation_distribution', {})
            if recommendations:
                print(f"投资建议: {recommendations}")
            
            # 显示情绪分布
            sentiments = summary.get('sentiment_distribution', {})
            if sentiments:
                print(f"市场情绪: {sentiments}")
            
            print("=" * 60)
            print(f"📁 详细报告已保存至: reports/{report['report_date']}/")
            
        else:
            print("❌ 报告生成失败")
            
    except Exception as e:
        print(f"❌ 报告生成失败: {str(e)}")
        logging.error(f"Report generation failed: {e}")

def collectNews(args):
    """收集新闻数据"""
    print("📰 开始收集新闻数据")
    print(f"📅 收集周期: 最近 {args.days_back} 天")
    print(f"📡 数据源: {', '.join(args.sources)}")
    
    try:
        collector = UnifiedNewsCollector()
        
        # 设置日期范围
        endDate = datetime.now()
        startDate = endDate - timedelta(days=args.days_back)
        
        # 收集所有新闻 (UnifiedNewsCollector会根据配置从多个源收集)
        print(f"\n📡 正在从配置的数据源收集新闻...")
        try:
            newsData = collector.collectAllNews(
                startDate=startDate.strftime('%Y-%m-%d'),
                endDate=endDate.strftime('%Y-%m-%d')
            )
            totalNews = len(newsData) if newsData else 0
            print(f"✅ 收集到 {totalNews} 条新闻")
            
        except Exception as e:
            print(f"⚠️  新闻收集失败 - {str(e)}")
            totalNews = 0
        
        print(f"\n📊 总计收集新闻: {totalNews} 条")
        print("📁 新闻数据已保存至 data/news_unified/ 目录")
        
    except Exception as e:
        print(f"❌ 新闻收集失败: {str(e)}")
        logging.error(f"News collection failed: {e}")

def analyzeNews(args):
    """分析新闻数据"""
    print("🔍 开始分析新闻数据")
    print(f"📅 分析周期: 最近 {args.days_back} 天")
    
    if args.targets:
        print(f"🎯 分析目标: {', '.join(args.targets)}")
    
    try:
        # 加载新闻数据
        newsInterface = NewsDataInterface()
        endDate = datetime.now()
        startDate = endDate - timedelta(days=args.days_back)
        dateRange = (startDate.strftime('%Y-%m-%d'), endDate.strftime('%Y-%m-%d'))
        
        allNews = newsInterface.loadUnifiedNews(dateRange=dateRange)
        print(f"📊 加载新闻数据: {len(allNews)} 条")
        
        if not allNews:
            print("❌ 没有找到新闻数据")
            return
        
        # 基础分析
        analyzer = NewsAnalyzer()
        
        import pandas as pd
        newsDF = pd.DataFrame(allNews)
        
        # 分析新闻
        analyzedNews = analyzer.analyzeNewsDataFrame(newsDF)
        
        print("📈 新闻分析完成!")
        print("=" * 60)
        
        # 显示基本统计
        if not analyzedNews.empty:
            sentimentCounts = analyzedNews['sentiment'].value_counts()
            print("情感分布:")
            for sentiment, count in sentimentCounts.items():
                print(f"  {sentiment}: {count}")
            
            # 显示关键词
            if 'keywords' in analyzedNews.columns:
                allKeywords = []
                for keywords in analyzedNews['keywords']:
                    if isinstance(keywords, list):
                        allKeywords.extend(keywords)
                
                from collections import Counter
                topKeywords = Counter(allKeywords).most_common(10)
                print("\n热门关键词:")
                for keyword, count in topKeywords:
                    print(f"  {keyword}: {count}")
        
        print("=" * 60)
        
        # 保存分析结果
        resultFile = f"reports/news_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('reports', exist_ok=True)
        
        import json
        analysisResult = {
            'analysis_date': datetime.now().isoformat(),
            'news_count': len(allNews),
            'analysis_period': f"最近 {args.days_back} 天",
            'sentiment_distribution': sentimentCounts.to_dict() if not analyzedNews.empty else {},
            'top_keywords': topKeywords if 'topKeywords' in locals() else []
        }
        
        with open(resultFile, 'w', encoding='utf-8') as f:
            json.dump(analysisResult, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"📁 分析结果已保存至: {resultFile}")
        
    except Exception as e:
        print(f"❌ 新闻分析失败: {str(e)}")
        logging.error(f"News analysis failed: {e}")

def showDataSummary(args):
    """显示数据汇总信息"""
    print("📊 数据汇总信息")
    
    try:
        newsInterface = NewsDataInterface()
        summary = newsInterface.getDataSummary()
        
        print("=" * 60)
        print(f"📁 数据文件数量: {summary.get('total_files', 0)}")
        print(f"📰 总新闻数量: {summary.get('total_articles', 0)}")
        print(f"📡 数据源: {', '.join(summary.get('sources', []))}")
        
        dataSourceTypes = summary.get('data_source_types', {})
        print(f"💾 数据来源: API({dataSourceTypes.get('api', 0)}), 本地({dataSourceTypes.get('local_file', 0)})")
        
        dateRange = summary.get('date_range', {})
        if dateRange.get('earliest') and dateRange.get('latest'):
            print(f"📅 数据时间范围: {dateRange['earliest'][:10]} 到 {dateRange['latest'][:10]}")
        
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 获取数据汇总失败: {str(e)}")
        logging.error(f"Data summary failed: {e}")

def configTargets(args):
    """配置投资分析目标"""
    if args.action == 'list':
        listTargets()
    elif args.action == 'add':
        print("🔧 添加新的投资目标")
        print("⚠️  请手动编辑 config/investment_analysis.yaml 文件")
        print("📖 参考现有目标的格式进行配置")
    elif args.action == 'edit':
        print("🔧 编辑投资目标配置")
        print("⚠️  请手动编辑 config/investment_analysis.yaml 文件")
        configFile = Path(projectRoot) / "config" / "investment_analysis.yaml"
        print(f"📁 配置文件路径: {configFile}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='投资新闻分析工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s list                              # 列出投资目标
  %(prog)s report                            # 生成日报
  %(prog)s report --targets NASDAQ GOLD     # 生成指定目标的报告
  %(prog)s collect --sources sina eastmoney # 收集新闻
  %(prog)s analyze --days-back 3            # 分析最近3天新闻
  %(prog)s summary                           # 显示数据汇总
        """
    )
    
    # 创建子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # list 命令
    listParser = subparsers.add_parser('list', help='列出可用的投资分析目标')
    
    # report 命令
    reportParser = subparsers.add_parser('report', help='生成投资分析日报')
    reportParser.add_argument('--targets', nargs='+', help='指定分析目标 (例如: NASDAQ GOLD)')
    reportParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # collect 命令
    collectParser = subparsers.add_parser('collect', help='收集新闻数据')
    collectParser.add_argument('--sources', nargs='+', 
                              choices=['sina', 'eastmoney', 'wallstreetcn', 'all'],
                              default=['sina', 'eastmoney', 'wallstreetcn'], 
                              help='新闻数据源')
    collectParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # analyze 命令
    analyzeParser = subparsers.add_parser('analyze', help='分析新闻数据')
    analyzeParser.add_argument('--targets', nargs='+', help='指定分析目标')
    analyzeParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # summary 命令
    summaryParser = subparsers.add_parser('summary', help='显示数据汇总信息')
    
    # config 命令
    configParser = subparsers.add_parser('config', help='配置投资分析目标')
    configParser.add_argument('action', choices=['list', 'add', 'edit'], help='配置操作')
    
    # 通用参数
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='日志级别')
    
    args = parser.parse_args()
    
    # 设置日志
    setupLogging(args.log_level)
    
    # 创建必要的目录
    os.makedirs('logs', exist_ok=True)
    os.makedirs('reports', exist_ok=True)
    os.makedirs('data/news_unified', exist_ok=True)
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'list':
            listTargets()
        elif args.command == 'report':
            generateDailyReport(args)
        elif args.command == 'collect':
            collectNews(args)
        elif args.command == 'analyze':
            analyzeNews(args)
        elif args.command == 'summary':
            showDataSummary(args)
        elif args.command == 'config':
            configTargets(args)
        else:
            print(f"❌ 未知命令: {args.command}")
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n👋 用户中断操作")
    except Exception as e:
        print(f"❌ 执行失败: {str(e)}")
        logging.error(f"Command execution failed: {e}")

if __name__ == "__main__":
    main() 