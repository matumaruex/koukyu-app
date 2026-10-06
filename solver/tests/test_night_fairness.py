"""夜勤の公平さを日勤改善より先に確定し、不可能と時間切れを区別する。"""
import unittest
from copy import deepcopy
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.validator import validate


def six_staff(month=9):
    return {'year': 2026, 'month': month, 'requiredStaff': [0, 0, 0],
            'maxReducedSundays': 0, 'maxExtraOffSpread': 1,
            'staff': [{'id': f's{i}', 'type': 'full', 'nightShiftType': 'all',
                       'monthlyDaysOff': 9, 'maxConsecutive': 3,
                       'canOvertime': True} for i in range(6)],
            'history': {f's{i}': ['off'] * 7 for i in range(6)}}


def equal_shortfall_fixture():
    n = 30
    a = {f's{i}': {str(d): 'off' for d in range(1, n + 1)} for i in range(5)}
    for d in range(1, n + 1):
        a[f's{(d-1)%3}'][str(d)] = 'night'
        a[f's{(d-2)%3}'][str(d)] = 'nightOff'
    a['s3']['11'] = 'early'
    a['s4']['11'] = 'part'
    raw = six_staff()
    raw['staff'] = raw['staff'][:3] + [dict(raw['staff'][0], id='s3', nightShiftType='none'),
                      {'id': 's4', 'type': 'part', 'startTime': '07:00', 'endTime': '16:00',
                       'monthlyDaysOff': 0, 'maxDaysPerWeek': 5, 'maxConsecutive': 3}]
    for st in raw['staff']: st['monthlyDaysOff'] = 0
    raw['history'] = {sid: ['off']*7 for sid in a}
    raw['history']['s2'][-1] = 'night'
    raw['fairnessExcludedStaff'] = list(a)
    raw['dailyRequiredStaff'] = {'11': [0, 3, 0]}
    raw['locked'] = deepcopy(a)
    for d in ('10', '11', '12'): raw['locked']['s0'].pop(d)
    return raw, a


class NightFairnessTests(unittest.TestCase):
    def test_thirty_and_thirty_one_nights_are_split_as_evenly_as_possible(self):
        for month, expected in [(9, [5]*6), (10, [5]*5+[6])]:
            raw = six_staff(month)
            r = solve(raw, seconds=5)
            self.assertIn(r['status'], ('OPTIMAL', 'FEASIBLE'), r)
            self.assertEqual(validate(raw, r['assignments']), [])
            f = r['nightFairness']
            self.assertEqual(sorted(f['byStaff'].values()), expected)
            self.assertTrue(f['minimumSpreadProven'])
            self.assertEqual(f['reason'], 'balanced')

    def test_requested_seven_nights_are_kept_and_imbalance_is_proven(self):
        raw = six_staff()
        days = [1, 5, 9, 13, 17, 21, 25]
        raw['shiftRequests'] = {'s0': {str(d): 'night' for d in days}}
        r = solve(raw, seconds=5)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertTrue(all(r['assignments']['s0'][str(d)] == 'night' for d in days))
        self.assertEqual(r['nightFairness']['byStaff']['s0'], 7)
        self.assertEqual(r['nightFairness']['spread'], 3)
        self.assertTrue(r['nightFairness']['minimumSpreadProven'])
        self.assertEqual(r['nightFairness']['reason'], 'constraints')

    def test_partial_search_does_not_call_imbalance_impossible(self):
        raw = six_staff()
        raw['shiftRequests'] = {'s0': {str(d): 'night' for d in [1, 5, 9, 13, 17, 21, 25]}}
        real = cp_model.CpSolver.solve
        calls = []
        def incomplete(solver, model, *args, **kwargs):
            status = real(solver, model, *args, **kwargs)
            calls.append(status)
            return cp_model.FEASIBLE if len(calls) == 1 and status == cp_model.OPTIMAL else status
        with patch.object(cp_model.CpSolver, 'solve', incomplete):
            r = solve(raw, seconds=5)
        self.assertEqual(r['status'], 'FEASIBLE')
        self.assertFalse(r['nightFairness']['minimumSpreadProven'])
        self.assertEqual(r['nightFairness']['reason'], 'not_proven')
        self.assertFalse(r['allocation']['minimumOvertimeProven'])

    def test_same_total_shortfall_prefers_a_filled_night(self):
        raw, before = equal_shortfall_fixture()
        self.assertEqual([e['code'] for e in validate(raw, before)], ['coverage'])
        r = solve(raw, seconds=5, allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['status'], 'DRAFT', r)
        self.assertEqual(r['staffingShortfallTotal'], 1)
        self.assertEqual(r['nightShortfallTotal'], 0)
        self.assertEqual(r['daytimeShortfallTotal'], 1)
        self.assertEqual(r['assignments']['s0']['10'], 'night')
        self.assertTrue(r['shortfallProvenMinimum'])
        # 同数の不足がある旧表からの追加計算でも、夜勤の穴を埋める。
        gap = deepcopy(before)
        gap['s0'].update({'10': 'off', '11': 'early', '12': 'off'})
        self.assertEqual([e['code'] for e in validate(raw, gap)], ['night_coverage'])
        improved = solve(raw, seconds=5, initial_assignments=gap,
                         allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(improved['nightShortfallTotal'], 0)
        self.assertTrue(improved['improved'])

    def test_timeout_keeps_baseline_without_claiming_constraint_proof(self):
        raw, baseline = equal_shortfall_fixture()
        r = solve(raw, seconds=0.000001, initial_assignments=baseline,
                  allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['assignments'], baseline)
        self.assertFalse(r['nightFairness']['priorityProven'])

    def test_additional_calculation_improves_unequal_baseline(self):
        raw = six_staff()
        raw['shiftRequests'] = {'s0': {str(d): 'night' for d in [1, 5, 9, 13, 17, 21, 25]}}
        before = solve(raw, seconds=5)['assignments']
        raw.pop('shiftRequests')
        self.assertEqual(validate(raw, before), [])
        r = solve(raw, seconds=5, initial_assignments=before)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(sorted(r['nightFairness']['byStaff'].values()), [5]*6)
        self.assertEqual(r['allocation']['nightSpread'], 0)
        self.assertTrue(r['improved'])


if __name__ == '__main__': unittest.main()
