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
    return dow === 0 || dow === 5 || dow === 6; // 日=0, 金=5, 土=6
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
 * - 夜勤ありフルタイム → 2日まで
 * - スタッフに個人設定がある場合 → その値を使用
 * - それ以外 → デフォルト設定値
 */
function getStaffMaxConsecutive(staff, settings) {
    // スタッフに個別の連勤制限がある場合はそれを優先
    if (staff.maxConsecutive && staff.maxConsecutive > 0) {
        return staff.maxConsecutive;
    }

    // 夜勤ありのフルタイムは日勤2連勤まで
    if (staff.type !== 'part' && staff.nightShiftType && staff.nightShiftType !== 'none') {
        return 2;
    }

    return settings.maxConsecutive || DEFAULT_SETTINGS.maxConsecutive;
}

/**
 * 指定日にこのスタッフが勤務可能かチェック
 */
function canWorkOnDay(staff, assignments, day, settings) {
    // すでに割り当て済みならNG
    if (assignments[day]) return false;

    // スタッフごとの連勤上限
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);

    // 連勤チェック：この日を勤務にした場合、連勤が上限を超えないか
    const pastConsecutive = getConsecutiveWorkDays(assignments, day - 1);
    if (pastConsecutive >= maxConsecutive) return false;

    return true;
}

/**
 * 指定日にこのスタッフを夜勤に割り当て可能かチェック
 */
