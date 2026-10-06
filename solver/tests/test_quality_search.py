"""条件確認と残業最少を確定してから、残り時間で配置を改善する。"""
import unittest
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.tests.test_night_fairness import six_staff, equal_shortfall_fixture


class QualitySearchTests(unittest.TestCase):
    def test_three_stages_validate_complete_table_and_can_finish_early(self):
        raw = six_staff()
        r = solve(raw, seconds=5, quality_first=True)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(sorted(r['nightFairness']['byStaff'].values()), [5]*6)
        self.assertTrue(r['allocation']['minimumOvertimeProven'])
        self.assertEqual(r['allocation']['overtimeTotal'], 0)
        self.assertEqual(r['timing']['mode'], 'quality')
        self.assertEqual([s['stage'] for s in r['search']['stages']], ['conditions','overtime','placement'])
        if r['status'] == 'OPTIMAL': self.assertFalse(r['search']['continueRecommended'])

    def test_hard_impossibility_returns_without_spending_whole_budget(self):
        raw = six_staff()
        raw['shiftRequests'] = {'s0': {'5':'night'},'s1': {'5':'night'}}
        r = solve(raw, seconds=60, quality_first=True, allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['status'], 'INFEASIBLE')
        self.assertNotIn('assignments', r)
        self.assertLess(r['seconds'], 5)
        self.assertFalse(r['search']['continueRecommended'])

    def test_unavoidable_shortfall_is_proven_with_every_night_filled(self):
        raw, a = equal_shortfall_fixture()
        r = solve(raw, seconds=5, quality_first=True, allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['staffingShortfallTotal'], 1)
        self.assertEqual(r['nightShortfallTotal'], 0)
        self.assertTrue(r['shortfallProvenMinimum'])
        self.assertTrue(r['allocation']['minimumOvertimeProven'])
        self.assertEqual([e['code'] for e in validate(raw, r['assignments'])], ['coverage'])

    def test_priority_timeout_does_not_enter_quality_or_claim_impossibility(self):
        raw = six_staff()
        real = cp_model.CpSolver.solve
        def incomplete(solver, model, *args, **kwargs):
            st = real(solver, model, *args, **kwargs)
            return cp_model.FEASIBLE if st == cp_model.OPTIMAL else st
        with patch.object(cp_model.CpSolver, 'solve', incomplete):
            r = solve(raw, seconds=2, quality_first=True)
        self.assertEqual(r['status'], 'FEASIBLE')
        self.assertTrue(all(s['stage']=='conditions' for s in r['search']['stages']))
        self.assertFalse(r['allocation']['minimumOvertimeProven'])
        self.assertTrue(r['search']['continueRecommended'])
        self.assertEqual(r['search']['reason'], 'conditions_unconfirmed')

    def test_tiny_budget_keeps_checked_baseline_and_requests_continuation(self):
        raw, a = equal_shortfall_fixture()
        r = solve(raw, seconds=0.000001, quality_first=True, initial_assignments=a,
                  allow_staffing_shortfall=True, allow_night_shortfall=True)
        self.assertEqual(r['assignments'], a)
        self.assertTrue(r['previousKept'])
        self.assertFalse(r['shortfallProvenMinimum'])
        self.assertTrue(r['search']['continueRecommended'])

    def test_new_api_mode_overrides_legacy_candidate_timer(self):
        with patch('solver.service.solve', return_value={'status':'UNKNOWN'}) as calculation:
            dispatch({'input':six_staff(),'seconds':60,'qualityFirst':True,'adaptive':True})
        self.assertTrue(calculation.call_args.kwargs['quality_first'])
        self.assertNotIn('min_seconds', calculation.call_args.kwargs)
        for bad in (1, 'true', None):
            self.assertEqual(dispatch({'input':six_staff(),'qualityFirst':bad})['status'], 'INVALID_INPUT')
        self.assertEqual(dispatch({'input':six_staff(),'qualityFirst':True,'seconds':121})['status'], 'INVALID_INPUT')


if __name__ == '__main__': unittest.main()
