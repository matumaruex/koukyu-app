// ===== メインアプリケーション =====
// 画面表示、スタッフ管理、シフト表の操作を管理する

// ===== データ管理 =====
// ブラウザのlocalStorage（内部保存領域）にデータを保存・読み込み

const STORAGE_KEYS = {
    STAFF: 'koukyu_staff',
    SCHEDULES: 'koukyu_schedules'
};

// スタッフのアバター色（名前から自動で色を決める）
const AVATAR_COLORS = [
    '#2563eb', '#7c3aed', '#059669', '#d97706',
    '#dc2626', '#0891b2', '#4f46e5', '#be185d',
    '#65a30d', '#ca8a04'
];

// ===== 状態管理 =====
let staffList = [];               // スタッフ一覧
let schedules = {};               // 全月のスケジュールデータ
let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 2; // 来月をデフォルトに
if (currentMonth > 12) {
    currentMonth = 1;
    currentYear++;
}

// ===== 初期化 =====
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    migrateStaffData(); // 古いデータ形式を新しい形式に変換
    initNavigation();
    initStaffModal();
    initRequestModal();
    initShiftModal();
    initScheduleActions();
    initDataActions();
    renderStaffList();
    renderSchedule();
});

// ===== データ移行（後方互換性） =====
// 古い canNightShift (boolean) を新しい nightShiftType に変換
function migrateStaffData() {
    let changed = false;
    staffList.forEach(staff => {
        // canNightShift → nightShiftType への変換
        if (staff.canNightShift !== undefined && !staff.nightShiftType) {
            staff.nightShiftType = staff.canNightShift ? 'all' : 'none';
            delete staff.canNightShift;
            changed = true;
        }
        // nightShiftType が未設定の場合のデフォルト
        if (!staff.nightShiftType) {
            staff.nightShiftType = 'none';
            changed = true;
        }
        // allowConsecutivePlus1 が未設定の場合のデフォルト（既存データ対応）
        if (staff.allowConsecutivePlus1 === undefined) {
            staff.allowConsecutivePlus1 = false;
            changed = true;
        }
    });
    if (changed) saveStaff();
}

// ===== データ読み込み・保存 =====
function loadData() {
    try {
        const staffData = localStorage.getItem(STORAGE_KEYS.STAFF);
        if (staffData) staffList = JSON.parse(staffData);

        const scheduleData = localStorage.getItem(STORAGE_KEYS.SCHEDULES);
        if (scheduleData) schedules = JSON.parse(scheduleData);
    } catch (e) {
        console.error('データ読み込みエラー:', e);
    }
}

function saveStaff() {
    localStorage.setItem(STORAGE_KEYS.STAFF, JSON.stringify(staffList));
}

function saveSchedules() {
    localStorage.setItem(STORAGE_KEYS.SCHEDULES, JSON.stringify(schedules));
}

function getScheduleKey() {
    return `${currentYear}-${String(currentMonth).padStart(2, '0')}`;
}

function getCurrentSchedule() {
    const key = getScheduleKey();
    if (!schedules[key]) {
        schedules[key] = { requests: {}, assignments: {} };
    }
    return schedules[key];
}

// ===== タブナビゲーション =====
function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const viewName = btn.dataset.view;
            // タブのアクティブ状態を切替
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            // 画面の表示を切替
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            document.getElementById(`${viewName}-view`).classList.add('active');

            // シフト表タブに切り替えたとき再描画
            if (viewName === 'schedule') {
                renderSchedule();
            }
        });
    });
}

// ===== スタッフ管理 =====

/**
 * スタッフ一覧を画面に表示
 */
