let currentUser = null;

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: {} };
  if (body) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}
// 출력 이스케이프: innerHTML 에 넣는 모든 사용자 제어 값에 적용 (XSS 방지)
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const initials = (s) => (s || "?").trim().charAt(0).toUpperCase();
function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind; t.textContent = msg;
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

/* ---------- 로그인 ---------- */
function showTab(t) {
  document.getElementById("login-form").classList.toggle("hidden", t !== "login");
  document.getElementById("register-form").classList.toggle("hidden", t !== "register");
  document.getElementById("tab-login").classList.toggle("active", t === "login");
  document.getElementById("tab-register").classList.toggle("active", t === "register");
}
async function login() {
  const username = document.getElementById("login-username").value;
  const password = document.getElementById("login-password").value;
  const r = await api("/api/auth/login", "POST", { username, password });
  if (r.ok) { currentUser = r.data; enterApp(); }
  else setMsg(r.data.error || "로그인 실패", "err");
}
async function register() {
  const username = document.getElementById("reg-username").value;
  const password = document.getElementById("reg-password").value;
  const full_name = document.getElementById("reg-fullname").value;
  const r = await api("/api/auth/register", "POST", { username, password, full_name });
  if (r.ok) { currentUser = r.data; enterApp(); }
  else setMsg(r.data.error || "가입 실패", "err");
}
function setMsg(m, k) { const e = document.getElementById("auth-msg"); e.textContent = m; e.className = "msg " + k; }
async function logout() {
  await api("/api/auth/logout", "POST");
  currentUser = null;
  document.getElementById("app").classList.add("hidden");
  document.getElementById("auth").classList.remove("hidden");
}
function enterApp() {
  document.getElementById("auth").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  document.getElementById("me-name").textContent = currentUser.username;
  document.getElementById("me-role").textContent = currentUser.role === "admin" ? "관리자" : "일반 사용자";
  document.getElementById("me-av").textContent = initials(currentUser.username);
  const isAdmin = currentUser.role === "admin";
  document.getElementById("nav-admin").style.display = isAdmin ? "flex" : "none";
  document.getElementById("admin-sec").style.display = isAdmin ? "block" : "none";
  showView("docs");
}

/* ---------- 뷰 전환 ---------- */
const TITLES = { docs: "문서", profile: "내 프로필", admin: "관리자" };
function showView(v) {
  for (const id of ["docs", "profile", "admin"]) {
    document.getElementById("view-" + id).classList.toggle("hidden", id !== v);
    const n = document.getElementById("nav-" + id); if (n) n.classList.toggle("active", id === v);
  }
  document.getElementById("topbar-title").textContent = TITLES[v];
  if (v === "docs") loadDocs();
  if (v === "profile") loadProfile();
  if (v === "admin") loadAdmin();
}
function toggleNew() { document.getElementById("new-panel").classList.toggle("hidden"); }

/* ---------- 문서 ---------- */
function docBadge(vis) { return vis === "public" ? '<span class="badge pub">● 공개</span>' : '<span class="badge pri">● 비공개</span>'; }
async function loadDocs() {
  const r = await api("/api/documents");
  if (!r.ok) return;
  const docs = r.data;
  const pub = docs.filter(d => d.visibility === "public").length;
  const mine = docs.filter(d => d.owner_id === currentUser.id).length;
  document.getElementById("stats").innerHTML = [
    ["전체 문서", docs.length, "🗂️", "var(--orange-l)", "var(--orange)"],
    ["내 문서", mine, "📝", "var(--blue-l)", "var(--blue)"],
    ["공개 문서", pub, "🌐", "var(--green-l)", "var(--green)"],
    ["팀원", "4+", "👥", "#efe9f7", "#6b4fa0"],
  ].map(s => `<div class="stat"><div class="k"><span class="ic" style="background:${s[3]};color:${s[4]}">${s[2]}</span>${s[0]}</div><div class="v">${s[1]}</div></div>`).join("");

  if (!docs.length) { document.getElementById("doc-list").innerHTML = '<div class="empty"><div class="big">🗂️</div>아직 문서가 없어요.</div>'; return; }
  document.getElementById("doc-list").innerHTML = docs.map(d => `
    <div class="doc">
      <div class="fic">📄</div>
      <div class="meta"><div class="t">${esc(d.title)}</div><div class="s">${docBadge(d.visibility)} &nbsp;·&nbsp; 문서 #${d.id}</div></div>
      <div class="act"><button class="btn btn-ghost btn-sm" onclick="viewDoc(${d.id})">열기</button></div>
    </div>`).join("");
}
async function createDoc() {
  const title = document.getElementById("doc-title").value;
  const body = document.getElementById("doc-body").value;
  const visibility = document.getElementById("doc-public").checked ? "public" : "private";
  const r = await api("/api/documents", "POST", { title, body, visibility });
  if (r.ok) { document.getElementById("doc-title").value = ""; document.getElementById("doc-body").value = ""; toggleNew(); toast("문서를 저장했어요.", "ok"); loadDocs(); }
}
async function search() {
  const q = document.getElementById("search-q").value;
  if (!q) return;
  const r = await api("/api/documents/search?q=" + encodeURIComponent(q));
  document.getElementById("search-panel").classList.remove("hidden");
  if (!r.ok) return;
  document.getElementById("search-results").innerHTML = r.data.length
    ? r.data.map(d => `<div class="doc"><div class="fic">🔎</div><div class="meta"><div class="t">${esc(d.title)}</div><div class="s">${esc(d.body || "")}</div></div><div class="act"><button class="btn btn-ghost btn-sm" onclick="viewDoc(${d.id})">열기</button></div></div>`).join("")
    : '<div class="empty">검색 결과가 없어요.</div>';
}
function clearSearch() { document.getElementById("search-panel").classList.add("hidden"); document.getElementById("search-q").value = ""; }

