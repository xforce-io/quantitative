#!/usr/bin/env python3
"""
自适应网格交易策略 - 基于机器学习的参数优化
Adaptive Grid Trading Strategy with ML-based Parameter Optimization
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
import joblib
import os

from .unified_grid_strategy import UnifiedGridTradingStrategy
from ..engines.strategy_optimizer import StrategyOptimizer, ParameterSpace
from ..config.config import Config

class AdaptiveGridStrategy(UnifiedGridTradingStrategy):
    """
    自适应网格策略 - 通过机器学习自动优化参数
    """
    
    def __init__(self, symbol: str, config: Dict = None):
        """
        初始化自适应网格策略
        
        Args:
            symbol: 股票代码
            config: 策略配置
        """
        super().__init__(symbol, config)
        
        # ML相关配置
        self.enable_learning = self.config.get('enable_learning', True)
        self.learning_lookback_days = self.config.get('learning_lookback_days', 60)
        self.min_learning_samples = self.config.get('min_learning_samples', 30)
        self.model_update_frequency = self.config.get('model_update_frequency', 5)  # 每5天更新一次模型
        
        # 特征工程参数
        self.feature_window = self.config.get('feature_window', 20)
        
        # 模型和预处理器
        self.model: Optional[RandomForestRegressor] = None
        self.scaler: Optional[StandardScaler] = None
        self.last_model_update: Optional[pd.Timestamp] = None
        
        # 参数历史记录
        self.parameter_history: List[Dict] = []
        self.performance_history: List[float] = []
        
        # 当前自适应参数
        self.adaptive_params = {
            'adjustmentThreshold': self.adjustmentThreshold,
            'minAdjustmentRatio': self.minAdjustmentRatio,
            'adjustmentCooldown': self.adjustmentCooldown,
            'centerPricePeriod': self.centerPricePeriod
        }
        
        self.logger = logging.getLogger(__name__)
        
    def _extract_market_features(self, prices: pd.Series) -> Dict[str, float]:
        """
        提取市场特征用于预测最优参数
        
        Args:
            prices: 价格序列
            
        Returns:
            特征字典
        """
        if len(prices) < self.feature_window:
            return {}
            
        recent_prices = prices.tail(self.feature_window)
        
        # 基础统计特征
        features = {
            # 价格趋势特征
            'price_change_1d': (prices.iloc[-1] - prices.iloc[-2]) / prices.iloc[-2] if len(prices) >= 2 else 0,
            'price_change_5d': (prices.iloc[-1] - prices.iloc[-6]) / prices.iloc[-6] if len(prices) >= 6 else 0,
            'price_change_10d': (prices.iloc[-1] - prices.iloc[-11]) / prices.iloc[-11] if len(prices) >= 11 else 0,
            'price_change_20d': (prices.iloc[-1] - prices.iloc[-21]) / prices.iloc[-21] if len(prices) >= 21 else 0,
            
            # 波动性特征
            'volatility_5d': recent_prices.pct_change().tail(5).std() * np.sqrt(252),
            'volatility_10d': recent_prices.pct_change().tail(10).std() * np.sqrt(252),
            'volatility_20d': recent_prices.pct_change().std() * np.sqrt(252),
            
            # 趋势强度特征
            'trend_strength': self._calculate_trend_strength(recent_prices),
            'momentum': self._calculate_momentum(recent_prices),
            
            # 均值回归特征
            'distance_from_ma5': (prices.iloc[-1] - recent_prices.tail(5).mean()) / recent_prices.tail(5).mean(),
            'distance_from_ma10': (prices.iloc[-1] - recent_prices.tail(10).mean()) / recent_prices.tail(10).mean(),
            'distance_from_ma20': (prices.iloc[-1] - recent_prices.mean()) / recent_prices.mean(),
            
            # 当前价格相对位置
            'price_position_in_range': (prices.iloc[-1] - recent_prices.min()) / (recent_prices.max() - recent_prices.min()) if recent_prices.max() != recent_prices.min() else 0.5,
            
            # 交易量特征（如果有的话）
            'avg_volume_ratio': 1.0,  # 暂时使用默认值
        }
        
        return features
    
    def _calculate_trend_strength(self, prices: pd.Series) -> float:
        """计算趋势强度"""
        if len(prices) < 5:
            return 0.0
            
        # 使用线性回归斜率表示趋势强度
        x = np.arange(len(prices))
        coeffs = np.polyfit(x, prices.values, 1)
        trend_slope = coeffs[0]
        
        # 标准化为百分比形式
        return trend_slope / prices.mean()
    
    def _calculate_momentum(self, prices: pd.Series) -> float:
        """计算动量指标"""
        if len(prices) < 10:
            return 0.0
            
        # ROC (Rate of Change) 动量指标
        roc = (prices.iloc[-1] - prices.iloc[-10]) / prices.iloc[-10]
        return roc
    
    def _should_update_model(self, timestamp: pd.Timestamp) -> bool:
        """判断是否需要更新模型"""
        if not self.enable_learning:
            return False
            
        if self.last_model_update is None:
            return True
            
        days_since_update = (timestamp - self.last_model_update).days
        return days_since_update >= self.model_update_frequency
    
    def _prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """准备训练数据"""
        if len(self.parameter_history) < self.min_learning_samples:
            return None, None
            
        # 构建特征矩阵
        X = []
        y = []
        
        for i, params in enumerate(self.parameter_history):
            if i < len(self.performance_history):
                # 特征：参数 + 市场状态
                feature_row = [
                    params['adjustmentThreshold'],
                    params['minAdjustmentRatio'], 
                    params['adjustmentCooldown'],
                    params['centerPricePeriod'],
                    params.get('volatility_20d', 0),
                    params.get('trend_strength', 0),
                    params.get('momentum', 0),
                    params.get('price_position_in_range', 0.5)
                ]
                X.append(feature_row)
                y.append(self.performance_history[i])
        
        return np.array(X), np.array(y)
    
    def _train_parameter_model(self, timestamp: pd.Timestamp):
        """训练参数预测模型"""
        X, y = self._prepare_training_data()
        
        if X is None or len(X) < self.min_learning_samples:
            self.logger.info(f"Not enough samples for training ({len(X) if X is not None else 0})")
            return
            
        try:
            # 时间序列交叉验证
            tscv = TimeSeriesSplit(n_splits=3)
            
            # 训练随机森林模型
            self.model = RandomForestRegressor(
                n_estimators=50,
                max_depth=6,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42
            )
            
            # 标准化特征
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
            
            # 训练模型
            self.model.fit(X_scaled, y)
            
            # 评估模型性能
            cv_scores = []
            for train_idx, val_idx in tscv.split(X_scaled):
                X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
                y_train, y_val = y[train_idx], y[val_idx]
                
                temp_model = RandomForestRegressor(
                    n_estimators=50,
                    max_depth=6,
                    min_samples_split=5,
                    min_samples_leaf=2,
                    random_state=42
                )
                temp_model.fit(X_train, y_train)
                score = temp_model.score(X_val, y_val)
                cv_scores.append(score)
            
            avg_cv_score = np.mean(cv_scores) if cv_scores else 0
            self.logger.info(f"Model trained successfully. CV Score: {avg_cv_score:.3f}")
            
            self.last_model_update = timestamp
            
            # 保存模型
            self._save_model()
            
        except Exception as e:
            self.logger.error(f"Error training model: {str(e)}")
    
    def _predict_optimal_parameters(self, market_features: Dict[str, float]) -> Dict[str, float]:
        """预测最优参数"""
        if self.model is None or self.scaler is None:
            return self.adaptive_params.copy()
            
        try:
            # 使用当前参数作为基线尝试不同的参数组合
            base_features = [
                self.adaptive_params['adjustmentThreshold'],
                self.adaptive_params['minAdjustmentRatio'],
                self.adaptive_params['adjustmentCooldown'],
                self.adaptive_params['centerPricePeriod'],
                market_features.get('volatility_20d', 0),
                market_features.get('trend_strength', 0),
                market_features.get('momentum', 0),
                market_features.get('price_position_in_range', 0.5)
            ]
            
            # 生成参数候选组合
            param_candidates = []
            
            # 调整阈值候选值
            threshold_candidates = [0.04, 0.06, 0.08, 0.10, 0.12, 0.15]
            ratio_candidates = [0.02, 0.03, 0.05, 0.07, 0.10]
            cooldown_candidates = [1, 3, 5, 7, 10]
            period_candidates = [10, 15, 20, 25, 30]
            
            best_score = float('-inf')
            best_params = self.adaptive_params.copy()
            
            # 评估不同参数组合
            for threshold in threshold_candidates:
                for ratio in ratio_candidates:
                    for cooldown in cooldown_candidates:
                        for period in period_candidates:
                            candidate_features = base_features.copy()
                            candidate_features[0] = threshold
                            candidate_features[1] = ratio
                            candidate_features[2] = cooldown
                            candidate_features[3] = period
                            
                            # 预测这组参数的表现
                            features_scaled = self.scaler.transform([candidate_features])
                            predicted_score = self.model.predict(features_scaled)[0]
                            
                            if predicted_score > best_score:
                                best_score = predicted_score
                                best_params = {
                                    'adjustmentThreshold': threshold,
                                    'minAdjustmentRatio': ratio,
                                    'adjustmentCooldown': cooldown,
                                    'centerPricePeriod': period
                                }
            
            self.logger.info(f"Predicted optimal parameters: {best_params}")
            self.logger.info(f"Predicted score: {best_score:.3f}")
            
            return best_params
            
        except Exception as e:
            self.logger.error(f"Error predicting parameters: {str(e)}")
            return self.adaptive_params.copy()
    
    def _save_model(self):
        """保存模型到文件"""
        try:
            model_dir = f"models/{self.symbol}"
            os.makedirs(model_dir, exist_ok=True)
            
            if self.model is not None:
                joblib.dump(self.model, f"{model_dir}/adaptive_grid_model.joblib")
            if self.scaler is not None:
                joblib.dump(self.scaler, f"{model_dir}/adaptive_grid_scaler.joblib")
                
        except Exception as e:
            self.logger.error(f"Error saving model: {str(e)}")
    
    def _load_model(self):
        """从文件加载模型"""
        try:
            model_dir = f"models/{self.symbol}"
            model_path = f"{model_dir}/adaptive_grid_model.joblib"
            scaler_path = f"{model_dir}/adaptive_grid_scaler.joblib"
            
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                self.logger.info("Loaded existing model")
                
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
                self.logger.info("Loaded existing scaler")
                
        except Exception as e:
            self.logger.error(f"Error loading model: {str(e)}")
    
    def _update_adaptive_parameters(self, timestamp: pd.Timestamp, currentPrice: float):
        """更新自适应参数"""
        if not self.enable_learning:
            return
            
        # 提取当前市场特征
        prices = pd.Series([p['price'] for p in self.priceHistory])
        market_features = self._extract_market_features(prices)
        
        # 检查是否需要更新模型
        if self._should_update_model(timestamp):
            self._train_parameter_model(timestamp)
        
        # 预测最优参数
        if self.model is not None:
            new_params = self._predict_optimal_parameters(market_features)
            
            # 平滑参数更新（避免过于频繁的变化）
            smoothing_factor = 0.3
            for key in self.adaptive_params:
                if key in new_params:
                    self.adaptive_params[key] = (
                        smoothing_factor * new_params[key] + 
                        (1 - smoothing_factor) * self.adaptive_params[key]
                    )
            
            # 更新策略参数
            self.adjustmentThreshold = self.adaptive_params['adjustmentThreshold']
            self.minAdjustmentRatio = self.adaptive_params['minAdjustmentRatio']
            self.adjustmentCooldown = int(self.adaptive_params['adjustmentCooldown'])
            self.centerPricePeriod = int(self.adaptive_params['centerPricePeriod'])
            
            # 记录参数变化
            param_record = market_features.copy()
            param_record.update(self.adaptive_params)
            self.parameter_history.append(param_record)
            
            self.logger.info(f"Updated adaptive parameters: {self.adaptive_params}")
    
    def _record_performance(self, performance_score: float):
        """记录策略表现"""
        self.performance_history.append(performance_score)
        
        # 限制历史记录长度
        max_history = 100
        if len(self.performance_history) > max_history:
            self.performance_history = self.performance_history[-max_history:]
            self.parameter_history = self.parameter_history[-max_history:]
    
    def processPrice(self, timestamp: pd.Timestamp, price: float) -> List[Dict]:
        """
        处理价格数据 - 增加自适应参数更新
        """
        # 更新自适应参数
        self._update_adaptive_parameters(timestamp, price)
        
        # 调用父类方法处理价格
        trades = super().processPrice(timestamp, price)
        
        # 记录表现（这里使用简单的收益率作为表现指标）
        if len(self.priceHistory) > 1:
            recent_return = (price - self.priceHistory[-2]['price']) / self.priceHistory[-2]['price']
            portfolio_return = self._calculate_portfolio_return()
            performance_score = portfolio_return - recent_return  # 超额收益
            self._record_performance(performance_score)
        
        return trades
    
    def _calculate_portfolio_return(self) -> float:
        """计算组合收益率"""
        if not self.priceHistory or len(self.priceHistory) < 2:
            return 0.0
            
        # 简化的组合收益计算
        current_value = self.currentCash + self.currentShares * self.priceHistory[-1]['price']
        initial_value = self.maxPosition
        
        return (current_value - initial_value) / initial_value
    
    def initialize(self):
        """初始化策略 - 加载已有模型"""
        super().initialize()
        
        # 尝试加载已有模型
        self._load_model()
        
        self.logger.info(f"Adaptive Grid Strategy initialized for {self.symbol}")
        self.logger.info(f"Learning enabled: {self.enable_learning}")
        self.logger.info(f"Initial adaptive parameters: {self.adaptive_params}") 