from __future__ import annotations

from dataclasses import dataclass
import unittest

import build_macro_json


@dataclass
class _Block:
    text: str


class _Response:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class _Client:
    def __init__(self, responses):
        self.messages = _Messages(responses)


class MacroResponseRepairTests(unittest.TestCase):
    def test_transport_fences_and_trailing_text_are_removed(self):
        value = build_macro_json._parse_macro_response(
            'Here is the object:\n```json\n{"regime_state":"NEUTRAL"}\n```\nDone.'
        )
        self.assertEqual(value["regime_state"], "NEUTRAL")

    def test_one_bounded_api_repair_recovers_invalid_json(self):
        client = _Client([
            _Response("identity"),
            _Response("analysis"),
            _Response('{"regime_state": nope}', "end_turn"),
            _Response('{"regime_state":"TRANSITIONAL"}', "end_turn"),
        ])
        original = build_macro_json._anthropic_client
        build_macro_json._anthropic_client = lambda: client
        try:
            value = build_macro_json.call_macro_api("fixture")
        finally:
            build_macro_json._anthropic_client = original
        self.assertEqual(value["regime_state"], "TRANSITIONAL")
        self.assertEqual(len(client.messages.calls), 4)
        self.assertIn("syntax corrected only", client.messages.calls[-1]["messages"][-1]["content"])

    def test_second_invalid_response_fails_closed(self):
        client = _Client([
            _Response("identity"), _Response("analysis"),
            _Response('{"a": nope}'), _Response('{"a": still_nope}'),
        ])
        original = build_macro_json._anthropic_client
        build_macro_json._anthropic_client = lambda: client
        try:
            with self.assertRaisesRegex(RuntimeError, "bounded repair attempt"):
                build_macro_json.call_macro_api("fixture")
        finally:
            build_macro_json._anthropic_client = original


if __name__ == "__main__":
    unittest.main()
