let currentUser = null;
let sessionGeneration = 0;

// CSRF 방어: 쿠키로 인증된 상태 변경 요청은 이 헤더가 있어야 서버가 받아준다.
const CSRF_HEADERS = { "X-Requested-With": "SecureDocs" };

async function api(path, method = "GET", body = null) {
  const generation = sessionGeneration;
  const opts = { method, headers: { ...CSRF_HEADERS } };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (generation !== sessionGeneration) return { ok: false, status: 401, data: {} };
  return { ok: res.ok, status: res.status, data };
}
// 출력 이스케이프: innerHTML 에 넣는 모든 사용자 제어 값에 적용 (XSS 방지)
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const initials = (s) => esc((s || "?").trim().charAt(0).toUpperCase());
const byId = (id) => document.getElementById(id);
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind; t.textContent = msg;
  byId("toasts").appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

/* ---------- 로그인 ---------- */
function showTab(t) {
  byId("login-form").classList.toggle("hidden", t !== "login");
  byId("register-form").classList.toggle("hidden", t !== "register");
  byId("tab-login").classList.toggle("active", t === "login");
  byId("tab-register").classList.toggle("active", t === "register");
}
async function login() {
  const username = byId("login-username").value;
  const password = byId("login-password").value;
  const r = await api("/api/auth/login", "POST", { username, password });
  if (r.ok) { currentUser = r.data; enterApp(); }
  else setMsg(r.data.error || "로그인 실패", "err");
}
async function register() {
  const username = byId("reg-username").value;
  const password = byId("reg-password").value;
  const full_name = byId("reg-fullname").value;
  const r = await api("/api/auth/register", "POST", { username, password, full_name });
  if (r.ok) { currentUser = r.data; enterApp(); }
  else setMsg(r.data.error || "가입 실패", "err");
}
function setMsg(m, k) { const e = byId("auth-msg"); e.textContent = m; e.className = "msg " + k; }
async function logout() {
  const result = await api("/api/auth/logout", "POST");
  if (!result.ok) { toast("로그아웃에 실패했습니다. 다시 시도하세요.", "err"); return; }
  sessionGeneration += 1;
  currentUser = null;
  for (const id of ["doc-list", "doc-detail", "comments", "profile-info", "admin-users", "admin-docs", "search-results", "stats"]) {
    const element = byId(id); if (element) element.replaceChildren();
  }
  for (const input of document.querySelectorAll("input, textarea")) input.value = "";
  byId("app").classList.add("hidden");
  byId("auth").classList.remove("hidden");
}
function enterApp() {
  sessionGeneration += 1;
  byId("auth").classList.add("hidden");
  byId("app").classList.remove("hidden");
  byId("me-name").textContent = currentUser.username;
  byId("me-role").textContent = currentUser.role === "admin" ? "관리자" : "일반 사용자";
  byId("me-av").textContent = (currentUser.username || "?").trim().charAt(0).toUpperCase();
  const isAdmin = currentUser.role === "admin";
  byId("nav-admin").classList.toggle("hidden", !isAdmin);
  byId("admin-sec").classList.toggle("hidden", !isAdmin);
  showView("docs");
}

/* ---------- 뷰 전환 ---------- */
const TITLES = { docs: "문서", profile: "내 프로필", admin: "관리자" };
function showView(v) {
  for (const id of ["docs", "profile", "admin"]) {
    byId("view-" + id).classList.toggle("hidden", id !== v);
    const n = byId("nav-" + id); if (n) n.classList.toggle("active", id === v);
  }
  byId("topbar-title").textContent = TITLES[v];
  if (v === "docs") loadDocs();
  if (v === "profile") loadProfile();
  if (v === "admin") loadAdmin();
}
function toggleNew() { byId("new-panel").classList.toggle("hidden"); }

