"""AVSHUNTER rebuild package.

Bounded contexts of the governed rebuild (specification v1.1). Domain modules
are pure: no pandas, files, SQLite, HTTP or wall clock outside ``adapters``.
The legacy pipeline is not imported from here except through explicit,
documented reuse.
"""

__version__ = "0.1.0"
