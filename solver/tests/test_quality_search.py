"""条件・残業合計・回数差を確定してから、残り時間で配置を改善する。"""
import unittest
from contextlib import nullcontext
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.service import dispatch
from solver.validator import validate
from solver.quality_search import search
from solver.service import check_resume
from solver.tests.test_night_fairness import six_staff, equal_shortfall_fixture


class QualitySearchTests(unittest.TestCase):
    def test_four_stages_validate_complete_table_and_can_finish_early(self):
        raw = six_staff()
        r = solve(raw, seconds=5, quality_first=True)
        self.assertEqual(validate(raw, r['assignments']), [])
        self.assertEqual(sorted(r['nightFairness']['byStaff'].values()), [5]*6)
        self.assertTrue(r['allocation']['minimumOvertimeProven'])
        self.assertEqual(r['allocation']['overtimeTotal'], 0)
        self.assertEqual(r['timing']['mode'], 'quality')
        self.assertEqual([s['stage'] for s in r['search']['stages']], ['conditions','overtime','overtime_fairness','placement'])
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


class CandidateProofTests(unittest.TestCase):
    """実CP-SATの小さい候補集合で、採用表と証明の取り違えを再現する。"""

    def run_case(self, *, rows=None, stage='overtime', seconds=2, proven=None,
                 proof_values=None, prefer_first_overtime=True, disable_bounds=False):
        rows = rows or [(0, 1, 2, 3), (1, 2, 2, 0), (2, 2, 3, 3)]
        model = cp_model.CpModel()
        choice = model.new_int_var(0, 2, 'choice')
        shifts = ('early', 'late', 'night')
        for shift in ('off', 'early', 'late', 'overtime', 'night', 'nightOff', 'part'):
            var = model.new_bool_var('s_0_' + shift)
            if shift in shifts:
                model.add(choice == shifts.index(shift)).only_enforce_if(var)
                model.add(choice != shifts.index(shift)).only_enforce_if(var.Not())
            else:
                model.add(var == 0)
        priority = model.new_int_var(0, 3, 'priority')
        overtime = model.new_int_var(0, 3, 'overtime')
        balance = model.new_int_var(0, 3, 'balance')
        objective = model.new_int_var(0, 1000, 'objective')
        model.add_allowed_assignments([choice, priority, overtime, balance], rows)
        model.add(objective == overtime * 100 + balance * 10)
        values = {shifts[c]: (pr, ot, fair) for c, pr, ot, fair in rows}

        def counts(p, assignments):
            pr, ot, fair = values[assignments['s']['1']]
            return dict(overtimeTotal=ot, overtimeBalance=fair, overtimeIdealBalance=0,
                        overtimeProportional=False, overtimePreferred=True, extraOffSpread=0)

        def quality(p, assignments):
            pr, ot, fair = values[assignments['s']['1']]
            return ot * 100 + fair * 10

        class TieSolver(cp_model.CpSolver):
            def solve(self, working, *args, **kwargs):
                if (prefer_first_overtime and list(working.proto.objective.vars) == [overtime.index]
                        and list(working.proto.objective.coeffs) == [1]):
                    # 合計最少の同点候補から上位条件の良い候補を返す、合法な探索経路。
                    working = working.clone()
                    working.add(working.get_int_var_from_proto_index(choice.index) == 0)
                return super().solve(working, *args, **kwargs)

        def new_solver(budget):
            solver = TieSolver()
            solver.parameters.max_time_in_seconds = budget
            solver.parameters.num_search_workers = 1
            return solver

        resume = dict(stage=stage, idle=0, proven=proven or {})
        if proof_values is not None:
            resume['proofValues'] = proof_values
        real_add = cp_model.CpModel.add
        guard = (patch.object(cp_model.CpModel, 'add', lambda m, constraint: real_add(m, True))
                 if disable_bounds else nullcontext())
        with patch('solver.quality_search.metrics', counts), patch('solver.quality_search.quality_value', quality), guard:
            result = search(model, {'days': 1}, seconds=seconds, priority=priority,
                            objective=objective, overtime=overtime, overtime_spread=balance,
                            new_solver=new_solver,
                            extract=lambda solver: {'s': {'1': shifts[solver.value(choice)]}},
                            priority_of=lambda a: values[a['s']['1']][0],
                            initial_assignments={'s': {'1': 'night'}}, resume=resume)
        return result, balance

    def test_later_stage_uses_latest_improved_priority_not_old_upper_bound(self):
        # 初期A=(条件2,合計3,差3)。B=(1,2,3)を採用後、C=(2,2,0)は探索範囲から除く。
        result, balance = self.run_case()
        self.assertEqual(result['candidate'], {'s': {'1': 'early'}})
        self.assertTrue(result['overtimeSpreadProven'])
        self.assertEqual(result['solver'].value(balance), 3)
        self.assertEqual(result['priorityValue'], 1)

    def test_rejected_optimum_does_not_certify_retained_candidate(self):
        # 公平化の候補は差0だが合計3。基準の合計2が維持されるため候補を採用しない。
        # extract後の採用検査を独立に確認するため、このテストだけ上限追加を無効にする。
        result, _ = self.run_case(rows=[(0, 1, 3, 0), (1, 2, 2, 0), (2, 1, 2, 3)],
                                  stage='overtime_fairness', prefer_first_overtime=False,
                                  disable_bounds=True)
        self.assertEqual(result['candidate'], {'s': {'1': 'night'}})
        self.assertFalse(result['overtimeSpreadProven'])
        self.assertTrue(result['info']['continueRecommended'])
        self.assertEqual(result['info']['resume']['stage'], 'overtime_fairness')

    def test_old_proofs_without_values_are_not_reused(self):
        result, _ = self.run_case(stage='placement', seconds=.000001,
                                 proven=dict(conditions=True, overtime=True, overtime_fairness=True))
        self.assertFalse(result['priorityProven'])
        self.assertFalse(result['overtimeProven'])
        self.assertFalse(result['overtimeSpreadProven'])

    def test_proofs_are_carried_only_when_the_candidate_values_match(self):
        proven = dict(conditions=True, overtime=True, overtime_fairness=True)
        scopes = dict(conditions=[2], overtime=[2, 3], overtime_fairness=[2, 3, 3])
        result, _ = self.run_case(stage='placement', seconds=.000001, proven=proven, proof_values=scopes)
        self.assertTrue(result['priorityProven'])
        self.assertTrue(result['overtimeProven'])
        self.assertTrue(result['overtimeSpreadProven'])
        scopes['overtime_fairness'] = [2, 3, 0]
        result, _ = self.run_case(stage='placement', seconds=.000001, proven=proven, proof_values=scopes)
        self.assertFalse(result['overtimeSpreadProven'])
        self.assertEqual(result['info']['resume']['proofValues'],
                         dict(conditions=[2], overtime=[2, 3]))

    def test_proof_values_input_checks(self):
        value = dict(stage='placement', idle=0, proven={'overtime': True},
                     proofValues={'overtime': [None, 2]})
        self.assertEqual(check_resume(value, True), value)
        for bad in ({'unknown': [0]}, {'overtime': [2]}, {'overtime': [0, True]},
                    {'overtime': [0, -1]}, {'overtime': [0, 1.5]}, []):
            with self.assertRaises(ValueError):
                check_resume(dict(value, proofValues=bad), True)


if __name__ == '__main__': unittest.main()
