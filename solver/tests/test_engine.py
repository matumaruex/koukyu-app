"""成立例、不成立例、故意の破壊、境界条件で独立検査の有効性を確認する。"""
import json
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate

ROOT = Path(__file__).resolve().parents[2]


def fixture(month=2):
    p = json.loads((ROOT / 'user_data.json').read_text(encoding='utf-8-sig'))
    p.update(year=2026, month=month)
    return p


class SolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = fixture()
        cls.result = solve(cls.raw, seconds=15)
        assert cls.result['status'] in ('OPTIMAL', 'FEASIBLE'), cls.result
        cls.table = cls.result['assignments']

    def test_real_roster_february_and_fairness(self):
        self.assertEqual(validate(self.raw, self.table), [])
        self.assertEqual(self.result['fairness']['spread'], 0)
        self.assertTrue(all(n == 0 for n in self.result['fairness']['extraDaysOff'].values()))
        self.assertEqual(self.result['verificationScope'], 'PERIOD_ONLY')

    def test_requested_holidays_including_night_eve(self):
        p = fixture()
        sid = p['staff'][0]['id']
        p['requests'] = {sid: [1, 2, 3]}
        r = solve(p, seconds=15)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual([r['assignments'][sid][str(d)] for d in (1, 2, 3)], ['off'] * 3)
        self.assertEqual(validate(p, r['assignments']), [])

    def test_no_night_workers_is_proven_impossible(self):
        p = fixture()
        for st in p['staff']:
            st['nightShiftType'] = 'none'
        r = solve(p, seconds=5)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)
        self.assertTrue(r['conflictGroups'])

    def test_everyone_requests_same_day_is_impossible(self):
        p = fixture()
        p['requests'] = {s['id']: [5] for s in p['staff']}
        r = solve(p, seconds=5)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)

    def test_timeout_is_not_impossible(self):
        r = solve(fixture(3), seconds=0.000001)
        self.assertEqual(r['status'], 'UNKNOWN')
        self.assertNotIn('assignments', r)

    def test_conflicting_locked_shift_and_request(self):
        p = fixture()
        sid = p['staff'][0]['id']
        p['requests'] = {sid: [1]}
        p['locked'] = {sid: {'1': 'early'}}
        self.assertEqual(solve(p, seconds=5)['status'], 'INFEASIBLE')

    def test_previous_night_propagates(self):
        p = fixture()
        p['history'] = {s['id']: ['off'] * 7 for s in p['staff']}
        sid = p['staff'][0]['id']
        p['history'][sid][-1] = 'night'
        r = solve(p, seconds=15, optimize=False)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['assignments'][sid]['1'], 'nightOff')
        self.assertEqual(r['verificationScope'], 'WITH_HISTORY')
        self.assertEqual(validate(p, r['assignments']), [])

    def test_history_consecutive_cannot_be_reset(self):
        p = fixture()
        sid = p['staff'][0]['id']
        p['history'] = {sid: ['off'] * 5 + ['early', 'early']}
        p['locked'] = {sid: {'1': 'early'}}
        self.assertEqual(solve(p, seconds=5)['status'], 'INFEASIBLE')

    def test_history_weekly_limit_cannot_be_reset(self):
        p = fixture(4)  # 4/16（木）開始、月〜水の3勤務を持ち越す。
        st = p['staff'][7]
        st['maxDaysPerWeek'] = 3
        st['maxConsecutive'] = 6
        sid = st['id']
        p['history'] = {sid: ['off'] * 4 + ['part'] * 3}
        p['locked'] = {sid: {'1': 'part'}}
        self.assertEqual(solve(p, seconds=5)['status'], 'INFEASIBLE')

    def test_leap_year_and_year_rollover(self):
        for year, month, n, end in [(2028, 2, 29, '2028-03-15'), (2026, 12, 31, '2027-01-15')]:
            p = fixture(month)
            p['year'] = year
            normalized = normalize(p)
            self.assertEqual(normalized['days'], n)
            self.assertEqual(str(normalized['start'] + timedelta(days=n - 1)), end)

    def test_bad_inputs_rejected(self):
        variants = [None, {}, {'year': 2026, 'month': 13, 'staff': []}]
        p = fixture(); p['staff'][0]['monthlyDaysOff'] = -1; variants.append(p)
        p = fixture(); p['staff'][1]['id'] = p['staff'][0]['id']; variants.append(p)
        p = fixture(); p['staff'][7]['startTime'] = '25:00'; variants.append(p)
        p = fixture(); p['requests'] = {'unknown': [1]}; variants.append(p)
        p = fixture(); p['history'] = {p['staff'][0]['id']: ['off']}; variants.append(p)
        p = fixture(); p['staff'][0] = None; variants.append(p)
        for p in variants:
            with self.subTest(p=p):
                self.assertEqual(solve(p)['status'], 'INVALID_INPUT')

    def codes(self, p, table):
        return {e['code'] for e in validate(p, table)}

    def test_validator_detects_holiday_violation(self):
        p = fixture(); a = deepcopy(self.table); sid = p['staff'][0]['id']
        p['requests'] = {sid: [1]}; a[sid]['1'] = 'night'
        self.assertIn('request', self.codes(p, a))

    def test_validator_detects_missing_and_unknown_cells(self):
        a = deepcopy(self.table); del a[next(iter(a))]['1']
        self.assertIn('structure', self.codes(self.raw, a))
        a = deepcopy(self.table); a[next(iter(a))]['1'] = 'fake'
        self.assertIn('structure', self.codes(self.raw, a))

    def test_validator_detects_missing_night_and_coverage(self):
        a = deepcopy(self.table)
        for row in a.values():
            row['4'] = 'off'
        self.assertTrue({'coverage', 'night_coverage'}.issubset(self.codes(self.raw, a)))

    def test_validator_detects_overtime_count_and_adjacency(self):
        a = deepcopy(self.table); sid = self.raw['staff'][0]['id']
        for d in range(1, 8):
            a[sid][str(d)] = 'overtime'
        self.assertTrue({'overtime_limit', 'adjacent_overtime', 'consecutive'}.issubset(self.codes(self.raw, a)))

    def test_validator_detects_weekly_and_eligibility(self):
        a = deepcopy(self.table); sid = self.raw['staff'][7]['id']
        for d in range(1, 8):
            a[sid][str(d)] = 'part'
        self.assertIn('weekly', self.codes(self.raw, a))
        a[sid]['1'] = 'night'
        self.assertIn('eligibility', self.codes(self.raw, a))

    def test_validator_detects_off_and_night_links(self):
        a = deepcopy(self.table); sid = self.raw['staff'][0]['id']
        for d in a[sid]:
            a[sid][d] = 'early'
        a[sid]['1'] = 'nightOff'
        self.assertTrue({'days_off', 'night_link'}.issubset(self.codes(self.raw, a)))

    def test_validator_counts_plus_one_once(self):
        p = fixture(); st = p['staff'][0]; st['allowConsecutivePlus1'] = True
        a = deepcopy(self.table); sid = st['id']
        for d in a[sid]:
            a[sid][d] = 'off'
        for d in (1, 2, 3):
            a[sid][str(d)] = 'early'
        self.assertNotIn('consecutive_plus_one', self.codes(p, a))
        self.assertNotIn('consecutive', self.codes(p, a))
        for d in (5, 6, 7):
            a[sid][str(d)] = 'early'
        self.assertIn('consecutive_plus_one', self.codes(p, a))

    def test_extra_holidays_are_distributed_equally(self):
        from solver.benchmark import cases
        p = list(cases())[-1][1]
        r = solve(p, seconds=20)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(set(r['fairness']['extraDaysOff'].values()), {2})
        self.assertEqual(validate(p, r['assignments']), [])

    def test_fairness_is_never_silently_relaxed(self):
        p = fixture(); p['staff'][7]['maxDaysPerWeek'] = 3
        r = solve(p, seconds=10)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)

    def test_validator_detects_unfair_extra_holidays(self):
        a = deepcopy(self.table); sid = self.raw['staff'][0]['id']
        for day in a[sid]:
            a[sid][day] = 'off'
        self.assertIn('fairness', self.codes(self.raw, a))

    def test_solver_plus_one_respects_one_time_limit(self):
        p = fixture(); st = p['staff'][0]; st['allowConsecutivePlus1'] = True
        sid = st['id']
        p['locked'] = {sid: {str(d): 'early' for d in (1, 2, 3)}}
        r = solve(p, seconds=15, optimize=False)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(validate(p, r['assignments']), [])
        p['locked'][sid].update({str(d): 'early' for d in (5, 6, 7)})
        self.assertEqual(solve(p, seconds=5)['status'], 'INFEASIBLE')

    def test_validator_limits_reduced_sundays(self):
        p = fixture(); a = deepcopy(self.table)
        for d in (7, 14, 21, 28):
            for row in a.values():
                row[str(d)] = 'off'
        self.assertIn('sunday_limit', self.codes(p, a))

    def test_last_night_is_carried_to_next_period(self):
        p = fixture(); sid = p['staff'][0]['id']
        p['locked'] = {sid: {'28': 'night'}}
        r = solve(p, seconds=15, optimize=False)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertEqual(r['carryForward'][sid]['nextDay'], 'nightOff')
        self.assertEqual(r['carryForward'][sid]['history'][-1], 'night')

    def test_timeout_keeps_verified_previous_result(self):
        r = solve(self.raw, seconds=0.000001, initial_assignments=self.table)
        self.assertEqual(r['status'], 'FEASIBLE')
        self.assertTrue(r['previousKept'])
        self.assertEqual(r['assignments'], self.table)
        self.assertFalse(r['fairness']['provenOptimal'])

    def test_longer_run_never_worsens_quality(self):
        r = solve(self.raw, seconds=3, initial_assignments=self.table)
        self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'))
        self.assertLessEqual(r['objective'], self.result['objective'])
        self.assertEqual(validate(self.raw, r['assignments']), [])

    def test_invalid_previous_result_is_rejected(self):
        a = deepcopy(self.table)
        a[self.raw['staff'][0]['id']]['1'] = 'nonsense'
        self.assertEqual(solve(self.raw, initial_assignments=a)['status'], 'INVALID_INPUT')


if __name__ == '__main__':
    unittest.main()
