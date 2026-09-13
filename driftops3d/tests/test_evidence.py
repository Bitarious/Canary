"""Saved evidence and replay boundaries. No training or hardware collection."""
import copy
import hashlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driftops import cases, copilot
import server


class NoFleetReads:
    def __getattribute__(self, name):
        raise AssertionError(f"Unexpected fleet read: {name}")


class EvidenceTests(unittest.TestCase):
    def test_three_real_cases_and_input_hashes(self):
        bundle = cases.load_case_bundle()
        self.assertEqual(tuple(c['case_id'] for c in bundle['cases']), cases.CASE_IDS)
        for case in bundle['cases']:
            self.assertEqual(hashlib.sha256(json.dumps(case['model_inputs'], sort_keys=True).encode()).hexdigest(), case['inference']['input_sha256'])
            for field in ('failure_probability', 'failure_window', 'confidence'):
                self.assertIsNone(case['inference'][field])
            self.assertNotIn('evaluation_reference', case['model_inputs'])
        mismatch = bundle['cases'][2]
        self.assertFalse(mismatch['evaluation_reference']['exact_match'])
        self.assertIn('smart_194_raw: falling', mismatch['inference']['output_text'])
        self.assertNotEqual(mismatch['inference']['output_text'], mismatch['evaluation_reference']['weak_rule_target'])

    def test_unknown_case(self):
        with self.assertRaises(KeyError):
            cases.case_detail('../../secret')

    def test_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'case.json'
            path.write_bytes(cases.BUNDLE_PATH.read_bytes() + b' ')
            with self.assertRaises(cases.CaseBundleError):
                cases.load_case_bundle(path)

    def test_contract_rejects_corruption_even_with_updated_bundle_hash(self):
        original = json.loads(cases.BUNDLE_PATH.read_text())
        mutations = [
            lambda p: p['cases'][0]['inference'].update(failure_probability=.4),
            lambda p: p['cases'][0]['model_inputs']['time_series'][0].__setitem__(0, 50),
            lambda p: p['cases'][0]['window']['dates'].__setitem__(0, '2030-01-01'),
            lambda p: p['cases'].__setitem__(0, None),
            lambda p: p['cases'][0]['source'].update(split='train'),
            lambda p: p['cases'][2]['evaluation_reference'].update(exact_match=True),
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'case.json'
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    payload = copy.deepcopy(original)
                    mutation(payload)
                    raw = json.dumps(payload).encode()
                    path.write_bytes(raw)
                    with self.assertRaises(cases.CaseBundleError):
                        cases.load_case_bundle(path, hashlib.sha256(raw).hexdigest())

    def test_copilot_rejects_non_current_cutoffs_before_fleet_reads(self):
        for cutoff in ({'day': -7, 'projected': False}, {'day': 3, 'projected': True}, '2025-12-23', None):
            with self.subTest(cutoff=cutoff):
                result = copilot.answer(NoFleetReads(), 'What should I do?', {'cutoff': cutoff})
                self.assertFalse(result['available'])
                self.assertIn('Return to Now', result['text'])

    def test_current_copilot_labels_origin_and_date(self):
        with patch.object(copilot, '_answer_now', return_value={'text': 'Saved rule answer'}):
            result = copilot.answer(NoFleetReads(), 'Why?', {'cutoff': 'now'})
        self.assertTrue(result['available'])
        self.assertEqual(result['origin'], 'illustrative_rules')
        self.assertEqual(result['cutoff'], 'now')
        self.assertIn('+00:00', result['answered_at'])


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def test_list_and_all_details(self):
        self.assertEqual(len(json.load(urlopen(self.base + '/api/cases'))['cases']), 3)
        for case_id in cases.CASE_IDS:
            self.assertEqual(json.load(urlopen(self.base + '/api/cases/' + case_id))['case']['case_id'], case_id)

    def test_unknown_404_and_corrupted_503(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + '/api/cases/no-such-case')
        self.assertEqual(error.exception.code, 404)
        error.exception.close()
        with patch.object(cases, 'load_case_bundle', side_effect=cases.CaseBundleError('bad source')):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + '/api/cases')
            self.assertEqual(error.exception.code, 503)
            error.exception.close()

    def test_historical_http_copilot_does_not_read_fleet(self):
        with patch.object(server, 'FLEET', NoFleetReads(), create=True):
            request = Request(self.base + '/api/copilot', data=json.dumps({'question': 'Why?', 'context': {'cutoff': {'day': -1}}}).encode(), headers={'Content-Type': 'application/json'})
            self.assertFalse(json.load(urlopen(request))['available'])


if __name__ == '__main__':
    unittest.main()
