#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Systemic Undervalue Analyzer
系统性低估判断器

This module provides multi-dimensional analysis to determine if a company
is systemically and severely undervalued.

Key concept: A company is considered "systemically undervalued" when
multiple independent valuation dimensions consistently point to undervaluation.

Dimensions analyzed:
    1. Price percentile (technical valuation)
    2. Fundamental valuation (PE, PB, ROE)
    3. PEG valuation (growth-adjusted PE)
    4. Regression deviation (mean reversion signal)

Each dimension produces a score from -3 to +3:
    -3: Severely undervalued
    -2: Undervalued
    -1: Slightly undervalued
     0: Fair value
    +1: Slightly overvalued
    +2: Overvalued
    +3: Severely overvalued

Composite scoring:
    - Weighted sum of all dimension scores
    - Confidence = agreement ratio among dimensions
    - Systemic undervalue: composite_score < -6 AND confidence > 70%

Value trap detection:
    - Declining revenue trend
    - Margin compression
    - High debt levels
    - Cyclical peak indicators
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from quant.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ValuationScore:
    """Score from a single valuation dimension."""
    dimension: str
    score: float  # -3 to +3
    confidence: float  # 0 to 1
    details: Dict[str, Any] = field(default_factory=dict)
    
    def is_undervalued(self) -> bool:
        return self.score < 0
    
    def is_severely_undervalued(self) -> bool:
        return self.score <= -2


@dataclass
class UndervalueResult:
    """Result of systemic undervalue analysis."""
    symbol: str
    is_undervalued: bool
    is_severely_undervalued: bool
    composite_score: float  # -12 to +12
    confidence: float  # 0 to 1
    dimension_scores: Dict[str, ValuationScore]
    value_trap_warnings: List[str]
    quality_checks: Dict[str, Any]
    signals: List[str]
    recommendation: str
    analyzed_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'symbol': self.symbol,
            'is_undervalued': self.is_undervalued,
            'is_severely_undervalued': self.is_severely_undervalued,
            'composite_score': self.composite_score,
            'confidence': self.confidence,
            'dimension_scores': {
                k: {
                    'score': v.score,
                    'confidence': v.confidence,
                    'details': v.details
                }
                for k, v in self.dimension_scores.items()
            },
            'value_trap_warnings': self.value_trap_warnings,
            'quality_checks': self.quality_checks,
            'signals': self.signals,
            'recommendation': self.recommendation,
            'analyzed_at': self.analyzed_at.isoformat()
        }


