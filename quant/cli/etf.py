#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ETF 相关命令

包括ETF筛选、估值分析等功能
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple
import yaml
import logging

logger = logging.getLogger(__name__)


def register_etf_commands(subparsers):
    """注册ETF相关命令"""
    etf_parser = subparsers.add_parser('etf', help='ETF筛选与分析')
    etf_subparsers = etf_parser.add_subparsers(dest='etf_action', help='ETF操作')
    
    # screen 命令
    screen_parser = etf_subparsers.add_parser('screen', help='筛选ETF')
    screen_parser.add_argument('--types', nargs='+', 
                              choices=['broad_market', 'sector', 'thematic', 'bonds', 'commodities', 'international'],
                              help='ETF类型')
    screen_parser.add_argument('--max-etfs', type=int, help='最大分析数量')
    screen_parser.add_argument('--save', action='store_true', help='保存结果')
    screen_parser.add_argument('--from-config', dest='config_name', help='从配置文件加载ETF列表')
    
    # single 命令
    single_parser = etf_subparsers.add_parser('single', help='分析单只ETF')
    single_parser.add_argument('symbol', help='ETF代码，如 510300.SH')
    single_parser.add_argument('--valuation', action='store_true', default=True, help='包含估值分析')
    
    # config 命令
    config_parser = etf_subparsers.add_parser('config', help='配置管理')
    config_parser.add_argument('--show', action='store_true', help='显示筛选配置')
    config_parser.add_argument('--list', action='store_true', dest='list_screens', help='列出配置中的ETF篮子')
    
    return etf_parser


def handle_etf_screen(args):
    """处理ETF筛选命令"""
    from quant.analysis.screener.etf_screener import ETFMomentumScreener
    from quant.analysis.screener.etf_report_generator import ETFReportGenerator
    from datetime import datetime
    
    screener = ETFMomentumScreener()
    
    # 从配置文件加载
    if args.config_name:
        print(f"\n🚀 从配置篮子筛选ETF: {args.config_name}")
        print("=" * 80)
        
        try:
            symbols, info_map = load_symbols_from_config(args.config_name)
            
            if args.max_etfs:
                print(f"分析数量限制: {args.max_etfs}")
            print(f"标的数量: {len(symbols)}")
            print("\n正在筛选中（包含估值分析），请耐心等待...\n")
            
            results = screener.screen_symbols(
                symbols, 
                info_map=info_map, 
                max_etfs=args.max_etfs,
                default_category=args.config_name
            )
            
            screener.print_screening_results(results)
            
            if args.save and not results.empty:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                # 保存CSV
                output_file = screener.report_dir / f"etf_screening_{args.config_name}_{timestamp}.csv"
                results.to_csv(output_file, index=False, encoding='utf-8-sig')
                print(f"\n💾 CSV结果已保存到: {output_file}")
                
                # 生成报告
                try:
                    report_generator = ETFReportGenerator(output_dir=str(screener.report_dir))
                    report_path = report_generator.generate_and_save_report(
                        results,
                        report_title=f"{args.config_name} ETF动量与估值筛选报告",
                        prefix=f"etf_screening_{args.config_name}",
                        include_valuation=True
                    )
                    print(f"📄 详细报告已保存到: {report_path}")
                except Exception as e:
                    print(f"⚠️ 报告生成失败: {e}")
        
        except Exception as e:
            print(f"❌ 读取配置失败: {e}")
            sys.exit(1)
    
    # 批量筛选
    else:
        print(f"\n🚀 批量筛选ETF（包含估值分析）")
        print("=" * 80)
        
        if args.types:
            print(f"ETF类型: {', '.join(args.types)}")
        else:
            print("ETF类型: 所有类型")
        
        if args.max_etfs:
            print(f"分析数量限制: {args.max_etfs}")
        
        print("\n正在筛选中（包含估值分析），请耐心等待...\n")
        
        results = screener.screen_etfs(args.types, args.max_etfs)
        
        screener.print_screening_results(results)
        
        if args.save and not results.empty:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 保存CSV
            output_file = screener.report_dir / f"etf_screening_{timestamp}.csv"
            results.to_csv(output_file, index=False, encoding='utf-8-sig')
            print(f"\n💾 CSV结果已保存到: {output_file}")
            
            # 生成报告
            try:
                report_generator = ETFReportGenerator(output_dir=str(screener.report_dir))
                report_path = report_generator.generate_and_save_report(
                    results,
                    report_title="ETF动量与估值筛选分析报告",
                    prefix="etf_screening",
                    include_valuation=True
                )
                print(f"📄 详细报告已保存到: {report_path}")
            except Exception as e:
                print(f"⚠️ 报告生成失败: {e}")


