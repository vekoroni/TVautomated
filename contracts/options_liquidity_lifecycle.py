"""Compatibility façade for the option contract-liquidity domain.

Business calculations live in ``domain.option_contract_liquidity``. Existing
producer and consumer imports remain stable during the DDD migration.
"""

from domain.option_contract_liquidity import *  # noqa: F401,F403
