"use strict";
// 학습 상세의 버전 칸: 계보(어디서 시작했나 · 여기서 시작한 학습) · 데이터에서 바뀐 것 · 모델 단계(후보·사용 중·보관).
// 계산은 agent(epokio/lineage.py). 여기는 /run 의 lineage·stage 를 그리고 /data-diff · /meta · /models/promote 를 부른다.
// ★제목·버튼·안내가 영어로 박혀 있어 한국어 화면에 영어가 섞였다. 화면 문장은 전부 t()를 거친다(lang.js의 KO)

const STAGES = { "": [t("No stage"), "var(--soft)"], candidate: [t("Candidate"), "var(--orange)"], production: [t("In use"), "var(--green)"], archived: [t("Archived"), "var(--soft)"] };

function versionsHTML(r, d) {
  const lin = d.lineage; if (!lin) return "";
  const local = r.source === "local" || r.source === S.label;
  const chain = [...(lin.ancestors || [])].reverse();
  let h = `<h3>${t("Where it came from")}</h3><p class="hint">${t("Which weights this run started from, and which runs started from this one.")}</p><div class="lineage">`;
  if (lin.pretrained && lin.weights) h += `<span class="node" style="cursor:default">📦 ${esc(lin.weights.split(/[\\/]/).pop())}</span> ›`;
  for (const a of chain) h += `<button class="node" data-go="${esc(a.path)}">${esc(a.name)}</button> ›`;
  h += `<span class="node me">${esc(display(r))}</span></div>`;
  const v = d.versions || {};
  if (v.data) h += `<p style="margin:8px 0 0"><span class="pill" style="--c:var(--accent)" title="${esc(v.data)}">${esc(dataLabel(v))}</span>`
    + (v.data_now ? ` <button class="btn small" id="vnow" data-a="${esc(v.data)}" data-b="${esc(v.data_now)}">⚠ ${t("The data changed after this run trained")}</button>` : "") + `</p>`;
  const p = lin.parent, mine = d.versions?.data;
  if (p && p.data && mine) h += p.data !== mine
    ? `<p style="margin:8px 0 0"><button class="btn" id="vdiff" data-a="${esc(p.data)}" data-b="${esc(mine)}">⎇ ${t("Data changed since {name}", { name: esc(p.name) })}</button></p>`
    : `<p class="hint" style="margin-top:8px">${t("Same data as {name}", { name: esc(p.name) })}</p>`;
  const kids = lin.children || [];
  if (kids.length) h += `<p class="hint" style="margin:10px 0 4px">${kids.length === 1 ? t("1 run started from this one") : t("{n} runs started from this one", { n: kids.length })}</p><div class="lineage">`
    + kids.map((c) => `<button class="node" data-go="${esc(c.path)}">↳ ${esc(c.name)}</button>`).join("") + `</div>`;
  const st = d.stage || "";
  h += `<h3>${t("Stage")}</h3><div class="toolbar"><span class="pill" id="vstage" style="--c:${STAGES[st][1]}">${STAGES[st][0]}</span>`
    + (local ? `<select id="vset" class="needs-run" aria-label="${t("Stage")}">${Object.entries(STAGES).filter(([k]) => k !== "production").map(([k, v]) => `<option value="${k}" ${k === st ? "selected" : ""}>${v[0]}</option>`).join("")}</select>
       <button class="btn primary needs-run" id="vpromote" ${d.weights ? "" : "disabled"} title="${t("Copy best.pt to the model registry as a new version")}">${t("Put in use")}</button>
       ${d.weights ? "" : `<span class="hint needs-run" style="margin:0">ⓘ ${t("This run has no weights/best.pt yet.")}</span>`}` : `<span class="hint">${t("Change it on the machine that has this run.")}</span>`)
    + `</div>`;
  return h;
}

/// "데이터 v3 / 4" (같은 data.yaml의 몇 번째 버전). 번호를 모르면 지문
function dataLabel(v) {
  return v.data_version ? t("Data v{n} of {of}", { n: v.data_version.n, of: v.data_version.of }) : t("Data {fp}", { fp: v.data });
}

