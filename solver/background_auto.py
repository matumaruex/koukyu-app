"""おまかせ作成のバックグラウンド化に向けたロジック検証。"""
from solver.background_normal import candidate

def quality(r):
    m = r.get('allocation') or {}
    return [r.get('exceptionCount') or 0, r.get('staffingShortfallTotal') or 0,
            len((r.get('nightRestPreferences') or {}).get('unmet') or []),
            m.get('nightSpread') or 0, m.get('overtimeTotal') or 0,
            (m.get('overtimeBalance') or 0) * (1 if m.get('overtimeProportional') else 100),
            m.get('surplusTotal') or 0, -(m.get('commonExtraDaysOff') or 0), m.get('minor') or 0]

def compare(a,b):
    for x,y in zip(quality(a),quality(b)):
        if x != y: return x-y
    return 0

async def auto(input_data, holiday_policy, solve, max_seconds=480, base_seconds=300, adjust_seconds=120, finish_seconds=60, per_call=60):
    spent=phase_spent=0
    rounds=[]
    best=last=resume=failure=details=pending=None
    base_done=adjust_done=necessity=False
    target={sid:q['target'] for sid,q in holiday_policy.items()}
    quota=dict(target)
    async def call(phase,budget,extra=None):
        nonlocal spent,phase_spent,last
        req={'mode':'auto','autoPhase':phase,'input':input_data,'holidayPolicy':holiday_policy,
             'seconds':min(per_call,budget,max_seconds-spent),'seed':len(rounds)%1000+1,**(extra or {})}
        r=await solve(req)
        elapsed=r.get('seconds')
        if not isinstance(elapsed,(int,float)) or isinstance(elapsed,bool) or elapsed<0: elapsed=min(per_call,budget)
        else: elapsed=max(.01,elapsed)
        spent+=elapsed
        phase_spent+=elapsed
        rounds.append({'phase':phase,'seconds':elapsed,'status':r.get('status')})
        last=r
        return r
    while phase_spent < base_seconds-.1:
        extra={}
        if best: extra['initialAssignments']=best['assignments']
        if resume: extra['resume']=resume
        r=await call('base',base_seconds-phase_spent,extra)
        take=candidate(r) and (not best or compare(r,best)<=0)
        if take: best=r
        status=r.get('status')
        search=r.get('search') or {}
        if status=='WORKER_ERROR': break
        if status=='INFEASIBLE': failure=r; necessity=True; break
        if status in ('INVALID_INPUT','VALIDATION_FAILED'): break
        if status=='OPTIMAL' or search.get('done'): base_done=True; break
        if not (status=='UNKNOWN' or search.get('continueRecommended')): break
        resume=search.get('resume') if take or not best else None
    fairness_spent=0
    while (not last or last.get('status')!='WORKER_ERROR') and best and (best.get('allocation') or {}).get('minimumOvertimeProven') is not True and isinstance((best.get('autoBounds') or {}).get('overtime'),int) and best['allocation']['overtimeTotal']>best['autoBounds']['overtime'] and fairness_spent<adjust_seconds-.1 and spent<max_seconds-.1:
        before=spent
        r=await call('polish',adjust_seconds-fairness_spent,{'referenceAssignments':best['assignments']})
        fairness_spent+=spent-before
        if r.get('status')=='WORKER_ERROR': break
        if candidate(r) and compare(r,best)<=0: best=r
        if candidate(r) and (r.get('allocation') or {}).get('minimumOvertimeProven'): break
    while (not last or last.get('status')!='WORKER_ERROR') and best and (best.get('overtimeFairness') or {}).get('minimumSpreadProven') is False and fairness_spent<adjust_seconds-.1 and spent<max_seconds-.1:
        before=spent
        r=await call('base',adjust_seconds-fairness_spent,{'initialAssignments':best['assignments'],'resume':{'stage':'overtime_fairness','idle':0,'proven':{}}})
        fairness_spent+=spent-before
        if r.get('status')=='WORKER_ERROR': break
        if candidate(r) and compare(r,best)<=0: best=r
        if not candidate(r) or (r.get('overtimeFairness') or {}).get('minimumSpreadProven'): break
    reference=best
    if best and (best.get('autoBounds') or {}).get('holidayChangeRuledOut'):
        adjust_done=True
        best={**best,'autoReason':'quality_preserved','autoDetails':{'daysProven':True,'shortageLowerBound':best['autoBounds'].get('shortage'),'overtimeLowerBound':best['autoBounds'].get('overtime')}}
    if (best or necessity) and (not last or last.get('status')!='WORKER_ERROR'):
        phase_spent=fairness_spent
        while not adjust_done and phase_spent<adjust_seconds-.1 and spent<max_seconds-.1:
            extra={}
            if reference: extra['referenceAssignments']=reference['assignments']
            if pending: extra['autoCandidate']=pending
            r=await call('adjust',adjust_seconds-phase_spent,extra)
            if candidate(r):
                selected=r.get('selectedQuota') or {}
                reduction=any(q<target[sid] for sid,q in selected.items())
                qr=quality(r)
                upper=not reference or qr[0]<quality(reference)[0] or (qr[0]==quality(reference)[0] and qr[1]<quality(reference)[1])
                all_protected=not reference or all(v<=quality(reference)[i] for i,v in enumerate(r.get('comparisonQuality') or qr))
                more=sum(selected.values())>sum(quota.values())
                first_reduction=reduction and all(q>=target[sid] for sid,q in quota.items())
                if ((reduction and (r.get('autoDetails') or {}).get('necessityProven') and upper) or (not reduction and all_protected)) and (not best or first_reduction or (more and not reduction) or compare(r,best)<=0):
                    if r.get('autoChanged') is False and reference:
                        allocation=dict(reference['allocation'])
                        if (r.get('allocation') or {}).get('minimumOvertimeProven'):
                            allocation.update({'minimumOvertimeProven':True,'minimumOvertimeScope':r['allocation'].get('minimumOvertimeScope')})
                        best={**reference,'autoDetails':r.get('autoDetails'),'autoReason':r.get('autoReason'),'allocation':allocation}
                    else: best=r
                    quota=dict(selected); details=r.get('autoDetails'); pending={'assignments':best['assignments'],'quotas':quota}
            elif r.get('autoCandidate'): pending=r['autoCandidate']
            if r.get('autoDone'): adjust_done=True; break
            if r.get('status') in ('INVALID_INPUT','VALIDATION_FAILED','INFEASIBLE','WORKER_ERROR'): break
        changed=any(q!=target[sid] for sid,q in quota.items())
        if best and (not last or last.get('status')!='WORKER_ERROR') and (not reference or changed or best['assignments']!=reference['assignments']):
            phase_spent=0
            while phase_spent<finish_seconds-.1 and spent<max_seconds-.1:
                extra={'selectedQuota':quota,'initialAssignments':best['assignments']}
                if reference: extra['referenceAssignments']=reference['assignments']
                r=await call('finish',finish_seconds-phase_spent,extra)
                if candidate(r) and compare(r,best)<=0: best={**r,'autoReason':best.get('autoReason'),'autoDetails':details}
                if (r.get('search') or {}).get('done') or r.get('status')=='OPTIMAL' or not candidate(r): break
    if best:
        best={**best,'selectedQuota':quota,'autoDetails':{**(best.get('autoDetails') or details or {}),'daysProven':adjust_done},'autoReason':best.get('autoReason') or ('quality_preserved' if adjust_done else 'days_unconfirmed')}
    return {'best':best,'last':last,'seconds':spent,'rounds':rounds,'error':'計算を完了できませんでした。' if last and last.get('status')=='WORKER_ERROR' else None,'failure':failure,'done':base_done and adjust_done,'stale':False}