function renderStaffList() {
    const listEl = document.getElementById('staff-list');
    const emptyEl = document.getElementById('staff-empty');

    if (staffList.length === 0) {
        listEl.innerHTML = '';
        emptyEl.style.display = 'block';
        return;
    }

    emptyEl.style.display = 'none';

    listEl.innerHTML = staffList.map((staff, index) => {
        const color = AVATAR_COLORS[index % AVATAR_COLORS.length];
        const initial = staff.name.charAt(0);
        const tags = [];

        if (staff.type === 'part') {
            tags.push('<span class="staff-tag tag-part">パート</span>');
        }

        // 夜勤設定の表示
        const nightType = staff.nightShiftType || 'none';
        if (nightType === 'all') {
            tags.push('<span class="staff-tag tag-night">夜勤OK</span>');
        } else if (nightType === 'weekday') {
            tags.push('<span class="staff-tag tag-night-weekday">夜勤（平日）</span>');
        }

        if (staff.canOvertime) {
            tags.push('<span class="staff-tag tag-overtime">残業OK</span>');
        }

        // 早出のみ（パート）
        if (staff.type === 'part' && staff.earlyOnly) {
            tags.push('<span class="staff-tag tag-early-only">早出(A)のみ</span>');
        }

        // 遅出のみ（パート）
        if (staff.type === 'part' && staff.lateOnly) {
            tags.push('<span class="staff-tag tag-late-only">遅出(B)のみ</span>');
        }

        tags.push(`<span class="staff-tag">公休${staff.monthlyDaysOff}日</span>`);

        if (staff.type === 'part') {
            tags.push(`<span class="staff-tag">週${staff.maxDaysPerWeek}日</span>`);
        }

        // 連勤上限の表示（個別設定がある場合のみ）
        if (staff.maxConsecutive && staff.maxConsecutive > 0) {
            tags.push(`<span class="staff-tag tag-consecutive">連勤${staff.maxConsecutive}日</span>`);
        }

        // パートの勤務時間表示
        if (staff.type === 'part' && staff.startTime && staff.endTime) {
            tags.push(`<span class="staff-tag tag-time">${staff.startTime}〜${staff.endTime}</span>`);
        }

        // 連勤+1許容の表示
        if (staff.allowConsecutivePlus1) {
            tags.push('<span class="staff-tag tag-plus1">連勤+1OK</span>');
        }

        return `
      <div class="staff-card" data-id="${staff.id}">
        <div class="staff-avatar" style="background:${color}">${initial}</div>
        <div class="staff-info">
          <div class="staff-name">${escapeHtml(staff.name)}</div>
          <div class="staff-tags">${tags.join('')}</div>
        </div>
        <div class="staff-actions">
          <button class="btn btn-outline btn-sm" onclick="editStaff('${staff.id}')">編集</button>
          <button class="btn btn-danger btn-sm" onclick="deleteStaff('${staff.id}')">削除</button>
        </div>
      </div>
    `;
    }).join('');
}

/**
 * HTMLエスケープ（入力値を安全に表示するため）
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * ユニークなID（識別番号）を生成
 */
function generateId() {
    return 'staff_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
}

