"use strict";
// 스윕(웹): 목록 · 최고 조합 · 가장 영향이 컸던 설정 · 값별 점수 · 순위표 · 멈추기 · 새 스윕.
// 펼치기·채점·조기 중단은 agent(epokio/sweep.py). 도는 동안 5초마다 조용히 새로 고친다.

const W = { list: [], sel: null, data: null, timer: 0 };
const SWEEP_STATE = { done: ["Done", "var(--green)"], running: ["Running", "var(--accent)"], queued: ["Waiting", "var(--soft)"],
                      pruned: ["Stopped early", "var(--orange)"], failed: ["Failed", "var(--red)"], cancelled: ["Cancelled", "var(--soft)"] };

async function drawSweeps() {
  clearInterval(W.timer);
  try { W.list = (await api("sweeps")).sweeps || []; }
  catch (e) { if (e instanceof Locked && S.tab === "sweeps" && await needToken()) return drawSweeps(); W.list = []; }   // 스윕 목록은 잠긴 보기다
  if (!W.sel || !W.list.some((s) => s.id === W.sel)) W.sel = W.list[0]?.id || null;
  W.data = W.list.find((s) => s.id === W.sel) || null;
  paintSweeps();
  W.timer = setInterval(async () => {                                   // 도는 스윕만, 보고 있을 때만
    if (S.tab !== "sweeps") return clearInterval(W.timer);
    if (document.hidden || document.querySelector(".modal") || !W.data || W.data.done >= W.data.total) return;
    try { W.data = await api("sweeps/" + W.sel); paintSweeps(); } catch {}
  }, 5000);
}

function paintSweeps() {
  const rows = W.list.map((s, i) => `<div class="row ${s.id === W.sel ? "on" : ""}" data-s="${s.id}" style="--c:var(--accent);animation-delay:${i * 25}ms;grid-template-columns:18px 1fr auto">
      <span>${s.mode === "smart" ? "✨" : s.mode === "random" ? "🎲" : "▦"}</span><span class="name">${esc(s.name)}</span><span class="best">${s.best?.best != null ? s.best.best.toFixed(3) : ""}</span>
      <span class="bar"><i style="width:${s.total ? s.done / s.total * 100 : 0}%"></i></span><span class="meta">${s.done} of ${s.total} runs${s.prune ? " · stops runs that fall behind" : ""}</span></div>`).join("");
  $("#main").innerHTML = `<div class="layout"><div class="card list"><div class="toolbar" style="margin:6px"><button class="btn primary" id="snew">＋ New sweep</button></div>
      ${rows || `<p class="hint" style="margin:10px">No sweeps yet.</p>`}</div><div class="card detail">${W.data ? sweepHTML(W.data) : `<div class="empty">A sweep tries several settings and ranks them. Start one with “New sweep”.</div>`}</div></div>`;
  document.querySelectorAll("[data-s]").forEach((el) => el.onclick = async () => { W.sel = el.dataset.s; W.data = await api("sweeps/" + W.sel); paintSweeps(); });
  $("#snew").onclick = newSweep;
  const stop = $("#sstop"); if (stop) stop.onclick = () => act(stop, () => apiPost(`sweeps/${W.sel}/cancel`), "Sweep stopped").then(drawSweeps);
  document.querySelectorAll("[data-run]").forEach((el) => el.onclick = () => { const p = el.dataset.run; if (p) { S.sel = p; tab("runs"); } });
  document.querySelectorAll("[data-key]").forEach((el) => el.onclick = () => { W.key = el.dataset.key; paintSweeps(); });
}