function bindVersions(r, d) {
  document.querySelectorAll("[data-go]").forEach((b) => b.onclick = () => { S.sel = b.dataset.go; drawRuns(); scrollTo({ top: 0, behavior: "smooth" }); });
  const diff = $("#vdiff"); if (diff) diff.onclick = () => dataDiff(diff.dataset.a, diff.dataset.b);
  const now = $("#vnow"); if (now) now.onclick = () => dataDiff(now.dataset.a, now.dataset.b);
  const set = $("#vset");
  if (set) set.onchange = () => act(set, () => apiPost("meta", { path: r.path, stage: set.value }), () => { d.stage = set.value; paintStage(set.value); return t("Stage saved"); })
    .then((ok) => { if (ok === undefined) set.value = d.stage || ""; });   // ★저장 못 했는데(토큰 없음) 선택 상자는 바꾼 값을 보였다
  const pr = $("#vpromote");
  if (pr) pr.onclick = () => act(pr, () => apiPost("models/promote", { path: r.path }), (m) => { d.stage = "production"; paintStage("production"); return t("Copied to the model registry as {name} v{version}", { name: m.name, version: m.version }); });
}

function paintStage(st) {
  const el = $("#vstage"); if (!el) return;
  el.style.setProperty("--c", STAGES[st][1]); el.textContent = STAGES[st][0];
  el.style.animation = "none"; void el.offsetWidth; el.style.animation = "pop .3s ease";      // 바뀌면 튀어 오른다
}

/// 두 데이터 버전 사이에 더해진·빠진·바뀐 파일
async function dataDiff(a, b) {
  // 닫는 단추를 늘 둔다. ★배경을 눌러야만 닫혀 키보드로는 갇혔다(4초 갱신도 창이 열린 동안 멈춘다)
  const close = `<button class="btn small" data-close aria-label="${t("Close")}" style="margin-left:8px">✕</button>`;
  const m = modal(t("What changed in the data")); m.innerHTML = `<div class="sheet" aria-busy="true"><div class="toolbar" style="margin:0"><p class="hint" style="flex:1">${t("Loading…")}</p>${close}</div></div>`;
  m.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) m.close(); });
  openModal(m);
  let d;
  try { d = await api(`data-diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`); }
  catch (e) {
    if (e instanceof Locked) { m.close(); if (await needToken()) dataDiff(a, b); return; }     // 잠긴 보기: 그 자리에서 토큰을 묻고 다시
    if (m.open) m.querySelector(".sheet").innerHTML = `<div class="toolbar" style="margin:0"><h3 style="margin:0;flex:1">${t("Can't compare")}</h3>${close}</div><p class="hint">${esc(e.message)}</p>`; return;
  }
  if (!m.open) return;                                   // 받는 사이 닫았다
  const list = (xs) => xs.length ? `<div style="max-height:180px;overflow:auto;font:12px ui-monospace,Menlo,monospace">${xs.map(esc).join("<br>")}</div>` : `<p class="hint">${t("None")}</p>`;
  m.querySelector(".sheet").removeAttribute("aria-busy");
  m.querySelector(".sheet").innerHTML = `<div class="toolbar" style="margin:0"><h3 style="margin:0">${t("What changed in the data")}</h3><span class="hint" style="margin-left:auto">${esc(a)} → ${esc(b)}</span>${close}</div>
    <div class="tiles">${tile(t("Images added"), d.images.added)}${tile(t("Images removed"), d.images.removed)}${tile(t("Labels changed"), d.labels.changed + d.labels.added)}</div>
    ${d.boxes.length ? `<table>${d.boxes.map((x) => `<tr><th>${t("class {c}", { c: esc(x.cls) })}</th><td class="num">${x.before} → ${x.after}</td></tr>`).join("")}</table>` : ""}
    <h3>${t("Added")}</h3>${list(d.added)}<h3>${t("Removed")}</h3>${list(d.removed)}<h3>${t("Changed")}</h3>${list(d.changed)}
    <p class="hint" style="margin-top:12px">${t("The list was recorded when Epokio first saw each data version.")}</p>`;
  document.querySelectorAll(".sheet .tile b").forEach((b) => b.textContent = (+b.textContent || 0).toFixed(0));
}