// ===== スタッフ追加・編集モーダル =====
function initStaffModal() {
    const modal = document.getElementById('staff-modal');
    const form = document.getElementById('staff-form');
    const typeSelect = document.getElementById('staff-type');

    // フォーム表示の切り替え関数
    function updateFormVisibility(type) {
        const nightGroup = document.getElementById('night-shift-group');
        const overtimeGroup = document.getElementById('overtime-group');
        const maxDaysGroup = document.getElementById('max-days-group');
        const earlyOnlyGroup = document.getElementById('early-only-group');
        const lateOnlyGroup = document.getElementById('late-only-group');
        const workHoursGroup = document.getElementById('work-hours-group');

        if (type === 'part') {
            // パート：夜勤・残業は非表示、早出のみ・遅出のみ・週の出勤日数・勤務時間を表示
            nightGroup.style.display = 'none';
            overtimeGroup.style.display = 'none';
            maxDaysGroup.style.display = '';
            earlyOnlyGroup.style.display = '';
            lateOnlyGroup.style.display = '';
            workHoursGroup.style.display = '';
            document.getElementById('staff-night-type').value = 'none';
            document.getElementById('staff-overtime').checked = false;
        } else {
            // フルタイム：夜勤・残業を表示、パート専用は非表示
            nightGroup.style.display = '';
            overtimeGroup.style.display = '';
            maxDaysGroup.style.display = 'none';
            earlyOnlyGroup.style.display = 'none';
            lateOnlyGroup.style.display = 'none';
            workHoursGroup.style.display = 'none';
            document.getElementById('staff-early-only').checked = false;
            document.getElementById('staff-late-only').checked = false;
        }
    }

    // 追加ボタン
    document.getElementById('add-staff-btn').addEventListener('click', () => {
        document.getElementById('staff-modal-title').textContent = 'スタッフ追加';
        document.getElementById('staff-id').value = '';
        document.getElementById('staff-name').value = '';
        document.getElementById('staff-type').value = 'full';
        document.getElementById('staff-night-type').value = 'none';
        document.getElementById('staff-overtime').checked = false;
        document.getElementById('staff-early-only').checked = false;
        document.getElementById('staff-late-only').checked = false;
        document.getElementById('staff-days-off').value = 9;
        document.getElementById('staff-max-days').value = 3;
        document.getElementById('staff-max-consecutive').value = 0;
        document.getElementById('staff-start-time').value = '09:00';
        document.getElementById('staff-end-time').value = '17:00';
        document.getElementById('staff-consecutive-plus1').checked = false;
        updateFormVisibility('full');
        modal.classList.add('show');
    });

    // 勤務形態の変更でフォームを切り替え
    typeSelect.addEventListener('change', () => {
        updateFormVisibility(typeSelect.value);
    });

    // 閉じるボタン
    document.getElementById('staff-modal-close').addEventListener('click', () => modal.classList.remove('show'));
    document.getElementById('staff-cancel').addEventListener('click', () => modal.classList.remove('show'));

    // モーダル外クリックで閉じる
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('show');
    });

    // フォーム送信（保存）
    form.addEventListener('submit', (e) => {
        e.preventDefault();

        const id = document.getElementById('staff-id').value;
        const type = document.getElementById('staff-type').value;

        const staffData = {
            id: id || generateId(),
            name: document.getElementById('staff-name').value.trim(),
            type: type,
            nightShiftType: document.getElementById('staff-night-type').value,
            canOvertime: document.getElementById('staff-overtime').checked,
            earlyOnly: document.getElementById('staff-early-only').checked,
            lateOnly: document.getElementById('staff-late-only').checked,
            monthlyDaysOff: parseInt(document.getElementById('staff-days-off').value) || 9,
            maxDaysPerWeek: parseInt(document.getElementById('staff-max-days').value) || 3,
            maxConsecutive: parseInt(document.getElementById('staff-max-consecutive').value) || 0,
            startTime: document.getElementById('staff-start-time').value || '',
            endTime: document.getElementById('staff-end-time').value || '',
            allowConsecutivePlus1: document.getElementById('staff-consecutive-plus1').checked
        };

        if (!staffData.name) return;

        // パートの場合は夜勤・残業を無効に
        if (staffData.type === 'part') {
            staffData.nightShiftType = 'none';
            staffData.canOvertime = false;
            // 早出のみと遅出のみは同時に選べない
            if (staffData.earlyOnly && staffData.lateOnly) {
                staffData.lateOnly = false; // 早出のみを優先
            }
        } else {
            // フルタイムの場合は早出のみ・遅出のみ・勤務時間を無効に
            staffData.earlyOnly = false;
            staffData.lateOnly = false;
            staffData.startTime = '';
            staffData.endTime = '';
        }

        if (id) {
            // 既存スタッフを更新
            const index = staffList.findIndex(s => s.id === id);
            if (index >= 0) staffList[index] = staffData;
        } else {
            // 新規追加
            staffList.push(staffData);
        }

        saveStaff();
        renderStaffList();
        modal.classList.remove('show');
    });
}

/**
 * スタッフを編集モードで開く
 */
function editStaff(id) {
    const staff = staffList.find(s => s.id === id);
    if (!staff) return;

    const modal = document.getElementById('staff-modal');
    document.getElementById('staff-modal-title').textContent = 'スタッフ編集';
    document.getElementById('staff-id').value = staff.id;
    document.getElementById('staff-name').value = staff.name;
    document.getElementById('staff-type').value = staff.type;
    document.getElementById('staff-night-type').value = staff.nightShiftType || 'none';
    document.getElementById('staff-overtime').checked = staff.canOvertime;
    document.getElementById('staff-early-only').checked = staff.earlyOnly || false;
    document.getElementById('staff-late-only').checked = staff.lateOnly || false;
    document.getElementById('staff-days-off').value = staff.monthlyDaysOff;
    document.getElementById('staff-max-days').value = staff.maxDaysPerWeek || 3;
    document.getElementById('staff-max-consecutive').value = staff.maxConsecutive || 0;
    document.getElementById('staff-start-time').value = staff.startTime || '09:00';
    document.getElementById('staff-end-time').value = staff.endTime || '17:00';
    document.getElementById('staff-consecutive-plus1').checked = staff.allowConsecutivePlus1 || false;

    // フォーム表示の切り替え
    const nightGroup = document.getElementById('night-shift-group');
    const overtimeGroup = document.getElementById('overtime-group');
    const maxDaysGroup = document.getElementById('max-days-group');
    const earlyOnlyGroup = document.getElementById('early-only-group');
    const lateOnlyGroup = document.getElementById('late-only-group');
    const workHoursGroup = document.getElementById('work-hours-group');

    if (staff.type === 'part') {
        nightGroup.style.display = 'none';
        overtimeGroup.style.display = 'none';
        maxDaysGroup.style.display = '';
        earlyOnlyGroup.style.display = '';
        lateOnlyGroup.style.display = '';
        workHoursGroup.style.display = '';
    } else {
        nightGroup.style.display = '';
        overtimeGroup.style.display = '';
        maxDaysGroup.style.display = 'none';
        earlyOnlyGroup.style.display = 'none';
        lateOnlyGroup.style.display = 'none';
        workHoursGroup.style.display = 'none';
    }

    modal.classList.add('show');
}

