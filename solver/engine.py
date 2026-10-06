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
from .validator import validate, is_rule_exception, exception_count, SHORTFALL_CODES
from .allocation import POLICY, covers, metrics, weights, quality_value, minor_unit
from .night_preferences import report as preference_report
from .quality_search import search as quality_search


class _FirstSolution(cp_model.CpSolverSolutionCallback):
    """最初の表が見つかった時刻だけを記録する。"""

    def __init__(self):
        super().__init__()
        self.first = None

    def on_solution_callback(self):
        if self.first is None:
            self.first = time.monotonic()


def _solve_with_stop_rule(solver, model, min_seconds, after_first, *, tracker=None, start=None):
    """min_seconds 経過し、かつ最初の表から after_first 秒たったら探索を止める。
    表が見つからない間は max_time_in_seconds まで探す。最適・不成立を証明できればその時点で終わる。"""
    # 複数段階でも、全体の開始時刻と最初の採用可能な表を引き継ぐ。
    tracker = tracker if tracker is not None else _FirstSolution()
    start = time.monotonic() if start is None else start
    done = threading.Event()
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


def _explain(model, dropped, night_missing, violations, violation_cap, seconds, seed):
    """作れないときだけ使う。夜勤を埋められない日 → 外す希望・固定の件数 → 中間ルールの例外、の順に最小化する。
    夜勤を埋められない日は、希望・固定をすべて外しても埋まらない日（職員の設定が原因）。"""
    keep_weight = violation_cap + 1
    night_weight = (len(dropped) + 1) * keep_weight
    model.minimize(sum(night_missing) * night_weight
                   + sum(1 - keep for keep, _ in dropped) * keep_weight
                   + (sum(violations) if violations else 0))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        return {'status': 'INFEASIBLE' if status == cp_model.INFEASIBLE else 'UNKNOWN', 'seconds': round(solver.wall_time, 3)}
    return {'status': 'EXPLAINED', 'proven': status == cp_model.OPTIMAL, 'seconds': round(solver.wall_time, 3),
            'missingNights': [d + 1 for d, v in enumerate(night_missing) if solver.value(v)],
            'droppedWishes': [item for keep, item in dropped if not solver.value(keep)]}


