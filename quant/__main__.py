"""Quantitative Trading System CLI Entry Point

统一的命令行入口，支持：
- 新闻分析
- 交易策略分析
- 系统管理
"""

import sys
import argparse
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from quant.core.config_manager import ConfigManager
from quant.core.data_manager import DataManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description='Quantitative Trading System CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # News analysis
  python -m quant news analyze --targets nasdaq,gold --days 7
  python -m quant news collect --sources sina,eastmoney
  
  # Trading analysis  
  python -m quant trading analyze --symbol 002594.SZ --strategy grid
  python -m quant trading backtest --config config/trading.yaml
  
  # System management
  python -m quant config validate
  python -m quant cache clear
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # News analysis commands
    news_parser = subparsers.add_parser('news', help='News analysis commands')
    news_subparsers = news_parser.add_subparsers(dest='news_action', help='News actions')
    
    # News analyze
    news_analyze_parser = news_subparsers.add_parser('analyze', help='Analyze news data')
    news_analyze_parser.add_argument('--targets', type=str, default='nasdaq,gold,csi300', 
                                    help='Investment targets (comma separated)')
    news_analyze_parser.add_argument('--days', type=int, default=7, 
                                    help='Number of days to look back')
    news_analyze_parser.add_argument('--mode', type=str, choices=['simple', 'two_stage'], 
                                    default='simple', help='Analysis mode')
    news_analyze_parser.add_argument('--output', type=str, default='reports/', 
                                    help='Output directory')
    news_analyze_parser.add_argument('--format', type=str, choices=['json', 'markdown', 'html'], 
                                    default='json', help='Output format')
    
    # News collect
    news_collect_parser = news_subparsers.add_parser('collect', help='Collect news data')
    news_collect_parser.add_argument('--sources', type=str, default='sina,eastmoney', 
                                    help='News sources (comma separated)')
    news_collect_parser.add_argument('--days', type=int, default=3, 
                                    help='Number of days to collect')
    
    # Trading analysis commands
    trading_parser = subparsers.add_parser('trading', help='Trading analysis commands')
    trading_subparsers = trading_parser.add_subparsers(dest='trading_action', help='Trading actions')
    
    # Trading analyze
    trading_analyze_parser = trading_subparsers.add_parser('analyze', help='Analyze trading strategy')
    trading_analyze_parser.add_argument('--symbol', type=str, required=True, 
                                       help='Stock symbol to analyze')
    trading_analyze_parser.add_argument('--strategy', type=str, choices=['grid', 'dca', 'momentum'], 
                                       default='grid', help='Trading strategy')
    trading_analyze_parser.add_argument('--start-date', type=str, default='2023-01-01', 
                                       help='Start date for analysis')
    trading_analyze_parser.add_argument('--end-date', type=str, default='2024-01-01', 
                                       help='End date for analysis')
    
    # Trading backtest
    trading_backtest_parser = trading_subparsers.add_parser('backtest', help='Run strategy backtest')
    trading_backtest_parser.add_argument('--config', type=str, default='config/trading.yaml', 
                                        help='Trading configuration file')
    trading_backtest_parser.add_argument('--symbol', type=str, required=True, 
                                        help='Stock symbol to backtest')
    
    # Config management commands
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_subparsers = config_parser.add_subparsers(dest='config_action', help='Config actions')
    
    # Config validate
    config_validate_parser = config_subparsers.add_parser('validate', help='Validate configurations')
    config_validate_parser.add_argument('--config', type=str, help='Specific config to validate')
    
    # Config list
    config_list_parser = config_subparsers.add_parser('list', help='List available configurations')
    
    # Cache management commands
    cache_parser = subparsers.add_parser('cache', help='Cache management')
    cache_subparsers = cache_parser.add_subparsers(dest='cache_action', help='Cache actions')
    
    # Cache clear
    cache_clear_parser = cache_subparsers.add_parser('clear', help='Clear cache')
    cache_clear_parser.add_argument('--type', type=str, choices=['all', 'news', 'trading'], 
                                   default='all', help='Type of cache to clear')
    
    return parser


