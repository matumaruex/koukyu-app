"""通常版の残業歓迎。合計を増やさず、比率換算後の回数から希望の上乗せを引いて比較する。"""
from copy import deepcopy
from functools import lru_cache
from .input_data import overtime_profile

POLICY = 'quality-first-7'


def offsets(p, scales):
    unit = 100 if any(v != 1 for v in scales.values()) else 1
    return {st['id']: st.get('overtimePreference', 0) * unit
            for st in p['staff'] if st['id'] in scales}


def active(p):
    return any(st.get('type') != 'part' and st.get('canOvertime')
               and st.get('overtimePreference', 0) for st in p['staff'])


def without_preferences(raw):
    """おまかせは従来の計算のまま。共有設定を計算の入口で取り除く。"""
    result = deepcopy(raw)
    for st in result.get('staff', []):
        st.pop('overtimePreference', None)
    return result


def score_bounds(p, scales):
    extra = offsets(p, scales)
    low = min([-extra[sid] for sid in scales] or [0])
    high = max([scales[st['id']] * min(p['days'], overtime_profile(p, st)['cap'])
                - extra[st['id']] for st in p['staff'] if st['id'] in scales] or [0])
    return low, high


@lru_cache(maxsize=4096)
def minimum_balance(profiles, total):
    """日付の制約を除いた、固定合計・整数回数・各人の上限の下での正確な最少差。
    各区間で許される回数は連続整数なので、合計の最小～最大内なら配分できる。
    これを達成した表だけは算術的に最少と証明できる。未達成なら日付条件で探索する。
    """
    if not profiles:
        return 0
    scores = sorted({scale * count - offset for scale, offset, cap in profiles
                     for count in range(cap + 1)})
    upper = [[min(cap, (score + offset) // scale) for scale, offset, cap in profiles]
             for score in scores]
    right, best = 0, scores[-1] - scores[0]
    for left, lo in enumerate(scores):
        lower = [max(0, -(-(lo + offset) // scale)) for scale, offset, cap in profiles]
        if any(v > cap for v, (_, _, cap) in zip(lower, profiles)) or sum(lower) > total:
            break
        right = max(right, left)
        while right < len(scores):
            bounds = upper[right]
            if all(a <= b for a, b in zip(lower, bounds)) and sum(bounds) >= total:
                break
            right += 1
        if right == len(scores):
            break
        best = min(best, scores[right] - lo)
    return best


def ideal_balance(p, scales, total):
    extra = offsets(p, scales)
    profiles = tuple((scales[st['id']], extra[st['id']], min(p['days'], overtime_profile(p, st)['cap']))
                     for st in p['staff'] if st['id'] in scales)
    return minimum_balance(profiles, total)


def arithmetic_proven(m):
    return (not m['overtimeProportional'] or m.get('overtimePreferred', False)) and m['overtimeBalance'] == m['overtimeIdealBalance']
