"""Domain exceptions for the AVSHUNTER canonical data control plane."""


class CanonicalDataError(RuntimeError):
    """Base error for canonical data operations."""


class CanonicalDataDisabled(CanonicalDataError):
    """Raised when callers use the gateway while CDS is disabled."""


class DatasetValidationError(CanonicalDataError, ValueError):
    """Raised when a request or dataset violates the canonical contract."""


class FetchNotAuthorised(CanonicalDataError):
    """Raised when lifecycle policy forbids a stage from requesting data."""


class IllegalLifecycleTransition(CanonicalDataError):
    """Raised when a ticker lifecycle transition is not allowed."""


class LifecycleConcurrencyError(CanonicalDataError):
    """Raised when optimistic lifecycle version checking fails."""


class WorklistViolation(CanonicalDataError):
    """Raised when stage data contains a ticker outside its governed worklist."""


class PayloadConflictError(CanonicalDataError):
    """Raised when a payload path already contains different content."""
