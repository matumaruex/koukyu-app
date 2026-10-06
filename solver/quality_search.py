"""候補が出た時刻で打ち切らず、条件・残業・配置を順に確認する。"""
import time
from ortools.sat.python import cp_model
from .allocation import metrics, quality_value


class Progress(cp_model.CpSolverSolutionCallback):
    def __init__(self, expression, start, incumbent=None):
        super().__init__()
        self.expression, self.start, self.best = expression, start, incumbent
        self.last_improvement = None

    def on_solution_callback(self):
        value = int(self.value(self.expression))
        if self.best is None or value < self.best:
            self.best = value
            self.last_improvement = time.monotonic() - self.start


def search(model, p, *, seconds, priority, objective, overtime, new_solver,
           extract, priority_of, initial_assignments=None):
    start = time.monotonic()
    candidate = initial_assignments
    actual_candidate = False
    stages = []
    solver = None
    status = cp_model.UNKNOWN
    priority_proven = priority is None
    priority_value = priority_of(candidate) if candidate is not None else None
    overtime_proven = False
    lower_bound = None
    last_quality_improvement = None

    def remaining():
        return max(0, seconds - (time.monotonic() - start))

    def rank(a):
        return priority_of(a), quality_value(p, a)

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

    def run(name, expression, budget, incumbent=None):
        nonlocal solver, status, candidate, actual_candidate
        model.minimize(expression)
        hints()
        solver = new_solver(max(0.000001, min(budget, remaining())))
        progress = Progress(expression, start, incumbent)
        status = solver.solve(model, progress)
        stages.append({'stage': name, 'seconds': round(solver.wall_time, 3),
                       'status': solver.status_name(status)})
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            found = extract(solver)
            if candidate is None or rank(found) <= rank(candidate):
                candidate = found
            actual_candidate = True
        return progress

    if priority is not None:
        run('conditions', priority, min(20, seconds / 3), priority_value)
        # 条件段階が未証明なら、配置改善へ進まず残り時間も条件確認に使う。
        if status in (cp_model.FEASIBLE, cp_model.UNKNOWN) and remaining() > 0.001:
            if candidate is not None:
                model.add(priority <= priority_of(candidate))
            run('conditions', priority, remaining(),
                priority_of(candidate) if candidate is not None else None)
        if status == cp_model.OPTIMAL:
            priority_proven = True
            priority_value = int(solver.value(priority))
            model.add(priority == priority_value)

    can_improve = priority_proven and status != cp_model.INFEASIBLE and candidate is not None
    if priority is None and candidate is None:
        can_improve = True
    if can_improve and (remaining() > 0.001 or solver is None):
        # 同じ条件の検査済み候補より悪くしない。
        if candidate is not None:
            model.add(objective <= quality_value(p, candidate))
            model.add(overtime <= metrics(p, candidate)['overtimeTotal'])
        run('overtime', overtime, min(20, remaining() / 2),
            metrics(p, candidate)['overtimeTotal'] if candidate is not None else None)
        if status in (cp_model.FEASIBLE, cp_model.UNKNOWN) and remaining() > 0.001:
            if candidate is not None:
                model.add(overtime <= metrics(p, candidate)['overtimeTotal'])
            run('overtime', overtime, remaining(),
                metrics(p, candidate)['overtimeTotal'] if candidate is not None else None)
        if status == cp_model.OPTIMAL:
            overtime_proven = True
            model.add(overtime == int(solver.value(overtime)))
            if remaining() > 0.001:
                model.add(objective <= quality_value(p, candidate))
                progress = run('placement', objective, remaining(), quality_value(p, candidate))
                last_quality_improvement = progress.last_improvement
                lower_bound = solver.best_objective_bound

    # 未証明で終わっても、採用した候補の条件値は検査に必要。
    if candidate is not None and not priority_proven:
        priority_value = priority_of(candidate)
    elapsed = time.monotonic() - start
    if candidate is not None and status != cp_model.INFEASIBLE:
        # 前の段階の最適性だけで、月全体の最適とは説明しない。
        all_proven = (priority_proven and overtime_proven and stages[-1]['stage'] == 'placement'
                      and status == cp_model.OPTIMAL)
        status = cp_model.OPTIMAL if all_proven else cp_model.FEASIBLE if actual_candidate else cp_model.UNKNOWN
    major_ready = False
    if candidate is not None:
        m = metrics(p, candidate)
        ot_count = len(m['overtimeByStaff'])
        ideal_ot_spread = int(ot_count > 0 and m['overtimeTotal'] % ot_count != 0)
        major_ready = (priority_proven and overtime_proven
                       and m['overtimeSpread'] == ideal_ot_spread and m['extraOffSpread'] == 0)
    recent = last_quality_improvement is not None and elapsed - last_quality_improvement <= 20
    # 暫く更新がないだけでは改善余地がないとは証明できない。
    # 未証明の段階があれば、画面側の合計上限まで自動で継続する。
    extend = status not in (cp_model.OPTIMAL, cp_model.INFEASIBLE)
    return {'solver': solver, 'status': status, 'candidate': candidate,
            'priorityProven': priority_proven, 'priorityValue': priority_value,
            'overtimeProven': overtime_proven, 'lowerBound': lower_bound,
            'seconds': elapsed,
            'info': {'stages': stages, 'majorQualityReady': bool(major_ready),
                     'continueRecommended': bool(extend),
                     'reason': 'conditions_unconfirmed' if not priority_proven else
                               'overtime_unconfirmed' if not overtime_proven else
                               'balance_unconfirmed' if not major_ready else
                               'recent_improvement' if recent else
                               'placement_unconfirmed' if extend else 'confirmed',
                     'lastQualityImprovementSeconds': last_quality_improvement}}
