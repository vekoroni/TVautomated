"""AVS-FIX-001 W4.2 — Worker 3 transport receipts (RCA3-D01, D02, D03).

Three defects the auth RCA found in `worker3/adapters/anthropic_http.py`, all
of which contributed to the 6 September credential incident being
undiagnosable from the artefacts it left:

* **D01** the provider's error body was withheld entirely, so a receipt said
  only "provider HTTP 400" and nothing about why.
* **D02** the call budget was decremented before the request was even sent, so
  a run of transport failures exhausted the allowance without one answer.
* **D03** nothing recorded WHICH credential a call used, so a rotation could
  not be told apart from a failure.

No live call is made anywhere in this file.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from worker3.adapters.anthropic_http import AnthropicHTTP
from worker3.domain import ContractError

SECRET = "sk-ant-api03-" + "x" * 95
BODY = json.dumps({
    "id": "msg_1", "type": "message", "role": "assistant",
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 4, "output_tokens": 6},
}).encode()


class TransportReceiptTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.connection.getresponse.return_value.status = 200
        self.connection.getresponse.return_value.read.return_value = BODY
        self.request = {
            "model": "claude-sonnet-4-5", "max_tokens": 16,
            "system": "s", "messages": [{"role": "user", "content": "hello"}],
        }

    def call(self, transport):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SECRET}), patch(
            "worker3.adapters.anthropic_http.http.client.HTTPSConnection",
            return_value=self.connection,
        ):
            return transport.create(self.request, timeout_seconds=10)

    def error_body(self, error_type, message):
        self.connection.getresponse.return_value.read.return_value = json.dumps(
            {"type": "error", "error": {"type": error_type, "message": message}}
        ).encode()

    # ---------------------------------------------------------------- D01

    def test_error_type_and_message_are_recorded(self):
        self.connection.getresponse.return_value.status = 400
        self.error_body("invalid_request_error", "max_tokens: must be >= 1")
        transport = AnthropicHTTP(enabled=True)
        with self.assertRaises(ContractError):
            self.call(transport)
        receipt = transport.receipts[-1]
        self.assertEqual(receipt["http_status"], 400)
        self.assertEqual(receipt["error_type"], "invalid_request_error")
        self.assertEqual(receipt["error_message"], "max_tokens: must be >= 1")

    def test_the_raised_error_names_the_provider_type(self):
        self.connection.getresponse.return_value.status = 401
        self.error_body("authentication_error", "invalid x-api-key")
        with self.assertRaises(ContractError) as context:
            self.call(AnthropicHTTP(enabled=True))
        self.assertIn("401", str(context.exception))
        self.assertIn("authentication_error", str(context.exception))

    def test_an_unparsable_error_body_is_named_not_lost(self):
        self.connection.getresponse.return_value.status = 500
        self.connection.getresponse.return_value.read.return_value = b"<html>502</html>"
        transport = AnthropicHTTP(enabled=True)
        with self.assertRaises(ContractError):
            self.call(transport)
        self.assertEqual(transport.receipts[-1]["error_type"], "unparsable_error_body")

    def test_a_successful_call_records_no_error(self):
        transport = AnthropicHTTP(enabled=True)
        self.call(transport)
        self.assertIsNone(transport.receipts[-1]["error_type"])
        self.assertIsNone(transport.receipts[-1]["error_message"])

    def test_response_headers_are_never_recorded(self):
        self.connection.getresponse.return_value.status = 429
        self.connection.getresponse.return_value.getheaders.return_value = [
            ("x-api-key", SECRET), ("retry-after", "30"),
        ]
        self.error_body("rate_limit_error", "slow down")
        transport = AnthropicHTTP(enabled=True)
        with self.assertRaises(ContractError):
            self.call(transport)
        recorded = json.dumps(transport.receipts)
        self.assertNotIn("retry-after", recorded)
        self.assertNotIn("x-api-key", recorded)

    def test_a_long_error_message_is_bounded(self):
        self.connection.getresponse.return_value.status = 400
        self.error_body("invalid_request_error", "e" * 5000)
        transport = AnthropicHTTP(enabled=True)
        with self.assertRaises(ContractError):
            self.call(transport)
        self.assertLessEqual(len(transport.receipts[-1]["error_message"]), 500)

    # ---------------------------------------------------------------- D02

    def test_a_non_2xx_does_not_consume_the_budget(self):
        for status in (400, 401, 429, 500, 302):
            with self.subTest(status=status):
                self.connection.getresponse.return_value.status = status
                self.error_body("api_error", "upstream")
                transport = AnthropicHTTP(enabled=True, max_calls=1)
                with self.assertRaises(ContractError):
                    self.call(transport)
                self.assertEqual(transport.calls, 0)
                self.assertIs(transport.receipts[-1]["budget_consumed"], False)

    def test_repeated_failures_leave_the_budget_intact(self):
        """The defect: a run of transport errors exhausted the allowance."""
        self.connection.getresponse.return_value.status = 500
        self.error_body("api_error", "upstream")
        transport = AnthropicHTTP(enabled=True, max_calls=1)
        for _ in range(5):
            with self.assertRaises(ContractError):
                self.call(transport)
        self.assertEqual(transport.calls, 0)
        # The budget survived, so a real answer is still affordable.
        self.connection.getresponse.return_value.status = 200
        self.connection.getresponse.return_value.read.return_value = BODY
        self.call(transport)
        self.assertEqual(transport.calls, 1)

    def test_a_2xx_with_model_output_does_consume_the_budget(self):
        transport = AnthropicHTTP(enabled=True, max_calls=1)
        self.call(transport)
        self.assertEqual(transport.calls, 1)
        self.assertIs(transport.receipts[-1]["budget_consumed"], True)
        with self.assertRaises(ContractError):
            self.call(transport)

    def test_a_2xx_whose_body_does_not_decode_does_not_consume_the_budget(self):
        """A 200 is not an answer until model output is actually in hand."""
        self.connection.getresponse.return_value.read.return_value = b"{"
        transport = AnthropicHTTP(enabled=True, max_calls=1)
        with self.assertRaises(ContractError):
            self.call(transport)
        self.assertEqual(transport.calls, 0)

    def test_the_budget_still_refuses_a_second_call(self):
        """D02 relaxes when the budget is spent, never whether it binds."""
        transport = AnthropicHTTP(enabled=True, max_calls=1)
        self.call(transport)
        with self.assertRaises(ContractError) as context:
            self.call(transport)
        self.assertIn("budget", str(context.exception).lower())

    # ---------------------------------------------------------------- D03

    def test_credential_source_and_fingerprint_are_recorded(self):
        transport = AnthropicHTTP(enabled=True)
        self.call(transport)
        receipt = transport.receipts[-1]
        self.assertEqual(receipt["credential_source"], "os.environ")
        self.assertEqual(len(receipt["credential_fingerprint"]), 8)
        self.assertTrue(
            all(character in "0123456789abcdef"
                for character in receipt["credential_fingerprint"])
        )

    def test_the_fingerprint_is_not_the_credential(self):
        transport = AnthropicHTTP(enabled=True)
        self.call(transport)
        recorded = json.dumps(transport.receipts)
        self.assertNotIn(SECRET, recorded)
        self.assertNotIn(SECRET[:24], recorded)
        self.assertNotIn(SECRET[-24:], recorded)

    def test_the_fingerprint_distinguishes_a_rotation(self):
        """The point of D03: a rotated key is visibly a different key."""
        fingerprints = set()
        for key in (SECRET, "sk-ant-api03-" + "y" * 95):
            transport = AnthropicHTTP(enabled=True)
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": key}), patch(
                "worker3.adapters.anthropic_http.http.client.HTTPSConnection",
                return_value=self.connection,
            ):
                transport.create(self.request, timeout_seconds=10)
            fingerprints.add(transport.receipts[-1]["credential_fingerprint"])
        self.assertEqual(len(fingerprints), 2)

    def test_the_same_key_fingerprints_identically(self):
        fingerprints = set()
        for _ in range(2):
            transport = AnthropicHTTP(enabled=True)
            self.call(transport)
            fingerprints.add(transport.receipts[-1]["credential_fingerprint"])
        self.assertEqual(len(fingerprints), 1)

    def test_a_failed_call_still_records_which_credential_it_used(self):
        """The 6 Sep case: the failing call is the one you need to identify."""
        self.connection.getresponse.return_value.status = 401
        self.error_body("authentication_error", "invalid x-api-key")
        transport = AnthropicHTTP(enabled=True)
        with self.assertRaises(ContractError):
            self.call(transport)
        receipt = transport.receipts[-1]
        self.assertEqual(receipt["credential_source"], "os.environ")
        self.assertEqual(len(receipt["credential_fingerprint"]), 8)


if __name__ == "__main__":
    unittest.main()
