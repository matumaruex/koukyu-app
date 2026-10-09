"""一操作のおまかせ、公休の必要最小限の調整、独立検査、証明の範囲を確認する。"""
from copy import deepcopy
import unittest
from unittest.mock import patch
from solver.engine import solve
from solver.service import dispatch
from solver.auto_schedule import inspect, rank, refinement_balance_limits
from solver.holiday_policy import effective_input
from solver.capacity_bounds import shortage_bounds, overtime_bound
from solver.validator import validate, is_rule_exception
from solver.input_data import normalize
from solver.tests.test_overtime_fairness import overtime_fixture


def policy_for(raw, maximum=3):
    return {s['id']: {'min': s['monthlyDaysOff'], 'target': s['monthlyDaysOff'],
                     'max': max(maximum, s['monthlyDaysOff']), 'fixed': False} for s in raw['staff']}


def reduction_fixture(locked=False):
    raw, rows = overtime_fixture()
    raw['dailyRequiredStaff'] = {str(d): [0, 1, 0] for d in range(1, 6)}
    for st in raw['staff'][:3]:
        st['canOvertime'] = False
        rows[st['id']] = {str(d): 'off' for d in range(1, 32)}
    raw['locked'] = deepcopy(rows)
    raw['staff'].append({'id': 'p', 'type': 'part', 'monthlyDaysOff': 27,
                         'startTime': '09:00', 'endTime': '17:00', 'maxDaysPerWeek': 7, 'maxConsecutive': 5})
    raw['history']['p'] = ['off'] * 7
    raw['fairnessExcludedStaff'].append('p')
    rows['p'] = {str(d): 'part' if d <= 4 else 'off' for d in range(1, 32)}
    if locked:
        raw['locked']['p'] = {str(d): 'part' if d <= 5 else 'off' for d in range(1, 32)}
    policy = {s['id']: dict(min=0, target=0, max=0, fixed=True) for s in raw['staff'][:-1]}
    policy['p'] = dict(min=25, target=27, max=27, fixed=False)
    return raw, rows, policy