def handle_etf_single(args):
    """处理单只ETF分析命令"""
    from quant.analysis.screener.etf_screener import ETFMomentumScreener
    from quant.analysis.etf_valuation_analyzer import ETFValuationAnalyzer
    
    screener = ETFMomentumScreener()
    
    print(f"\n📊 分析ETF: {args.symbol}")
    print("=" * 80)
    
    result = screener.analyze_etf(args.symbol, include_valuation=args.valuation)
    
    if not result['success']:
        print(f"❌ 分析失败: {result.get('error', '未知错误')}")
        return
    
    # 显示基本信息
    print(f"\n📈 基本信息:")
    print(f"  代码: {args.symbol}")
    print(f"  数据点数: {result['data_points']}")
    print(f"  分析日期: {result['analysis_date']}")
    
    # 显示动量指标
    momentum = result['momentum']
    print(f"\n📊 动量指标:")
    print(f"  1月收益率: {momentum.get('1month_return', 0):.2f}%")
    print(f"  3月收益率: {momentum.get('3month_return', 0):.2f}%")
    print(f"  6月收益率: {momentum.get('6month_return', 0):.2f}%")
    print(f"  12月收益率: {momentum.get('12month_return', 0):.2f}%")
    print(f"  RSI: {momentum.get('rsi', 50):.1f}")
    print(f"  MACD: {momentum.get('macd', 0):.4f}")
    
    # 显示估值信息
    if args.valuation and 'valuation' in result:
        valuation = result['valuation']
        print(f"\n💎 估值分析:")
        print(f"  估值水平: {valuation.get('valuation_level', '合理')}")
        print(f"  价格分位数: {valuation.get('percentile', 50):.1f}%")
        print(f"  估值区间: {valuation.get('valuation_zone', '合理区')}")
        print(f"  均值回归信号: {valuation.get('mean_reversion_signal', '持有')}")
        print(f"  布林带位置: {valuation.get('bollinger_position', 50):.1f}%")
    
    # 显示筛选结果
    screening = result['screening_result']
    print(f"\n🎯 筛选结果:")
    print(f"  动量得分: {screening['momentum']['score']:.3f}/1.000 {'✅' if screening['momentum']['passes'] else '❌'}")
    print(f"  综合得分: {screening['overall']['score']:.3f}/1.000")
    print(f"  评级: {screening['overall']['grade']}")
    print(f"  是否通过: {'✅ 通过筛选' if screening['overall']['passes'] else '❌ 未通过筛选'}")
    
    if 'valuation_adjustment' in screening['overall']:
        adj = screening['overall']['valuation_adjustment']
        if adj != 0:
            print(f"  估值调整: {adj:+.2f}")


def handle_etf_config(args):
    """处理ETF配置命令"""
    from quant.analysis.screener.etf_screener import ETFMomentumScreener
    
    screener = ETFMomentumScreener()
    
    if args.show:
        # 显示筛选配置
        config = screener.screening_config
        
        print("\n📋 ETF筛选配置")
        print("=" * 80)
        
        print("\n🎯 动量指标阈值:")
        momentum = config['momentum']
        print(f"  • 1月收益率 >= {momentum['1month_return_min']:.1f}%")
        print(f"  • 3月收益率 >= {momentum['3month_return_min']:.1f}%")
        print(f"  • 6月收益率 >= {momentum['6month_return_min']:.1f}%")
        print(f"  • 12月收益率 >= {momentum['12month_return_min']:.1f}%")
        print(f"  • RSI: {momentum['rsi_min']:.0f} - {momentum['rsi_max']:.0f}")
        print(f"  • MACD信号: {momentum['macd_signal']}")
        
        print("\n📊 估值调整机制:")
        print("  • 极度高估: -0.20 分")
        print("  • 高估: -0.10 分")
        print("  • 极度低估: +0.15 分")
        print("  • 低估: +0.10 分")
        print()
    
    if args.list_screens:
        # 列出配置篮子
        print("\n📋 可用的ETF配置篮子")
        print("=" * 80)
        
        try:
            config_path = Path('config') / 'screens.yaml'
            if not config_path.exists():
                print("❌ 配置文件不存在: config/screens.yaml")
                return
            
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            
            screens = data.get('screens', {})
            
            if not screens:
                print("未找到配置篮子")
                return
            
            for screen_name, entries in screens.items():
                count = len(entries) if entries else 0
                print(f"\n📦 {screen_name} ({count} 只)")
                
                if entries and count <= 10:
                    for code, meta in list(entries.items())[:10]:
                        name = (meta or {}).get('name', '')
                        sector = (meta or {}).get('sector', '')
                        print(f"  • {code}: {name} ({sector})")
                elif count > 10:
                    print(f"  （{count} 只标的，使用 --from-config {screen_name} 查看详情）")
        
        except Exception as e:
            print(f"❌ 读取配置失败: {e}")


def load_symbols_from_config(screen_name: str) -> Tuple[List[str], Dict[str, Dict[str, str]]]:
    """从配置文件加载ETF列表"""
    config_path = Path('config') / 'screens.yaml'
    if not config_path.exists():
        raise FileNotFoundError("配置文件不存在: config/screens.yaml")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    
    screens = data.get('screens') or {}
    if screen_name not in screens:
        raise KeyError(f"配置中不存在篮子 '{screen_name}'")
    
    entries: Dict[str, Dict[str, str]] = screens[screen_name] or {}
    symbols: List[str] = list(entries.keys())
    info_map: Dict[str, Dict[str, str]] = {}
    
    for code, meta in entries.items():
        name = (meta or {}).get('name', '')
        category = (meta or {}).get('sector') or screen_name
        info_map[code] = {'name': name, 'category': category}
    
    return symbols, info_map


def handle_etf_command(args):
    """ETF命令总入口"""
    if args.etf_action == 'screen':
        handle_etf_screen(args)
    elif args.etf_action == 'single':
        handle_etf_single(args)
    elif args.etf_action == 'config':
        handle_etf_config(args)
    else:
        print("❌ 未知的ETF操作")
        sys.exit(1)

