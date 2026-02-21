// ===== 自動スケジュール生成アルゴリズム =====
// 介護施設の制約条件を考慮してシフトを自動配置する

/**
 * シフトの種類を定義
 */
const SHIFT_TYPES = {
    EARLY: 'early',       // 早番（早出）→ 表示「A」
    LATE: 'late',         // 遅番（遅出）→ 表示「B」
    NIGHT: 'night',       // 夜勤
    NIGHT_OFF: 'nightOff', // 明け（夜勤翌日）
    OFF: 'off',           // 休み
    OVERTIME: 'overtime'  // 通し（早残）→ 表示「A残」
};

/**
 * シフトの表示名
 */
const SHIFT_LABELS = {
    [SHIFT_TYPES.EARLY]: 'A',
    [SHIFT_TYPES.LATE]: 'B',
    [SHIFT_TYPES.NIGHT]: '夜',
    [SHIFT_TYPES.NIGHT_OFF]: '明',
    [SHIFT_TYPES.OFF]: '休',
    [SHIFT_TYPES.OVERTIME]: 'A残'
};

/**
 * フルタイムのシフト時間（固定）
 * 時刻は分単位に変換して判定に使う
 */
const SHIFT_TIME_RANGES = {
    [SHIFT_TYPES.EARLY]: { start: 420, end: 960 },      // 7:00〜16:00
    [SHIFT_TYPES.LATE]: { start: 570, end: 1110 },       // 9:30〜18:30
    [SHIFT_TYPES.OVERTIME]: { start: 420, end: 1110 },   // 7:00〜18:30
    [SHIFT_TYPES.NIGHT]: { start: 1020, end: 1440 },     // 夜勤入り 17:00〜（夕方にいる人としてカウント）
    [SHIFT_TYPES.NIGHT_OFF]: { start: 0, end: 540 }      // 明け 〜9:00（朝にいる人としてカウント）
};

/**
 * 表示用シフト時間テキスト
 */
const SHIFT_TIMES = {
    [SHIFT_TYPES.EARLY]: '7:00〜16:00',
    [SHIFT_TYPES.LATE]: '9:30〜18:30',
    [SHIFT_TYPES.OVERTIME]: '7:00〜18:30',
    [SHIFT_TYPES.NIGHT]: '夜勤',
    [SHIFT_TYPES.NIGHT_OFF]: '明け',
    [SHIFT_TYPES.OFF]: '休み'
};

/**
 * 時間帯チェック：必要人数を確認する時刻（分単位）
 */
const TIME_CHECKPOINTS = [
    { label: '朝(7:00)', minutes: 420, required: 4, sundayRequired: 4 },
    { label: '昼(10:00)', minutes: 600, required: 4, sundayRequired: 4 },
    { label: '夕(17:45)', minutes: 1065, required: 4, sundayRequired: 3 }
];

/**
 * デフォルトの設定値
 */
const DEFAULT_SETTINGS = {
    earlyRequired: 3,        // 平日の早番必要人数（夜勤明け1人と合わせて朝4人）
    lateRequired: 3,         // 平日の遅番必要人数（夜勤入り1人と合わせて夕方4人）
    nightRequired: 1,        // 夜勤必要人数
    sundayEarlyRequired: 3,  // 日曜の早番必要人数（夜勤明け1人と合わせて朝4人）
    sundayLateRequired: 2,   // 日曜の遅番必要人数（夜勤入り1人と合わせて夕方3人）
    sundayNightRequired: 1,  // 日曜の夜勤必要人数
    maxConsecutive: 5        // デフォルトの最大連勤日数
};

/**
 * 時刻文字列（"HH:MM"）を分に変換
 */
function timeToMinutes(timeStr) {
    if (!timeStr) return null;
    const parts = timeStr.split(':');
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
}

/**
 * スタッフが指定時刻に勤務中かどうかを判定
 * @param {Object} staff - スタッフ情報
 * @param {string} shift - シフトタイプ
 * @param {number} checkMinutes - チェックする時刻（分単位）
 * @returns {boolean} その時刻に勤務中かどうか
 */
