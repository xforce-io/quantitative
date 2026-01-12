#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一投资顾问入口 (Unified Investment Advisor)

整合 Smart Advisor 和 Investment Advisor 的功能，提供统一的分析接口

使用方式:
  # 单标的深度分析
  python advisor.py --mode single --symbol 002049.SZ
  
  # 投资组合策略分析  
  python advisor.py --mode portfolio --symbols 002049.SZ,300661.SZ,603501.SH
  
  # 综合分析（深度分析+策略回测）
  python advisor.py --mode comprehensive --symbol 002049.SZ
  
  # 快速批量分析
  python advisor.py --mode batch --symbols-file semiconductor_stocks.txt
"""

import sys
import argparse
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 导入两个advisor
from quant.analysis.advisor.investment_advisor import InvestmentAdvisor
from analyst.etf_capital_flow_analyzer import ETFCapitalFlowAnalyzer
from analyst.etf_flow_simplified import SimplifiedETFFlowAnalyzer
from analyst.portfolios import portfolio_manager, PortfolioManager, SymbolInfo
from analyst.screens import screen_manager


class UnifiedAdvisor:
    """统一投资顾问 - 整合单标的深度分析和多标的策略分析"""
    
    def __init__(self, use_cache: bool = True, enable_fundamental: bool = True):
        self.use_cache = use_cache
        self.enable_fundamental = enable_fundamental
        self.results = {}
        self.project_root = Path(__file__).parent.parent
        self.portfolio_manager = portfolio_manager
    
    def analyze_single(self, symbol: str, days_back: int = 2500, **kwargs) -> Dict[str, Any]:
        """
        单标的深度分析 - 使用Smart Advisor
        
        Args:
            symbol: 股票代码
            days_back: 历史数据天数
            **kwargs: 其他参数
            
        Returns:
            分析结果字典
        """
        logger.info("\n🎯 单标的深度分析模式")
        logger.info("📊 标的: {symbol}")
        print("=" * 60)
        
        try:
            advisor = SmartAdvisor(
                symbol=symbol, 
                days_back=days_back,
                enable_fundamental=self.enable_fundamental
            )
            
            # 获取分析结果（不直接打印）
            advisor.analyze()
            
            # 基础数据校验：若数据缺失或明显不足，则判定为失败，避免误报成功
            try:
                data_len = len(advisor.data) if getattr(advisor, 'data', None) is not None else 0
            except Exception:
                data_len = 0
            if data_len < 200:
                error_msg = (
                    f"数据获取失败或数据不足(实际 {data_len} 天，至少需要 200 天)"
                )
                error_result = {
                    'symbol': symbol,
                    'mode': 'single',
                    'analysis_time': datetime.now().isoformat(),
                    'error': error_msg,
                    'success': False
                }
                self.results[symbol] = error_result
                logger.info("❌ 分析失败: {error_msg}")
                return error_result
            
            # 构造返回结果
            result = {
                'symbol': symbol,
                'mode': 'single',
                'analysis_time': datetime.now().isoformat(),
                'position_analysis': advisor.position_analysis,
                'fundamental_analysis': advisor.fundamental_analysis,
                'risk_analysis': {
                    'risk_score': advisor.risk_score,
                    'risk_level': advisor.risk_level,
                    'risk_details': advisor.risk_details
                },
                'probability_analysis': advisor.probability_analysis,
                'recommendation': advisor.recommendation,
                'action_details': advisor.action_details,
                'success': True
            }
            
            self.results[symbol] = result
            return result
            
        except Exception as e:
            error_result = {
                'symbol': symbol,
                'mode': 'single', 
                'analysis_time': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }
            self.results[symbol] = error_result
            logger.info("❌ 分析失败: {e}")
            return error_result
    
    def analyze_portfolio(self, symbols: List[str] = None, portfolio_name: str = 'CUSTOM', weights: Optional[Dict[str, float]] = None, use_sleeves: bool = False, **kwargs) -> Dict[str, Any]:
        """
        投资组合策略分析 - 使用Investment Advisor

        Args:
            symbols: 股票代码列表，如果为空则使用预定义组合
            portfolio_name: 组合名称
            weights: 自定义权重
            use_sleeves: 是否使用sleeve配置
            **kwargs: 其他参数

        Returns:
            组合分析结果
        """
        # 如果没有提供标的，尝试使用预定义组合
        if not symbols:
            try:
                portfolio = self.portfolio_manager.get_portfolio(portfolio_name)
                symbols = list(portfolio.keys())
                portfolio_meta = self.portfolio_manager.get_portfolio_meta(portfolio_name)
                logger.info("📚 使用预定义组合: {portfolio_name}")
                logger.info("📝 组合描述: {portfolio_meta.get('description', '未知')}")
                logger.info("⚠️ 风险等级: {portfolio_meta.get('risk_level', '未知')}")
                logger.info("🎯 适合人群: {portfolio_meta.get('suitable_for', '未知')}")

                # 检查并显示sleeve配置
                sleeves = self.portfolio_manager.get_sleeves(portfolio_name)
                if sleeves and use_sleeves:
                    logger.info("\n📊 使用Sleeve配置:")
                    for sleeve in sleeves:
                        logger.info("  • {sleeve.name} ({sleeve.risk_level}): {sleeve.allocation_ratio:.1%} 配置, 目标收益 {sleeve.target_return:.1%}")
                    # 使用sleeve配置的权重
                    weights = self.portfolio_manager.get_weights(portfolio_name, use_sleeves=True)

            except ValueError as e:
                available_portfolios = self.portfolio_manager.list_portfolios()
                logger.info("❌ {e}")
                logger.info("📊 可用组合: {', '.join(available_portfolios)}")
                return {'error': str(e), 'available_portfolios': available_portfolios, 'success': False}
        
        logger.info("\n📈 投资组合策略分析模式")
        logger.info("📊 标的数量: {len(symbols)}")
        logger.info("📝 组合名称: {portfolio_name}")
        print("=" * 60)
        
        try:
            # 从 kwargs中移除InvestmentAdvisor不支持的参数
            advisor_kwargs = {k: v for k, v in kwargs.items() if k not in ['current_days']}
            advisor = InvestmentAdvisor(
                symbols=symbols,
                use_cache=self.use_cache,
                portfolio=portfolio_name,
                **advisor_kwargs
            )
            
            # 执行当前信号分析
            results = advisor.analyze_current_signals_only(
                symbols=symbols, 
                current_days=kwargs.get('current_days', 300)
            )
            
            portfolio_result = {
                'symbols': symbols,
                'mode': 'portfolio',
                'analysis_time': datetime.now().isoformat(),
                'portfolio_name': portfolio_name,
                'results': results,
                'summary': self._generate_portfolio_summary(results, portfolio_name, weights=weights),
                'success': True
            }
            
            self.results[f'portfolio_{portfolio_name}'] = portfolio_result
            return portfolio_result
            
        except Exception as e:
            error_result = {
                'symbols': symbols,
                'mode': 'portfolio',
                'analysis_time': datetime.now().isoformat(),
                'portfolio_name': portfolio_name,
                'error': str(e),
                'success': False
            }
            logger.info("❌ 组合分析失败: {e}")
            return error_result
    
    def analyze_comprehensive(self, symbol: str, periods: tuple = ("3Y", "5Y"), **kwargs) -> Dict[str, Any]:
        """
        综合分析模式 - 结合深度分析和策略回测
        
        Args:
            symbol: 股票代码
            periods: 回测周期
            **kwargs: 其他参数
            
        Returns:
            综合分析结果
        """
        logger.info("\n🔍 综合分析模式")
        logger.info("📊 标的: {symbol}")
        logger.info("📈 回测周期: {periods}")
        print("=" * 60)
        
        try:
            # 1. 深度分析
            single_result = self.analyze_single(symbol, **kwargs)
            
            # 2. ETF资金流分析（如果是ETF）
            etf_flow_result = None
            if self._is_etf(symbol) and single_result.get('success'):
                logger.info("\n📊 执行ETF资金流分析...")
                try:
                    # 优先使用简化版分析器（基于已有日线数据）
                    simplified_analyzer = SimplifiedETFFlowAnalyzer()
                    
                    # 从 SmartAdvisor 的结果中获取数据
                    advisor = SmartAdvisor(symbol=symbol, days_back=kwargs.get('days_back', 2500))
                    advisor.fetch_data()
                    
                    if advisor.data is not None and len(advisor.data) > 20:
                        etf_flow_result = simplified_analyzer.analyze_etf_flow_from_daily(advisor.data, symbol)
                        
                        if 'error' not in etf_flow_result:
                            logger.info("✅ ETF资金流分析完成 - 综合评分: {etf_flow_result['comprehensive_score']}/100")
                        else:
                            logger.info("⚠️ ETF资金流分析数据不足: {etf_flow_result['error']}")
                    else:
                        logger.info("⚠️ 无法获取{symbol}的日线数据")
                        etf_flow_result = {'error': '无法获取日线数据'}
                        
                except Exception as etf_e:
                    logger.info("⚠️ ETF资金流分析异常: {etf_e}")
                    etf_flow_result = {'error': str(etf_e)}
            
            # 3. 策略分析
            logger.info("\n📈 执行策略回测分析...")
            advisor = InvestmentAdvisor(symbols=[symbol], use_cache=self.use_cache)
            strategy_result = advisor.analyze_multi_period_and_current(
                symbols=[symbol],
                periods=periods,
                current_days=kwargs.get('current_days', 300)
            )
            
            # 4. 合并结果
            comprehensive_result = {
                'symbol': symbol,
                'mode': 'comprehensive', 
                'analysis_time': datetime.now().isoformat(),
                'single_analysis': single_result,
                'strategy_analysis': strategy_result.get(symbol, {}),
                'etf_flow_analysis': etf_flow_result,
                'consolidated_recommendation': self._generate_consolidated_recommendation(
                    single_result, strategy_result.get(symbol, {}), etf_flow_result
                ),
                'success': True
            }
            
            self.results[f'comprehensive_{symbol}'] = comprehensive_result
            return comprehensive_result
            
        except Exception as e:
            error_result = {
                'symbol': symbol,
                'mode': 'comprehensive',
                'analysis_time': datetime.now().isoformat(), 
                'error': str(e),
                'success': False
            }
            logger.info("❌ 综合分析失败: {e}")
            return error_result
    
    def analyze_all_portfolios(self, analysis_mode: str = 'portfolio', **kwargs) -> Dict[str, Any]:
        """
        分析所有预定义投资组合 - 生成完整的投资分析报告
        
        Args:
            analysis_mode: 'portfolio' 或 'comprehensive'
            **kwargs: 其他分析参数
            
        Returns:
            所有组合的分析结果
        """
        logger.info("\n🌟 全组合批量分析模式")
        logger.info("🔧 分析模式: {analysis_mode}")
        available_portfolios = self.portfolio_manager.list_portfolios()
        logger.info("📊 组合数量: {len(available_portfolios)}")
        print("=" * 80)
        
        all_results = {}
        successful_count = 0
        failed_count = 0
        
        for i, portfolio_name in enumerate(available_portfolios, 1):
            logger.info("\n🔄 进度: {i}/{len(available_portfolios)} - 分析组合: {portfolio_name}")
            print("-" * 60)
            
            try:
                if analysis_mode == 'portfolio':
                    result = self.analyze_portfolio(
                        symbols=None, 
                        portfolio_name=portfolio_name, 
                        **kwargs
                    )
                elif analysis_mode == 'comprehensive':
                    # 对组合中的每个标的做综合分析
                    portfolio = self.portfolio_manager.get_portfolio(portfolio_name)
                    portfolio_symbols = list(portfolio.keys())
                    
                    portfolio_comprehensive = {
                        'portfolio_name': portfolio_name,
                        'mode': 'comprehensive_portfolio',
                        'analysis_time': datetime.now().isoformat(),
                        'symbols_analysis': {},
                        'portfolio_summary': {}
                    }
                    
                    # 分析组合中的每个标的
                    for j, symbol in enumerate(portfolio_symbols[:5]):  # 限制前5个标的避免太长
                        logger.info("  🎯 分析标的 {j+1}/{min(5, len(portfolio_symbols))}: {symbol}")
                        symbol_result = self.analyze_comprehensive(symbol, **kwargs)
                        portfolio_comprehensive['symbols_analysis'][symbol] = symbol_result
                    
                    # 生成组合级汇总
                    portfolio_comprehensive['portfolio_summary'] = self._generate_comprehensive_portfolio_summary(
                        portfolio_comprehensive['symbols_analysis'], portfolio_name
                    )
                    
                    result = portfolio_comprehensive
                else:
                    result = self.analyze_portfolio(
                        symbols=None, 
                        portfolio_name=portfolio_name, 
                        **kwargs
                    )
                
                all_results[portfolio_name] = result
                if result.get('success', True):
                    successful_count += 1
                    logger.info("✅ {portfolio_name} 分析完成")
                else:
                    failed_count += 1
                    logger.info("❌ {portfolio_name} 分析失败")
                    
            except Exception as e:
                failed_count += 1
                error_result = {
                    'portfolio_name': portfolio_name,
                    'mode': f'{analysis_mode}_portfolio_batch',
                    'analysis_time': datetime.now().isoformat(),
                    'error': str(e),
                    'success': False
                }
                all_results[portfolio_name] = error_result
                logger.info("❌ {portfolio_name} 分析异常: {e}")
        
        # 生成全局汇总报告
        global_summary = {
            'mode': 'all_portfolios_analysis',
            'analysis_mode': analysis_mode,
            'analysis_time': datetime.now().isoformat(),
            'total_portfolios': len(available_portfolios),
            'successful_portfolios': successful_count,
            'failed_portfolios': failed_count,
            'success_rate': f'{successful_count/len(available_portfolios)*100:.1f}%',
            'portfolios_results': all_results,
            'global_insights': self._generate_global_portfolio_insights(all_results),
            'recommended_allocation': self._generate_allocation_recommendation(all_results)
        }
        
        self.results['all_portfolios_analysis'] = global_summary
        
        # 打印汇总
        print(f"\n" + "=" * 80)
        logger.info("📋 全组合分析完成汇总")
        logger.info("📊 总组合数: {len(available_portfolios)}")
        logger.info("✅ 成功: {successful_count}")
        logger.info("❌ 失败: {failed_count}")
        logger.info("📈 成功率: {successful_count/len(available_portfolios)*100:.1f}%")
        
        if global_summary['global_insights']:
            insights = global_summary['global_insights']
            logger.info("\n🎯 全局洞察:")
            if insights.get('top_performing_portfolios'):
                logger.info("🏆 表现最佳组合: {', '.join([p['name'] for p in insights['top_performing_portfolios'][:3]])}")
            if insights.get('sector_distribution'):
                logger.info("📊 行业分布: {insights['sector_distribution']}")
        
        return global_summary

    def batch_analyze(self, symbols: List[str], mode: str = 'single', **kwargs) -> Dict[str, Any]:
        """
        批量分析模式
        
        Args:
            symbols: 股票代码列表
            mode: 分析模式 ('single' 或 'portfolio')
            **kwargs: 其他参数
            
        Returns:
            批量分析结果
        """
        logger.info("\n⚡ 批量分析模式")
        logger.info("📊 标的数量: {len(symbols)}")
        logger.info("🔧 分析模式: {mode}")
        print("=" * 60)
        
        batch_results = {}
        
        if mode == 'single':
            # 逐一深度分析
            for i, symbol in enumerate(symbols, 1):
                logger.info("\n🔄 进度: {i}/{len(symbols)} - {symbol}")
                result = self.analyze_single(symbol, **kwargs)
                batch_results[symbol] = result
                
        elif mode == 'portfolio':
            # 作为组合分析
            result = self.analyze_portfolio(symbols, portfolio_name='BATCH', **kwargs)
            batch_results['portfolio'] = result
        
        # 生成批量汇总
        batch_summary = {
            'mode': 'batch',
            'sub_mode': mode,
            'symbols': symbols,
            'analysis_time': datetime.now().isoformat(),
            'total_count': len(symbols),
            'success_count': sum(1 for r in batch_results.values() if r.get('success', False)),
            'results': batch_results,
            'summary': self._generate_batch_summary(batch_results, mode)
        }
        
        self.results['batch_analysis'] = batch_summary
        return batch_summary
    
    def _generate_portfolio_summary(self, results: Dict[str, Any], portfolio_name: Optional[str] = None, weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """生成投资组合汇总（支持权重聚合和sleeve分析）"""
        if not results:
            return {'message': '无有效分析结果'}

        summary = {
            'total_symbols': len(results),
            'recommendations': {},
            'weighted_recommendations': {},
            'risk_distribution': {},
            'top_picks': [],
            'top_picks_weighted': [],
            'portfolio_weighted_score': None,
            'weights_used': False,
            'sleeve_analysis': None
        }
        # 取权重
        w_map = weights
        if w_map is None and portfolio_name:
            try:
                from analyst.portfolios import portfolio_manager
                w_map = portfolio_manager.get_weights(portfolio_name)
            except Exception:
                w_map = None
        if w_map is None:
            # 等权作为回退
            symbols = list(results.keys())
            if symbols:
                eq = 1.0 / len(symbols)
                w_map = {s: eq for s in symbols}
        else:
            summary['weights_used'] = True

        # 统计建议分布
        for symbol, data in results.items():
            if 'current_signal' in data:
                action = data['current_signal'].get('action', '观望')
                summary['recommendations'][action] = summary['recommendations'].get(action, 0) + 1
                w = float(w_map.get(symbol, 0.0))
                summary['weighted_recommendations'][action] = summary['weighted_recommendations'].get(action, 0.0) + w
        
        # 找出评分最高的标的
        scored_symbols = []
        for symbol, data in results.items():
            if 'current_signal' in data:
                score = data['current_signal'].get('combined_score', 0)
                scored_symbols.append((symbol, score, data.get('name', symbol)))
        
        # 按评分排序，取前3
        scored_symbols.sort(key=lambda x: x[1], reverse=True)
        summary['top_picks'] = scored_symbols[:3]
        # 加权Top picks（按score*weight排序）
        weighted_scores = []
        total_weighted = 0.0
        for symbol, score, name in scored_symbols:
            w = float(w_map.get(symbol, 0.0))
            weighted_scores.append((symbol, score * w, name, w))
            total_weighted += score * w
        weighted_scores.sort(key=lambda x: x[1], reverse=True)
        summary['top_picks_weighted'] = weighted_scores[:3]
        summary['portfolio_weighted_score'] = round(total_weighted, 2)

        # 添加sleeve分析
        if portfolio_name:
            try:
                sleeves = self.portfolio_manager.get_sleeves(portfolio_name)
                if sleeves:
                    sleeve_analysis = []
                    for sleeve in sleeves:
                        sleeve_performance = {
                            'name': sleeve.name,
                            'target_return': f"{sleeve.target_return:.1%}",
                            'risk_level': sleeve.risk_level,
                            'allocation': f"{sleeve.allocation_ratio:.1%}",
                            'symbols_count': len(sleeve.symbols),
                            'top_symbols': list(sleeve.symbols.keys())[:3]
                        }

                        # 计算sleeve内的平均得分
                        sleeve_scores = []
                        for symbol, symbol_weight in sleeve.symbols.items():
                            if symbol in results and 'current_signal' in results[symbol]:
                                score = results[symbol]['current_signal'].get('combined_score', 0)
                                sleeve_scores.append(score * symbol_weight)

                        if sleeve_scores:
                            sleeve_performance['avg_score'] = round(sum(sleeve_scores), 2)
                        else:
                            sleeve_performance['avg_score'] = 0

                        sleeve_analysis.append(sleeve_performance)

                    summary['sleeve_analysis'] = sleeve_analysis
            except Exception:
                pass

        return summary

    def analyze_screen(self, screen_name: str, weight_method: str = 'equal', use_proxy: bool = True, current_days: int = 300, use_dynamic: bool = False, auto_refresh: bool = False, **kwargs) -> Dict[str, Any]:
        """基于选股篮子生成临时组合并分析
        
        Args:
            screen_name: 选股篮子名称
            weight_method: 权重方法 ('equal', 'inv_vol')
            use_proxy: 是否使用代理映射
            current_days: 当前信号分析天数
            use_dynamic: 是否使用动态筛选篮子
            auto_refresh: 是否自动刷新过期的动态篮子
        """
        screen_type = "动态" if use_dynamic else "静态"
        logger.info("📚 使用{screen_type}选股篮子: {screen_name} | 权重: {weight_method}")
        
        # 如果使用动态篮子且需要刷新
        if use_dynamic and auto_refresh:
            try:
                refresh_success = screen_manager.refresh_dynamic_screen(screen_name)
                if refresh_success:
                    logger.info("✅ 动态篮子 {screen_name} 刷新成功")
                else:
                    logger.info("⚠️ 动态篮子 {screen_name} 刷新失败，使用现有数据")
            except Exception as e:
                logger.info("⚠️ 动态篮子刷新异常: {e}")
        
        try:
            symbols = screen_manager.get_symbols(screen_name, use_dynamic=use_dynamic)
            if use_proxy:
                symbols = [self.portfolio_manager.apply_index_proxy(s) for s in symbols]
            weights = screen_manager.build_weights(screen_name, method=weight_method, use_dynamic=use_dynamic)
            
            # 获取篮子状态信息
            screen_info = {
                'is_dynamic': screen_manager.is_dynamic_screen(screen_name) if use_dynamic else False,
                'symbol_count': len(symbols),
                'screen_type': screen_type
            }
            if use_dynamic:
                screen_status = screen_manager.get_dynamic_screen_status(screen_name)
                screen_info.update(screen_status)
                
        except ValueError as e:
            available = screen_manager.list_screens(include_dynamic=True)
            return {'error': str(e), 'available_screens': available, 'success': False}

        try:
            advisor_kwargs = {k: v for k, v in kwargs.items() if k not in ['current_days', 'use_dynamic', 'auto_refresh']}
            advisor = InvestmentAdvisor(
                symbols=symbols,
                use_cache=self.use_cache,
                portfolio=f'SCREEN_{screen_name}',
                **advisor_kwargs
            )
            results = advisor.analyze_current_signals_only(symbols=symbols, current_days=current_days)
            return {
                'symbols': symbols,
                'mode': 'dynamic-screen-portfolio' if use_dynamic else 'screen-portfolio',
                'analysis_time': datetime.now().isoformat(),
                'portfolio_name': f'SCREEN_{screen_name}',
                'screen_name': screen_name,
                'weights_method': weight_method,
                'screen_info': screen_info,
                'results': results,
                'summary': self._generate_portfolio_summary(results, portfolio_name=None, weights=weights),
                'success': True
            }
        except Exception as e:
            return {'error': str(e), 'success': False}
    
    def refresh_dynamic_screens(self, screen_names: List[str] = None, force: bool = False) -> Dict[str, Any]:
        """刷新动态选股篮子
        
        Args:
            screen_names: 要刷新的篮子名称列表，为None则刷新所有
            force: 是否强制刷新
            
        Returns:
            刷新结果
        """
        logger.info("🔄 开始刷新动态选股篮子...")
        
        if screen_names is None:
            # 刷新所有动态篮子
            results = screen_manager.refresh_all_dynamic_screens(force=force)
        else:
            # 刷新指定篮子
            results = {}
            for screen_name in screen_names:
                try:
                    results[screen_name] = screen_manager.refresh_dynamic_screen(screen_name, force=force)
                except Exception as e:
                    logger.info("❌ 刷新篮子 {screen_name} 失败: {e}")
                    results[screen_name] = False
        
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)
        
        summary = {
            'mode': 'dynamic_screen_refresh',
            'analysis_time': datetime.now().isoformat(),
            'total_screens': total_count,
            'successful_refreshes': success_count,
            'failed_refreshes': total_count - success_count,
            'success_rate': f'{success_count/total_count*100:.1f}%' if total_count > 0 else '0%',
            'results': results,
            'success': success_count > 0
        }
        
        logger.info("✅ 动态篮子刷新完成: {success_count}/{total_count} 成功")
        
        return summary
    
    def get_screen_status(self, screen_name: str) -> Dict[str, Any]:
        """获取选股篮子状态信息"""
        try:
            # 获取基本信息
            static_symbols = screen_manager.get_symbols(screen_name, use_dynamic=False) if screen_name in screen_manager.static_screens else []
            is_dynamic = screen_manager.is_dynamic_screen(screen_name)
            
            status = {
                'screen_name': screen_name,
                'exists_static': len(static_symbols) > 0,
                'static_symbol_count': len(static_symbols),
                'is_dynamic': is_dynamic,
                'analysis_time': datetime.now().isoformat()
            }
            
            if is_dynamic:
                dynamic_status = screen_manager.get_dynamic_screen_status(screen_name)
                status.update(dynamic_status)
            
            return status
            
        except Exception as e:
            return {
                'screen_name': screen_name,
                'error': str(e),
                'success': False
            }
    
    def _is_etf(self, symbol: str) -> bool:
        """判断是否为ETF"""
        # 简单的ETF判断逻辑：代码以 5/15 开头或包含ETF关键词
        if not symbol:
            return False
        
        etf_prefixes = ['5', '15']  # ETF常见代码前缀
        etf_keywords = ['ETF', 'etf']
        
        # 检查代码前缀
        for prefix in etf_prefixes:
            if symbol.startswith(prefix):
                return True
        
        # 检查关键词
        for keyword in etf_keywords:
            if keyword in symbol:
                return True
                
        return False
    
    def _generate_consolidated_recommendation(self, single_result: Dict, strategy_result: Dict, etf_flow_result: Dict = None) -> Dict[str, Any]:
        """生成综合建议（包含ETF资金流分析）"""
        if not single_result.get('success') or not strategy_result:
            return {'recommendation': '数据不足，建议观望', 'confidence': 'low'}
        
        # 获取单标的建议
        single_action = single_result.get('recommendation', '观望')
        single_score = single_result.get('risk_analysis', {}).get('risk_score', 50)
        
        # 获取策略建议
        strategy_advice = strategy_result.get('action_advice', '观望')
        overall_strategy = strategy_result.get('overall_strategy', '未知')
        
        # 获取ETF资金流建议（如果有）
        etf_advice = None
        etf_score = 0
        if etf_flow_result and 'error' not in etf_flow_result:
            etf_score = etf_flow_result.get('comprehensive_score', 0)
            etf_advice = etf_flow_result.get('investment_suggestion', '观望')
        
        # 综合判断（加入ETF资金流评分）
        positive_signals = 0
        if '加仓' in single_action:
            positive_signals += 1
        if '加仓' in strategy_advice:
            positive_signals += 1
        if etf_advice and ('适合积极配置' in etf_advice or '可适度增持' in etf_advice):
            positive_signals += 1
        
        negative_signals = 0
        if '减仓' in single_action or '谨慎' in single_action:
            negative_signals += 1
        if '减仓' in strategy_advice or '谨慎' in strategy_advice:
            negative_signals += 1
        if etf_advice and ('谨慎操作' in etf_advice or '控制仓位' in etf_advice):
            negative_signals += 1
        
        # 综合判断逻辑
        if positive_signals >= 2 and negative_signals == 0:
            consolidated = "强烈推荐加仓"
            confidence = 'high'
        elif positive_signals >= 1 and negative_signals == 0:
            consolidated = "适度加仓"  
            confidence = 'medium'
        elif negative_signals >= 1:
            consolidated = "建议谨慎操作"
            confidence = 'medium'
        else:
            consolidated = "持有观望"
            confidence = 'low'
        
        # 构建详细原因说明
        reasoning_parts = [f'深度分析({single_action})', f'策略回测({strategy_advice})']
        if etf_advice:
            reasoning_parts.append(f'ETF资金流(评分{etf_score})')
        
        return {
            'recommendation': consolidated,
            'confidence': confidence,
            'single_advice': single_action,
            'strategy_advice': strategy_advice,
            'etf_flow_advice': etf_advice,
            'etf_flow_score': etf_score,
            'overall_strategy': overall_strategy,
            'positive_signals': positive_signals,
            'negative_signals': negative_signals,
            'reasoning': f'基于{" + ".join(reasoning_parts)}的综合判断'
        }
    
    def _generate_batch_summary(self, results: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """生成批量分析汇总"""
        if mode == 'portfolio':
            portfolio_data = results.get('portfolio', {})
            return portfolio_data.get('summary', {'message': '组合分析汇总失败'})
        
        # single模式的批量汇总
        summary = {
            'recommendations': {},
            'risk_levels': {},
            'top_opportunities': [],
            'high_risk_alerts': []
        }
        
        scored_results = []
        
        for symbol, result in results.items():
            if not result.get('success'):
                continue
            
            # 统计建议分布
            recommendation = result.get('recommendation', '观望')
            summary['recommendations'][recommendation] = summary['recommendations'].get(recommendation, 0) + 1
            
            # 统计风险分布  
            risk_level = result.get('risk_analysis', {}).get('risk_level', '未知')
            summary['risk_levels'][risk_level] = summary['risk_levels'].get(risk_level, 0) + 1
            
            # 收集评分信息
            risk_score = result.get('risk_analysis', {}).get('risk_score', 50)
            fundamental_score = 0
            if result.get('fundamental_analysis', {}).get('has_data'):
                fundamental_score = result['fundamental_analysis']['fundamental_score'].get('total_score', 0)
            
            scored_results.append({
                'symbol': symbol,
                'risk_score': risk_score,
                'fundamental_score': fundamental_score,
                'recommendation': recommendation,
                'combined_score': (100 - risk_score) * 0.6 + fundamental_score * 0.4  # 综合评分
            })
        
        # 按综合评分排序
        scored_results.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # 机会标的（综合评分高且建议加仓）
        summary['top_opportunities'] = [
            r for r in scored_results[:5] 
            if '加仓' in r['recommendation']
        ][:3]
        
        # 高风险警示（风险分数高）
        high_risk = [r for r in scored_results if r['risk_score'] > 70]
        summary['high_risk_alerts'] = high_risk[:3]
        
        return summary
    
    def _generate_comprehensive_portfolio_summary(self, symbols_analysis: Dict[str, Any], portfolio_name: str) -> Dict[str, Any]:
        """生成综合组合分析汇总"""
        summary = {
            'portfolio_name': portfolio_name,
            'total_symbols': len(symbols_analysis),
            'successful_analysis': 0,
            'failed_analysis': 0,
            'consolidated_recommendations': {},
            'risk_distribution': {},
            'confidence_levels': {},
            'top_recommendations': [],
            'risk_warnings': []
        }
        
        scored_symbols = []
        
        for symbol, analysis in symbols_analysis.items():
            if analysis.get('success'):
                summary['successful_analysis'] += 1
                
                # 获取综合建议
                consolidated = analysis.get('consolidated_recommendation', {})
                recommendation = consolidated.get('recommendation', '观望')
                confidence = consolidated.get('confidence', 'low')
                
                # 统计建议分布
                summary['consolidated_recommendations'][recommendation] = \
                    summary['consolidated_recommendations'].get(recommendation, 0) + 1
                
                # 统计置信度分布
                summary['confidence_levels'][confidence] = \
                    summary['confidence_levels'].get(confidence, 0) + 1
                
                # 获取风险信息
                single_analysis = analysis.get('single_analysis', {})
                if single_analysis.get('success'):
                    risk_level = single_analysis.get('risk_analysis', {}).get('risk_level', '未知')
                    summary['risk_distribution'][risk_level] = \
                        summary['risk_distribution'].get(risk_level, 0) + 1
                    
                    # 评分用于排序
                    risk_score = single_analysis.get('risk_analysis', {}).get('risk_score', 50)
                    scored_symbols.append({
                        'symbol': symbol,
                        'recommendation': recommendation,
                        'confidence': confidence,
                        'risk_score': risk_score,
                        'combined_score': (100 - risk_score) * 0.7 + ({'low': 20, 'medium': 50, 'high': 80}.get(confidence, 30)) * 0.3
                    })
            else:
                summary['failed_analysis'] += 1
        
        # 按综合评分排序
        scored_symbols.sort(key=lambda x: x['combined_score'], reverse=True)
        
        # 顶级推荐（高评分且高置信度）
        summary['top_recommendations'] = [
            s for s in scored_symbols[:3] 
            if s['confidence'] in ['medium', 'high'] and '加仓' in s['recommendation']
        ]
        
        # 风险警告（高风险评分）
        summary['risk_warnings'] = [
            s for s in scored_symbols
            if s['risk_score'] > 70
        ][:3]
        
        return summary
    
    def _generate_global_portfolio_insights(self, all_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成全局投资组合洞察"""
        insights = {
            'top_performing_portfolios': [],
            'sector_distribution': {},
            'risk_level_distribution': {},
            'overall_market_sentiment': 'neutral',
            'recommended_diversification': []
        }
        
        portfolio_scores = []
        
        # 分析每个组合的表现
        for portfolio_name, result in all_results.items():
            if not result.get('success', True):
                continue
                
            portfolio_score = 0
            positive_signals = 0
            total_signals = 0
            
            # 计算组合评分
            if result.get('mode') == 'portfolio':
                portfolio_results = result.get('results', {})
                for symbol_data in portfolio_results.values():
                    if 'current_signal' in symbol_data:
                        total_signals += 1
                        score = symbol_data['current_signal'].get('combined_score', 0)
                        portfolio_score += score
                        
                        action = symbol_data['current_signal'].get('action', '观望')
                        if '买入' in action or '加仓' in action:
                            positive_signals += 1
            
            if total_signals > 0:
                avg_score = portfolio_score / total_signals
                positivity_ratio = positive_signals / total_signals
                
                portfolio_scores.append({
                    'name': portfolio_name,
                    'avg_score': avg_score,
                    'positivity_ratio': positivity_ratio,
                    'total_signals': total_signals,
                    'combined_metric': avg_score * 0.7 + positivity_ratio * 30
                })
        
        # 按综合指标排序
        portfolio_scores.sort(key=lambda x: x['combined_metric'], reverse=True)
        insights['top_performing_portfolios'] = portfolio_scores[:5]
        
        # 整体市场情绪判断
        if portfolio_scores:
            avg_positivity = sum(p['positivity_ratio'] for p in portfolio_scores) / len(portfolio_scores)
            if avg_positivity > 0.6:
                insights['overall_market_sentiment'] = 'bullish'
            elif avg_positivity < 0.3:
                insights['overall_market_sentiment'] = 'bearish'
            else:
                insights['overall_market_sentiment'] = 'neutral'
        
        return insights
    
    def _generate_allocation_recommendation(self, all_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成资产配置建议"""
        allocation = {
            'conservative_allocation': {},
            'balanced_allocation': {},
            'aggressive_allocation': {},
            'reasoning': {}
        }
        
        # 根据组合的风险特征和表现给出配置建议
        portfolio_meta = self.portfolio_manager.portfolio_meta
        
        for portfolio_name, result in all_results.items():
            if not result.get('success', True):
                continue
            
            meta = portfolio_meta.get(portfolio_name, {})
            risk_level = meta.get('risk_level', 'medium')
            
            # 简化的配置逻辑
            if risk_level == 'low':
                allocation['conservative_allocation'][portfolio_name] = '30-40%'
                allocation['balanced_allocation'][portfolio_name] = '20-25%'
                allocation['aggressive_allocation'][portfolio_name] = '10-15%'
            elif risk_level == 'medium':
                allocation['conservative_allocation'][portfolio_name] = '20-30%'
                allocation['balanced_allocation'][portfolio_name] = '25-35%'
                allocation['aggressive_allocation'][portfolio_name] = '20-30%'
            else:  # high risk
                allocation['conservative_allocation'][portfolio_name] = '5-10%'
                allocation['balanced_allocation'][portfolio_name] = '15-20%'
                allocation['aggressive_allocation'][portfolio_name] = '30-50%'
        
        allocation['reasoning'] = {
            'conservative': '以低风险组合为主，追求稳定收益',
            'balanced': '风险与收益平衡，适合大部分投资者',
            'aggressive': '高风险高收益，适合激进投资者'
        }
        
        return allocation
    
    def save_results(self, filename: str = None):
        """保存分析结果到文件"""
        # 创建data/backtest_results目录（如果不存在）
        backtest_dir = self.project_root / 'data' / 'backtest_results'
        backtest_dir.mkdir(parents=True, exist_ok=True)
        
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'advisor_results_{timestamp}.json'
        
        # 如果filename没有完整路径，则保存到backtest_results目录
        if not Path(filename).is_absolute() and '/' not in filename:
            filepath = backtest_dir / filename
        else:
            filepath = Path(filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2, default=str)
        
        logger.info("📁 分析结果已保存到: {filepath}")


def load_symbols_from_file(filepath: str) -> List[str]:
    """从文件加载股票代码列表"""
    symbols = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    # 支持逗号分隔或每行一个
                    if ',' in line:
                        symbols.extend([s.strip() for s in line.split(',') if s.strip()])
                    else:
                        symbols.append(line)
        logger.info("📄 从文件加载了 {len(symbols)} 个股票代码")
    except Exception as e:
        logger.info("❌ 加载文件失败: {e}")
    
    return symbols


def main():
    # 获取可用投资组合列表
    available_portfolios = portfolio_manager.list_portfolios()
    portfolio_descriptions = []
    for portfolio_name in available_portfolios:
        meta = portfolio_manager.get_portfolio_meta(portfolio_name)
        desc = meta.get('description', '未知')
        risk = meta.get('risk_level', '未知')
        portfolio_descriptions.append(f"  {portfolio_name}: {desc} (\u98ce\u9669: {risk})")
    
    parser = argparse.ArgumentParser(
        description='统一投资顾问 - 整合深度分析和策略回测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
使用示例:
  # 单标的深度分析
  python advisor.py --mode single --symbol 002049.SZ
  
  # 自定义投资组合策略分析
  python advisor.py --mode portfolio --symbols 002049.SZ,300661.SZ,603501.SH
  
  # 使用预定义投资组合分析
  python advisor.py --mode portfolio --portfolio DEFAULT

  # 使用选股篮子，动态生成组合（等权/逆波动）
  python advisor.py --mode portfolio --screen SEMICONDUCTOR --weight-method equal
  python advisor.py --mode portfolio --screen BANK --weight-method inv_vol
  
  # 使用动态筛选篮子（基于算法实时筛选）
  python advisor.py --mode portfolio --screen ETF_HIGH_MOMENTUM --dynamic
  python advisor.py --mode portfolio --screen SEMICONDUCTOR_DYNAMIC --dynamic --auto-refresh
  
  # 刷新动态选股篮子
  python advisor.py --refresh-screens
  python advisor.py --refresh-screens --screens ETF_HIGH_MOMENTUM,BANK_DYNAMIC --force
  
  # 综合分析（深度+策略）
  python advisor.py --mode comprehensive --symbol 002049.SZ
  
  # 批量分析
  python advisor.py --mode batch --symbols-file semiconductor_stocks.txt
  
  # 全组合分析（生成完整报告）
  python advisor.py --mode all-portfolios --save all_portfolios_report.json

可用投资组合:
{chr(10).join(portfolio_descriptions)}

可用选股篮子:
{chr(10).join('  ' + s for s in screen_manager.list_screens())}
        """
    )
    
    # 基础参数
    parser.add_argument('--mode', 
                       choices=['single', 'portfolio', 'comprehensive', 'batch', 'all-portfolios', 'refresh-screens', 'screen-status'],
                       required=False,
                       help='分析模式')
    
    # 动态筛选相关参数
    parser.add_argument('--refresh-screens',
                       action='store_true',
                       help='刷新动态选股篮子')
                       
    parser.add_argument('--screens',
                       help='指定要刷新的篮子名称，逗号分隔')
                       
    parser.add_argument('--screen-status',
                       help='查看指定篮子的状态信息')
                       
    parser.add_argument('--dynamic',
                       action='store_true',
                       help='使用动态筛选篮子（适用于 --screen 参数）')
                       
    parser.add_argument('--auto-refresh',
                       action='store_true',
                       help='自动刷新过期的动态篮子')
                       
    parser.add_argument('--force',
                       action='store_true',
                       help='强制刷新动态篮子（忽略时间限制）')
    
    parser.add_argument('--symbol', 
                       help='股票代码（单标的分析用）')
    
    parser.add_argument('--symbols', 
                       help='股票代码列表，逗号分隔（组合分析用）')
    
    parser.add_argument('--symbols-file',
                       help='包含股票代码的文件路径')
    
    parser.add_argument('--portfolio',
                       default='CUSTOM', 
                       help='组合名称（仅支持 DEFAULT；其他请使用 --screen）')
    parser.add_argument('--screen',
                       help='选股篮子名称（静态: BANK/SEMICONDUCTOR; 动态: ETF_HIGH_MOMENTUM/BANK_DYNAMIC）')
    parser.add_argument('--weight-method',
                       choices=['equal', 'inv_vol'],
                       default='equal',
                       help='从选股篮子生成权重的方法')
    
    # 分析参数
    parser.add_argument('--days-back', 
                       type=int, 
                       default=2500,
                       help='历史数据天数')
    
    parser.add_argument('--periods',
                       default='3Y,5Y',
                       help='回测周期，逗号分隔（综合分析用）')
    
    parser.add_argument('--current-days',
                       type=int,
                       default=300,
                       help='当前信号分析的数据天数')
    
    # 功能开关
    parser.add_argument('--no-fundamental',
                       action='store_true',
                       help='禁用基本面分析')
    
    parser.add_argument('--no-cache',
                       action='store_true', 
                       help='禁用缓存')
    
    parser.add_argument('--save',
                       help='保存结果到指定文件')
    
    args = parser.parse_args()
    
    # 处理新的功能模式
    if args.refresh_screens:
        args.mode = 'refresh-screens'
    elif args.screen_status:
        args.mode = 'screen-status'
    
    # 参数验证
    if not args.mode:
        parser.error("必须指定分析模式或使用 --refresh-screens/--screen-status")
        
    if args.mode in ['single', 'comprehensive'] and not args.symbol:
        parser.error("--symbol is required for single/comprehensive mode")
    
    # 对于portfolio模式，如果没有提供标的也没有文件，也没提供screen，则要求使用预定义组合
    if args.mode == 'portfolio' and not (args.symbols or args.symbols_file or args.screen):
        available_portfolios = portfolio_manager.list_portfolios()
        if args.portfolio not in available_portfolios:
            parser.error(
                "--symbols/--symbols-file/--screen 其一必需，或使用预定义组合。"
                f" 可用组合: {', '.join(available_portfolios)} | 可用选股篮子: {', '.join(screen_manager.list_screens())}"
            )
    
    if args.mode == 'batch' and not (args.symbols or args.symbols_file):
        parser.error("--symbols or --symbols-file is required for batch mode")
    
    # 创建统一顾问
    advisor = UnifiedAdvisor(
        use_cache=not args.no_cache,
        enable_fundamental=not args.no_fundamental
    )
    
    # 解析股票代码
    symbols = []
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    elif args.symbols_file:
        symbols = load_symbols_from_file(args.symbols_file)
    
    # 解析回测周期
    periods = tuple(p.strip() for p in args.periods.split(',')) if args.periods else ("3Y", "5Y")
    
    # 执行分析
    try:
        if args.mode == 'single':
            result = advisor.analyze_single(
                symbol=args.symbol,
                days_back=args.days_back
            )
            
        elif args.mode == 'portfolio':
            if args.screen and not symbols:
                # 使用选股篮子，支持动态篮子
                result = advisor.analyze_screen(
                    screen_name=args.screen,
                    weight_method=args.weight_method,
                    current_days=args.current_days,
                    use_dynamic=args.dynamic,
                    auto_refresh=args.auto_refresh
                )
            else:
                # 普通组合分析
                result = advisor.analyze_portfolio(
                    symbols=symbols,
                    portfolio_name=args.portfolio,
                    current_days=args.current_days
                )
            
        elif args.mode == 'comprehensive':
            result = advisor.analyze_comprehensive(
                symbol=args.symbol,
                periods=periods,
                days_back=args.days_back,
                current_days=args.current_days
            )
            
        elif args.mode == 'batch':
            # 批量模式默认使用single子模式
            result = advisor.batch_analyze(
                symbols=symbols,
                mode='single',
                days_back=args.days_back
            )
            
        elif args.mode == 'all-portfolios':
            # 全组合分析模式
            result = advisor.analyze_all_portfolios(
                analysis_mode='portfolio',  # 默认使用portfolio分析模式
                current_days=args.current_days
            )
            
        elif args.mode == 'refresh-screens':
            # 刷新动态篮子模式
            screen_names = None
            if args.screens:
                screen_names = [s.strip() for s in args.screens.split(',') if s.strip()]
            
            result = advisor.refresh_dynamic_screens(
                screen_names=screen_names,
                force=args.force
            )
            
        elif args.mode == 'screen-status':
            # 查看篮子状态模式
            result = advisor.get_screen_status(args.screen_status)
        
        # 保存结果（非状态查询模式）
        if args.save and args.mode not in ['screen-status']:
            advisor.save_results(args.save)
        
        # 根据模式显示不同的完成信息
        if args.mode == 'refresh-screens':
            logger.info("\n🔄 动态篮子刷新完成")
        elif args.mode == 'screen-status':
            logger.info("\n📊 篮子状态查询完成")
        else:
            logger.info("\n✅ 分析完成")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ 用户中断分析")
    except Exception as e:
        logger.info("❗ 分析过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
