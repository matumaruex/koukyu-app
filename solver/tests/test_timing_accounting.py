"""連休なし・夜勤端数の予備判定も、画面へ返す累計計算時間に含める。"""
import unittest
from unittest.mock import patch
from ortools.sat.python import cp_model
from solver.engine import solve
from solver.quality_search import search
from solver.tests.test_no_consecutive_rest import setting
from solver.tests.test_night_remainder import priority


class TimingAccountingTests(unittest.TestCase):
    def test_proof_calculations_are_included_and_original_budget_is_reported(self):
        combined = priority('s1')
        combined['staff'][0]['noConsecutiveRest'] = True
        for raw in (setting(), priority('s1'), combined):
            with self.subTest(rest=raw['staff'][0].get('noConsecutiveRest'),
                              night=raw['staff'][1].get('nightRemainderPriority')):
                phase = []

                def calculation(*args, **kwargs):
                    result = search(*args, **kwargs)
                    phase.append(result['seconds'])
                    return result

                # 実際にCP-SATを実行する。予備判定を0.4秒長く数え、
                # 丸め誤差では説明できない集計漏れを安定して検査する。
                wall_time = cp_model.CpSolver.wall_time.fget
                with patch.object(cp_model.CpSolver, 'wall_time',
                                  property(lambda solver: wall_time(solver) + .4)), \
                        patch('solver.engine.quality_search', calculation):
                    result = solve(raw, seconds=8, quality_first=True,
                                   allow_staffing_shortfall=True, allow_rule_exceptions=True)
                self.assertIn('assignments', result)
                proof_seconds = sum(result.get(name, {}).get('seconds', 0)
                                    for name in ('noConsecutiveRest', 'nightRemainder'))
                self.assertGreater(proof_seconds, .4)
                self.assertAlmostEqual(result['seconds'], phase[0] + proof_seconds, delta=.002)
                self.assertEqual(result['timing']['maxSeconds'], 8)


if __name__ == '__main__':
    unittest.main()
