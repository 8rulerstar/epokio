"use strict";
// 검수(웹): 맥 앱의 검수 화면과 같은 흐름. 채점은 agent(epokio/review.py)가 하고 여기는 그리기만 한다.
//   평가 고르기·새 평가·예측 파일 열기 → 문턱 슬라이더(즉시 다시 채점) → 클래스 표·혼동 행렬(칸을 누르면 그 이미지만)
//   → 이미지 격자(박스 상태 색) → 크게 보기에서 1~4로 판정, ←→로 넘기기 → 재학습 세트
// 라벨 박스 편집은 아직 맥 앱에만 있다(웹은 분류의 "클래스 고치기"까지).

const R = { jobs: [], job: null, data: null, conf: null, filter: "all", cls: null, cell: null, verdicts: {}, fixed: [], open: -1, more: false, timer: 0,
            hist: [], sel: new Set(), anchor: null, hover: null, rows: [] };   // 되돌리기 기록 · 고른 이미지 · 스페이스로 볼 이미지
const VERDICT = { model_wrong: ["Model is wrong", "var(--red)", "1", "⚙"], label_wrong: ["Label is wrong", "var(--orange)", "2", "🏷"],
                  unsure: ["Not sure", "#d4a90c", "3", "?"], ok: ["Looks right", "var(--green)", "4", "✓"] };
const STATUS = { tp: "var(--green)", fn: "var(--orange)", fp: "var(--red)", cls: "var(--purple)" };
const stemOf = (p) => { const n = p.split(/[\\/]/).pop(); const i = n.lastIndexOf("."); return i > 0 ? n.slice(0, i) : n; };
const nameOf = (c) => (R.data?.names || {})[c] ?? String(c);

async function drawReview() {
  $("#main").innerHTML = `<div class="card detail"><p class="hint">Loading checks…</p></div>`;
  try { R.jobs = (await api("jobs")).jobs.filter((j) => j.kind === "evaluate" && j.state === "done").reverse(); }
  catch (e) { if (e instanceof Locked && S.tab === "review" && await needToken()) return drawReview(); R.jobs = []; }   // 작업 목록은 잠긴 보기다
  if (!R.job || !R.jobs.some((j) => j.id === R.job)) R.job = R.jobs[0]?.id || null;
  if (R.job) await loadEval(true); else paintReview();
}

async function loadEval(first) {
  const q = first || R.conf == null ? "" : "?conf=" + R.conf;
  try {
    R.data = await api(`jobs/${R.job}/eval${q}`);
    if (first) { R.conf = R.data.conf ?? 0.25; const st = await api(`review/state?job=${R.job}`); R.verdicts = st.verdicts || {}; R.fixed = st.fixed || []; }
  } catch { R.data = null; }
  paintReview();
}

function shown() {
  let rows = (R.data?.rows || []).filter((x) => {
    const v = R.verdicts[x.image];
    switch (R.filter) {
      case "missed": return x.fn > 0; case "extra": return x.fp > 0; case "cls": return (x.gt_status || []).includes("cls");
      case "todo": return !v; case "done": return !!v; case "all": return true; default: return v === R.filter;
    }
  });
  if (R.cls != null) rows = rows.filter((x) => (x.classes || []).includes(R.cls));
  if (R.cell) rows = rows.filter((x) => hasCell(x, R.cell));
  return rows;
}
function hasCell(x, [g, p]) {
  const gs = x.gt_status || [], ps = x.pred_status || [];
  const gHit = (w) => x.gt.some((b, i) => b.cls === g && gs[i] === w), pHit = (w) => x.pred.some((b, i) => b.cls === p && ps[i] === w);
  if (p === -1) return gHit("fn"); if (g === -1) return pHit("fp"); if (g === p) return gHit("tp"); return gHit("cls") && pHit("cls");
}

