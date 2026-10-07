"""条件 → 残業合計 → 残業回数差 → 配置の順に改善する。
各段階は、最少と証明できたとき、または一定時間良くならなかったときに次の段階へ進む。
証明を待ち続けて次の段階に届かない、時間で区切って良くなっている途中で打ち切る、の両方を避けるため。
60秒ずつの呼び出しに分けても続きから再開できるよう、段階と「最後に良くなってからの秒数」を返す。"""
import threading
import time
from ortools.sat.python import cp_model
from .allocation import metrics, quality_value

STAGES = ('conditions', 'overtime', 'overtime_fairness', 'placement')
# 何秒良くならなかったら次の段階へ進むか。2026年10月の実測（偽名11人の設定・5条件）で、
# 改善と改善の間隔は最大で 条件26秒・残業21秒・配置9秒だったが、人数不足が出る月は条件段階で
# 30秒以上空いてから不足が減った例があった。人数不足は最優先なので条件段階は長めにとる。
# 夜勤を必須にすると、不足のない月の条件段階は数秒で証明できるため、長くしても待ち時間は増えない。
# 残業回数差の30秒は配置段階に合わせた初期設定。公平化段階の実測に基づく値ではない。
IDLE_SECONDS = {'conditions': 60, 'overtime': 40, 'overtime_fairness': 30, 'placement': 30}


class Progress(cp_model.CpSolverSolutionCallback):
    """この段階の評価値が良くなった時刻を記録する。元の表と同じ値は改善に数えない。"""

    def __init__(self, expression, incumbent, idle_since):
        super().__init__()
        self.expression, self.best = expression, incumbent
        self.last_improvement = idle_since
        self.improvements = 0
        self.found = False

    def on_solution_callback(self):
        self.found = True
        value = int(self.value(self.expression))
        if self.best is None or value < self.best:
            self.best = value
            self.last_improvement = time.monotonic()
            self.improvements += 1


