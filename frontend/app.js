/* app.js — 아파트 시세 AI 비서 프론트엔드 */

// ── API 기반 URL (config.js에서 주입, 없으면 로컬 기본값) ──
const BASE = (window.API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

// ── 전역 상태 ──────────────────────────────────────────────
const state = {
  currentConvId:  null,   // 현재 열린 대화 ID
  isSending:      false,  // 채팅 전송 중 여부
  coldStartTimer: null,   // 콜드 스타트 타이머
  dataPage:       1,
  dataPageSize:   20,
  dataFilters:    { region: '전국', start: '', end: '' },
  dataFirstLoad:  false,  // 데이터 관리 탭 최초 로드 여부
};

// ─────────────────────────────────────────────────────────
// API 헬퍼
// ─────────────────────────────────────────────────────────
async function apiFetch(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    // 422 Pydantic 오류: detail이 배열일 수 있음
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => e.msg || JSON.stringify(e)).join(' / ')
      : (err.detail || `HTTP ${res.status}`);
    throw new Error(detail);
  }
  // 204 No Content 또는 응답 본문이 없는 경우 json() 호출 금지
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) return null;
  return res.json();
}

const api = {
  get:  (path)       => apiFetch('GET',    path),
  post: (path, body) => apiFetch('POST',   path, body),
  put:  (path, body) => apiFetch('PUT',    path, body),
  del:  (path)       => apiFetch('DELETE', path),
};

// ─────────────────────────────────────────────────────────
// 유틸 함수
// ─────────────────────────────────────────────────────────

/** XSS 방지: HTML 특수문자 이스케이프 */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** 데이터 추가/수정 폼 입력 검사. 오류 문자열 또는 null 반환. */
function validateDataForm(fd) {
  const date = fd.get('date');
  const val  = fd.get('value');
  if (!date || !date.trim()) return '날짜를 입력해주세요.';
  const DAY_KO = ['월', '화', '수', '목', '금', '토', '일'];
  const dt = new Date(date + 'T00:00:00');   // 로컬 시간 기준 파싱
  const dow = dt.getDay();                   // 0=일, 1=월
  if (dow !== 1) {
    const dayName = DAY_KO[dow === 0 ? 6 : dow - 1];
    return `주간지수 날짜는 월요일이어야 합니다. (선택한 날짜: ${date} ${dayName}요일)`;
  }
  const num = parseFloat(val);
  if (!val || !val.trim()) return '지수값을 입력해주세요.';
  if (isNaN(num) || num <= 0) return '지수값은 0보다 큰 숫자로 입력해주세요.';
  return null;
}

/** 숫자 → "+1.23%" 형식 */
function fmtPct(val) {
  if (val == null) return '-';
  const n = parseFloat(val);
  return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

/** 숫자 부호 → CSS 클래스 (up/down/flat) */
function numColorClass(val) {
  if (val == null) return 'flat';
  const n = parseFloat(val);
  if (Math.abs(n) < 0.005) return 'flat';
  return n > 0 ? 'up' : 'down';
}

/** 방향 문자열 → CSS 클래스 */
function dirColorClass(direction) {
  if (direction === '상승') return 'up';
  if (direction === '하락') return 'down';
  return 'flat';
}

/** 방향 → 화살표 문자 */
function dirArrow(direction) {
  if (direction === '상승') return '▲';
  if (direction === '하락') return '▼';
  return '─';
}

// ─────────────────────────────────────────────────────────
// 탭 전환
// ─────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const tabId = btn.dataset.tab;
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
      document.getElementById('tab-' + tabId).classList.remove('hidden');

      // 데이터 관리 탭 최초 진입 시 자동 조회
      if (tabId === 'data-mgmt' && !state.dataFirstLoad) {
        state.dataFirstLoad = true;
        loadData();
      }
    });
  });
}

// ─────────────────────────────────────────────────────────
// 사이드바 — 대화 목록
// ─────────────────────────────────────────────────────────
async function loadConversations() {
  try {
    const list = await api.get('/api/conversations');
    renderConversations(list);
  } catch (e) {
    document.getElementById('conv-list').innerHTML =
      `<div class="conv-empty">목록 불러오기 실패: ${esc(e.message)}</div>`;
  }
}