function isStaffPresentAt(staff, shift, checkMinutes) {
    if (!shift || shift === SHIFT_TYPES.OFF) return false;

    // パートの場合：個人の勤務時間で判定
    if (staff.type === 'part' && staff.startTime && staff.endTime) {
        // パートは早番(A)または遅番(B)で入る
        // earlyまたはlateの場合、パート個人の時間で判定
        if (shift === SHIFT_TYPES.EARLY || shift === SHIFT_TYPES.LATE) {
            const start = timeToMinutes(staff.startTime);
            const end = timeToMinutes(staff.endTime);
            if (start !== null && end !== null) {
                return checkMinutes >= start && checkMinutes < end;
            }
        }
        // それ以外のシフト（休み、明けなど）はフルタイムと同じ判定
    }

    // フルタイムの場合：シフトの固定時間で判定
    const range = SHIFT_TIME_RANGES[shift];
    if (range) {
        return checkMinutes >= range.start && checkMinutes < range.end;
    }

    return false;
}

/**
 * 指定日の特定時刻に何人いるかを数える
 */
function countStaffAtTime(staffList, allAssignments, day, checkMinutes) {
    let count = 0;
    staffList.forEach(staff => {
        const shift = allAssignments[staff.id]?.[day];
        if (isStaffPresentAt(staff, shift, checkMinutes)) {
            count++;
        }
    });
    return count;
}

/**
 * 指定月の日数を取得
 */
function getDaysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
}

/**
 * 指定日の曜日を取得（0=日曜, 6=土曜）
 */
function getDayOfWeek(year, month, day) {
    return new Date(year, month - 1, day).getDay();
}

/**
 * その日が日曜日かどうか
 */
function isSunday(year, month, day) {
    return getDayOfWeek(year, month, day) === 0;
}

/**
 * その日が金・土・日かどうか（夜勤制限の判定用）
 */
function isFriSatSun(year, month, day) {
    const dow = getDayOfWeek(year, month, day);
    return dow === 0 || dow === 5 || dow === 6;
}

/**
 * スタッフの連勤日数を計算（指定日を含む過去の連続勤務日数）
 */
function getConsecutiveWorkDays(assignments, day) {
    let count = 0;
    for (let d = day; d >= 1; d--) {
        const shift = assignments[d];
        if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
            count++;
        } else {
            break;
        }
    }
    return count;
}

/**
 * スタッフごとの最大連勤日数を取得
 */
function getStaffMaxConsecutive(staff, settings) {
    if (staff.maxConsecutive && staff.maxConsecutive > 0) {
        return staff.maxConsecutive;
    }
    if (staff.type !== 'part' && staff.nightShiftType && staff.nightShiftType !== 'none') {
        return 2;
    }
    return settings.maxConsecutive || DEFAULT_SETTINGS.maxConsecutive;
}

/**
 * 指定日にこのスタッフが勤務可能かチェック
 */
function canWorkOnDay(staff, assignments, day, settings) {
    if (assignments[day]) return false;
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;
    return true;
}

/**
 * 指定日にこのスタッフを夜勤に割り当て可能かチェック
 */
function canAssignNight(staff, assignments, day, daysInMonth, settings, year, month) {
    const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');
    if (nightType === 'none') return false;
    if (staff.type === 'part') return false;
    if (nightType === 'weekday' && isFriSatSun(year, month, day)) return false;
    if (assignments[day]) return false;
    if (day + 1 <= daysInMonth && assignments[day + 1]) return false;
    if (day + 2 <= daysInMonth && assignments[day + 2]) return false;
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;
    return true;
}

/**
 * スタッフの特定シフトの割り当て回数を数える
 */
function countShiftType(assignments, shiftType, daysInMonth) {
    let count = 0;
    for (let d = 1; d <= daysInMonth; d++) {
        if (assignments[d] === shiftType) count++;
    }
    return count;
}

/**
 * スタッフの勤務日数を数える
 */
function countWorkDays(assignments, daysInMonth) {
    let count = 0;
    for (let d = 1; d <= daysInMonth; d++) {
        const s = assignments[d];
        if (s && s !== SHIFT_TYPES.OFF && s !== SHIFT_TYPES.NIGHT_OFF) {
            count++;
        }
    }
    return count;
}

/**
 * スタッフの休日数を数える
 */
function countOffDays(assignments, daysInMonth) {
    let count = 0;
    for (let d = 1; d <= daysInMonth; d++) {
        if (assignments[d] === SHIFT_TYPES.OFF) count++;
    }
    return count;
}

/**
 * パートスタッフの週ごとの勤務日数をチェック
 */
