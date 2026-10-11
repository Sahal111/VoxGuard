"""VoxGuard shared contracts — event envelope, error format, correlation ID."""

from voxguard_contracts.events import EventEnvelope, EventType, Producer
from voxguard_contracts.errors import ErrorDetail, ErrorBody, ErrorResponse

__all__ = [
    "EventEnvelope",
    "EventType",
    "Producer",
    "ErrorDetail",
    "ErrorBody",
    "ErrorResponse",
]