function paintReview() {
  const d = R.data;
  let h = `<div class="card detail"><div class="toolbar"><h2 style="margin:0;font-size:19px">Review</h2>
    <select id="rjob">${R.jobs.map((j) => `<option value="${j.id}" ${j.id === R.job ? "selected" : ""}>${esc(j.name)}</option>`).join("") || "<option>No checks yet</option>"}</select>
    <button class="btn" id="rnew">＋ New check</button><button class="btn" id="rimp">⇪ Open predictions file</button>`;
  if (d?.rows) h += `<span style="margin-left:auto" class="hint">${Object.keys(R.verdicts).length} of ${d.rows.length} reviewed</span>
    <button class="btn" id="rret" title="Make a dataset from marked images and fixed labels">↻ Retrain set</button>`;
  h += `</div>`;
  if (!d?.rows) {
    h += `<div class="empty">Check where your model goes wrong: run it on images that already have labels, then look at the worst ones first.<br><br>
      Works for detection, pose, segmentation and classification. For other frameworks, export predictions as JSONL and open the file.</div></div>`;
    $("#main").innerHTML = h; bindReviewTop(); return;
  }
  const o = d.overall || {}, rows = shown(), cls = d.task === "classify";
  h += `<div class="toolbar"><label class="hint" style="display:flex;gap:8px;align-items:center;margin:0">Confidence
      <input id="rconf" type="range" min="${d.conf_floor ?? 0.05}" max="0.95" step="0.05" value="${R.conf}" style="width:170px"><b id="rconfv">${(+R.conf).toFixed(2)}</b></label>
    ${d.best_conf != null && Math.abs(d.best_conf - R.conf) > 0.001 ? `<button class="btn" id="rbest" style="color:var(--purple)">✦ Best F1 at ${d.best_conf.toFixed(2)}</button>` : ""}
    <div class="stats" style="margin-left:auto"><div><b>${f3(o.precision)}</b><span>Precision</span></div><div><b>${f3(o.recall)}</b><span>Recall</span></div><div><b>${f3(o.f1)}</b><span>F1</span></div></div>
    <button class="btn" id="rmore">${R.more ? "▴" : "▾"} Classes</button></div>`;
  if (R.more) h += classesHTML(d) + `<p class="hint">${cls ? "Counted from each image's top answer. Below the confidence, the answer counts as “not sure”."
                                          : "Counted at one confidence and 50% overlap, so numbers differ from mAP in training results."}</p>`;
  const n = (f) => (d.rows || []).filter(f).length, vc = (v) => Object.values(R.verdicts).filter((x) => x === v).length;
  const chip = (k, t, c, cnt) => `<button class="chip ${R.filter === k ? "on" : ""}" data-f="${k}" style="--c:${c}">${t}<i>${cnt}</i></button>`;
  h += `<div class="chips">${chip("all", "All", "var(--accent)", d.rows.length)}${chip("missed", cls ? "Not sure / wrong" : "Missed something", "var(--orange)", n((x) => x.fn > 0))}
    ${cls ? "" : chip("extra", "Extra detections", "var(--red)", n((x) => x.fp > 0))}${chip("cls", "Wrong class", "var(--purple)", n((x) => (x.gt_status || []).includes("cls")))}
    ${chip("todo", "Not reviewed", "var(--soft)", d.rows.length - Object.keys(R.verdicts).length)}
    ${Object.entries(VERDICT).map(([k, v]) => chip(k, v[0], v[1], vc(k))).join("")}
    ${R.cls != null ? `<button class="chip on" id="rclsx" style="--c:#5856d6">Class: ${esc(nameOf(R.cls))} ✕</button>` : ""}
    ${R.cell ? `<button class="chip on" id="rcellx" style="--c:#5856d6">Mix-up cell ✕</button>` : ""}
    <select id="rbatch" style="margin-left:auto;font:inherit;border-radius:8px;padding:3px 6px"><option value="">Mark ${rows.length} shown…</option>${Object.entries(VERDICT).map(([k, v]) => `<option value="${k}">${v[0]}</option>`).join("")}<option value="-">Clear marks</option></select></div>`;
  h += `<div class="grid">${rows.slice(0, 120).map((x, i) => shotHTML(x, i)).join("")}</div>`
    + (rows.length > 120 ? `<p class="hint" style="margin-top:10px">Showing the first 120 of ${rows.length}. Filter to narrow down.</p>` : "")
    + (rows.length ? "" : `<div class="empty">Nothing matches. Try another filter.</div>`) + `</div>`;
  $("#main").innerHTML = h;
  bindReviewTop(); bindReviewBody(rows);
}

