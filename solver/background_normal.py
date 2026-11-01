"""通常作成を端末から切り離して進めるための検証用ロジック。"""

def rank(r):
    m = r.get('allocation') or {}
    return [r.get('restExceptionCount') or 0, r.get('exceptionCount') or 0,
            r.get('nightRemainderExceptions') or 0, r.get('restBalanceExceptions') or 0,
            r.get('staffingShortfallTotal') or 0, r.get('nightShortfallTotal') or 0,
            r.get('overtimeCycleExcess') or 0,
            len((r.get('nightRestPreferences') or {}).get('unmet') or []),
            m.get('nightSpread') or 0, m.get('overtimeTotal') or 0,
            m.get('overtimeBalance') if m.get('overtimeBalance') is not None else (m.get('overtimeSpread') or 0),
            m.get('surplusTotal') or 0, -(m.get('commonExtraDaysOff') or 0), m.get('minor') or 0]

def proof(r):
    return [r.get('status') == 'OPTIMAL', bool(r.get('preferencePriorityProven')),
            bool((r.get('allocation') or {}).get('minimumOvertimeProven')),
            bool((r.get('overtimeFairness') or {}).get('minimumSpreadProven')),
            bool(r.get('shortfallProvenMinimum')),
            bool((r.get('nightFairness') or {}).get('minimumSpreadProven'))]

def compare(a, b):
    for x, y in zip(rank(a), rank(b)):
        if x != y: return x - y
    for x, y in zip(proof(a), proof(b)):
        if x != y: return int(y) - int(x)
    return 0

def candidate(r):
    return bool(r and r.get('assignments') and r.get('status') in ('OPTIMAL', 'FEASIBLE', 'DRAFT'))

async def normal(input_data, initial, solve, max_seconds=480, base_seconds=60):
    best = last = resume = None
    seconds = 0
    done = False
    bound = None
    rounds = []
    while max_seconds - seconds > .1:
        budget = min(base_seconds, max_seconds - seconds)
        baseline = best.get('assignments') if best else initial
        req = {'input': input_data, 'seconds': budget, 'adaptive': False, 'qualityFirst': True,
               'seed': len(rounds) % 1000 + 1, 'allowStaffingShortfall': True,
               'allowNightShortfall': False, 'allowRuleExceptions': True}
        if baseline: req['initialAssignments'] = baseline
        if resume: req['resume'] = resume
        r = await solve(req)
        last = r
        elapsed = r.get('seconds')
        if not isinstance(elapsed, (float, int)) or isinstance(elapsed, bool) or elapsed < 0:
            elapsed = budget
        seconds += elapsed
        search = r.get('search') or {}
        rounds.append({'seconds': elapsed, 'status': r.get('status'), 'reason': search.get('reason'),
                       'stage': (search.get('resume') or {}).get('stage')})
        lower = r.get('shortfallLowerBound')
        if isinstance(lower, int) and not isinstance(lower, bool): bound = max(bound or 0, lower)
        improved = candidate(r) and (not best or compare(r, best) <= 0)
        if improved: best = r
        status = r.get('status')
        if status == 'WORKER_ERROR': break
        if status in ('OPTIMAL', 'INFEASIBLE', 'INVALID_INPUT', 'VALIDATION_FAILED'):
            done = status == 'OPTIMAL'
            break
        if search.get('done') is True:
            done = True
            break
        if not (search.get('continueRecommended') is True or status == 'UNKNOWN'): break
        resume = search.get('resume') if improved or not best else None
    if best and bound is not None and isinstance(best.get('staffingShortfallTotal'), int):
        best = {**best, 'shortfallLowerBound': min(bound, best['staffingShortfallTotal'])}
    return {'best': best, 'last': last, 'seconds': seconds, 'rounds': rounds, 'error': '計算を完了できませんでした。' if last and last.get('status') == 'WORKER_ERROR' else None, 'done': done, 'stale': False}