def handle_news_analyze(args):
    """Handle news analysis command"""
    try:
        logger.info(f"Starting news analysis for targets: {args.targets}")
        
        # Initialize managers
        config_manager = ConfigManager()
        data_manager = DataManager(config_manager)
        
        # Parse targets
        targets = [t.strip() for t in args.targets.split(',')]
        
        # Get news data
        logger.info(f"Collecting news data for last {args.days} days...")
        news_data = data_manager.get_news_data(days_back=args.days)
        
        if not news_data:
            logger.warning("No news data found")
            return
        
        logger.info(f"Found {len(news_data)} news articles")
        
        # For now, save the collected data as a simple report
        report_data = {
            "title": "News Analysis Report",
            "analysis_date": data_manager._standardize_timestamp(""),
            "targets": targets,
            "days_analyzed": args.days,
            "total_articles": len(news_data),
            "articles_summary": [
                {
                    "title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "timestamp": article.get("timestamp", "")
                } 
                for article in news_data[:10]  # Show first 10 articles
            ]
        }
        
        # Save report
        report_path = data_manager.save_report(
            report_data=report_data,
            report_type="news_analysis",
            target="multi_target",
            format_type=args.format
        )
        
        logger.info(f"News analysis completed. Report saved to: {report_path}")
        
    except Exception as e:
        logger.error(f"News analysis failed: {e}")
        sys.exit(1)


def handle_config_validate(args):
    """Handle configuration validation"""
    try:
        config_manager = ConfigManager()
        
        if args.config:
            # Validate specific config
            logger.info(f"Validating configuration: {args.config}")
            is_valid = config_manager.validate_config(args.config)
            if is_valid:
                logger.info(f"Configuration {args.config} is valid ✓")
            else:
                logger.error(f"Configuration {args.config} is invalid ✗")
                sys.exit(1)
        else:
            # Validate all configs
            logger.info("Validating all configurations...")
            configs = config_manager.list_available_configs()
            all_valid = True
            
            for config_name in configs:
                try:
                    is_valid = config_manager.validate_config(config_name)
                    status = "✓" if is_valid else "✗"
                    logger.info(f"  {config_name}: {status}")
                    if not is_valid:
                        all_valid = False
                except Exception as e:
                    logger.error(f"  {config_name}: Error - {e}")
                    all_valid = False
            
            if all_valid:
                logger.info("All configurations are valid ✓")
            else:
                logger.error("Some configurations are invalid ✗")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)


def handle_config_list(args):
    """Handle configuration listing"""
    try:
        config_manager = ConfigManager()
        configs = config_manager.list_available_configs()
        
        logger.info("Available configurations:")
        for config_name in configs:
            logger.info(f"  - {config_name}")
            
    except Exception as e:
        logger.error(f"Failed to list configurations: {e}")
        sys.exit(1)


def handle_cache_clear(args):
    """Handle cache clearing"""
    try:
        config_manager = ConfigManager()
        data_manager = DataManager(config_manager)
        
        logger.info(f"Clearing {args.type} cache...")
        
        if args.type in ['all', 'news']:
            # Clear news cache
            news_cache_dir = data_manager.cache_dir / "news_analysis"
            if news_cache_dir.exists():
                import shutil
                shutil.rmtree(news_cache_dir)
                news_cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info("News cache cleared")
        
        if args.type in ['all', 'trading']:
            # Clear trading cache
            trading_cache_dir = data_manager.cache_dir / "trading"
            if trading_cache_dir.exists():
                import shutil
                shutil.rmtree(trading_cache_dir)
                trading_cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Trading cache cleared")
        
        if args.type == 'all':
            # Clear configuration cache
            config_manager.clear_cache()
            logger.info("Configuration cache cleared")
        
        logger.info("Cache clearing completed ✓")
        
    except Exception as e:
        logger.error(f"Cache clearing failed: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        # Route to appropriate handler
        if args.command == 'news':
            if args.news_action == 'analyze':
                handle_news_analyze(args)
            elif args.news_action == 'collect':
                logger.info("News collection not implemented yet")
            else:
                logger.error("Unknown news action")
                sys.exit(1)
                
        elif args.command == 'trading':
            if args.trading_action == 'analyze':
                logger.info("Trading analysis not implemented yet")
            elif args.trading_action == 'backtest':
                logger.info("Trading backtest not implemented yet")
            else:
                logger.error("Unknown trading action")
                sys.exit(1)
                
        elif args.command == 'config':
            if args.config_action == 'validate':
                handle_config_validate(args)
            elif args.config_action == 'list':
                handle_config_list(args)
            else:
                logger.error("Unknown config action")
                sys.exit(1)
                
        elif args.command == 'cache':
            if args.cache_action == 'clear':
                handle_cache_clear(args)
            else:
                logger.error("Unknown cache action")
                sys.exit(1)
                
        else:
            logger.error("Unknown command")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main() 