function classesHTML(d) {
  const pc = (d.per_class || []).slice().sort((a, b) => (a.f1 ?? 0) - (b.f1 ?? 0));
  const c = d.confusion || { classes: [], matrix: [], labels: [] }, top = Math.max(1, ...c.matrix.flat());
  const col = (f) => f == null ? "var(--soft)" : f < 0.5 ? "var(--red)" : f < 0.8 ? "var(--orange)" : "var(--green)";
  const table = `<table><tr><th>Class</th><th>Objects</th><th>Precision</th><th>Recall</th><th>F1</th></tr>${pc.map((x) =>
    `<tr class="pick ${R.cls === x.cls ? "on" : ""}" data-cls="${x.cls}" title="${x.tp} right, ${x.fp} wrong, ${x.fn} missed"><td><button class="cellbtn" data-k="c${x.cls}" aria-pressed="${R.cls === x.cls}"
     aria-label="${esc(x.name)}: ${x.tp} right, ${x.fp} wrong, ${x.fn} missed, F1 ${f3(x.f1)}. Show only this class">${esc(x.name)}</button></td><td class="num">${x.support}</td>
     <td class="num">${f3(x.precision)}</td><td class="num">${f3(x.recall)}</td><td class="num" style="color:${col(x.f1)};font-weight:700">${f3(x.f1)}</td></tr>`).join("")}</table>`;
  const lab = (i) => c.classes[i] === -1 ? "Background" : c.labels[i];
  const grid = `<p class="hint" style="margin:0 0 4px">Label ↓ · Model →</p><table class="cm">${c.matrix.map((row, i) => `<tr><th>${esc(lab(i))}</th>${row.map((v, j) => {
      const diag = i === j && c.classes[i] !== -1, a = v ? 0.2 + 0.8 * v / top : 0.05, sel = R.cell && R.cell[0] === c.classes[i] && R.cell[1] === c.classes[j];
      return `<td class="${sel ? "sel" : ""}" data-g="${c.classes[i]}" data-p="${c.classes[j]}" title="${esc(lab(i))} → ${esc(lab(j))}: ${v}"
        style="background:color-mix(in srgb, ${diag ? "var(--green)" : "var(--red)"} ${Math.round(a * 100)}%, transparent);color:${a > 0.55 ? "#fff" : "inherit"}"><button class="cellbtn" data-k="m${c.classes[i]}_${c.classes[j]}" aria-pressed="${!!sel}"
        aria-label="Label ${esc(lab(i))}, model ${esc(lab(j))}: ${v}. Show these images">${v || ""}</button></td>`; }).join("")}</tr>`).join("")}</table>`;
  return `<div class="twocol" style="margin-bottom:6px"><div>${table}</div><div style="overflow:auto">${grid}</div></div>`;
}

/// 정답(실선)·예측(점선)을 상태 색으로. 분류는 박스 대신 한 줄 글자
function overlay(x, big) {
  if (R.data?.task === "classify") {
    const st = (x.gt_status || [])[0], p = x.pred[0];
    const text = st === "tp" ? `✓ ${nameOf(x.truth)}` : `${nameOf(x.truth)} → ${p ? nameOf(p.cls) + " " + p.conf.toFixed(2) : "not sure"}`;
    return `<span style="position:absolute;left:6px;top:6px;max-width:calc(100% - 12px);background:${STATUS[st] || "var(--soft)"};color:#fff;font:700 ${big ? 15 : 11}px system-ui;padding:2px 7px;border-radius:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(text)}</span>`;
  }
  const w = big ? 2.5 : 1.5, shape = (b, c, dash, fill) => b.poly && b.poly.length > 2
    ? `<polygon points="${b.poly.map((q) => q.join(",")).join(" ")}" fill="${fill ? c : "none"}" fill-opacity=".18" stroke="${c}" stroke-width="${w}" vector-effect="non-scaling-stroke" ${dash ? 'stroke-dasharray="5 3"' : ""}/>`
    : `<rect x="${b.box[0] - b.box[2] / 2}" y="${b.box[1] - b.box[3] / 2}" width="${b.box[2]}" height="${b.box[3]}" fill="none" stroke="${c}" stroke-width="${w}" vector-effect="non-scaling-stroke" ${dash ? 'stroke-dasharray="5 3"' : ""}/>`;
  const g = x.gt.map((b, i) => shape(b, STATUS[(x.gt_status || [])[i]] || "var(--green)", false, true)).join("");
  const p = x.pred.map((b, i) => { const st = (x.pred_status || [])[i]; return !big && st === "tp" ? "" : shape(b, STATUS[st] || "var(--red)", true, false); }).join("");
  return `<svg viewBox="0 0 1 1" preserveAspectRatio="none">${g}${p}</svg>`;
}
const img = (x) => "file?path=" + encodeURIComponent(x.image);
const scoreColor = (s) => s < 0.5 ? "var(--red)" : s < 0.8 ? "var(--orange)" : "var(--green)";

