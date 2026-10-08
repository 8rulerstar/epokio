"use strict";
// 공통(상태·API·토큰 전달·새로 고침) + 학습 목록·상세·곡선. 언어(t)와 저장소(LS)는 lang.js에 있다.
// ── 상태 ──
const S = { smooth: +LS.epokioSmooth || 0, tab: "runs", runs: [], sel: null, detail: {}, curve: 1, picks: [], cmpKey: "", events: [], seen: +LS.epokioSeen || 0, sys: null, label: "",
            token: LS.epokioToken || "", locked: false, pythons: null, python: LS.epokioPython || "", schema: {}, all: false, jobs: null, logs: {}, diag: {},
            task: LS.epokioTask || "detect", size: LS.epokioSize || "n", setupId: null, again: null,
            evSeq: 0, gen: 0, sortScore: !!LS.epokioSortScore, lastMain: "", q: "", hooks: null, phoneOpen: false };
const STATE = { running: [t("Training"), "var(--green)"], starting: [t("Starting"), "var(--purple)"], stalled: [t("Stalled"), "var(--orange)"],
                failed: [t("Failed"), "var(--red)"], stopped: [t("Stopped"), "var(--soft)"], done: [t("Done"), "var(--accent)"] };
// 계획 에폭을 모르는 학습(Keras·Lightning·TensorBoard)은 끝난 것과 멈춘 것을 구별할 수 없다. ★끝난 학습이 전부 '중단됨'으로 떴다
const stateOf = (r) => (r.state === "stopped" && r.total == null ? [t("Ended"), "var(--soft)"] : STATE[r.state] || [esc(r.state), "var(--soft)"]);
const RANK = { running: 0, starting: 1, stalled: 2, failed: 3, stopped: 4, done: 5 };
const COLORS = ["var(--brand)", "var(--brand2)", "var(--good)", "var(--warn)", "var(--mixup)", "var(--gold)", "var(--info)", "var(--bad)"];   // 토큰 순서(앱의 chartPalette와 같다)
const GENERIC = /^(train|exp|val|predict|run|detect|segment|pose|classify)\d*$/;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const f3 = (v) => v == null ? "–" : (+v).toFixed(3);

/// 같은 agent의 API. 토큰이 있으면 모든 요청에 싣는다(헤더로만. 주소에는 싣지 않는다).
/// 401이면 Locked를 던진다. 부른 쪽이 needToken()으로 그 자리에서 묻는다
class Locked extends Error {}
async function api(p, method, body) {
  // ★agent 문장(검진·해설·진단)도 화면과 같은 언어로 받는다. 안 실으면 브라우저 언어로 와서 한 카드 안에 섞였다
  const headers = { "Accept-Language": LANG };
  if (S.token) headers.Authorization = "Bearer " + S.token;
  if (body) headers["Content-Type"] = "application/json";
  const r = await fetch(p, { method: method || "GET", headers, body: body ? JSON.stringify(body) : undefined, cache: "no-store" });
  if (r.status === 401) throw new Locked(t("This needs this machine's token"));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j.error || t("request failed ({status})", { status: r.status })) + (j.hint ? ". " + j.hint : ""));
  return j;
}
/// 실행 요청(POST). 토큰이 없거나 틀렸으면 한 번 묻고 다시 보낸다(검수·스윕·계보 화면이 쓴다)
async function apiPost(p, body) {
  try { return await api(p, "POST", body || {}); }
  catch (e) {
    if (!(e instanceof Locked)) throw e;
    S.locked = true;
    if (!await needToken()) throw new Error(t("A token is needed for this action."));
    return api(p, "POST", body || {});
  }
}
/// 그림(<img>)은 헤더를 못 보내서, 맞는 토큰이면 agent가 HttpOnly 쿠키를 준다(자바스크립트는 쿠키를 읽을 수 없다)
const login = () => fetch("login", { method: "POST", headers: { Authorization: "Bearer " + S.token } }).catch(() => {});

/// 파이썬 환경 목록을 고르기 칸에 채운다(ultralytics 없는 것은 고를 수 없게)
async function fillPythons(sel) {
  let envs = []; try { envs = (await api("pythons")).envs || []; } catch {}
  sel.innerHTML = envs.map((e) => `<option value="${esc(e.path)}" ${e.ready ? "" : "disabled"}>${esc(e.name)}${e.device ? " · " + esc(e.device) : ""}${e.ready ? "" : " (" + t("no ultralytics") + ")"}</option>`).join("")
    || `<option value="">${t("No Python with ultralytics found")}</option>`;
  sel.animate?.([{ opacity: .4 }, { opacity: 1 }], { duration: 250 });
}
/// x축 단위. step으로 적는 학습(/runs의 x_axis "step")은 epoch 자리에 step 번호가 온다. 천 단위 쉼표로 보인다
const isStep = (r) => r?.x_axis === "step";
const xnum = (r, v) => v == null ? "?" : isStep(r) ? Number(v).toLocaleString(LOCALE) : v;
const xprog = (r) => t(isStep(r) ? "step {e}/{n}" : "epoch {e}/{n}", { e: xnum(r, r.epoch), n: xnum(r, r.total) });
/// 여러 학습의 단위 이름: 전부 step이면 step, 섞이면 둘 다
const axisLabel = (runs, epoch, step, mixed) => { const n = runs.filter(isStep).length; return t(n === 0 ? epoch : n === runs.length ? step : mixed); };
const xname = (r) => isStep(r) ? (v) => t("step {n}", { n: xnum(r, v) }) : undefined;
/// 짧은 알림(아래 가운데). bad면 빨강
function toast(text, bad, action) {
  document.querySelector(".toast")?.remove();
  const el = document.createElement("div"); el.className = "toast" + (bad ? " bad" : ""); el.textContent = text;
  if (action) {                                        // 예: 되돌리기
    const b = document.createElement("button"); b.className = "toast-act"; b.textContent = action.title;
    b.onclick = () => { el.remove(); action.run(); }; el.append(b);
  }
  document.body.append(el); setTimeout(() => el.remove(), action ? 6000 : bad ? 6000 : 3200);
}
/// 실행 버튼 공통: 누르는 동안 버튼이 숨 쉬고(busy), 끝나면 초록 ok·실패면 흔들림(bad)으로 잠깐 답한다
async function act(btn, work, done) {
  if (btn) { btn.disabled = true; btn.classList.remove("ok", "bad"); btn.classList.add("busy"); }
  const flash = (c) => { if (!btn) return; btn.classList.add(c); setTimeout(() => btn.classList.remove(c), 700); };
  try { const r = await work(); if (done) toast(typeof done === "function" ? done(r) : done); flash("ok"); return r; }
  catch (e) { toast(e.message, true); flash("bad"); } finally { if (btn) { btn.disabled = false; btn.classList.remove("busy"); } }
}

