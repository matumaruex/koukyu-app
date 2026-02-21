// ===== 自動スケジュール生成アルゴリズム =====
// 介護施設の制約条件を考慮してシフトを自動配置する

/**
 * シフトの種類を定義
 */
const SHIFT_TYPES = {
    EARLY: 'early',       // 早番
    LATE: 'late',         // 遅番
    NIGHT: 'night',       // 夜勤
    NIGHT_OFF: 'nightOff', // 明け（夜勤翌日）
    OFF: 'off',           // 休み
    OVERTIME: 'overtime'  // 通し（早番→遅番の残業）
};

/**
 * シフトの表示名
 */
const SHIFT_LABELS = {
    [SHIFT_TYPES.EARLY]: '早',
    [SHIFT_TYPES.LATE]: '遅',
    [SHIFT_TYPES.NIGHT]: '夜',
    [SHIFT_TYPES.NIGHT_OFF]: '明',
    [SHIFT_TYPES.OFF]: '休',
    [SHIFT_TYPES.OVERTIME]: '通'
};

/**
 * デフォルトの設定値
 */
const DEFAULT_SETTINGS = {
    earlyRequired: 3,        // 平日の早番必要人数
    lateRequired: 3,         // 平日の遅番必要人数
    nightRequired: 1,        // 夜勤必要人数
    sundayEarlyRequired: 2,  // 日曜の早番必要人数
    sundayLateRequired: 2,   // 日曜の遅番必要人数
    sundayNightRequired: 1,  // 日曜の夜勤必要人数
    maxConsecutive: 3         // 最大連勤日数
};

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
 * 指定日にこのスタッフが勤務可能かチェック
 */
function canWorkOnDay(assignments, day, maxConsecutive) {
    // すでに割り当て済みならNG
    if (assignments[day]) return false;

    // 連勤チェック：この日を勤務にした場合、連勤が上限を超えないか
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;

    return true;
}

/**
 * 指定日にこのスタッフを夜勤に割り当て可能かチェック
 */
