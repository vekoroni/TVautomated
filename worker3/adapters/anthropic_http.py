"""Opt-in bounded HTTPS transport. No retries, redirects or credential logging."""
import hashlib
import http.client
import json
import os
import time
from anthropic_runtime_config import workspace_id as configured_workspace_id

from ..application import _pairs, _constant
from ..domain import ContractError, canonical, digest


def _record_provider_error(receipt, response, max_response_bytes):
    """Record the provider's own error type and message on a non-2xx receipt.

    AVS-FIX-001 W4.2 (RCA3-D01). Reads at most 8 KiB -- enough for any error
    envelope, small enough that a hostile or malfunctioning endpoint cannot
    turn an error path into a memory problem. Never raises: a receipt with no
    diagnosis is worse than one with a partial diagnosis, but neither is worth
    losing the original error over. Response HEADERS are never read or stored.
    """
    try:
        raw = response.read(min(8192, max_response_bytes))
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        error = payload.get("error") if type(payload) is dict else None
        if type(error) is dict:
            error_type = error.get("type")
            message = error.get("message")
            receipt["error_type"] = error_type if type(error_type) is str else None
            receipt["error_message"] = message[:500] if type(message) is str else None
    except Exception:
        # A body that is absent, truncated or not JSON is itself information;
        # the status code is already on the receipt.
        receipt["error_type"] = receipt.get("error_type") or "unparsable_error_body"


