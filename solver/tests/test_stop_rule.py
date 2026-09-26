"""「最低時間を過ぎ、最初の表から一定時間たったら止める」計算の止め方を確認する。"""
import unittest
from solver.benchmark import cases
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_engine import fixture

OK = ('OPTIMAL', 'FEASIBLE')


class StopRuleTests(unittest.TestCase):
    def test_stops_after_minimum_instead_of_running_to_cap(self):
        # 3月の設定は時間内に最適と確認できない例。上限60秒でも、表が見つかれば早く返る。
        p = fixture(3)
        r = solve(p, seconds=60, min_seconds=3, after_first=1)
        self.assertIn(r['status'], OK)
        self.assertEqual(validate(p, r['assignments']), [])
        self.assertLess(r['seconds'], 30)
        rule = r['stopRule']
        self.assertIsNotNone(rule['firstSolutionSeconds'])
        if r['status'] == 'FEASIBLE':
            self.assertTrue(rule['stoppedEarly'])
            self.assertGreaterEqual(r['seconds'], 3 - 0.3)
            self.assertGreaterEqual(r['seconds'], rule['firstSolutionSeconds'] + 1 - 0.3)

    def test_impossible_conditions_are_still_proven(self):
        p = fixture()
        p['requests'] = {s['id']: [5] for s in p['staff']}
        r = solve(p, seconds=60, min_seconds=15, after_first=10)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)
        self.assertFalse(r['stopRule']['stoppedEarly'])

    def test_no_table_until_cap_is_unknown_not_impossible(self):
        r = solve(fixture(3), seconds=0.000001, min_seconds=0, after_first=0)
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)

    def test_invalid_stop_rule_is_rejected(self):
        p = fixture()
        for kwargs in ({'min_seconds': 5}, {'after_first': 5}, {'min_seconds': -1, 'after_first': 1},
                       {'min_seconds': 5, 'after_first': float('nan')}, {'min_seconds': 70, 'after_first': 1}):
            self.assertEqual(solve(p, seconds=60, **kwargs)['status'], 'INVALID_INPUT', kwargs)

    def test_without_rule_result_is_unchanged(self):
        r = solve(fixture(3), seconds=0.000001)
        self.assertNotIn('stopRule', r)

    def test_api_options_are_type_checked(self):
        raw = next(cases())[1]
        for bad in ({'adaptive': 'yes'}, {'adaptive': 1}, {'seed': 0}, {'seed': 1001}, {'seed': True}, {'seed': '2'}, {'seed': 1.5}):
            self.assertEqual(dispatch({'input': raw, 'seconds': 60, **bad})['status'], 'INVALID_INPUT', bad)

    def test_api_adaptive_uses_the_stop_rule(self):
        raw = next(cases())[1]
        r = dispatch({'input': raw, 'seconds': 60, 'adaptive': True, 'seed': 2})
        self.assertIn(r['status'], OK)
        self.assertEqual(r['stopRule']['minSeconds'], 15)
        self.assertEqual(r['stopRule']['afterFirst'], 10)
        self.assertLess(r['seconds'], 59)
        self.assertEqual(validate(raw, r['assignments']), [])


if __name__ == '__main__':
    unittest.main()
