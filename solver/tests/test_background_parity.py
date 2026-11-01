"""元の画面側のワークフローが返した架空の結果との比較。"""
import json
import unittest
from pathlib import Path
from solver.background_normal import normal
from solver.background_auto import auto

HERE=Path(__file__).parent

class BackgroundParityTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_auto(self):
        cases=json.loads((HERE/'background_auto_cases.json').read_text(encoding='utf8'))
        policy={'a':{'min':9,'target':10,'max':11,'fixed':False}}
        for case in cases:
            calls=[]
            async def solve(request):
                calls.append(request)
                return case['replies'][len(calls)-1]
            result=await auto({},policy,solve)
            self.assertEqual(calls,case['calls'])
            self.assertEqual(result,case['result'])

    async def test_solver_error_retains_existing_best(self):
        best={'status':'FEASIBLE','assignments':{'s0':{'1':'off'}},'seconds':60,
              'allocation':{'overtimeTotal':2},'search':{'continueRecommended':True}}
        replies=iter([best,{'status':'WORKER_ERROR','seconds':0}])
        async def solve(_): return next(replies)
        result=await normal({},None,solve)
        self.assertEqual(result['best'],best)
        self.assertTrue(result['error'])

if __name__=='__main__': unittest.main()