/* ---------- 문서 ---------- */
function docBadge(vis) { return vis === "public" ? '<span class="badge pub">● 공개</span>' : '<span class="badge pri">● 비공개</span>'; }
const openButton = (id) => `<button class="btn btn-ghost btn-sm" data-action="view-doc" data-id="${Number(id)}">열기</button>`;
function pager(action, offset, count, docId = 0) {
  return `<div class="row mt-12"><button class="btn btn-ghost" data-action="${action}" data-offset="${Math.max(0, offset - 50)}" data-id="${docId}" ${offset === 0 ? "disabled" : ""}>이전</button><span>${offset / 50 + 1} 페이지</span><button class="btn btn-ghost" data-action="${action}" data-offset="${offset + 50}" data-id="${docId}" ${count < 50 ? "disabled" : ""}>다음</button></div>`;
}
async function loadDocs(offset = 0) {
  const r = await api(`/api/documents?limit=50&offset=${offset}`);
  if (!r.ok) return;
  const docs = r.data;
  const pub = docs.filter(d => d.visibility === "public").length;
  const mine = docs.filter(d => d.owner_id === currentUser.id).length;
  byId("stats").innerHTML = [
    ["현재 페이지 문서", docs.length, "🗂️", "ic-orange"],
    ["현재 페이지 내 문서", mine, "📝", "ic-blue"],
    ["현재 페이지 공개", pub, "🌐", "ic-green"],
    ["팀원", "4+", "👥", "ic-purple"],
  ].map(s => `<div class="stat"><div class="k"><span class="ic ${s[3]}">${s[2]}</span>${s[0]}</div><div class="v">${s[1]}</div></div>`).join("");

  if (!docs.length) { byId("doc-list").innerHTML = '<div class="empty">문서가 없어요.</div>' + pager("docs-page", offset, 0); return; }
  byId("doc-list").innerHTML = docs.map(d => `
    <div class="doc">
      <div class="fic">📄</div>
      <div class="meta"><div class="t">${esc(d.title)}</div><div class="s">${docBadge(d.visibility)} &nbsp;·&nbsp; 문서 #${Number(d.id)}</div></div>
      <div class="act">${openButton(d.id)}</div>
    </div>`).join("") + pager("docs-page", offset, docs.length);
}
async function createDoc() {
  const title = byId("doc-title").value;
  const body = byId("doc-body").value;
  const visibility = byId("doc-public").checked ? "public" : "private";
  const r = await api("/api/documents", "POST", { title, body, visibility });
  if (r.ok) { byId("doc-title").value = ""; byId("doc-body").value = ""; toggleNew(); toast("문서를 저장했어요.", "ok"); loadDocs(); }
}
async function search(offset = 0) {
  const q = byId("search-q").value;
  if (!q) return;
  const r = await api("/api/documents/search?q=" + encodeURIComponent(q) + `&limit=50&offset=${offset}`);
  byId("search-panel").classList.remove("hidden");
  if (!r.ok) return;
  byId("search-results").innerHTML = r.data.length
    ? r.data.map(d => `<div class="doc"><div class="fic">🔎</div><div class="meta"><div class="t">${esc(d.title)}</div><div class="s">${esc(d.body || "")}</div></div><div class="act">${openButton(d.id)}</div></div>`).join("")
    : '<div class="empty">검색 결과가 없어요.</div>';
  byId("search-results").insertAdjacentHTML("beforeend", pager("search-page", offset, r.data.length));
}
function clearSearch() { byId("search-panel").classList.add("hidden"); byId("search-q").value = ""; }

async function viewDoc(id) {
  const r = await api("/api/documents/" + id);
  const box = byId("doc-detail");
  box.classList.remove("hidden");
  if (!r.ok) { box.innerHTML = `<div class="bd"><div class="empty">${esc(r.data.error || "열 수 없어요.")}</div></div>`; return; }
  const d = r.data;
  const atts = (d.attachments || []).map(a => `<div class="attach"><span class="fi">📎</span> ${esc(a.filename)} <a class="btn btn-ghost btn-sm ml-auto" href="/api/files/download?name=${encodeURIComponent(a.stored_name || a.filename)}">다운로드</a></div>`).join("");
  box.innerHTML = `
    <div class="bd doc-detail">
      <h1>${esc(d.title)}</h1>
      <div class="docmeta">${docBadge(d.visibility)} · 소유자 #${Number(d.owner_id)} · 문서 #${Number(d.id)}
        <button class="btn btn-ghost btn-sm ml-auto" data-action="close-detail">닫기</button></div>
      <div class="body">${esc(d.body || "")}</div>
      ${atts ? `<div class="attach-list">${atts}</div>` : ""}
      <h3 class="comments-title">댓글</h3>
      <div id="comments"></div>
      <div class="row mt-12"><input id="comment-body" placeholder="댓글을 입력하세요"><button class="btn" data-action="add-comment" data-id="${Number(id)}">등록</button></div>
    </div>`;
  loadComments(id);
}
async function loadComments(docId, offset = 0) {
  const r = await api(`/api/documents/${docId}/comments?limit=50&offset=${offset}`);
  if (!r.ok) return;
  const box = byId("comments");
  if (!r.data.length) { box.innerHTML = '<div class="comment-empty">댓글이 없어요.</div>' + pager("comments-page", offset, 0, docId); return; }
  box.innerHTML = r.data.map(c => `<div class="comment"><div class="av">${initials(c.author)}</div><div class="cb"><div class="ca">${esc(c.author)}</div><div class="ct">${esc(c.body)}</div></div></div>`).join("") + pager("comments-page", offset, r.data.length, docId);
}
async function addComment(docId) {
  const el = byId("comment-body");
  await api(`/api/documents/${docId}/comments`, "POST", { body: el.value });
  el.value = ""; loadComments(docId);
}