/**
 * スタッフを削除
 */
function deleteStaff(id) {
    const staff = staffList.find(s => s.id === id);
    if (!staff) return;

    if (confirm(`${staff.name}さんを削除しますか？`)) {
        staffList = staffList.filter(s => s.id !== id);
        saveStaff();
        renderStaffList();
    }
}

// ===== シフト表の表示 =====

/**
 * シフト表を描画
 */
function renderSchedule() {
    const noStaffEl = document.getElementById('schedule-no-staff');
    const containerEl = document.getElementById('schedule-container');

    // 月の表示を更新
    document.getElementById('current-month').textContent =
        `${currentYear}年${currentMonth}月`;

    if (staffList.length === 0) {
        noStaffEl.style.display = 'block';
        containerEl.style.display = 'none';
        return;
    }

    noStaffEl.style.display = 'none';
    containerEl.style.display = '';

    const daysInMonth = getDaysInMonth(currentYear, currentMonth);
    const schedule = getCurrentSchedule();
    const dayNames = ['日', '月', '火', '水', '木', '金', '土'];

    // ===== ヘッダー行（日付と曜日） =====
    const thead = document.getElementById('schedule-thead');
    let headerRow1 = '<tr><th class="staff-name-cell">名前</th>';
    let headerRow2 = '<tr><th class="staff-name-cell"></th>';

    for (let day = 1; day <= daysInMonth; day++) {
        const dow = getDayOfWeek(currentYear, currentMonth, day);
        const dowName = dayNames[dow];
        let dayClass = '';
        if (dow === 0) dayClass = 'day-sunday';
        if (dow === 6) dayClass = 'day-saturday';

        headerRow1 += `<th class="${dayClass}">${day}</th>`;
        headerRow2 += `<th class="${dayClass}" style="font-size:0.65rem">${dowName}</th>`;
    }

    // 集計列
    headerRow1 += '<th>A</th><th>B</th><th>夜</th><th>A残</th><th>休</th>';
    headerRow2 += '<th></th><th></th><th></th><th></th><th></th>';

    thead.innerHTML = headerRow1 + '</tr>' + headerRow2 + '</tr>';

    // ===== スタッフの行 =====
    const tbody = document.getElementById('schedule-tbody');
    let tbodyHtml = '';

    staffList.forEach(staff => {
        const assignments = schedule.assignments[staff.id] || {};
        let earlyCount = 0, lateCount = 0, nightCount = 0, overtimeCount = 0, offCount = 0;

        let row = `<tr><td class="staff-name-cell">${escapeHtml(staff.name)}</td>`;

        for (let day = 1; day <= daysInMonth; day++) {
            const shift = assignments[day];
            const dow = getDayOfWeek(currentYear, currentMonth, day);
            const sundayClass = dow === 0 ? ' day-sunday' : '';

            if (shift) {
                const label = SHIFT_LABELS[shift] || '';
                row += `<td class="shift-cell${sundayClass}" data-staff="${staff.id}" data-day="${day}">
          <span class="shift-badge shift-${shift}">${label}</span></td>`;

                // 集計
                if (shift === SHIFT_TYPES.EARLY) earlyCount++;
                if (shift === SHIFT_TYPES.LATE) lateCount++;
                if (shift === SHIFT_TYPES.NIGHT) nightCount++;
                if (shift === SHIFT_TYPES.OVERTIME) overtimeCount++;
                if (shift === SHIFT_TYPES.OFF) offCount++;
            } else {
                row += `<td class="shift-cell${sundayClass}" data-staff="${staff.id}" data-day="${day}"></td>`;
            }
        }

        // 個人集計
        row += `<td>${earlyCount}</td><td>${lateCount}</td><td>${nightCount}</td><td>${overtimeCount}</td><td>${offCount}</td>`;
        row += '</tr>';
        tbodyHtml += row;
    });

    tbody.innerHTML = tbodyHtml;

    // ===== 日ごとの集計行 =====
    renderSummary(daysInMonth, schedule);

    // セルクリックイベント
    document.querySelectorAll('.shift-cell').forEach(cell => {
        cell.addEventListener('click', () => {
            const staffId = cell.dataset.staff;
            const day = parseInt(cell.dataset.day);
            openShiftModal(staffId, day);
        });
    });
}

