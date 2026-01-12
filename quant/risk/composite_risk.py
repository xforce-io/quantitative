#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Composite Risk Model
组合风控模型

Combines multiple risk models into a single model.
"""

from typing import Dict, List, Optional
import pandas as pd
from .base_risk_model import BaseRiskModel, RiskCheckResult


class CompositeRiskModel(BaseRiskModel):
    """
    Composite risk model that combines multiple risk models.
    
    Runs all component models sequentially and aggregates results.
    Position adjustments from earlier models are passed to later models.
    """
    
    def __init__(
        self,
        models: Optional[List[BaseRiskModel]] = None,
        name: Optional[str] = None
    ):
        """
        Initialize composite risk model.
        
        Args:
            models: List of risk models to combine
            name: Model name
        """
        super().__init__(name or "CompositeRisk")
        self.models = models or []
    
    def add_model(self, model: BaseRiskModel):
        """
        Add a risk model to the composite.
        
        Args:
            model: Risk model to add
        """
        self.models.append(model)
    
    def remove_model(self, model: BaseRiskModel):
        """
        Remove a risk model from the composite.
        
        Args:
            model: Risk model to remove
        """
        if model in self.models:
            self.models.remove(model)
    
    def check(
        self,
        positions: Dict[str, float],
        market_data: Optional[pd.DataFrame] = None,
        **kwargs
    ) -> RiskCheckResult:
        """
        Run all component models and aggregate results.
        
        Args:
            positions: Target positions {symbol: weight}
            market_data: Market data for calculations
            **kwargs: Additional parameters passed to component models
            
        Returns:
            Aggregated RiskCheckResult
        """
        if not self.models:
            # No models, just pass through
            return RiskCheckResult(
                passed=True,
                adjusted_positions=positions.copy(),
                violations=[],
                risk_metrics={'models_run': 0}
            )
        
        # Run models sequentially
        current_positions = positions.copy()
        all_violations = []
        all_metrics = {}
        overall_passed = True
        
        for model in self.models:
            result = model.check(current_positions, market_data, **kwargs)
            
            # Update positions for next model
            current_positions = result.adjusted_positions
            
            # Aggregate violations
            for violation in result.violations:
                all_violations.append(f"[{model.name}] {violation}")
            
            # Aggregate metrics
            all_metrics[model.name] = result.risk_metrics
            
            # Update overall status
            if not result.passed:
                overall_passed = False
        
        return RiskCheckResult(
            passed=overall_passed,
            adjusted_positions=current_positions,
            violations=all_violations,
            risk_metrics={
                'models_run': len(self.models),
                'model_results': all_metrics,
            }
        )
    
    def get_models(self) -> List[BaseRiskModel]:
        """Get list of component models."""
        return self.models.copy()
    
    def __len__(self) -> int:
        """Get number of component models."""
        return len(self.models)
    
    def __iter__(self):
        """Iterate over component models."""
        return iter(self.models)