function sweepHTML(s) {
  const keys = s.importance.map((x) => x.key), metric = s.metric ? pretty(s.metric, null).replace("metrics/", "") : "score";
  let h = `<div class="toolbar"><div style="flex:1"><h2 style="margin:0">${esc(s.name)}</h2><div class="meta">${s.mode === "smart" ? "Smart search" : s.mode === "random" ? "Random search" : "Chosen values"} · ${s.done} of ${s.total} runs</div></div>
    ${s.done < s.total ? `<button class="btn danger" id="sstop">■ Stop sweep</button>` : ""}</div>`;
  if (s.best) h += `<div class="note" style="background:color-mix(in srgb,#f5c542 14%,transparent)">🏆 <b>Best ${esc(metric)} ${s.best.best.toFixed(4)}</b>
      ${keys.map((k) => `<span class="pill" style="--c:var(--accent);margin-left:6px">${esc(k)} = ${esc(String(s.best.trial[k]))}</span>`).join("")}
      ${s.best.run ? `<button class="btn" style="margin-left:10px" data-run="${esc(s.best.run)}">Open run</button>` : ""}</div>`;
  h += paretoHTML(s, metric);
  h += bestSoFarHTML(s);
  if (s.importance.length > 1) h += `<h3>What mattered most</h3><p class="hint">How much the average score changed across the values of each setting. A rough guide, not a proof.</p>`
    + s.importance.map((x) => `<div style="display:grid;grid-template-columns:90px 1fr 44px;gap:8px;align-items:center;margin:4px 0;cursor:pointer" data-key="${esc(x.key)}">
        <code>${esc(x.key)}</code><div style="background:var(--panel2);border-radius:5px"><div class="hbar" style="width:${Math.max(3, x.share * 100)}%;opacity:${(W.key || keys[0]) === x.key ? 1 : .5}"></div></div>
        <span class="hint" style="margin:0;text-align:right">${Math.round(x.share * 100)}%</span></div>`).join("");
  h += parallelHTML(s, keys, metric);
  const k = W.key && keys.includes(W.key) ? W.key : keys[0], bk = s.by_key[k];
  if (bk && bk.values.length) {
    const vals = bk.values.map((v) => v.mean), lo = Math.min(...vals), hi = Math.max(...vals), top = s.higher ? hi : lo;
    const H = 150, span = hi - lo || 1, bw = Math.min(80, 560 / bk.values.length - 12);
    h += `<h3>Score by value · <code>${esc(k)}</code></h3><p class="hint">Average best score of the runs that used each value.</p>
      <svg viewBox="0 0 ${bk.values.length * (bw + 12) + 10} ${H + 40}" style="width:100%;max-width:640px;height:${H + 40}px">${bk.values.map((v, i) => {
        const bh = 20 + (v.mean - lo) / span * (H - 30), x = 10 + i * (bw + 12);
        return `<rect x="${x}" y="${H - bh + 14}" width="${bw}" height="${bh}" rx="6" fill="${v.mean === top ? "var(--accent)" : "color-mix(in srgb, var(--accent) 40%, transparent)"}"><animate attributeName="height" from="0" to="${bh}" dur=".5s"/></rect>
          <text x="${x + bw / 2}" y="${H - bh + 8}" text-anchor="middle" font-size="11" fill="var(--soft)">${v.mean.toFixed(3)}</text>
          <text x="${x + bw / 2}" y="${H + 30}" text-anchor="middle" font-size="11.5" fill="var(--ink)">${esc(String(v.value))}</text>`; }).join("")}</svg>`;
  }
  const rows = s.rows.slice().sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999));
  const multi = (s.machines || []).length > 1, host = (u) => u ? (u.split("//").pop() || u).split(":")[0] : "This machine";
  if ((s.needs_tokens || []).length) h += `<div class="note" style="background:color-mix(in srgb,var(--warn) 12%,transparent)">🔑 Waiting for the token of ${s.needs_tokens.map((u) => esc(host(u))).join(", ")}. Open Epokio on the Mac that started this sweep.</div>`;
  h += `<h3>All runs</h3><table><tr><th>#</th>${keys.map((x) => `<th>${esc(x)}</th>`).join("")}<th>${esc(metric)}</th>${multi ? "<th>Machine</th>" : ""}<th>State</th></tr>${rows.map((r) => {
    const [label, c] = SWEEP_STATE[r.state] || [r.state, "var(--soft)"];
    return `<tr class="pick" data-run="${esc(r.run || "")}"><td class="num" style="${r.rank === 1 ? "color:#d4a90c;font-weight:700" : ""}">${r.rank ?? "–"}</td>
      ${keys.map((x) => `<td class="num">${esc(String(r.trial[x] ?? "–"))}</td>`).join("")}<td class="num">${r.best != null ? r.best.toFixed(4) : "–"}</td>${multi ? `<td>${esc(host(r.machine))}</td>` : ""}
      <td><span class="pill" style="--c:${c}">${label}</span></td></tr>`; }).join("")}</table>`;
  return h;
}

