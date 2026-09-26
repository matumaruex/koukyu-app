"""ローカル・公開環境で同じ入力検査を通す。個人名や表をログに記録しない。"""
from .engine import solve
from .input_data import normalize
from .validator import validate

ADAPTIVE_MIN_SECONDS = 15
ADAPTIVE_AFTER_FIRST = 10


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
        # adaptive：上限まで探すが、15秒たち、かつ最初の表から10秒たった時点で返す。
        adaptive = payload.get('adaptive', False)
        if type(adaptive) is not bool:
            raise ValueError('adaptive は true か false で指定してください。')
        # seed：時間内に見つからなかったとき、探す順番を変えて再計算するための値。
        seed = payload.get('seed', 1)
        if type(seed) is not int or not 1 <= seed <= 1000:
            raise ValueError('seed は1〜1000の整数で指定してください。')
    except (ValueError, TypeError) as exc:
        return {'status': 'INVALID_INPUT', 'errors': [str(exc)]}
    rule = {'min_seconds': min(ADAPTIVE_MIN_SECONDS, seconds), 'after_first': ADAPTIVE_AFTER_FIRST} if adaptive else {}
    return solve(raw, seconds=seconds, seed=seed, initial_assignments=payload.get('initialAssignments'), **rule)
