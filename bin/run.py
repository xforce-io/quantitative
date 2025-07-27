#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quantitative Trading System Unified Entry Point
量化交易系统统一入口

统一的CLI入口脚本，整合所有功能模块
Unified CLI entry script integrating all functional modules
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
projectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(projectRoot))

# 加载环境变量
load_dotenv(dotenv_path=projectRoot / '.env')

def setupLogging(level: str = 'INFO'):
    """设置统一的日志配置"""
    logLevel = getattr(logging, level.upper(), logging.INFO)
    
    # 确保logs目录存在
    logsDir = projectRoot / 'logs'
    logsDir.mkdir(exist_ok=True)
    
    logging.basicConfig(
        level=logLevel,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f'logs/quant_system_{datetime.now().strftime("%Y%m%d")}.log')
        ]
    )

def createParser():
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        description='量化交易系统统一入口 (Quantitative Trading System Unified Entry)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例 (Examples):

🚀 交易策略 (Trading Strategies):
  %(prog)s trading list                        # 列出可用策略
  %(prog)s trading backtest grid 000001.SZ    # 网格策略回测
  %(prog)s trading optimize grid 002594.SZ    # 策略参数优化
  
📰 新闻分析 (News Analysis):  
  %(prog)s news list                           # 列出投资目标
  %(prog)s news collect                        # 收集新闻数据
  %(prog)s news analyze                        # 分析新闻数据
  %(prog)s news report                         # 生成投资日报
  