/* ---------- 프로필 ---------- */
async function loadProfile() {
  const r = await api("/api/profile");
  if (!r.ok) return;
  const p = r.data;
  byId("profile-info").innerHTML = `
    <dt>아이디</dt><dd>${esc(p.username)}</dd>
    <dt>이름</dt><dd>${esc(p.full_name || "-")}</dd>
    <dt>이메일</dt><dd>${esc(p.email || "-")}</dd>
    <dt>전화번호</dt><dd>${esc(p.phone || "-")}</dd>
    <dt>주민등록번호</dt><dd>${esc(p.ssn || "-")}</dd>
    <dt>역할</dt><dd>${p.role === "admin" ? '<span class="badge adm">관리자</span>' : '<span class="badge usr">일반</span>'}</dd>`;
  byId("pf-fullname").value = p.full_name || "";
  byId("pf-email").value = p.email || "";
  byId("pf-phone").value = p.phone || "";
}
async function saveProfile() {
  const body = {
    full_name: byId("pf-fullname").value, email: byId("pf-email").value,
    phone: byId("pf-phone").value, ssn: byId("pf-ssn").value,
  };
  const r = await api("/api/profile", "PUT", body);
  if (r.ok) { toast("프로필을 저장했어요.", "ok"); loadProfile(); }
}

/* ---------- 관리자 ---------- */
async function loadAdmin(offset = 0) {
  const u = await api(`/api/admin/users?limit=50&offset=${offset}`);
  const ut = byId("admin-users");
  if (u.ok) ut.innerHTML = `<tr><th>사용자</th><th>역할</th><th>이메일</th><th>전화</th></tr>` +
    u.data.map(x => `<tr><td><span class="av-sm">${initials(x.username)}</span>${esc(x.username)}</td><td>${x.role === "admin" ? '<span class="badge adm">관리자</span>' : '<span class="badge usr">일반</span>'}</td><td>${esc(x.email || "-")}</td><td>${esc(x.phone || "-")}</td></tr>`).join("");
  else ut.innerHTML = `<tr><td>${esc(u.data.error || "권한이 없어요.")}</td></tr>`;
  const d = await api(`/api/admin/documents?limit=50&offset=${offset}`);
  const dt = byId("admin-docs");
  if (d.ok) dt.innerHTML = `<tr><th>제목</th><th>소유자</th><th>공개</th></tr>` +
    d.data.map(x => `<tr><td>📄 ${esc(x.title)}</td><td>${esc(x.owner)}</td><td>${docBadge(x.visibility)}</td></tr>`).join("");
  if (u.ok && d.ok) dt.insertAdjacentHTML("beforeend", `<tr><td colspan="3">${pager("admin-page", offset, Math.max(u.data.length, d.data.length))}</td></tr>`);
}

/* ---------- 이벤트 위임 (CSP: 인라인 onclick 대신 data-action) ---------- */
const ACTIONS = {
  "docs-page": (el) => loadDocs(Number(el.dataset.offset)),
  "search-page": (el) => search(Number(el.dataset.offset)),
  "comments-page": (el) => loadComments(Number(el.dataset.id), Number(el.dataset.offset)),
  "admin-page": (el) => loadAdmin(Number(el.dataset.offset)),
  "show-tab": (el) => showTab(el.dataset.tab),
  "login": login,
  "register": register,
  "logout": logout,
  "show-view": (el) => showView(el.dataset.view),
  "toggle-new": toggleNew,
  "create-doc": createDoc,
  "clear-search": clearSearch,
  "view-doc": (el) => viewDoc(Number(el.dataset.id)),
  "close-detail": () => byId("doc-detail").classList.add("hidden"),
  "add-comment": (el) => addComment(Number(el.dataset.id)),
  "save-profile": saveProfile,
};
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-action]");
  const handler = el && ACTIONS[el.dataset.action];
  if (handler) handler(el);
});
byId("search-q").addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

/* ---------- 세션 복구 ---------- */
(async () => { const r = await api("/api/auth/me"); if (r.ok) { currentUser = r.data; enterApp(); } })();