/// 새 스윕: 데이터·모델·에폭·파이썬 + 고른 값(격자) 또는 범위(무작위) + 조기 중단
async function newSweep() {
  const m = document.createElement("div"); m.className = "modal";
  m.innerHTML = `<div class="sheet"><h3 style="margin-top:0">New sweep</h3><p class="hint">Paths are on the machine running the agent (${esc(S.label)}). Runs go into the queue one after another.</p>
    <div class="form"><label>data.yaml<input id="wd" type="text" placeholder="/path/to/data.yaml"></label>
    <div class="twocol"><label>Model<input id="wm" type="text" value="yolo11n.pt"></label><label>Epochs<input id="we" type="text" value="50"></label></div>
    <label>Python<select id="wp"><option>Looking for Python…</option></select></label>
    <label>How<select id="wmode"><option value="grid">Values I choose</option><option value="random">Random in a range</option><option value="smart">Smart (learns from each run)</option></select></label>
    <div id="wgrid" class="twocol"><label>Setting<select id="wk"><option>lr0</option><option>imgsz</option><option>batch</option><option>optimizer</option><option value="model">model (n, s, m, l, x)</option></select></label>
      <label>Values, separated by commas<input id="wv" type="text" value="0.01, 0.005, 0.001"></label></div>
    <div id="wrand" class="twocol" hidden><label>Setting<select id="wrk"><option>lr0</option><option>imgsz</option><option>batch</option></select></label>
      <label>From · to · runs<span style="display:flex;gap:6px"><input id="wlo" type="text" value="0.0001" style="width:33%"><input id="whi" type="text" value="0.01" style="width:33%"><input id="wn" type="text" value="8" style="width:33%"></span></label></div>
    <div id="wmore" hidden><div id="wrows"></div><button class="btn" id="wadd" type="button">＋ Add a setting</button>
      <p class="hint">Up to 4 settings. Write a range as <code>0.001-0.01</code> or a list as <code>SGD, AdamW</code>.</p></div>
    <label>Also aim for<select id="wsec"><option value="">Nothing else</option><option value="size">A smaller model</option><option value="time">Faster training</option></select></label>
    <label style="display:flex;flex-direction:row;gap:8px;align-items:center;color:var(--ink)"><input id="wprune" type="checkbox"> Stop runs that fall behind (checked at 30% of epochs)</label></div>
    <div class="toolbar" style="margin:14px 0 0;justify-content:flex-end"><button class="btn" id="wc">Cancel</button><button class="btn primary" id="ws">Queue sweep</button></div></div>`;
  document.body.append(m);
  fillPythons(m.querySelector("#wp"));                 // 파이썬 찾기는 몇 초 걸린다: 창을 먼저 띄우고 목록은 뒤에 채운다
  const mode = m.querySelector("#wmode");
  mode.onchange = () => { m.querySelector("#wgrid").hidden = mode.value !== "grid"; m.querySelector("#wrand").hidden = mode.value === "grid";
                          m.querySelector("#wmore").hidden = mode.value === "grid"; };
  const KEYS = ["lr0", "imgsz", "batch", "epochs", "optimizer", "model"];
  m.querySelector("#wadd").onclick = () => {                  // 무작위·똑똑하게: 설정을 더(최대 4개)
    const rowsEl = m.querySelector("#wrows"); if (rowsEl.children.length >= 3) return;
    const used = [m.querySelector("#wrk").value, ...[...rowsEl.querySelectorAll("select")].map((x) => x.value)];
    const k = KEYS.find((x) => !used.includes(x)) || "batch";
    const row = document.createElement("div"); row.className = "twocol"; row.style.marginTop = "6px";
    row.innerHTML = `<label>Setting<select>${KEYS.map((x) => `<option ${x === k ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label>Range or values<input type="text" value="${k === "optimizer" ? "SGD, AdamW" : k === "model" ? "n, s" : "8-32"}"></label>`;
    rowsEl.append(row);
  };
  m.querySelector("#wc").onclick = () => m.remove();
  const go = m.querySelector("#ws");
  go.onclick = () => act(go, async () => {
    const data = m.querySelector("#wd").value.trim(); if (!data) throw new Error("Give the path to data.yaml.");
    const rk = m.querySelector("#wrk").value;
    const space = mode.value === "grid"
      ? [{ key: m.querySelector("#wk").value, values: m.querySelector("#wv").value.split(",").map((v) => v.trim()).filter(Boolean) }]
      : [{ key: rk, low: +m.querySelector("#wlo").value, high: +m.querySelector("#whi").value, log: rk === "lr0", int: rk !== "lr0" },
         ...[...m.querySelectorAll("#wrows .twocol")].map((row) => {
           const k = row.querySelector("select").value, v = row.querySelector("input").value.trim();
           const NUM = "[-+]?(?:\\d+\\.?\\d*|\\.\\d+)(?:[eE][-+]?\\d+)?";          // ★[\d.eE+-]+는 "1e-4-1e-2"를 엉뚱하게 갈랐다
           const r = v.match(new RegExp(`^\\s*(${NUM})\\s*[-~]\\s*(${NUM})\\s*$`));
           if (r && !v.includes(",")) return { key: k, low: +r[1], high: +r[2], log: k === "lr0", int: ["imgsz", "batch", "epochs"].includes(k) };
           const vals = v.split(",").map((x) => x.trim()).filter(Boolean);
           if (!vals.length) throw new Error(`Give a range or values for ${k}.`);
           return { key: k, values: vals };
         })];
    const r = await apiPost("sweeps", { name: data.split(/[\\/]/).slice(-2, -1)[0] || "sweep", python: m.querySelector("#wp").value, mode: mode.value,
      base: { data, model: m.querySelector("#wm").value.trim(), epochs: +m.querySelector("#we").value || 50 }, space,
      trials: +m.querySelector("#wn").value || 8, prune: m.querySelector("#wprune").checked, prune_at: 0.3,
      second: m.querySelector("#wsec").value || undefined });
    m.remove(); W.sel = r.id; drawSweeps(); return r;
  }, (r) => `${r.runs} runs added to the queue`);
}

/// 평행 좌표: 설정마다 세로축, 맨 오른쪽이 점수. 학습 하나 = 선 하나(좋을수록 진하게). 올리면 도드라지고 값이 뜬다(맥 앱 ParallelCoords와 같은 규칙)
function parallelHTML(s, keys, metric) {
  const rows = s.rows.filter((r) => r.best != null);
  if (rows.length < 2 || !keys.length) return "";
  const axes = [...keys, "__score"], Wd = 640, H = 170, x = (i) => 30 + (Wd - 60) * i / (axes.length - 1);
  const bs = rows.map((r) => r.best), lo = Math.min(...bs), hi = Math.max(...bs);
  const pos = (k, r) => {
    if (k === "__score") return hi > lo ? (s.higher ? (r.best - lo) : (hi - r.best)) / (hi - lo) : 0.5;   // 위 = 좋음(손실은 뒤집는다)
    const vals = rows.map((q) => q.trial[k]);
    if (vals.every((v) => typeof v === "number")) {
      const a = Math.min(...vals), b = Math.max(...vals), v = r.trial[k];
      if (a === b) return 0.5;
      return a > 0 && b / a >= 20 ? (Math.log(v) - Math.log(a)) / (Math.log(b) - Math.log(a)) : (v - a) / (b - a);   // 자릿수가 넓으면 로그 눈금
    }
    const show = (v) => v == null ? "–" : String(v);                   // 값이 없는 학습은 "–" 칸(가운데에 그리면 없는 값처럼 보였다)
    const cats = [...new Set(vals.map(show))].sort();
    return cats.length === 1 ? 0.5 : cats.indexOf(show(r.trial[k])) / (cats.length - 1);
  };
  const lines = rows.map((r, n) => {
    const q = hi > lo ? (s.higher ? (r.best - lo) / (hi - lo) : (hi - r.best) / (hi - lo)) : 1;
    const d = axes.map((k, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${(12 + H * (1 - pos(k, r))).toFixed(1)}`).join(" ");
    const tip = axes.map((k) => `${k === "__score" ? metric : k} = ${k === "__score" ? r.best.toFixed(4) : (r.trial[k] ?? "–")}`).join("\n");
    return `<path class="pc" d="${d}" data-run="${esc(r.run || "")}" style="stroke-opacity:${(0.2 + 0.8 * q).toFixed(2)};stroke-width:${(1.2 + 1.3 * q).toFixed(2)};animation-delay:${n * 20}ms"><title>${esc(tip)}</title></path>`;
  }).join("");
  const labels = axes.map((k, i) => `<line x1="${x(i)}" x2="${x(i)}" y1="12" y2="${12 + H}" class="pc-axis"/>
    <text x="${x(i)}" y="${H + 30}" text-anchor="${i === 0 ? "start" : i === axes.length - 1 ? "end" : "middle"}" class="pc-label">${esc(k === "__score" ? metric : k)}</text>`).join("");
  return `<h3>How settings led to the score</h3><p class="hint">One line per run, from each setting to its score. Darker lines scored better. Point at a line to see its values.</p>
    <div class="pc-wrap"><svg class="pcoords" viewBox="0 0 ${Wd} ${H + 40}" style="width:100%;max-width:${Wd}px">${labels}${lines}</svg></div>`;
}