/**
 * 日ごとの人数集計を表示
 * 朝(7:00)、昼(10:00)、夕(17:45)、夜勤 の4行で表示
 * パート個人の勤務時間も考慮して正確にカウント
 */
function renderSummary(daysInMonth, schedule) {
    const summaryThead = document.querySelector('#summary-table thead tr');
    let summaryHeaderHtml = '<th class="staff-name-cell">集計</th>';
    for (let day = 1; day <= daysInMonth; day++) {
        summaryHeaderHtml += '<th></th>';
    }
    summaryHeaderHtml += '<th></th><th></th><th></th><th></th><th></th>';
    summaryThead.innerHTML = summaryHeaderHtml;

    const summaryTbody = document.getElementById('summary-tbody');

    // 4行：朝(7:00)、昼(10:00)、夕(17:45)、夜勤
    const rows = [
        { label: '朝7時', minutes: 420, required: 4, sundayRequired: 4 },
        { label: '昼10時', minutes: 600, required: 4, sundayRequired: 4 },
        { label: '夕17時', minutes: 1065, required: 4, sundayRequired: 3 },
        { label: '夜勤', minutes: null, required: 1, sundayRequired: 1 }
    ];

    let summaryHtml = '';

    rows.forEach(rowDef => {
        let row = `<tr><td class="staff-name-cell">${rowDef.label}</td>`;

        for (let day = 1; day <= daysInMonth; day++) {
            let count = 0;
            const sunday = isSunday(currentYear, currentMonth, day);

            if (rowDef.minutes !== null) {
                // 時間帯チェック：countStaffAtTimeでパート個人の時間も考慮
                count = countStaffAtTime(staffList, schedule.assignments, day, rowDef.minutes);
            } else {
                // 夜勤の人数
                staffList.forEach(staff => {
                    const shift = schedule.assignments[staff.id]?.[day];
                    if (shift === SHIFT_TYPES.NIGHT) count++;
                });
            }

            const required = sunday ? rowDef.sundayRequired : rowDef.required;
            const isOk = count >= required;
            const cssClass = isOk ? 'summary-ok' : 'summary-warn';

            row += `<td class="${cssClass}">${count}</td>`;
        }

        row += '<td></td><td></td><td></td><td></td><td></td></tr>';
        summaryHtml += row;
    });

    summaryTbody.innerHTML = summaryHtml;
}

