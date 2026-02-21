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
    OVERTIME: 'overtime', // 通し（早残）→ 表示「A残」
    PART: 'part'          // パート（個別時間）→ 表示「P」
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
    [SHIFT_TYPES.OVERTIME]: 'A残',
    [SHIFT_TYPES.PART]: 'P'
};

/**
 * フルタイムのシフト時間（固定）
 * 時刻は分単位に変換して判定に使う
 */
const SHIFT_TIME_RANGES = {
    [SHIFT_TYPES.EARLY]: { start: 420, end: 960 },       // 7:00〜16:00
    [SHIFT_TYPES.LATE]: { start: 570, end: 1110 },       // 9:30〜18:30
    [SHIFT_TYPES.OVERTIME]: { start: 420, end: 1110 },   // 7:00〜18:30
    [SHIFT_TYPES.NIGHT]: { start: 1020, end: 1440 },     // 夜勤入り 17:00〜（夕方にいる人としてカウント）
    [SHIFT_TYPES.NIGHT_OFF]: { start: 0, end: 540 },     // 明け 〜9:00（朝にいる人としてカウント）
    // Pシフトの時間は動的（スタッフの設定による）なのでここには静的に持たない
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
    [SHIFT_TYPES.OFF]: '休み',
    [SHIFT_TYPES.PART]: '設定時間'
};

/**
 * 時間帯チェック：必要人数を確認する時刻（分単位）
 */
