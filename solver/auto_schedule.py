"""60秒ずつ実行する公休おまかせ。送られた評価値や証明は採用せず表を再検査する。"""
from copy import deepcopy
import time
from ortools.sat.python import cp_model
from .allocation import metrics, minor_unit
from .capacity_bounds import shortage_bounds, overtime_bound
from .holiday_policy import POLICY, checked_policy, checked_quotas, effective_input, target_input
from .input_data import normalize, overtime_profile, SHIFTS
from .night_preferences import report
from .validator import validate, is_rule_exception, exception_count
from .rest_blocks import report as rest_report
from .overtime_preference import without_preferences


def inspect(raw, rows):
    raw = without_preferences(raw)
    p = normalize(raw)
    errors = validate(raw, rows)
    if any(e['code'] not in ('coverage', 'sunday_limit') and not is_rule_exception(p, e) for e in errors):
        raise ValueError('候補の表が現在の条件に合いません。')
    m = metrics(p, rows)
    shortage = sum(e['required'] - e['actual'] for e in errors if e['code'] == 'coverage')
    exceptions = exception_count(p, errors)
    pref = report(p, rows)
    bounds = shortage_bounds(raw)
    lower = overtime_bound(raw, shortage, bounds=bounds)
    ot_proven = m['overtimeTotal'] == lower
    profiles = {st['id']: overtime_profile(p, st) for st in p['staff'] if st['id'] in m['overtimeByStaff']}
    arithmetic = not m['overtimeProportional'] and m['overtimeBalance'] == m['overtimeIdealBalance']
    m.update(minimumOvertimeProven=ot_proven, minimumOvertimeScope='WITH_FIXED_STAFFING_NIGHT_REST_AND_NIGHT_BALANCE')
    extras = {st['id']: list(rows[st['id']].values()).count('off') - st['monthlyDaysOff'] for st in p['staff']}
    result = {'status': 'DRAFT' if shortage else 'FEASIBLE', 'solverStatus': 'FEASIBLE',
              'assignments': deepcopy(rows), 'validationErrors': errors, 'allocation': m,
              'exceptionCount': exceptions, 'ruleExceptions': [e for e in errors if is_rule_exception(p, e)],
              'exceptionsProvenMinimum': exceptions == 0, 'staffingShortfallTotal': shortage,
              'nightShortfallTotal': 0, 'shortfallLowerBound': bounds['total'],
              'shortfallProvenMinimum': shortage == bounds['total'],
              'boundaryComplete': p['boundaryComplete'], 'optimizationPolicy': POLICY,
              'nightRestPreferences': pref, 'preferencePriorityProven': not pref['unmet'],
              'fairness': {'extraDaysOff': extras, 'spread': m['extraOffSpread'], 'limit': p['maxExtraOffSpread'],
                           'comparedStaff': [sid for sid in extras if sid not in p['fairnessExcludedStaff']],
                           'excludedStaff': p['fairnessExcludedStaff']},
              'overtimeFairness': {'byStaff': m['overtimeByStaff'], 'total': m['overtimeTotal'],
                                  'spread': m['overtimeSpread'], 'balance': m['overtimeBalance'],
                                  'idealSpread': None if m['overtimeProportional'] else m['overtimeIdealBalance'],
                                  'minimumSpreadProven': arithmetic,
                                  'reason': 'balanced' if arithmetic else 'not_proven',
                                  'scope': 'FIXED_STAFFING_NIGHT_REST_NIGHT_BALANCE_AND_OVERTIME_TOTAL',
                                  'proportionalStaff': {sid: {'availableDays': v['available'], 'normalDays': v['normal'], 'cap': v['cap']}
                                                        for sid, v in profiles.items() if v['proportional']}}}
    if shortage:
        result['unmetConditions'] = errors
    if any(st['minConsecutiveRest'] for st in p['staff']):
        result['consecutiveRest'] = rest_report(p, rows)
    nights = {st['id']: list(rows[st['id']].values()).count('night') for st in p['staff']
              if st['type'] != 'part' and st['nightShiftType'] != 'none'}
    if nights:
        ideal = int(sum(nights.values()) % len(nights) != 0)
        result['nightFairness'] = {'byStaff': nights, 'spread': m['nightSpread'], 'idealSpread': ideal,
                                  'minimumSpreadProven': m['nightSpread'] == ideal, 'filledNights': sum(nights.values()),
                                  'reason': 'balanced' if m['nightSpread'] == ideal else 'not_proven'}
    return result