function renderConversations(list) {
  const el = document.getElementById('conv-list');
  if (!list.length) {
    el.innerHTML = '<div class="conv-empty">대화 기록이 없습니다.</div>';
    return;
  }
  el.innerHTML = list.map(c => {
    const isActive = c.id === state.currentConvId;
    const msgLabel = c.message_count ? `메시지 ${c.message_count}개` : '빈 대화';
    return `
      <div class="conv-item ${isActive ? 'active' : ''}" data-id="${esc(c.id)}">
        <div class="conv-item-info">
          <div class="conv-item-title" title="${esc(c.title)}">${esc(c.title)}</div>
          <div class="conv-item-meta">${msgLabel}</div>
        </div>
        <button class="conv-del-btn" data-id="${esc(c.id)}" title="삭제">✕</button>
      </div>`;
  }).join('');

  el.querySelectorAll('.conv-item').forEach(item => {
    item.addEventListener('click', e => {
      if (e.target.closest('.conv-del-btn')) return;
      loadConversation(item.dataset.id);
    });
  });

  el.querySelectorAll('.conv-del-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      deleteConversation(btn.dataset.id);
    });
  });
}

async function loadConversation(id) {
  try {
    const detail = await api.get(`/api/conversations/${id}`);
    state.currentConvId = id;
    document.getElementById('chat-title').textContent = detail.title;
    renderPastMessages(detail.messages);
    loadConversations(); // active 상태 갱신
  } catch (e) {
    alert(`대화를 불러올 수 없습니다: ${e.message}`);
  }
}

function renderPastMessages(messages) {
  const el = document.getElementById('messages');
  el.innerHTML = '';
  messages.forEach(m => appendMessage(m.role, m.content));
  scrollToBottom();
}

async function deleteConversation(id) {
  if (!confirm('이 대화를 삭제하시겠습니까?')) return;
  try {
    await api.del(`/api/conversations/${id}`);
    if (state.currentConvId === id) {
      state.currentConvId = null;
      document.getElementById('chat-title').textContent = '새 대화';
      showWelcome();
    }
    loadConversations();
  } catch (e) {
    alert(`삭제 실패: ${e.message}`);
  }
}

// ─────────────────────────────────────────────────────────
// 채팅
// ─────────────────────────────────────────────────────────
function initChat() {
  const form    = document.getElementById('chat-form');
  const input   = document.getElementById('chat-input');
  const btnSend = document.getElementById('btn-send');

  // Enter → 전송 / Shift+Enter → 줄바꿈
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event('submit', { cancelable: true }));
    }
  });

  // 텍스트 입력 시 버튼 활성화 + 높이 자동 조절
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    updateSendBtn();
  });

  function updateSendBtn() {
    btnSend.disabled = state.isSending || !input.value.trim();
  }

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || state.isSending) return;

    // 환영 화면 제거
    const welcome = document.querySelector('.welcome');
    if (welcome) welcome.remove();

    input.value = '';
    input.style.height = 'auto';
    state.isSending = true;
    updateSendBtn();

    appendMessage('user', text);
    showLoadingBubble(true);
    startColdStartTimer();

    try {
      const res = await api.post('/api/chat', {
        message:         text,
        conversation_id: state.currentConvId || undefined,
      });
      stopColdStartTimer();
      showLoadingBubble(false);
      appendMessage('assistant', res.answer);

      if (!state.currentConvId) {
        state.currentConvId = res.conversation_id;
      }
      // 서버가 반환한 제목으로 헤더 즉시 갱신 (새 대화 첫 전송 시 자동 제목 반영)
      document.getElementById('chat-title').textContent = res.title;
      loadConversations();
    } catch (e) {
      stopColdStartTimer();
      showLoadingBubble(false);
      appendMessage('assistant', `오류가 발생했습니다: ${e.message}`, true);
    } finally {
      state.isSending = false;
      updateSendBtn();
      input.focus();
    }
  });

  // 예시 질문 칩 클릭
  document.getElementById('messages').addEventListener('click', e => {
    const chip = e.target.closest('.example-chip');
    if (!chip) return;
    input.value = chip.dataset.q;
    updateSendBtn();
    form.dispatchEvent(new Event('submit', { cancelable: true }));
  });
}

