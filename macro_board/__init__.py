"""Standalone ETF macro decision board.

Reads AVSHUNTER data stores and macro outputs read-only and renders a self-contained HTML
board. It is not a pipeline input: nothing in the pipeline reads it, and it writes only
under ``macro_board/output``.
"""

BOARD_VERSION = "macro-board-v1.0.0"