function getWeekWorkDays(assignments, day, year, month) {
    const date = new Date(year, month - 1, day);
    const dayOfWeek = date.getDay();
    const monday = day - ((dayOfWeek + 6) % 7);
    let count = 0;
    for (let d = monday; d < monday + 7; d++) {
        if (d < 1 || d > getDaysInMonth(year, month)) continue;
        const s = assignments[d];
        if (s && s !== SHIFT_TYPES.OFF && s !== SHIFT_TYPES.NIGHT_OFF) {
            count++;
        }
    }
    return count;
}

/**
 * 配列をシャッフル
 */
function shuffleArray(arr) {
    const shuffled = [...arr];
    for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
}

/**
 * スタッフの目標勤務日数を計算
 */
function getTargetWorkDays(staff, daysInMonth) {
    return daysInMonth - (staff.monthlyDaysOff || 9);
}

/**
 * スタッフが早番に入れるかどうか
 */
function canAssignEarly(staff) {
    if (staff.type === 'part' && staff.lateOnly) return false;
    return true;
}

/**
 * スタッフが遅番に入れるかどうか
 */
function canAssignLate(staff) {
    if (staff.type === 'part' && staff.earlyOnly) return false;
    return true;
}

/**
 * スタッフが特定のシフトに割り当てられた場合、
 * 各時間帯チェックポイントでカバーできる時間帯を返す
 */
function getStaffCoverage(staff, shiftType) {
    const coverage = [];
    TIME_CHECKPOINTS.forEach(cp => {
        if (isStaffPresentAt(staff, shiftType, cp.minutes)) {
            coverage.push(cp.minutes);
        }
    });
    return coverage;
}

/**
 * メインの自動生成関数
 */
