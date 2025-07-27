#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Stock Strategy Compatibility Analyzer
股票策略适配性分析器

通用股票策略适配性分析工具，可分析任何股票的策略适配性
Universal stock strategy compatibility analyzer for any stock
"""

import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# 添加数据提供者导入
import sys
sys.path.append(str(Path(__file__).parent.parent))
from quant.data_providers.data_provider_factory import DataProviderFactory
from datetime import datetime, timedelta

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class StockStrategyAnalyzer:
    """通用股票策略分析器"""
    
    def __init__(self, data_dir: str = "quant/data", config_dir: str = "config/stocks", verbose: bool = False):
        self.dataDir = Path(data_dir)
        self.configDir = Path(config_dir)
        self.stockData = None
        self.config = None
        self.symbol = None
        self.verbose = verbose  # 详细模式标志
        
        # 初始化数据提供者（用于自动获取数据）
        self.dataProvider = None
        self._initializeDataProvider()
    
    def _initializeDataProvider(self):
        """初始化数据提供者"""
        try:
            self.dataProvider = DataProviderFactory.create('tushare')
        except Exception as e:
            print(f"⚠️ 无法初始化数据提供者: {e}")
            self.dataProvider = None
        
    def loadStockData(self, symbol: str) -> None:
        """加载指定股票的数据"""
        self.symbol = symbol
        self.stockData = None  # 重置股票数据，防止使用前一个股票的数据
        
        print(f"📊 加载股票数据: {symbol}")
        
        # 首先尝试从本地文件加载
        success = self._loadDataFromLocalFiles(symbol)
        
        # 如果本地文件不存在，尝试从数据提供者获取
        if not success and self.dataProvider is not None:
            success = self._loadDataFromProvider(symbol)
        
        if not success:
            print(f"❌ 无法获取股票 {symbol} 的数据")
            return
        
        # 计算技术指标
        if self.stockData is not None:
            self.calculateTechnicalIndicators()
            print(f"✅ 数据加载完成: {len(self.stockData)} 个交易日")
    
    def _loadDataFromLocalFiles(self, symbol: str) -> bool:
        """从本地文件加载数据"""
        try:
            # 查找最新的数据文件
            data_files = list(self.dataDir.glob(f"{symbol}_*.csv"))
            if not data_files:
                print(f"📁 未找到股票 {symbol} 的本地数据文件")
                return False
            
            # 选择最新的数据文件
            latest_file = max(data_files, key=lambda x: x.stat().st_mtime)
            print(f"✅ 使用数据文件: {latest_file.name}")
            
            # 读取数据
            self.stockData = pd.read_csv(latest_file)
            
            # 处理日期列
            if 'date' in self.stockData.columns:
                self.stockData['date'] = pd.to_datetime(self.stockData['date'])
                self.stockData.set_index('date', inplace=True)
            
            return True
            
        except Exception as e:
            print(f"❌ 本地数据加载失败: {e}")
            return False
    
    def _loadDataFromProvider(self, symbol: str) -> bool:
        """从数据提供者获取数据"""
        try:
            print(f"🔄 尝试从tushare获取 {symbol} 的数据...")
            
            # 计算日期范围：最近2年的数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=730)  # 2年
            
            # 格式化日期
            start_date_str = start_date.strftime('%Y%m%d')
            end_date_str = end_date.strftime('%Y%m%d')
            
            # 获取数据
            data = self.dataProvider.getStockData(
                symbol=symbol,
                startDate=start_date_str,
                endDate=end_date_str,
                frequency='D'
            )
            
            if data.empty:
                print(f"❌ 从tushare获取的数据为空")
                return False
            
            # 转换数据格式以匹配本地文件格式
            self.stockData = data.copy()
            
            # 确保有必要的列
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in self.stockData.columns]
            if missing_columns:
                print(f"❌ 缺少必要的列: {missing_columns}")
                return False
            
            # 保存到本地文件以便下次使用
            self._saveDataToLocal(symbol, start_date_str, end_date_str)
            
            print(f"✅ 从tushare成功获取 {symbol} 的数据")
            return True
            
        except Exception as e:
            print(f"❌ 从tushare获取数据失败: {e}")
            return False
    
    def _saveDataToLocal(self, symbol: str, start_date: str, end_date: str):
        """保存数据到本地文件"""
        try:
            # 创建目录
            self.dataDir.mkdir(parents=True, exist_ok=True)
            
            # 构建文件名
            filename = f"{symbol}_{start_date}_{end_date}_D.csv"
            filepath = self.dataDir / filename
            
            # 保存数据
            self.stockData.to_csv(filepath)
            print(f"💾 数据已保存到: {filepath}")
            
        except Exception as e:
            print(f"⚠️ 保存数据失败: {e}")
    
    def loadConfig(self, symbol: str) -> None:
        """加载股票配置"""
        config_file = self.configDir / f"{symbol}.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            print(f"✅ 配置加载完成: {self.config.get('name', symbol)}")
        else:
            print(f"⚠️ 配置文件不存在: {config_file}，将使用默认配置")
            self.config = self.getDefaultConfig(symbol)
    
    def getDefaultConfig(self, symbol: str) -> Dict:
        """获取默认配置"""
        return {
            "symbol": symbol,
            "name": symbol,
            "industry": "未知",
            "market": "A股",
            "riskLevel": "medium",
            "totalMaxPosition": 100000,
            "gridStrategy": {
                "gridLevels": 10,
                "gridSpacing": 0.025,
                "maxPosition": 80000,
                "baseRatio": 0.5,
                "commission": 0.0003,
                "slippage": 0.001,
                "stopLoss": 0.10,
                "takeProfit": 0.20
            },
            "dcaStrategy": {
                "interval": "monthly",
                "amount": 2000,
                "maxPosition": 60000,
                "baseRatio": 0.6,
                "commission": 0.0003
            },
            "momentumStrategy": {
                "lookbackPeriod": 25,
                "threshold": 0.03,
                "maxPosition": 10000,
                "baseRatio": 0.05,
                "commission": 0.0003
            }
        }
    
    def calculateTechnicalIndicators(self) -> None:
        """计算技术指标"""
        if self.stockData is None:
            return
        
        # 计算移动平均线
        self.stockData['MA5'] = self.stockData['close'].rolling(window=5).mean()
        self.stockData['MA10'] = self.stockData['close'].rolling(window=10).mean()
        self.stockData['MA20'] = self.stockData['close'].rolling(window=20).mean()
        self.stockData['MA60'] = self.stockData['close'].rolling(window=60).mean()
        
        # 计算收益率
        self.stockData['daily_return'] = self.stockData['close'].pct_change()
        self.stockData['cumulative_return'] = (1 + self.stockData['daily_return']).cumprod() - 1
        
        # 计算波动率
        self.stockData['volatility_20d'] = self.stockData['daily_return'].rolling(window=20).std() * np.sqrt(252)
        
        # 计算最大回撤
        self.stockData['peak'] = self.stockData['close'].expanding().max()
        self.stockData['drawdown'] = (self.stockData['close'] - self.stockData['peak']) / self.stockData['peak']
        self.stockData['max_drawdown'] = self.stockData['drawdown'].expanding().min()
        
        # 计算RSI
        delta = self.stockData['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.stockData['RSI'] = 100 - (100 / (1 + rs))
        
        # 计算布林带
        self.stockData['BB_middle'] = self.stockData['close'].rolling(window=20).mean()
        bb_std = self.stockData['close'].rolling(window=20).std()
        self.stockData['BB_upper'] = self.stockData['BB_middle'] + (bb_std * 2)
        self.stockData['BB_lower'] = self.stockData['BB_middle'] - (bb_std * 2)
        
        # 计算成交量指标
        if 'volume' in self.stockData.columns:
            self.stockData['volume_ma'] = self.stockData['volume'].rolling(window=20).mean()
            self.stockData['volume_ratio'] = self.stockData['volume'] / self.stockData['volume_ma']
    
    def analyzeStockCharacteristics(self) -> Dict:
        """分析股票特征"""
        if self.stockData is None:
            return {}
        
        # 基本统计
        total_return = (self.stockData['close'].iloc[-1] / self.stockData['close'].iloc[0]) - 1
        annual_return = (1 + total_return) ** (252 / len(self.stockData)) - 1
        volatility = self.stockData['daily_return'].std() * np.sqrt(252)
        max_drawdown = self.stockData['max_drawdown'].min()
        sharpe_ratio = annual_return / volatility if volatility > 0 else 0
        
        # 价格特征
        price_range = (self.stockData['high'].max() - self.stockData['low'].min()) / self.stockData['close'].mean()
        avg_price = self.stockData['close'].mean()
        price_std = self.stockData['close'].std()
        price_cv = price_std / avg_price  # 变异系数
        
        # 交易特征
        avg_volume = self.stockData['volume'].mean() if 'volume' in self.stockData.columns else 0
        volume_volatility = self.stockData['volume'].std() / avg_volume if avg_volume > 0 else 0
        
        # 趋势特征 - 修复计算bug
        if len(self.stockData) > 20 and 'MA20' in self.stockData.columns:
            ma20_start = self.stockData['MA20'].iloc[0]
            ma20_end = self.stockData['MA20'].iloc[-1]
            if pd.notna(ma20_start) and pd.notna(ma20_end) and ma20_start != 0:
                trend_strength = abs(ma20_end - ma20_start) / ma20_start
            else:
                # 备用计算方法：使用收盘价
                trend_strength = abs(self.stockData['close'].iloc[-1] - self.stockData['close'].iloc[0]) / self.stockData['close'].iloc[0]
        else:
            trend_strength = 0
        
        # 震荡特征
        rsi_avg = self.stockData['RSI'].mean()
        rsi_std = self.stockData['RSI'].std()
        
        # 市场环境判断
        market_environment = self.judgeMarketEnvironment(total_return, volatility, trend_strength)
        
        characteristics = {
            'symbol': self.symbol,
            'total_return': total_return,
            'annual_return': annual_return,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'price_range': price_range,
            'price_cv': price_cv,
            'volume_volatility': volume_volatility,
            'trend_strength': trend_strength,
            'rsi_avg': rsi_avg,
            'rsi_std': rsi_std,
            'avg_price': avg_price,
            'avg_volume': avg_volume,
            'market_environment': market_environment
        }
        
        print(f"\n📈 {self.symbol} 股票特征分析:")
        print("=" * 60)
        print(f"总收益率: {total_return:.2%}")
        print(f"年化收益率: {annual_return:.2%}")
        print(f"年化波动率: {volatility:.2%}")
        print(f"最大回撤: {max_drawdown:.2%}")
        print(f"夏普比率: {sharpe_ratio:.3f}")
        print(f"价格区间: {price_range:.2%}")
        print(f"价格变异系数: {price_cv:.3f}")
        print(f"成交量波动率: {volume_volatility:.3f}")
        print(f"趋势强度: {trend_strength:.2%}")
        print(f"RSI均值: {rsi_avg:.1f}")
        print(f"RSI标准差: {rsi_std:.1f}")
        print(f"市场环境: {market_environment}")
        
        return characteristics
    
    def judgeMarketEnvironment(self, total_return: float, volatility: float, trend_strength: float) -> str:
        """判断市场环境"""
        if total_return > 0.2 and trend_strength > 0.3:
            return "强上涨趋势"
        elif total_return > 0.1 and trend_strength > 0.2:
            return "上涨趋势"
        elif total_return < -0.2 and trend_strength > 0.3:
            return "强下跌趋势"
        elif total_return < -0.1 and trend_strength > 0.2:
            return "下跌趋势"
        elif volatility > 0.4:
            return "高波动震荡"
        elif volatility > 0.2:
            return "中等波动震荡"
        else:
            return "低波动震荡"
    
    def analyzeStrategyCompatibility(self, characteristics: Dict) -> Dict:
        """分析策略适配性"""
        if not characteristics:
            return {}
        
        if self.verbose:
            print("\n📊 详细评分计算:")
            print("=" * 60)
        
        # 策略评分标准
        strategy_scores = {
            'dca': 0,
            'grid': 0,
            'momentum': 0,
            'ma_crossover': 0
        }
        
        # DCA策略评分
        dca_score = 0
        dca_details = []
        
        # 波动率评分
        if characteristics['volatility'] < 0.3:  # 低波动率适合DCA
            dca_score += 30
            dca_details.append(f"波动率({characteristics['volatility']:.1%}): +30分 (低波动适合DCA)")
        elif characteristics['volatility'] < 0.5:
            dca_score += 20
            dca_details.append(f"波动率({characteristics['volatility']:.1%}): +20分 (中等波动)")
        else:
            dca_score += 10
            dca_details.append(f"波动率({characteristics['volatility']:.1%}): +10分 (高波动不太适合)")
            
        # 趋势强度评分
        if characteristics['trend_strength'] > 0.5:  # 强趋势适合DCA
            dca_score += 25
            dca_details.append(f"趋势强度({characteristics['trend_strength']:.1%}): +25分 (强趋势适合)")
        elif characteristics['trend_strength'] > 0.2:
            dca_score += 15
            dca_details.append(f"趋势强度({characteristics['trend_strength']:.1%}): +15分 (中等趋势)")
        else:
            dca_score += 5
            dca_details.append(f"趋势强度({characteristics['trend_strength']:.1%}): +5分 (弱趋势)")
            
        # 夏普比率评分
        if characteristics['sharpe_ratio'] > 0.5:  # 高夏普比率
            dca_score += 20
            dca_details.append(f"夏普比率({characteristics['sharpe_ratio']:.3f}): +20分 (高夏普比率)")
        else:
            dca_details.append(f"夏普比率({characteristics['sharpe_ratio']:.3f}): +0分 (较低夏普比率)")
            
        # 价格稳定性评分
        if characteristics['price_cv'] < 0.3:  # 价格稳定
            dca_score += 15
            dca_details.append(f"价格变异系数({characteristics['price_cv']:.3f}): +15分 (价格稳定)")
        else:
            dca_details.append(f"价格变异系数({characteristics['price_cv']:.3f}): +0分 (价格不够稳定)")
            
        # RSI评分
        if characteristics['rsi_avg'] < 60:  # RSI适中
            dca_score += 10
            dca_details.append(f"RSI均值({characteristics['rsi_avg']:.1f}): +10分 (RSI适中)")
        else:
            dca_details.append(f"RSI均值({characteristics['rsi_avg']:.1f}): +0分 (RSI偏高)")
            
        strategy_scores['dca'] = min(dca_score, 100)
        
        if self.verbose:
            print(f"\n📊 DCA策略评分明细:")
            for detail in dca_details:
                print(f"  {detail}")
            print(f"  总分: {strategy_scores['dca']}/100")
        
        # 网格策略评分
        grid_score = 0
        if 0.2 < characteristics['volatility'] < 0.6:  # 中等波动率适合网格
            grid_score += 30
        elif characteristics['volatility'] < 0.8:
            grid_score += 20
        else:
            grid_score += 10
            
        if characteristics['trend_strength'] < 0.3:  # 弱趋势适合网格
            grid_score += 25
        elif characteristics['trend_strength'] < 0.6:
            grid_score += 15
        else:
            grid_score += 5
            
        if characteristics['price_cv'] > 0.2:  # 价格波动适中
            grid_score += 20
            
        if 40 < characteristics['rsi_avg'] < 70:  # RSI在合理区间
            grid_score += 15
            
        if characteristics['volume_volatility'] < 1.0:  # 成交量稳定
            grid_score += 10
            
        strategy_scores['grid'] = min(grid_score, 100)
        
        # 动量策略评分 - 改进评分逻辑
        momentum_score = 0
        
        # 波动率要求更高（动量策略需要剧烈波动）
        if characteristics['volatility'] > 0.5:  # 高波动率适合动量
            momentum_score += 25
        elif characteristics['volatility'] > 0.3:
            momentum_score += 15
        elif characteristics['volatility'] > 0.2:
            momentum_score += 8
        else:
            momentum_score += 2  # 低波动率严重不适合
            
        # 趋势强度要求（但不是长期稳定趋势）
        if characteristics['trend_strength'] > 0.6:  # 非常强趋势
            momentum_score += 30
        elif characteristics['trend_strength'] > 0.4:  # 强趋势
            momentum_score += 25
        elif characteristics['trend_strength'] > 0.2:
            momentum_score += 15
        else:
            momentum_score += 5
            
        # 成交量活跃度（动量策略需要高流动性）
        if characteristics['volume_volatility'] > 1.0:  # 成交量高度活跃
            momentum_score += 20
        elif characteristics['volume_volatility'] > 0.7:
            momentum_score += 15
        elif characteristics['volume_volatility'] > 0.5:
            momentum_score += 10
        else:
            momentum_score += 3
            
        # RSI波动（技术指标敏感性）
        if characteristics['rsi_std'] > 15:  # RSI波动大
            momentum_score += 15
        elif characteristics['rsi_std'] > 10:
            momentum_score += 10
        else:
            momentum_score += 5
            
        # 价格变异系数（价格不稳定性）
        if characteristics['price_cv'] > 0.3:  # 价格高度不稳定
            momentum_score += 10
        elif characteristics['price_cv'] > 0.2:
            momentum_score += 5
        else:
            momentum_score += 0  # 价格稳定不适合动量策略
            
        # 白马股惩罚机制（稳定性强的股票不适合动量策略）
        if (characteristics['volatility'] < 0.25 and 
            characteristics['price_cv'] < 0.15 and 
            characteristics['rsi_std'] < 12):
            momentum_score = max(momentum_score - 30, 10)  # 白马股特征惩罚
            
        strategy_scores['momentum'] = min(momentum_score, 100)
        
        # 均线交叉策略评分
        ma_crossover_score = 0
        
        # 趋势强度要求（均线交叉需要适中的趋势性）
        if 0.15 < characteristics['trend_strength'] < 0.6:  # 适中趋势适合均线交叉
            ma_crossover_score += 30
        elif 0.1 < characteristics['trend_strength'] < 0.8:
            ma_crossover_score += 20
        else:
            ma_crossover_score += 10
            
        # 波动率要求（需要适中波动率）
        if 0.2 < characteristics['volatility'] < 0.4:  # 适中波动率
            ma_crossover_score += 25
        elif 0.15 < characteristics['volatility'] < 0.5:
            ma_crossover_score += 20
        elif characteristics['volatility'] < 0.6:
            ma_crossover_score += 15
        else:
            ma_crossover_score += 5  # 过高波动率不适合
            
        # RSI波动性（技术指标敏感性）
        if 12 < characteristics['rsi_std'] < 20:  # 适中的RSI波动
            ma_crossover_score += 20
        elif 8 < characteristics['rsi_std'] < 25:
            ma_crossover_score += 15
        else:
            ma_crossover_score += 10
            
        # 价格变异系数（适度的价格波动）
        if 0.1 < characteristics['price_cv'] < 0.25:  # 适度价格波动
            ma_crossover_score += 15
        elif characteristics['price_cv'] < 0.35:
            ma_crossover_score += 10
        else:
            ma_crossover_score += 5
            
        # 成交量活跃度
        if 0.4 < characteristics['volume_volatility'] < 0.8:  # 适中成交量波动
            ma_crossover_score += 10
        elif characteristics['volume_volatility'] < 1.0:
            ma_crossover_score += 5
        else:
            ma_crossover_score += 3
            
        strategy_scores['ma_crossover'] = min(ma_crossover_score, 100)
        
        print(f"\n🎯 策略适配性评分:")
        print("=" * 60)
        print(f"DCA策略: {strategy_scores['dca']}/100")
        print(f"网格策略: {strategy_scores['grid']}/100")
        print(f"动量策略: {strategy_scores['momentum']}/100")
        print(f"均线交叉策略: {strategy_scores['ma_crossover']}/100")
        
        # 动量策略详细解释
        if strategy_scores['momentum'] < 50:
            print(f"\n💡 动量策略评分较低的原因:")
            reasons = []
            if characteristics['volatility'] < 0.3:
                reasons.append(f"- 波动率偏低({characteristics['volatility']:.1%})，动量策略需要>30%的波动率")
            if characteristics['trend_strength'] < 0.4:
                reasons.append(f"- 趋势强度不足({characteristics['trend_strength']:.1%})，缺乏动量策略需要的价格加速度")
            if characteristics['price_cv'] < 0.15:
                reasons.append(f"- 价格过于稳定({characteristics['price_cv']:.3f})，属于白马股特征")
            if characteristics['rsi_std'] < 12:
                reasons.append(f"- RSI波动偏小({characteristics['rsi_std']:.1f})，技术指标敏感性不足")
            if characteristics['volume_volatility'] < 0.5:
                reasons.append(f"- 成交量波动偏低({characteristics['volume_volatility']:.3f})，流动性不够活跃")
            
            for reason in reasons:
                print(reason)
            
            print(f"\n🔍 {self.symbol} 更适合长期投资策略，如DCA定投或价值投资")
        
        return strategy_scores
    
    def recommendOptimalParameters(self, strategy_scores: Dict, characteristics: Dict) -> Dict:
        """推荐最优参数"""
        recommendations = {}
        
        # 基于股票特征推荐参数
        if self.stockData is not None:
            avg_price = self.stockData['close'].mean()
            volatility = self.stockData['daily_return'].std() * np.sqrt(252)
            
            # DCA策略推荐
            if strategy_scores['dca'] > 70:
                recommendations['dca'] = {
                    'interval': 'monthly',
                    'amount': int(avg_price * 100),  # 约1手股票
                    'base_ratio': 0.6,
                    'max_position': 100000,
                    'reason': f'{self.symbol}波动率适中，趋势稳定，适合定期定额投资'
                }
            
            # 网格策略推荐
            if strategy_scores['grid'] > 70:
                grid_spacing = max(0.02, min(0.05, volatility / 10))  # 基于波动率调整
                recommendations['grid'] = {
                    'grid_levels': 8,
                    'grid_spacing': grid_spacing,
                    'base_ratio': 0.4,
                    'max_position': 80000,
                    'commission': 0.0003,
                    'slippage': 0.001,
                    'reason': f'{self.symbol}价格波动适中，建议{grid_spacing:.1%}网格间距'
                }
            
            # 动量策略推荐
            if strategy_scores['momentum'] > 70:
                recommendations['momentum'] = {
                    'lookback_period': 20,
                    'threshold': max(0.03, volatility / 20),
                    'base_ratio': 0.2,
                    'max_position': 50000,
                    'reason': f'{self.symbol}有一定趋势性，适合动量策略'
                }
            
            # 均线交叉策略推荐
            if strategy_scores['ma_crossover'] > 60:
                recommendations['ma_crossover'] = {
                    'ma_short': 5,
                    'ma_long': 10,
                    'base_ratio': 0.8,
                    'max_position': 60000,
                    'commission': 0.0003,
                    'slippage': 0.001,
                    'min_volume_ratio': 1.0,
                    'reason': f'{self.symbol}趋势适中，波动合理，适合均线交叉策略'
                }
        
        return recommendations
    
    def generateVisualizations(self, output_dir: str = None) -> None:
        """生成可视化图表"""
        if self.stockData is None:
            return
        
        # 创建输出目录
        if output_dir is None:
            output_dir = f"reports/stock_analysis_{self.symbol}"
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 设置图表样式
        plt.style.use('seaborn-v0_8')
        fig_size = (12, 8)
        
        # 1. 价格走势图
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['close'], label='收盘价', linewidth=2)
        plt.plot(self.stockData.index, self.stockData['MA20'], label='MA20', alpha=0.7)
        plt.plot(self.stockData.index, self.stockData['MA60'], label='MA60', alpha=0.7)
        plt.fill_between(self.stockData.index, self.stockData['BB_upper'], 
                        self.stockData['BB_lower'], alpha=0.2, label='布林带')
        plt.title(f'{self.symbol} 价格走势与技术指标', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('价格 (元)')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / f'{self.symbol}_price_trend.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 收益率分布
        plt.figure(figsize=fig_size)
        returns = self.stockData['daily_return'].dropna()
        plt.hist(returns, bins=50, alpha=0.7, edgecolor='black')
        plt.axvline(returns.mean(), color='red', linestyle='--', label=f'均值: {returns.mean():.3f}')
        plt.axvline(returns.std(), color='orange', linestyle='--', label=f'标准差: {returns.std():.3f}')
        plt.title(f'{self.symbol} 日收益率分布', fontsize=14, fontweight='bold')
        plt.xlabel('日收益率')
        plt.ylabel('频次')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(output_path / f'{self.symbol}_return_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. 波动率变化
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['volatility_20d'], linewidth=2)
        plt.axhline(self.stockData['volatility_20d'].mean(), color='red', linestyle='--', 
                   label=f'平均波动率: {self.stockData["volatility_20d"].mean():.2%}')
        plt.title(f'{self.symbol} 20日滚动波动率', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('年化波动率')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / f'{self.symbol}_volatility.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 4. RSI指标
        plt.figure(figsize=fig_size)
        plt.plot(self.stockData.index, self.stockData['RSI'], linewidth=2)
        plt.axhline(70, color='red', linestyle='--', alpha=0.7, label='超买线')
        plt.axhline(30, color='green', linestyle='--', alpha=0.7, label='超卖线')
        plt.axhline(50, color='gray', linestyle='-', alpha=0.5, label='中线')
        plt.title(f'{self.symbol} RSI指标', fontsize=14, fontweight='bold')
        plt.xlabel('日期')
        plt.ylabel('RSI')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(output_path / f'{self.symbol}_rsi.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"📊 可视化图表已保存到: {output_path}")
    
    def generateReport(self, characteristics: Dict, strategy_scores: Dict, 
                      recommendations: Dict, output_file: str = None) -> None:
        """生成分析报告"""
        if output_file is None:
            output_file = f"reports/stock_strategy_report_{self.symbol}.md"
        
        # 确保输出目录存在
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成报告内容
        report_content = f"""# {self.symbol} 策略适配性分析报告