/// "지금까지 최고" 선(맥 앱 BestSoFar와 같은 규칙): 시도 순서대로, 최고점을 찾은 시도는 금색
function bestSoFarHTML(s) {
  const bs = s.best_so_far || [], pts = bs.map((v, i) => [i + 1, v]).filter((p) => p[1] != null);
  if (pts.length < 2) return "";
  const W = 560, H = 110, n = bs.length, lo = Math.min(...pts.map((p) => p[1])), hi = Math.max(...pts.map((p) => p[1])), span = hi - lo || 1;
  const x = (i) => 20 + (W - 40) * (i - 1) / Math.max(n - 1, 1), y = (v) => 10 + (H - 20) * (s.higher === false ? (v - lo) : (hi - v)) / span;
  const last = pts[pts.length - 1][1], found = pts.find((p) => p[1] === last)[0];
  const d = pts.map((p, k) => (k ? `H${x(p[0]).toFixed(1)}V${y(p[1]).toFixed(1)}` : `M${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`)).join("");
  const guide = s.mode === "smart" && n > 4 ? `<line x1="${x(4.5)}" x2="${x(4.5)}" y1="4" y2="${H - 4}" class="pc-axis" stroke-dasharray="4 3"/><text x="${x(4.5) + 4}" y="12" class="hint" font-size="10.5">guided from here</text>` : "";
  return `<h3>Best so far</h3><p class="hint">The best score was found at run ${found} of ${n}.</p>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px">${guide}<path d="${d}" fill="none" stroke="var(--brand)" stroke-width="2"/>
    ${pts.map((p) => `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="${p[0] === found ? 5 : 2.5}" fill="${p[0] === found ? "var(--gold)" : "var(--brand)"}"/>`).join("")}</svg>`;
}