function generateSchedule(staffList, year, month, requests, settings) {
    const s = { ...DEFAULT_SETTINGS, ...settings };
    const daysInMonth = getDaysInMonth(year, month);
    const warnings = [];

    // 全スタッフの割り当てを初期化
    const allAssignments = {};
    staffList.forEach(staff => {
        allAssignments[staff.id] = {};
    });

    // ===== フェーズ1: 希望休を設定 =====
    staffList.forEach(staff => {
        const staffRequests = requests[staff.id] || [];
        staffRequests.forEach(day => {
            if (day >= 1 && day <= daysInMonth) {
                allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
            }
        });
    });

    // ===== フェーズ2: 夜勤を割り当て =====
    const nightEligible = staffList.filter(st => {
        const nightType = st.nightShiftType || (st.canNightShift ? 'all' : 'none');
        return nightType !== 'none' && st.type !== 'part';
    });

    for (let day = 1; day <= daysInMonth; day++) {
        const required = isSunday(year, month, day) ? s.sundayNightRequired : s.nightRequired;
        for (let n = 0; n < required; n++) {
            const candidates = nightEligible.filter(st =>
                canAssignNight(st, allAssignments[st.id], day, daysInMonth, s, year, month)
            );
            if (candidates.length === 0) {
                warnings.push(`${month}月${day}日：夜勤に入れるスタッフが見つかりません`);
                continue;
            }
            const scored = candidates.map(st => ({
                staff: st,
                nightCount: countShiftType(allAssignments[st.id], SHIFT_TYPES.NIGHT, daysInMonth),
                workDays: countWorkDays(allAssignments[st.id], daysInMonth)
            }));
            scored.sort((a, b) => {
                if (a.nightCount !== b.nightCount) return a.nightCount - b.nightCount;
                return a.workDays - b.workDays;
            });
            const minScore = scored[0].nightCount;
            const topCandidates = shuffleArray(scored.filter(s => s.nightCount === minScore));
            const chosen = topCandidates[0].staff;

            allAssignments[chosen.id][day] = SHIFT_TYPES.NIGHT;
            if (day + 1 <= daysInMonth) {
                allAssignments[chosen.id][day + 1] = SHIFT_TYPES.NIGHT_OFF;
            }
            if (day + 2 <= daysInMonth) {
                allAssignments[chosen.id][day + 2] = SHIFT_TYPES.OFF;
            }
        }
    }

    // ===== フェーズ3: 日勤（早番・遅番）を時間帯カバーを考慮して割り当て =====
    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);
        const earlyNeeded = sunday ? s.sundayEarlyRequired : s.earlyRequired;
        const lateNeeded = sunday ? s.sundayLateRequired : s.lateRequired;

        // この日に勤務可能な人を集める
        const available = staffList.filter(st => {
            if (allAssignments[st.id][day]) return false;
            if (!canWorkOnDay(st, allAssignments[st.id], day, s)) return false;
            if (st.type === 'part') {
                const weekWork = getWeekWorkDays(allAssignments[st.id], day, year, month);
                if (weekWork >= (st.maxDaysPerWeek || 3)) return false;
            }
            return true;
        });

        // 専用スタッフを先に割り当て
        const earlyOnlyStaff = available.filter(st => st.type === 'part' && st.earlyOnly);
        const lateOnlyStaff = available.filter(st => st.type === 'part' && st.lateOnly);
        const flexStaff = available.filter(st => {
            if (st.type === 'part' && st.earlyOnly) return false;
            if (st.type === 'part' && st.lateOnly) return false;
            return true;
        });

        let earlyAssigned = 0;
        let lateAssigned = 0;
        const usedIds = new Set();

        // 公休優先：目標勤務日数に達していないかチェック
        const canWorkMore = (st) => {
            return countWorkDays(allAssignments[st.id], daysInMonth) < getTargetWorkDays(st, daysInMonth);
        };

        // (1) A残（通し勤務）の積極的割り当て（最優先）
        const TARGET_OVERTIME_PER_MONTH = 4;
        const overtimeEligible = flexStaff.filter(st => st.canOvertime && st.type !== 'part' && canWorkMore(st));
        const overtimeSorted = shuffleArray(overtimeEligible).sort((a, b) => {
            const aOT = countShiftType(allAssignments[a.id], SHIFT_TYPES.OVERTIME, daysInMonth);
            const bOT = countShiftType(allAssignments[b.id], SHIFT_TYPES.OVERTIME, daysInMonth);
            return aOT - bOT;
        });

        for (let i = 0; i < overtimeSorted.length && earlyAssigned < earlyNeeded && lateAssigned < lateNeeded; i++) {
            const st = overtimeSorted[i];
            const currentOT = countShiftType(allAssignments[st.id], SHIFT_TYPES.OVERTIME, daysInMonth);
            if (currentOT < TARGET_OVERTIME_PER_MONTH) {
                allAssignments[st.id][day] = SHIFT_TYPES.OVERTIME;
                usedIds.add(st.id);
                earlyAssigned++;
                lateAssigned++;
            }
        }

        // (2) 早出のみ → 早番（公休優先でフィルタ）
        const sortedEarlyOnly = [...earlyOnlyStaff].filter(canWorkMore).sort((a, b) => {
            const aGap = getTargetWorkDays(a, daysInMonth) - countWorkDays(allAssignments[a.id], daysInMonth);
            const bGap = getTargetWorkDays(b, daysInMonth) - countWorkDays(allAssignments[b.id], daysInMonth);
            return bGap - aGap; // 不足が大きい人を先に
        });
        for (let i = 0; i < sortedEarlyOnly.length && earlyAssigned < earlyNeeded; i++) {
            allAssignments[sortedEarlyOnly[i].id][day] = SHIFT_TYPES.EARLY;
            usedIds.add(sortedEarlyOnly[i].id);
            earlyAssigned++;
        }

        // (3) 遅出のみ → 遅番（公休優先でフィルタ）
        const sortedLateOnly = [...lateOnlyStaff].filter(canWorkMore).sort((a, b) => {
            const aGap = getTargetWorkDays(a, daysInMonth) - countWorkDays(allAssignments[a.id], daysInMonth);
            const bGap = getTargetWorkDays(b, daysInMonth) - countWorkDays(allAssignments[b.id], daysInMonth);
            return bGap - aGap;
        });
        for (let i = 0; i < sortedLateOnly.length && lateAssigned < lateNeeded; i++) {
            allAssignments[sortedLateOnly[i].id][day] = SHIFT_TYPES.LATE;
            usedIds.add(sortedLateOnly[i].id);
            lateAssigned++;
        }

        // (4) 両方可能なスタッフ：目標勤務日数に対する不足度を最優先でソート
        const flexSorted = shuffleArray(flexStaff).filter(st => !usedIds.has(st.id) && canWorkMore(st)).sort((a, b) => {
            const aGap = getTargetWorkDays(a, daysInMonth) - countWorkDays(allAssignments[a.id], daysInMonth);
            const bGap = getTargetWorkDays(b, daysInMonth) - countWorkDays(allAssignments[b.id], daysInMonth);
            return bGap - aGap;
        });

        // 早番を埋める
        const earlyCandidates = flexSorted.filter(st => canAssignEarly(st)).sort((a, b) => {
            const aEarly = countShiftType(allAssignments[a.id], SHIFT_TYPES.EARLY, daysInMonth);
            const bEarly = countShiftType(allAssignments[b.id], SHIFT_TYPES.EARLY, daysInMonth);
            const aLate = countShiftType(allAssignments[a.id], SHIFT_TYPES.LATE, daysInMonth);
            const bLate = countShiftType(allAssignments[b.id], SHIFT_TYPES.LATE, daysInMonth);
            const aDiff = aEarly - aLate;
            const bDiff = bEarly - bLate;
            if (aDiff !== bDiff) return aDiff - bDiff;
            return aEarly - bEarly;
        });

        for (let i = 0; i < earlyCandidates.length && earlyAssigned < earlyNeeded; i++) {
            const st = earlyCandidates[i];
            if (usedIds.has(st.id)) continue;
            allAssignments[st.id][day] = SHIFT_TYPES.EARLY;
            earlyAssigned++;
            usedIds.add(st.id);
        }

        // 遅番を埋める
        const lateCandidates = flexSorted.filter(st => canAssignLate(st) && !usedIds.has(st.id)).sort((a, b) => {
            const aLate = countShiftType(allAssignments[a.id], SHIFT_TYPES.LATE, daysInMonth);
            const bLate = countShiftType(allAssignments[b.id], SHIFT_TYPES.LATE, daysInMonth);
            const aEarly = countShiftType(allAssignments[a.id], SHIFT_TYPES.EARLY, daysInMonth);
            const bEarly = countShiftType(allAssignments[b.id], SHIFT_TYPES.EARLY, daysInMonth);
            const aDiff = aLate - aEarly;
            const bDiff = bLate - bEarly;
            if (aDiff !== bDiff) return aDiff - bDiff;
            return aLate - bLate;
        });

        for (let i = 0; i < lateCandidates.length && lateAssigned < lateNeeded; i++) {
            const st = lateCandidates[i];
            allAssignments[st.id][day] = SHIFT_TYPES.LATE;
            lateAssigned++;
            usedIds.add(st.id);
        }

        // (5) それでも足りない場合の緊急フォールバック（公休優先を一時無視）
        if (earlyAssigned < earlyNeeded) {
            const emergencyEarly = shuffleArray(available).filter(st => !usedIds.has(st.id) && canAssignEarly(st));
            for (let i = 0; i < emergencyEarly.length && earlyAssigned < earlyNeeded; i++) {
                allAssignments[emergencyEarly[i].id][day] = SHIFT_TYPES.EARLY;
                earlyAssigned++;
                usedIds.add(emergencyEarly[i].id);
            }
        }
        if (lateAssigned < lateNeeded) {
            const emergencyLate = shuffleArray(available).filter(st => !usedIds.has(st.id) && canAssignLate(st));
            for (let i = 0; i < emergencyLate.length && lateAssigned < lateNeeded; i++) {
                allAssignments[emergencyLate[i].id][day] = SHIFT_TYPES.LATE;
                lateAssigned++;
                usedIds.add(emergencyLate[i].id);
            }
            // A残でカバーできるならA残に昇格させる緊急処理
            if (lateAssigned < lateNeeded) {
                const upgradeCandidates = staffList.filter(st =>
                    allAssignments[st.id][day] === SHIFT_TYPES.EARLY && st.canOvertime && st.type !== 'part');
                for (let i = 0; i < upgradeCandidates.length && lateAssigned < lateNeeded; i++) {
                    allAssignments[upgradeCandidates[i].id][day] = SHIFT_TYPES.OVERTIME;
                    lateAssigned++;
                }
            }
        }

        // (6) 昼間（10時）の人数チェック → 不足なら追加で割り当て
        const middayCheckpoint = TIME_CHECKPOINTS.find(cp => cp.minutes === 600);
        if (middayCheckpoint) {
            const middayRequired = sunday ? middayCheckpoint.sundayRequired : middayCheckpoint.required;
            let middayCount = countStaffAtTime(staffList, allAssignments, day, 600);

            if (middayCount < middayRequired) {
                // ここでもなるべく公休優先
                const middayAvailable = shuffleArray(flexStaff).filter(st => !usedIds.has(st.id) && canWorkMore(st));
                for (let i = 0; i < middayAvailable.length && middayCount < middayRequired; i++) {
                    const st = middayAvailable[i];
                    const earlyCovers = isStaffPresentAt(st, SHIFT_TYPES.EARLY, 600);
                    const lateCovers = isStaffPresentAt(st, SHIFT_TYPES.LATE, 600);
                    if (earlyCovers && canAssignEarly(st)) {
                        allAssignments[st.id][day] = SHIFT_TYPES.EARLY;
                        usedIds.add(st.id);
                        middayCount++;
                    } else if (lateCovers && canAssignLate(st)) {
                        allAssignments[st.id][day] = SHIFT_TYPES.LATE;
                        usedIds.add(st.id);
                        middayCount++;
                    }
                }
                if (middayCount < middayRequired) {
                    warnings.push(`${month}月${day}日：昼(10時)の人数が${middayCount}人です（必要${middayRequired}人）`);
                }
            }
        }

        if (earlyAssigned < earlyNeeded) {
            warnings.push(`${month}月${day}日：早番が${earlyNeeded - earlyAssigned}人不足しています`);
        }
    }

    // ===== フェーズ4: 残りを「休み」にする =====
    staffList.forEach(staff => {
        for (let day = 1; day <= daysInMonth; day++) {
            if (!allAssignments[staff.id][day]) {
                allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
            }
        }
    });

    // ===== フェーズ5: 公休日数の調整（強化版） =====
    // 複数ラウンドで調整し、各スタッフの公休が目標に近づくようにする
    for (let round = 0; round < 3; round++) {
        staffList.forEach(staff => {
            const targetOff = staff.monthlyDaysOff || 9;
            let currentOff = countOffDays(allAssignments[staff.id], daysInMonth);

            // --- 公休が足りない場合：勤務日を休みに変換 ---
            if (currentOff < targetOff) {
                const changeCandidates = [];
                for (let day = 1; day <= daysInMonth; day++) {
                    const shift = allAssignments[staff.id][day];
                    if (shift !== SHIFT_TYPES.EARLY && shift !== SHIFT_TYPES.LATE) continue;

                    // その日の各時間帯の人数をチェック
                    let canRemove = true;
                    TIME_CHECKPOINTS.forEach(cp => {
                        const sundayFlag = isSunday(year, month, day);
                        // 朝夕はより厳格に、昼はやや緩めに
                        const requiredScore = sundayFlag ? cp.sundayRequired : cp.required;
                        // 昼（600）は9割程度でも許容するが、朝（420）夕（1065）は100%必須にするための調整
                        const actualRequired = (cp.minutes === 600) ? Math.max(requiredScore - 1, 1) : requiredScore;

                        // この人がいなくなった場合の人数
                        const currentCount = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
                        const wouldBePresent = isStaffPresentAt(staff, shift, cp.minutes);
                        if (wouldBePresent && (currentCount - 1) < actualRequired) {
                            canRemove = false;
                        }
                    });

                    if (canRemove) {
                        // 同シフトの人数も確認
                        let sameshiftCount = 0;
                        staffList.forEach(other => {
                            if (other.id === staff.id) return;
                            const otherShift = allAssignments[other.id][day];
                            if (shift === SHIFT_TYPES.EARLY && (otherShift === SHIFT_TYPES.EARLY || otherShift === SHIFT_TYPES.OVERTIME)) sameshiftCount++;
                            if (shift === SHIFT_TYPES.LATE && (otherShift === SHIFT_TYPES.LATE || otherShift === SHIFT_TYPES.OVERTIME)) sameshiftCount++;
                        });
                        const sundayCheck = isSunday(year, month, day);
                        const required = shift === SHIFT_TYPES.EARLY
                            ? (sundayCheck ? s.sundayEarlyRequired : s.earlyRequired)
                            : (sundayCheck ? s.sundayLateRequired : s.lateRequired);
                        const surplus = sameshiftCount - required;
                        changeCandidates.push({ day, surplus: Math.max(surplus, 0) });
                    }
                }
                // 余裕がある日から優先的に休みに変更
                changeCandidates.sort((a, b) => b.surplus - a.surplus);
                for (let i = 0; i < changeCandidates.length && currentOff < targetOff; i++) {
                    allAssignments[staff.id][changeCandidates[i].day] = SHIFT_TYPES.OFF;
                    currentOff++;
                }
            }

            // --- 公休が多すぎる場合：休みを勤務日に変換 ---
            if (currentOff > targetOff) {
                const changeCandidates = [];
                for (let day = 1; day <= daysInMonth; day++) {
                    if (allAssignments[staff.id][day] !== SHIFT_TYPES.OFF) continue;
                    // 希望休は変更しない
                    const staffRequests = requests[staff.id] || [];
                    if (staffRequests.includes(day)) continue;
                    // 連勤チェック（厳密にチェック）
                    if (!canWorkOnDay(staff, allAssignments[staff.id], day, s)) continue;
                    // パートの週間上限チェック
                    if (staff.type === 'part') {
                        const weekWork = getWeekWorkDays(allAssignments[staff.id], day, year, month);
                        if (weekWork >= (staff.maxDaysPerWeek || 3)) continue;
                    }

                    // この日の朝(420)・昼(600)・夕(1065)の不足状況を確認
                    const sundayFlag = isSunday(year, month, day);
                    let earlyScore = 0; // 早番が不足している度合い
                    let lateScore = 0;  // 遅番が不足している度合い
                    TIME_CHECKPOINTS.forEach(cp => {
                        const req = sundayFlag ? cp.sundayRequired : cp.required;
                        const count = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
                        if (count < req) {
                            if (cp.minutes === 420) earlyScore += (req - count) * 2; // 朝は重大
                            if (cp.minutes === 600) { earlyScore += (req - count); lateScore += (req - count); }
                            if (cp.minutes === 1065) lateScore += (req - count) * 2; // 夕方は重大
                        }
                    });

                    // どこかで不足があれば優先度高
                    changeCandidates.push({ day, earlyScore, lateScore, totalScore: earlyScore + lateScore });
                }

                // 優先度が高い日（不足が大きい日）から埋める
                changeCandidates.sort((a, b) => b.totalScore - a.totalScore);

                for (let i = 0; i < changeCandidates.length && currentOff > targetOff; i++) {
                    const c = changeCandidates[i];

                    if (canAssignEarly(staff) && canAssignLate(staff)) {
                        // 朝と夕方の不足度合いに合わせて割り当て
                        if (c.earlyScore >= c.lateScore) {
                            allAssignments[staff.id][c.day] = SHIFT_TYPES.EARLY;
                        } else {
                            allAssignments[staff.id][c.day] = SHIFT_TYPES.LATE;
                        }
                    } else if (canAssignEarly(staff)) {
                        allAssignments[staff.id][c.day] = SHIFT_TYPES.EARLY;
                    } else if (canAssignLate(staff)) {
                        allAssignments[staff.id][c.day] = SHIFT_TYPES.LATE;
                    } else {
                        continue; // 入れられない
                    }
                    currentOff--;
                }
            }
        });
    }

    // 最終チェック：公休数の警告
    staffList.forEach(staff => {
        const targetOff = staff.monthlyDaysOff || 9;
        const finalOff = countOffDays(allAssignments[staff.id], daysInMonth);
        if (finalOff !== targetOff) {
            warnings.push(`${staff.name}さん：公休が${finalOff}日です（目標${targetOff}日）`);
        }
    });

    // ===== フェーズ6: 時間帯別の人数チェック =====
    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);
        TIME_CHECKPOINTS.forEach(cp => {
            const required = sunday ? cp.sundayRequired : cp.required;
            const count = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
            if (count < required) {
                warnings.push(`${month}月${day}日：${cp.label}の人数が${count}人です（必要${required}人）`);
            }
        });
    }

    // ===== フェーズ7: 最終バリデーション =====
    const validationWarnings = validateSchedule(staffList, allAssignments, year, month, s);
    warnings.push(...validationWarnings);

    return { assignments: allAssignments, warnings: warnings };
}