def search(model, p, *, seconds, priority, objective, overtime, new_solver,
           extract, priority_of, overtime_spread=None, initial_assignments=None, resume=None, idle_seconds=None):
    limits = dict(IDLE_SECONDS, **(idle_seconds or {}))
    start = time.monotonic()
    resume = resume or {}
    candidate = initial_assignments
    actual_candidate = False
    stages = []
    solver, status = None, cp_model.UNKNOWN
    proven = {k: bool(v) for k, v in (resume.get('proven') or {}).items() if k in STAGES}
    stage = resume.get('stage', 'conditions')
    idle = float(resume.get('idle', 0))
    pending = None
    priority_bound = lower_bound = last_quality_improvement = None
    exprs = {'conditions': priority, 'overtime': overtime,
             'overtime_fairness': overtime_spread, 'placement': objective}

    def remaining():
        return max(0.0, seconds - (time.monotonic() - start))

    def rank(a):
        return (priority_of(a) if priority is not None else 0), quality_value(p, a)

    def value_of(name, a):
        if name == 'conditions':
            return priority_of(a)
        if name == 'overtime':
            return metrics(p, a)['overtimeTotal']
        if name == 'overtime_fairness':
            # 出勤できる日数で換算した回数の差（計算の式 overtime_spread と同じ値）。
            return metrics(p, a)['overtimeBalance']
        return quality_value(p, a)

    def hints():
        model.clear_hints()
        if candidate is None:
            return
        variables = {v.name: model.get_int_var_from_proto_index(i)
                     for i, v in enumerate(model.proto.variables)}
        for sid, row in candidate.items():
            for d in range(p['days']):
                shift = row[str(d + 1)]
                for k in ('off', 'early', 'late', 'overtime', 'night', 'nightOff', 'part'):
                    model.add_hint(variables[f'{sid}_{d}_{k}'], int(k == shift))

    def run(name, expression, idle):
        nonlocal solver, status, candidate, actual_candidate
        model.minimize(expression)
        hints()
        solver = new_solver(max(0.000001, remaining()))
        progress = Progress(expression, value_of(name, candidate) if candidate is not None else None,
                            time.monotonic() - idle)
        stalled, finished = [], threading.Event()

        def watch():
            while not finished.wait(0.1):
                # 表がある状態で一定時間良くならなければ、この段階を終える（表がない間は探し続ける）。
                if ((candidate is not None or progress.found)
                        and time.monotonic() - progress.last_improvement >= limits[name]):
                    stalled.append(True)
                    solver.stop_search()
                    return

        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
        try:
            status = solver.solve(model, progress)
        finally:
            finished.set()
            thread.join()
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            found = extract(solver)
            if candidate is None or rank(found) <= rank(candidate):
                candidate = found
            actual_candidate = True
        stages.append({'stage': name, 'seconds': round(solver.wall_time, 3), 'status': solver.status_name(status),
                       'improvements': progress.improvements, 'stalled': bool(stalled)})
        return progress, bool(stalled)

    if stage not in STAGES:
        stage = 'conditions'
    # 続きの計算でも、前の段階までに得た値より悪くしない。
    if candidate is not None and priority is not None:
        model.add(priority <= priority_of(candidate))
    for name in STAGES[STAGES.index(stage):]:
        expression = exprs[name]
        if expression is None:
            idle = 0
            continue
        if remaining() <= 0.001:
            pending = name
            break
        if candidate is not None and name != 'conditions':
            model.add(objective <= quality_value(p, candidate))
            # 公平化や配置のために残業合計を増やさない。通信をまたいでも維持する。
            current = metrics(p, candidate)
            model.add(overtime <= current['overtimeTotal'])
            if proven.get('overtime'):
                # 最少合計が証明済みなら固定し、算術的な回数差の下限もモデルへ伝える。
                model.add(overtime == current['overtimeTotal'])
                if name == 'overtime_fairness' and overtime_spread is not None:
                    model.add(overtime_spread >= current['overtimeIdealBalance'])
        progress, stalled = run(name, expression, idle)
        if name == 'conditions' and status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            priority_bound = solver.best_objective_bound
        if name == 'placement':
            lower_bound = solver.best_objective_bound
            if progress.improvements:
                last_quality_improvement = round(progress.last_improvement - start, 3)
        if status == cp_model.INFEASIBLE or candidate is None:
            # 不成立の証明、または時間内に表がまだない。
            pending = None if status == cp_model.INFEASIBLE else name
            idle = 0
            break
        if status == cp_model.OPTIMAL:
            proven[name] = True
        if status == cp_model.OPTIMAL or stalled:
            # この段階の値を固定して次へ。証明済みなら最少、未証明なら「今より悪くしない」。
            model.add(expression <= value_of(name, candidate))
            idle = 0
            continue
        # この呼び出しの時間切れ。同じ段階の続きから再開する。
        pending = name
        idle = time.monotonic() - progress.last_improvement
        break

    done = pending is None and status != cp_model.INFEASIBLE
    if candidate is not None and status != cp_model.INFEASIBLE:
        all_proven = all(proven.get(k) for k in STAGES if exprs[k] is not None)
        status = cp_model.OPTIMAL if all_proven else cp_model.FEASIBLE if actual_candidate else cp_model.UNKNOWN
    if solver is None:
        solver = cp_model.CpSolver()
    priority_proven = priority is None or bool(proven.get('conditions'))
    overtime_proven = priority_proven and bool(proven.get('overtime'))
    overtime_spread_proven = overtime_proven and bool(proven.get('overtime_fairness'))
    major_ready = False
    if candidate is not None:
        m = metrics(p, candidate)
        balanced = (m['overtimeBalance'] == m['overtimeIdealBalance'] if not m['overtimeProportional']
                    else overtime_spread_proven)
        major_ready = (priority_proven and overtime_proven and balanced and m['extraOffSpread'] == 0)
    keep_going = not done and status != cp_model.INFEASIBLE
    reason = ('confirmed' if done else 'infeasible' if status == cp_model.INFEASIBLE
              else f'{pending}_unconfirmed')
    return {'solver': solver, 'status': status, 'candidate': candidate,
            'priorityProven': priority_proven,
            'priorityValue': priority_of(candidate) if candidate is not None and priority is not None else None,
            'overtimeProven': overtime_proven, 'overtimeSpreadProven': overtime_spread_proven,
            'lowerBound': lower_bound, 'priorityBound': priority_bound,
            'seconds': time.monotonic() - start,
            'info': {'stages': stages, 'done': done, 'majorQualityReady': bool(major_ready),
                     'continueRecommended': bool(keep_going),
                     'resume': {'stage': pending, 'idle': round(idle, 2), 'proven': proven} if keep_going else None,
                     'idleSeconds': limits, 'reason': reason,
                     'lastQualityImprovementSeconds': last_quality_improvement}}