function canAssignNight(staff, assignments, day, daysInMonth, maxConsecutive) {
    // 夜勤不可のスタッフ
    if (!staff.canNightShift) return false;

    // パートは夜勤不可
    if (staff.type === 'part') return false;

    // すでに割り当て済み
    if (assignments[day]) return false;

    // 翌日（明け）と翌々日（休み）が確保できるか
    if (day + 1 <= daysInMonth && assignments[day + 1]) return false;
    if (day + 2 <= daysInMonth && assignments[day + 2]) return false;

    // 連勤チェック
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;

    // ソフト制約：3日連続日勤の後の夜勤は避けたい
    if (pastConsecutive >= 3) return false;

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
 * スタッフの勤務日数（夜勤は1日、明けは非勤務）を数える
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
 * スタッフの休日数（明けを含まない純粋な公休）を数える
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
    // その週（月曜〜日曜）の勤務日数を計算
    const date = new Date(year, month - 1, day);
    const dayOfWeek = date.getDay();
    // 週の開始（月曜）を計算
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
 * 配列をシャッフル（同条件のスタッフからランダムに選ぶため）
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
 * メインの自動生成関数
 * @param {Array} staffList - スタッフ一覧
 * @param {number} year - 年
 * @param {number} month - 月
 * @param {Object} requests - 希望休 { staffId: [日の配列] }
 * @param {Object} settings - 設定値
 * @returns {Object} { assignments: { staffId: { day: shiftType } }, warnings: [string] }
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

    // ===== フェーズ2: 夜勤を割り当て（最も制約が厳しい） =====
    const nightEligible = staffList.filter(st => st.canNightShift && st.type !== 'part');

    for (let day = 1; day <= daysInMonth; day++) {
        const required = isSunday(year, month, day) ? s.sundayNightRequired : s.nightRequired;

        for (let n = 0; n < required; n++) {
            // 夜勤可能なスタッフをフィルタリング
            const candidates = nightEligible.filter(st =>
                canAssignNight(st, allAssignments[st.id], day, daysInMonth, s.maxConsecutive)
            );

            if (candidates.length === 0) {
                warnings.push(`${month}月${day}日：夜勤に入れるスタッフが見つかりません`);
                continue;
            }

            // 夜勤回数が少ない人を優先（公平性）
            const scored = candidates.map(st => ({
                staff: st,
                nightCount: countShiftType(allAssignments[st.id], SHIFT_TYPES.NIGHT, daysInMonth),
                workDays: countWorkDays(allAssignments[st.id], daysInMonth)
            }));

            // 夜勤回数 → 総勤務日数 の順で少ない人を優先
            scored.sort((a, b) => {
                if (a.nightCount !== b.nightCount) return a.nightCount - b.nightCount;
                return a.workDays - b.workDays;
            });

            // 同順位がいたらシャッフル
            const minScore = scored[0].nightCount;
            const topCandidates = shuffleArray(scored.filter(s => s.nightCount === minScore));
            const chosen = topCandidates[0].staff;

            // 夜勤を割り当て
            allAssignments[chosen.id][day] = SHIFT_TYPES.NIGHT;
            // 翌日は「明け」
            if (day + 1 <= daysInMonth) {
                allAssignments[chosen.id][day + 1] = SHIFT_TYPES.NIGHT_OFF;
            }
            // 翌々日は「休み」
            if (day + 2 <= daysInMonth) {
                allAssignments[chosen.id][day + 2] = SHIFT_TYPES.OFF;
            }
        }
    }

    // ===== フェーズ3: 日勤（早番・遅番）を割り当て =====
    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);
        const earlyNeeded = sunday ? s.sundayEarlyRequired : s.earlyRequired;
        const lateNeeded = sunday ? s.sundayLateRequired : s.lateRequired;

        // この日に勤務可能な人を集める
        const available = staffList.filter(st => {
            if (allAssignments[st.id][day]) return false; // すでに割り当て済み

            // 連勤チェック
            if (!canWorkOnDay(allAssignments[st.id], day, s.maxConsecutive)) return false;

            // パートの週間上限チェック
            if (st.type === 'part') {
                const weekWork = getWeekWorkDays(allAssignments[st.id], day, year, month);
                if (weekWork >= (st.maxDaysPerWeek || 3)) return false;
            }

            return true;
        });

        // 勤務日数でソート（少ない人を優先して公平に）
        const sortedAvailable = shuffleArray(available).sort((a, b) => {
            const aWork = countWorkDays(allAssignments[a.id], daysInMonth);
            const bWork = countWorkDays(allAssignments[b.id], daysInMonth);
            return aWork - bWork;
        });

        // 早番・遅番のバランスを考慮して割り当て
        let earlyAssigned = 0;
        let lateAssigned = 0;
        const dayAvailable = [...sortedAvailable];

        // まず早番を割り当て
        for (let i = 0; i < dayAvailable.length && earlyAssigned < earlyNeeded; i++) {
            const st = dayAvailable[i];
            // パートは早番か遅番のみ（通しはNG）
            allAssignments[st.id][day] = SHIFT_TYPES.EARLY;
            earlyAssigned++;
            dayAvailable.splice(i, 1);
            i--;
        }

        // 次に遅番を割り当て
        for (let i = 0; i < dayAvailable.length && lateAssigned < lateNeeded; i++) {
            const st = dayAvailable[i];
            allAssignments[st.id][day] = SHIFT_TYPES.LATE;
            lateAssigned++;
            dayAvailable.splice(i, 1);
            i--;
        }

        // 人が足りない場合：早番の人を「通し」に変更（残業できる人のみ）
        if (lateAssigned < lateNeeded) {
            const shortage = lateNeeded - lateAssigned;
            // 早番に入っている人で残業可能な人を探す
            const overtimeCandidates = staffList.filter(st =>
                allAssignments[st.id][day] === SHIFT_TYPES.EARLY &&
                st.canOvertime &&
                st.type !== 'part'
            );

            const overtimeSorted = shuffleArray(overtimeCandidates).sort((a, b) => {
                const aOT = countShiftType(allAssignments[a.id], SHIFT_TYPES.OVERTIME, daysInMonth);
                const bOT = countShiftType(allAssignments[b.id], SHIFT_TYPES.OVERTIME, daysInMonth);
                return aOT - bOT;
            });

            for (let i = 0; i < overtimeSorted.length && i < shortage; i++) {
                allAssignments[overtimeSorted[i].id][day] = SHIFT_TYPES.OVERTIME;
                lateAssigned++;
            }

            if (lateAssigned < lateNeeded) {
                warnings.push(`${month}月${day}日：遅番が${lateNeeded - lateAssigned}人不足しています`);
            }
        }

        if (earlyAssigned < earlyNeeded) {
            warnings.push(`${month}月${day}日：早番が${earlyNeeded - earlyAssigned}人不足しています`);
        }
    }

    // ===== フェーズ4: 残りの未割り当て日を「休み」にする =====
    staffList.forEach(staff => {
        for (let day = 1; day <= daysInMonth; day++) {
            if (!allAssignments[staff.id][day]) {
                allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
            }
        }
    });

    // ===== フェーズ5: 公休日数の調整 =====
    staffList.forEach(staff => {
        const targetOff = staff.monthlyDaysOff || 9;
        const currentOff = countOffDays(allAssignments[staff.id], daysInMonth);

        if (Math.abs(currentOff - targetOff) > 2) {
            warnings.push(`${staff.name}さん：公休が${currentOff}日です（目標${targetOff}日）`);
        }
    });

    // ===== フェーズ6: 最終バリデーション =====
    const validationWarnings = validateSchedule(staffList, allAssignments, year, month, s);
    warnings.push(...validationWarnings);

    return {
        assignments: allAssignments,
        warnings: warnings
    };
}