/**
 * シフト表のバリデーション
 */
function validateSchedule(staffList, allAssignments, year, month, settings) {
    const s = { ...DEFAULT_SETTINGS, ...settings };
    const daysInMonth = getDaysInMonth(year, month);
    const warnings = [];

    staffList.forEach(staff => {
        const assignments = allAssignments[staff.id];
        if (!assignments) return;
        const maxConsec = getStaffMaxConsecutive(staff, s);

        // 連勤チェック
        let consecutive = 0;
        for (let day = 1; day <= daysInMonth; day++) {
            const shift = assignments[day];
            if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
                consecutive++;
                if (consecutive > maxConsec) {
                    warnings.push(`${staff.name}さん：${day}日目で${consecutive}連勤（上限${maxConsec}日）`);
                }
            } else {
                consecutive = 0;
            }
        }

        // 夜勤チェック
        const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');
        for (let day = 1; day <= daysInMonth; day++) {
            if (assignments[day] === SHIFT_TYPES.NIGHT) {
                if (nightType === 'none' || staff.type === 'part') {
                    warnings.push(`${staff.name}さん：${day}日に夜勤が入っていますが、夜勤不可です`);
                }
                if (nightType === 'weekday' && isFriSatSun(year, month, day)) {
                    warnings.push(`${staff.name}さん：${day}日（金土日）に夜勤が入っていますが、平日のみOKです`);
                }
                if (day + 1 <= daysInMonth && assignments[day + 1] !== SHIFT_TYPES.NIGHT_OFF) {
                    warnings.push(`${staff.name}さん：${day}日の夜勤後、翌日が明けになっていません`);
                }
            }
        }

        // 通しチェック
        for (let day = 1; day <= daysInMonth; day++) {
            if (assignments[day] === SHIFT_TYPES.OVERTIME) {
                if (!staff.canOvertime || staff.type === 'part') {
                    warnings.push(`${staff.name}さん：${day}日に通し勤務が入っていますが、残業不可です`);
                }
            }
        }

        // 早出のみ / 遅出のみチェック
        if (staff.type === 'part' && staff.earlyOnly) {
            for (let day = 1; day <= daysInMonth; day++) {
                if (assignments[day] === SHIFT_TYPES.LATE || assignments[day] === SHIFT_TYPES.OVERTIME) {
                    warnings.push(`${staff.name}さん：${day}日に遅番が入っていますが、早出のみです`);
                }
            }
        }
        if (staff.type === 'part' && staff.lateOnly) {
            for (let day = 1; day <= daysInMonth; day++) {
                if (assignments[day] === SHIFT_TYPES.EARLY || assignments[day] === SHIFT_TYPES.OVERTIME) {
                    warnings.push(`${staff.name}さん：${day}日に早番が入っていますが、遅出のみです`);
                }
            }
        }
    });

    return warnings;
}

