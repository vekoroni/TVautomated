
class ControlResult:
    def __init__(self, controller, confidence, buyer_pct):
        self.controller = controller
        self.confidence = confidence
        self.buyer_pct = buyer_pct


class ControlIdentifier:

    def __init__(self, strong_threshold=0.65):
        self.strong_threshold = strong_threshold

    def identify(self, buyer_volume, seller_volume):
        total = buyer_volume + seller_volume
        if total == 0:
            return ControlResult("NEUTRAL", 0.0, 0.5)

        buyer_pct = buyer_volume / total

        # FIXED THRESHOLD LOGIC
        if buyer_pct >= self.strong_threshold:
            controller = "BUYERS"
        elif buyer_pct <= (1 - self.strong_threshold):
            controller = "SELLERS"
        else:
            controller = "NEUTRAL"

        confidence = abs(buyer_pct - 0.5) * 2  # 0 → 1 scale

        return ControlResult(controller, confidence, buyer_pct)


# Backwards-compatibility alias
# ControlIdentifier is an exact match but add defensive variant
MarketControlIdentifier  = ControlIdentifier    # defensive alias
ControlIdentifierEngine  = ControlIdentifier    # defensive alias