// ===== スケジュール操作 =====
function initScheduleActions() {
    // 前月・次月ボタン
    document.getElementById('prev-month').addEventListener('click', () => {
        currentMonth--;
        if (currentMonth < 1) { currentMonth = 12; currentYear--; }
        renderSchedule();
    });

    document.getElementById('next-month').addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 12) { currentMonth = 1; currentYear++; }
        renderSchedule();
    });

    // 自動生成ボタン
    document.getElementById('auto-generate-btn').addEventListener('click', () => {
        if (staffList.length === 0) {
            alert('まずスタッフを登録してください');
            return;
        }

        const schedule = getCurrentSchedule();
        const hasAssignments = Object.keys(schedule.assignments).some(
            id => Object.keys(schedule.assignments[id] || {}).length > 0
        );

        if (hasAssignments) {
            if (!confirm('すでにシフトが入っています。リセットして自動生成しますか？')) {
                return;
            }
        }

        // ローディング表示
        document.getElementById('loading-modal').style.display = 'flex';

        // 少し遅らせて描画を更新してからアルゴリズムを実行
        setTimeout(() => {
            try {
                const result = generateSchedule(
                    staffList,
                    currentYear,
                    currentMonth,
                    schedule.requests || {},
                    DEFAULT_SETTINGS
                );

                schedule.assignments = result.assignments;
                saveSchedules();
                renderSchedule();

                // 警告があれば表示
                if (result.warnings.length > 0) {
                    const uniqueWarnings = [...new Set(result.warnings)];
                    alert('自動生成が完了しました！\n\n注意点：\n' + uniqueWarnings.join('\n'));
                } else {
                    alert('自動生成が完了しました！');
                }
            } catch (e) {
                console.error('自動生成エラー:', e);
                alert('自動生成中にエラーが発生しました。スタッフの設定を確認してください。');
            }

            document.getElementById('loading-modal').style.display = 'none';
        }, 100);
    });

    // リセットボタン
    document.getElementById('clear-schedule-btn').addEventListener('click', () => {
        if (confirm('このシフト表をリセットしますか？希望休は残ります。')) {
            const schedule = getCurrentSchedule();
            schedule.assignments = {};
            saveSchedules();
            renderSchedule();
        }
    });

    // 印刷ボタン
    document.getElementById('print-btn').addEventListener('click', () => {
        // シフト表タブをアクティブにして印刷
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById('schedule-view').classList.add('active');
        window.print();
    });

    // 希望休ボタン
    document.getElementById('request-btn').addEventListener('click', () => {
        openRequestModal();
    });
}

// ===== 希望休入力モーダル =====
function initRequestModal() {
    const modal = document.getElementById('request-modal');
    document.getElementById('request-modal-close').addEventListener('click', () => modal.classList.remove('show'));
    document.getElementById('request-done').addEventListener('click', () => {
        modal.classList.remove('show');
        renderSchedule();
    });
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
            renderSchedule();
        }
    });

    // スタッフ選択変更時にカレンダーを再描画
    document.getElementById('request-staff').addEventListener('change', () => {
        renderRequestCalendar();
    });
}

function openRequestModal() {
    if (staffList.length === 0) {
        alert('まずスタッフを登録してください');
        return;
    }

    const modal = document.getElementById('request-modal');
    const select = document.getElementById('request-staff');

    // スタッフ選択肢を更新
    select.innerHTML = staffList.map(s =>
        `<option value="${s.id}">${escapeHtml(s.name)}</option>`
    ).join('');

    renderRequestCalendar();
    modal.classList.add('show');
}

function renderRequestCalendar() {
    const calEl = document.getElementById('request-calendar');
    const staffId = document.getElementById('request-staff').value;
    const schedule = getCurrentSchedule();
    const requests = schedule.requests[staffId] || [];
    const daysInMonth = getDaysInMonth(currentYear, currentMonth);
    const firstDow = getDayOfWeek(currentYear, currentMonth, 1);
    const dayHeaders = ['日', '月', '火', '水', '木', '金', '土'];

    let html = '';

    // 曜日ヘッダー
    dayHeaders.forEach((d, i) => {
        let cls = 'cal-header';
        if (i === 0) cls += ' sunday';
        if (i === 6) cls += ' saturday';
        html += `<div class="${cls}">${d}</div>`;
    });

    // 1日までの空白
    for (let i = 0; i < firstDow; i++) {
        html += '<div class="cal-day empty"></div>';
    }

    // 各日
    for (let day = 1; day <= daysInMonth; day++) {
        const dow = getDayOfWeek(currentYear, currentMonth, day);
        const isSelected = requests.includes(day);
        let cls = 'cal-day';
        if (isSelected) cls += ' selected';
        if (dow === 0) cls += ' sunday';

        html += `<div class="${cls}" data-day="${day}">${day}</div>`;
    }

    calEl.innerHTML = html;

    // 日付クリックイベント
    calEl.querySelectorAll('.cal-day:not(.empty)').forEach(el => {
        el.addEventListener('click', () => {
            const day = parseInt(el.dataset.day);
            const schedule = getCurrentSchedule();
            if (!schedule.requests[staffId]) schedule.requests[staffId] = [];

            const idx = schedule.requests[staffId].indexOf(day);
            if (idx >= 0) {
                // 希望休を解除
                schedule.requests[staffId].splice(idx, 1);
                el.classList.remove('selected');
            } else {
                // 希望休を追加
                schedule.requests[staffId].push(day);
                el.classList.add('selected');
            }

            saveSchedules();
        });
    });
}