function appendMessage(role, content, isError = false) {
  const el = document.getElementById('messages');
  const isUser = role === 'user';
  const row = document.createElement('div');
  row.className = `msg-row ${role}`;
  const bubbleClass = isError ? 'msg-bubble error-bubble' : 'msg-bubble';
  row.innerHTML = `
    <div class="msg-avatar">${isUser ? '나' : 'AI'}</div>
    <div class="${bubbleClass}">${esc(content)}</div>`;
  el.appendChild(row);
  scrollToBottom();
}

function showLoadingBubble(show) {
  const existing = document.getElementById('loading-bubble');
  if (!show) { if (existing) existing.remove(); return; }
  if (existing) return;
  const el = document.getElementById('messages');
  const row = document.createElement('div');
  row.id = 'loading-bubble';
  row.className = 'msg-row assistant';
  row.innerHTML = `
    <div class="msg-avatar">AI</div>
    <div class="msg-bubble loading-dots">
      <span></span><span></span><span></span>
    </div>`;
  el.appendChild(row);
  scrollToBottom();
}

function startColdStartTimer() {
  state.coldStartTimer = setTimeout(() => {
    document.getElementById('cold-start-warn').classList.remove('hidden');
  }, 10000);
}

function stopColdStartTimer() {
  if (state.coldStartTimer) {
    clearTimeout(state.coldStartTimer);
    state.coldStartTimer = null;
  }
  document.getElementById('cold-start-warn').classList.add('hidden');
}

function scrollToBottom() {
  const el = document.getElementById('messages');
  el.scrollTop = el.scrollHeight;
}