def rank(result):
    m = result['allocation']
    unit = 1 if m['overtimeProportional'] else 100
    return (result.get('exceptionCount', 0), result.get('staffingShortfallTotal', 0),
            len(result['nightRestPreferences']['unmet']), m['nightSpread'], m['overtimeTotal'],
            m['overtimeBalance'] * unit, m['surplusTotal'], -m['commonExtraDaysOff'], m['minor'])


def refinement_balance_limits(p, maximum, baseline_balance):
    """合計を減らしても算術上の公平さを保つ上限。0差を固定して合計削減を妨げない。"""
    profiles = [overtime_profile(p, st) for st in p['staff'] if st['type'] != 'part' and st['canOvertime']]
    if not profiles:
        return [(0, baseline_balance)]
    scales = [min(600, (200 * v['normal'] + v['available']) // (2 * v['available']))
              if v['proportional'] and v['available'] else 100 for v in profiles]
    if all(s == 100 for s in scales) and min(v['cap'] for v in profiles) >= (maximum + len(profiles) - 1) // len(profiles):
        return [(total, max(baseline_balance, 100 * int(total % len(profiles) != 0))) for total in range(maximum + 1)]
    caps = [v['cap'] for v in profiles]
    values = sorted({count * scale for cap, scale in zip(caps, scales) for count in range(cap + 1)})
    ideals = [values[-1]] * (maximum + 1)
    for low in values:
        lower = [(low + scale - 1) // scale for scale in scales]
        if any(a > cap for a, cap in zip(lower, caps)) or sum(lower) > maximum:
            continue
        for high in values:
            if high < low:
                continue
            upper = [min(cap, high // scale) for cap, scale in zip(caps, scales)]
            if any(a > b for a, b in zip(lower, upper)):
                continue
            # 各人の許される回数は連続整数なので、合計もこの範囲内の全整数を取れる。
            for total in range(sum(lower), min(maximum, sum(upper)) + 1):
                ideals[total] = min(ideals[total], high - low)
    return [(total, max(baseline_balance, ideal)) for total, ideal in enumerate(ideals)]


def decision_bounds(raw, policy, result):
    bounds = shortage_bounds(raw)
    lower = overtime_bound(raw, result.get('staffingShortfallTotal', 0), bounds=bounds)
    target = {sid: q['target'] for sid, q in policy.items()}
    groups = {}
    p = normalize(raw)
    for st in p['staff']:
        q = policy[st['id']]
        if not q['fixed'] and q['target'] < q['max']:
            groups.setdefault((st['type'], q['min'], q['target'], q['max']), []).append(st['id'])
    # 共通日数の組を1日増やすだけで残業増が必要なら、それ以上の増加も採用条件に合わない。
    rejected = []
    for members in groups.values():
        quotas = dict(target)
        for sid in members:
            quotas[sid] += 1
        rejected.append(overtime_bound(effective_input(raw, quotas), result.get('staffingShortfallTotal', 0), bounds=bounds)
                        > result['allocation']['overtimeTotal'])
    no_lower = result.get('exceptionCount', 0) == 0 and result.get('staffingShortfallTotal', 0) == bounds['total']
    return {'shortage': bounds['total'], 'overtime': lower, 'holidayChangeRuledOut': no_lower and all(rejected)}


class HolidayPlan:
    def __init__(self, raw, policy, deadline, reference, *, candidate=None, candidate_quotas=None):
        self.original, self.policy = without_preferences(raw), policy
        self.deadline, self.reference = deadline, reference
        self.candidate_rows, self.candidate_quotas = candidate, candidate_quotas
        self.minimums, self.caps, self.scales, self.groups = {}, {}, {}, {}
        self.trace = []

    def prepare(self):
        return effective_input(self.original, {sid: q['min'] for sid, q in self.policy.items()})

    def bind(self, model, p):
        self.model, self.p = model, p
        self.balance_bound = 0
        for st in p['staff']:
            sid, q = st['id'], self.policy[st['id']]
            key = (st['type'], q['min'], q['target'], q['max'], q['fixed'])
            if key not in self.groups:
                self.groups[key] = model.new_int_var(q['min'], q['max'], f'auto_quota_{len(self.groups)}')
            var = self.minimums[sid] = self.groups[key]
            table = []
            for count in range(q['min'], q['max'] + 1):
                v = overtime_profile(p, dict(st, monthlyDaysOff=count))
                scale = min(600, (200 * v['normal'] + v['available']) // (2 * v['available'])) if v['proportional'] and v['available'] else 100
                table.append((count, v['cap'], scale))
            self.caps[sid] = model.new_int_var(min(t[1] for t in table), max(t[1] for t in table), sid + '_auto_ot_cap')
            self.scales[sid] = model.new_int_var(min(t[2] for t in table), max(t[2] for t in table), sid + '_auto_ot_scale')
            model.add_allowed_assignments([var, self.caps[sid], self.scales[sid]], table)
            if st['type'] != 'part' and st['canOvertime']:
                self.balance_bound = max(self.balance_bound, *(cap * scale for _, cap, scale in table))
        return self

    def minimum(self, sid):
        return self.minimums[sid]

    def cap(self, sid):
        return self.caps[sid]

    def scale(self, sid):
        return self.scales[sid]

    def run(self, model, p, new_solver, extract, **expressions):
        variables = [model.get_int_var_from_proto_index(i) for i in range(len(model.proto.variables))]
        names = {v.name: v for v in variables}
        targets = {sid: q['target'] for sid, q in self.policy.items()}
        target = target_input(self.original, self.policy)
        reference = inspect(target, self.reference) if self.reference is not None else None
        bounds = shortage_bounds(target)
        upper = expressions['exceptions'] * (120 * p['days'] + 1) + expressions['shortage']
        baseline_upper = (reference['exceptionCount'] * (120 * p['days'] + 1) + reference['staffingShortfallTotal']) if reference else None
        hints = None
        def add_hints(rows, quotas):
            model.clear_hints()
            for st in p['staff']:
                sid = st['id']
                for d in range(p['days']):
                    for k in SHIFTS:
                        model.add_hint(names[f'{sid}_{d}_{k}'], int(rows[sid][str(d + 1)] == k))
            for key, var in self.groups.items():
                sid = next(s['id'] for s in p['staff'] if self.minimums[s['id']].index == var.index)
                model.add_hint(var, quotas[sid])

        def remaining():
            return max(.000001, self.deadline - time.monotonic())

        def fixed_target():
            copied = model.clone()
            for sid, var in self.minimums.items():
                copied.add(copied.get_int_var_from_proto_index(var.index) == targets[sid])
            return copied

        # 基準割れの許可はクライアントの証明フラグを使わず、毎回サーバーで確認する。
        may_lower = False
        if reference is None or reference['exceptionCount'] or reference['staffingShortfallTotal'] > bounds['total']:
            baseline_model = fixed_target()
            baseline_model.minimize(upper)
            if reference is not None:
                add_hints(self.reference, targets)
                baseline_model = fixed_target()
                baseline_model.minimize(upper)
                baseline_model.add(upper <= baseline_upper)
            solver = new_solver(min(20, remaining() * .4))
            status = solver.solve(baseline_model)
            self.trace.append({'stage': 'necessity', 'status': solver.status_name(status), 'seconds': round(solver.wall_time, 3)})
            may_lower = (status == cp_model.INFEASIBLE and reference is None or
                         status == cp_model.OPTIMAL and reference is not None and round(solver.objective_value) == baseline_upper)
            if reference is None and status != cp_model.INFEASIBLE:
                return {'status': 'UNKNOWN', 'autoReason': 'necessity_unconfirmed', 'autoDone': True, 'trace': self.trace}
        mode = 'lower' if may_lower else 'increase'
        if mode == 'increase':
            for sid, var in self.minimums.items():
                model.add(var >= targets[sid])
            if reference is None:
                return {'status': 'UNKNOWN', 'autoDone': True}
            original_extras = []
            for st in p['staff']:
                sid = st['id']
                off = sum(names[f'{sid}_{d}_off'] for d in range(p['days']))
                model.add(off >= list(self.reference[sid].values()).count('off'))
                if sid not in p['fairnessExcludedStaff']:
                    original_extras.append(off - targets[sid])
            high = model.new_int_var(-p['days'], p['days'], 'auto_original_extra_high')
            low = model.new_int_var(-p['days'], p['days'], 'auto_original_extra_low')
            if original_extras:
                model.add_max_equality(high, original_extras)
                model.add_min_equality(low, original_extras)
            else:
                model.add(high == 0)
                model.add(low == 0)
            original_minor = expressions['minor'] - expressions['extra_spread'] * minor_unit(p) + (high - low) * minor_unit(p)
            limits = {'exceptions': reference['exceptionCount'], 'shortage': reference['staffingShortfallTotal'],
                      'preference': len(reference['nightRestPreferences']['unmet']), 'night_spread': reference['allocation']['nightSpread'],
                      'overtime': reference['allocation']['overtimeTotal'],
                      'balance': reference['allocation']['overtimeBalance'] * (1 if reference['allocation']['overtimeProportional'] else 100),
                      'surplus': reference['allocation']['surplusTotal']}
            for name, limit in limits.items():
                model.add(expressions[name] <= limit)
            model.add(high - low <= reference['allocation']['extraOffSpread'])
            model.add(low >= reference['allocation']['commonExtraDaysOff'])
            model.add(original_minor <= reference['allocation']['minor'])
            rest = sum(self.minimums[s['id']] for s in p['staff'])
            stages = [('holidays', -rest)]
        else:
            if reference:
                model.add(upper < baseline_upper)
            deficits = []
            for sid, var in self.minimums.items():
                delta = model.new_int_var(0, p['days'], sid + '_auto_deficit')
                model.add_max_equality(delta, [0, targets[sid] - var])
                deficits.append(delta)
                # 基準割れと増加を一緒に行って、別の人の休みを削ることを避ける。
                model.add(var <= targets[sid])
            maximum = model.new_int_var(0, p['days'], 'auto_max_deficit')
            model.add_max_equality(maximum, deficits)
            stages = [('conditions', upper), ('max_deficit', maximum), ('total_deficit', sum(deficits)),
                      ('night_rest', expressions['preference']), ('night_balance', expressions['night_spread']),
                      ('overtime', expressions['overtime']), ('overtime_fairness', expressions['balance'])]
        variables = [model.get_int_var_from_proto_index(i) for i in range(len(model.proto.variables))]
        initial_rows = self.candidate_rows or self.reference
        initial_quotas = self.candidate_quotas or targets
        if initial_rows is not None and (mode == 'increase' or self.candidate_rows is not None):
            add_hints(initial_rows, initial_quotas)
            completion = new_solver(min(1, remaining()))
            completion.parameters.num_search_workers = 1
            completion.parameters.fix_variables_to_their_hinted_value = True
            status = completion.solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                hints = [int(completion.value(v)) for v in variables]
        candidate, proven = None, {}
        for name, expression in stages:
            if remaining() < .01:
                break
            model.minimize(expression)
            if hints is not None:
                model.clear_hints()
                for v, value in zip(variables, hints):
                    model.add_hint(v, value)
            solver = new_solver(remaining())
            status = solver.solve(model)
            self.trace.append({'stage': name, 'status': solver.status_name(status), 'seconds': round(solver.wall_time, 3)})
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                hints = [int(solver.value(v)) for v in variables]
                quotas = {sid: int(solver.value(var)) for sid, var in self.minimums.items()}
                candidate = {'rows': extract(solver), 'quotas': quotas}
                proven[name] = status == cp_model.OPTIMAL
                model.add(expression == int(solver.value(expression)))
                if status != cp_model.OPTIMAL:
                    break
            else:
                proven[name] = status == cp_model.INFEASIBLE
                if name == 'conditions' and reference is None and status == cp_model.INFEASIBLE:
                    return {'status': 'INFEASIBLE', 'autoDone': True, 'autoReason': 'range_infeasible', 'trace': self.trace}
                break
        done = all(proven.get(name) for name, _ in stages)
        if candidate is None:
            return {'status': 'UNKNOWN', 'autoDone': done or bool(proven), 'autoReason': 'unchanged' if reference else 'no_candidate', 'trace': self.trace}
        chosen = effective_input(target, candidate['quotas'])
        proposal = inspect(chosen, candidate['rows'])
        if reference is not None:
            if mode == 'increase':
                # 共通の目標で再集計して、日数の書き換えだけで公平さが良く見えることを防ぐ。
                shared = inspect(target, candidate['rows'])
                if (any(a > b for a, b in zip(rank(shared), rank(reference)))
                        or any(list(candidate['rows'][sid].values()).count('off') < list(row.values()).count('off')
                               for sid, row in self.reference.items())):
                    return {'status': 'UNKNOWN', 'autoDone': True, 'autoReason': 'reference_kept', 'trace': self.trace}
            elif (proposal['exceptionCount'], proposal['staffingShortfallTotal']) >= (reference['exceptionCount'], reference['staffingShortfallTotal']):
                return {'status': 'UNKNOWN', 'autoDone': True, 'autoReason': 'reference_kept', 'trace': self.trace}
        if mode == 'lower' and not (proven.get('max_deficit') and proven.get('total_deficit')):
            # 最小限の基準割れを確認するまでは、参照候補を完成結果として保持する。
            return {'status': 'UNKNOWN', 'autoDone': done, 'autoReason': 'deficit_unconfirmed',
                    'autoCandidate': {'assignments': candidate['rows'], 'quotas': candidate['quotas']}, 'trace': self.trace}
        proposal.update(selectedQuota=candidate['quotas'], autoDone=done, autoReason='necessary_reduction' if mode == 'lower' else 'quality_preserved',
                        trace=self.trace, autoChanged=(candidate['quotas'] != targets or candidate['rows'] != self.reference),
                        autoReferenceActualOff={sid: list(row.values()).count('off') for sid, row in (self.reference or {}).items()})
        if mode == 'increase':
            actual_bound = overtime_bound(chosen, proposal['staffingShortfallTotal'], actual_off=proposal['autoReferenceActualOff'])
            if proposal['allocation']['overtimeTotal'] == actual_bound:
                proposal['allocation'].update(minimumOvertimeProven=True, minimumOvertimeScope='WITH_CURRENT_ACTUAL_HOLIDAYS_PRESERVED')
        proposal['comparisonQuality'] = list(rank(shared if mode == 'increase' else proposal))
        proposal['autoDetails'] = {'necessityProven': mode == 'lower', 'daysProven': done, 'qualityPreserved': mode == 'increase',
                                  'shortageLowerBound': bounds['total'], 'overtimeLowerBound': overtime_bound(chosen, proposal['staffingShortfallTotal']),
                                  'referenceOvertime': reference['allocation']['overtimeTotal'] if reference else None,
                                  'referenceShortage': reference['staffingShortfallTotal'] if reference else None}
        return proposal


class QualityRefinement(HolidayPlan):
    """基準の完成候補を改善する追加探索。残業の偏りも同時に守り、基準割れは行わない。"""
    def run(self, model, p, new_solver, extract, **expressions):
        target = target_input(self.original, self.policy)
        before = inspect(target, self.reference)
        variables = [model.get_int_var_from_proto_index(i) for i in range(len(model.proto.variables))]
        names = {v.name: v for v in variables}
        for sid, var in self.minimums.items():
            model.add(var == self.policy[sid]['target'])
        for name, limit in {'exceptions': before['exceptionCount'], 'shortage': before['staffingShortfallTotal'],
                            'preference': len(before['nightRestPreferences']['unmet']), 'night_spread': before['allocation']['nightSpread'],
                            'overtime': before['allocation']['overtimeTotal']}.items():
            model.add(expressions[name] <= limit)
        baseline_balance = before['allocation']['overtimeBalance'] * (1 if before['allocation']['overtimeProportional'] else 100)
        table = refinement_balance_limits(p, before['allocation']['overtimeTotal'], baseline_balance)
        total = model.new_int_var(0, before['allocation']['overtimeTotal'], 'auto_refine_total')
        limit = model.new_int_var(0, max(v for _, v in table), 'auto_refine_fairness_limit')
        model.add(total == expressions['overtime'])
        model.add_allowed_assignments([total, limit], table)
        model.add(expressions['balance'] <= limit)
        model.add(expressions['common_extra'] >= before['allocation']['commonExtraDaysOff'])
        model.clear_hints()
        for st in p['staff']:
            sid = st['id']
            for d in range(p['days']):
                for k in SHIFTS:
                    model.add_hint(names[f'{sid}_{d}_{k}'], int(self.reference[sid][str(d + 1)] == k))
        for var in self.groups.values():
            sid = next(sid for sid, v in self.minimums.items() if v.index == var.index)
            model.add_hint(var, self.policy[sid]['target'])
        completion = new_solver(min(1, max(.000001, self.deadline - time.monotonic())))
        completion.parameters.num_search_workers = 1
        completion.parameters.fix_variables_to_their_hinted_value = True
        status = completion.solve(model)
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            model.clear_hints()
            for v in variables:
                model.add_hint(v, int(completion.value(v)))
        model.minimize(expressions['overtime'])
        solver = new_solver(max(.000001, self.deadline - time.monotonic()))
        status = solver.solve(model)
        if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            return {'status': 'UNKNOWN'}
        after = inspect(target, extract(solver))
        if rank(after) > rank(before):
            return {'status': 'UNKNOWN'}
        # 新合計の算術上の差まで許し、基準の均等さを守る範囲。全条件での最少とは混同しない。
        if status == cp_model.OPTIMAL and not after['allocation']['minimumOvertimeProven']:
            after['allocation'].update(minimumOvertimeProven=True, minimumOvertimeScope='WITH_BASELINE_FAIRNESS_AND_COMMON_HOLIDAYS_PRESERVED')
        after['search'] = {'done': True}
        return after


class BaselineNecessity(HolidayPlan):
    """継続・仕上げで基準割れを使う前に、基準側の必要性を再確認する。"""
    def run(self, model, p, new_solver, extract, **expressions):
        for sid, var in self.minimums.items():
            model.add(var == self.policy[sid]['target'])
        upper = expressions['exceptions'] * (120 * p['days'] + 1) + expressions['shortage']
        model.minimize(upper)
        solver = new_solver(max(.000001, self.deadline - time.monotonic()))
        status = solver.solve(model)
        return {'status': solver.status_name(status),
                'upperMinimum': int(solver.value(upper)) if status == cp_model.OPTIMAL else None}


def dispatch_auto(payload):
    from .engine import solve
    from .service import dispatch, check_resume
    started = time.monotonic()
    raw = without_preferences(payload['input'])
    policy = checked_policy(raw, payload.get('holidayPolicy'))
    seconds = payload.get('seconds', 60)
    seed = payload.get('seed', 1)
    if type(seconds) not in (int, float) or not 0 < seconds <= 60 or type(seed) is not int or not 1 <= seed <= 1000:
        raise ValueError('計算時間は1〜60秒、探し方は1〜1000で指定してください。')
    target = target_input(raw, policy)
    phase = payload.get('autoPhase', 'base')
    if phase == 'base':
        normal = {k: deepcopy(v) for k, v in payload.items() if k not in ('mode', 'holidayPolicy', 'autoPhase')}
        resume = check_resume(normal.get('resume'), True)
        if resume is not None:
            # 段階・停滞時間は継続の手掛かり。クライアントが送る最少証明は採用しない。
            resume['proven'] = {}
            normal['resume'] = resume
        normal.update(input=target, qualityFirst=True, adaptive=False, allowStaffingShortfall=True,
                      allowRuleExceptions=True, allowNightShortfall=False)
        result = dispatch(normal, _deadline=started + seconds)
        result['selectedQuota'] = {sid: q['target'] for sid, q in policy.items()}
        if 'assignments' in result:
            result['autoBounds'] = decision_bounds(target, policy, result)
            if result['allocation']['overtimeTotal'] == result['autoBounds']['overtime']:
                result['allocation']['minimumOvertimeProven'] = True
    elif phase == 'polish':
        reference = payload.get('referenceAssignments')
        inspect(target, reference)
        fixed_policy = {sid: dict(min=q['target'], target=q['target'], max=q['target'], fixed=q['fixed']) for sid, q in policy.items()}
        plan = QualityRefinement(raw, fixed_policy, started + seconds - .15, reference)
        result = solve(target, seconds=seconds, seed=seed, quality_first=True,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True, _holiday_plan=plan)
        if 'assignments' in result:
            result['selectedQuota'] = {sid: q['target'] for sid, q in policy.items()}
            result['autoBounds'] = decision_bounds(target, policy, result)
    elif phase == 'adjust':
        reference = payload.get('referenceAssignments')
        if reference is not None:
            inspect(target, reference)
        candidate = payload.get('autoCandidate')
        quotas, rows = None, None
        if candidate is not None:
            if not isinstance(candidate, dict):
                raise ValueError('継続する公休候補を確認してください。')
            quotas = checked_quotas(policy, candidate.get('quotas'), target)
            rows = candidate.get('assignments')
            inspect(effective_input(target, quotas), rows)
        plan = HolidayPlan(raw, policy, started + seconds - .15, reference, candidate=rows, candidate_quotas=quotas)
        result = solve(plan.prepare(), seconds=seconds, seed=seed, quality_first=True,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True, _holiday_plan=plan)
    elif phase == 'finish':
        quotas = checked_quotas(policy, payload.get('selectedQuota'), target)
        chosen = effective_input(target, quotas)
        rows = payload.get('initialAssignments')
        previous = inspect(chosen, rows)
        reference = payload.get('referenceAssignments')
        actual = None
        reducing = any(quotas[sid] < q['target'] for sid, q in policy.items())
        if reducing:
            proof_plan = BaselineNecessity(raw, policy, min(started + seconds - .15, time.monotonic() + 20), reference)
            proof = solve(proof_plan.prepare(), seconds=seconds, seed=seed, quality_first=True,
                          allow_staffing_shortfall=True, allow_rule_exceptions=True, _holiday_plan=proof_plan)
            if reference is None:
                if proof['status'] != 'INFEASIBLE':
                    raise ValueError('基準の公休では成立しないことを確認できていません。')
            else:
                ref = inspect(target, reference)
                original_upper = ref['exceptionCount'] * (120 * normalize(raw)['days'] + 1) + ref['staffingShortfallTotal']
                if proof['status'] != 'OPTIMAL' or proof['upperMinimum'] != original_upper:
                    raise ValueError('公休を減らす必要性を確認できていません。')
        if reference is not None:
            ref = inspect(target, reference)
            if all(quotas[sid] >= q['target'] for sid, q in policy.items()):
                actual = {sid: list(row.values()).count('off') for sid, row in reference.items()}
                if any(list(rows[sid].values()).count('off') < value for sid, value in actual.items()):
                    raise ValueError('確保済みの休みを維持できていません。')
            elif (previous['exceptionCount'], previous['staffingShortfallTotal']) >= (ref['exceptionCount'], ref['staffingShortfallTotal']):
                raise ValueError('休みを減らす必要性を確認できていません。')
        result = solve(chosen, seconds=max(.000001, started + seconds - time.monotonic()), seed=seed, quality_first=True,
                       allow_staffing_shortfall=True, allow_rule_exceptions=True,
                       initial_assignments=rows, resume={'stage': 'conditions', 'idle': 0, 'proven': {}},
                       _holiday_actual_off=actual, _deadline=started + seconds)
        if 'assignments' in result:
            new = inspect(chosen, result['assignments'])
            # 段階の辞書式比較に加え、増加時は全保護項目を個別に確認する。
            shared_ok = actual is None or all(a <= b for a, b in zip(rank(inspect(target, result['assignments'])), rank(inspect(target, rows))))
            if rank(new) > rank(previous) or not shared_ok:
                result = previous
            if actual is not None:
                result['allocation']['minimumOvertimeScope'] = 'WITH_CURRENT_ACTUAL_HOLIDAYS_PRESERVED'
        result['selectedQuota'] = quotas
    else:
        raise ValueError('おまかせの計算段階を確認してください。')
    result['seconds'] = round(time.monotonic() - started, 3)
    result['optimizationPolicy'] = POLICY
    return result
