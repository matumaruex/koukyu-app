"""期間全体を同時に解く CP-SAT 試作。違反のある表は返さない。"""
import argparse
import json
import math
import threading
import time
from datetime import timedelta
from pathlib import Path
from ortools.sat.python import cp_model
from .input_data import normalize, SHIFTS
from .validator import validate
from .allocation import POLICY, covers, metrics, weights, quality_value


class _FirstSolution(cp_model.CpSolverSolutionCallback):
    """最初の表が見つかった時刻だけを記録する。"""

    def __init__(self):
        super().__init__()
        self.first = None

    def on_solution_callback(self):
        if self.first is None:
            self.first = time.monotonic()


def _solve_with_stop_rule(solver, model, min_seconds, after_first):
    """min_seconds 経過し、かつ最初の表から after_first 秒たったら探索を止める。
    表が見つからない間は max_time_in_seconds まで探す。最適・不成立を証明できればその時点で終わる。"""
    tracker, done, start = _FirstSolution(), threading.Event(), time.monotonic()
    stopped = []

    def watch():
        while not done.wait(0.1):
            now = time.monotonic()
            if tracker.first is not None and now - start >= min_seconds and now - tracker.first >= after_first:
                stopped.append(True)
                solver.stop_search()
                return

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    try:
        status = solver.solve(model, tracker)
    finally:
        done.set()
        thread.join()
    first = None if tracker.first is None else round(tracker.first - start, 3)
    return status, bool(stopped), first