def solve(raw, seconds=15, seed=1, optimize=True, initial_assignments=None, min_seconds=None, after_first=None, allow_staffing_shortfall=False, allow_night_shortfall=False, quality_first=False, allow_rule_exceptions=False, resume=None, relax_wishes=False):
    """seconds は上限。min_seconds と after_first を両方指定すると、表が早く見つかった場合に上限より前に止める。
    allow_rule_exceptions：連勤上限・連勤＋1・日勤の種類（許可した人のみ）を、守ると表が作れないときだけ最小限破る中間ルールにする。
    resume：quality_first の続きの計算（段階と、最後に良くなってからの経過秒）。
    relax_wishes：作れないときの理由調べ専用。希望・固定・夜勤を外せる形で解き、外す件数が最小の組合せを返す。"""
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        return {'status': 'INVALID_INPUT', 'errors': ['seconds must be finite and positive']}
    if type(allow_staffing_shortfall) is not bool:
        return {'status': 'INVALID_INPUT', 'errors': ['allow_staffing_shortfall must be boolean.']}
    if type(quality_first) is not bool or (quality_first and not optimize):
        return {'status': 'INVALID_INPUT', 'errors': ['quality_first requires optimized calculation.']}
    if type(allow_night_shortfall) is not bool or (allow_night_shortfall and not allow_staffing_shortfall):
        return {'status': 'INVALID_INPUT', 'errors': ['夜勤未配置は人数不足の下書きでのみ指定できます。']}
    if type(allow_rule_exceptions) is not bool or (allow_rule_exceptions and not allow_staffing_shortfall):
        return {'status': 'INVALID_INPUT', 'errors': ['中間ルールの例外は人数不足を許す作成でのみ指定できます。']}
    if resume is not None and not quality_first:
        return {'status': 'INVALID_INPUT', 'errors': ['続きの計算は qualityFirst でのみ指定できます。']}
    try:
        p = normalize(raw)
    except (ValueError, TypeError) as exc:
        return {'status': 'INVALID_INPUT', 'errors': [str(exc)]}

    def rule_exception(e):
        return allow_rule_exceptions and is_rule_exception(p, e)

    def permitted_shortfall(e):
        return (e['code'] in SHORTFALL_CODES or rule_exception(e)
                or (allow_night_shortfall and e['code'] == 'night_coverage' and e.get('actual') == 0 and e.get('required') == 1))

    def exceptions_of(errors):
        return exception_count(p, errors) if allow_rule_exceptions else 0
    if (min_seconds is None) != (after_first is None):
        return {'status': 'INVALID_INPUT', 'errors': ['min_seconds and after_first must be given together']}
    if min_seconds is not None:
        for v in (min_seconds, after_first):
            if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
                return {'status': 'INVALID_INPUT', 'errors': ['min_seconds and after_first must be finite and non-negative']}
        if min_seconds > seconds:
            return {'status': 'INVALID_INPUT', 'errors': ['min_seconds must not exceed seconds']}
    if initial_assignments is not None:
        errors = validate(raw, initial_assignments)
        if errors and (not allow_staffing_shortfall or any(not permitted_shortfall(e) for e in errors)):
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

    # 中間ルールの違反（連勤上限を超えた日、＋1の超過、許可した人の逆の日勤）。
    rule_violations = []
    # 作れないときの理由調べ用：外せる形にした希望・固定。
    dropped = []
    night_soft = allow_night_shortfall or relax_wishes

    def wish(expr, key, label, item):
        if relax_wishes:
            keep = model.new_bool_var(f'keep_wish_{len(dropped)}')
            model.add(expr).only_enforce_if(keep)
            dropped.append((keep, item))
        else:
            required(expr, key, label)

    preference_misses = []
    quality = []
    extra_off = []
    compared_extra_off = []
    night_totals, ab_totals = [], []
    overtime_totals, overtime_squares = [], []
    for i, st in enumerate(p['staff']):
        sid = st['id']
        label = f'職員{i + 1}'
        nt = st['nightShiftType']
        limit = st['maxConsecutive'] or (2 if st['type'] != 'part' and nt != 'none' else 5)
        extensions = []
        overs = []
        flexible = (allow_rule_exceptions and st['type'] != 'part' and st['dayShiftFlexible']
                    and st['dayShiftType'] != 'both')
        for d in range(n):
            dt = p['start'] + timedelta(days=d)
            allowed = {'off', 'part'} if st['type'] == 'part' else {'off', 'early', 'late', 'nightOff'}
            if st['type'] != 'part':
                if st['dayShiftType'] == 'early':
                    allowed.remove('late')
                elif st['dayShiftType'] == 'late':
                    allowed.remove('early')
                if flexible:
                    # 逆の日勤は入れられるが、1日ごとに中間ルールの違反として数える。
                    opposite = 'late' if st['dayShiftType'] == 'early' else 'early'
                    allowed.add(opposite)
                    rule_violations.append(x[sid, d, opposite])
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
                wish(x[sid, d, 'off'] == 1, sid + '_requests', label + 'の希望休',
                     {'kind': 'request', 'staff': sid, 'day': d + 1, 'shift': 'off'})
                if sid in p['nightRestRequiredStaff'] and d not in p['requests'].get(sid, []):
                    # この逆向きの指定だけは優先希望。実際の夜勤→明け→公休は必須のまま。
                    missed = model.new_bool_var(f'{sid}_preferred_night_rest_{d}')
                    model.add(missed >= 1 - value(sid, d - 2, 'night'))
                    model.add(missed >= 1 - value(sid, d - 1, 'nightOff'))
                    model.add(missed <= 2 - value(sid, d - 2, 'night') - value(sid, d - 1, 'nightOff'))
                    preference_misses.append(missed)
            requested = p['shiftRequests'].get(sid, {}).get(d + 1)
            if requested is not None:
                shift_label = {'early': 'A（早出）', 'late': 'B（遅出）', 'overtime': 'A残', 'night': '夜勤', 'part': 'P'}[requested]
                wish(x[sid, d, requested] == 1, f'{sid}_shift_request_{d}',
                     label + f'の{dt}の希望勤務「{shift_label}」',
                     {'kind': 'shiftRequest', 'staff': sid, 'day': d + 1, 'shift': requested})
            locked = p['locked'].get(sid, {}).get(d + 1)
            if locked is not None:
                wish(x[sid, d, locked] == 1, sid + '_locked', label + 'の固定済み勤務',
                     {'kind': 'locked', 'staff': sid, 'day': d + 1, 'shift': locked})
            window = sum(working(sid, t) for t in range(d - limit, d + 1))
            if allow_rule_exceptions:
                # 中間ルール：上限を超えて働く日を1件として数える（明けで連勤は途切れる）。
                over = model.new_bool_var(f'{sid}_over_limit_{d}')
                model.add(window - limit <= over)
                overs.append(over)
            elif st['allowConsecutivePlus1']:
                extra = model.new_bool_var(f'{sid}_extension_{d}')
                model.add(window == limit + 1).only_enforce_if(extra)
                model.add(window <= limit).only_enforce_if(extra.Not())
                extensions.append(extra)
                required(sum(working(sid, t) for t in range(d - limit - 1, d + 1)) <= limit + 1, sid + '_consecutive', label + 'の連勤上限（+1は月1回）')
            else:
                required(window <= limit, sid + '_consecutive', label + 'の連勤上限')
        if extensions:
            required(sum(extensions) <= 1, sid + '_consecutive', label + 'の連勤上限（+1は月1回）')
        if overs:
            if st['allowConsecutivePlus1']:
                # ＋1を許可した人は、上限を1日超える分を月1回まで違反に数えない。
                used = model.new_bool_var(f'{sid}_plus_one_used')
                model.add(used <= sum(overs))
                rule_violations.append(sum(overs) - used)
            else:
                rule_violations.append(sum(overs))
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
            total_ot = model.new_int_var(0, min(6, n), sid + '_ot_total')
            model.add(total_ot == ot)
            square = model.new_int_var(0, min(6, n) ** 2, sid + '_ot_square')
            model.add_multiplication_equality(square, [total_ot, total_ot])
            overtime_totals.append(total_ot)
            overtime_squares.append(square)
        if st['type'] == 'part':
            mondays = {d - (p['start'] + timedelta(days=d)).weekday() for d in range(n)}
            for monday in sorted(mondays):
                required(sum(working(sid, d) for d in range(monday, min(n, monday + 7))) <= st['maxDaysPerWeek'], sid + '_weekly', label + f'の週{st["maxDaysPerWeek"]}日以内（月曜始まり）')
        else:
            if st['dayShiftType'] == 'both' and (optimize or allow_staffing_shortfall):
                a = model.new_int_var(0, n, sid + '_a_total')
                b = model.new_int_var(0, n, sid + '_b_total')
                model.add(a == sum(x[sid, d, 'early'] for d in range(n)))
                model.add(b == sum(x[sid, d, 'late'] for d in range(n)))
                ab_totals.append((sid, a, b))
            if nt != 'none':
                total = model.new_int_var(0, n, sid + '_night_total')
                model.add(total == sum(x[sid, d, 'night'] for d in range(n)))
                night_totals.append(total)

    night_spread = 0
    if night_totals:
        high, low = model.new_int_var(0, n, 'night_high'), model.new_int_var(0, n, 'night_low')
        model.add_max_equality(high, night_totals)
        model.add_min_equality(low, night_totals)
        night_spread = high - low
        quality.append((100 * len(p['staff']) + 1) * night_spread)

    if ab_totals:
        def percentage(a, b, maximum, name):
            days = model.new_int_var(0, maximum, name + '_days')
            denominator = model.new_int_var(1, max(1, maximum), name + '_denominator')
            percent = model.new_int_var(0, 100, name + '_percent')
            model.add(days == a + b)
            model.add_max_equality(denominator, [1, days])
            # 1%単位で四捨五入。A残・明け・公休は分母に含めない。
            model.add_division_equality(percent, 200 * a + days, 2 * denominator)
            return days, percent
        _, target = percentage(sum(a for _, a, _ in ab_totals),
                               sum(b for _, _, b in ab_totals), n * len(ab_totals), 'ab_pool')
        for sid, a, b in ab_totals:
            days, percent = percentage(a, b, n, sid + '_ab')
            active = model.new_bool_var(sid + '_ab_active')
            model.add(days >= 1).only_enforce_if(active)
            model.add(days == 0).only_enforce_if(active.Not())
            difference = model.new_int_var(0, 100, sid + '_ab_difference')
            model.add_abs_equality(difference, percent - target)
            deviation = model.new_int_var(0, 100, sid + '_ab_deviation')
            model.add(deviation == difference).only_enforce_if(active)
            model.add(deviation == 0).only_enforce_if(active.Not())
            quality.append(deviation)

    reduced = []
    shortfalls = []
    surpluses = []
    night_missing = []
    shortfall_cap = 0
    for d in range(n):
        dt = p['start'] + timedelta(days=d)
        night_count = sum(x[st['id'], d, 'night'] for st in p['staff'])
        if night_soft:
            missing_night = model.new_bool_var(f'missing_night_{d}')
            model.add(night_count + missing_night == 1)
            night_missing.append(missing_night)
            if allow_night_shortfall:
                shortfalls.append(missing_night)
                shortfall_cap += 1
        else:
            required(night_count == 1, f'night_{d}', f'{dt}の夜勤1人')
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
                shortfall_cap += need
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
    if relax_wishes:
        return _explain(model, dropped, night_missing, rule_violations, len(p['staff']) * 2 * n, seconds, seed)
    overtime_range = 0
    if overtime_totals:
        high_ot, low_ot = model.new_int_var(0, n, 'ot_high'), model.new_int_var(0, n, 'ot_low')
        model.add_max_equality(high_ot, overtime_totals)
        model.add_min_equality(low_ot, overtime_totals)
        overtime_range = high_ot - low_ot
    initial_metric = metrics(p, initial_assignments) if initial_assignments is not None else None
    initial_shortage = sum(e['required'] - e['actual'] for e in validate(raw, initial_assignments)
                           if e['code'] in ('coverage', 'night_coverage')) if initial_metric is not None else 0
    preserved_night_spread = None
    if initial_metric is not None and resume is None:
        # 全員に配れている追加公休を、残業削減のために取り上げない。
        # 続きの計算では、途中の表の追加公休はたまたまの値なので、ここでは固定しない。
        model.add(min_extra >= initial_metric['commonExtraDaysOff'])
    shortage_weight = weights(p)[1]
    initial_preferences = preference_report(p, initial_assignments) if initial_assignments is not None else None
    objective = None
    if optimize or allow_staffing_shortfall:
        minor = ((max_extra - min_extra) * minor_unit(p)
                 + sum(overtime_squares) + sum(quality))
        terms = (sum(overtime_totals), sum(surpluses), overtime_range, n - min_extra, minor)
        objective = sum(term * weight for term, weight in zip(terms, weights(p)[0]))
    # 第1段階は小さな整数だけで優先順を確定する。
    # 不足合計 → 未配置夜勤 → 希望休の夜勤後配置 → 夜勤回数の差。
    # 下位項の最大値より1大きい係数なので、上位の1件を下位で逆転できない。
    balance_nights = bool(night_totals and objective is not None)
    preference_weight = n + 1 if balance_nights else 1
    gap_weight = (len(preference_misses) + 1) * preference_weight
    shortage_priority_weight = (n + 1 if allow_night_shortfall else 1) * gap_weight
    night_gaps = sum(v for v in shortfalls if v.name.startswith('missing_night_'))
    priority = (sum(shortfalls) * shortage_priority_weight + night_gaps * gap_weight
                + sum(preference_misses) * preference_weight
                + (night_spread if balance_nights else 0))
    # 中間ルールの違反は人数不足より上。係数は下位全体の上限より大きく、
    # 希望休の件数を取り出す計算（gap_weight の倍数）を崩さない値にする。
    violation_weight = 0
    if rule_violations:
        lower_max = (shortfall_cap * shortage_priority_weight + n * gap_weight
                     + len(preference_misses) * preference_weight + n)
        violation_weight = (lower_max // gap_weight + 1) * gap_weight
        priority = sum(rule_violations) * violation_weight + priority
    has_priority = bool(preference_misses or shortfalls or balance_nights or rule_violations)
    initial_errors = validate(raw, initial_assignments) if initial_metric is not None else []
    initial_night_shortage = sum(e['required'] - e['actual'] for e in initial_errors
                                 if e['code'] == 'night_coverage') if initial_metric is not None else 0
    initial_priority = (exceptions_of(initial_errors) * violation_weight
                        + initial_shortage * shortage_priority_weight + initial_night_shortage * gap_weight
                        + len(initial_preferences['unmet']) * preference_weight
                        + (initial_metric['nightSpread'] if balance_nights else 0)) if initial_metric is not None else None

    def decode_bound(bound, assignments):
        """条件段階の下限から、例外と人数不足の理論上の最少を取り出す（例外が下限に達している場合のみ）。"""
        if bound is None or not math.isfinite(bound):
            return None, None
        b = int(math.floor(bound + 1e-6))
        errors = validate(raw, assignments)
        found_exceptions = exceptions_of(errors)
        exceptions_bound = b // violation_weight if violation_weight else 0
        if exceptions_bound != found_exceptions:
            return exceptions_bound, None
        return exceptions_bound, max(0, (b - found_exceptions * violation_weight) // shortage_priority_weight)
    if has_priority:
        model.minimize(priority)
        if initial_priority is not None:
            model.add(priority <= initial_priority)
    elif objective is not None:
        model.minimize(objective)
        if initial_assignments is not None:
            model.add(objective <= quality_value(p, initial_assignments) + initial_shortage * shortage_weight)
    if initial_assignments is not None:
        for (sid, d, shift), variable in x.items():
            model.add_hint(variable, int(initial_assignments[sid][str(d + 1)] == shift))
    def new_solver(limit):
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = limit
        solver.parameters.random_seed = seed
        solver.parameters.num_search_workers = 4 if allow_staffing_shortfall else 1
        return solver
    def extract(solver):
        return {st['id']: {str(d + 1): next(k for k in SHIFTS if solver.value(x[st['id'], d, k]))
                           for d in range(n)} for st in p['staff']}
    stop_rule = min_seconds is not None
    search_start, tracker = time.monotonic(), _FirstSolution()
    if stop_rule and initial_assignments is not None:
        # 検査済みの元の表も候補。新しい表が見つからなくても早く返せる。
        tracker.first = search_start
    stopped_early, first_seconds = False, None
    priority_proven, priority_value = False, None
    phase_seconds, phase_candidate, lower_bound = 0, None, None
    # 時間内に最少を証明できなければ、見つかった表の件数を維持して改善する。
    # 第2段階だけが最適でも全体の最適・希望件数の最少とは説明しない。
    solver = new_solver(seconds)
    quality_result = None
    if quality_first:
        def priority_of(a):
            errors = validate(raw, a)
            shortage = sum(e['required'] - e['actual'] for e in errors if e['code'] in ('coverage', 'night_coverage'))
            gaps = sum(e['required'] - e['actual'] for e in errors if e['code'] == 'night_coverage')
            return (exceptions_of(errors) * violation_weight
                    + shortage * shortage_priority_weight + gaps * gap_weight
                    + len(preference_report(p, a)['unmet']) * preference_weight
                    + (metrics(p, a)['nightSpread'] if balance_nights else 0))
        quality_result = quality_search(model, p, seconds=seconds, priority=priority if has_priority else None,
                                        objective=objective, overtime=sum(overtime_totals),
                                        overtime_spread=overtime_range if overtime_totals else None,
                                        new_solver=new_solver, extract=extract, priority_of=priority_of,
                                        initial_assignments=initial_assignments, resume=resume)
        solver, status = quality_result['solver'], quality_result['status']
        phase_candidate = quality_result['candidate']
        if status == cp_model.INFEASIBLE and phase_candidate is not None:
            return {'status': 'VALIDATION_FAILED', 'errors': ['配置改善の検査を完了できませんでした。確認済みの表は変更していません。']}
        priority_proven, priority_value = quality_result['priorityProven'], quality_result['priorityValue']
        lower_bound, elapsed = quality_result['lowerBound'], quality_result['seconds']
        if initial_priority is not None and phase_candidate is not None and priority_of(phase_candidate) == initial_priority:
            preserved_night_spread = initial_metric['nightSpread']
    elif has_priority:
        if objective is not None:
            # 表が出ない間は全上限まで探す。最初の表が出れば残り時間を配置改善へ回す。
            phase_min, phase_after = min(seconds / 3, 15), min(3, seconds / 4)
            if stop_rule:
                phase_min, phase_after = min(phase_min, min_seconds), min(phase_after, after_first)
                if initial_assignments is not None:
                    # この段階で候補が出なくても元の表を返す。全体の終了条件を守る。
                    phase_min, phase_after = min_seconds, after_first
            status, phase_stopped, first_seconds = _solve_with_stop_rule(
                solver, model, phase_min, phase_after, tracker=tracker, start=search_start)
        elif stop_rule:
            status, stopped_early, first_seconds = _solve_with_stop_rule(
                solver, model, min_seconds, after_first, tracker=tracker, start=search_start)
        else:
            status = solver.solve(model)
        phase_seconds = solver.wall_time
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            phase_candidate = extract(solver)
            priority_value = int(solver.value(priority))
            priority_proven = status == cp_model.OPTIMAL
            model.add(priority == priority_value)
            if objective is not None:
                model.minimize(objective)
                if initial_priority == priority_value:
                    model.add(objective <= quality_value(p, initial_assignments))
                    model.add(night_spread <= initial_metric['nightSpread'])
                    preserved_night_spread = initial_metric['nightSpread']
                    if metrics(p, phase_candidate)['nightSpread'] > preserved_night_spread:
                        phase_candidate = initial_assignments
                model.clear_hints()
                for (sid, d, shift), variable in x.items():
                    model.add_hint(variable, int(phase_candidate[sid][str(d + 1)] == shift))
                # 第2段階が時間切れなら、その段階の比較上限を守る表を返す。
                if (initial_priority == priority_value
                        and quality_value(p, phase_candidate) > quality_value(p, initial_assignments)):
                    phase_candidate = initial_assignments
                early_deadline = (max(search_start + min_seconds, tracker.first + after_first)
                                  if stop_rule and tracker.first is not None else None)
                if early_deadline is not None and time.monotonic() >= early_deadline:
                    # 第1段階の表を返す。配置の最適性までは証明していない。
                    status, stopped_early = cp_model.FEASIBLE, True
                    elapsed = phase_seconds
                else:
                    solver = new_solver(max(0.000001, seconds - (time.monotonic() - search_start)))
                    if stop_rule:
                        status, stopped_early, first_seconds = _solve_with_stop_rule(
                            solver, model, min_seconds, after_first, tracker=tracker, start=search_start)
                    else:
                        status = solver.solve(model)
                    lower_bound = solver.best_objective_bound
                    if status == cp_model.UNKNOWN:
                        status = cp_model.FEASIBLE
                    elif status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
                        phase_candidate = extract(solver)
                    else:
                        return {'status': 'VALIDATION_FAILED', 'errors': ['配置改善の計算を確認できませんでした。元の表は変更していません。']}
                    elapsed = phase_seconds + solver.wall_time
                if not priority_proven:
                    status = cp_model.FEASIBLE
            else:
                elapsed = phase_seconds
        else:
            elapsed = phase_seconds
            if stop_rule and objective is not None:
                stopped_early = phase_stopped
    else:
        if stop_rule:
            status, stopped_early, first_seconds = _solve_with_stop_rule(
                solver, model, min_seconds, after_first, tracker=tracker, start=search_start)
        else:
            status = solver.solve(model)
        elapsed = solver.wall_time
        lower_bound = solver.best_objective_bound
    result = {'status': solver.status_name(status), 'seconds': round(elapsed, 3), 'boundaryComplete': p['boundaryComplete'], 'optimized': optimize}
    reason = ('early_return' if stopped_early else 'optimal' if status == cp_model.OPTIMAL
              else 'infeasible' if status == cp_model.INFEASIBLE
              else 'time_limit' if elapsed >= seconds - 0.1 else 'completed')
    result['timing'] = {'mode': 'quality' if quality_first else 'adaptive' if stop_rule else 'full', 'maxSeconds': seconds, 'reason': reason}
    if quality_result is not None:
        result['search'] = quality_result['info']
    if stop_rule and not quality_first:
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
    assignments = initial_assignments if keep_previous else phase_candidate if phase_candidate is not None else extract(solver)
    preferences = preference_report(p, assignments)
    if has_priority and not keep_previous and len(preferences['unmet']) != (priority_value // preference_weight) % (len(preference_misses) + 1):
        return {'status': 'VALIDATION_FAILED', 'errors': ['希望休の確認結果が計算と一致しません。']}
    preferences['minimumUnmetProven'] = bool(not preferences['unmet'] or priority_proven)
    result['nightRestPreferences'] = preferences
    result['preferencePriorityProven'] = priority_proven
    errors = validate(raw, assignments)
    hard_errors = [e for e in errors if not permitted_shortfall(e)]
    if errors and (not allow_staffing_shortfall or hard_errors):
        return {'status': 'VALIDATION_FAILED', 'errors': errors, 'seconds': result['seconds']}
    exceptions = [e for e in errors if rule_exception(e)]
    if exceptions:
        # 中間ルールの例外は、守ると表が作れない分だけ。人数不足とは別に一覧で返す。
        result['ruleExceptions'] = exceptions
        result['exceptionCount'] = exception_count(p, exceptions)
        result['exceptionsProvenMinimum'] = bool(priority_proven)
    is_draft = any(not rule_exception(e) for e in errors)
    if is_draft:
        result['solverStatus'] = result['status']
        result['status'] = 'DRAFT'
        result['unmetConditions'] = errors
        result['staffingShortfallTotal'] = sum(e['required'] - e['actual'] for e in errors if e['code'] in ('coverage', 'night_coverage'))
        result['nightShortfallTotal'] = sum(e['required'] - e['actual'] for e in errors if e['code'] == 'night_coverage')
        result['daytimeShortfallTotal'] = result['staffingShortfallTotal'] - result['nightShortfallTotal']
        result['shortfallProvenMinimum'] = priority_proven if has_priority else status == cp_model.OPTIMAL
        result['explanation'] = '人数不足のある下書きです。希望休・希望勤務・勤務資格・実際の夜勤後公休は守っています。'
    if quality_result is not None and not keep_previous and (initial_assignments is None or resume is not None):
        # 「理論上あと何か所減る可能性があるか」の表示用。追加公休を固定した改善計算では出さない。
        exceptions_bound, shortfall_bound = decode_bound(quality_result.get('priorityBound'), assignments)
        if exceptions_bound is not None and allow_rule_exceptions:
            result['exceptionLowerBound'] = exceptions_bound
        if shortfall_bound is not None and is_draft:
            result['shortfallLowerBound'] = min(shortfall_bound, result['staffingShortfallTotal'])
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
    result['allocation']['minimumOvertimeProven'] = bool(quality_result['overtimeProven'] if quality_result is not None
                                                       else (optimize or allow_staffing_shortfall) and status == cp_model.OPTIMAL)
    ot_counts = result['allocation']['overtimeByStaff']
    ot_total = result['allocation']['overtimeTotal']
    ot_spread = result['allocation']['overtimeSpread']
    ideal_ot_spread = int(bool(ot_counts) and ot_total % len(ot_counts) != 0)
    spread_proven = bool(ot_spread == ideal_ot_spread or
                         (quality_result['overtimeSpreadProven'] if quality_result is not None
                          else (optimize or allow_staffing_shortfall) and status == cp_model.OPTIMAL))
    result['overtimeFairness'] = {
        'byStaff': ot_counts, 'total': ot_total, 'spread': ot_spread,
        'idealSpread': ideal_ot_spread, 'minimumSpreadProven': spread_proven,
        'scope': 'FIXED_STAFFING_NIGHT_REST_NIGHT_BALANCE_AND_OVERTIME_TOTAL',
        'reason': 'balanced' if ot_spread == ideal_ot_spread else 'constraints' if spread_proven else 'not_proven',
    }
    if has_priority:
        result['allocation']['minimumOvertimeScope'] = 'WITH_FIXED_STAFFING_NIGHT_REST_AND_NIGHT_BALANCE'
    result['allocation']['preservedCommonExtraDaysOff'] = initial_metric['commonExtraDaysOff'] if initial_metric is not None else None
    if not preference_misses and result.get('staffingShortfallTotal', 0) < initial_shortage:
        preserved_night_spread = None
    result['allocation']['preservedNightSpread'] = preserved_night_spread
    night_counts = {st['id']: sum(v == 'night' for v in assignments[st['id']].values())
                    for st in p['staff'] if st['type'] != 'part' and st['nightShiftType'] != 'none'}
    if night_counts:
        filled = sum(night_counts.values())
        ideal_spread = int(filled % len(night_counts) != 0)
        spread = max(night_counts.values()) - min(night_counts.values())
        proven = balance_nights and (priority_proven or spread == ideal_spread)
        result['nightFairness'] = {'byStaff': night_counts, 'spread': spread,
                                  'idealSpread': ideal_spread, 'filledNights': filled,
                                  'minimumSpreadProven': bool(proven),
                                  'priorityProven': priority_proven,
                                  'scope': 'FIXED_STAFFING_AND_NIGHT_REST_PRIORITY',
                                  'reason': 'balanced' if spread == ideal_spread else
                                            'constraints' if proven else 'not_proven'}
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
        if not keep_previous and lower_bound is not None:
            result['bestBound'] = lower_bound
            if has_priority:
                result['bestBoundScope'] = 'FIXED_STAFFING_AND_NIGHT_BALANCE_PRIORITY'
        if initial_assignments is not None:
            old_quality = quality_value(p, initial_assignments) + initial_shortage * shortage_weight
            new_priority = (result.get('exceptionCount', 0) * violation_weight
                            + result.get('staffingShortfallTotal', 0) * shortage_priority_weight
                            + result.get('nightShortfallTotal', 0) * gap_weight
                            + len(preferences['unmet']) * preference_weight
                            + (result['allocation']['nightSpread'] if balance_nights else 0))
            result['improved'] = (initial_priority, old_quality) > (new_priority, result['objective'])
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
