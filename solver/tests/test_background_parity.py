"""元の画面側のワークフローが返した架空の結果との比較。"""
import json
from copy import deepcopy
import subprocess
import unittest
from pathlib import Path
from solver.background_normal import normal

HERE=Path(__file__).parent

class BackgroundParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_arrangement_exceptions_match_browser_and_keep_better_candidate(self):
        base = {'status': 'FEASIBLE', 'seconds': 1, 'allocation': {'overtimeTotal': 0}}
        for field in ('isolatedWorkExceptions', 'restStreakExceptions'):
            with self.subTest(field=field):
                good = dict(base, assignments={'s0': {'1': 'early'}}, staffingShortfallTotal=1,
                            **{field: 0})
                bad = dict(base, assignments={'s0': {'1': 'late'}}, staffingShortfallTotal=0,
                           **{field: 1})
                for order in ([good, bad], [bad, good]):
                    replies = deepcopy(order)
                    replies[0]['search'] = {'continueRecommended': True}
                    replies[1]['search'] = {'done': True}
                    script = ('const flow=require("./public/creation-workflow.js");const rows='
                              + json.dumps(replies) + ';let i=0;flow.run({input:{},'
                              'nextSeed:()=>1,request:async()=>rows[i++]}).then(r=>console.log(JSON.stringify(r.best)));')
                    expected = json.loads(subprocess.check_output(
                        ['node', '-e', script], cwd=HERE.parent.parent, text=True))
                    iterator = iter(replies)
                    async def solve(_): return next(iterator)
                    result = await normal({}, None, solve)
                    self.assertEqual(result['best'], expected)
                    self.assertEqual(result['best'][field], 0)

    async def test_single_work_priority_remains_above_rest_streak(self):
        replies = [{'status': 'FEASIBLE', 'seconds': 1, 'assignments': {'s0': {'1': 'early'}},
                    'isolatedWorkExceptions': 0, 'restStreakExceptions': 9,
                    'search': {'continueRecommended': True}},
                   {'status': 'FEASIBLE', 'seconds': 1, 'assignments': {'s0': {'1': 'late'}},
                    'isolatedWorkExceptions': 1, 'restStreakExceptions': 0,
                    'search': {'done': True}}]
        iterator = iter(replies)
        async def solve(_): return next(iterator)
        result = await normal({}, None, solve)
        self.assertEqual(result['best'], replies[0])

    async def test_normal(self):
        cases=json.loads((HERE/'background_normal_cases.json').read_text(encoding='utf8'))
        for case in cases:
            calls=[]
            async def solve(request):
                calls.append({k:v for k,v in request.items() if k not in ('allowStaffingShortfall','allowNightShortfall','allowRuleExceptions')})
                return case['replies'][len(calls)-1]
            result=await normal({'staff':[]},{'z':{'1':'off'}},solve)
            self.assertEqual(calls,case['calls'])
            self.assertEqual(result,case['result'])

    async def test_progress_contains_only_public_stage_names(self):
        stages = []
        async def progress(stage): stages.append(stage)
        replies = iter([{'status':'FEASIBLE','assignments':{'s0':{'1':'off'}},'seconds':2,
                         'search':{'continueRecommended':True,'resume':{'stage':'overtime'}}},
                        {'status':'OPTIMAL','assignments':{'s0':{'1':'off'}},'seconds':1}])
        async def solve(_): return next(replies)
        result = await normal({}, None, solve, progress=progress)
        self.assertEqual(stages, ['conditions', 'overtime'])
        self.assertTrue(result['done'])

    async def test_solver_error_retains_existing_best(self):
        best={'status':'FEASIBLE','assignments':{'s0':{'1':'off'}},'seconds':60,
              'allocation':{'overtimeTotal':2},'search':{'continueRecommended':True}}
        replies=iter([best,{'status':'WORKER_ERROR','seconds':0}])
        async def solve(_): return next(replies)
        result=await normal({},None,solve)
        self.assertEqual(result['best'],best)
        self.assertTrue(result['error'])

if __name__=='__main__': unittest.main()