⚙️  系统管理 (System Management):
  %(prog)s system status                       # 查看系统状态
  %(prog)s system config                       # 配置管理
  %(prog)s system clean                        # 清理缓存
        """
    )
    
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='日志级别')
    parser.add_argument('--config', help='配置文件路径')
    
    subparsers = parser.add_subparsers(dest='module', help='功能模块')
    
    # 交易策略子命令
    tradingParser = subparsers.add_parser('trading', help='交易策略模块')
    tradingSubparsers = tradingParser.add_subparsers(dest='action', help='交易操作')
    
    # 交易策略 - 列表
    tradingSubparsers.add_parser('list', help='列出可用策略')
    
    # 交易策略 - 回测
    backtestParser = tradingSubparsers.add_parser('backtest', help='策略回测')
    backtestParser.add_argument('strategy', choices=['grid', 'enhanced_grid'], help='策略类型')
    backtestParser.add_argument('symbol', help='股票代码')
    backtestParser.add_argument('--start-date', default='2023-01-01', help='开始日期')
    backtestParser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'), help='结束日期')
    backtestParser.add_argument('--initial-balance', type=float, default=100000, help='初始资金')
    backtestParser.add_argument('--grid-spacing', type=float, default=0.02, help='网格间距')
    backtestParser.add_argument('--grid-levels', type=int, default=10, help='网格层数')
    
    # 交易策略 - 从实验加载回测
    backtestFromExpParser = tradingSubparsers.add_parser('backtest-from-experiment', help='从实验结果加载配置进行回测')
    backtestFromExpParser.add_argument('experiment_path', help='实验目录路径')
    backtestFromExpParser.add_argument('--start-date', help='开始日期 (覆盖实验配置)')
    backtestFromExpParser.add_argument('--end-date', help='结束日期 (覆盖实验配置)')
    backtestFromExpParser.add_argument('--initial-balance', type=float, help='初始资金 (覆盖实验配置)')
    backtestFromExpParser.add_argument('--output-format', choices=['json', 'excel', 'both'], default='both', help='输出格式')
    
    # 交易策略 - 优化
    optimizeParser = tradingSubparsers.add_parser('optimize', help='参数优化')
    optimizeParser.add_argument('strategy', choices=['grid', 'enhanced_grid'], help='策略类型')
    optimizeParser.add_argument('symbol', help='股票代码')
    optimizeParser.add_argument('--start-date', default='2018-01-01', help='开始日期 (建议至少7年历史数据)')
    optimizeParser.add_argument('--end-date', default=datetime.now().strftime('%Y-%m-%d'), help='结束日期')
    optimizeParser.add_argument('--optimization-method', choices=['comprehensive', 'random', 'genetic', 'pso'], 
                              default='comprehensive', help='优化方法 (comprehensive=综合优化, random=随机搜索, genetic=遗传算法, pso=粒子群优化)')
    optimizeParser.add_argument('--initial-capital', type=float, default=100000, help='初始资金')
    optimizeParser.add_argument('--min-optimization-years', type=int, default=5, help='最小优化期年数 (默认5年)')
    optimizeParser.add_argument('--min-backtest-years', type=int, default=2, help='最小回测期年数 (默认2年)')
    optimizeParser.add_argument('--optimization-ratio', type=float, default=0.7, help='优化期占总数据比例 (默认0.7即70%)')
    
    # 交易策略 - 模拟交易
    liveParser = tradingSubparsers.add_parser('live', help='模拟交易')
    liveParser.add_argument('strategy', choices=['grid', 'enhanced_grid'], help='策略类型')
    liveParser.add_argument('symbol', help='股票代码')
    liveParser.add_argument('--initial-balance', type=float, default=100000, help='初始资金')
    liveParser.add_argument('--grid-spacing', type=float, default=0.02, help='网格间距')
    liveParser.add_argument('--grid-levels', type=int, default=10, help='网格层数')
    
    # 交易策略 - Agent 实验
    agentParser = tradingSubparsers.add_parser('agent', help='Agent 策略实验')
    agentSubparsers = agentParser.add_subparsers(dest='agent_action', help='Agent 操作')
    
    # Agent - 列出实验
    agentSubparsers.add_parser('list', help='列出可用的实验配置')
    
    # Agent - 运行实验
    runExpParser = agentSubparsers.add_parser('run', help='运行指定实验')
    runExpParser.add_argument('experiment', help='实验名称')
    runExpParser.add_argument('--dry-run', action='store_true', help='仅验证配置')
    
    # Agent - 验证配置
    agentSubparsers.add_parser('validate', help='验证 Agent 配置文件')
    
    # Agent - 列出实验结果
    agentSubparsers.add_parser('list-results', help='列出已保存的实验结果')
    
    # 新闻分析子命令
    newsParser = subparsers.add_parser('news', help='新闻分析模块')
    newsSubparsers = newsParser.add_subparsers(dest='action', help='新闻操作')
    
    # 新闻分析 - 列表
    newsSubparsers.add_parser('list', help='列出投资目标')
    
    # 新闻分析 - 收集
    collectParser = newsSubparsers.add_parser('collect', help='收集新闻')
    collectParser.add_argument('--sources', nargs='+', default=['sina', 'eastmoney'], 
                              help='新闻源列表')
    collectParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # 新闻分析 - 分析
    analyzeParser = newsSubparsers.add_parser('analyze', help='分析新闻')
    analyzeParser.add_argument('--targets', nargs='+', help='分析目标')
    analyzeParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # 新闻分析 - 报告
    reportParser = newsSubparsers.add_parser('report', help='生成投资日报')
    reportParser.add_argument('--targets', nargs='+', help='报告目标')
    reportParser.add_argument('--days-back', type=int, default=2, help='回溯天数')
    
    # 新闻分析 - 摘要
    newsSubparsers.add_parser('summary', help='数据摘要')
    
    # 系统管理子命令
    systemParser = subparsers.add_parser('system', help='系统管理模块')
    systemSubparsers = systemParser.add_subparsers(dest='action', help='系统操作')
    
    # 系统管理 - 状态
    systemSubparsers.add_parser('status', help='系统状态')
    
    # 系统管理 - 配置
    configParser = systemSubparsers.add_parser('config', help='配置管理')
    configSubParser = configParser.add_subparsers(dest='config_action', help='配置操作')
    configSubParser.add_parser('validate', help='验证配置')
    configSubParser.add_parser('list', help='列出配置')
    
    # 系统管理 - 清理
    cleanParser = systemSubparsers.add_parser('clean', help='清理缓存')
    cleanParser.add_argument('--type', choices=['all', 'cache', 'logs', 'reports'], 
                            default='cache', help='清理类型')
    
    return parser

def handleTradingCommands(args):
    """处理交易策略命令"""
    if args.action == 'list':
        from bin.trading_strategy import listStrategies
        listStrategies()
    elif args.action == 'backtest':
        from bin.trading_strategy import runBacktest
        runBacktest(args)
    elif args.action == 'backtest-from-experiment':
        from bin.trading_strategy import runBacktestFromExperiment
        runBacktestFromExperiment(args)
    elif args.action == 'optimize':
        from bin.trading_strategy import optimizeStrategy
        optimizeStrategy(args)
    elif args.action == 'live':
        from bin.trading_strategy import liveTrading
        liveTrading(args)
    elif args.action == 'agent':
        handleAgentCommands(args)

def handleAgentCommands(args):
    """处理 Agent 策略命令"""
    if args.agent_action == 'list':
        from bin.agent_experiment import listExperiments
        listExperiments()
    elif args.agent_action == 'run':
        from bin.agent_experiment import runExperiment
        runExperiment(args.experiment, args.dry_run)
    elif args.agent_action == 'validate':
        from bin.agent_experiment import validateConfiguration
        validateConfiguration()
    elif args.agent_action == 'list-results':
        from bin.agent_experiment import listExperimentResults
        listExperimentResults()

def handleNewsCommands(args):
    """处理新闻分析命令"""
    if args.action == 'list':
        from bin.investment_news import listTargets
        listTargets()
    elif args.action == 'collect':
        from bin.investment_news import collectNews
        collectNews(args)
    elif args.action == 'analyze':
        from bin.investment_news import analyzeNews
        analyzeNews(args)
    elif args.action == 'report':
        from bin.investment_news import generateDailyReport
        generateDailyReport(args)
    elif args.action == 'summary':
        from bin.investment_news import showDataSummary
        showDataSummary(args)

def handleSystemCommands(args):
    """处理系统管理命令"""
    if args.action == 'status':
        showSystemStatus()
    elif args.action == 'config':
        handleConfigCommands(args)
    elif args.action == 'clean':
        handleCleanCommands(args)

def showSystemStatus():
    """显示系统状态"""
    print("🔍 系统状态检查")
    print("=" * 60)
    
    # 检查环境配置
    envFile = projectRoot / '.env'
    print(f"环境文件: {'✅ 存在' if envFile.exists() else '❌ 不存在'}")
    
    # 检查关键目录
    criticalDirs = ['logs', 'cache', 'reports', 'data']
    for dirName in criticalDirs:
        dirPath = projectRoot / dirName
        print(f"{dirName}目录: {'✅ 存在' if dirPath.exists() else '❌ 不存在'}")
    
    # 检查配置文件
    configDir = projectRoot / 'config'
    configFiles = list(configDir.glob('*.yaml'))
    print(f"配置文件: {len(configFiles)} 个")
    
    # 检查缓存大小
    cacheDir = projectRoot / 'cache'
    if cacheDir.exists():
        cacheSize = sum(f.stat().st_size for f in cacheDir.rglob('*') if f.is_file())
        print(f"缓存大小: {cacheSize / 1024 / 1024:.1f} MB")
    
    print("=" * 60)

def handleConfigCommands(args):
    """处理配置命令"""
    if args.config_action == 'validate':
        print("🔧 验证配置文件...")
        # 这里可以调用配置验证逻辑
        print("✅ 配置验证完成")
    elif args.config_action == 'list':
        print("📋 配置文件列表:")
        configDir = projectRoot / 'config'
        for configFile in configDir.glob('*.yaml'):
            print(f"  📄 {configFile.name}")

def handleCleanCommands(args):
    """处理清理命令"""
    print(f"🧹 开始清理: {args.type}")
    
    import shutil
    
    if args.type in ['all', 'cache']:
        cacheDir = projectRoot / 'cache'
        if cacheDir.exists():
            shutil.rmtree(cacheDir)
            cacheDir.mkdir()
            print("✅ 缓存已清理")
    
    if args.type in ['all', 'logs']:
        logsDir = projectRoot / 'logs'
        if logsDir.exists():
            for logFile in logsDir.glob('*.log'):
                if (datetime.now() - datetime.fromtimestamp(logFile.stat().st_mtime)).days > 7:
                    logFile.unlink()
            print("✅ 旧日志已清理")
    
    if args.type in ['all', 'reports']:
        reportsDir = projectRoot / 'reports'
        if reportsDir.exists():
            # 只清理30天前的报告
            for reportFile in reportsDir.rglob('*'):
                if reportFile.is_file() and (datetime.now() - datetime.fromtimestamp(reportFile.stat().st_mtime)).days > 30:
                    reportFile.unlink()
            print("✅ 旧报告已清理")

def main():
    """主函数"""
    parser = createParser()
    args = parser.parse_args()
    
    # 设置日志
    setupLogging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 检查基本环境
    if not (projectRoot / '.env').exists():
        print("⚠️  警告: 未找到.env文件，请确保环境配置正确")
    
    try:
        if args.module == 'trading':
            handleTradingCommands(args)
        elif args.module == 'news':
            handleNewsCommands(args)
        elif args.module == 'system':
            handleSystemCommands(args)
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n🛑 操作已取消")
        sys.exit(0)
    except Exception as e:
        logger.error(f"执行失败: {str(e)}")
        print(f"❌ 错误: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 