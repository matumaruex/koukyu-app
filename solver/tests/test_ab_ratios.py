"""人数・夜勤・公休を変えず、異なる日勤数に対するA/B比率を比較する。"""
import unittest
from copy import deepcopy
from solver.allocation import ab_ratio_report, covers, metrics, quality_value
from solver.engine import solve
from solver.input_data import normalize
from solver.validator import validate
from solver.tests.test_monthly_allocation import exchange_fixture
from solver.tests.test_night_rest import roomy_fixture


def ratio_fixture():
    p, a = exchange_fixture()
    workdays = [2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14]
    for sid in ('s0', 's1', 's2', 's3'):
        a[sid] = {str(d): 'off' for d in range(1, 29)}
    for i, d in enumerate(workdays):
        a['s0'][str(d)] = 'early' if i < 10 else 'late'
        if i < 10:
            a['s1'][str(d)] = 'early' if i < 5 else 'late'
    for st in p['staff']:
        st['monthlyDaysOff'] = list(a[st['id']].values()).count('off')
        st['canOvertime'] = False
        st['maxConsecutive'] = 6
        if st['id'] in ('s0', 's1'):
            st['dayShiftType'] = 'both'
    p['locked'] = {sid: {d: shift for d, shift in row.items()
                         if sid not in ('s0', 's1') or shift == 'off'} for sid, row in a.items()}
    np = normalize(p)
    p['dailyRequiredStaff'] = {str(d): [sum(covers(st, a[st['id']][str(d)], t) for st in np['staff'])
                                      for t in (420, 600, 1065)] for d in range(1, 29)}
    assert validate(p, a) == []
    return p, a


class AbRatioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.before = ratio_fixture()
        cls.result = solve(cls.raw, seconds=5, initial_assignments=cls.before)

    def test_different_day_totals_get_same_proportion_instead_of_same_counts(self):
        r = self.result
        self.assertEqual(r['status'], 'OPTIMAL', r)
        self.assertEqual(validate(self.raw, r['assignments']), [])
        report = r['allocation']['abRatioBalance']
        self.assertEqual(report['targetAPercent'], 71)
        self.assertEqual(report['deviationTotal'], 3)
        self.assertEqual((report['byStaff']['s0']['early'], report['byStaff']['s0']['late']), (8, 3))
        self.assertEqual((report['byStaff']['s1']['early'], report['byStaff']['s1']['late']), (7, 3))

    def test_coverage_off_counts_overtime_and_nights_are_preserved(self):
        before = metrics(normalize(self.raw), self.before)
        after = self.result['allocation']
        self.assertEqual(after['preservedNightSpread'], before['nightSpread'])
        for key in ('overtimeTotal', 'surplusTotal', 'nightSpread', 'commonExtraDaysOff', 'extraOffSpread'):
            self.assertEqual(before[key], after[key], key)
        for sid in self.before:
            for shift in ('off', 'night', 'nightOff'):
                self.assertEqual(list(self.before[sid].values()).count(shift),
                                 list(self.result['assignments'][sid].values()).count(shift))

    def test_model_score_matches_independent_completed_table_score(self):
        self.assertEqual(self.result['objective'], quality_value(normalize(self.raw), self.result['assignments']))

    def test_single_type_and_no_day_work_do_not_distort_target(self):
        p, a = deepcopy(self.raw), deepcopy(self.before)
        p['staff'][2]['dayShiftType'] = 'early'
        p['staff'][3]['dayShiftType'] = 'late'
        a['s2']['1'] = 'early'
        a['s3'].update({str(d): 'late' for d in range(1, 29)})
        np = normalize(p)
        r = ab_ratio_report(np, a)
        self.assertNotIn('s2', r['byStaff'])
        self.assertNotIn('s3', r['byStaff'])
        self.assertEqual(r['targetAPercent'], 71)
        self.assertNotIn('s4', r['comparedStaff'])
        self.assertIsNone(r['byStaff']['s4']['earlyPercent'])

    def test_all_zero_days_and_rounding_are_defined(self):
        p, a = deepcopy(self.raw), deepcopy(self.before)
        for row in a.values():
            row.update({str(d): 'off' for d in range(1, 29)})
        r = ab_ratio_report(normalize(p), a)
        self.assertIsNone(r['targetAPercent'])
        self.assertEqual(r['deviationTotal'], 0)
        self.assertEqual(r['comparedStaff'], [])
        a['s0'].update({'1': 'early', '2': 'late', '3': 'late'})
        self.assertEqual(ab_ratio_report(normalize(p), a)['targetAPercent'], 33)

    def test_ratio_balance_does_not_override_requested_work(self):
        p = deepcopy(self.raw)
        p['shiftRequests'] = {'s0': {'9': 'early', '10': 'early', '11': 'early', '12': 'early', '13': 'early'}}
        r = solve(p, seconds=5, initial_assignments=self.before)
        self.assertEqual(r['status'], 'OPTIMAL', r)
        self.assertEqual(validate(p, r['assignments']), [])
        self.assertGreater(r['allocation']['abRatioBalance']['deviationTotal'], 3)
        self.assertTrue(all(r['assignments']['s0'][str(d)] == 'early' for d in (9, 10, 11, 12, 13)))

    def test_timeout_preserves_incumbent_and_computes_current_policy_metrics(self):
        r = solve(self.raw, seconds=0.000001, initial_assignments=self.before)
        self.assertEqual(r['assignments'], self.before)
        self.assertTrue(r['previousKept'])
        self.assertEqual(r['allocation']['abRatioBalance']['deviationTotal'], 41)

    def test_reducing_shortage_takes_priority_over_saved_night_spread(self):
        p = roomy_fixture()
        p['requiredStaff'] = [0, 0, 0]
        p['fairnessExcludedStaff'] = [st['id'] for st in p['staff']]
        p['requests'] = {st['id']: list(range(1, 29)) for st in p['staff'][1:]}
        before = {st['id']: {str(d): 'off' for d in range(1, 29)} for st in p['staff']}
        r = solve(p, seconds=5, initial_assignments=before,
                  allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['status'], 'DRAFT', r)
        self.assertLess(r['nightShortfallTotal'], 28)
        self.assertGreater(r['allocation']['nightSpread'], 0)
        self.assertIsNone(r['allocation']['preservedNightSpread'])
        self.assertTrue(all(e['code'] == 'night_coverage' for e in validate(p, r['assignments'])))
