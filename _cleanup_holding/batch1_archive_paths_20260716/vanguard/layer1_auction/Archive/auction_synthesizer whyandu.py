
class AuctionState:
    def __init__(self, state, confidence, reasoning):
        self.state = state
        self.confidence = confidence
        self.reasoning = reasoning


class AuctionSynthesizer:

    def __init__(self,
                 min_acceptance_score=50,
                 min_control_confidence=0.6,
                 min_migration_confidence=0.5):

        self.min_acceptance_score = min_acceptance_score
        self.min_control_confidence = min_control_confidence
        self.min_migration_confidence = min_migration_confidence

    def synthesize(self, acceptance_score, control_result, migration_result):

        reasons = []

        # Strict confidence gating (FIX)
        if control_result.confidence < self.min_control_confidence:
            reasons.append("[FAIL] Control confidence too weak")
            return AuctionState("NOT_READY", control_result.confidence, reasons)

        if migration_result["confidence"] < self.min_migration_confidence:
            reasons.append("[FAIL] Migration confidence too weak")
            return AuctionState("NOT_READY", migration_result["confidence"], reasons)

        if acceptance_score < self.min_acceptance_score:
            reasons.append("[FAIL] Acceptance below threshold")
            return AuctionState("NOT_READY", acceptance_score / 100, reasons)

        reasons.append("[PASS] Control strong")
        reasons.append("[PASS] Migration aligned")
        reasons.append("[PASS] Acceptance sufficient")

        composite_conf = (
            (control_result.confidence * 0.4) +
            (migration_result["confidence"] * 0.3) +
            (acceptance_score / 100 * 0.3)
        )

        return AuctionState("ALIGNED", composite_conf, reasons)


# Backwards-compatibility aliases
# Pipeline imports AuctionStateSynthesizer from this module
AuctionStateSynthesizer  = AuctionSynthesizer   # confirmed by import error
AuctionSynthesizerEngine = AuctionSynthesizer   # defensive alias
