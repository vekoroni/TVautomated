"""Compatibility façade for the long-option execution domain.

Business policy lives in ``domain.long_option_execution``. Existing imports
remain stable while infrastructure and presentation layers migrate gradually.
"""

from domain.long_option_execution import *  # noqa: F401,F403