function dur(s) {
  if (s == null) return "–"; s = Math.round(s);
  // ★반올림하면 3,570초가 '60분'이 됐고, 하루가 넘으면 시간이 사라졌다('1일'). 내림으로, 날에는 시간도
  if (s < 60) return t("{n}s", { n: s }); if (s < 3600) return t("{n}m", { n: Math.floor(s / 60) });
  if (s < 86400) { const m = Math.floor(s % 3600 / 60); return m ? t("{h}h {m}m", { h: Math.floor(s / 3600), m }) : t("{n}h", { n: Math.floor(s / 3600) }); }
  const h = Math.floor(s % 86400 / 3600);
  return h ? t("{d}d {h}h", { d: Math.floor(s / 86400), h }) : t("{n}d", { n: Math.floor(s / 86400) });
}
function display(r) {           // 'train'처럼 흔한 이름이면 위 폴더를 붙인다(앱과 같은 규칙)
  if (r.display) return r.display;                  // agent가 정한 이름(scan.display_name)이 있으면 그것
  if (!GENERIC.test(r.name)) return r.name;
  const parts = r.path.split(/[\\/]/).slice(0, -1).reverse().filter((p) => !["runs", "detect", "segment", "pose", "classify", "obb"].includes(p));
  return parts[0] ? parts[0] + "/" + r.name : r.name;
}
// 열 이름은 agent가 보낸 column_info로 부른다(형식 지식은 agent의 schema.py 한 곳).
// column_info가 없을 때(옛 agent·대표 점수 이름만 있을 때)만 글자로 다듬는다: val/val_loss → "val loss"(★"val val"로 보였다)
const pretty = (k, d) => {
  const i = d && d.column_info && d.column_info[k];
  // ★한국어 화면에 "train box", "precision · Pose"처럼 영어로 나왔다. 쪽·이름·머리를 각각 번역한다(모르는 열 이름은 그대로)
  if (i) { const s = i.side ? t(i.side) + " " + t(i.name) : t(i.name); return i.head ? s + " · " + t(i.head) : s; }
  return String(k || "").replace(/^(val|train)\/\1_/, "$1/").replace("metrics/", "").replace("_loss", "").replace("(B)", " · " + t("Box")).replace("(P)", " · " + t("Pose")).replace("(M)", " · " + t("Mask")).replace("/", " ");
};
const kindOf = (k, d) => (d && d.column_info && d.column_info[k] || {}).kind;
/// 열(열 이름·epoch 칸 등) 중 점수 열인지(agent column_info)
const isScore = (k, d) => kindOf(k, d) === "score";

