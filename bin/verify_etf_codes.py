#!/usr/bin/env python3
"""
ETF/股票代码验证脚本
验证配置文件中所有证券代码的准确性，通过Tushare官方API交叉验证

Usage:
    python bin/verify_etf_codes.py --config config/screens.yaml
    python bin/verify_etf_codes.py --config config/portfolios.yaml --fix
"""

import os
import sys
import yaml
import argparse
import tushare as ts
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
from datetime import datetime

from quant.core.logging_config import get_logger
logger = get_logger(__name__)


# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class ETFCodeVerifier:
    """ETF/股票代码验证器"""

    def __init__(self):
        load_dotenv()
        token = os.getenv('TUSHARE_TOKEN')
        if not token:
            raise ValueError("未找到TUSHARE_TOKEN环境变量")

        ts.set_token(token)
        self.pro = ts.pro_api()
        self.errors = []
        self.warnings = []
        self.verified = []

    def verify_symbol(self, symbol: str, configured_name: str, skip_symbols: set = None) -> Tuple[bool, str, str]:
        """
        验证单个证券代码

        Returns:
            (is_valid, real_name, error_type)
            error_type: 'OK', 'NAME_MISMATCH', 'NOT_FOUND', 'SKIPPED'
        """
        if skip_symbols and symbol in skip_symbols:
            return True, configured_name, 'SKIPPED'

        try:
            # 先尝试ETF/基金
            fund_info = self.pro.fund_basic(ts_code=symbol, fields='ts_code,name,management')

            if fund_info is not None and len(fund_info) > 0:
                real_name = fund_info.iloc[0]['name']
                management = fund_info.iloc[0]['management']

                if configured_name != real_name:
                    return False, real_name, 'NAME_MISMATCH'
                return True, real_name, 'OK'

            # 再尝试股票
            stock_info = self.pro.stock_basic(ts_code=symbol, fields='ts_code,name')

            if stock_info is not None and len(stock_info) > 0:
                real_name = stock_info.iloc[0]['name']

                if configured_name != real_name:
                    return False, real_name, 'NAME_MISMATCH'
                return True, real_name, 'OK'

            return False, 'NOT_FOUND', 'NOT_FOUND'

        except Exception as e:
            return False, f'ERROR: {str(e)}', 'ERROR'

    def verify_screens_yaml(self, config_path: str) -> Dict:
        """验证screens.yaml配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        screens = config.get('screens', {})
        skip_symbols = {'CASH', 'IXIC', 'HKTECH', 'NDX', 'SPX', 'SP500', 'DJI', 'HSI'}

        results = {}

        for screen_name, holdings in screens.items():
            screen_results = {
                'total': len(holdings),
                'errors': [],
                'warnings': [],
                'verified': []
            }

            for symbol, info in holdings.items():
                name = info.get('name', 'N/A')
                is_valid, real_name, error_type = self.verify_symbol(symbol, name, skip_symbols)

                if error_type == 'SKIPPED':
                    screen_results['verified'].append({
                        'symbol': symbol,
                        'name': name,
                        'status': 'SKIPPED'
                    })
                elif error_type == 'OK':
                    screen_results['verified'].append({
                        'symbol': symbol,
                        'name': name,
                        'status': 'OK'
                    })
                elif error_type == 'NAME_MISMATCH':
                    screen_results['errors'].append({
                        'symbol': symbol,
                        'configured_name': name,
                        'real_name': real_name,
                        'error_type': 'NAME_MISMATCH'
                    })
                elif error_type == 'NOT_FOUND':
                    screen_results['errors'].append({
                        'symbol': symbol,
                        'configured_name': name,
                        'real_name': 'NOT_FOUND',
                        'error_type': 'NOT_FOUND'
                    })

            results[screen_name] = screen_results

        return results

    def verify_portfolios_yaml(self, config_path: str) -> Dict:
        """验证portfolios.yaml配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        portfolios = config.get('portfolios', {})
        skip_symbols = {'CASH', 'IXIC', 'HKTECH', 'NDX', 'SPX', 'SP500', 'DJI', 'HSI'}

        results = {}

        for portfolio_name, holdings in portfolios.items():
            portfolio_results = {
                'total': len(holdings),
                'errors': [],
                'warnings': [],
                'verified': []
            }

            for symbol, info in holdings.items():
                name = info.get('name', 'N/A')
                is_valid, real_name, error_type = self.verify_symbol(symbol, name, skip_symbols)

                if error_type == 'SKIPPED':
                    portfolio_results['verified'].append({
                        'symbol': symbol,
                        'name': name,
                        'status': 'SKIPPED'
                    })
                elif error_type == 'OK':
                    portfolio_results['verified'].append({
                        'symbol': symbol,
                        'name': name,
                        'status': 'OK'
                    })
                elif error_type == 'NAME_MISMATCH':
                    portfolio_results['errors'].append({
                        'symbol': symbol,
                        'configured_name': name,
                        'real_name': real_name,
                        'error_type': 'NAME_MISMATCH'
                    })
                elif error_type == 'NOT_FOUND':
                    portfolio_results['errors'].append({
                        'symbol': symbol,
                        'configured_name': name,
                        'real_name': 'NOT_FOUND',
                        'error_type': 'NOT_FOUND'
                    })

            results[portfolio_name] = portfolio_results

        return results

    def print_verification_report(self, results: Dict, config_name: str):
        """打印验证报告"""
        print('=' * 100)
        logger.info("ETF/股票代码验证报告 - {config_name}")
        logger.info("验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print('=' * 100)

        total_items = 0
        total_errors = 0
        total_verified = 0

        for section_name, section_results in results.items():
            total_items += section_results['total']
            total_errors += len(section_results['errors'])
            total_verified += len(section_results['verified'])

            logger.info("【{section_name}】")
            logger.info("总数: {section_results['total']}")
            logger.info("验证通过: {len(section_results['verified'])}")
            logger.info("错误: {len(section_results['errors'])}")

            if section_results['errors']:
                logger.info("\n  ❌ 发现错误:")
                for error in section_results['errors']:
                    if error['error_type'] == 'NAME_MISMATCH':
                        logger.info("{error['symbol']}: \"{error['configured_name']}\" → \"{error['real_name']}\"")
                    elif error['error_type'] == 'NOT_FOUND':
                        logger.info("{error['symbol']}: 未找到数据 (配置名称: {error['configured_name']})")

        print('\n' + '=' * 100)
        logger.info("总计: {total_items}个代码, {total_verified}个通过, {total_errors}个错误")
        logger.info("错误率: {total_errors/total_items*100:.1f}%" if total_items > 0 else "错误率: N/A")
        print('=' * 100)

        return total_errors

    def generate_fix_suggestions(self, results: Dict, config_name: str) -> List[Dict]:
        """生成修正建议"""
        suggestions = []

        for section_name, section_results in results.items():
            for error in section_results['errors']:
                if error['error_type'] == 'NAME_MISMATCH':
                    suggestions.append({
                        'section': section_name,
                        'symbol': error['symbol'],
                        'action': 'UPDATE_NAME',
                        'old_name': error['configured_name'],
                        'new_name': error['real_name']
                    })
                elif error['error_type'] == 'NOT_FOUND':
                    suggestions.append({
                        'section': section_name,
                        'symbol': error['symbol'],
                        'action': 'REMOVE_OR_REPLACE',
                        'old_name': error['configured_name'],
                        'reason': '代码不存在'
                    })

        return suggestions

    def save_verification_report(self, results: Dict, config_name: str, output_path: str):
        """保存验证报告到文件"""
        report = {
            'verification_time': datetime.now().isoformat(),
            'config_file': config_name,
            'results': results,
            'suggestions': self.generate_fix_suggestions(results, config_name)
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(report, f, allow_unicode=True, default_flow_style=False)

        logger.info("\n✅ 验证报告已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='ETF/股票代码验证工具')
    parser.add_argument('--config', required=True, help='配置文件路径 (screens.yaml或portfolios.yaml)')
    parser.add_argument('--output', help='验证报告输出路径')
    parser.add_argument('--fix', action='store_true', help='自动修正错误（暂未实现）')

    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.info("❌ 配置文件不存在: {config_path}")
        sys.exit(1)

    verifier = ETFCodeVerifier()

    # 根据配置文件类型选择验证方法
    if 'screens' in config_path.name:
        results = verifier.verify_screens_yaml(str(config_path))
    elif 'portfolios' in config_path.name:
        results = verifier.verify_portfolios_yaml(str(config_path))
    else:
        logger.info("❌ 不支持的配置文件类型: {config_path.name}")
        sys.exit(1)

    # 打印报告
    error_count = verifier.print_verification_report(results, config_path.name)

    # 保存报告
    if args.output:
        output_path = args.output
    else:
        output_path = f'config/verification_{config_path.stem}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml'

    verifier.save_verification_report(results, str(config_path), output_path)

    # 返回错误码
    sys.exit(1 if error_count > 0 else 0)


if __name__ == '__main__':
    main()