function showWelcome() {
  document.getElementById('messages').innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">🏠</div>
      <h2>아파트 시세 AI 비서</h2>
      <p>한국부동산원 주간 아파트 매매가격지수에 대해 질문하세요.</p>
      <div class="welcome-examples">
        <span class="example-chip" data-q="서울 강남 최근 추세가 어떤가요?">서울 강남 최근 추세</span>
        <span class="example-chip" data-q="전국 고점 대비 현재 수준은?">전국 고점 대비 현재 수준</span>
        <span class="example-chip" data-q="세종 지수 전체 변화를 알려주세요">세종 지수 전체 변화</span>
        <span class="example-chip" data-q="5개 지역 중 최근 4주 동안 가장 많이 오른 곳은?">최근 4주 가장 많이 오른 지역</span>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────────────────
// 새 대화 버튼
// ─────────────────────────────────────────────────────────
function initNewChat() {
  document.getElementById('btn-new-chat').addEventListener('click', () => {
    state.currentConvId = null;
    document.getElementById('chat-title').textContent = '새 대화';
    showWelcome();
    loadConversations(); // active 해제
    document.getElementById('chat-input').focus();
  });
}

// ─────────────────────────────────────────────────────────
// 요약 패널
// ─────────────────────────────────────────────────────────
async function loadSummary() {
  const container = document.getElementById('summary-cards');
  container.innerHTML = '<p class="loading-text">불러오는 중...</p>';
  try {
    const summary = await api.get('/api/data/summary');
    renderSummaryCards(summary);
  } catch (e) {
    container.innerHTML =
      `<p class="loading-text" style="color:var(--up)">오류: ${esc(e.message)}</p>`;
  }
}

function renderSummaryCards(summary) {
  const container  = document.getElementById('summary-cards');
  const byRegion   = summary.by_region || {};
  const periodStart = (summary.data_period || {}).start || '';
  const regions = ['전국', '서울-강북', '서울-강남', '대전', '세종'];

  container.innerHTML = regions
    .map(r => (byRegion[r] ? buildRegionCard(r, byRegion[r], periodStart) : ''))
    .join('');
}

function buildRegionCard(region, s, periodStart) {
  const latest  = s.latest  || {};
  const trend   = s.trend   || {};
  const streak  = s.streak  || {};

  const trendArrow  = dirArrow(trend.direction);
  const streakArrow = dirArrow(streak.direction);
  const trendCls    = numColorClass(s.change_4w_pct);
  const streakCls   = dirColorClass(streak.direction);

  const peakCls  = numColorClass(s.from_peak_pct);
  const w52Cls   = numColorClass(s.change_52w_pct);
  const totalCls = numColorClass(s.change_total_pct);

  const totalLabel = periodStart ? `전체 변화 (${periodStart} 이후)` : '전체 변화';

  return `
    <div class="summary-card ${region === '전국' ? 'national' : ''}">
      <div class="card-title">${esc(region)}</div>
      <div class="card-latest-row">
        <span class="card-latest">${latest.value != null ? Number(latest.value).toFixed(2) : '-'}</span>
      </div>
      <div class="card-date">${esc(latest.date ?? '-')} 기준</div>
      <div class="card-rows">
        <div class="card-row">
          <span class="lbl">추세 (4주)</span>
          <span class="val ${trendCls}">${trendArrow} ${esc(trend.direction ?? '-')} (${fmtPct(s.change_4w_pct)})</span>
        </div>
        <div class="card-row">
          <span class="lbl">최근 흐름</span>
          <span class="val ${streakCls}">${streakArrow} ${esc(streak.direction ?? '-')} ${streak.weeks ?? 0}주 연속</span>
        </div>
        <div class="card-divider"></div>
        <div class="card-row">
          <span class="lbl">고점 대비</span>
          <span class="val ${peakCls}">${fmtPct(s.from_peak_pct)}</span>
        </div>
        <div class="card-row">
          <span class="lbl">52주 변화</span>
          <span class="val ${w52Cls}">${fmtPct(s.change_52w_pct)}</span>
        </div>
        <div class="card-row">
          <span class="lbl">${esc(totalLabel)}</span>
          <span class="val ${totalCls}">${fmtPct(s.change_total_pct)}</span>
        </div>
      </div>
    </div>`;
}

// ─────────────────────────────────────────────────────────
// 데이터 관리
// ─────────────────────────────────────────────────────────
function initDataMgmt() {
  // 필터 조회
  document.getElementById('btn-filter').addEventListener('click', () => {
    state.dataFilters = {
      region: document.getElementById('filter-region').value,
      start:  document.getElementById('filter-start').value,
      end:    document.getElementById('filter-end').value,
    };
    state.dataPage = 1;
    loadData();
  });

  // 추가 폼
  document.getElementById('add-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd  = new FormData(e.target);
    const msg = document.getElementById('add-msg');
    const validErr = validateDataForm(fd);
    if (validErr) {
      msg.textContent = validErr;
      msg.className = 'form-msg';
      return;
    }
    try {
      await api.post('/api/data', {
        date:   fd.get('date'),
        region: fd.get('region'),
        value:  parseFloat(fd.get('value')),
        memo:   fd.get('memo') || '',
      });
      msg.textContent = '추가되었습니다.';
      msg.className = 'form-msg ok';
      e.target.reset();                          // 성공 시에만 폼 초기화
      setTimeout(() => { msg.textContent = ''; }, 3000);
      loadData();
      loadSummary();
    } catch (err) {
      msg.textContent = `오류: ${err.message}`;
      msg.className = 'form-msg';
      // 오류 시 입력값 유지 (reset 없음)
    }
  });

  // 수정 모달 취소
  document.getElementById('btn-cancel-edit').addEventListener('click', closeEditModal);
  document.getElementById('edit-modal').addEventListener('click', e => {
    if (e.target === document.getElementById('edit-modal')) closeEditModal();
  });

  // 수정 폼 제출
  document.getElementById('edit-form').addEventListener('submit', async e => {
    e.preventDefault();
    const fd  = new FormData(e.target);
    const id  = fd.get('id');
    const msg = document.getElementById('edit-msg');
    const validErr = validateDataForm(fd);
    if (validErr) {
      msg.textContent = validErr;
      return;
    }
    try {
      await api.put(`/api/data/${id}`, {
        date:   fd.get('date'),
        region: fd.get('region'),
        value:  parseFloat(fd.get('value')),
        memo:   fd.get('memo') || '',
      });
      closeEditModal();
      loadData();
      loadSummary();
    } catch (err) {
      msg.textContent = `오류: ${err.message}`;
      // 오류 시 모달 유지 (입력값 보존)
    }
  });

  // 요약 새로고침 버튼
  document.getElementById('btn-refresh-summary').addEventListener('click', loadSummary);
}