class AutoScheduleTests(unittest.TestCase):
    def adjust(self, raw, policy, rows=None, **extra):
        return dispatch(dict(mode='auto', autoPhase='adjust', input=raw, holidayPolicy=policy,
                             seconds=5, **({'referenceAssignments': rows} if rows is not None else {}), **extra))

    def test_increase_preserves_actual_holidays_and_all_quality_in_common_units(self):
        raw, before = overtime_fixture()
        baseline = solve(raw, seconds=5, initial_assignments=before, quality_first=True,
                         allow_staffing_shortfall=True, allow_rule_exceptions=True)
        original = deepcopy(raw)
        r = self.adjust(raw, policy_for(raw), baseline['assignments'])
        self.assertEqual(r['status'], 'FEASIBLE')
        self.assertEqual(set(r['selectedQuota'].values()), {3})
        self.assertTrue(r['autoDone'])
        self.assertEqual(validate(effective_input(raw, r['selectedQuota']), r['assignments']), [])
        old = inspect(raw, baseline['assignments'])
        common = inspect(raw, r['assignments'])
        self.assertTrue(all(a <= b for a, b in zip(rank(common), rank(old))))
        for sid in before:
            self.assertGreaterEqual(list(r['assignments'][sid].values()).count('off'), list(baseline['assignments'][sid].values()).count('off'))
        self.assertEqual(raw, original)

    def test_reduction_only_for_proven_shortage_and_minimum_deficit(self):
        raw, rows, policy = reduction_fixture()
        before = inspect(raw, rows)
        self.assertEqual(before['staffingShortfallTotal'], 1)
        r = self.adjust(raw, policy, rows)
        self.assertEqual(r['selectedQuota']['p'], 26)
        self.assertEqual(r['staffingShortfallTotal'], 0)
        self.assertEqual(r['autoReason'], 'necessary_reduction')
        self.assertTrue(r['autoDetails']['necessityProven'])
        self.assertEqual(validate(effective_input(raw, r['selectedQuota']), r['assignments']), [])
        self.assertEqual(r['allocation']['overtimeTotal'], 0)
        finished = dispatch(dict(mode='auto', autoPhase='finish', input=raw, holidayPolicy=policy, seconds=5,
                                 referenceAssignments=rows, initialAssignments=r['assignments'], selectedQuota=r['selectedQuota']))
        self.assertEqual(finished['selectedQuota']['p'], 26)
        self.assertEqual(finished.get('staffingShortfallTotal', 0), 0)
        self.assertEqual(validate(effective_input(raw, finished['selectedQuota']), finished['assignments']), [])

    def test_baseline_infeasibility_can_be_resolved_inside_range_without_changing_wishes(self):
        raw, _, policy = reduction_fixture(locked=True)
        r = self.adjust(raw, policy)
        self.assertEqual(r['selectedQuota']['p'], 26)
        self.assertEqual(r['assignments']['p'], raw['locked']['p'])
        self.assertTrue(r['autoDetails']['necessityProven'])
        finished = dispatch(dict(mode='auto', autoPhase='finish', input=raw, holidayPolicy=policy, seconds=5,
                                 initialAssignments=r['assignments'], selectedQuota=r['selectedQuota']))
        self.assertEqual(finished['selectedQuota']['p'], 26)
        self.assertEqual(finished['assignments']['p'], raw['locked']['p'])

    def test_lower_bound_infeasibility_is_reported_without_breaking_fixed_holidays(self):
        raw, _, policy = reduction_fixture(locked=True)
        policy['p']['min'] = 27
        r = self.adjust(raw, policy)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)

    def test_timeout_does_not_authorize_reduction(self):
        raw, rows, policy = reduction_fixture()
        r = dispatch(dict(mode='auto', autoPhase='adjust', input=raw, holidayPolicy=policy,
                          referenceAssignments=rows, seconds=.000001))
        self.assertNotIn('selectedQuota', r)
        self.assertNotIn('assignments', r)

    def test_long_leave_overtime_profile_uses_adopted_minimums(self):
        raw, rows = overtime_fixture()
        raw['requests'] = {'s0': list(range(20, 32))}
        baseline = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertIn('assignments', baseline)
        r = self.adjust(raw, policy_for(raw), baseline['assignments'])
        self.assertEqual(r['status'], 'FEASIBLE')
        chosen = effective_input(raw, r['selectedQuota'])
        self.assertEqual(validate(chosen, r['assignments']), [])
        self.assertIn('s0', r['overtimeFairness']['proportionalStaff'])
        self.assertTrue(all(r['assignments']['s0'][str(d)] == 'off' for d in raw['requests']['s0']))

    def test_reference_and_pending_candidate_are_independently_checked(self):
        raw, rows = overtime_fixture()
        policy = policy_for(raw)
        broken = deepcopy(rows)
        broken['s0']['1'] = 'night'
        self.assertEqual(self.adjust(raw, policy, broken)['status'], 'INVALID_INPUT')
        bad_candidate = dict(assignments=rows, quotas={sid: 4 for sid in rows})
        self.assertEqual(self.adjust(raw, policy, rows, autoCandidate=bad_candidate)['status'], 'INVALID_INPUT')
        bad_policy = deepcopy(policy)
        bad_policy['s0']['fixed'] = True
        self.assertEqual(self.adjust(raw, bad_policy, rows)['status'], 'INVALID_INPUT')

    def test_normal_path_still_uses_original_input_and_policy(self):
        raw, before = overtime_fixture()
        r = dispatch(dict(input=raw, initialAssignments=before, seconds=5, qualityFirst=True,
                          allowStaffingShortfall=True, allowRuleExceptions=True))
        self.assertEqual(r['optimizationPolicy'], 'quality-first-7')
        self.assertEqual(validate(raw, r['assignments']), [])

    def test_additional_overtime_search_does_not_reduce_target_or_increase_spread(self):
        raw, before = overtime_fixture()
        r = dispatch(dict(mode='auto', autoPhase='polish', input=raw, holidayPolicy=policy_for(raw),
                          seconds=5, referenceAssignments=before))
        self.assertEqual(r['allocation']['overtimeTotal'], 13)
        self.assertLessEqual(r['overtimeFairness']['spread'], 3)
        self.assertEqual(set(r['selectedQuota'].values()), {0})
        self.assertEqual(validate(raw, r['assignments']), [])

    def test_equal_overtime_can_decrease_total_to_indivisible_but_balanced_distribution(self):
        raw, rows = overtime_fixture()
        raw['dailyRequiredStaff']['25'] = [1, 0, 1]
        baseline = solve(raw, seconds=5, quality_first=True, initial_assignments=rows,
                         allow_staffing_shortfall=True, allow_rule_exceptions=True)
        self.assertEqual(baseline['allocation']['overtimeTotal'], 12)
        self.assertEqual(baseline['overtimeFairness']['spread'], 0)
        raw['dailyRequiredStaff']['23'] = [1, 0, 1]
        r = dispatch(dict(mode='auto', autoPhase='polish', input=raw, holidayPolicy=policy_for(raw),
                          seconds=5, referenceAssignments=baseline['assignments']))
        self.assertEqual(r['allocation']['overtimeTotal'], 11)
        self.assertEqual(sorted(r['overtimeFairness']['byStaff'].values()), [3, 4, 4])
        self.assertTrue(r['overtimeFairness']['minimumSpreadProven'])
        self.assertEqual(validate(raw, r['assignments']), [])

    def test_proportional_refinement_limits_match_exhaustive_distribution_optima(self):
        from itertools import product
        from solver.input_data import overtime_profile
        raw, _ = overtime_fixture()
        raw['requests'] = {'s0': list(range(1, 19))}
        p = normalize(raw)
        profiles = [overtime_profile(p, st) for st in p['staff'] if st['canOvertime']]
        scales = [min(600, (200 * v['normal'] + v['available']) // (2 * v['available']))
                  if v['proportional'] and v['available'] else 100 for v in profiles]
        brute = {}
        for counts in product(*(range(v['cap'] + 1) for v in profiles)):
            values = [a * b for a, b in zip(counts, scales)]
            total, balance = sum(counts), max(values) - min(values)
            brute[total] = min(brute.get(total, balance), balance)
        self.assertEqual(dict(refinement_balance_limits(p, max(brute), 0)), brute)

    def test_one_communication_includes_preparation_and_diagnosis_in_budget(self):
        raw, _, policy = reduction_fixture(locked=True)
        r = dispatch(dict(mode='auto', autoPhase='base', input=raw, holidayPolicy=policy, seconds=1))
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertLess(r['seconds'], 1.15)

    def test_client_resume_cannot_supply_a_false_minimum_proof(self):
        raw, before = overtime_fixture()
        raw['dailyRequiredStaff']['25'] = [1, 0, 1]
        r = dispatch(dict(mode='auto', autoPhase='base', input=raw, holidayPolicy=policy_for(raw), seconds=5,
                          initialAssignments=before, resume={'stage': 'placement', 'idle': 0,
                          'proven': dict(conditions=True, overtime=True, overtime_fairness=True, placement=True)}))
        self.assertFalse(r['allocation']['minimumOvertimeProven'])

    def test_finish_preserves_reference_and_uses_effective_minimums(self):
        raw, before = overtime_fixture()
        baseline = solve(raw, seconds=5, initial_assignments=before, quality_first=True,
                         allow_staffing_shortfall=True, allow_rule_exceptions=True)
        policy = policy_for(raw)
        selected = self.adjust(raw, policy, baseline['assignments'])
        r = dispatch(dict(mode='auto', autoPhase='finish', input=raw, holidayPolicy=policy, seconds=5,
                          referenceAssignments=baseline['assignments'], initialAssignments=selected['assignments'],
                          selectedQuota=selected['selectedQuota']))
        self.assertEqual(validate(effective_input(raw, r['selectedQuota']), r['assignments']), [])
        self.assertLessEqual(r['allocation']['overtimeTotal'], baseline['allocation']['overtimeTotal'])


class CapacityBoundsTests(unittest.TestCase):
    def test_bounds_do_not_exceed_valid_fixture_counts_across_month_lengths(self):
        raw, _ = overtime_fixture()
        for year, month, days in ((2027, 2, 28), (2028, 2, 29), (2026, 9, 30), (2026, 10, 31)):
            q = deepcopy(raw)
            q.update(year=year, month=month)
            for row in q['locked'].values():
                for key in list(row):
                    if int(key) > days:
                        del row[key]
            r = solve(q, seconds=5, quality_first=True, allow_staffing_shortfall=True, allow_rule_exceptions=True)
            self.assertIn('assignments', r)
            b = shortage_bounds(q)
            self.assertLessEqual(b['total'], r.get('staffingShortfallTotal', 0))
            self.assertLessEqual(overtime_bound(q, r.get('staffingShortfallTotal', 0), bounds=b), r['allocation']['overtimeTotal'])

    def test_part_time_covering_both_times_is_not_counted_as_one(self):
        raw, rows = overtime_fixture()
        raw['staff'].append(dict(id='p', type='part', monthlyDaysOff=0, startTime='06:00', endTime='19:00', maxDaysPerWeek=7))
        raw['history']['p'] = ['off'] * 7
        # 朝夕を両方覆うパートの供給上限を、残業必要回数と誤認しない。
        self.assertEqual(overtime_bound(raw, 0), 0)


if __name__ == '__main__':
    unittest.main()
