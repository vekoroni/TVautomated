"""Resolver-only CDS gateway skeleton; provider adapters arrive after CDS-1."""

from __future__ import annotations

from .contracts import DatasetRequest, DatasetResolution, ResolutionKind
from .errors import CanonicalDataDisabled, FetchNotAuthorised
from .feature_flags import CanonicalFeatureFlags
from .lifecycle import LifecycleManager
from .registry import CanonicalRegistry
from .request_ledger import RequestLedger, RequestResolution


class CanonicalDataGateway:
    """Enforces lifecycle before resolving canonical data.

    CDS-1 intentionally performs no provider calls. A miss is returned to the
    caller for later phases to handle through governed adapters.
    """

    def __init__(
        self,
        registry: CanonicalRegistry,
        lifecycle: LifecycleManager,
        ledger: RequestLedger,
        *,
        flags: CanonicalFeatureFlags | None = None,
    ):
        self.registry = registry
        self.lifecycle = lifecycle
        self.ledger = ledger
        self.flags = flags or CanonicalFeatureFlags.from_environment()

    def resolve(self, request: DatasetRequest) -> DatasetResolution:
        if not self.flags.enabled:
            raise CanonicalDataDisabled(
                "canonical data gateway is disabled; production path is unchanged"
            )
        authorise = (
            self.lifecycle.authorise_worklist
            if self.flags.stage_gating_enforced
            else self.lifecycle.authorise
        )
        decision = authorise(
            request.run_id,
            request.requesting_stage,
            request.instrument_id,
            request.dataset_type,
        )
        if not decision.authorised:
            self.ledger.record_blocked(request, decision.reason)
            raise FetchNotAuthorised(decision.reason)

        request_id = self.ledger.start(request)
        resolution = self.registry.resolve(request)
        ledger_resolution = {
            ResolutionKind.EXACT_HIT: RequestResolution.CACHE_HIT,
            ResolutionKind.SUPERSET_HIT: RequestResolution.SUPERSET_HIT,
            ResolutionKind.PARTIAL_HIT: RequestResolution.PARTIAL_HIT,
            ResolutionKind.MISS: RequestResolution.CACHE_MISS,
        }[resolution.kind]
        self.ledger.finish(
            request_id,
            ledger_resolution,
            dataset_id=resolution.records[0].dataset_id
            if len(resolution.records) == 1
            else None,
            physical_request_count=0,
            reason=resolution.reason,
        )
        return resolution