// ===== シフト変更モーダル =====
function initShiftModal() {
    const modal = document.getElementById('shift-modal');
    document.getElementById('shift-modal-close').addEventListener('click', () => modal.classList.remove('show'));
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('show');
    });

    // シフトオプションのクリック
    document.querySelectorAll('.shift-option').forEach(btn => {
        btn.addEventListener('click', () => {
            const newShift = btn.dataset.shift;
            applyShiftChange(newShift);
        });
    });
}

let editingStaffId = null;
let editingDay = null;

function openShiftModal(staffId, day) {
    const staff = staffList.find(s => s.id === staffId);
    if (!staff) return;

    editingStaffId = staffId;
    editingDay = day;

    const modal = document.getElementById('shift-modal');
    const dow = getDayOfWeek(currentYear, currentMonth, day);
    const dayNames = ['日', '月', '火', '水', '木', '金', '土'];

    document.getElementById('shift-modal-title').textContent = 'シフト変更';
    document.getElementById('shift-modal-info').textContent =
        `${staff.name}さん ─ ${currentMonth}月${day}日（${dayNames[dow]}）`;

    // 警告をクリア
    document.getElementById('shift-warning').style.display = 'none';

    modal.classList.add('show');
}

function applyShiftChange(newShift) {
    if (!editingStaffId || !editingDay) return;

    const staff = staffList.find(s => s.id === editingStaffId);
    const schedule = getCurrentSchedule();
    if (!schedule.assignments[editingStaffId]) {
        schedule.assignments[editingStaffId] = {};
    }

    // 警告チェック
    const warnings = getShiftChangeWarnings(
        staff,
        schedule.assignments,
        staffList,
        editingDay,
        newShift,
        currentYear,
        currentMonth,
        DEFAULT_SETTINGS
    );

    if (warnings.length > 0) {
        const warningEl = document.getElementById('shift-warning');
        warningEl.innerHTML = '⚠️ ' + warnings.join('<br>⚠️ ');
        warningEl.style.display = 'block';

        // 警告があっても変更は適用する（ソフト制約）
    }

    // シフト変更を適用
    schedule.assignments[editingStaffId][editingDay] = newShift;

    // 夜勤の場合、翌日を「明け」、翌々日を「休み」にする
    if (newShift === SHIFT_TYPES.NIGHT) {
        const daysInMonth = getDaysInMonth(currentYear, currentMonth);
        if (editingDay + 1 <= daysInMonth) {
            schedule.assignments[editingStaffId][editingDay + 1] = SHIFT_TYPES.NIGHT_OFF;
        }
        if (editingDay + 2 <= daysInMonth) {
            schedule.assignments[editingStaffId][editingDay + 2] = SHIFT_TYPES.OFF;
        }
    }

    saveSchedules();
    renderSchedule();

    // 警告がなければモーダルを閉じる
    if (warnings.length === 0) {
        document.getElementById('shift-modal').classList.remove('show');
    }
}

// ===== データのエクスポート・インポート =====
function initDataActions() {
    // エクスポート（書き出し）
    document.getElementById('export-btn').addEventListener('click', () => {
        const data = {
            staff: staffList,
            schedules: schedules,
            exportDate: new Date().toISOString()
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `公休表_バックアップ_${currentYear}${String(currentMonth).padStart(2, '0')}.json`;
        a.click();
        URL.revokeObjectURL(url);
    });

    // インポート（読み込み）
    document.getElementById('import-btn').addEventListener('click', () => {
        document.getElementById('import-file').click();
    });

    document.getElementById('import-file').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const data = JSON.parse(event.target.result);
                if (data.staff && Array.isArray(data.staff)) {
                    if (confirm('現在のデータを上書きします。よろしいですか？')) {
                        staffList = data.staff;
                        if (data.schedules) schedules = data.schedules;
                        migrateStaffData(); // インポートしたデータも移行
                        saveStaff();
                        saveSchedules();
                        renderStaffList();
                        renderSchedule();
                        alert('データを読み込みました！');
                    }
                } else {
                    alert('正しいバックアップファイルではありません');
                }
            } catch (err) {
                alert('ファイルの読み込みに失敗しました');
            }
        };
        reader.readAsText(file);
        e.target.value = '';
    });
}
