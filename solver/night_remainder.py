"""夜勤の端数（割り切れない分）を、職員設定で「端数を優先」にした人へ回す（3.39）。

夜勤できるフルタイム（パート以外・夜勤タイプがなし以外）で期間の夜勤を割ると、基準回数＝期間日数÷人数（切り捨て）、
端数＝余り。目安は、端数を優先する人が基準＋1回、それ以外の人が基準回数。目安を超えた夜勤の合計を「超過」と数える。
優先する人が端数より少ないときは、残りの端数（端数−優先する人数）がほかの人へ行くのは避けられないので許容量にする。
超過が許容量を超えた分だけが例外（中間ルール：数学的に無理なときだけ、最少回数を表示）。"""


def eligible(p):
    return [st for st in p['staff'] if st['type'] != 'part' and st['nightShiftType'] != 'none']


def plan(p):
    staff = eligible(p)
    priority = [st['id'] for st in staff if st.get('nightRemainderPriority')]
    if not staff or not priority:
        return None
    base, extras = divmod(p['days'], len(staff))
    fair = {st['id']: base + (1 if st['id'] in priority else 0) for st in staff}
    return {'base': base, 'extras': extras, 'priority': priority, 'fair': fair,
            'allowance': max(0, extras - len(priority))}


def report(p, assignments):
    result = plan(p)
    if result is None:
        return None
    counts = {sid: sum(v == 'night' for v in assignments[sid].values()) for sid in result['fair']}
    over = {sid: counts[sid] - result['fair'][sid] for sid in counts if counts[sid] > result['fair'][sid]}
    excess = sum(over.values())
    return {**result, 'counts': counts, 'over': over, 'excess': excess,
            'exceptions': max(0, excess - result['allowance'])}


def max_nights(p, st, seconds=2.0):
    """その職員ひとりの条件だけで入れられる夜勤の最大回数（全体の計算で使う上限の補助）。
    夜勤の曜日・夜勤→明け→公休・希望休・希望勤務・固定・前期の最終日・公休の最低日数だけを見る。
    ほかの条件を外した緩い計算なので、ここで出る回数は実際の最大以上になり、上限として使っても表を狭めない。
    この上限があると「優先する人は端数を受け持てない」ことの証明がすぐ終わる。"""
    from datetime import timedelta
    from ortools.sat.python import cp_model
    n, sid = p['days'], st['id']
    model = cp_model.CpModel()
    night = [model.new_bool_var(f'n{d}') for d in range(n)]
    recovery = [model.new_bool_var(f'r{d}') for d in range(n)]
    off = [model.new_bool_var(f'o{d}') for d in range(n)]
    history = p['history'][sid]
    requests = set(p['requests'].get(sid, []))
    wishes = p['shiftRequests'].get(sid, {})
    locked = p['locked'].get(sid, {})
    for d in range(n):
        model.add(night[d] + recovery[d] + off[d] <= 1)
        if st['nightShiftType'] == 'weekday' and (p['start'] + timedelta(days=d)).weekday() >= 4:
            model.add(night[d] == 0)
        model.add(recovery[d] == (night[d - 1] if d else int(history[6] == 'night')))
        if d:
            model.add(off[d] >= recovery[d - 1])
        elif history[6] == 'nightOff':
            model.add(off[0] == 1)
        if d + 1 in requests:
            model.add(off[d] == 1)
        fixed = locked.get(d + 1) or wishes.get(d + 1)
        if fixed == 'night':
            model.add(night[d] == 1)
        elif fixed == 'nightOff':
            model.add(recovery[d] == 1)
        elif fixed == 'off':
            model.add(off[d] == 1)
        elif fixed is not None:
            model.add(night[d] + recovery[d] + off[d] == 0)
    model.add(sum(off) >= st['monthlyDaysOff'])
    model.maximize(sum(night))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    return int(solver.objective_value) if status == cp_model.OPTIMAL else n
