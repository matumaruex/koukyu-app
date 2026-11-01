"""端末の秘密による結果保護と匿名化の検査。すべて架空データ。"""
import hashlib
import unittest
from unittest.mock import AsyncMock, patch
from api.background import handle

TOKEN='a'*64
DIGEST=hashlib.sha256(TOKEN.encode()).hexdigest()

class Run:
    run_id='wrun_TEST123'
    def __init__(self, digest=DIGEST, state='completed'):
        self.digest=digest; self.state=state; self.terminated=False
    async def attributes(self): return {} if self.digest is None else {'access_hash':self.digest}
    async def status(self): return self.state
    async def return_value(self): return {'best':{'assignments':{'s0':{'1':'off'}}}}
    async def terminate(self): self.terminated=True

class BackgroundApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_removes_names_and_stores_only_hash(self):
        run=Run()
        with patch('api.background.workflow.start', new=AsyncMock(return_value=run)) as start:
            code,result=await handle({'action':'start','token':TOKEN,'mode':'normal','input':{'staff':[{'id':'s0','name':'架空'}]}})
        self.assertEqual((code,result),(200,{'runId':run.run_id}))
        args=start.await_args.args
        self.assertEqual(args[2]['staff'],[{'id':'s0'}])
        self.assertEqual(args[-1],DIGEST)
        self.assertNotIn(TOKEN,repr(args))

    async def test_read_requires_matching_secret(self):
        with patch('api.background.workflow.get_run',return_value=Run()):
            code,result=await handle({'action':'status','token':'b'*64,'runId':'wrun_TEST123'})
            self.assertEqual(code,403)
            self.assertNotIn('result',result)
            code,result=await handle({'action':'status','token':TOKEN,'runId':'wrun_TEST123'})
            self.assertEqual(code,200)
            self.assertEqual(result['result']['best']['assignments']['s0']['1'],'off')

    async def test_cancel_requires_matching_secret(self):
        run=Run()
        with patch('api.background.workflow.get_run',return_value=run):
            await handle({'action':'cancel','token':'b'*64,'runId':'wrun_TEST123'})
            self.assertFalse(run.terminated)
            await handle({'action':'cancel','token':TOKEN,'runId':'wrun_TEST123'})
            self.assertTrue(run.terminated)

    async def test_creation_race_is_not_authorized(self):
        with patch('api.background.workflow.get_run',return_value=Run(None)):
            _,result=await handle({'action':'status','token':TOKEN,'runId':'wrun_TEST123'})
            self.assertEqual(result,{'status':'not_ready'})

    async def test_reject_malformed_values(self):
        for payload in ({'action':'status','token':'no','runId':'wrun_TEST123'}, {'action':'status','token':TOKEN,'runId':'../../x'}):
            code,_=await handle(payload)
            self.assertIn(code,(400,403))

if __name__=='__main__': unittest.main()