## 📊 股票基本信息
- **股票代码**: {self.symbol}
- **股票名称**: {self.config.get('name', self.symbol)}
- **行业**: {self.config.get('industry', '未知')}
- **风险等级**: {self.config.get('riskLevel', 'medium')}
- **分析期间**: {self.stockData.index[0].strftime('%Y-%m-%d')} 至 {self.stockData.index[-1].strftime('%Y-%m-%d')}
- **交易天数**: {len(self.stockData)} 天

## 📈 股票特征分析

### 收益特征
- **总收益率**: {characteristics['total_return']:.2%}
- **年化收益率**: {characteristics['annual_return']:.2%}
- **年化波动率**: {characteristics['volatility']:.2%}
- **最大回撤**: {characteristics['max_drawdown']:.2%}
- **夏普比率**: {characteristics['sharpe_ratio']:.3f}

### 价格特征
- **平均价格**: ¥{characteristics['avg_price']:.2f}
- **价格区间**: {characteristics['price_range']:.2%}
- **价格变异系数**: {characteristics['price_cv']:.3f}

### 技术特征
- **趋势强度**: {characteristics['trend_strength']:.2%}
- **RSI均值**: {characteristics['rsi_avg']:.1f}
- **RSI标准差**: {characteristics['rsi_std']:.1f}
- **成交量波动率**: {characteristics['volume_volatility']:.3f}
- **市场环境**: {characteristics['market_environment']}