/**
 * シフト表のバリデーション（ルール違反をチェック）
 */
function validateSchedule(staffList, allAssignments, year, month, settings) {
    const s = { ...DEFAULT_SETTINGS, ...settings };
    const daysInMonth = getDaysInMonth(year, month);
    const warnings = [];

    staffList.forEach(staff => {
        const assignments = allAssignments[staff.id];
        if (!assignments) return;

        // 連勤チェック
        let consecutive = 0;
        for (let day = 1; day <= daysInMonth; day++) {
            const shift = assignments[day];
            if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
                consecutive++;
                if (consecutive > s.maxConsecutive) {
                    warnings.push(`${staff.name}さん：${day}日目で${consecutive}連勤になっています`);
                }
            } else {
                consecutive = 0;
            }
        }

        // 夜勤のルールチェック
        for (let day = 1; day <= daysInMonth; day++) {
            if (assignments[day] === SHIFT_TYPES.NIGHT) {
                // 夜勤不可のスタッフに夜勤が入っていないか
                if (!staff.canNightShift || staff.type === 'part') {
                    warnings.push(`${staff.name}さん：${day}日に夜勤が入っていますが、夜勤不可です`);
                }
                // 翌日が明けになっているか
                if (day + 1 <= daysInMonth && assignments[day + 1] !== SHIFT_TYPES.NIGHT_OFF) {
                    warnings.push(`${staff.name}さん：${day}日の夜勤後、翌日が明けになっていません`);
                }
            }
        }

        // 通し勤務のチェック
        for (let day = 1; day <= daysInMonth; day++) {
            if (assignments[day] === SHIFT_TYPES.OVERTIME) {
                if (!staff.canOvertime || staff.type === 'part') {
                    warnings.push(`${staff.name}さん：${day}日に通し勤務が入っていますが、残業不可です`);
                }
            }
        }
    });

    // 各日の必要人数チェック
    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);
        let earlyCount = 0;
        let lateCount = 0;
        let nightCount = 0;

        staffList.forEach(staff => {
            const shift = allAssignments[staff.id]?.[day];
            if (shift === SHIFT_TYPES.EARLY) earlyCount++;
            if (shift === SHIFT_TYPES.LATE) lateCount++;
            if (shift === SHIFT_TYPES.OVERTIME) { earlyCount++; lateCount++; }
            if (shift === SHIFT_TYPES.NIGHT) nightCount++;
        });

        const earlyNeeded = sunday ? s.sundayEarlyRequired : s.earlyRequired;
        const lateNeeded = sunday ? s.sundayLateRequired : s.lateRequired;
        const nightNeeded = sunday ? s.sundayNightRequired : s.nightRequired;

        if (earlyCount < earlyNeeded) {
            // 重複警告を避ける（生成時にすでに出してる可能性あり）
        }
    }

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

    // 変更を仮適用
    assignments[day] = newShift;

    // 連勤チェック
    let consecutive = 0;
    for (let d = 1; d <= daysInMonth; d++) {
        const shift = assignments[d];
        if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
            consecutive++;
            if (consecutive > s.maxConsecutive) {
                warnings.push(`${consecutive}連勤になります！（上限${s.maxConsecutive}日）`);
                break;
            }
        } else {
            consecutive = 0;
        }
    }

    // 夜勤チェック
    if (newShift === SHIFT_TYPES.NIGHT) {
        if (!staff.canNightShift) {
            warnings.push(`${staff.name}さんは夜勤ができません`);
        }
        if (staff.type === 'part') {
            warnings.push(`パートスタッフは夜勤に入れません`);
        }
    }

    // 通しチェック
    if (newShift === SHIFT_TYPES.OVERTIME) {
        if (!staff.canOvertime) {
            warnings.push(`${staff.name}さんは残業（通し）ができません`);
        }
        if (staff.type === 'part') {
            warnings.push(`パートスタッフは通し勤務に入れません`);
        }
    }

    return warnings;
}
