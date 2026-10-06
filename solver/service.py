"""ローカル・公開環境で同じ入力検査を通す。個人名や表をログに記録しない。"""
from .engine import solve
from .input_data import normalize
from .validator import validate
from .night_preferences import report
from .quality_search import STAGES

ADAPTIVE_MIN_SECONDS = 15
ADAPTIVE_AFTER_FIRST = 10
DIAGNOSIS_SECONDS = 20


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
            result = {'status': 'INVALID' if errors else 'VALID', 'validationErrors': errors, 'boundaryComplete': p['boundaryComplete']}
            if not any(e['code'] == 'structure' for e in errors):
                result['nightRestPreferences'] = report(p, payload['assignments'])
            return result
        seconds = payload.get('seconds', 15)
        if type(seconds) not in (int, float) or not 0 < seconds <= 60:
            raise ValueError('計算時間は1〜60秒にしてください。')
        # adaptive：上限まで探すが、15秒たち、かつ最初の表から10秒たった時点で返す。
        adaptive = payload.get('adaptive', False)
        if type(adaptive) is not bool:
            raise ValueError('adaptive は true か false で指定してください。')
        quality_first = payload.get('qualityFirst', False)
        if type(quality_first) is not bool:
            raise ValueError('qualityFirst は true か false で指定してください。')
        # seed：時間内に見つからなかったとき、探す順番を変えて再計算するための値。
        seed = payload.get('seed', 1)
        if type(seed) is not int or not 1 <= seed <= 1000:
            raise ValueError('seed は1〜1000の整数で指定してください。')
        allow_shortfall = payload.get('allowStaffingShortfall', False)
        if type(allow_shortfall) is not bool:
            raise ValueError('allowStaffingShortfall は true か false で指定してください。')
        allow_night_shortfall = payload.get('allowNightShortfall', False)
        if type(allow_night_shortfall) is not bool or (allow_night_shortfall and not allow_shortfall):
            raise ValueError('夜勤未配置は人数不足の下書きでのみ指定できます。')
        # 中間ルール：連勤上限・連勤＋1・日勤の種類（許可した人のみ）を、守ると作れないときだけ最小限破る。
        allow_exceptions = payload.get('allowRuleExceptions', False)
        if type(allow_exceptions) is not bool or (allow_exceptions and not allow_shortfall):
            raise ValueError('allowRuleExceptions は人数不足を許す作成でのみ true にできます。')
        resume = check_resume(payload.get('resume'), quality_first)
    except (ValueError, TypeError) as exc:
        return {'status': 'INVALID_INPUT', 'errors': [str(exc)]}
    # 通常作成は不足許可でも早期終了。追加計算は adaptive=false で上限まで改善する。
    rule = {'min_seconds': min(ADAPTIVE_MIN_SECONDS, seconds), 'after_first': ADAPTIVE_AFTER_FIRST} if adaptive and not quality_first else {}
    if quality_first:
        rule['quality_first'] = True
    if resume is not None:
        rule['resume'] = resume
    result = solve(raw, seconds=seconds, seed=seed, initial_assignments=payload.get('initialAssignments'), allow_staffing_shortfall=allow_shortfall, allow_night_shortfall=allow_night_shortfall, allow_rule_exceptions=allow_exceptions, **rule)
    if result.get('status') == 'INFEASIBLE' and allow_shortfall:
        # 作れないときだけ、どの希望・固定を外せば作れるか、夜勤を埋められない日はどこかを調べる。
        result['diagnosis'] = solve(raw, seconds=min(DIAGNOSIS_SECONDS, seconds), seed=seed, allow_staffing_shortfall=True,
                                    allow_rule_exceptions=allow_exceptions, relax_wishes=True)
    return result


def check_resume(value, quality_first):
    if value is None:
        return None
    if not quality_first or not isinstance(value, dict) or set(value) - {'stage', 'idle', 'proven'}:
        raise ValueError('resume の形式を確認してください。')
    if value.get('stage') not in STAGES:
        raise ValueError('resume.stage を確認してください。')
    idle = value.get('idle', 0)
    if type(idle) not in (int, float) or not 0 <= idle <= 600:
        raise ValueError('resume.idle を確認してください。')
    proven = value.get('proven', {})
    if not isinstance(proven, dict) or set(proven) - set(STAGES) or any(type(v) is not bool for v in proven.values()):
        raise ValueError('resume.proven を確認してください。')
    return {'stage': value['stage'], 'idle': float(idle), 'proven': dict(proven)}