const TIME_CHECKPOINTS = [
    { label: '朝(7:00)', minutes: 420, required: 4, sundayRequired: 4 },
    { label: '昼(10:00)', minutes: 600, required: 4, sundayRequired: 4 },
    { label: '夕(17:45)', minutes: 1065, required: 4, sundayRequired: 4 }
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

    // パート個別のPシフトの場合：設定された自身の勤務時間で判定
    if (shift === SHIFT_TYPES.PART && staff.startTime && staff.endTime) {
        const start = timeToMinutes(staff.startTime);
        const end = timeToMinutes(staff.endTime);
        if (start !== null && end !== null) {
            return checkMinutes >= start && checkMinutes < end;
        }
    }

    // フルタイムなどの固定シフト時間で判定
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
 * スタッフの連勤日数を計算（指定日を含む過去方向の連続勤務日数）
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
 * スタッフの連勤日数を計算（指定日を含む未来方向の連続勤務日数）
 * 夜勤が先に配置されている場合などに、前方の連勤を正確に把握する
 */
function getForwardConsecutiveWorkDays(assignments, day) {
    let count = 0;
    for (let d = day; ; d++) {
        const shift = assignments[d];
        if (!shift) break; // 月の範囲外
        if (shift === SHIFT_TYPES.OFF || shift === SHIFT_TYPES.NIGHT_OFF) break;
        count++;
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
 * 過去方向 + 未来方向の両方の連勤をチェックする
 */
function canWorkOnDay(staff, assignments, day, settings) {
    const shift = assignments[day];
    if (shift && shift !== SHIFT_TYPES.OFF) return false;
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;
    // ★前方向チェック: この日に出勤を入れた場合、未来の既存シフトと合わせて連勤超過しないか
    const forwardConsecutive = getForwardConsecutiveWorkDays(assignments, day + 1);
    if (pastConsecutive + 1 + forwardConsecutive > maxConsecutive) return false;
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
    const shift1 = assignments[day];
    if (shift1 && shift1 !== SHIFT_TYPES.OFF) return false;
    if (day + 1 <= daysInMonth) {
        const shift2 = assignments[day + 1];
        if (shift2 && shift2 !== SHIFT_TYPES.OFF) return false;
    }
    if (day + 2 <= daysInMonth) {
        const shift3 = assignments[day + 2];
        if (shift3 && shift3 !== SHIFT_TYPES.OFF) return false;
    }
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;
    // ★前方向チェック: 夜勤の翌日はnightOff(連勤から除外)なので、day+2以降を確認
    const forwardConsecutive = getForwardConsecutiveWorkDays(assignments, day + 2);
    if (pastConsecutive + 1 + forwardConsecutive > maxConsecutive) return false;
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

    // ===== フェーズ0: 白紙スタート（全日OFF） =====
    const allAssignments = {};
    staffList.forEach(staff => {
        allAssignments[staff.id] = {};
        for (let day = 1; day <= daysInMonth; day++) {
            allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
        }
    });

    // 希望休をSetに保存（後の判定用）
    const requestedDays = {};
    staffList.forEach(staff => {
        requestedDays[staff.id] = new Set(requests[staff.id] || []);
    });

    // ===== フェーズ1: 希望休（全日OFFなので記録のみ） =====

    // ===== フェーズ2: 夜勤と明けを配置 =====
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
            const topCandidates = shuffleArray(scored.filter(c => c.nightCount === minScore));
            const chosen = topCandidates[0].staff;

            allAssignments[chosen.id][day] = SHIFT_TYPES.NIGHT;
            if (day + 1 <= daysInMonth) {
                allAssignments[chosen.id][day + 1] = SHIFT_TYPES.NIGHT_OFF;
            }
        }
    }

    // 目標出勤日数（夜勤明けの日数を控除して正確に計算）
    const getActualTarget = (staff) => {
        const offDays = (staff.monthlyDaysOff || 9);
        const nightOffs = countShiftType(allAssignments[staff.id], SHIFT_TYPES.NIGHT_OFF, daysInMonth);
        return daysInMonth - offDays - nightOffs;
    };

    // 出勤目標との差（正:まだ足りない / 0以下:達成済み）
    const getWorkGap = (st) => {
        return getActualTarget(st) - countWorkDays(allAssignments[st.id], daysInMonth);
    };

    // ===== フェーズ3: パートPシフト配置 =====
    const partStaff = staffList.filter(st => st.type === 'part');
    partStaff.forEach(staff => {
        const targetWorkDays = getActualTarget(staff);
        const maxPerWeek = staff.maxDaysPerWeek || 3;

        if (!staff.startTime) staff.startTime = '09:00';
        if (!staff.endTime) staff.endTime = '17:00';

        // パス①: 順番に貪欲に埋める（Work,Work,OFFパターンを自然に作る）
        // ランダムな開始日で多様性を確保
        const startDay = Math.floor(Math.random() * daysInMonth) + 1;
        let currentWork = countWorkDays(allAssignments[staff.id], daysInMonth);

        for (let offset = 0; offset < daysInMonth && currentWork < targetWorkDays; offset++) {
            const day = ((startDay - 1 + offset) % daysInMonth) + 1;
            if (requestedDays[staff.id].has(day)) continue;
            if (allAssignments[staff.id][day] !== SHIFT_TYPES.OFF) continue;
            if (getWeekWorkDays(allAssignments[staff.id], day, year, month) >= maxPerWeek) continue;
            if (!canWorkOnDay(staff, allAssignments[staff.id], day, s)) continue;

            allAssignments[staff.id][day] = SHIFT_TYPES.PART;
            currentWork++;
        }

        // パス2②: まだ足りなければ逆方向からも埋める
        if (currentWork < targetWorkDays) {
            for (let d = daysInMonth; d >= 1 && currentWork < targetWorkDays; d--) {
                if (requestedDays[staff.id].has(d)) continue;
                if (allAssignments[staff.id][d] !== SHIFT_TYPES.OFF) continue;
                if (getWeekWorkDays(allAssignments[staff.id], d, year, month) >= maxPerWeek) continue;
                if (!canWorkOnDay(staff, allAssignments[staff.id], d, s)) continue;

                allAssignments[staff.id][d] = SHIFT_TYPES.PART;
                currentWork++;
            }
        }
    });

    // ===== フェーズ4: フルタイム日勤の最適配置（全面新設） =====
    const fullStaff = staffList.filter(st => st.type !== 'part');

    // その日に出勤可能なフルタイムスタッフを取得
    const getAvailableFull = (day) => {
        return fullStaff.filter(st => {
            if (allAssignments[st.id][day] !== SHIFT_TYPES.OFF) return false;
            if (!canWorkOnDay(st, allAssignments[st.id], day, s)) return false;
            if (requestedDays[st.id].has(day)) return false;
            return true;
        });
    };

    // ソフトリミット付きソート：目標未達の人を優先するが、全員達成済みでも候補に含める
    const sortSoft = (list) => {
        return shuffleArray(list).sort((a, b) => {
            const aGap = getWorkGap(a);
            const bGap = getWorkGap(b);
            if (aGap > 0 && bGap <= 0) return -1;
            if (aGap <= 0 && bGap > 0) return 1;
            return bGap - aGap;
        });
    };

    // A残ソート：回数が少ない人を優先、同回数なら出勤ギャップが大きい人を優先
    const sortForOT = (list) => {
        return shuffleArray(list).sort((a, b) => {
            const aOt = countShiftType(allAssignments[a.id], SHIFT_TYPES.OVERTIME, daysInMonth);
            const bOt = countShiftType(allAssignments[b.id], SHIFT_TYPES.OVERTIME, daysInMonth);
            if (aOt !== bOt) return aOt - bOt;
            return getWorkGap(b) - getWorkGap(a);
        });
    };

    // 1日→31日の正順ループ
    for (let day = 1; day <= daysInMonth; day++) {
        // ステップ1: 現在のカバー状況（夜勤・明け・パートから）
        let morn = countStaffAtTime(staffList, allAssignments, day, 420);
        let noon = countStaffAtTime(staffList, allAssignments, day, 600);
        let eve = countStaffAtTime(staffList, allAssignments, day, 1065);

        let mNeed = Math.max(0, 4 - morn);
        let nNeed = Math.max(0, 4 - noon);
        let eNeed = Math.max(0, 4 - eve);

        // ステップ2: A残（通し）を戦略的に使う
        // 朝と夕の両方が足りない場合、かつA残4回未満の人がいるなら1人で両方カバー
        const TARGET_OT = 4; // A残の目標回数（これ未満なら積極利用、以上なら最後の手段）
        const otWant = Math.min(mNeed, eNeed);
        if (otWant > 0) {
            // A残回数が少ない人（4回未満）のみ候補にする
            const otCands = sortForOT(
                getAvailableFull(day).filter(st => {
                    if (!st.canOvertime) return false;
                    const otCount = countShiftType(allAssignments[st.id], SHIFT_TYPES.OVERTIME, daysInMonth);
                    return otCount < TARGET_OT; // 4回未満のみ
                })
            );
            let assigned = 0;
            for (let i = 0; i < otCands.length && assigned < otWant; i++) {
                allAssignments[otCands[i].id][day] = SHIFT_TYPES.OVERTIME;
                assigned++;
            }
            // 再カウント
            morn = countStaffAtTime(staffList, allAssignments, day, 420);
            noon = countStaffAtTime(staffList, allAssignments, day, 600);
            eve = countStaffAtTime(staffList, allAssignments, day, 1065);
            mNeed = Math.max(0, 4 - morn);
            nNeed = Math.max(0, 4 - noon);
            eNeed = Math.max(0, 4 - eve);
        }

        // ステップ3: 早番(A)で朝を埋める
        if (mNeed > 0) {
            const cands = sortSoft(getAvailableFull(day));
            let assigned = 0;
            for (let i = 0; i < cands.length && assigned < mNeed; i++) {
                allAssignments[cands[i].id][day] = SHIFT_TYPES.EARLY;
                assigned++;
            }
            morn = countStaffAtTime(staffList, allAssignments, day, 420);
            noon = countStaffAtTime(staffList, allAssignments, day, 600);
            mNeed = Math.max(0, 4 - morn);
            nNeed = Math.max(0, 4 - noon);
        }

        // ステップ4: 遅番(B)で夕方を埋める
        if (eNeed > 0) {
            const cands = sortSoft(getAvailableFull(day));
            let assigned = 0;
            for (let i = 0; i < cands.length && assigned < eNeed; i++) {
                allAssignments[cands[i].id][day] = SHIFT_TYPES.LATE;
                assigned++;
            }
            eve = countStaffAtTime(staffList, allAssignments, day, 1065);
            noon = countStaffAtTime(staffList, allAssignments, day, 600);
            eNeed = Math.max(0, 4 - eve);
            nNeed = Math.max(0, 4 - noon);
        }

        // ステップ5: 昼がまだ足りない場合
        if (nNeed > 0) {
            const cands = sortSoft(getAvailableFull(day));
            for (let i = 0; i < cands.length && nNeed > 0; i++) {
                const shift = (morn <= eve) ? SHIFT_TYPES.EARLY : SHIFT_TYPES.LATE;
                allAssignments[cands[i].id][day] = shift;
                noon = countStaffAtTime(staffList, allAssignments, day, 600);
                morn = countStaffAtTime(staffList, allAssignments, day, 420);
                eve = countStaffAtTime(staffList, allAssignments, day, 1065);
                nNeed = Math.max(0, 4 - noon);
            }
        }

        // ステップ6: A残フォールバック — 上記で足りない場合のみ（5回目以降も許容）
        // 夕方不足 → 早番の人をA残にアップグレード
        eve = countStaffAtTime(staffList, allAssignments, day, 1065);
        if (eve < 4) {
            const upgradable = fullStaff.filter(st =>
                allAssignments[st.id][day] === SHIFT_TYPES.EARLY && st.canOvertime
            );
            const sorted = sortForOT(upgradable);
            for (let i = 0; i < sorted.length && eve < 4; i++) {
                allAssignments[sorted[i].id][day] = SHIFT_TYPES.OVERTIME;
                eve = countStaffAtTime(staffList, allAssignments, day, 1065);
            }
        }

        // 朝不足 → 遅番の人をA残にアップグレード
        morn = countStaffAtTime(staffList, allAssignments, day, 420);
        if (morn < 4) {
            const upgradable = fullStaff.filter(st =>
                allAssignments[st.id][day] === SHIFT_TYPES.LATE && st.canOvertime
            );
            const sorted = sortForOT(upgradable);
            for (let i = 0; i < sorted.length && morn < 4; i++) {
                allAssignments[sorted[i].id][day] = SHIFT_TYPES.OVERTIME;
                morn = countStaffAtTime(staffList, allAssignments, day, 420);
            }
        }

        // ステップ7: 最終人数の警告
        morn = countStaffAtTime(staffList, allAssignments, day, 420);
        noon = countStaffAtTime(staffList, allAssignments, day, 600);
        eve = countStaffAtTime(staffList, allAssignments, day, 1065);
        if (morn < 4) warnings.push(`${month}月${day}日：朝(7:00)の人数が${morn}人です（必要4人）`);
        if (noon < 4) warnings.push(`${month}月${day}日：昼(10:00)の人数が${noon}人です（必要4人）`);
        if (eve < 4) warnings.push(`${month}月${day}日：夕(17:45)の人数が${eve}人です（必要4人）`);
    }

    // ===== フェーズ5: 出勤目標に未達のスタッフの追加出勤 =====
    // 手薄な日に優先的に配置し、チェックポイントの弱い時間帯をカバーするシフトを選ぶ
    fullStaff.forEach(st => {
        let gap = getWorkGap(st);
        while (gap > 0) {
            // 出勤可能な日の中で、全体の出勤人数が最も少ない日を探す
            let tiedDays = [];
            let bestCount = Infinity;
            for (let d = 1; d <= daysInMonth; d++) {
                if (allAssignments[st.id][d] !== SHIFT_TYPES.OFF) continue;
                if (requestedDays[st.id].has(d)) continue;
                if (!canWorkOnDay(st, allAssignments[st.id], d, s)) continue;

                let dayTotal = 0;
                staffList.forEach(other => {
                    const shift = allAssignments[other.id][d];
                    if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) dayTotal++;
                });

                if (dayTotal < bestCount) {
                    bestCount = dayTotal;
                    tiedDays = [d];
                } else if (dayTotal === bestCount) {
                    tiedDays.push(d);
                }
            }

            if (tiedDays.length === 0) break;
            const chosenDay = tiedDays[Math.floor(Math.random() * tiedDays.length)];

            // どの時間帯が最も手薄かを見てシフトを決める
            const mc = countStaffAtTime(staffList, allAssignments, chosenDay, 420);
            const nc = countStaffAtTime(staffList, allAssignments, chosenDay, 600);
            const ec = countStaffAtTime(staffList, allAssignments, chosenDay, 1065);

            let shift;
            if (ec <= mc && ec <= nc) {
                shift = SHIFT_TYPES.LATE;   // 夕方が最も手薄 → 遅番
            } else if (mc <= nc) {
                shift = SHIFT_TYPES.EARLY;  // 朝が最も手薄 → 早番
            } else {
                // 昼が手薄 → 朝と夕のうち少ない方のシフトを選ぶ
                shift = (mc <= ec) ? SHIFT_TYPES.EARLY : SHIFT_TYPES.LATE;
            }

            allAssignments[st.id][chosenDay] = shift;
            gap = getWorkGap(st);
        }
    });

    // 公休数の警告
    staffList.forEach(staff => {
        const targetOff = staff.monthlyDaysOff || 9;
        const finalOff = countOffDays(allAssignments[staff.id], daysInMonth);
        if (finalOff !== targetOff) {
            warnings.push(`${staff.name}さん：公休が${finalOff}日です（目標${targetOff}日）`);
        }
    });

    // ===== フェーズ6: 時間帯別の人数チェック（最終確認） =====
    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);
        TIME_CHECKPOINTS.forEach(cp => {
            const required = sunday ? cp.sundayRequired : cp.required;
            const count = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
            if (count < required) {
                const msg = `${month}月${day}日：${cp.label}の人数が${count}人です（必要${required}人）`;
                if (!warnings.includes(msg)) warnings.push(msg);
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
