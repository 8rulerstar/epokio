"use strict";
// 비교 탭: 2~8개 학습의 곡선·점수·다른 설정 + 보이는 학습 전부의 설정 표·CSV·보고서
/// 기본 비교 열: 서버가 고른 대표 점수(/runs의 metric_name)를 따른다. 없을 때만 첫 mAP50-95 열로 폴백
function headlineKey(runs, keys) {
  const named = runs.map((r) => r.metric_name).find((m) => m && keys.includes(m));
  return named || keys.find((k) => k.startsWith("metrics/mAP50-95")) || keys[0] || "";
}
async function drawCompare(periodic) {
  const g = ++S.gen;
  const runs = S.picks.map((p) => S.runs.find((r) => r.path === p)).filter(Boolean);
  const ds = await Promise.all(runs.map((r) => detail(r)));
  if (g !== S.gen || S.tab !== "compare") return;
  const keys = [...new Set(ds.flatMap((d) => d ? Object.keys(d.columns).filter((k) => k !== "epoch" && k !== "time") : []))]
    .sort((a, b) => (a.startsWith("metrics/") ? 0 : 1) - (b.startsWith("metrics/") ? 0 : 1) || a.localeCompare(b));
  if (!keys.includes(S.cmpKey)) S.cmpKey = headlineKey(runs, keys);
  let right = `<div class="empty">${t("Tick two to eight runs in the list.")}</div>`;
  if (runs.length >= 2) {
    const best = Math.max(...ds.map((d) => d?.heads[0]?.f1 ?? -1));
    // 대표 점수 열. 같은 점수끼리일 때만 1등을 표시한다(낮을수록 좋으면 가장 낮은 것).
    // ★F1만 봐서 Keras·HF 학습끼리는 1등도 점수 열도 없었다
    const same = new Set(runs.map((r) => r.metric_name)).size === 1 && new Set(runs.map((r) => !!r.lower)).size === 1;
    const vals = runs.map((r) => r.best).filter((v) => v != null);
    const top = same && vals.length ? (runs[0].lower ? Math.min(...vals) : Math.max(...vals)) : null;
    right = `<div style="display:flex;align-items:center;gap:10px"><h2 style="margin:0;font-size:18px">${t("Compare runs")}</h2>
      <select id="ck" style="margin-left:auto;font:inherit;padding:4px 8px;border-radius:8px">${keys.map((k) => `<option value="${esc(k)}" ${k === S.cmpKey ? "selected" : ""}>${esc(pretty(k, ds.find((d) => d && d.column_info && d.column_info[k])))}</option>`).join("")}</select></div>`
      + chart(runs.map((r, i) => ({ name: display(r), x: ds[i]?.columns.epoch || [], y: ds[i]?.columns[S.cmpKey] || [], color: COLORS[i] })))
      + `<table style="margin-top:14px"><tr><th>${t("Run")}</th><th>${t("Epochs")}</th><th>${t("Score")}</th><th>${t("Precision")}</th><th>${t("Recall")}</th><th>F1</th><th>mAP50-95</th><th>${t("Model")}</th></tr>`
      + runs.map((r, i) => { const h = ds[i]?.heads[0] || {}; const a = ds[i]?.args || {};
          return `<tr><td>${esc(display(r))}</td><td class="num">${xnum(r, r.epoch)}/${xnum(r, r.total)}</td><td class="num ${top != null && r.best === top ? "win" : ""}" title="${esc(pretty(r.metric_name))}">${f3(r.best)}${r.lower ? " ↓" : ""}</td><td class="num">${f3(h.precision)}</td><td class="num">${f3(h.recall)}</td>
          <td class="num ${h.f1 != null && h.f1 === best ? "win" : ""}">${f3(h.f1)}</td><td class="num">${f3(h.map5095)}</td><td>${esc((a.model || "").split(/[\\/]/).pop())}</td></tr>`; }).join("") + `</table>`;
    // 데이터가 다르면 점수를 나란히 놓는 의미가 없다(같은 프로젝트 안에서만 비교한다는 원칙)
    const fps = new Set(ds.map((d) => d?.versions?.data).filter(Boolean));
    if (fps.size > 1) right += `<div class="msg" style="--c:var(--orange);margin-top:12px"><b>${t("These runs used different data.")}</b> ${t("Their scores are not directly comparable.")}</div>`;
    right += settingsDiff(runs, ds);
  }
  right += settingsTableHTML();
  const shown = filteredRuns();
  if (!setMain(`<div class="layout"><div class="card list" data-keep="cmplist">
      <div class="inrow" style="margin:6px"><input class="in" id="q" aria-label="${t("Filter by name or #tag")}" placeholder="${t("Filter by name or #tag")}" value="${esc(S.q || "")}" spellcheck="false"><button class="btn small" id="csv" title="${t("All runs as a spreadsheet")}">CSV</button><button class="btn small" id="report" title="${t("A Markdown report of the picked runs (or all shown), saved on the training machine")}">${t("Report")}</button></div>
      <p class="hint" style="margin:2px 10px 6px${S.pickFull && Date.now() - S.pickFull < 4000 ? ";color:var(--orange)" : ""}">${S.pickFull && Date.now() - S.pickFull < 4000 ? t("Up to 8 runs. Untick one first.") : t("Pick up to 8 runs")}</p>${shown.map((x, i) => rowHTML(x, i, true)).join("") || `<p class="hint" style="margin:10px">${t("No run matches.")}</p>`}</div>
    <div class="card detail">${right}</div></div>`, periodic)) return;
  document.querySelectorAll(".row").forEach((el) => el.onclick = () => {
    const p = el.dataset.path, i = S.picks.indexOf(p);
    if (i >= 0) S.picks.splice(i, 1); else if (S.picks.length < 8) S.picks.push(p);       // 표 탭과 같게 8개까지
    else { $("#sr").textContent = t("Up to 8 runs. Untick one first."); S.pickFull = Date.now(); }   // ★말없이 무시했다
    drawCompare();
  });
  bindCharts();
  const ck = $("#ck"); if (ck) ck.onchange = () => { S.cmpKey = ck.value; drawCompare(); };
  wireSettingsTable(periodic);
  const cd = $("#cmpdata"); if (cd) cd.onclick = () => dataDiff(cd.dataset.a, cd.dataset.b);
  const q = $("#q");
  q.oninput = () => { S.q = q.value; drawCompare().then(() => { const n = $("#q"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); };
  $("#csv").onclick = downloadCSV;
  // 보고서: 고른 학습(없으면 보이는 것 전부). 파일은 학습 기계의 바탕화면에 생긴다(★agent에 있는데 웹에서는 부를 수 없었다)
  $("#report").onclick = async () => {
    if (!await needToken()) return;
    const paths = S.picks.length ? S.picks : filteredRuns().map((x) => x.path);
    try {
      const r = await api("report", "POST", { paths });
      $("#sr").textContent = t("Report saved on {machine}: {path}", { machine: S.label || t("this machine"), path: r.path });
      alert(t("Report saved on {machine}: {path}", { machine: S.label || t("this machine"), path: r.path }));
    } catch (e) {
      if (e instanceof Locked) { S.locked = true; needToken(); return; }
      alert(e.message);
    }
  };
}
/// 고른 학습들 사이에서 **값이 다른 설정만**. 무엇을 바꿔서 점수가 달라졌는지 한눈에
const DIFF_SKIP = new Set(["name", "project", "save_dir", "exist_ok", "resume", "mode"]);
function settingsDiff(runs, ds) {
  // 설정 + 실행 환경(env · torch 등). 점수가 다른 이유가 설정이 아니라 판 차이일 수도 있다
  const all = ds.map((d) => {
    const a = { ...((d && Object.keys(d.all_args || {}).length ? d.all_args : d?.args) || {}) };
    for (const [k, v] of Object.entries(d?.env || {})) a["env · " + k] = v == null ? "–" : String(v);   // ★null이 "null" 글자로 보였다
    if (d?.versions?.data) a[t("data version")] = dataLabel(d.versions);      // 같은 data.yaml이라도 안의 파일이 바뀌었을 수 있다
    return a;
  });
  const fps = [...new Set(ds.map((d) => d?.versions?.data).filter(Boolean))];
  const dataBtn = fps.length > 1 ? `<p style="margin:8px 0 0"><button class="btn" id="cmpdata" data-a="${esc(fps[0])}" data-b="${esc(fps[1])}">⎇ ${t("What changed in the data")}</button></p>` : "";
  // 옛 agent는 주요 설정 11개만 준다. 한쪽에만 있는 설정은 "다름"이 아니다(★전부 다르다고 70줄이 나왔다). 모두에게 있는 것만 비교
  const common = all.reduce((acc, a) => acc.filter((k) => k in a), Object.keys(all[0] || {}));
  const keys = common.filter((k) => !DIFF_SKIP.has(k) && new Set(all.map((a) => a[k] ?? "–")).size > 1).sort();
  if (!keys.length) return `<p class="hint" style="margin-top:12px">${t("Same settings in all of them.")}</p>` + dataBtn;
  return `<h3>${t("Settings that differ")}</h3><table><tr><th>${t("Setting")}</th>${runs.map((r) => `<th>${esc(display(r))}</th>`).join("")}</tr>`
    + keys.map((k) => `<tr><th>${esc(k)}</th>${all.map((a) => `<td class="num">${esc(a[k] ?? "–")}</td>`).join("")}</tr>`).join("") + `</table>` + dataBtn;
}
/// 모든 학습을 표 파일로(엑셀·구글 시트에서 열린다). 이 브라우저에서 만들어 내려받는다
/// 비교 탭의 거르기. 태그는 #을 붙여 찾는다(★자리 표시가 '#tag'라고 하는데 #을 치면 하나도 안 걸렸다)
function filteredRuns() {
  const q = (S.q || "").toLowerCase().trim();
  if (!q) return S.runs;
  return S.runs.filter((x) => (display(x) + " " + x.source + " " + (x.meta?.tags || []).map((g) => "#" + g).join(" ")).toLowerCase().includes(q));
}
/// 설정 표: 보이는 학습 전부의 '값이 다른 설정'과 대표 점수를 한 표에(스윕 결과 읽기).
/// ★비교는 4개까지라 스윕 12개에서 어떤 설정이 점수를 움직였는지 볼 곳이 없었다
function settingsTableHTML() {
  if (!S.sweepOpen) return `<div style="margin-top:14px"><button class="btn small" id="sweepbtn">${t("Settings table for all shown runs")}</button></div>`;
  // 설정 전부(비밀일 수 있다)라 토큰이 있어야 한다
  if (!S.token || S.locked) return `<p class="hint" style="margin-top:14px">${t("The settings table needs this machine's token")}. <button class="btn small" id="sweepunlock">🔒 ${t("Unlock")}</button></p>`;
  const sw = S.sweep;
  if (!sw) return `<p class="hint" style="margin-top:14px">${t("Loading…")}</p>`;
  const want = new Set(filteredRuns().map((r) => r.path));
  let rows = sw.runs.filter((r) => want.has(r.path));
  // 열은 보이는 학습 사이에서 값이 다른 것만(★전체 기준이라 거르면 '–'뿐인 열이 수십 개였다)
  const allKeys = sw.keys.filter((k) => new Set(rows.map((r) => r.args[k]).filter((v) => v != null)).size > 1);
  const keys = allKeys.slice(0, 40);
  // 점수는 같은 점수(이름·방향)끼리만 순위를 매긴다(★점수 없는 학습이 방향 투표에 끼어, 손실이 가장 큰 학습에 1등이 갔다)
  const group = (r) => (r.best == null ? "" : r.metric_name + "|" + (r.lower ? 1 : 0));
  const sizes = {}; for (const r of rows) if (r.best != null) sizes[group(r)] = (sizes[group(r)] || 0) + 1;
  const order = Object.keys(sizes).sort((a, b) => sizes[b] - sizes[a]);
  const byScore = (a, b) => (a.best == null) - (b.best == null) || order.indexOf(group(a)) - order.indexOf(group(b))
    || (a.lower ? a.best - b.best : b.best - a.best);
  const num = (v) => (v == null || v === "" || isNaN(+v) ? null : +v);
  const cmp = (a, b) => {
    if (a == null || b == null) return (a == null) - (b == null);                   // 없는 값은 늘 아래로
    const x = num(a), y = num(b), d = x != null && y != null ? x - y : String(a).localeCompare(String(b));
    return S.sweepDesc ? -d : d;
  };
  rows = rows.slice().sort(S.sweepKey ? (a, b) => cmp(a.args[S.sweepKey], b.args[S.sweepKey]) || byScore(a, b) : byScore);
  const tops = new Set(order.map((g) => rows.find((r) => group(r) === g)));   // 무리마다 1등
  const mixed = order.length > 1;
  const head = (k, label) => `<th><button type="button" class="linkish" data-sk="${esc(k)}" aria-pressed="${(S.sweepKey || "") === k}">${esc(label)}${(S.sweepKey || "") === k && k ? (S.sweepDesc ? " ▴" : " ▾") : ""}</button></th>`;
  const single = order.length === 1 && rows.find((r) => r.best != null);
  return `<h3 style="display:flex;align-items:center">${t("Settings table")}<button class="btn small" id="sweephide" style="margin-left:auto">${t("Hide")}</button></h3>`
    + (mixed ? `<div class="msg" style="--c:var(--orange)">${t("Runs use different scores:")} ${order.map((g) => esc(pretty(g.split("|")[0])) + (g.endsWith("|1") ? " ↓" : "")).join(", ")}. ${t("Each score is ranked on its own.")}</div>` : "")
    + (keys.length ? "" : `<p class="hint">${t("These runs used the same settings.")}</p>`)
    + `<div style="overflow-x:auto"><table><tr><th>${t("Run")}</th>${head("", t("Score") + (single && single.lower ? " ↓" : ""))}${keys.map((k) => head(k, k)).join("")}</tr>`
    + rows.slice(0, 300).map((r) => `<tr><td><button type="button" class="linkish" data-open="${esc(r.path)}">${esc(r.display)}</button></td>
        <td class="num ${tops.has(r) && r.best != null ? "win" : ""}" title="${esc(pretty(r.metric_name))}">${f3(r.best)}${mixed && r.lower ? " ↓" : ""}</td>${keys.map((k) => `<td class="num">${esc(r.args[k] ?? "–")}</td>`).join("")}</tr>`).join("")
    + `</table></div>`
    + (rows.length > 300 || allKeys.length > keys.length ? `<p class="hint">${t("Showing {r} of {n} runs and {c} of {k} settings. Filter the list to narrow it down; the CSV has everything.", { r: Math.min(rows.length, 300), n: rows.length, c: keys.length, k: allKeys.length })}</p>` : "");
}
let settingsLoading = null;
/// 한 번에 하나만 받는다. 새로 받았으면 true(★처음 열 때 두 번 받았고, 거르기 글자마다 화면을 두 번 그렸다)
function loadSettingsTable(force) {
  if (!force && S.sweep && Date.now() - S.sweepAt < 15000) return Promise.resolve(false);
  if (!S.token || S.locked) return Promise.resolve(false);
  if (!settingsLoading) settingsLoading = api("sweep")
    .then((d) => { S.sweep = d; }, (e) => { if (e instanceof Locked) S.locked = true; S.sweep = { keys: [], runs: [] }; })
    .then(() => { S.sweepAt = Date.now(); settingsLoading = null; return true; });
  return settingsLoading;
}
function wireSettingsTable(periodic) {
  const b = $("#sweepbtn"); if (b) b.onclick = () => { S.sweepOpen = true; drawCompare(); };
  const u = $("#sweepunlock"); if (u) u.onclick = async () => { if (await needToken(t("The settings table needs this machine's token"))) { S.sweep = null; drawCompare(); } };
  const h = $("#sweephide"); if (h) h.onclick = () => { S.sweepOpen = false; drawCompare(); };
  document.querySelectorAll("[data-sk]").forEach((el) => el.onclick = () => {
    const k = el.dataset.sk;
    S.sweepDesc = k && S.sweepKey === k ? !S.sweepDesc : false;                     // 같은 머리를 다시 누르면 거꾸로
    S.sweepKey = k; drawCompare();
  });
  document.querySelectorAll("[data-open]").forEach((el) => el.onclick = () => { S.sel = el.dataset.open; tab("runs"); });
  if (S.sweepOpen && !periodic) loadSettingsTable().then((fresh) => { if (fresh && S.tab === "compare") drawCompare(true); });
}
function downloadCSV() {
  // lower: best가 낮을수록 좋은 점수인가(★없으면 0.2가 최고인지 최악인지 알 수 없었다)
  const cols = ["name", "state", "epoch", "total", "best", "best_epoch", "metric_name", "lower", "framework", "source", "tags", "path"];
  const cell = (v) => {
    let s = String(v ?? "");
    if (/^[=+\-@\t\r]/.test(s) && isNaN(+s)) s = "'" + s;          // 엑셀이 수식으로 실행하지 않게(학습 이름·태그는 남이 정할 수 있다)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  // 거른 것이 있으면 보이는 학습만(★거른 뒤에도 전부 내보냈다)
  // 설정 표를 연 적이 있으면 설정 열도 싣는다(★점수와 설정을 한 파일에서 볼 수 없었다)
  const keys = S.sweep?.keys || [], args = new Map((S.sweep?.runs || []).map((x) => [x.path, x.args]));
  const rows = filteredRuns().map((r) => [...cols.map((c) => cell(c === "name" ? display(r) : c === "tags" ? (r.meta?.tags || []).join(" ") : r[c])),
    ...keys.map((k) => cell(args.get(r.path)?.[k]))].join(","));
  const blob = new Blob(["\ufeff" + [[...cols, ...keys].map(cell).join(","), ...rows].join("\r\n")], { type: "text/csv;charset=utf-8" });   // BOM: 엑셀이 한글을 안 깨게
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `epokio-runs-${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(a.href);
}