## 🎯 策略适配性评分

| 策略类型 | 适配性评分 | 推荐等级 | 说明 |
|----------|------------|----------|------|
| DCA策略 | {strategy_scores['dca']}/100 | {'⭐' * (strategy_scores['dca'] // 20)} | {'非常适合' if strategy_scores['dca'] > 80 else '适合' if strategy_scores['dca'] > 60 else '一般' if strategy_scores['dca'] > 40 else '不适合'} |
| 网格策略 | {strategy_scores['grid']}/100 | {'⭐' * (strategy_scores['grid'] // 20)} | {'非常适合' if strategy_scores['grid'] > 80 else '适合' if strategy_scores['grid'] > 60 else '一般' if strategy_scores['grid'] > 40 else '不适合'} |
|| 动量策略 | {strategy_scores['momentum']}/100 | {'⭐' * (strategy_scores['momentum'] // 20)} | {'非常适合' if strategy_scores['momentum'] > 80 else '适合' if strategy_scores['momentum'] > 60 else '一般' if strategy_scores['momentum'] > 40 else '不适合'} |
|| 均线交叉策略 | {strategy_scores['ma_crossover']}/100 | {'⭐' * (strategy_scores['ma_crossover'] // 20)} | {'非常适合' if strategy_scores['ma_crossover'] > 80 else '适合' if strategy_scores['ma_crossover'] > 60 else '一般' if strategy_scores['ma_crossover'] > 40 else '不适合'} |
|
## 💡 策略推荐

"""
        
        # 添加策略推荐
        for strategy, params in recommendations.items():
            strategy_name = {'dca': 'DCA策略', 'grid': '网格策略', 'momentum': '动量策略', 'ma_crossover': '均线交叉策略'}[strategy]
            report_content += f"""
### {strategy_name}
**推荐理由**: {params['reason']}

**推荐参数**:
"""
            for key, value in params.items():
                if key != 'reason':
                    if isinstance(value, float):
                        report_content += f"- {key}: {value:.3f}\n"
                    else:
                        report_content += f"- {key}: {value}\n"
        
        report_content += f"""
## 📊 投资建议

### 1. 策略优先级
1. **首选策略**: {max(strategy_scores, key=strategy_scores.get).upper()}
2. **备选策略**: {sorted(strategy_scores.items(), key=lambda x: x[1], reverse=True)[1][0].upper()}

### 2. 风险控制建议
- 建议最大回撤控制在 {abs(characteristics['max_drawdown'] * 0.8):.1%} 以内
- 夏普比率目标: {max(1.0, characteristics['sharpe_ratio'] * 1.2):.2f}
- 单次投资金额不超过总资金的 20%

### 3. 市场环境适配
- **震荡市场**: 优先考虑网格策略
- **趋势市场**: 优先考虑DCA策略
- **高波动市场**: 谨慎使用动量策略

## 📈 可视化图表
相关图表已生成并保存到 `reports/stock_analysis_{self.symbol}/` 目录。

---
*报告生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        # 保存报告
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 分析报告已保存到: {output_path}")
    
    def analyze_stock(self, symbol: str) -> Dict:
        """通用股票分析方法，返回股票分析结果"""
        self.loadStockData(symbol)
        if self.stockData is not None and not self.stockData.empty:
            characteristics = self.analyzeStockCharacteristics()
            return characteristics
        return {}

def main():
    """主函数"""
    import sys
    import argparse
    
    # 设置命令行参数
    parser = argparse.ArgumentParser(description='股票策略适配性分析工具')
    parser.add_argument('symbol', help='股票代码 (例: 002594.SZ)')
    parser.add_argument('--verbose', '-v', action='store_true', 
                       help='显示详细的评分计算过程')
    parser.add_argument('--detail', '-d', action='store_true',
                       help='显示详细的评分计算过程 (与--verbose相同)')
    
    # 解析参数
    args = parser.parse_args()
    
    # 详细模式标志
    verbose = args.verbose or args.detail
    
    symbol = args.symbol
    
    print(f"🚀 股票策略适配性分析工具启动")
    if verbose:
        print("🔍 详细模式: 开启")
    print("=" * 60)
    
    # 创建分析器
    analyzer = StockStrategyAnalyzer(verbose=verbose)
    
    # 加载数据
    analyzer.loadStockData(symbol)
    analyzer.loadConfig(symbol)
    
    if analyzer.stockData is None:
        print("❌ 无法加载股票数据")
        return
    
    # 执行分析
    print("\n" + "="*60)
    print(f"📊 开始 {symbol} 策略适配性分析")
    print("="*60)
    
    # 分析股票特征
    characteristics = analyzer.analyzeStockCharacteristics()
    
    # 分析策略适配性
    strategy_scores = analyzer.analyzeStrategyCompatibility(characteristics)
    
    # 推荐最优参数
    recommendations = analyzer.recommendOptimalParameters(strategy_scores, characteristics)
    
    # 生成可视化
    analyzer.generateVisualizations()
    
    # 生成报告
    analyzer.generateReport(characteristics, strategy_scores, recommendations)
    
    print("\n✅ 分析完成！")
    print(f"📊 可视化图表: reports/stock_analysis_{symbol}/")
    print(f"📄 详细报告: reports/stock_strategy_report_{symbol}.md")

if __name__ == "__main__":
    main() 