function canAssignNight(staff, assignments, day, daysInMonth, settings, year, month) {
    // 夜勤設定を取得（後方互換性：古い canNightShift を変換）
    const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');

    // 夜勤不可のスタッフ
    if (nightType === 'none') return false;

    // パートは夜勤不可
    if (staff.type === 'part') return false;

    // 「平日のみOK」の人で、金土日の場合はNG
    if (nightType === 'weekday' && isFriSatSun(year, month, day)) return false;

    // すでに割り当て済み
    if (assignments[day]) return false;

    // 翌日（明け）と翌々日（休み）が確保できるか
    if (day + 1 <= daysInMonth && assignments[day + 1]) return false;
    if (day + 2 <= daysInMonth && assignments[day + 2]) return false;

    // スタッフごとの連勤上限
    const maxConsecutive = getStaffMaxConsecutive(staff, settings);

    // 連勤チェック
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
 * スタッフの目標勤務日数を計算（月の日数 - 公休日数 - 夜勤明けの日数を考慮）
 */
function getTargetWorkDays(staff, daysInMonth) {
    return daysInMonth - (staff.monthlyDaysOff || 9);
}

/**
 * スタッフが早番に入れるかどうか
 */
function canAssignEarly(staff) {
    // 遅出のみのパートは早番NG
    if (staff.type === 'part' && staff.lateOnly) return false;
    return true;
}

/**
 * スタッフが遅番に入れるかどうか
 */
function canAssignLate(staff) {
    // 早出のみのパートは遅番NG
    if (staff.type === 'part' && staff.earlyOnly) return false;
    return true;
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
    const nightEligible = staffList.filter(st => {
        const nightType = st.nightShiftType || (st.canNightShift ? 'all' : 'none');
        return nightType !== 'none' && st.type !== 'part';
    });

    for (let day = 1; day <= daysInMonth; day++) {
        const required = isSunday(year, month, day) ? s.sundayNightRequired : s.nightRequired;

        for (let n = 0; n < required; n++) {
            // 夜勤可能なスタッフをフィルタリング
            const candidates = nightEligible.filter(st =>
                canAssignNight(st, allAssignments[st.id], day, daysInMonth, s, year, month)
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

            // スタッフごとの連勤チェック
            if (!canWorkOnDay(st, allAssignments[st.id], day, s)) return false;

            // パートの週間上限チェック
            if (st.type === 'part') {
                const weekWork = getWeekWorkDays(allAssignments[st.id], day, year, month);
                if (weekWork >= (st.maxDaysPerWeek || 3)) return false;
            }

            return true;
        });

        // ===== 公平な早番・遅番割り当て =====
        // 目標勤務日数との差、早番/遅番のバランスを考慮してソート

        // 早番専用（早出のみ）、遅番専用（遅出のみ）、両方可能を分ける
        const earlyOnlyStaff = available.filter(st => st.type === 'part' && st.earlyOnly);
        const lateOnlyStaff = available.filter(st => st.type === 'part' && st.lateOnly);
        const flexStaff = available.filter(st => {
            if (st.type === 'part' && st.earlyOnly) return false;
            if (st.type === 'part' && st.lateOnly) return false;
            return true;
        });

        let earlyAssigned = 0;
        let lateAssigned = 0;

        // (1) 早出のみのパートを早番に割り当て
        for (let i = 0; i < earlyOnlyStaff.length && earlyAssigned < earlyNeeded; i++) {
            allAssignments[earlyOnlyStaff[i].id][day] = SHIFT_TYPES.EARLY;
            earlyAssigned++;
        }

        // (2) 遅出のみのパートを遅番に割り当て
        for (let i = 0; i < lateOnlyStaff.length && lateAssigned < lateNeeded; i++) {
            allAssignments[lateOnlyStaff[i].id][day] = SHIFT_TYPES.LATE;
            lateAssigned++;
        }

        // (3) 両方可能なスタッフを早番/遅番のバランスを見ながら割り当て
        // 早番回数が少ない人 → 早番、遅番回数が少ない人 → 遅番
        const flexSorted = shuffleArray(flexStaff);

        // 早番と遅番を交互にバランスよく割り当て
        // まず目標勤務日数に対する余裕度でソート
        flexSorted.sort((a, b) => {
            const aWork = countWorkDays(allAssignments[a.id], daysInMonth);
            const bWork = countWorkDays(allAssignments[b.id], daysInMonth);
            const aTarget = getTargetWorkDays(a, daysInMonth);
            const bTarget = getTargetWorkDays(b, daysInMonth);
            // 目標に対して余裕がない人を優先
            return (aWork - aTarget) - (bWork - bTarget);
        });

        const earlyRemaining = earlyNeeded - earlyAssigned;
        const lateRemaining = lateNeeded - lateAssigned;

        // 早番用と遅番用に分けて割り当て
        // 各スタッフの早番/遅番の回数バランスを見て、少ない方に割り当てる
        const usedIds = new Set();

        // 早番を埋める（早番回数が少ない順に）
        const earlyCandidates = flexSorted
            .filter(st => canAssignEarly(st))
            .sort((a, b) => {
                const aEarly = countShiftType(allAssignments[a.id], SHIFT_TYPES.EARLY, daysInMonth);
                const bEarly = countShiftType(allAssignments[b.id], SHIFT_TYPES.EARLY, daysInMonth);
                const aLate = countShiftType(allAssignments[a.id], SHIFT_TYPES.LATE, daysInMonth);
                const bLate = countShiftType(allAssignments[b.id], SHIFT_TYPES.LATE, daysInMonth);
                // 早番が少ない人、かつ早番と遅番の差が大きい人を優先
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

        // 遅番を埋める（遅番回数が少ない順に）
        const lateCandidates = flexSorted
            .filter(st => canAssignLate(st) && !usedIds.has(st.id))
            .sort((a, b) => {
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
    // 目標より公休が少なすぎる場合、勤務日を休みに変更
    staffList.forEach(staff => {
        const targetOff = staff.monthlyDaysOff || 9;
        let currentOff = countOffDays(allAssignments[staff.id], daysInMonth);

        // 公休が足りない場合 → 勤務日を休みに変換
        if (currentOff < targetOff) {
            const shortage = targetOff - currentOff;
            // 変更候補：早番・遅番の日で、他の日勤スタッフが十分いる日
            const changeCandidates = [];

            for (let day = 1; day <= daysInMonth; day++) {
                const shift = allAssignments[staff.id][day];
                if (shift !== SHIFT_TYPES.EARLY && shift !== SHIFT_TYPES.LATE) continue;

                // その日の同シフトの人数を数える
                let sameshiftCount = 0;
                staffList.forEach(other => {
                    if (other.id === staff.id) return;
                    const otherShift = allAssignments[other.id][day];
                    if (shift === SHIFT_TYPES.EARLY && (otherShift === SHIFT_TYPES.EARLY || otherShift === SHIFT_TYPES.OVERTIME)) {
                        sameshiftCount++;
                    }
                    if (shift === SHIFT_TYPES.LATE && (otherShift === SHIFT_TYPES.LATE || otherShift === SHIFT_TYPES.OVERTIME)) {
                        sameshiftCount++;
                    }
                });

                const sunday = isSunday(year, month, day);
                const required = shift === SHIFT_TYPES.EARLY
                    ? (sunday ? s.sundayEarlyRequired : s.earlyRequired)
                    : (sunday ? s.sundayLateRequired : s.lateRequired);

                // 必要人数を上回っている場合のみ変更候補
                if (sameshiftCount >= required) {
                    changeCandidates.push({ day, surplus: sameshiftCount - required });
                }
            }

            // 余裕がある日から優先的に休みに変更
            changeCandidates.sort((a, b) => b.surplus - a.surplus);

            for (let i = 0; i < changeCandidates.length && currentOff < targetOff; i++) {
                allAssignments[staff.id][changeCandidates[i].day] = SHIFT_TYPES.OFF;
                currentOff++;
            }
        }

        // 公休が多すぎる場合 → 休みを勤務日に変換
        if (currentOff > targetOff + 1) {
            const excess = currentOff - targetOff;
            const changeCandidates = [];

            for (let day = 1; day <= daysInMonth; day++) {
                if (allAssignments[staff.id][day] !== SHIFT_TYPES.OFF) continue;
                // 希望休は変更しない
                const staffRequests = requests[staff.id] || [];
                if (staffRequests.includes(day)) continue;
                // 連勤チェック
                if (!canWorkOnDay(staff, allAssignments[staff.id], day, s)) continue;

                changeCandidates.push(day);
            }

            for (let i = 0; i < changeCandidates.length && currentOff > targetOff; i++) {
                const day = changeCandidates[i];
                // 早番と遅番のバランスを見て割り当て
                const earlyCount = countShiftType(allAssignments[staff.id], SHIFT_TYPES.EARLY, daysInMonth);
                const lateCount = countShiftType(allAssignments[staff.id], SHIFT_TYPES.LATE, daysInMonth);

                if (canAssignEarly(staff) && (earlyCount <= lateCount || !canAssignLate(staff))) {
                    allAssignments[staff.id][day] = SHIFT_TYPES.EARLY;
                } else if (canAssignLate(staff)) {
                    allAssignments[staff.id][day] = SHIFT_TYPES.LATE;
                } else {
                    allAssignments[staff.id][day] = SHIFT_TYPES.EARLY;
                }
                currentOff--;
            }
        }

        // 最終チェック
        const finalOff = countOffDays(allAssignments[staff.id], daysInMonth);
        if (Math.abs(finalOff - targetOff) > 1) {
            warnings.push(`${staff.name}さん：公休が${finalOff}日です（目標${targetOff}日）`);
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

        // スタッフごとの連勤上限
        const maxConsec = getStaffMaxConsecutive(staff, s);

        // 連勤チェック
        let consecutive = 0;
        for (let day = 1; day <= daysInMonth; day++) {
            const shift = assignments[day];
            if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) {
                consecutive++;
                if (consecutive > maxConsec) {
                    warnings.push(`${staff.name}さん：${day}日目で${consecutive}連勤になっています（上限${maxConsec}日）`);
                }
            } else {
                consecutive = 0;
            }
        }

        // 夜勤のルールチェック
        const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');

        for (let day = 1; day <= daysInMonth; day++) {
            if (assignments[day] === SHIFT_TYPES.NIGHT) {
                // 夜勤不可のスタッフに夜勤が入っていないか
                if (nightType === 'none' || staff.type === 'part') {
                    warnings.push(`${staff.name}さん：${day}日に夜勤が入っていますが、夜勤不可です`);
                }
                // 平日のみOKの人が金土日に入っていないか
                if (nightType === 'weekday' && isFriSatSun(year, month, day)) {
                    warnings.push(`${staff.name}さん：${day}日（金土日）に夜勤が入っていますが、平日のみOKです`);
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

        // 早出のみのパートが遅番に入っていないかチェック
        if (staff.type === 'part' && staff.earlyOnly) {
            for (let day = 1; day <= daysInMonth; day++) {
                if (assignments[day] === SHIFT_TYPES.LATE || assignments[day] === SHIFT_TYPES.OVERTIME) {
                    warnings.push(`${staff.name}さん：${day}日に遅番/通しが入っていますが、早出のみです`);
                }
            }
        }

        // 遅出のみのパートが早番に入っていないかチェック
        if (staff.type === 'part' && staff.lateOnly) {
            for (let day = 1; day <= daysInMonth; day++) {
                if (assignments[day] === SHIFT_TYPES.EARLY || assignments[day] === SHIFT_TYPES.OVERTIME) {
                    warnings.push(`${staff.name}さん：${day}日に早番/通しが入っていますが、遅出のみです`);
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
            // 重複警告を避ける
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

    // スタッフごとの連勤上限
    const maxConsec = getStaffMaxConsecutive(staff, s);

    // 連勤チェック
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

    // 夜勤チェック
    if (newShift === SHIFT_TYPES.NIGHT) {
        const nightType = staff.nightShiftType || (staff.canNightShift ? 'all' : 'none');
        if (nightType === 'none') {
            warnings.push(`${staff.name}さんは夜勤ができません`);
        }
        if (nightType === 'weekday' && isFriSatSun(year, month, day)) {
            warnings.push(`${staff.name}さんは金土日の夜勤ができません`);
        }
        if (staff.type === 'part') {
            warnings.push(`パートスタッフは夜勤に入れません`);
        }
    }

    // 早番チェック（遅出のみのパート）
    if (newShift === SHIFT_TYPES.EARLY && staff.type === 'part' && staff.lateOnly) {
        warnings.push(`${staff.name}さんは遅出のみです`);
    }

    // 遅番チェック（早出のみのパート）
    if (newShift === SHIFT_TYPES.LATE && staff.type === 'part' && staff.earlyOnly) {
        warnings.push(`${staff.name}さんは早出のみです`);
    }

    // 通しチェック
    if (newShift === SHIFT_TYPES.OVERTIME) {
        if (!staff.canOvertime) {
            warnings.push(`${staff.name}さんは残業（通し）ができません`);
        }
        if (staff.type === 'part') {
            warnings.push(`パートスタッフは通し勤務に入れません`);
        }
        if (staff.earlyOnly || staff.lateOnly) {
            warnings.push(`${staff.name}さんは${staff.earlyOnly ? '早出' : '遅出'}のみです`);
        }
    }

    return warnings;
}