class AnthropicHTTP:
    def __init__(self, *, enabled=False, max_calls=1, max_input_bytes=100000,
                 max_output_tokens=2048, max_response_bytes=500000):
        if type(enabled) is not bool:
            raise ContractError("explicit live opt-in required")
        for value in (max_calls, max_input_bytes, max_output_tokens, max_response_bytes):
            if type(value) is not int or value <= 0:
                raise ContractError("positive transport budgets required")
        self.enabled = enabled
        self.max_calls = max_calls
        self.max_input_bytes = max_input_bytes
        self.max_output_tokens = max_output_tokens
        self.max_response_bytes = max_response_bytes
        self.calls = 0
        self.receipts = []

    def create(self, request, *, timeout_seconds):
        if not self.enabled:
            raise ContractError("live transport disabled")
        if self.calls >= self.max_calls:
            raise ContractError("live call budget exhausted; no automatic retries")
        if type(timeout_seconds) not in (float, int) or not 0 < timeout_seconds <= 300:
            raise ContractError("live timeout must be at most 300 seconds")
        if type(request) is not dict or set(request) not in (
                {"model", "max_tokens", "system", "messages"},
                {"model", "max_tokens", "system", "messages", "output_config"}):
            raise ContractError("unsupported live request fields (tools/streaming disabled)")
        if "output_config" in request:
            config = request["output_config"]
            if type(config) is not dict or set(config) != {"format"}:
                raise ContractError("unsupported structured output configuration")
            fmt = config["format"]
            if (type(fmt) is not dict or set(fmt) != {"type", "schema"}
                    or fmt["type"] != "json_schema" or type(fmt["schema"]) is not dict):
                raise ContractError("unsupported structured output format")
        if type(request["max_tokens"]) is not int or not 0 < request["max_tokens"] <= self.max_output_tokens:
            raise ContractError("output token budget exceeded")
        data = canonical(request).encode("utf-8")
        if len(data) > self.max_input_bytes:
            raise ContractError("live input byte budget exceeded")
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key or any(c in key for c in "\r\n"):
            raise ContractError("ANTHROPIC_API_KEY not available or invalid")
        # AVS-FIX-001 W4.2 (RCA3-D03). The 6 Sep incident could not be
        # diagnosed from the receipts because nothing recorded WHICH credential
        # the call used. The first eight hex characters of the key's SHA-256
        # identify it across a rotation without being reversible to it: 2^32
        # of the digest, from a 108-character secret. The source is recorded
        # too, because the whole failure was two sources with no documented
        # precedence.
        credential_source = "os.environ"
        credential_fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            headers["anthropic-workspace-id"] = configured_workspace_id()
        except RuntimeError as exc:
            raise ContractError(str(exc)) from None
        receipt = {"request_hash": digest(request), "model": request["model"], "status": "STARTED",
                   "http_status": None, "input_tokens": None, "output_tokens": None,
                   "usage_reported": None, "elapsed_ms": None,
                   # AVS-FIX-001 W4.2 (RCA3-D03): which credential, not the credential.
                   "credential_source": credential_source,
                   "credential_fingerprint": credential_fingerprint,
                   # AVS-FIX-001 W4.2 (RCA3-D01): provider error type and message.
                   "error_type": None, "error_message": None,
                   # AVS-FIX-001 W4.2 (RCA3-D02): whether this call spent budget.
                   "budget_consumed": False,
                   "failure_stage": None, "timeout_seconds": timeout_seconds}
        self.receipts.append(receipt)
        start = time.monotonic()
        connection = None
        failure_stage = "SENDING_REQUEST"
        try:
            connection = http.client.HTTPSConnection("api.anthropic.com", timeout=timeout_seconds)
            connection.request("POST", "/v1/messages", body=data, headers=headers)
            failure_stage = "AWAITING_HEADERS"
            response = connection.getresponse()
            receipt["http_status"] = response.status
            if response.status != 200:
                # AVS-FIX-001 W4.2 (RCA3-D01). The body was withheld entirely,
                # so a receipt recorded only "provider HTTP 400" -- which is
                # exactly the position the 6 Sep credential incident left the
                # operator in. The provider's own `error.type` and
                # `error.message` are diagnostic text about the REQUEST; they
                # are not, and cannot be, credential material, since the
                # credential only ever travels in a header. Headers are still
                # never recorded.
                receipt["status"] = "HTTP_ERROR"
                _record_provider_error(receipt, response, self.max_response_bytes)
                raise ContractError(
                    f"provider HTTP {response.status}"
                    f" ({receipt.get('error_type') or 'unknown_error'});"
                    " no retry"
                )
            failure_stage = "READING_RESPONSE"
            raw = response.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raise ContractError("provider response byte limit exceeded")
            failure_stage = "DECODING_RESPONSE"
            result = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
            canonical(result)
            if type(result) is not dict:
                raise ContractError("provider response must be an object")
            usage = result.get("usage", {})
            if type(usage) is dict:
                for field in ("input_tokens", "output_tokens"):
                    value = usage.get(field)
                    if type(value) is int and value >= 0:
                        receipt[field] = value
                # Only numeric counters, never provider error text or prompts.
                receipt["usage_reported"] = {k: v for k, v in usage.items() if type(v) is int and v >= 0}
            # AVS-FIX-001 W4.2 (RCA3-D02). The budget was decremented before
            # the request was even sent, so a run of transport failures
            # exhausted the allowance without a single answer -- and the
            # budget's purpose is to bound what is SPENT, not what is
            # attempted. It is now consumed here: a 2xx whose body decoded into
            # model output. Every other path leaves it untouched.
            self.calls += 1
            receipt["budget_consumed"] = True
            receipt["status"] = "RESPONSE_RECEIVED_NOT_VALIDATED"
            return result
        except ContractError:
            receipt["failure_stage"] = failure_stage
            if receipt["status"] == "STARTED":
                receipt["status"] = "INVALID_RESPONSE"
            raise
        except Exception as exc:
            receipt["status"] = "TRANSPORT_OR_DECODE_ERROR"
            receipt["failure_stage"] = failure_stage
            receipt["error_type"] = (
                "TIMEOUT" if isinstance(exc, TimeoutError) else
                "DECODE_ERROR" if failure_stage == "DECODING_RESPONSE" else
                "CONNECTION_ERROR"
            )
            raise ContractError("provider request failed; details withheld; no automatic retry") from None
        finally:
            receipt["elapsed_ms"] = round((time.monotonic() - start) * 1000)
            if connection is not None:
                connection.close()
