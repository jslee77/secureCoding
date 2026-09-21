// 플래그 현황판 — 입력한 값은 이 브라우저(localStorage)에만 저장된다.
const KEY = "securedocs_flags";
const CSRF_HEADERS = { "X-Requested-With": "SecureDocs" };

function getFound() { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; } }
function setFound(a) { localStorage.setItem(KEY, JSON.stringify([...new Set(a)])); }

async function postJson(path, body) {
  const r = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json", ...CSRF_HEADERS },
    body: JSON.stringify(body) });
  return r.json();
}

async function submitFlag() {
  const input = document.getElementById("flag-input");
  const v = input.value.trim();
  if (!v) return;
  const d = await postJson("/api/flags/check", { value: v });
  const msg = document.getElementById("flag-msg");
  msg.classList.toggle("ok", d.ok);
  msg.classList.toggle("err", !d.ok);
  if (d.ok) {
    setFound([...getFound(), v]);
    msg.textContent = "🎉 " + d.message;
    input.value = "";
    render();
  } else {
    msg.textContent = d.message;
  }
}

function resetFlags() { setFound([]); render(); document.getElementById("flag-msg").textContent = ""; }

// innerHTML 대신 DOM API 로 그린다 (진행 막대 너비도 style 속성이 아닌 CSSOM 으로 설정).
function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function render() {
  const d = await postJson("/api/flags/score", { values: getFound() });
  const overall = document.getElementById("overall");
  overall.replaceChildren(el("h3", "flags-total", `전체: ${d.total.got} / ${d.total.all}`));
  const board = document.getElementById("board");
  board.replaceChildren(...Object.entries(d.modules).map(([name, s]) => {
    const item = el("div", "item");
    item.append(el("b", "", name), ` — ${s.got}/${s.total}`);
    const bar = el("div", "progress-bar");
    bar.style.width = `${Math.round((s.got / s.total) * 100)}%`;
    const track = el("div", "progress");
    track.append(bar);
    item.append(track);
    return item;
  }));
}

document.getElementById("flag-submit").addEventListener("click", submitFlag);
document.getElementById("flag-reset").addEventListener("click", resetFlags);
document.getElementById("flag-input").addEventListener("keydown", (e) => { if (e.key === "Enter") submitFlag(); });
render();