async function loadData() {
  const { region, start, end } = state.dataFilters;
  const params = new URLSearchParams({
    page:      state.dataPage,
    page_size: state.dataPageSize,
  });
  if (region) params.set('region', region);
  if (start)  params.set('start_date', start);
  if (end)    params.set('end_date', end);

  const tbody = document.getElementById('data-tbody');
  tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">불러오는 중...</td></tr>`;

  try {
    const data = await api.get(`/api/data?${params}`);
    renderDataTable(data.items);
    renderPagination(data.total, data.page, data.page_size);
  } catch (e) {
    tbody.innerHTML =
      `<tr><td colspan="5" class="empty-cell" style="color:var(--up)">오류: ${esc(e.message)}</td></tr>`;
    document.getElementById('data-pagination').innerHTML = '';
  }
}

function renderDataTable(items) {
  const tbody = document.getElementById('data-tbody');
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty-cell">데이터가 없습니다.</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(item => `
    <tr>
      <td>${esc(item.date)}</td>
      <td>${esc(item.region)}</td>
      <td>${Number(item.value).toFixed(2)}</td>
      <td>${esc(item.memo || '')}</td>
      <td>
        <button class="btn-edit" data-id="${esc(item.id)}">수정</button>
        <button class="btn-del"  data-id="${esc(item.id)}"
                data-date="${esc(item.date)}" data-region="${esc(item.region)}"
                data-value="${Number(item.value).toFixed(2)}">삭제</button>
      </td>
    </tr>`).join('');

  tbody.querySelectorAll('.btn-edit').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = items.find(i => i.id === btn.dataset.id);
      if (item) openEditModal(item);
    });
  });

  tbody.querySelectorAll('.btn-del').forEach(btn => {
    btn.addEventListener('click', async () => {
      const { date, region, value } = btn.dataset;
      const msg = `${date} ${region} (${value}) 데이터를 삭제할까요?\n요약 통계가 다시 계산됩니다.`;
      if (!confirm(msg)) return;
      try {
        await api.del(`/api/data/${btn.dataset.id}`);
        loadData();
        loadSummary();
      } catch (e) {
        alert(`삭제 실패: ${e.message}`);
      }
    });
  });
}

function renderPagination(total, page, pageSize) {
  const container = document.getElementById('data-pagination');
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) { container.innerHTML = ''; return; }

  const range = buildPageRange(page, totalPages);
  let html = '';
  html += `<button class="page-btn" ${page <= 1 ? 'disabled' : ''} data-page="${page - 1}">&#8249;</button>`;
  range.forEach(p => {
    if (p === '...') {
      html += `<button class="page-btn" disabled>…</button>`;
    } else {
      html += `<button class="page-btn ${p === page ? 'active' : ''}" data-page="${p}">${p}</button>`;
    }
  });
  html += `<button class="page-btn" ${page >= totalPages ? 'disabled' : ''} data-page="${page + 1}">&#8250;</button>`;
  container.innerHTML = html;

  container.querySelectorAll('.page-btn[data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      state.dataPage = parseInt(btn.dataset.page, 10);
      loadData();
    });
  });
}

/** 페이지 범위 배열 생성 (최대 7개, 초과 시 '...' 삽입) */
function buildPageRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  if (current > 3) pages.push('...');
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) {
    pages.push(p);
  }
  if (current < total - 2) pages.push('...');
  pages.push(total);
  return pages;
}

function openEditModal(item) {
  const form = document.getElementById('edit-form');
  form.elements['id'].value     = item.id;
  form.elements['date'].value   = item.date;
  form.elements['region'].value = item.region;
  form.elements['value'].value  = item.value;
  form.elements['memo'].value   = item.memo || '';
  document.getElementById('edit-msg').textContent = '';
  document.getElementById('edit-modal').classList.remove('hidden');
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.add('hidden');
}

// ─────────────────────────────────────────────────────────
// 초기화
// ─────────────────────────────────────────────────────────
async function init() {
  initTabs();
  initNewChat();
  initChat();
  initDataMgmt();

  // 대화 목록 + 요약 병렬 로드
  await Promise.all([
    loadConversations(),
    loadSummary(),
  ]);
}

document.addEventListener('DOMContentLoaded', init);
