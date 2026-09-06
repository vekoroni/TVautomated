import json
import os
import unittest
from unittest.mock import patch, MagicMock

from worker3.adapters.anthropic_http import AnthropicHTTP
from worker3.domain import ContractError
from worker3.semantic import review_assessment
from test_assessment_v2 import initial, payload_for, response


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.request = {"model": "fixture-model", "max_tokens": 10, "system": "test", "messages": []}
        self.connection = MagicMock()
        self.connection.getresponse.return_value.status = 200
        self.connection.getresponse.return_value.read.return_value = b'{"usage":{"input_tokens":5,"output_tokens":6}}'

    def call(self, transport):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-secret"}), patch(
                "worker3.adapters.anthropic_http.http.client.HTTPSConnection", return_value=self.connection):
            return transport.create(self.request, timeout_seconds=10)

    def test_disabled_default(self):
        with self.assertRaises(ContractError): self.call(AnthropicHTTP())

    def test_success_usage_and_no_secret(self):
        transport = AnthropicHTTP(enabled=True)
        self.call(transport)
        self.assertEqual(transport.receipts[0]["output_tokens"], 6)
        self.assertNotIn("fake-secret", json.dumps(transport.receipts))
        self.connection.close.assert_called_once()

    def test_call_budget(self):
        transport = AnthropicHTTP(enabled=True); self.call(transport)
        with self.assertRaises(ContractError): self.call(transport)
        self.assertEqual(transport.calls, 1)

    def test_redirect_and_errors_not_followed(self):
        # AVS-FIX-001 W4.2 (RCA3-D02), T2: OBSOLETE_ASSERTION_CORRECTED.
        # The property under test is that a redirect or error is never
        # followed, and that is unchanged and still asserted. The incidental
        # `transport.calls == 1` encoded the retired policy that a non-2xx
        # spends the call budget. RCA3-D02 retires it: the budget bounds what
        # is SPENT, not what is attempted, so a run of transport failures must
        # not exhaust the allowance without a single answer. The assertion is
        # inverted to the new, stronger property.
        for status in (302,401,429,500):
            self.connection.getresponse.return_value.status = status
            transport = AnthropicHTTP(enabled=True)
            with self.subTest(status=status), self.assertRaises(ContractError): self.call(transport)
            self.assertEqual(transport.calls, 0)
            self.assertIs(transport.receipts[-1]["budget_consumed"], False)

    def test_response_limit(self):
        with self.assertRaises(ContractError): self.call(AnthropicHTTP(enabled=True,max_response_bytes=1))

    def test_bad_json_and_nonfinite(self):
        for value in (b'{',b'{"x":NaN}',b'{"x":1,"x":2}'):
            self.connection.getresponse.return_value.read.return_value=value
            with self.assertRaises(ContractError): self.call(AnthropicHTTP(enabled=True))

    def test_no_tools(self):
        self.request["tools"]=[]
        with self.assertRaises(ContractError): self.call(AnthropicHTTP(enabled=True))

    def test_missing_credentials(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY":""}):
            with self.assertRaises(ContractError): AnthropicHTTP(enabled=True).create(self.request,timeout_seconds=10)

    def test_timeout_error_sanitized(self):
        self.connection.request.side_effect = RuntimeError("fake-secret")
        with self.assertRaises(ContractError) as caught: self.call(AnthropicHTTP(enabled=True))
        self.assertNotIn("fake-secret",str(caught.exception))


class SemanticTests(unittest.TestCase):
    def review(self, text=None, kind="OBSERVATION"):
        ctx=initial(); payload=payload_for(ctx)
        if text: payload["claims"][0]["text"]=text
        payload["claims"][0]["claim_type"]=kind
        return review_assessment(ctx,response(ctx,payload))

    def test_clean_never_automatically_published(self):
        result=self.review()
        self.assertTrue(result.human_review_required)
        self.assertFalse(result.publication_ready)

    def test_unsupported_absorption(self):
        result=self.review("Absorption is confirmed.")
        self.assertEqual(result.status,"BLOCKED")
        self.assertTrue(any("WITHOUT_BEHAVIOUR" in s for s in result.findings))

    def test_no_news_not_inferred(self):
        self.assertIn("UNSUPPORTED_ABSENCE_CLAIM",self.review("No news affects this ticker.").findings)

    def test_phase_not_fabricated(self):
        self.assertIn("UNIMPLEMENTED_PHASE_OR_HISTORICAL_SUCCESS_CLAIM",self.review("Phase D is confirmed.").findings)

    def test_trade_command_blocked(self):
        self.assertEqual(self.review("Buy now.").status,"BLOCKED")

    def test_novel_hallucination_is_not_certified(self):
        result=self.review("Management has quietly improved its supply chain.")
        self.assertTrue(result.human_review_required)
        self.assertFalse(result.publication_ready)

    def behaviour_review(self, text):
        from dataclasses import replace
        from test_behaviour import evidence
        from worker3.behaviour import attach_behaviour
        from worker3.v2.assessment import AssessmentContext, build_evidence
        ctx=initial(); e=evidence()
        bundle=attach_behaviour(replace(ctx.job.bundle,evidence_cutoff_utc=e.cutoff),e)
        ctx=AssessmentContext(replace(ctx.job,bundle=bundle),ctx.scenarios)
        payload=payload_for(ctx)
        ref=next(k for k,v in build_evidence(ctx)["catalog"].items() if v.get("observation",{}).get("field")=="behaviour_report")
        payload["claims"][0].update(text=text,claim_type="HYPOTHESIS",supporting_evidence_ids=[ref])
        return review_assessment(ctx,response(ctx,payload))

    def test_control_contradiction_against_computed_report(self):
        result=self.behaviour_review("Sellers are in control.")
        self.assertTrue(any("CONTROL_CONTRADICTS" in f for f in result.findings))

    def test_matching_proxy_still_needs_human_review(self):
        result=self.behaviour_review("Buyers are in control as a provisional hypothesis.")
        self.assertFalse(any("CONTROL_CONTRADICTS" in f for f in result.findings))
        self.assertTrue(result.human_review_required)


if __name__ == "__main__": unittest.main()
