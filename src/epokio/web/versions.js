"use strict";
// 학습 상세의 버전 칸: 계보(어디서 시작했나 · 여기서 시작한 학습) · 데이터에서 바뀐 것 · 모델 단계(후보·사용 중·보관).
// 계산은 agent(epokio/lineage.py). 여기는 /run 의 lineage·stage 를 그리고 /data-diff · /meta · /models/promote 를 부른다.

const STAGES = { "": ["No stage", "var(--soft)"], candidate: ["Candidate", "var(--orange)"], production: ["In use", "var(--green)"], archived: ["Archived", "var(--soft)"] };

function versionsHTML(r, d) {
  const lin = d.lineage; if (!lin) return "";
  const local = r.source === "local" || r.source === S.label;
  const chain = [...(lin.ancestors || [])].reverse();
  let h = `<h3>Where it came from</h3><p class="hint">Which weights this run started from, and which runs started from this one.</p><div class="lineage">`;
  if (lin.pretrained && lin.weights) h += `<span class="node" style="cursor:default">📦 ${esc(lin.weights.split(/[\\/]/).pop())}</span> ›`;
  for (const a of chain) h += `<button class="node" data-go="${esc(a.path)}">${esc(a.name)}</button> ›`;
  h += `<span class="node me">${esc(display(r))}</span></div>`;
  const v = d.versions || {};
  if (v.data) h += `<p style="margin:8px 0 0"><span class="pill" style="--c:var(--accent)" title="${esc(v.data)}">${esc(dataLabel(v))}</span>`
    + (v.data_now ? ` <button class="btn small" id="vnow" data-a="${esc(v.data)}" data-b="${esc(v.data_now)}">⚠ ${t("The data changed after this run trained")}</button>` : "") + `</p>`;
  const p = lin.parent, mine = d.versions?.data;
  if (p && p.data && mine) h += p.data !== mine
    ? `<p style="margin:8px 0 0"><button class="btn" id="vdiff" data-a="${esc(p.data)}" data-b="${esc(mine)}">⎇ Data changed since ${esc(p.name)}</button></p>`
    : `<p class="hint" style="margin-top:8px">Same data as ${esc(p.name)}</p>`;
  if ((lin.children || []).length) h += `<p class="hint" style="margin:10px 0 4px">${lin.children.length} runs started from this one</p><div class="lineage">`
    + lin.children.map((c) => `<button class="node" data-go="${esc(c.path)}">↳ ${esc(c.name)}</button>`).join("") + `</div>`;
  const st = d.stage || "";
  h += `<h3>Stage</h3><div class="toolbar"><span class="pill" id="vstage" style="--c:${STAGES[st][1]}">${STAGES[st][0]}</span>`
    + (local ? `<select id="vset">${Object.entries(STAGES).filter(([k]) => k !== "production").map(([k, v]) => `<option value="${k}" ${k === st ? "selected" : ""}>${v[0]}</option>`).join("")}</select>
       <button class="btn primary" id="vpromote" ${d.weights ? "" : "disabled"} title="Copy best.pt to the model registry as a new version">Put in use</button>
       ${d.weights ? "" : `<span class="hint" style="margin:0">ⓘ This run has no weights/best.pt yet.</span>`}` : `<span class="hint">Change it on the machine that has this run.</span>`)
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
  if (set) set.onchange = () => act(set, () => apiPost("meta", { path: r.path, stage: set.value }), () => { d.stage = set.value; paintStage(set.value); return "Stage saved"; })
    .then((ok) => { if (ok === undefined) set.value = d.stage || ""; });   // ★저장 못 했는데(토큰 없음) 선택 상자는 바꾼 값을 보였다
  const pr = $("#vpromote");
  if (pr) pr.onclick = () => act(pr, () => apiPost("models/promote", { path: r.path }), (m) => { d.stage = "production"; paintStage("production"); return `Copied to the model registry as ${m.name} v${m.version}`; });
}

function paintStage(st) {
  const el = $("#vstage"); if (!el) return;
  el.style.setProperty("--c", STAGES[st][1]); el.textContent = STAGES[st][0];
  el.style.animation = "none"; void el.offsetWidth; el.style.animation = "pop .3s ease";      // 바뀌면 튀어 오른다
}

/// 두 데이터 버전 사이에 더해진·빠진·바뀐 파일
async function dataDiff(a, b) {
  const m = document.createElement("div"); m.className = "modal"; m.innerHTML = `<div class="sheet"><p class="hint">Loading…</p></div>`;
  m.onclick = (e) => { if (e.target === m) m.remove(); };
  document.body.append(m);
  let d;
  try { d = await api(`data-diff?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`); }
  catch (e) {
    if (e instanceof Locked) { m.remove(); if (await needToken()) dataDiff(a, b); return; }     // 잠긴 보기: 그 자리에서 토큰을 묻고 다시
    m.querySelector(".sheet").innerHTML = `<h3 style="margin-top:0">Can't compare</h3><p class="hint">${esc(e.message)}</p>`; return;
  }
  const list = (xs) => xs.length ? `<div style="max-height:180px;overflow:auto;font:12px ui-monospace,Menlo,monospace">${xs.map(esc).join("<br>")}</div>` : `<p class="hint">None</p>`;
  m.querySelector(".sheet").innerHTML = `<div class="toolbar" style="margin:0"><h3 style="margin:0">What changed in the data</h3><span class="hint" style="margin-left:auto">${esc(a)} → ${esc(b)}</span></div>
    <div class="tiles">${tile("Images added", d.images.added)}${tile("Images removed", d.images.removed)}${tile("Labels changed", d.labels.changed + d.labels.added)}</div>
    ${d.boxes.length ? `<table>${d.boxes.map((x) => `<tr><th>class ${esc(x.cls)}</th><td class="num">${x.before} → ${x.after}</td></tr>`).join("")}</table>` : ""}
    <h3>Added</h3>${list(d.added)}<h3>Removed</h3>${list(d.removed)}<h3>Changed</h3>${list(d.changed)}
    <p class="hint" style="margin-top:12px">The list was recorded when Epokio first saw each data version.</p>`;
  document.querySelectorAll(".sheet .tile b").forEach((b) => b.textContent = (+b.textContent || 0).toFixed(0));
}