// ── 데이터 ──
// 한 번에 하나만 돈다. ★느린 응답 중에 4초 타이머가 또 돌면 같은 since로 두 번 받아 알림이 두 개씩 쌓였다.
// 도는 중에 버튼 뒤 새로 고침이 오면 끝난 뒤 한 번 더 돈다(방금 한 일이 보이게)
let refreshing = null, refreshAgain = false;
function refresh(periodic) {
  if (refreshing) { refreshAgain = refreshAgain || !periodic; return refreshing; }
  refreshing = (async () => {
    try { await refreshOnce(periodic); while (refreshAgain) { refreshAgain = false; await refreshOnce(false); } }
    finally { refreshing = null; }
  })();
  return refreshing;
}
async function refreshOnce(periodic) {
  try {
    const [r, s, e] = await Promise.all([api("runs?lite=1"), api("system"), api("events?since=" + S.evSeq)]);
    S.label = r.label; S.runs = r.runs.sort((a, b) => (RANK[a.state] ?? 9) - (RANK[b.state] ?? 9) || a.idle - b.idle);
    S.sys = s.now;
    await loadSSH();                                                    // SSH 서버 상태(목록 아래 칸). ★맥 앱에만 있었다
    // 알림은 새로 온 것만 받는다(★매 4초 200개를 통째로 받았다). agent를 다시 켜면 번호가 1부터 다시 시작한다
    // boot가 바뀌면 다시 켠 것이다. ★번호만 보면, 탭을 숨긴 사이 새 번호가 옛 커서를 넘어서면 앞의 알림을 조용히 건너뛰었다
    if ((e.boot && S.boot && e.boot !== S.boot) || e.seq < S.evSeq) { S.boot = e.boot; S.evSeq = 0; S.events = []; S.seen = 0; LS.epokioSeen = 0; return refreshOnce(periodic); }
    S.boot = e.boot;
    if (e.seq < S.seen || (e.boot && LS.epokioBoot && LS.epokioBoot !== e.boot)) { S.seen = 0; LS.epokioSeen = 0; }   // ★안 그러면 다시 켠 뒤의 알림이 전부 '읽음'으로 묻혔다
    if (e.boot) LS.epokioBoot = e.boot;
    // 새 알림은 화면 읽기 프로그램에도 알린다(처음 불러온 옛 알림은 빼고). ★예전엔 대기열·알림 변화가 소리 없이 지나갔다
    if (S.evSeq && e.events.length) { const last = e.events[e.events.length - 1]; $("#sr").textContent = (EV[last.kind] || [last.kind])[0] + (last.run?.name ? ": " + last.run.name : ""); }
    S.events = e.events.slice().reverse().concat(S.events).slice(0, 200); S.evSeq = e.seq;
    if (!S.sel && S.runs[0]) S.sel = S.runs[0].path;
    // 대기열 작업도 센다. ★'0개 진행 중'인데 대기열에서는 작업이 돌고 있었다(설치·내보내기·스크립트는 학습 목록에 없다)
    const jr = (S.jobs || []).filter((j) => j.state === "running").length, jq = (S.jobs || []).filter((j) => j.state === "queued").length;
    $("#where").textContent = r.label + " · " + t("{n} active", { n: S.runs.filter((x) => RANK[x.state] <= 1).length })
      + (jr || jq ? " · " + t("queue: {r} running, {q} waiting", { r: jr, q: jq }) : "");
    $("#where").classList.remove("down");
    const live = new Set(S.runs.map((x) => x.path));                    // 사라진 학습의 상세는 버린다
    for (const p of Object.keys(S.detail)) if (!live.has(p)) delete S.detail[p];
    S.down = false; S.at = Date.now();
  } catch (e) {
    // 네트워크에 연 agent는 보기에도 토큰을 요구한다. 그 자리에서 한 번 묻는다
    if (e instanceof Locked && !periodic && !S.asked) { S.asked = true; if (await needToken(t("A token is needed to view this machine."))) return refreshOnce(false); }
    // ★PC가 자거나 agent가 죽으면 옛 값("Training · 8m left")이 살아 있는 것처럼 그대로 보였다
    S.down = true; S.downWhy = e instanceof TypeError ? "" : e.message;   // TypeError = 연결 자체가 안 됨
    // ★작은 회색 글씨뿐이라 옛 수치·'도는 중' 작업이 살아 있는 것처럼 보였다
    $("#where").textContent = t("Lost connection to {machine}", { machine: S.label || t("this machine") })
      + (S.at ? " · " + t("showing the state at {time}", { time: new Date(S.at).toLocaleTimeString(LOCALE, HM) }) : "");
    $("#where").classList.add("down");
  }
  $("#main").classList.toggle("offline", !!S.down);
  if (S.token && !S.locked) await loadJobs();         // 대기열은 토큰이 있을 때만 (없으면 묻지 않는다)
  drawSys(); drawBadge(); drawBusy();
  // 검수·스윕·표는 자기 화면이 스스로 새로 고친다(4초마다 다시 그리면 슬라이더·열린 창이 날아간다)
  if (S.tab === "runs") drawRuns(periodic); else if (S.tab === "compare") drawCompare(periodic);
  else if (S.tab === "train") { if (!periodic) drawTrain(); else watchSetup(); }   // ★주기 갱신으로 폼을 다시 그리면 입력하던 값이 지워진다
  else if (S.tab === "queue") drawQueue(periodic); else if (S.tab === "inbox") drawInbox(periodic);
}
async function loadJobs() {
  try {
    S.jobs = (await api("jobs")).jobs;
    const ids = new Set(S.jobs.map((j) => j.id));                      // 목록에서 빠진 작업의 로그·진단은 버린다
    for (const c of [S.logs, S.diag]) for (const id of Object.keys(c)) if (!ids.has(id)) delete c[id];
  } catch (e) { if (e instanceof Locked) S.locked = true; }
}
/// 학습 상세. 에폭이나 상태가 바뀔 때만 다시 받는다
///   ★예전엔 도는 학습이면 4초마다 받고(에폭은 몇 분에 한 번 바뀐다), 끝난 학습은 끝나기 전 것을 계속 보여 줬다
///   (ultralytics는 마지막 에폭 뒤에 그림을 쓴다). 막 끝난 학습은 5분 동안 30초마다 한 번 더 받는다
async function detail(r) {
  const k = r.epoch + "|" + r.state, c = S.detail[r.path], now = Date.now();
  const fresh = c && c.k === k && (c.d ? r.idle > 300 || now - c.at < 30000 : now - c.at < 30000);   // 실패는 30초 뒤 다시
  if (!fresh) {
    let d = null; try { d = await api("run?path=" + encodeURIComponent(r.path)); } catch { }
    S.detail[r.path] = { k, d, at: now };
  }
  return S.detail[r.path].d;
}
let pressing = false;
addEventListener("pointerdown", () => { pressing = true; }, true);
addEventListener("pointerup", () => { pressing = false; }, true);
addEventListener("pointercancel", () => { pressing = false; }, true);
/// #main을 바꾼다. 주기 갱신이면 같은 내용일 때, 사용자가 누르거나 고르거나 곡선을 읽는 중일 때는 건드리지 않는다
///   ★예전엔 4초마다 통째로 다시 그려 목록 스크롤이 맨 위로 튀고, 열린 선택 상자가 닫히고, 읽던 로그가 맨 아래로 갔다
function setMain(html, periodic) {
  const m = $("#main");
  if (periodic) {
    if (html === S.lastMain) return false;
    const a = document.activeElement;
    if (pressing) return false;
    if (a && m.contains(a) && (/^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName) || a.classList?.contains("chart"))) return false;
  }
  const keep = {};
  m.querySelectorAll("[data-keep]").forEach((el) => keep[el.dataset.keep] = [el.scrollTop, el.scrollHeight - el.scrollTop - el.clientHeight < 20]);
  m.classList.toggle("static", !!periodic);                              // 주기 갱신은 나타남 애니메이션을 다시 틀지 않는다
  // 다시 그려도 키보드 초점을 같은 것에 둔다. ★예전엔 행에서 Enter·슬라이더·곡선 전환 뒤 초점이 BODY로 떨어져
  //   키보드 사용자가 자리를 잃었다(WCAG 2.4.3). 같은 것 = 같은 id, 또는 같은 data-path, 또는 같은 작업의 같은 버튼
  const a = document.activeElement, focus = a && m.contains(a) && a !== m
    ? (a.id ? "#" + CSS.escape(a.id) : a.dataset.path != null ? `[data-path="${CSS.escape(a.dataset.path)}"]`
      : a.dataset.op && a.closest(".job") ? `.job[data-id="${CSS.escape(a.closest(".job").dataset.id)}"] [data-op="${a.dataset.op}"]`
      : a.dataset.v != null && a.closest("[id]") ? `#${CSS.escape(a.closest("[id]").id)} [data-v="${CSS.escape(a.dataset.v)}"]` : null) : null;
  m.innerHTML = html; S.lastMain = html;
  m.querySelectorAll("[data-keep]").forEach((el) => {
    const k = keep[el.dataset.keep];
    el.scrollTop = el.classList.contains("log") && (!k || k[1]) ? el.scrollHeight : k ? k[0] : 0;   // 로그는 맨 아래에 있었을 때만 따라간다
  });
  if (focus) m.querySelector(focus)?.focus({ preventScroll: true });
  return true;
}

// ── 머리말 ──
function drawSys() {
  const s = S.sys; if (!s || S.down) { $("#sys").innerHTML = ""; return; }      // 끊기면 옛 수치를 지운다
  const g = (s.gpus || [])[0] || {}; const mem = s.mem_total ? s.mem_used / s.mem_total * 100 : null;
  const p = (v) => v == null ? "–" : Math.round(v) + "%";
  $("#sys").innerHTML = `<span>GPU <b>${p(g.util)}</b></span><span>CPU <b>${p(s.cpu)}</b></span><span>${t("MEM")} <b>${p(mem)}</b></span>${s.fan != null ? `<span title="${esc(s.fan_source === "gpu" ? t("GPU fan speed") : t("Fan speed") + (s.fan_rpm ? ` · ${s.fan_rpm} rpm` : ""))}">${s.fan_source === "gpu" ? t("GPU fan") : t("Fan")} <b>${p(s.fan)}</b></span>` : ""}<span>${esc(g.name || s.host)}</span>`;   // 팬: 팬 있는 맥만(macfan.py)
}
function drawBadge() {
  // 알림 탭에 그리는 것 전부(시작·다시 돎은 빼고). ★디스크·GPU 경고가 빠져 있어 '디스크 거의 참'이 와도 표시가 안 켜졌다
  const n = S.events.filter((e) => e.seq > S.seen && e.kind in EV && !["started", "recovered"].includes(e.kind)).length;
  const b = $("#unread"); b.hidden = n === 0; b.textContent = n;
}
function drawBusy() {           // 대기열 탭: 돌거나 기다리는 작업 수
  const n = (S.jobs || []).filter((j) => j.state === "running" || j.state === "queued").length;
  const b = $("#busy"); b.hidden = n === 0; b.textContent = n;
}