function shotHTML(x, i) {
  const v = R.verdicts[x.image];
  const said = `Image ${i + 1}, score ${x.score.toFixed(2)}, ${x.tp} right, ${x.fp} wrong, ${x.fn} missed${v ? ", marked " + VERDICT[v][0] : ""}`;
  return `<div class="shot ${R.sel.has(x.image) ? "sel" : ""}" data-i="${i}" tabindex="0" role="button" aria-pressed="${R.sel.has(x.image)}" aria-label="${esc(said)}" style="animation-delay:${Math.min(i, 30) * 15}ms"><div class="frame"><span class="pic"><img loading="lazy" src="${img(x)}" alt="">${overlay(x, false)}</span>
    ${v ? `<span class="mark" style="--c:${VERDICT[v][1]}">${VERDICT[v][3]}</span>` : ""}${R.fixed.includes(stemOf(x.image)) ? `<span class="mark" style="--c:#14b8a6;right:32px">✎</span>` : ""}</div>
    <div class="foot"><span class="score" style="color:${scoreColor(x.score)}">${x.score.toFixed(2)}</span><span class="hint" style="margin:0">✓${x.tp} +${x.fp} −${x.fn}</span></div></div>`;
}

function bindReviewTop() {
  const sel = $("#rjob"); if (sel) sel.onchange = () => { R.job = sel.value; R.cls = R.cell = null; R.filter = "all"; loadEval(true); };
  $("#rnew").onclick = newCheck; $("#rimp").onclick = importFile;
  const ret = $("#rret"); if (ret) ret.onclick = () => act(ret, () => apiPost("review/retrain", { job: R.job, want: ["model_wrong", "label_wrong", "unsure"], repeat: 2 }),
    (r) => r.warning ? `Made a set of ${r.images} images. Check before training: ${r.warning}`
                     : `Retrain set ready: ${r.data}` + (r.moved_from_val ? ` (${r.moved_from_val} moved out of validation to keep the score honest)` : ""));
}

function bindReviewBody(rows) {
  const c = $("#rconf");
  if (c) c.oninput = () => { R.conf = +c.value; $("#rconfv").textContent = R.conf.toFixed(2); clearTimeout(R.timer); R.timer = setTimeout(() => loadEval(false), 160); };
  const b = $("#rbest"); if (b) b.onclick = () => { R.conf = R.data.best_conf; loadEval(false); };
  $("#rmore").onclick = () => { R.more = !R.more; paintReview(); };
  document.querySelectorAll(".chip[data-f]").forEach((el) => el.onclick = () => { R.filter = el.dataset.f; paintReview(); });
  const cx = $("#rclsx"); if (cx) cx.onclick = () => { R.cls = null; paintReview(); };
  const ex = $("#rcellx"); if (ex) ex.onclick = () => { R.cell = null; paintReview(); };
  const keep = (f) => (e) => { const k = e.target.closest?.("[data-k]")?.dataset.k; f(); if (k) document.querySelector(`[data-k="${k}"]`)?.focus(); };   // 다시 그려도 키보드 자리 유지
  document.querySelectorAll("tr.pick").forEach((el) => el.onclick = keep(() => { const k = +el.dataset.cls; R.cls = R.cls === k ? null : k; paintReview(); }));
  document.querySelectorAll(".cm td").forEach((el) => el.onclick = keep(() => { const k = [+el.dataset.g, +el.dataset.p];
    R.cell = R.cell && R.cell[0] === k[0] && R.cell[1] === k[1] ? null : k; paintReview(); }));
  R.rows = rows;
  document.querySelectorAll(".shot").forEach((el) => {
    const i = +el.dataset.i, x = rows[i];
    el.onmouseenter = () => { R.hover = i; }; el.onmouseleave = () => { if (R.hover === i) R.hover = null; };
    el.onclick = (e) => {                               // 사진 앱처럼: ⌘/Ctrl = 하나 더, ⇧ = 범위, 고른 게 있으면 그냥 눌러도 고르기
      if (e.shiftKey && R.anchor != null) { const [a, b] = [Math.min(R.anchor, i), Math.max(R.anchor, i)]; for (let k = a; k <= b; k++) R.sel.add(rows[k].image); }
      else if (e.metaKey || e.ctrlKey || R.sel.size) { R.sel.has(x.image) ? R.sel.delete(x.image) : R.sel.add(x.image); R.anchor = i; }
      else { R.anchor = i; return openShot(rows, i); }
      paintReview(); document.querySelector(`.shot[data-i="${i}"]`)?.focus();
    };
    el.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); el.onclick(e); } };   // 키보드로도 연다·고른다
  });
  const bt = $("#rbatch"); if (bt) bt.onchange = () => { const v = bt.value; if (!v) return; mark(rows.map((x) => x.image), v === "-" ? null : v, true); };
  selBar();
}

