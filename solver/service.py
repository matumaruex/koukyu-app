"""ローカル・公開環境で同じ入力検査を通す。個人名や表をログに記録しない。"""
from .engine import solve
from .input_data import normalize
from .validator import validate


def dispatch(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('input'), dict):
        return {'status': 'INVALID_INPUT', 'errors': ['職員と対象期間を確認してください。']}
    raw = payload['input']
    try:
        p = normalize(raw)
        if len(p['staff']) > 40:
            raise ValueError('40人以内で指定してください。')
        if payload.get('action') == 'validate':
            errors = validate(raw, payload.get('assignments'))
            return {'status': 'INVALID' if errors else 'VALID', 'validationErrors': errors, 'boundaryComplete': p['boundaryComplete']}
        seconds = payload.get('seconds', 15)
        if type(seconds) not in (int, float) or not 0 < seconds <= 60:
            raise ValueError('計算時間は1〜60秒にしてください。')
    except (ValueError, TypeError) as exc:
        return {'status': 'INVALID_INPUT', 'errors': [str(exc)]}
    return solve(raw, seconds=seconds, initial_assignments=payload.get('initialAssignments'))
