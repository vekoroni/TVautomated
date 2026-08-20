"""
VANGUARD Layer 2 - Statistical Edge Package
State calculation, actuarial query, and edge detection
"""

from .state_calculator import StateVectorCalculator
from .actuarial_query import ActuarialQueryEngine
from .edge_detector import EdgeDetector

__all__ = [
    'StateVectorCalculator',
    'ActuarialQueryEngine',
    'EdgeDetector'
]
