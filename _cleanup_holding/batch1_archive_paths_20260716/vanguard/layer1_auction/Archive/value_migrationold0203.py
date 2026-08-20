
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
