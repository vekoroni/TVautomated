"""Isolated AVSHUNTER feedback bridge package.

This package must remain outside the AVSHUNTER execution pipeline. Pipeline code
may write CSV/JSON outputs; bridge code may read them and write bridge-local
state or dropbox feedback files, but AVSHUNTER must not import bridge modules.
"""