/// 판정을 바꾸는 곳은 전부 여기로: 되돌리기 기록 · 저장. announce면 "Undo" 달린 알림
function mark(images, v, announce) {
  if (!images.length) return;
  R.hist.push(Object.fromEntries(images.map((k) => [k, R.verdicts[k] ?? null]))); if (R.hist.length > 50) R.hist.shift();
  for (const k of images) { if (v == null) delete R.verdicts[k]; else R.verdicts[k] = v; }
  saveVerdicts();
  if (announce) toast(v == null ? `Cleared ${images.length} marks` : `Marked ${images.length} images`, false, { title: "Undo", run: undo });
  if (!document.querySelector(".modal")) paintReview();
}
function undo() {
  const last = R.hist.pop(); if (!last) return;
  for (const [k, v] of Object.entries(last)) { if (v == null) delete R.verdicts[k]; else R.verdicts[k] = v; }
  saveVerdicts(`Undone: ${Object.keys(last).length} images`);
  if (!document.querySelector(".modal")) paintReview();
}
/// 여러 장 골랐을 때 아래 막대
function selBar() {
  document.querySelector(".selbar")?.remove();
  if (!R.sel.size || S.tab !== "review") return;
  const b = document.createElement("div"); b.className = "selbar";
  b.innerHTML = `<b>${R.sel.size} selected</b>${Object.entries(VERDICT).map(([k, t]) => `<button class="btn" data-sv="${k}" title="Press ${t[2]}">${t[3]} ${t[0]}</button>`).join("")}
    <button class="btn" id="sx" title="Clear selection (Esc)">✕</button>`;
  document.body.append(b);
  b.querySelectorAll("[data-sv]").forEach((x) => x.onclick = () => { const ids = [...R.sel]; R.sel.clear(); mark(ids, x.dataset.sv, true); selBar(); });
  b.querySelector("#sx").onclick = () => { R.sel.clear(); paintReview(); };
}
// 격자 키보드: 스페이스 = 훑어보기, 1~4 = 고른 이미지에 판정, Esc = 선택 풀기, ⌘/Ctrl+Z = 되돌리기, ⌘/Ctrl+A = 전부 고르기
document.addEventListener("keydown", (e) => {
  if (S.tab !== "review" || document.querySelector(".modal") || /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); }
  else if (mod && e.key.toLowerCase() === "a") { e.preventDefault(); R.rows.forEach((x) => R.sel.add(x.image)); paintReview(); }
  else if (e.key === " " && !e.target.closest?.("button, input, select, textarea, [role=button]")) { const i = R.hover ?? R.rows.findIndex((x) => R.sel.has(x.image)); if (i != null && i >= 0) { e.preventDefault(); openShot(R.rows, i); } }
  else if (e.key === "Escape" && R.sel.size) { R.sel.clear(); paintReview(); }
  else if (R.sel.size) { const k = Object.keys(VERDICT).find((q) => VERDICT[q][2] === e.key); if (k) { const ids = [...R.sel]; R.sel.clear(); mark(ids, k, true); } }
});

