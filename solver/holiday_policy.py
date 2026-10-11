"""通常の最低公休から独立した、おまかせの目標・範囲・個別固定。"""
from copy import deepcopy
from .input_data import normalize

POLICY = 'auto-holidays-4'


def checked_policy(raw, value):
    p = normalize(raw)
    if not isinstance(value, dict) or set(value) != {s['id'] for s in p['staff']}:
        raise ValueError('おまかせの職員ごとの公休条件を確認してください。')
    result = {}
    for st in p['staff']:
        q = value[st['id']]
        if (not isinstance(q, dict) or set(q) != {'min', 'target', 'max', 'fixed'}
                or type(q['fixed']) is not bool
                or any(type(q[k]) is not int for k in ('min', 'target', 'max'))
                or not 0 <= q['min'] <= q['target'] <= q['max'] <= p['days']
                or (q['fixed'] and not q['min'] == q['target'] == q['max'])):
            raise ValueError('公休の下限・目標・上限、個別固定を確認してください。')
        if q['fixed'] and q['target'] != st['monthlyDaysOff']:
            raise ValueError('個別固定の日数は通常版と共通です。')
        result[st['id']] = dict(q)
    return result


def effective_input(raw, quotas):
    out = deepcopy(raw)
    for st in out['staff']:
        st['monthlyDaysOff'] = quotas[st['id']]
    normalize(out)
    return out


def target_input(raw, policy):
    return effective_input(raw, {sid: q['target'] for sid, q in policy.items()})


def checked_quotas(policy, quotas, raw=None):
    if not isinstance(quotas, dict) or set(quotas) != set(policy):
        raise ValueError('採用した公休日数を確認してください。')
    for sid, n in quotas.items():
        if type(n) is not int or not policy[sid]['min'] <= n <= policy[sid]['max']:
            raise ValueError('採用した公休日数が調整範囲に合いません。')
    if raw is not None:
        groups = {}
        for st in normalize(raw)['staff']:
            q = policy[st['id']]
            key = (st['type'], q['min'], q['target'], q['max'], q['fixed'])
            if key in groups and groups[key] != quotas[st['id']]:
                raise ValueError('同じ公休条件の職員は共通の日数で指定してください。')
            groups[key] = quotas[st['id']]
    return dict(quotas)
