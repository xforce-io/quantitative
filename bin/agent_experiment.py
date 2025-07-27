#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Agent Experiment CLI Tool
基于配置的 Agent 实验命令行工具
"""

import os
import sys
import yaml
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# 添加项目根目录到路径
projectRoot = Path(__file__).parent.parent
sys.path.insert(0, str(projectRoot))

# 加载环境变量
load_dotenv(dotenv_path=projectRoot / '.env')

from quant.agents.agent_manager import AgentManager, AgentOptimizationConfig

def loadAgentConfig():
    """加载 Agent 配置文件"""
    configPath = projectRoot / 'config' / 'agent_strategies.yaml'
    if not configPath.exists():
        raise FileNotFoundError(f"找不到配置文件: {configPath}")
    
    with open(configPath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def listExperiments():
    """列出可用的实验配置"""
    try:
        config = loadAgentConfig()
        experiments = config.get('agent_experiments', {})
        
        print("🧪 可用的 Agent 实验配置:")
        print("=" * 80)
        for expName, expConfig in experiments.items():
            symbol = expConfig.get('symbol', 'N/A')
            name = expConfig.get('name', expName)
            description = expConfig.get('description', '无描述')
            
            # 统计 Agent 数量
            agents = expConfig.get('agents', {})
            totalAgents = 0
            for agentType, agentConfig in agents.items():
                if agentConfig.get('enabled', False):
                    totalAgents += agentConfig.get('count', 1)
            
            print(f"  {expName:<20} : {name}")
            print(f"  {'':>20}   股票: {symbol} | 总 Agent: {totalAgents} 个")
            print(f"  {'':>20}   描述: {description}")
            print("-" * 80)
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 无法加载实验配置: {str(e)}")

def runExperiment(experimentName: str, dryRun: bool = False):
    """运行指定的实验"""
    try:
        config = loadAgentConfig()
        experiments = config.get('agent_experiments', {})
        
        if experimentName not in experiments:
            print(f"❌ 未找到实验配置: {experimentName}")
            print(f"可用的实验: {list(experiments.keys())}")
            return
        
        expConfig = experiments[experimentName]
        
        print(f"🧪 开始运行实验: {experimentName}")
        print("=" * 80)
        print(f"📊 实验名称: {expConfig.get('name', experimentName)}")
        print(f"🏷️  股票代码: {expConfig['symbol']}")
        print(f"📅 时间范围: {expConfig['date_range']['start']} - {expConfig['date_range']['end']}")
        print(f"💰 初始资金: ¥{expConfig['initial_capital']:,}")
        
        if dryRun:
            print("\n🔍 DRY RUN 模式 - 仅显示配置信息")
            print("✅ 配置验证通过")
            return
        
        # 初始化 Agent 管理器
        agentManager = AgentManager('tushare')
        
        # 收集所有 Agent 配置
        allAgents = []
        agents = expConfig.get('agents', {})
        
        for agentType, agentConfig in agents.items():
            if not agentConfig.get('enabled', False):
                continue
                
            # 解析 Agent 类型名
            agentTypeName = agentType.split('_')[0]  # grid_strategies -> grid
            
            # 创建优化配置
            optimizationConfig = AgentOptimizationConfig(
                agentType=agentTypeName,
                parameterRanges=agentConfig['parameter_ranges'],
                riskProfile=agentConfig.get('risk_profile', 'moderate'),
                maxVariants=agentConfig.get('count', 5)
            )
            
            # 生成 Agent 变体
            agentVariants = agentManager.generateAgentVariants(
                agentTypeName, 
                expConfig['symbol'], 
                optimizationConfig
            )
            
            # 限制数量
            maxCount = agentConfig.get('count', len(agentVariants))
            selectedAgents = agentVariants[:maxCount]
            allAgents.extend(selectedAgents)
        
        print(f"📊 总计生成 {len(allAgents)} 个 Agent")
        
        # 执行优化
        results = agentManager.optimizeAgents(
            symbol=expConfig['symbol'],
            startDate=expConfig['date_range']['start'],
            endDate=expConfig['date_range']['end'],
            agentConfigs=allAgents,
            initialCapital=expConfig['initial_capital']
        )
        
        # 生成报告
        report = agentManager.generateOptimizationReport(expConfig['symbol'], results)
        
        # 保存实验结果
        metadata = {
            'initial_capital': expConfig['initial_capital'],
            'start_date': expConfig['date_range']['start'],
            'end_date': expConfig['date_range']['end'],
            'experiment_config': expConfig
        }
        
        experimentDir = agentManager.saveExperimentResults(
            symbol=expConfig['symbol'],
            experimentName=experimentName,
            results=results,
            report=report,
            metadata=metadata
        )
        
        # 显示结果
        bestAgent = report['bestOverall']
        print(f"\n🏆 最佳 Agent: {bestAgent['name']}")
        print(f"收益率: {bestAgent['performance']['totalReturn']:.2%}")
        print(f"夏普比率: {bestAgent['performance']['sharpeRatio']:.3f}")
        
        print(f"\n📂 可以使用以下命令进行回测:")
        print(f"python bin/run.py trading backtest-from-experiment {experimentDir}")
        
        print("\n✅ 实验完成!")
        
    except Exception as e:
        print(f"❌ 实验执行失败: {str(e)}")

def validateConfiguration():
    """验证配置文件"""
    try:
        config = loadAgentConfig()
        print("✅ 配置文件格式验证通过")
        
        experiments = config.get('agent_experiments', {})
        print(f"📊 发现 {len(experiments)} 个实验配置")
        
        print("✅ 配置验证完成")
        
    except Exception as e:
        print(f"❌ 配置验证失败: {str(e)}")

def listExperimentResults():
    """列出已保存的实验结果"""
    try:
        experimentsDir = Path('data') / 'expr'
        if not experimentsDir.exists():
            print("📂 实验结果目录不存在，还没有运行过实验")
            return
        
        # 查找所有实验目录
        experimentDirs = [d for d in experimentsDir.iterdir() if d.is_dir()]
        
        if not experimentDirs:
            print("📂 未找到任何实验结果")
            return
        
        print("📊 已保存的实验结果:")
        print("=" * 90)
        
        for expDir in sorted(experimentDirs, reverse=True):  # 按时间倒序
            try:
                # 读取实验元数据
                metaFile = expDir / 'experiment_meta.json'
                if metaFile.exists():
                    with open(metaFile, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    
                    # 读取策略配置
                    configFile = expDir / 'best_strategy_config.json'
                    strategyName = "Unknown"
                    performance = {}
                    if configFile.exists():
                        with open(configFile, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                        strategyName = config.get('strategy_name', 'Unknown')
                        performance = config.get('performance', {})
                    
                    # 显示信息
                    expName = meta.get('experiment_name', 'Unknown')
                    symbol = meta.get('symbol', 'Unknown')
                    timestamp = meta.get('timestamp', 'Unknown')
                    bestStrategy = meta.get('best_overall_strategy', {})
                    
                    print(f"📁 {expDir.name}")
                    print(f"   实验名称: {expName}")
                    print(f"   股票代码: {symbol}")
                    print(f"   创建时间: {timestamp[:19] if isinstance(timestamp, str) else timestamp}")
                    print(f"   最佳策略: {strategyName}")
                    
                    if bestStrategy:
                        returnRate = bestStrategy.get('return', 0)
                        sharpeRatio = bestStrategy.get('sharpe_ratio', 0)
                        maxDrawdown = bestStrategy.get('max_drawdown', 0)
                        print(f"   收益率: {returnRate:.2%} | 夏普比率: {sharpeRatio:.3f} | 最大回撤: {maxDrawdown:.2%}")
                    
                    print(f"   📂 使用命令回测: python bin/run.py trading backtest-from-experiment {expDir}")
                    print("-" * 90)
                else:
                    print(f"📁 {expDir.name} (元数据缺失)")
                    print("-" * 90)
                    
            except Exception as e:
                print(f"📁 {expDir.name} (读取失败: {str(e)})")
                print("-" * 90)
        
        print("=" * 90)
        
    except Exception as e:
        print(f"❌ 列出实验结果失败: {str(e)}") 