// ── 학습 목록 + 상세 ──
function rowHTML(r, i, check) {
  const [st, c] = stateOf(r);
  const pct = r.total ? Math.min(100, r.epoch / r.total * 100) : 0;     // 총 에폭을 모르면 막대를 숨긴다(빈 막대가 0%처럼 보였다). 자리는 지켜 줄이 안 흔들린다
  const when = r.state === "running" ? t("{d} left", { d: dur(r.eta) }) : t("{d} ago", { d: dur(r.idle) });
  const box = check ? `<input type="checkbox" class="check" tabindex="-1" aria-label="${esc(t("Compare") + ": " + display(r))}" ${S.picks.includes(r.path) ? "checked" : ""}>` : `<span class="dot"></span>`;
  return `<div class="row ${r.state} ${!check && S.sel === r.path ? "on" : ""}" role="button" tabindex="0" style="--c:${c};animation-delay:${Math.min(i, 12) * 25}ms" data-path="${esc(r.path)}">
    ${box}<span class="name">${r.meta?.star ? "⭐ " : ""}${esc(display(r))}</span><span class="best" ${r.lower ? `title="${t("lower is better")}"` : ""}>${r.best != null ? r.best.toFixed(3) + (r.lower ? " ↓" : "") : ""}</span>
    ${r.total ? `<span class="bar"><i style="width:${pct}%"></i></span>` : `<span class="bar" style="visibility:hidden"></span>`}
    <span class="meta">${st} · ${xprog(r)} · ${when} · ${esc(r.source)}${(r.meta?.tags || []).map((tag) => " · #" + esc(tag)).join("")}</span></div>`;
}
async function drawRuns(periodic) {
  const g = ++S.gen;
  if (!S.runs.length) {
    // ★예전엔 연결이 끊겨도 "No runs yet"과 "--root 로 켜라"(두 번 눌러 켜는 사람에겐 없는 명령)를 보여 줬다
    if (S.down) { setMain(`<div class="card empty"><b>${t("Can't reach Epokio on this machine.")}</b><br>${S.downWhy ? esc(S.downWhy) : t("Is the helper running? On Windows, look for the Epokio icon under ^ at the right end of the taskbar, or run Epokio.exe again.")}</div>`, periodic); return; }
    if (setMain(`<div class="card empty"><b>${t("No training runs found yet.")}</b><p class="hint">${t("Add the folder where your runs are saved (the one that holds <code>runs</code>, or <code>runs</code> itself).")}</p>
      <div class="inrow" style="max-width:520px;margin:0 auto"><input class="in" id="rootpath" aria-label="${t("Folder with runs")}" placeholder="C:\\Users\\you\\projects\\yolo\\runs" spellcheck="false"><button class="btn primary" id="addroot">${t("Add folder")}</button></div>
      <div id="rootmsg" role="status"></div></div>`, periodic)) wireAddRoot();
    return;
  }
  // 보던 학습이 지워졌으면 첫 학습을 고른 것으로 한다(★S.sel이 옛 경로로 남아 목록에 선택 표시가 없었다)
  if (!S.runs.some((x) => x.path === S.sel)) S.sel = S.runs[0].path;
  // 거르면 걸린 것 중 첫 학습을 보인다(★목록에 없는 학습이 오른쪽에 남아 있었다)
  const base = filteredRuns();
  if (base.length && !base.some((x) => x.path === S.sel)) S.sel = base[0].path;
  const r = S.runs.find((x) => x.path === S.sel);
  const d = await detail(r);
  if (g !== S.gen || S.tab !== "runs") return;                   // ★받는 사이 다른 탭·다른 학습을 눌렀다. 늦게 온 그림이 덮어썼다
  // 처음엔 200개만 그린다(도는 것·최근 것이 위). ★학습 3,000개면 4초마다 3,000줄을 새로 만들고 손잡이 3,000개를 다시 달아 폰이 버벅였다
  // 점수 순으로도 본다(낮을수록 좋은 점수는 거꾸로). ★상태·시간 순뿐이라 스윕의 1등이 위로 오지 않았다
  const byScore = (a, b) => (a.best == null) - (b.best == null) || (a.lower ? a.best - b.best : b.best - a.best);
  // 이름·#태그로 거른다(비교 탭과 같은 칸). ★학습이 수백 개면 목록에서 찾을 방법이 스크롤뿐이었다
  const ordered = S.sortScore ? [...base].sort(byScore) : base;
  const shown = ordered.slice(0, S.allRows ? ordered.length : 200);
  if (!shown.includes(r) && !S.q) shown.push(r);
  const more = base.length - shown.length;
  const qbox = `<div class="inrow" style="margin:6px 8px 0"><input class="in" id="runq" type="search" aria-label="${t("Filter by name or #tag")}" placeholder="${t("Filter by name or #tag")}" value="${esc(S.q || "")}" spellcheck="false"></div>`
    + (S.q && !base.length ? `<p class="hint" style="margin:8px 12px">${t("No runs match {q}.", { q: esc(S.q) })} <button class="more" id="runqclear" style="margin:0">${t("Clear")}</button></p>` : "");
  if (!setMain(`<div class="layout"><div class="card list" data-keep="runlist">${qbox}<div class="seg" style="margin:6px 8px"><button type="button" id="sortstate" aria-pressed="${!S.sortScore}" class="${S.sortScore ? "" : "on"}">${t("Newest")}</button><button type="button" id="sortscore" aria-pressed="${!!S.sortScore}" class="${S.sortScore ? "on" : ""}">${t("Best score")}</button><button type="button" id="addfolder" title="${t("Watch another folder of runs")}">+ ${t("Folder")}</button></div>${shown.map((x, i) => rowHTML(x, i)).join("")}${more > 0 ? `<button class="btn small" id="morerows" style="margin:10px">${t("Show {n} more", { n: more })}</button>` : ""}${sshHTML()}</div>
    <div class="card detail" data-keep="detail">${detailHTML(r, d)}</div></div>`, periodic)) return;
  wireSSH();
  // 폰에서는 목록 아래에 상세가 있다. ★눌러도 화면이 안 바뀌는 것처럼 보였다
  // 손잡이는 목록에 하나만(줄마다 달지 않는다)
  $(".list").onclick = (e) => {
    if (e.target.closest("#morerows")) { S.allRows = true; drawRuns(); return; }
    if (e.target.closest("#addfolder")) { addFolder(); return; }
    if (e.target.closest("#runqclear")) { S.q = ""; drawRuns(); return; }
    if (e.target.closest("#sortscore, #sortstate")) { S.sortScore = !!e.target.closest("#sortscore"); LS.epokioSortScore = S.sortScore ? "1" : ""; drawRuns(); return; }
    const el = e.target.closest(".row"); if (!el) return;
    // 폰에서는 상세가 목록 아래라 초점도 옮긴다(★키보드로는 남은 줄 200개를 Tab으로 지나야 상세에 닿았다)
    S.sel = el.dataset.path; drawRuns().then(() => { if (innerWidth < 820) { const h = $(".detail h2"); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); } $(".detail")?.scrollIntoView({ behavior: "smooth" }); } });
  };
  $("#runq").oninput = (e) => { S.q = e.target.value; drawRuns().then(() => { const n = $("#runq"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); };
  document.querySelectorAll(".detail .seg button").forEach((b) => b.onclick = () => { S.curve = +b.dataset.v; drawRuns(); });
  const sm = $("#sm"); if (sm) sm.onchange = () => { S.smooth = +sm.value; LS.epokioSmooth = S.smooth; drawRuns(); };
  document.querySelectorAll(".gallery figure").forEach((f) => f.onclick = () => lightbox(f.dataset.src));
  bindCharts();
  const big = $(".detail .big"), was = (S.shown ||= {})[r.path];       // 값 변화: 최고 점수가 바뀌면 살짝 튄다
  if (big && was != null && was !== r.best) big.classList.add("bump");
  S.shown[r.path] = r.best;
  if (d) { bindVersions(r, d); bindPerClass(r, d); bindSnapshots(r, d); }                                         // 계보·단계 (versions.js)
  document.querySelectorAll("[data-next]").forEach((b) => b.onclick = () => queueNext(r, d, d.notes[+b.dataset.next].next));
  const rs = $("#resume");
  if (rs) rs.onclick = async () => {
    if (!await needToken()) return;                        // 그 자리에서 토큰을 묻는다
    rs.disabled = true;
    try {
      // 파이썬은 보내지 않는다: agent가 이 학습을 처음 띄운 파이썬을 고른다(★학습 화면의 파이썬으로 이어 해 버전이 바뀌었다)
      await api("jobs", "POST", { kind: "train", name: display(r), params: { model: d.last, resume: true } });
      tab("queue");
    } catch (e) {
      rs.disabled = false;
      // 토큰이 틀렸으면 토큰을 넣는 곳으로. 다른 오류는 상태에 두어 다음 새로 고침에도 남게 한다(★곧바로 지워졌다)
      if (e instanceof Locked) { S.locked = true; needToken(); return; }
      S.resumeMsg = { path: r.path, text: e.message }; drawRuns();
    }
  };
  const mb = $("#metricbox"); if (mb) mb.ontoggle = () => { S.metricOpen = mb.open; };
  const ms = $("#msave");
  if (ms) ms.onclick = async () => {
    if (!await needToken()) return;                        // 저장은 토큰이 있어야 한다
    const col = $("#mcol").value;
    try {
      const goal = $("#mgoal").value.trim() === "" ? null : Number($("#mgoal").value);   // 목표: 넘으면 폰 알림(★웹에서는 정할 수 없었다)
      const body = { path: r.path, metric: col || null, lower: !!col && $("#mdir").value === "1" };
      const g = Number.isFinite(goal) ? goal : null;
      if (g !== (r.meta?.goal ?? null)) body.goal = g;           // 그대로면 보내지 않는다(★보내면 '이미 넘음'이 지워져 알림이 또 간다)
      // 태그도 여기서 붙인다(★웹에서는 볼 수만 있고 붙일 수 없어, 스윕을 태그로 묶으려면 맥 앱이 있어야 했다)
      body.tags = $("#mtags").value.split(",").map((x) => x.trim().replace(/^#/, "")).filter(Boolean);
      await api("meta", "POST", body);
      delete S.detail[r.path]; await refresh();
    } catch (e) {
      if (e instanceof Locked) { S.locked = true; needToken(); return; }
      $("#mmsg").innerHTML = `<span style="color:var(--red)">${esc(e.message)}</span>`;
    }
  };
  const ag = $("#again"); if (ag) ag.onclick = () => { S.again = { name: display(r), args: Object.keys(d.all_args || {}).length ? d.all_args : d.args }; tab("train"); };
}
/// 감시할 폴더 더하기 (POST /roots, 토큰 필요)
/// 학습이 있어도 폴더를 더한다. ★폴더 더하기가 학습이 하나도 없을 때만 보여, 그 뒤로는 웹에서 더할 방법이 없었다
async function addFolder() {
  if (!await needToken(t("Adding a folder needs this machine's token"))) return;
  const raw = prompt(t("Folder with runs on {machine}", { machine: S.label || t("this machine") }));
  const path = raw && cleanPath(raw);
  if (!path) return;
  try { await api("roots", "POST", { path }); $("#sr").textContent = t("Added.") + " " + t("Looking for runs…"); refresh(); }
  catch (e) { if (e instanceof Locked) { S.locked = true; needToken(t("Adding a folder needs this machine's token")); return; } alert(t("Not added.") + " " + e.message); }
}
function wireAddRoot() {
  const go = async () => {
    const path = cleanPath($("#rootpath").value), box = $("#rootmsg");
    if (!path) return;
    if (!await needToken(t("Adding a folder needs this machine's token"))) return;
    try { await api("roots", "POST", { path }); box.innerHTML = `<div class="msg" style="--c:var(--green)"><b>${t("Added.")}</b> ${t("Looking for runs…")}</div>`; refresh(); }
    catch (e) { box.innerHTML = `<div class="msg" style="--c:var(--red)"><b>${t("Not added.")}</b> ${esc(e instanceof Locked ? t("The token did not work.") : e.message)}</div>`; }
  };
  $("#addroot").onclick = go; $("#rootpath").onkeydown = (e) => { if (e.key === "Enter") go(); };
}
/// 탐색기 "경로로 복사"는 "C:\...\data.yaml" 처럼 따옴표를 씌운다. ★그대로 보내면 'not found'였다
const cleanPath = (s) => s.trim().replace(/^"(.*)"$/, "$1").replace(/^'(.*)'$/, "$1").trim();

/// "다음 학습" 제안 글자: epochs 30 → 60 · from best.pt (맥 앱 NextRunButton과 같은 규칙)
function nextSummary(change, args) {
  return Object.keys(change).sort().map((k) => k === "weights" ? t("from {file}", { file: String(change[k]).split(/[\\/]/).pop() })
    : (args[k] != null && String(args[k]) !== String(change[k]) ? `${k} ${args[k]} → ${change[k]}` : `${k} ${change[k]}`)).join(" · ");
}
/// 제안대로 학습을 대기열에: 한 번 더 확인(파이썬 고르기)한다. 누르자마자 학습이 돌지 않게
function queueNext(r, d, change) {
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="sheet"><h3 style="margin-top:0">${t("Train again with a change")}</h3>
    <p class="hint">${t("Same settings as {name}, with {change}.", { name: esc(display(r)), change: "<b>" + esc(nextSummary(change, d.args)) + "</b>" })}</p>
    <div class="form"><label>Python<select id="xp"><option>${t("Looking for Python…")}</option></select></label></div>
    <div class="toolbar" style="margin:14px 0 0;justify-content:flex-end"><button class="btn" id="xc">${t("Cancel")}</button><button class="btn primary" id="xs">${t("Queue training")}</button></div></div>`;
  document.body.append(m);
  fillPythons(m.querySelector("#xp"));
  m.querySelector("#xc").onclick = () => m.remove();
  const go = m.querySelector("#xs");
  go.onclick = () => act(go, async () => {
    const params = { ...d.args, ...change };
    if (change.weights) { params.model = change.weights; delete params.weights; }
    for (const k of ["project", "name", "save_dir", "exist_ok", "resume", "device"]) delete params[k];     // 새 학습은 새 폴더에. device는 기계마다 다르다
    const res = await apiPost("jobs", { kind: "train", name: display(r) + "_next", python: m.querySelector("#xp").value, params });
    m.remove(); return res;
  }, t("Added to the queue"));
}
function detailHTML(r, d) {
  const [st, c] = stateOf(r);
  let h = `<div style="display:flex;gap:12px;align-items:flex-start"><div style="flex:1;min-width:0"><h2>${esc(display(r))}</h2>
    <div class="meta"><span class="pill" style="--c:${c}">${st}</span> · ${xprog(r)}${r.elapsed ? " · " + t("took {d}", { d: dur(r.elapsed) }) : ""} · ${esc(r.source)}</div>${paceHTML(r)}</div>
    ${r.best != null ? `<div style="text-align:right"><div class="big">${r.best.toFixed(4)}</div><div class="hint" title="${esc(r.metric_name)}">${t("Score")} · ${esc(pretty(r.metric_name, d))}</div></div>` : ""}</div>`;
  if (!d) return h + `<p class="hint">${t("No details for this run.")}</p>`;
  // 대표 점수를 고른다(W&B의 요약 지표처럼). ★손실·오류율이 대표여야 하는 학습도 '높을수록 좋은 첫 열'로만 골랐다
  const pick = Object.keys(d.columns).filter((k) => k !== "epoch" && k !== "time").sort();
  if (pick.length) h += `<details class="hint" style="margin-top:6px"${S.metricOpen ? " open" : ""} id="metricbox"><summary>${t("Main score")}: ${esc(pretty(r.metric_name, d) || t("none"))}${r.lower ? " · " + t("lower is better") : ""}</summary>
    <div class="inrow" style="margin-top:6px"><select class="in" id="mcol" aria-label="${t("Main score")}"><option value="">${t("Automatic")}</option>${pick.map((k) => `<option value="${esc(k)}"${r.meta?.metric === k ? " selected" : ""}>${esc(pretty(k, d))}</option>`).join("")}</select>
    <select class="in" id="mdir" aria-label="${t("Direction")}"><option value="0">${t("Higher is better")}</option><option value="1"${r.lower ? " selected" : ""}>${t("Lower is better")}</option></select>
    <input class="in" id="mgoal" type="number" step="any" style="max-width:110px" aria-label="${t("Target")}" placeholder="${t("Target")}" value="${r.meta?.goal ?? ""}">
    <button class="btn small" id="msave">${t("Save")}</button></div>
    <input class="in" id="mtags" style="margin-top:6px" aria-label="${t("Tags, separated by commas")}" placeholder="${t("Tags, separated by commas")}" value="${esc((r.meta?.tags || []).join(", "))}" spellcheck="false">
    <div id="mmsg" role="status"></div></details>`;
  // 끊긴 학습은 last.pt에서 이어 한다. ★예전엔 처음부터 다시 돌리는 것밖에 없었다
  // 'stopped'(30분 넘게 조용함)만. ★'stalled'는 에폭이 긴 학습이 도는 중에도 떠서, 도는 학습에 두 번째 학습을 붙였다
  const canResume = d.last && r.state === "stopped" && r.framework === "ultralytics" && (r.total == null || r.epoch < r.total);
  if (d.args?.data || canResume) h += `<div class="actions" style="margin-top:10px">`
    + (canResume ? `<button class="btn small primary" id="resume" title="${t("Continue from the last saved epoch (weights/last.pt)")}">${t("Resume")}</button>` : "")
    + (d.args?.data ? `<button class="btn small" id="again" title="${t("Open Train with the settings this run used")}">${t("Train again with these settings")}</button>` : "") + `</div><div id="resumemsg" role="alert">${S.resumeMsg?.path === r.path ? `<div class="msg" style="--c:var(--red)">${esc(S.resumeMsg.text)}</div>` : ""}</div>`;
  const names = { B: t("Box"), P: t("Pose"), M: t("Mask") };
  if (d.heads.length) {
    h += `<h3>${t("Scores")}</h3><p class="hint">${t("At the best epoch. Higher is better.")}</p>`;
    for (const x of d.heads) {
      h += (d.heads.length > 1 ? `<div style="font-weight:600;margin-top:8px">${names[x.head] || esc(x.head)}</div>` : "") + `<div class="tiles">
        ${tile(t("Precision"), x.precision, t("Of what it found, how much was right"))}${tile(t("Recall"), x.recall, t("Of what was there, how much it found"))}
        ${tile("F1", x.f1, t("Balance of precision and recall"), true)}${tile("mAP50", x.map50)}${tile("mAP50-95", x.map5095)}
        <div class="tile"><b>${x.best_epoch}</b><span>${t("Best epoch")}</span></div></div>`;
    }
  }
  // 손실·점수 열은 agent의 column_info로 가른다. 없으면(옛 agent) 이름으로
  const want = S.curve === 0 ? "loss" : "score";
  const keys = Object.keys(d.columns).filter((k) => d.column_info ? kindOf(k, d) === want : (S.curve === 0 ? k.endsWith("loss") : k.startsWith("metrics/"))).sort();
  if (keys.length || Object.keys(d.columns).length) {
    h += `<h3 style="display:flex;align-items:center">${t("Curves")}<span style="margin-left:auto" class="seg"><button data-v="0" aria-pressed="${S.curve === 0}" class="${S.curve === 0 ? "on" : ""}">${t("Loss")}</button><button data-v="1" aria-pressed="${S.curve === 1}" class="${S.curve === 1 ? "on" : ""}">${t("Scores")}</button></span></h3>
      <p class="hint">${S.curve === 0 ? t("Loss should go down. If validation goes up while training goes down, it is overfitting.") : t("Scores should go up and level off.")}</p>`
      + chart(keys.map((k, i) => ({ name: pretty(k, d), x: d.columns.epoch || [], y: ema(d.columns[k], S.smooth), color: COLORS[i % COLORS.length], dash: k.startsWith("val/") })),
              { mark: S.curve === 0 ? valLossLow(d, isStep(r)) : null, xname: xname(r) })
      + `<label class="hint" style="display:flex;align-items:center;gap:8px;margin-top:6px">${t("Smoothing")} <input id="sm" type="range" min="0" max="0.95" step="0.05" value="${S.smooth}" style="width:160px"> ${S.smooth.toFixed(2)}</label>`;
  }
  if (r.meta?.note || r.meta?.goal != null) h += `<h3>${t("Your notes")}</h3>${r.meta.note ? `<p style="white-space:pre-wrap;margin:4px 0">${esc(r.meta.note)}</p>` : ""}`
    + (r.meta.goal != null ? `<p class="hint">${t("Goal:")} ${esc(pretty(r.metric_name, d))} ${r.lower ? "≤" : "≥"} ${esc(r.meta.goal)} ${r.meta.goal_hit ? `· <b style='color:var(--green)'>${t("reached")}</b>` : ""}</p>` : "");
  h += perClassHTML(r, d) + snapshotsHTML(r, d) + machineHTML(r, d);                            // 클래스별 성능 (classes.js)
  if (d.notes.length) h += `<h3>${t("What stands out")}</h3>` + d.notes.map((n, i) => `<div class="note" style="animation-delay:${i * 60}ms">💡 ${esc(n.observation)}<p>→ ${esc(n.try)}</p>
      ${n.next && r.source === S.label ? `<button class="chip nextrun" style="--c:var(--brand)" data-next="${i}">▶ ${esc(t("Try: {change}", { change: nextSummary(n.next, d.args) }))}</button>` : ""}</div>`).join("");
  if (d.images.length) h += `<h3>${t("Result images")}</h3><p class="hint">${t("Saved by the framework. Click to enlarge.")}</p><div class="gallery">`
    + d.images.map((n) => { const src = "file?path=" + encodeURIComponent(r.path + "/" + n); return `<figure role="button" tabindex="0" aria-label="${esc(n)}" data-src="${src}"><img loading="lazy" src="${src}" alt=""><figcaption>${esc(n)}</figcaption></figure>`; }).join("") + `</div>`;
  h += versionsHTML(r, d);                           // 계보·단계 (versions.js)
  // 어떤 환경에서 돌았나(epokio_env.json). 재현이 안 될 때 먼저 볼 곳
  if (Object.keys(d.env || {}).length) h += `<h3>${t("Environment")}</h3><p class="hint">${t("Recorded when Epokio started this run.")}</p><table>${Object.entries(d.env).map(([k, v]) => `<tr><th>${esc(k)}</th><td class="num">${esc(v ?? "–")}</td></tr>`).join("")}</table>`;
  if (Object.keys(d.args).length) h += `<h3>${t("Settings used")}</h3><table>${Object.entries(d.args).sort().map(([k, v]) => `<tr><th>${esc(k)}</th><td class="num">${esc(v)}</td></tr>`).join("")}</table>`;
  return h;
}
/// 지수 이동 평균(TensorBoard와 같은 방식)
function ema(ys, w) {
  if (!w) return ys; let last = null;
  return ys.map((y) => { if (y == null) return null; last = last == null ? y : last * w + y * (1 - w); return last; });
}
const tile = (name, v, hint, strong) => `<div class="tile ${strong ? "strong" : ""}" title="${esc(hint || "")}"><b>${f3(v)}</b><span>${name}</span></div>`;

/// 선 그래프(SVG). 세로축은 값 범위에 맞춘다. opt.mark = {x, label, hint}면 그 에폭에 세로 점선
/// 그린 뒤 bindCharts()가 마우스·터치·키보드(좌우 화살표) 툴팁을 붙인다
const CHARTS = [];
function chart(series, opt = {}) {
  const pts = series.flatMap((s) => s.y.map((y, i) => [s.x[i] ?? i + 1, y]).filter((p) => p[1] != null));
  if (!pts.length) return `<p class="hint">${t("No data yet.")}</p>`;
  const W = 640, H = 240, L = 44, R = 10, T = 10, B = 26;
  let [x0, x1] = [Math.min(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[0]))];
  let [y0, y1] = [Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[1]))];
  if (x0 === x1) x1 = x0 + 1; if (y0 === y1) { y0 -= .5; y1 += .5; }
  const pad = (y1 - y0) * .08; y0 -= pad; y1 += pad;
  if (opt.range) [y0, y1] = opt.range;                          // 사용률처럼 축이 정해진 값(0~100%)
  const X = (x) => L + (x - x0) / (x1 - x0) * (W - L - R), Y = (y) => T + (1 - (y - y0) / (y1 - y0)) * (H - T - B);
  let g = "";
  for (let i = 0; i <= 4; i++) { const v = y0 + (y1 - y0) * i / 4, y = Y(v); g += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/><text x="${L - 6}" y="${y + 4}" text-anchor="end">${v.toFixed(Math.abs(y1 - y0) < 1 ? 2 : 1)}</text>`; }
  g += `<text x="${L}" y="${H - 6}">${x0}</text><text x="${W - R}" y="${H - 6}" text-anchor="end">${opt.xname ? opt.xname(x1) : t("epoch {n}", { n: x1 })}</text>`;
  const m = opt.mark;
  if (m && m.x >= x0 && m.x <= x1) g += `<line class="mark-line" x1="${X(m.x)}" x2="${X(m.x)}" y1="${T}" y2="${H - B}"><title>${esc(m.hint)}</title></line>`;
  const lines = series.map((s) => {
    const p = s.y.map((y, i) => y == null ? null : [X(s.x[i] ?? i + 1), Y(y)]).filter(Boolean);
    if (!p.length) return "";
    const dpath = "M" + p.map((q) => q[0].toFixed(1) + "," + q[1].toFixed(1)).join(" L");
    let len = 0; for (let i = 1; i < p.length; i++) len += Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]);
    return `<path class="line" d="${dpath}" stroke="${s.color}" style="--len:${Math.ceil(len) + 2}" ${s.dash ? 'stroke-dasharray="5 3"' : ""}><title>${esc(s.name)}</title></path>`;
  }).join("");
  const xs = [...new Set(pts.map((p) => p[0]))].sort((a, b) => a - b);
  const id = CHARTS.push({ series, xs, X, Y, W, H, T, B, xname: opt.xname, digits: opt.digits }) - 1;
  if (CHARTS.length > 40) CHARTS[CHARTS.length - 41] = null;       // 오래된 그림 자료는 버린다
  return `<div class="chart-wrap" data-chart="${id}"><svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" tabindex="0" role="img"
      aria-label="${t("Curve chart. Use left and right arrow keys to read values by epoch.")}">${g}${lines}<line class="cursor" y1="${T}" y2="${H - B}" hidden/></svg>
    <div class="tip" role="status" aria-live="polite" hidden></div></div>
    <div class="legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join("")}</div>`
    + (m ? `<p class="hint mark-hint" title="${esc(m.hint)}"><span class="mark-key"></span>${esc(m.label)}</p>` : "");
}
/// 곡선 툴팁: 가장 가까운 에폭의 값들. 마우스·터치는 따라가고, 초점이 있으면 화살표로 옮긴다
function bindCharts() {
  document.querySelectorAll(".chart-wrap").forEach((wrap) => {
    const c = CHARTS[+wrap.dataset.chart]; if (!c || wrap.bound) return; wrap.bound = true;
    const svg = wrap.querySelector("svg"), tip = wrap.querySelector(".tip"), cur = wrap.querySelector(".cursor");
    let k = -1;
    const show = (i) => {
      k = Math.max(0, Math.min(c.xs.length - 1, i)); const ep = c.xs[k];
      const rows = c.series.map((s) => { const j = s.x.length ? s.x.indexOf(ep) : ep - 1; const v = j >= 0 ? s.y[j] : null;
        return v == null ? "" : `<div><i style="background:${s.color}"></i>${esc(s.name)} <b>${(+v).toFixed(c.digits ?? 4)}</b></div>`; }).join("");
      tip.innerHTML = `<div class="tip-h">${c.xname ? c.xname(ep) : t("Epoch {n}", { n: ep })}</div>${rows || `<div>${t("No value")}</div>`}`;
      const vx = c.X(ep); cur.setAttribute("x1", vx); cur.setAttribute("x2", vx); cur.hidden = false;
      const fx = vx / c.W * svg.clientWidth; tip.hidden = false;
      tip.style.left = Math.max(0, Math.min(fx + 12, svg.clientWidth - tip.offsetWidth)) + "px";
      if (fx + 12 + tip.offsetWidth > svg.clientWidth) tip.style.left = Math.max(0, fx - 12 - tip.offsetWidth) + "px";
    };
    const hide = () => { tip.hidden = true; cur.hidden = true; };
    const near = (e) => { const r = svg.getBoundingClientRect(); const vx = (e.clientX - r.left) / r.width * c.W;
      let best = 0; c.xs.forEach((x, i) => { if (Math.abs(c.X(x) - vx) < Math.abs(c.X(c.xs[best]) - vx)) best = i; }); return best; };
    svg.addEventListener("pointermove", (e) => show(near(e)));
    svg.addEventListener("pointerdown", (e) => show(near(e)));             // 터치: 누른 자리
    svg.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && document.activeElement !== svg) hide(); });
    svg.addEventListener("focus", () => show(k < 0 ? c.xs.length - 1 : k));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (e) => {
      const step = { ArrowLeft: -1, ArrowRight: 1, Home: -1e9, End: 1e9 }[e.key];
      if (step != null) { e.preventDefault(); show(k < 0 ? c.xs.length - 1 : k + step); } else if (e.key === "Escape") { hide(); svg.blur(); }
    });
  });
}
/// 검증 손실(val/*_loss 합)이 가장 낮은 에폭. analysis.py와 같은 규칙(0이나 빈 에폭은 뺀다, 8개 이상일 때만)
function valLossLow(d, step) {
  const vl = Object.keys(d.columns).filter((k) => k.startsWith("val/") && k.endsWith("_loss"));
  if (!vl.length) return null;
  const n = Math.max(...vl.map((k) => d.columns[k].length)), ep = d.columns.epoch || [];
  const s = []; for (let i = 0; i < n; i++) { const v = vl.map((k) => d.columns[k][i]);
    s.push(v.every((x) => x != null) && v.some((x) => x > 0) ? v.reduce((a, b) => a + b, 0) : null); }
  const ok = s.map((v, i) => v == null ? -1 : i).filter((i) => i >= 0);
  if (ok.length < 8) return null;
  const lo = ok.reduce((a, b) => s[b] < s[a] ? b : a), last = s[ok[ok.length - 1]];
  const over = lo < n - 3 && last > s[lo] * 1.10;
  const x = ep[lo] ?? lo + 1;
  if (step) return { x, label: over ? t("Lowest val loss · step {x} · overfitting after", { x }) : t("Lowest val loss · step {x}", { x }),
    hint: over ? t("Validation loss rose after step {x}: likely overfitting.", { x }) : t("Validation loss was lowest here.") };
  return { x, label: over ? t("Lowest val loss · epoch {x} · overfitting after", { x }) : t("Lowest val loss · epoch {x}", { x }),
    hint: over ? t("Validation loss rose after epoch {x}: likely overfitting. best.pt keeps the best epoch.", { x }) : t("Validation loss was lowest here.") };
}
/// 학습 속도: 에폭당 시간과 끝날 예상 시각(/runs의 elapsed·epoch·eta로 계산). 시각은 화면 언어로
function paceHTML(r) {
  if (r.state !== "running" || !r.epoch || !r.elapsed) return "";
  const per = r.elapsed / r.epoch;
  const end = r.eta != null ? new Date(Date.now() + r.eta * 1000) : null;
  const when = end && end.toLocaleString(LOCALE, end.toDateString() === new Date().toDateString() ? HM : { month: "short", day: "numeric", ...HM });
  const per_t = isStep(r) ? [t("Time per step"), t("{d}/step", { d: dur(per) })] : [t("Time per epoch"), t("{d}/epoch", { d: dur(per) })];
  return `<div class="pace"><span title="${per_t[0]}"><b>${esc(per_t[1])}</b></span>${end ? `<span title="${t("Time left")}"><b>${esc(t("{d} left", { d: dur(r.eta) }))}</b></span><span title="${t("Estimated finish")}"><b>~${esc(when)}</b></span>` : ""}</div>`;
}

function lightbox(src) {
  const d = document.createElement("div"); d.className = "lightbox"; d.innerHTML = `<img src="${src}" alt="">`;
  d.onclick = () => d.remove(); document.body.append(d);
}
function tab(name) {
  document.querySelector(".selbar")?.remove();
  S.tab = name; S.lastMain = ""; S.gen++;
  document.querySelectorAll("nav button").forEach((b) => { b.classList.toggle("on", b.dataset.tab === name); b.setAttribute("aria-selected", b.dataset.tab === name); });
  if (name === "review") drawReview(); else if (name === "sweeps") drawSweeps(); else if (name === "table") drawTable();
  refresh();
}
