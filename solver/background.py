"""画面を離れても、氏名を含まない入力で作成を継続する。"""
import asyncio
from vercel import workflow
from solver.background_normal import normal
from solver.background_auto import auto

wf = workflow.Workflows()

@wf.step
async def calculate(request):
    from solver.service import dispatch
    # エラーの詳細には勤務情報が混ざる場合があるので記録しない。
    try:
        return await asyncio.to_thread(dispatch, request)
    except Exception:
        return {'status': 'WORKER_ERROR', 'seconds': 0}

@wf.workflow
async def create_schedule(mode, raw, policy, initial, access_hash):
    # 属性は暗号化されないため、ランダムな鍵のハッシュのみを記録する。
    await workflow.set_attributes(access_hash=access_hash)
    if mode == 'auto':
        return await auto(raw, policy, calculate)
    return await normal(raw, initial, calculate)
