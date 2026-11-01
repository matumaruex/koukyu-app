"""残業総数と配分を優先したうえで、期間内への集中を減らす。"""
from functools import lru_cache
from .input_data import overtime_profile

POLICY = 'rolling-overtime-distribution-1'
WEIGHT = 100
WINDOWS = (7, 14, 15)


def eligible(p):
    return [st for st in p['staff'] if p.get('overtimeDistribution')
            and st['type'] != 'part' and st['canOvertime']
            and overtime_profile(p, st)['cap'] > 0]


@lru_cache(maxsize=64)
def staff_score_bound(n, cap):
    result = 0
    for length in WINDOWS:
        # 区間内は連日の残業不可。1回の残業は最大length個の区間に入る。
        # count<=mなら max(0,count-target)<=count*max(0,m-target)/m。
        # 月の回数ごとの上限を調べ、すべての区間の超過を安全に抑える。
        bounds = []
        for total in range(1, cap + 1):
            maximum = min(total, (length + 1) // 2)
            target = (length * total + n - 1) // n
            bounds.append(length * total * max(0, maximum - target) // maximum)
        result += max(bounds, default=0)
    return result


def score_bound(p):
    return sum(staff_score_bound(p['days'], overtime_profile(p, st)['cap']) for st in eligible(p))


def bound(p):
    return WEIGHT * score_bound(p)


def build(model, p, x, overtime_totals):
    n, terms = p['days'], []
    for st in eligible(p):
        sid, prefix = st['id'], [0]
        for day in range(1, n + 1):
            cumulative = model.new_int_var(0, day, f'{sid}_overtime_prefix_{day}')
            model.add(cumulative == prefix[-1] + x[sid, day - 1, 'overtime'])
            prefix.append(cumulative)
        for length in WINDOWS:
            ceiling = model.new_int_var(0, length, f'{sid}_overtime_window_cap_{length}')
            model.add_division_equality(ceiling, length * overtime_totals[sid] + n - 1, n)
            for start in range(n - length + 1):
                excess = model.new_int_var(0, length, f'{sid}_overtime_cluster_{length}_{start}')
                model.add_max_equality(excess, [prefix[start + length] - prefix[start] - ceiling, 0])
                terms.append(excess)
    if not terms:
        return 0
    total = model.new_int_var(0, score_bound(p), 'overtime_distribution_penalty')
    model.add(total == sum(terms))
    return WEIGHT * total


def report(p, assignments):
    n, rows = p['days'], {}
    for st in eligible(p):
        sid, values = st['id'], assignments[st['id']]
        dates = [d for d in range(1, n + 1) if values[str(d)] == 'overtime']
        count, penalty, by_window, prefix = len(dates), 0, {}, [0]
        for day in range(1, n + 1):
            prefix.append(prefix[-1] + (values[str(day)] == 'overtime'))
        for length in WINDOWS:
            target = (length * count + n - 1) // n
            counts = [prefix[start + length] - prefix[start] for start in range(n - length + 1)]
            excess = sum(max(0, value - target) for value in counts)
            penalty += excess
            by_window[str(length)] = {'targetMaximum': target, 'maximum': max(counts), 'penalty': excess}
        rows[sid] = {'dates': dates, 'count': count, 'penalty': penalty, 'windows': by_window}
    return {'policy': POLICY, 'penalty': sum(row['penalty'] for row in rows.values()), 'byStaff': rows}
