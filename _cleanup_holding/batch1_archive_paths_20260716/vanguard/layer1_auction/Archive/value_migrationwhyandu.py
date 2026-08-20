
def evaluate_migration(current_vwap, previous_vwap):

    delta = current_vwap - previous_vwap

    if previous_vwap == 0:
        return {"direction": "FLAT", "confidence": 0.0}

    pct_change = abs(delta / previous_vwap)

    if pct_change < 0.002:
        return {"direction": "FLAT", "confidence": pct_change}

    direction = "UP" if delta > 0 else "DOWN"

    return {
        "direction": direction,
        "confidence": min(pct_change * 10, 1.0)  # scaled confidence
    }


class ValueMigrationTracker:
    """
    Backwards-compatibility class wrapper around evaluate_migration().

    The pipeline imports ValueMigrationTracker from this module.
    All logic remains in evaluate_migration() — this class delegates to it
    so both the function-based and class-based call patterns work correctly.
    """

    def evaluate(self, current_vwap: float, previous_vwap: float) -> dict:
        """Delegates to module-level evaluate_migration()."""
        return evaluate_migration(current_vwap, previous_vwap)

    def evaluate_migration(self, current_vwap: float, previous_vwap: float) -> dict:
        """Alias so callers using tracker.evaluate_migration() also work."""
        return evaluate_migration(current_vwap, previous_vwap)