/**
 * 特定のセルを変更したときの警告を取得
 */
function getShiftChangeWarnings(staff, allAssignments, staffList, day, newShift, year, month, settings) {
    const s = { ...DEFAULT_SETTINGS, ...settings };
    const daysInMonth = getDaysInMonth(year, month);
    const warnings = [];
    const assignments = { ...allAssignments[staff.id] };
    assignments[day] = newShift;

    const maxConsec = getStaffMaxConsecutive(staff, s);
    let consecutive = 0;
    for (let d = 1; d <= daysInMonth; d++) {
        const shift = assignments[d];
        if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
            consecutive++;
            if (consecutive > maxConsec) {
                warnings.push(`${consecutive}連勤になります！（上限${maxConsec}日）`);
                break;
            }
        } else {
            consecutive = 0;
        }
    }

    if (newShift === SHIFT_TYPES.NIGHT) {
        const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');
        if (nightType === 'none') warnings.push(`${staff.name}さんは夜勤ができません`);
        if (nightType === 'weekday' && isFriSatSun(year, month, day)) warnings.push(`${staff.name}さんは金土日の夜勤ができません`);
        if (staff.type === 'part') warnings.push(`パートスタッフは夜勤に入れません`);
    }

    if (newShift === SHIFT_TYPES.EARLY && staff.type === 'part' && staff.lateOnly) {
        warnings.push(`${staff.name}さんは遅出のみです`);
    }
    if (newShift === SHIFT_TYPES.LATE && staff.type === 'part' && staff.earlyOnly) {
        warnings.push(`${staff.name}さんは早出のみです`);
    }

    if (newShift === SHIFT_TYPES.OVERTIME) {
        if (!staff.canOvertime) warnings.push(`${staff.name}さんは残業（通し）ができません`);
        if (staff.type === 'part') warnings.push(`パートスタッフは通し勤務に入れません`);
        if (staff.earlyOnly || staff.lateOnly) warnings.push(`${staff.name}さんは${staff.earlyOnly ? '早出' : '遅出'}のみです`);
    }

    return warnings;
}
