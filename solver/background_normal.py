"""通常作成を端末から切り離して進めるための検証用ロジック。"""

def rank(r):
    m = r.get('allocation') or {}
    return [r.get('restExceptionCount') or 0, r.get('exceptionCount') or 0,
            r.get('nightRemainderExceptions') or 0, r.get('restBalanceExceptions') or 0,
            r.get('isolatedWorkExceptions') or 0, r.get('restStreakExceptions') or 0,
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

async def normal(input_data, initial, solve, max_seconds=480, base_seconds=60, progress=None, improvement=False, compare_initial=False):
    best = last = resume = None
    initial_rank = None
    seconds = 0
    done = False
    bound = None
    rounds = []
    while max_seconds - seconds > .1:
        if progress:
            await progress((resume or {}).get('stage', 'conditions'))
        budget = min(base_seconds, max_seconds - seconds)
        baseline = best.get('assignments') if best else initial
        req = {'input': input_data, 'seconds': budget, 'adaptive': False, 'qualityFirst': True,
               'seed': len(rounds) % 1000 + 1, 'allowStaffingShortfall': True,
               'allowNightShortfall': False, 'allowRuleExceptions': True}
        if baseline: req['initialAssignments'] = baseline
        if resume: req['resume'] = resume
        if improvement:
            req['improvementPass'] = True
        if compare_initial and not rounds:
            req['compareInitial'] = True
        r = await solve(req)
        if not rounds:
            initial_rank = r.get('initialRank')
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
    return {**({'initialRank': initial_rank} if initial_rank is not None else {}), 'best': best, 'last': last, 'seconds': seconds, 'rounds': rounds, 'error': '計算を完了できませんでした。' if last and last.get('status') == 'WORKER_ERROR' else None, 'done': done, 'stale': False}


async def create_normal(input_data, initial, solve, progress=None):
    if initial:
        return await normal(input_data, initial, solve, progress=progress, improvement=True, compare_initial=True)
    first = await normal(input_data, None, solve, progress=progress)
    best = first['best']
    if not best or first['error'] or best['status'] == 'OPTIMAL' or best.get('solverStatus') == 'OPTIMAL':
        return first

    async def improving(_stage):
        if progress:
            await progress('improvement')

    extra = await normal(input_data, best['assignments'], solve, progress=improving, improvement=True)
    other = extra['best']
    # 同点で勤務を動かさない。同じ勤務について新たに得た証明だけは採用できる。
    if other and (rank(other) < rank(best) or
                  (other['assignments'] == best['assignments'] and compare(other, best) < 0)):
        best = other
    return {**extra, 'best': best, 'seconds': first['seconds'] + extra['seconds'],
            'rounds': first['rounds'] + extra['rounds'], 'automaticImprovement': True,
            'error': extra['error'] or (None if other else '追加計算を完了できませんでした。')}