async function viewDoc(id) {
  const r = await api("/api/documents/" + id);
  const box = document.getElementById("doc-detail");
  box.classList.remove("hidden");
  if (!r.ok) { box.innerHTML = `<div class="bd"><div class="empty">${esc(r.data.error || "열 수 없어요.")}</div></div>`; return; }
  const d = r.data;
  const atts = (d.attachments || []).map(a => `<div class="attach"><span class="fi">📎</span> ${esc(a.filename)} <a class="btn btn-ghost btn-sm" style="margin-left:auto" href="/api/files/download?name=${encodeURIComponent(a.stored_name || a.filename)}">다운로드</a></div>`).join("");
  box.innerHTML = `
    <div class="bd doc-detail">
      <h1>${esc(d.title)}</h1>
      <div class="docmeta">${docBadge(d.visibility)} · 소유자 #${d.owner_id} · 문서 #${d.id}
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="document.getElementById('doc-detail').classList.add('hidden')">닫기</button></div>
      <div class="body">${esc(d.body || "")}</div>
      ${atts ? `<div style="margin-bottom:18px">${atts}</div>` : ""}
      <h3 style="font-size:15px;margin:0 0 10px">댓글</h3>
      <div id="comments"></div>
      <div class="row" style="margin-top:12px"><input id="comment-body" placeholder="댓글을 입력하세요"><button class="btn" onclick="addComment(${id})">등록</button></div>
    </div>`;
  loadComments(id);
}
async function loadComments(docId) {
  const r = await api(`/api/documents/${docId}/comments`);
  if (!r.ok) return;
  const box = document.getElementById("comments");
  if (!r.data.length) { box.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:6px 0">첫 댓글을 남겨보세요.</div>'; return; }
  box.innerHTML = r.data.map(c => `<div class="comment"><div class="av">${initials(c.author)}</div><div class="cb"><div class="ca">${esc(c.author)}</div><div class="ct">${esc(c.body)}</div></div></div>`).join("");
}
async function addComment(docId) {
  const el = document.getElementById("comment-body");
  await api(`/api/documents/${docId}/comments`, "POST", { body: el.value });
  el.value = ""; loadComments(docId);
}

/* ---------- 프로필 ---------- */
async function loadProfile() {
  const r = await api("/api/profile");
  if (!r.ok) return;
  const p = r.data;
  document.getElementById("profile-info").innerHTML = `
    <dt>아이디</dt><dd>${esc(p.username)}</dd>
    <dt>이름</dt><dd>${esc(p.full_name || "-")}</dd>
    <dt>이메일</dt><dd>${esc(p.email || "-")}</dd>
    <dt>전화번호</dt><dd>${esc(p.phone || "-")}</dd>
    <dt>주민등록번호</dt><dd>${esc(p.ssn || "-")}</dd>
    <dt>역할</dt><dd>${p.role === "admin" ? '<span class="badge adm">관리자</span>' : '<span class="badge usr">일반</span>'}</dd>`;
  document.getElementById("pf-fullname").value = p.full_name || "";
  document.getElementById("pf-email").value = p.email || "";
  document.getElementById("pf-phone").value = p.phone || "";
}
async function saveProfile() {
  const body = { full_name: pf_fullname.value, email: pf_email.value, phone: pf_phone.value, ssn: pf_ssn.value };
  const r = await api("/api/profile", "PUT", body);
  if (r.ok) { toast("프로필을 저장했어요.", "ok"); loadProfile(); }
}

/* ---------- 관리자 ---------- */
async function loadAdmin() {
  const u = await api("/api/admin/users");
  const ut = document.getElementById("admin-users");
  if (u.ok) ut.innerHTML = `<tr><th>사용자</th><th>역할</th><th>이메일</th><th>전화</th></tr>` +
    u.data.map(x => `<tr><td><span class="av-sm">${initials(x.username)}</span>${esc(x.username)}</td><td>${x.role === "admin" ? '<span class="badge adm">관리자</span>' : '<span class="badge usr">일반</span>'}</td><td>${esc(x.email || "-")}</td><td>${esc(x.phone || "-")}</td></tr>`).join("");
  else ut.innerHTML = `<tr><td>${esc(u.data.error || "권한이 없어요.")}</td></tr>`;
  const d = await api("/api/admin/documents");
  const dt = document.getElementById("admin-docs");
  if (d.ok) dt.innerHTML = `<tr><th>제목</th><th>소유자</th><th>공개</th></tr>` +
    d.data.map(x => `<tr><td>📄 ${esc(x.title)}</td><td>${esc(x.owner)}</td><td>${docBadge(x.visibility)}</td></tr>`).join("");
}

/* ---------- 세션 복구 ---------- */
(async () => { const r = await api("/api/auth/me"); if (r.ok) { currentUser = r.data; enterApp(); } })();
