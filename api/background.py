"""作成を開始し、同じ端末の秘密でのみ結果を読み出す窓口。"""
import hashlib
import hmac
import json
import re
from urllib.parse import urlparse
from vercel import workflow
from solver.background import create_schedule

_TOKEN = re.compile(r'^[0-9a-f]{64}$')
_RUN = re.compile(r'^wrun_[A-Za-z0-9]+$')

async def handle(payload):
    action = payload.get('action')
    token = payload.get('token')
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return 403, {'error': '結果を開くための情報を確認できません。'}
    digest = hashlib.sha256(token.encode('ascii')).hexdigest()
    if action == 'start':
        mode = payload.get('mode')
        raw = payload.get('input')
        policy = payload.get('holidayPolicy')
        if mode != 'normal' or not isinstance(raw, dict) or not isinstance(raw.get('staff'), list):
            return 400, {'error': '作成条件を確認してください。'}
        raw = dict(raw)
        raw['staff'] = [{k:v for k,v in st.items() if k != 'name'} for st in raw['staff'] if isinstance(st, dict)]
        run = await workflow.start(create_schedule, mode, raw, policy, payload.get('initialAssignments'), digest)
        return 200, {'runId': run.run_id}
    run_id = payload.get('runId')
    if action not in ('status','cancel') or not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
        return 400, {'error': '作成の情報を確認できません。'}
    run = workflow.get_run(run_id, type=dict)
    attributes = await run.attributes()
    saved = attributes.get('access_hash')
    if saved is None:
        return 200, {'status': 'not_ready'}
    if not hmac.compare_digest(saved, digest):
        return 403, {'error': '結果を開くための情報を確認できません。'}
    if action == 'cancel':
        await run.terminate()
        return 200, {'status': 'cancelled'}
    status = await run.status()
    if status == 'completed':
        return 200, {'status': status, 'result': await run.return_value()}
    stage = saved_stage if (saved_stage := attributes.get('stage')) in ('conditions', 'overtime', 'overtime_fairness', 'placement') else None
    return 200, {'status': status, 'stage': stage}

async def app(scope, receive, send):
    if scope['type'] != 'http':
        return
    headers = {k.decode('latin1').lower():v.decode('latin1') for k,v in scope.get('headers', [])}
    status, result = 500, {'error': '作成サービスに接続できませんでした。時間をおいて再確認してください。'}
    try:
        if scope.get('method') != 'POST':
            status, result = 405, {'error': '操作を確認してください。'}
        elif headers.get('origin') and urlparse(headers['origin']).netloc != headers.get('host', ''):
            status, result = 403, {'error': 'アプリから操作してください。'}
        elif not headers.get('content-type','').lower().startswith('application/json'):
            status, result = 415, {'error': '入力形式を確認してください。'}
        else:
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body',b''))
                if len(body)>400_000:
                    status, result = 413, {'error': 'データが大きすぎます。'}
                    break
                if not message.get('more_body',False):
                    data=json.loads(body)
                    if not isinstance(data,dict):
                        status, result = 400, {'error':'入力形式を確認してください。'}
                    else:
                        status, result = await handle(data)
                    break
    except (ValueError, TypeError):
        status, result = 400, {'error': '入力データを読み取れませんでした。'}
    except Exception as exc:
        if getattr(exc, 'status', None) in (404, 410):
            status, result = 410, {'error': '結果の受け取り期限が過ぎました。元の表は残っています。'}
    body=json.dumps(result,ensure_ascii=False).encode('utf-8')
    await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json; charset=utf-8'),(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')]})
    await send({'type':'http.response.body','body':body})