def solve(raw, seconds=15, seed=1, optimize=True, initial_assignments=None, min_seconds=None, after_first=None, allow_staffing_shortfall=False):
    """seconds は上限。min_seconds と after_first を両方指定すると、表が早く見つかった場合に上限より前に止める。"""
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        return {'status': 'INVALID_INPUT', 'errors': ['seconds must be finite and positive']}
    if type(allow_staffing_shortfall) is not bool:
        return {'status': 'INVALID_INPUT', 'errors': ['allow_staffing_shortfall must be boolean.']}
    if (min_seconds is None) != (after_first is None):
        return {'status': 'INVALID_INPUT', 'errors': ['min_seconds and after_first must be given together']}
    if min_seconds is not None:
        for v in (min_seconds, after_first):
            if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
                return {'status': 'INVALID_INPUT', 'errors': ['min_seconds and after_first must be finite and non-negative']}
        if min_seconds > seconds:
            return {'status': 'INVALID_INPUT', 'errors': ['min_seconds must not exceed seconds']}
    try:
        p = normalize(raw)
    except (ValueError, TypeError) as exc:
        return {'status': 'INVALID_INPUT', 'errors': [str(exc)]}
    if initial_assignments is not None:
        errors = validate(raw, initial_assignments)
        if errors and (not allow_staffing_shortfall or any(e['code'] not in ('coverage', 'sunday_limit') for e in errors)):
            return {'status': 'INVALID_INPUT', 'errors': ['比較する元の表が現在の条件に合いません。'], 'validationErrors': errors}
        initial_assignments = {sid: {str(d): k for d, k in row.items()} for sid, row in initial_assignments.items()}
    model = cp_model.CpModel()
    n = p['days']
    x = {}
    assumptions = {}
    groups = {}

    def guard(key, label):
        if key not in groups:
            bit = model.new_bool_var(key)
            if allow_staffing_shortfall:
                # 下書きでも必須条件をすべて有効に固定する。
                # 原因集合の抽出用の仮定を外し、複数の探索を使えるようにする。
                model.add(bit == 1)
            else:
                model.add_assumption(bit)
            assumptions[bit.index] = label
            groups[key] = bit
        return groups[key]

    def required(expr, key, label):
        model.add(expr).only_enforce_if(guard(key, label))

    for st in p['staff']:
        sid = st['id']
        for d in range(n):
            for shift in SHIFTS:
                x[sid, d, shift] = model.new_bool_var(f'{sid}_{d}_{shift}')
            model.add(sum(x[sid, d, k] for k in SHIFTS) == 1)

    def value(sid, d, shift):
        return x[sid, d, shift] if d >= 0 else int(p['history'][sid][d + 7] == shift)

    def working(sid, d):
        return 1 - value(sid, d, 'off') - value(sid, d, 'nightOff')

    quality = []
    extra_off = []
    compared_extra_off = []
    night_totals = []
    overtime_totals, overtime_squares = [], []
    for i, st in enumerate(p['staff']):
        sid = st['id']
        label = f'職員{i + 1}'
        nt = st['nightShiftType']
        limit = st['maxConsecutive'] or (2 if st['type'] != 'part' and nt != 'none' else 5)
        extensions = []
        for d in range(n):
            dt = p['start'] + timedelta(days=d)
            allowed = {'off', 'part'} if st['type'] == 'part' else {'off', 'early', 'late', 'nightOff'}
            if st['type'] != 'part':
                if st['dayShiftType'] == 'early':
                    allowed.remove('late')
                elif st['dayShiftType'] == 'late':
                    allowed.remove('early')
                if st['canOvertime']:
                    allowed.add('overtime')
                if nt == 'all' or (nt == 'weekday' and dt.weekday() < 4):
                    allowed.add('night')
            for k in sorted(set(SHIFTS) - allowed):
                required(x[sid, d, k] == 0, sid + '_eligibility', label + 'の勤務可能時間・A/Bの可否・夜勤資格')
            required(x[sid, d, 'nightOff'] == value(sid, d - 1, 'night'), sid + '_night_link', label + 'の夜勤翌日は明け（期間境界を含む）')
            required(x[sid, d, 'off'] >= value(sid, d - 1, 'nightOff'), sid + '_night_rest', label + 'の夜勤明け翌日は必ず公休（期間境界を含む）')
            required(x[sid, d, 'overtime'] + value(sid, d - 1, 'overtime') <= 1, sid + '_ot', label + 'のA残は月6回以内・連日不可')
            if d + 1 in p['requests'].get(sid, []):
                required(x[sid, d, 'off'] == 1, sid + '_requests', label + 'の希望休')
                if sid in p['nightRestRequiredStaff'] and d not in p['requests'].get(sid, []):
                    # 連続する希望休の先頭のみ。期間冒頭は前期の実績に接続する。
                    key = f'{sid}_requested_night_rest_{d}'
                    description = label + f'の{dt}の希望休は夜勤→明け→公休（連休は初日）'
                    required(value(sid, d - 2, 'night') == 1, key, description)
                    required(value(sid, d - 1, 'nightOff') == 1, key, description)
            requested = p['shiftRequests'].get(sid, {}).get(d + 1)
            if requested is not None:
                shift_label = {'early': 'A（早出）', 'late': 'B（遅出）', 'overtime': 'A残', 'night': '夜勤', 'part': 'P'}[requested]
                required(x[sid, d, requested] == 1, f'{sid}_shift_request_{d}',
                         label + f'の{dt}の希望勤務「{shift_label}」')
            locked = p['locked'].get(sid, {}).get(d + 1)
            if locked is not None:
                required(x[sid, d, locked] == 1, sid + '_locked', label + 'の固定済み勤務')
            window = sum(working(sid, t) for t in range(d - limit, d + 1))
            if st['allowConsecutivePlus1']:
                extra = model.new_bool_var(f'{sid}_extension_{d}')
                model.add(window == limit + 1).only_enforce_if(extra)
                model.add(window <= limit).only_enforce_if(extra.Not())
                extensions.append(extra)
                required(sum(working(sid, t) for t in range(d - limit - 1, d + 1)) <= limit + 1, sid + '_consecutive', label + 'の連勤上限（+1は月1回）')
            else:
                required(window <= limit, sid + '_consecutive', label + 'の連勤上限')
        if extensions:
            required(sum(extensions) <= 1, sid + '_consecutive', label + 'の連勤上限（+1は月1回）')
        off = sum(x[sid, d, 'off'] for d in range(n))
        required(off >= st['monthlyDaysOff'], sid + '_off', label + f'の公休{st["monthlyDaysOff"]}日以上')
        ot = sum(x[sid, d, 'overtime'] for d in range(n))
        required(ot <= 6, sid + '_ot', label + 'のA残は月6回以内・連日不可')
        extra = model.new_int_var(-n, n, sid + '_extra_off')
        model.add(extra == off - st['monthlyDaysOff'])
        extra_off.append(extra)
        if sid not in p['fairnessExcludedStaff']:
            compared_extra_off.append(extra)
        if st['type'] != 'part' and st['canOvertime']:
            total_ot = model.new_int_var(0, n, sid + '_ot_total')
            model.add(total_ot == ot)
            square = model.new_int_var(0, n * n, sid + '_ot_square')
            model.add_multiplication_equality(square, [total_ot, total_ot])
            overtime_totals.append(total_ot)
            overtime_squares.append(square)
        if st['type'] == 'part':
            mondays = {d - (p['start'] + timedelta(days=d)).weekday() for d in range(n)}
            for monday in sorted(mondays):
                required(sum(working(sid, d) for d in range(monday, min(n, monday + 7))) <= st['maxDaysPerWeek'], sid + '_weekly', label + f'の週{st["maxDaysPerWeek"]}日以内（月曜始まり）')
        else:
            if st['dayShiftType'] == 'both':
                diff = model.new_int_var(0, n, sid + '_ab_difference')
                model.add_abs_equality(diff, sum(x[sid, d, 'early'] - x[sid, d, 'late'] for d in range(n)))
                quality.append(2 * diff)
            if nt != 'none':
                total = model.new_int_var(0, n, sid + '_night_total')
                model.add(total == sum(x[sid, d, 'night'] for d in range(n)))
                night_totals.append(total)

    if night_totals:
        high, low = model.new_int_var(0, n, 'night_high'), model.new_int_var(0, n, 'night_low')
        model.add_max_equality(high, night_totals)
        model.add_min_equality(low, night_totals)
        quality.append(5 * (high - low))

    reduced = []
    shortfalls = []
    surpluses = []
    for d in range(n):
        dt = p['start'] + timedelta(days=d)
        required(sum(x[st['id'], d, 'night'] for st in p['staff']) == 1, f'night_{d}', f'{dt}の夜勤1人')
        counts_required = p['dailyRequiredStaff'].get(d + 1, p['requiredStaff'])
        can_reduce = dt.weekday() == 6 and d + 1 not in p['dailyRequiredStaff'] and p['maxReducedSundays'] > 0
        relax = model.new_bool_var(f'reduced_{d}') if can_reduce else 0
        if can_reduce:
            reduced.append(relax)
        for j, t in enumerate((420, 600, 1065)):
            count = sum(x[st['id'], d, k] for st in p['staff'] for k in SHIFTS if covers(st, k, t))
            need = counts_required[j]
            target = need - (relax if j < 2 and need > 0 else 0)
            surplus = model.new_int_var(0, len(p['staff']), f'surplus_{d}_{t}')
            model.add_max_equality(surplus, [0, count - need])
            surpluses.append(surplus)
            if allow_staffing_shortfall:
                missing = model.new_int_var(0, need, f'shortfall_{d}_{t}')
                model.add(count + missing >= target)
                shortfalls.append(missing)
            else:
                required(count >= target, f'coverage_{d}_{t}', f'{dt} {t // 60:02}:{t % 60:02}の必要人数{need}人')
    required(sum(reduced) <= p['maxReducedSundays'], 'sundays', f'日曜の朝昼を1人減らせる日は月{p["maxReducedSundays"]}日以内')
    max_extra = model.new_int_var(-n, n, 'max_extra_off')
    min_extra = model.new_int_var(-n, n, 'min_extra_off')
    if compared_extra_off:
        model.add_max_equality(max_extra, compared_extra_off)
        model.add_min_equality(min_extra, compared_extra_off)
    else:
        model.add(max_extra == 0)
        model.add(min_extra == 0)
    required(max_extra - min_extra <= p['maxExtraOffSpread'], 'fairness', f'余分な公休の差は{p["maxExtraOffSpread"]}日以内')
    overtime_range = 0
    if overtime_totals:
        high_ot, low_ot = model.new_int_var(0, n, 'ot_high'), model.new_int_var(0, n, 'ot_low')
        model.add_max_equality(high_ot, overtime_totals)
        model.add_min_equality(low_ot, overtime_totals)
        overtime_range = high_ot - low_ot
    initial_metric = metrics(p, initial_assignments) if initial_assignments is not None else None
    if initial_metric is not None:
        # 全員に配れている追加公休を、残業削減のために取り上げない。
        model.add(min_extra >= initial_metric['commonExtraDaysOff'])
    shortage_weight = weights(p)[1]
    initial_shortage = sum(e['required'] - e['actual'] for e in validate(raw, initial_assignments)
                           if e['code'] == 'coverage') if initial_metric is not None else 0
    if optimize or allow_staffing_shortfall:
        # 月全体：不足 → 残業総数 → 人数超過 → 残業の偏り → 全員の追加公休 → その他のバランス。
        # 公休差の設定は必須のまま。部分的な追加公休やA/B合わせのために残業を増やさない。
        minor = ((max_extra - min_extra) * (36 * len(p['staff']) + 2 * len(p['staff']) * n + 5 * n + 1)
                 + sum(overtime_squares) + sum(quality))
        terms = (sum(overtime_totals), sum(surpluses), overtime_range, n - min_extra, minor)
        objective = sum(term * weight for term, weight in zip(terms, weights(p)[0]))
        if allow_staffing_shortfall:
            objective += sum(shortfalls) * shortage_weight
        model.minimize(objective)
        if initial_assignments is not None:
            model.add(objective <= quality_value(p, initial_assignments) + initial_shortage * shortage_weight)
    if initial_assignments is not None:
        for (sid, d, shift), variable in x.items():
            model.add_hint(variable, int(initial_assignments[sid][str(d + 1)] == shift))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.random_seed = seed
    # 通常作成は原因診断・再現性を優先。下書きは複数の探索で不足を減らす。
    solver.parameters.num_search_workers = 4 if allow_staffing_shortfall else 1
    stop_rule = min_seconds is not None
    if stop_rule:
        status, stopped_early, first_seconds = _solve_with_stop_rule(solver, model, min_seconds, after_first)
    else:
        status = solver.solve(model)
    result = {'status': solver.status_name(status), 'seconds': round(solver.wall_time, 3), 'boundaryComplete': p['boundaryComplete'], 'optimized': optimize}
    if stop_rule:
        result['stopRule'] = {'minSeconds': min_seconds, 'afterFirst': after_first, 'stoppedEarly': stopped_early, 'firstSolutionSeconds': first_seconds}
    keep_previous = status == cp_model.UNKNOWN and initial_assignments is not None
    if keep_previous:
        result.update(status='FEASIBLE', previousKept=True, explanation='改善を時間内に確認できなかったため、検査済みの元の表を保持しました。')
    if status == cp_model.INFEASIBLE:
        result['conflictGroups'] = [assumptions[i] for i in solver.sufficient_assumptions_for_infeasibility() if i in assumptions]
        result['explanation'] = '列挙した条件群は同時に成立しません。最小の原因集合とは限りません。'
        return result
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL) and not keep_previous:
        result['explanation'] = '時間内に成立する表を確認できませんでした。不可能と判定したわけではありません。'
        return result
    assignments = initial_assignments if keep_previous else {st['id']: {str(d + 1): next(k for k in SHIFTS if solver.value(x[st['id'], d, k])) for d in range(n)} for st in p['staff']}
    errors = validate(raw, assignments)
    hard_errors = [e for e in errors if e['code'] not in ('coverage', 'sunday_limit')]
    if errors and (not allow_staffing_shortfall or hard_errors):
        return {'status': 'VALIDATION_FAILED', 'errors': errors, 'seconds': result['seconds']}
    is_draft = bool(errors)
    if is_draft:
        result['solverStatus'] = result['status']
        result['status'] = 'DRAFT'
        result['unmetConditions'] = errors
        result['staffingShortfallTotal'] = sum(e['required'] - e['actual'] for e in errors if e['code'] == 'coverage')
        result['shortfallProvenMinimum'] = status == cp_model.OPTIMAL
        result['explanation'] = '朝昼夕の人数が不足する下書きです。希望休・連勤・夜勤後公休など他の登録条件は守っています。'
    result['assignments'] = assignments
    result['validationErrors'] = errors
    result['verificationScope'] = ('DRAFT_' if is_draft else '') + ('WITH_HISTORY' if p['boundaryComplete'] else 'PERIOD_ONLY')
    extras = {st['id']: sum(k == 'off' for k in assignments[st['id']].values()) - st['monthlyDaysOff'] for st in p['staff']}
    compared = [sid for sid in extras if sid not in p['fairnessExcludedStaff']]
    compared_values = [extras[sid] for sid in compared]
    spread = max(compared_values) - min(compared_values) if compared_values else 0
    result['fairness'] = {'extraDaysOff': extras, 'comparedStaff': compared, 'excludedStaff': p['fairnessExcludedStaff'], 'spread': spread, 'limit': p['maxExtraOffSpread'], 'spreadProvenOptimal': spread == 0, 'provenOptimal': optimize and status == cp_model.OPTIMAL}
    result['optimizationPolicy'] = POLICY
    result['allocation'] = metrics(p, assignments)
    result['allocation']['minimumOvertimeProven'] = bool((optimize or allow_staffing_shortfall) and status == cp_model.OPTIMAL)
    result['allocation']['preservedCommonExtraDaysOff'] = initial_metric['commonExtraDaysOff'] if initial_metric is not None else None
    if initial_metric is not None:
        result['allocation']['before'] = initial_metric
        result['allocation']['overtimeReducedBy'] = initial_metric['overtimeTotal'] - result['allocation']['overtimeTotal']
    result['carryForward'] = {}
    for sid, row in assignments.items():
        next_days = ['nightOff', 'off'] if row[str(n)] == 'night' else ['off'] if row[str(n)] == 'nightOff' else []
        result['carryForward'][sid] = {
            'history': [row[str(d)] for d in range(n - 6, n + 1)],
            'nextDay': next_days[0] if next_days else None,
            'nextDays': next_days,
        }
    if optimize or allow_staffing_shortfall:
        result['objective'] = quality_value(p, assignments) + result.get('staffingShortfallTotal', 0) * shortage_weight
        if not keep_previous:
            result['bestBound'] = solver.best_objective_bound
        if initial_assignments is not None:
            result['improved'] = result['objective'] < quality_value(p, initial_assignments) + initial_shortage * shortage_weight
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--feasibility-only', action='store_true')
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = solve(raw, args.seconds, optimize=not args.feasibility_only)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(result['status'], result.get('seconds'), result.get('verificationScope', ''))


if __name__ == '__main__':
    main()