async function saveVerdicts(msg) {
  try { await apiPost("review/verdicts", { job: R.job, verdicts: R.verdicts }); if (msg) toast(msg); }
  catch (e) {                                          // 저장 못 했으면 화면도 저장된 상태로 되돌린다(안 된 표시가 남지 않게)
    toast(e.message, true);
    try { R.verdicts = (await api(`review/state?job=${R.job}`)).verdicts || {}; } catch {}
    if (!document.querySelector(".modal")) paintReview();
  }
}

/// 크게 보기: 1~4 판정(다음 장으로), ←→ 넘기기, Esc 닫기. 분류는 올바른 클래스를 골라 저장
function openShot(rows, i) {
  document.querySelector(".modal")?.remove();
  const x = rows[i]; if (!x) return;
  const cls = R.data.task === "classify", v = R.verdicts[x.image];
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="top"><b style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(x.image.split(/[\\/]/).pop())}</b>
      <span class="hint" style="margin:0">${i + 1} / ${rows.length}</span><button class="btn" id="mx">Done</button></div>
    <div class="big"><span class="pic"><img src="${img(x)}" alt="">${overlay(x, true)}</span></div>
    <div class="bottom"><span class="score" style="color:${scoreColor(x.score)}">Score ${x.score.toFixed(2)}</span>
      ${cls ? `<select id="mcls">${Object.entries(R.data.names || {}).map(([k, n]) => `<option value="${k}" ${+k === (x.pred[0]?.cls ?? x.truth) ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
               <button class="btn" id="mfix" title="Saved next to the check results. Your image folders stay as they are.">Save right class</button>` : ""}
      <span style="margin-left:auto"></span>${Object.entries(VERDICT).map(([k, t]) => `<button class="btn" data-v="${k}" style="${v === k ? `background:${t[1]};color:#fff` : ""}" title="Press ${t[2]}">${t[3]} ${t[0]}</button>`).join("")}</div>`;
  document.body.append(m);
  fillPythons(m.querySelector("#np"));                 // 파이썬 찾기는 몇 초 걸린다: 창을 먼저 띄우고 목록은 뒤에 채운다
  const close = () => { m.remove(); document.removeEventListener("keydown", key); paintReview(); };
  const pick = (k) => {                        // ★누르자마자 다음 장으로 넘어가 눌렸는지 알 수 없었다: 도장을 잠깐 보이고 넘긴다
    mark([x.image], k); document.removeEventListener("keydown", key);
    const [word, c, , ic] = VERDICT[k], st = document.createElement("div");
    st.className = "stamp"; st.style.setProperty("--c", c); st.textContent = `${ic}  ${word}`;
    m.querySelector(".sheet, .shot, img")?.parentElement?.append(st);
    setTimeout(() => openShot(rows, Math.min(i + 1, rows.length - 1)), 330);
  };
  const key = (e) => {
    if (e.target.tagName === "SELECT") return;
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); undo(); document.removeEventListener("keydown", key); openShot(rows, i); return; }
    if (e.key === "Escape" || e.key === " ") { e.preventDefault(); close(); } else if (e.key === "ArrowRight") { document.removeEventListener("keydown", key); openShot(rows, Math.min(i + 1, rows.length - 1)); }
    else if (e.key === "ArrowLeft") { document.removeEventListener("keydown", key); openShot(rows, Math.max(i - 1, 0)); }
    else { const k = Object.keys(VERDICT).find((q) => VERDICT[q][2] === e.key); if (k) pick(k); }
  };
  document.addEventListener("keydown", key);
  m.querySelector("#mx").onclick = close;
  m.querySelectorAll("[data-v]").forEach((b) => b.onclick = () => pick(b.dataset.v));
  zoomable(m.querySelector(".big"), m.querySelector(".big .pic"));
  const fx = m.querySelector("#mfix");
  if (fx) fx.onclick = () => act(fx, () => apiPost("review/fix", { job: R.job, image: x.image, boxes: [{ cls: +m.querySelector("#mcls").value, box: [0.5, 0.5, 1, 1] }] }),
    () => { R.fixed.push(stemOf(x.image)); if (!R.verdicts[x.image] || R.verdicts[x.image] === "ok") mark([x.image], "label_wrong"); return "Fixed label saved"; });
}