/// 두 목표: 가로 = 두 번째 목표, 세로 = 점수. 앞줄(파레토)은 강조색 큰 점을 계단 선으로 잇는다(맥 앱 ParetoChart와 같은 규칙)
function paretoHTML(s, metric) {
  if (!s.second) return "";
  const pts = s.rows.filter((r) => r.best != null && r.second != null);
  if (pts.length < 2) return "";
  const front = new Set(s.pareto || []), unit = s.second === "size" ? "Model size (MB)" : "Training time (seconds)";
  const W = 560, H = 170, xs = pts.map((r) => r.second), ys = pts.map((r) => r.best);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const x = (v) => 30 + (W - 50) * (x1 > x0 ? (v - x0) / (x1 - x0) : 0.5), y = (v) => 12 + (H - 40) * (y1 > y0 ? (y1 - v) / (y1 - y0) : 0.5);
  const line = pts.filter((r) => front.has(r.job)).sort((a, b) => a.second - b.second);
  const d = line.map((r, k) => (k ? `H${x(r.second).toFixed(1)}V${y(r.best).toFixed(1)}` : `M${x(r.second).toFixed(1)},${y(r.best).toFixed(1)}`)).join("");
  const tip = (r) => Object.keys(r.trial).map((k) => `${k} ${r.trial[k]}`).join(" · ") + ` → ${r.best.toFixed(4)}, ${r.second}`;
  return `<h3>Best trade-offs</h3><p class="hint">Each dot is a run. The highlighted ones are not beaten on both ${esc(metric)} and ${s.second === "size" ? "model size" : "training time"}.</p>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px"><path d="${d}" fill="none" stroke="var(--brand)" stroke-opacity=".5" stroke-width="1.5"/>
    ${pts.map((r) => `<circle cx="${x(r.second)}" cy="${y(r.best)}" r="${front.has(r.job) ? 5 : 3}" fill="${front.has(r.job) ? "var(--brand)" : "var(--soft)"}" fill-opacity="${front.has(r.job) ? 1 : .5}"><title>${esc(tip(r))}</title></circle>`).join("")}
    <text x="${W / 2}" y="${H - 4}" text-anchor="middle" class="pc-label">${unit}</text></svg>`;
}
