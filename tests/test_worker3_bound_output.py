import copy
import json
import re
import unittest
from unittest.mock import Mock, patch

from worker3.adapters.bound_output import output_schema
from worker3.adapters.anthropic_http import AnthropicHTTP
from worker3.domain import ContractError
from worker3.integration.current_canary import count_frozen_request, counted_cost_ceiling, MODEL


class BoundOutputTests(unittest.TestCase):
    def setUp(self):
        self.contract = {'authority': 'ADVISORY_ONLY', 'identity': {'ticker': 'TEST'},
                         'claims': [], 'sections': [{'section': 'SUMMARY'}], 'numeric_facts': []}
        self.catalog = {}
        for ref, value, kind, unit, status in (
            ('current:hash:price', 10.5, 'OBSERVATION', 'USD', 'AVAILABLE'),
            ('prior:hash:price', 9, 'OBSERVATION', 'USD', 'AVAILABLE'),
            ('change:hash', 1.5, 'CHANGE', 'USD', 'AVAILABLE'),
            ('scenario:hash', 'SATISFIED', 'SCENARIO', 'state', 'AVAILABLE'),
            ('state', 'STRONG', 'OBSERVATION', 'state', 'AVAILABLE'),
            ('numeric_string', '10.5', 'OBSERVATION', 'USD', 'AVAILABLE'),
            ('boolean', True, 'OBSERVATION', 'flag', 'AVAILABLE'),
            ('document', 10, 'OBSERVATION', 'structured_json', 'AVAILABLE'),
            ('missing', 10, 'OBSERVATION', 'USD', 'UNAVAILABLE'),
            ('literal.a[1]', 3, 'OBSERVATION', 'USD', 'AVAILABLE'),
        ):
            self.catalog[ref] = dict(value=value, kind=kind, unit=unit, status=status)
        self.schema = output_schema(self.contract, self.catalog)
        self.pattern = self.schema['properties']['claims']['items']['properties']['text']['pattern']

    def test_valid_numeric_historical_change_scenario_slots(self):
        for ref in ('current:hash:price', 'prior:hash:price', 'change:hash', 'scenario:hash', 'literal.a[1]'):
            self.assertIsNotNone(re.fullmatch(self.pattern, 'Observed {{slot:' + ref + '}}.'))

    def test_categorical_unavailable_boolean_document_and_unknown_slots_rejected(self):
        for ref in ('state', 'numeric_string', 'boolean', 'document', 'missing', 'unknown', 'literalXa1'):
            self.assertIsNone(re.fullmatch(self.pattern, '{{slot:' + ref + '}}'))

    def test_raw_digits_and_malformed_slots_rejected(self):
        for text in ('EV3 rejected.', 'Value 10.5.', 'Value \u0663.', '{{slot:state}', 'Unexpected {brace}'):
            self.assertIsNone(re.fullmatch(self.pattern, text))
        self.assertIsNotNone(re.fullmatch(self.pattern, 'Evidence is qualitative.'))

    def test_summary_cannot_emit_slots_or_digits(self):
        pattern = self.schema['properties']['sections']['items']['properties']['summary']['pattern']
        self.assertIsNone(re.fullmatch(pattern, '{{slot:current:hash:price}}'))
        self.assertIsNone(re.fullmatch(pattern, 'EV3'))
        self.assertIsNotNone(re.fullmatch(pattern, 'See the cited claims.'))

    def test_identity_and_numeric_types_are_constrained(self):
        self.assertEqual(self.schema['properties']['identity']['properties']['ticker']['const'], 'TEST')
        facts = self.schema['properties']['numeric_facts']['items']['properties']
        self.assertEqual(facts['value']['type'], 'number')
        self.assertNotIn('numeric_string', facts['evidence_id']['enum'])
        self.assertFalse(self.schema['additionalProperties'])

    def test_empty_catalog_is_valid_and_permits_only_qualitative_text(self):
        schema = output_schema(self.contract, {})
        pattern = schema['properties']['claims']['items']['properties']['text']['pattern']
        self.assertIsNone(re.fullmatch(pattern, '{{slot:unknown}}'))
        self.assertIsNotNone(re.fullmatch(pattern, 'No evidence available.'))

    def test_preflight_includes_schema_and_binds_its_fingerprint(self):
        request = dict(model=MODEL, max_tokens=8192, system='test', messages=[],
                       output_config={'format': {'type': 'json_schema', 'schema': self.schema}})
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b'{"input_tokens": 80000}'
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'fixture-only', 'ANTHROPIC_WORKSPACE_ID': ''}):
            receipt = count_frozen_request(request, connection_factory=lambda *a, **k: connection)
        sent = json.loads(connection.request.call_args.kwargs['body'])
        self.assertEqual(sent['output_config'], request['output_config'])
        altered = copy.deepcopy(request)
        altered['output_config']['format']['schema']['properties']['authority']['const'] = 'CHANGED'
        with self.assertRaisesRegex(ContractError, 'changed'):
            counted_cost_ceiling(altered, receipt)
        self.assertEqual(connection.request.call_count, 1)

    def test_transport_rejects_unapproved_output_options_without_network(self):
        base = dict(model=MODEL, max_tokens=10, system='test', messages=[])
        for config in ({'effort': 'high'}, {'format': {'type': 'text', 'schema': {}}}, {'format': None}):
            transport = AnthropicHTTP(enabled=True)
            with patch('socket.socket.connect', side_effect=AssertionError('network prohibited')):
                with self.assertRaisesRegex(ContractError, 'structured output'):
                    transport.create(dict(base, output_config=config), timeout_seconds=10)
            self.assertEqual(transport.calls, 0)
    def test_transport_sends_structured_schema_unchanged_once(self):
        request = dict(model=MODEL, max_tokens=10, system='test', messages=[],
                       output_config={'format': {'type': 'json_schema', 'schema': self.schema}})
        connection = Mock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b'{"usage":{"input_tokens":10,"output_tokens":2}}'
        transport = AnthropicHTTP(enabled=True)
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'fixture-only', 'ANTHROPIC_WORKSPACE_ID': ''}), patch('worker3.adapters.anthropic_http.http.client.HTTPSConnection', return_value=connection):
            transport.create(request, timeout_seconds=10)
            with self.assertRaisesRegex(ContractError, 'budget exhausted'):
                transport.create(request, timeout_seconds=10)
        sent = json.loads(connection.request.call_args.kwargs['body'])
        self.assertEqual(sent['output_config'], request['output_config'])
        self.assertEqual(connection.request.call_count, 1)