/// 새 평가: 모델 파일·이미지 폴더(이 agent 기계의 경로)·파이썬
async function newCheck() {
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="sheet"><h3 style="margin-top:0">New check</h3><p class="hint">Paths are on the machine running the agent (${esc(S.label)}).</p>
    <div class="form"><label>Model (best.pt)<input id="nm" type="text" placeholder="/path/to/runs/train/weights/best.pt"></label>
    <label>Images with labels (for classification, the folder with one subfolder per class)<input id="nf" type="text" placeholder="/path/to/dataset/images/val"></label>
    <label>Python<select id="np"><option>Looking for Python…</option></select></label></div>
    <div class="toolbar" style="margin:14px 0 0;justify-content:flex-end"><button class="btn" id="nc">Cancel</button><button class="btn primary" id="ns">Start check</button></div></div>`;
  document.body.append(m);
  m.querySelector("#nc").onclick = () => m.remove();
  const go = m.querySelector("#ns");
  go.onclick = () => act(go, async () => {
    const model = m.querySelector("#nm").value.trim(), folder = m.querySelector("#nf").value.trim();
    if (!model || !folder) throw new Error("Give both the model and the image folder.");
    await apiPost("jobs", { kind: "evaluate", name: "eval_" + folder.split(/[\\/]/).filter(Boolean).pop(), python: m.querySelector("#np").value, params: { model, source: folder, conf: 0.25 } });
    m.remove();
  }, "Added to the queue. Pick it here when it finishes.");
}

/// 다른 프레임워크의 예측 파일(JSONL)
function importFile() {
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="sheet"><h3 style="margin-top:0">Open a predictions file</h3>
    <p class="hint">One JSON object per line, for any framework. Path on the agent machine.</p>
    <pre style="font-size:11.5px;background:var(--panel2);padding:10px;border-radius:8px;overflow:auto;white-space:pre-wrap">{"names": {"0": "cat", "1": "dog"}}
{"image": "/data/a.jpg", "gt": [{"cls": 0, "box": [0.5, 0.5, 0.2, 0.3]}], "pred": [{"cls": 0, "box": [0.51, 0.5, 0.2, 0.3], "conf": 0.91}]}
{"image": "/data/b.jpg", "label": "cat", "probs": [0.87, 0.13]}</pre>
    <div class="form"><label>File<input id="ip" type="text" placeholder="/path/to/predictions.jsonl"></label></div>
    <div class="toolbar" style="margin:14px 0 0;justify-content:flex-end"><button class="btn" id="ic">Cancel</button><button class="btn primary" id="io">Open</button></div></div>`;
  document.body.append(m);
  m.querySelector("#ic").onclick = () => m.remove();
  const go = m.querySelector("#io");
  go.onclick = () => act(go, async () => {
    const r = await apiPost("review/import", { path: m.querySelector("#ip").value.trim() });
    m.remove(); R.job = r.id; await drawReview(); return r;
  }, (r) => `Opened ${r.images} images`);
}

/// 확대·이동(미리보기처럼): 휠·트랙패드로 확대, 끌어서 이동, 두 번 눌러 원래대로/2.5배
function zoomable(area, pic) {
  let z = 1, x = 0, y = 0, drag = null;
  const tag = document.createElement("span"); tag.className = "zoomtag"; tag.hidden = true; area.append(tag);
  const apply = () => { pic.style.transform = `translate(${x}px, ${y}px) scale(${z})`; pic.classList.toggle("zoomed", z > 1); tag.hidden = z <= 1.01; tag.textContent = z.toFixed(1) + "×"; };
  area.addEventListener("wheel", (e) => { e.preventDefault(); z = Math.min(8, Math.max(1, z * Math.exp(-e.deltaY * 0.002))); if (z === 1) x = y = 0; apply(); }, { passive: false });
  pic.addEventListener("dblclick", () => { if (z > 1) { z = 1; x = y = 0; } else z = 2.5; apply(); });
  pic.addEventListener("mousedown", (e) => { if (z > 1) { drag = [e.clientX - x, e.clientY - y]; e.preventDefault(); } });
  window.addEventListener("mousemove", (e) => { if (drag) { x = e.clientX - drag[0]; y = e.clientY - drag[1]; pic.style.transition = "none"; apply(); } });
  window.addEventListener("mouseup", () => { drag = null; pic.style.transition = ""; });
}
