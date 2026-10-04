"""Explicit per-period exceptions change only the comparison of extra holidays."""
import unittest
from copy import deepcopy
from solver.engine import solve, quality_value
from solver.input_data import normalize
from solver.validator import validate
from solver.tests.test_night_rest import roomy_fixture


class FairnessExceptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = roomy_fixture()
        cls.raw['fairnessExcludedStaff'] = ['s0']
        cls.raw['locked'] = {'s0': {str(d): 'off' for d in range(1, 29)}}
        cls.result = solve(cls.raw, seconds=10, optimize=False)
        assert cls.result['status'] in ('FEASIBLE', 'OPTIMAL'), cls.result
        cls.table = cls.result['assignments']

    def test_exception_does_not_force_peers_to_match_long_leave(self):
        self.assertEqual(validate(self.raw, self.table), [])
        metric = self.result['fairness']
        self.assertEqual(metric['excludedStaff'], ['s0'])
        self.assertNotIn('s0', metric['comparedStaff'])
        self.assertEqual(metric['extraDaysOff']['s0'], 19)
        self.assertLessEqual(metric['spread'], 1)
        self.assertGreater(max(metric['extraDaysOff'].values()) - min(metric['extraDaysOff'].values()), 1)
        restored = deepcopy(self.raw)
        restored.pop('fairnessExcludedStaff')
        self.assertIn('fairness', {e['code'] for e in validate(restored, self.table)})

    def test_peers_are_still_compared(self):
        bad = deepcopy(self.table)
        bad['s1'] = {str(d): 'off' for d in range(1, 29)}
        self.assertIn('fairness', {e['code'] for e in validate(self.raw, bad)})

    def test_exception_does_not_remove_minimum_or_wishes(self):
        p = deepcopy(self.raw)
        p['staff'][0]['monthlyDaysOff'] = 28
        bad = deepcopy(self.table)
        bad['s0']['1'] = 'early'
        p['requests'] = {'s0': [1]}
        self.assertTrue({'days_off', 'request', 'locked'}.issubset({e['code'] for e in validate(p, bad)}))

    def test_exception_does_not_remove_recovery_rest(self):
        bad = deepcopy(self.table)
        bad['s0']['2'] = 'night'
        bad['s0']['3'] = 'nightOff'
        bad['s0']['4'] = 'early'
        self.assertIn('night_rest', {e['code'] for e in validate(self.raw, bad)})

    def test_zero_or_one_member_has_no_comparison_and_no_crash(self):
        for members in ([], ['s1']):
            p = deepcopy(self.raw)
            p['fairnessExcludedStaff'] = [s['id'] for s in p['staff'] if s['id'] not in members]
            r = solve(p, seconds=10, optimize=False)
            self.assertIn(r['status'], ('FEASIBLE', 'OPTIMAL'))
            self.assertEqual(r['fairness']['spread'], 0)
            self.assertEqual(r['fairness']['comparedStaff'], members)
            self.assertEqual(validate(p, r['assignments']), [])
            self.assertIsInstance(quality_value(normalize(p), r['assignments']), int)

    def test_bad_exceptions_are_rejected(self):
        for invalid in (None, True, 's0', ['unknown'], ['s0', 's0'], [0], [[]]):
            p = deepcopy(self.raw)
            p['fairnessExcludedStaff'] = invalid
            self.assertEqual(solve(p)['status'], 'INVALID_INPUT')


if __name__ == '__main__':
    unittest.main()