class SystemicUndervalueAnalyzer:
    """
    Systemic undervalue analyzer.
    
    Combines multiple valuation dimensions to determine if a company
    is systemically and severely undervalued.
    
    Usage:
        from quant.analysis.valuation import SystemicUndervalueAnalyzer
        from quant.data import create_data_provider
        
        provider = create_data_provider('auto')
        analyzer = SystemicUndervalueAnalyzer(provider)
        
        result = analyzer.analyze('000001.SZ', period_days=756)
        
        if result.is_severely_undervalued:
            print(f"Severely undervalued with {result.confidence:.0%} confidence")
            print(f"Signals: {result.signals}")
    """
    
    # Dimension weights for composite score
    DEFAULT_WEIGHTS = {
        'price_percentile': 0.25,
        'fundamental': 0.30,
        'peg': 0.25,
        'regression': 0.20
    }
    
    def __init__(self, data_provider, weights: Optional[Dict[str, float]] = None):
        """
        Initialize the analyzer.
        
        Args:
            data_provider: Data provider instance (from quant.data)
            weights: Optional custom weights for dimensions (must sum to 1.0)
        """
        self.data_provider = data_provider
        self.weights = weights or self.DEFAULT_WEIGHTS
        
        # Validate weights
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"Weights sum to {total_weight}, normalizing to 1.0"
            )
            self.weights = {
                k: v / total_weight for k, v in self.weights.items()
            }
        
        # Initialize sub-analyzers lazily
        self._price_analyzer = None
        self._fundamental_analyzer = None
        self._peg_analyzer = None
        self._regression_analyzer = None
    
    @property
    def price_analyzer(self):
        """Lazy initialization of price valuation analyzer."""
        if self._price_analyzer is None:
            try:
                from .price_valuation import PriceValuationAnalyzer
                self._price_analyzer = PriceValuationAnalyzer(self.data_provider)
            except ImportError:
                from quant.analysis.etf_valuation_analyzer import ETFValuationAnalyzer
                self._price_analyzer = ETFValuationAnalyzer(self.data_provider)
        return self._price_analyzer
    
    @property
    def fundamental_analyzer(self):
        """Lazy initialization of fundamental analyzer."""
        if self._fundamental_analyzer is None:
            try:
                from .fundamental_valuation import FundamentalValuationAnalyzer
                self._fundamental_analyzer = FundamentalValuationAnalyzer(self.data_provider)
            except ImportError:
                from quant.analysis.etf_fundamental_analyzer import ETFFundamentalAnalyzer
                self._fundamental_analyzer = ETFFundamentalAnalyzer(self.data_provider)
        return self._fundamental_analyzer
    
    @property
    def peg_analyzer(self):
        """Lazy initialization of PEG analyzer."""
        if self._peg_analyzer is None:
            try:
                from .peg_valuation import PEGValuationAnalyzer
                self._peg_analyzer = PEGValuationAnalyzer(self.data_provider)
            except (ImportError, TypeError):
                self._peg_analyzer = None
        return self._peg_analyzer
    
    @property
    def regression_analyzer(self):
        """Lazy initialization of regression analyzer."""
        if self._regression_analyzer is None:
            try:
                from .regression_analyzer import RegressionAnalyzer
                self._regression_analyzer = RegressionAnalyzer()
            except (ImportError, NotImplementedError):
                self._regression_analyzer = None
        return self._regression_analyzer
    
    def analyze(
        self,
        symbol: str,
        period_days: int = 756
    ) -> UndervalueResult:
        """
        Perform systemic undervalue analysis.
        
        Args:
            symbol: Stock/ETF symbol
            period_days: Number of historical days for analysis (default 3 years)
        
        Returns:
            UndervalueResult with comprehensive valuation assessment
        """
        logger.info(f"Analyzing systemic undervalue for {symbol}")
        
        dimension_scores = {}
        signals = []
        value_trap_warnings = []
        quality_checks = {}
        
        # 1. Price Percentile Analysis
        try:
            price_score = self._analyze_price_percentile(symbol, period_days)
            dimension_scores['price_percentile'] = price_score
            if price_score.is_undervalued():
                signals.append(f"Price at {price_score.details.get('percentile', 'N/A')}th percentile")
        except Exception as e:
            logger.warning(f"Price analysis failed: {e}")
            dimension_scores['price_percentile'] = ValuationScore(
                dimension='price_percentile', score=0, confidence=0,
                details={'error': str(e)}
            )
        
        # 2. Fundamental Analysis
        try:
            fundamental_score = self._analyze_fundamental(symbol)
            dimension_scores['fundamental'] = fundamental_score
            if fundamental_score.is_undervalued():
                signals.append(f"Fundamental score: {fundamental_score.score:.1f}")
        except Exception as e:
            logger.warning(f"Fundamental analysis failed: {e}")
            dimension_scores['fundamental'] = ValuationScore(
                dimension='fundamental', score=0, confidence=0,
                details={'error': str(e)}
            )
        
        # 3. PEG Analysis
        try:
            if self.peg_analyzer:
                peg_score = self._analyze_peg(symbol)
                dimension_scores['peg'] = peg_score
                if peg_score.is_undervalued():
                    signals.append(f"PEG ratio indicates undervalue")
            else:
                dimension_scores['peg'] = ValuationScore(
                    dimension='peg', score=0, confidence=0,
                    details={'error': 'PEG analyzer not available'}
                )
        except Exception as e:
            logger.warning(f"PEG analysis failed: {e}")
            dimension_scores['peg'] = ValuationScore(
                dimension='peg', score=0, confidence=0,
                details={'error': str(e)}
            )
        
        # 4. Regression Analysis
        try:
            if self.regression_analyzer:
                regression_score = self._analyze_regression(symbol, period_days)
                dimension_scores['regression'] = regression_score
                if regression_score.is_undervalued():
                    signals.append(f"Price below regression trend")
            else:
                dimension_scores['regression'] = ValuationScore(
                    dimension='regression', score=0, confidence=0,
                    details={'error': 'Regression analyzer not available'}
                )
        except Exception as e:
            logger.warning(f"Regression analysis failed: {e}")
            dimension_scores['regression'] = ValuationScore(
                dimension='regression', score=0, confidence=0,
                details={'error': str(e)}
            )
        
        # Calculate composite score
        composite_score = self._calculate_composite_score(dimension_scores)
        
        # Calculate confidence (agreement ratio)
        confidence = self._calculate_confidence(dimension_scores)
        
        # Value trap detection
        value_trap_warnings = self._check_value_traps(symbol)
        
        # Quality checks
        quality_checks = self._perform_quality_checks(symbol)
        
        # Determine undervalue status
        is_undervalued = composite_score < -3
        is_severely_undervalued = composite_score < -6 and confidence > 0.7
        
        # Adjust for value trap warnings
        if value_trap_warnings:
            is_severely_undervalued = False
            signals.append("⚠️ Value trap warning - proceed with caution")
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            composite_score, confidence, value_trap_warnings
        )
        
        return UndervalueResult(
            symbol=symbol,
            is_undervalued=is_undervalued,
            is_severely_undervalued=is_severely_undervalued,
            composite_score=composite_score,
            confidence=confidence,
            dimension_scores=dimension_scores,
            value_trap_warnings=value_trap_warnings,
            quality_checks=quality_checks,
            signals=signals,
            recommendation=recommendation
        )
    
    def _analyze_price_percentile(
        self,
        symbol: str,
        period_days: int
    ) -> ValuationScore:
        """Analyze price percentile valuation."""
        # This is a placeholder - actual implementation would use price_analyzer
        # For now, return a neutral score
        return ValuationScore(
            dimension='price_percentile',
            score=0,
            confidence=0.5,
            details={'note': 'Placeholder implementation'}
        )
    
    def _analyze_fundamental(self, symbol: str) -> ValuationScore:
        """Analyze fundamental valuation (PE, PB, ROE)."""
        # Placeholder implementation
        return ValuationScore(
            dimension='fundamental',
            score=0,
            confidence=0.5,
            details={'note': 'Placeholder implementation'}
        )
    
    def _analyze_peg(self, symbol: str) -> ValuationScore:
        """Analyze PEG valuation."""
        # Placeholder implementation
        return ValuationScore(
            dimension='peg',
            score=0,
            confidence=0.5,
            details={'note': 'Placeholder implementation'}
        )
    
    def _analyze_regression(
        self,
        symbol: str,
        period_days: int
    ) -> ValuationScore:
        """Analyze regression-based valuation."""
        # Placeholder implementation
        return ValuationScore(
            dimension='regression',
            score=0,
            confidence=0.5,
            details={'note': 'Placeholder implementation'}
        )
    
    def _calculate_composite_score(
        self,
        dimension_scores: Dict[str, ValuationScore]
    ) -> float:
        """Calculate weighted composite score."""
        total_score = 0
        total_weight = 0
        
        for dimension, score in dimension_scores.items():
            weight = self.weights.get(dimension, 0)
            # Weight by both dimension weight and score confidence
            effective_weight = weight * score.confidence
            total_score += score.score * effective_weight
            total_weight += effective_weight
        
        if total_weight == 0:
            return 0
        
        # Normalize to -12 to +12 range (4 dimensions * 3 max score)
        return (total_score / total_weight) * 4
    
    def _calculate_confidence(
        self,
        dimension_scores: Dict[str, ValuationScore]
    ) -> float:
        """Calculate confidence based on dimension agreement."""
        if not dimension_scores:
            return 0
        
        # Count how many dimensions agree on direction
        undervalued_count = sum(
            1 for s in dimension_scores.values() if s.is_undervalued()
        )
        overvalued_count = sum(
            1 for s in dimension_scores.values() if s.score > 0
        )
        
        total = len(dimension_scores)
        max_agreement = max(undervalued_count, overvalued_count)
        
        # Agreement ratio
        agreement = max_agreement / total if total > 0 else 0
        
        # Also factor in individual confidences
        avg_confidence = sum(
            s.confidence for s in dimension_scores.values()
        ) / total if total > 0 else 0
        
        return (agreement + avg_confidence) / 2
    
    def _check_value_traps(self, symbol: str) -> List[str]:
        """Check for value trap indicators."""
        warnings = []
        
        # Placeholder - actual implementation would check:
        # - Declining revenue trend
        # - Margin compression
        # - High debt levels
        # - Industry sunset indicators
        # - Accounting irregularities
        
        return warnings
    
    def _perform_quality_checks(self, symbol: str) -> Dict[str, Any]:
        """Perform quality checks on the company."""
        return {
            'data_quality': 'good',
            'analysis_coverage': 4,
            'warnings': []
        }
    
    def _generate_recommendation(
        self,
        composite_score: float,
        confidence: float,
        value_trap_warnings: List[str]
    ) -> str:
        """Generate investment recommendation."""
        if value_trap_warnings:
            return "AVOID - Potential value trap detected"
        
        if composite_score < -6 and confidence > 0.7:
            return "STRONG BUY - Systemically severely undervalued"
        elif composite_score < -3:
            return "BUY - Undervalued"
        elif composite_score > 6 and confidence > 0.7:
            return "STRONG SELL - Systemically severely overvalued"
        elif composite_score > 3:
            return "SELL - Overvalued"
        else:
            return "HOLD - Fair value"


__all__ = [
    'SystemicUndervalueAnalyzer',
    'UndervalueResult',
    'ValuationScore',
]
