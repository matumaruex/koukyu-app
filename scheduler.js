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
    const shift = assignments[day];
    if (shift && shift !== SHIFT_TYPES.OFF) return false;
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

    // ===== フェーズ0: 白紙スタート =====
    const allAssignments = {};
    staffList.forEach(staff => {
        allAssignments[staff.id] = {};
        for (let day = 1; day <= daysInMonth; day++) {
            allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
        }
    });

    // ===== フェーズ1: 希望休 =====
    staffList.forEach(staff => {
        const staffRequests = requests[staff.id] || [];
        staffRequests.forEach(day => {
            if (day >= 1 && day <= daysInMonth) {
                allAssignments[staff.id][day] = SHIFT_TYPES.OFF;
            }
        });
    });

    // ===== フェーズ2: 夜勤と明けを優先配置 =====
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

    // ★修正: 目標出勤日数を正確に計算（夜勤の明けを「実質休みだが公休ではない日」として控除）
    const getActualTargetWorkDays = (staff) => {
        const offDays = (staff.monthlyDaysOff || 9);
        const nightOffs = countShiftType(allAssignments[staff.id], SHIFT_TYPES.NIGHT_OFF, daysInMonth);
        return daysInMonth - offDays - nightOffs;
    };

    // ===== フェーズ3: パートのシフト(P)配置 =====
    const partStaff = staffList.filter(st => st.type === 'part');
    partStaff.forEach(staff => {
        const targetWorkDays = getActualTargetWorkDays(staff);
        const maxPerWeek = staff.maxDaysPerWeek || 3;

        let candidates = [];
        for (let d = 1; d <= daysInMonth; d++) {
            const reqs = requests[staff.id] || [];
            if (!reqs.includes(d) && allAssignments[staff.id][d] === SHIFT_TYPES.OFF) {
                candidates.push(d);
            }
        }
        candidates = shuffleArray(candidates);

        let currentWork = countWorkDays(allAssignments[staff.id], daysInMonth);
        for (let i = 0; i < candidates.length && currentWork < targetWorkDays; i++) {
            const day = candidates[i];
            if (getWeekWorkDays(allAssignments[staff.id], day, year, month) < maxPerWeek &&
                canWorkOnDay(staff, allAssignments[staff.id], day, s)) {

                if (!staff.startTime) staff.startTime = '09:00';
                if (!staff.endTime) staff.endTime = '17:00';
                allAssignments[staff.id][day] = SHIFT_TYPES.PART;
                currentWork++;
            }
        }
    });

    // ===== フェーズ4: フルタイムの配置 (時間帯ごとの100%確保) =====
    const fullStaff = staffList.filter(st => st.type !== 'part');
    const TARGET_OT = 4; // 残業（通し）の月の許容回数

    for (let day = 1; day <= daysInMonth; day++) {
        const sunday = isSunday(year, month, day);

        TIME_CHECKPOINTS.forEach(cp => {
            const required = sunday ? cp.sundayRequired : cp.required;
            let currentCount = countStaffAtTime(staffList, allAssignments, day, cp.minutes);

            while (currentCount < required) {
                // ★修正: まだ空欄で、かつ「出勤目標」に達していない人を探す（公休確保のストッパー）
                let available = fullStaff.filter(st => {
                    if (allAssignments[st.id][day] !== SHIFT_TYPES.OFF) return false;
                    if (!canWorkOnDay(st, allAssignments[st.id], day, s)) return false;
                    const reqs = requests[st.id] || [];
                    if (reqs.includes(day)) return false;
                    const worked = countWorkDays(allAssignments[st.id], daysInMonth);
                    const target = getActualTargetWorkDays(st);
                    if (worked >= target) return false; // 目標出勤に達している人はもう追加しない！
                    return true;
                });

                available.sort((a, b) => {
                    const aGap = getActualTargetWorkDays(a) - countWorkDays(allAssignments[a.id], daysInMonth);
                    const bGap = getActualTargetWorkDays(b) - countWorkDays(allAssignments[b.id], daysInMonth);
                    return bGap - aGap; // 出勤日数が足りていない人を優先
                });

                if (available.length === 0) {
                    // ★修正: 追加人数が無理な場合のみ、すでにいる早番・遅番を「A残(残業)」に引き伸ばしてカバー
                    const upgradable = fullStaff.filter(st => {
                        const shift = allAssignments[st.id][day];
                        if (shift !== SHIFT_TYPES.EARLY && shift !== SHIFT_TYPES.LATE) return false;
                        if (!st.canOvertime) return false;
                        return true;
                    });

                    if (upgradable.length > 0) {
                        // 残業回数が少ない人を優先して選ぶ（真に必要な時のみ上限突破を許容）
                        upgradable.sort((a, b) => countShiftType(allAssignments[a.id], SHIFT_TYPES.OVERTIME, daysInMonth) - countShiftType(allAssignments[b.id], SHIFT_TYPES.OVERTIME, daysInMonth));
                        const st = upgradable[0];
                        allAssignments[st.id][day] = SHIFT_TYPES.OVERTIME;
                        currentCount = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
                        if (currentCount >= required) break;
                        continue;
                    }

                    // それでも無理なら赤文字になる（警告は出す）
                    warnings.push(`${month}月${day}日：${cp.label}の人数が${currentCount}人で埋めきれません（必要${required}人）`);
                    break;
                }

                // 選ばれたスタッフを出勤させる
                const chosen = available[0];
                let chosenShift = SHIFT_TYPES.EARLY;
                if (cp.minutes >= 1065) {
                    chosenShift = SHIFT_TYPES.LATE;
                } else if (cp.minutes === 600) {
                    chosenShift = Math.random() > 0.5 ? SHIFT_TYPES.EARLY : SHIFT_TYPES.LATE;
                }

                allAssignments[chosen.id][day] = chosenShift;
                currentCount = countStaffAtTime(staffList, allAssignments, day, cp.minutes);
            }
        });
    }

    // ===== フェーズ5: 残りの出勤日数の調整（手薄な日を狙って埋める） =====
    fullStaff.forEach(st => {
        let currentWork = countWorkDays(allAssignments[st.id], daysInMonth);
        const targetWork = getActualTargetWorkDays(st);

        while (currentWork < targetWork) {
            // ★修正: 「すでに出勤人数が多い日」を避け、「手薄な日」を探す
            let dayAffinities = [];
            for (let d = 1; d <= daysInMonth; d++) {
                if (allAssignments[st.id][d] !== SHIFT_TYPES.OFF) continue;
                const reqs = requests[st.id] || [];
                if (reqs.includes(d)) continue;
                if (!canWorkOnDay(st, allAssignments[st.id], d, s)) continue;

                let countOfDay = 0;
                staffList.forEach(otherStaff => {
                    const shift = allAssignments[otherStaff.id][d];
                    if (shift && shift !== SHIFT_TYPES.OFF && shift !== SHIFT_TYPES.NIGHT_OFF) countOfDay++;
                });
                dayAffinities.push({ day: d, count: countOfDay });
            }

            if (dayAffinities.length === 0) break; // もう入れられる日がない

            dayAffinities.sort((a, b) => a.count - b.count);

            const minCount = dayAffinities[0].count;
            const candidates = dayAffinities.filter(d => d.count === minCount);
            const chosenDay = candidates[Math.floor(Math.random() * candidates.length)].day;

            allAssignments[st.id][chosenDay] = Math.random() > 0.5 ? SHIFT_TYPES.EARLY : SHIFT_TYPES.LATE;
            currentWork = countWorkDays(allAssignments[st.id], daysInMonth);
        }
    });

    // 最終チェック：公休数の警告
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
