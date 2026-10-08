"use strict";
// 학습 기록 표(웹): 맥 앱 RunsTable과 같은 규칙. 칸 머리를 누르면 정렬, 위 칸에 "lr0<0.01 batch>=16 tag:sample coco"로 거르기,
// 여러 줄 골라 비교(최대 8개). 데이터는 GET /runs/table(api/table.py).

const T = { data: null, sort: "best", desc: true, q: "", sel: new Set() };
const T_MAX = 8;
const GENERIC_NAME = /^(train|exp|val|predict|run|detect|segment|pose|classify)\d*$/;
function tName(r) {                       // 흔한 이름("train")이면 상위 폴더를 붙인다(맥 앱 runDisplayName과 같은 규칙)
  if (!GENERIC_NAME.test(r.name)) return r.name;
  const parts = r.path.split(/[\\/]/).filter(Boolean).slice(0, -1).filter((p) => !["runs", "detect", "segment", "pose", "classify", "obb"].includes(p));
  return parts.length ? parts[parts.length - 1] + "/" + r.name : r.name;
}

function tMatch(r, q) {
  for (const tok of q.split(/\s+/).filter(Boolean)) {
    if (tok.startsWith("tag:")) { if (!r.tags.some((g) => g.toLowerCase().includes(tok.slice(4).toLowerCase()))) return false; continue; }
    const m = tok.match(/^([^<>=!]+)(<=|>=|!=|<|>|=)(.*)$/);
    if (m) {
      const [, k, op, want] = m;
      const have = k === "best" ? (r.best ?? "") : k === "epoch" ? r.epoch : (r.args[k] ?? "");
      const a = parseFloat(have), b = parseFloat(want);
      const num = !isNaN(a) && !isNaN(b) && String(have).trim() !== "" && want.trim() !== "";
      const ok = num ? { "<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b, "!=": a !== b, "=": a === b }[op]
                     : (op === "!=" ? !String(have).toLowerCase().includes(want.toLowerCase()) : op === "=" && String(have).toLowerCase().includes(want.toLowerCase()));
      if (!ok) return false;
      continue;
    }
    const hay = [tName(r), r.path, r.state, ...Object.values(r.args)].join(" ").toLowerCase();
    if (!hay.includes(tok.toLowerCase())) return false;
  }
  return true;
}

function tValue(r, k) {
  // 낮을수록 좋은 지표는 부호를 뒤집어 한 표에서도 "위가 더 좋은 쪽"이 되게 한다
  if (k === "best") return r.best == null ? -Infinity : (r.metric_higher === false ? -r.best : r.best);
  if (k === "epoch") return r.total ?? 0;
  if (k === "idle") return r.idle ?? Infinity;
  if (k === "name") return tName(r);
  const v = r.args[k]; const n = parseFloat(v);
  return v == null || v === "" ? null : isNaN(n) ? v : n;
}

async function drawTable() {
  try { T.data = await api("runs/table"); } catch { T.data = { keys: [], rows: [] }; }
  paintTable();
}

function paintTable() {
  const d = T.data; if (!d) return;
  const rows = d.rows.filter((r) => tMatch(r, T.q)).sort((a, b) => {
    const x = tValue(a, T.sort), y = tValue(b, T.sort);
    if (x == null || y == null) return x == null ? 1 : -1;                    // 빈 칸은 늘 아래
    const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
    return T.desc ? -c : c;
  });
  // 지표가 섞인 표에서 최고를 하나 고르면 뜻이 없다. 같은 지표가 한 종류일 때만 강조한다
  const kinds = new Set(d.rows.filter((r) => r.best != null).map((r) => r.metric_name || ""));
  const cmp = d.rows.some((r) => r.metric_higher === false) ? Math.min : Math.max;
  const top = kinds.size === 1 ? cmp(...d.rows.filter((r) => r.best != null).map((r) => r.best)) : null;
  const head = (k, label) => `<th class="sortable ${T.sort === k ? "on" : ""}" data-sort="${esc(k)}">${esc(label)}${T.sort === k ? (T.desc ? " ↓" : " ↑") : ""}</th>`;
  const dot = { running: "var(--good)", starting: "var(--good)", failed: "var(--bad)", stalled: "var(--warn)", done: "var(--brand)" };
  $("#main").innerHTML = `<div class="card" style="padding:14px">
    <div class="toolbar" style="margin:0 0 10px;flex-wrap:wrap">
      <input id="tq" type="search" placeholder="${esc(t("Filter"))}: lr0<0.01  batch>=16  tag:sample  coco" value="${esc(T.q)}" style="flex:1;min-width:200px"
        title="name or text, key<value · key>=value · key=value · key!=value, tag:name. All must match.">
      <span class="hint" style="margin:0">${rows.length} of ${d.rows.length}</span>
      <button class="btn primary" id="tcmp" ${T.sel.size >= 2 && T.sel.size <= T_MAX ? "" : "disabled"}>Compare ${T.sel.size}</button>
    </div>
    <div style="overflow-x:auto"><table class="runs-table"><tr><th></th>${head("name", "Run")}${head("best", "Score")}${head("epoch", axisLabel(rows, "Epochs", "Steps", "Epochs / steps"))}
      ${d.keys.map((k) => head(k, k)).join("")}<th>${t("Tags")}</th>${head("idle", t("Updated"))}</tr>
      ${rows.map((r) => `<tr class="pick" data-path="${esc(r.path)}">
        <td><input type="checkbox" class="tsel" ${T.sel.has(r.path) ? "checked" : ""} aria-label="${esc(t("Select {name}", { name: tName(r) }))}"></td>
        <td><span class="dot" style="display:inline-block;margin:0 6px 0 0;--c:${dot[r.state] || "var(--soft)"}"></span>${r.star ? "⭐ " : ""}${esc(tName(r))}</td>
        <td class="num" style="${top != null && r.best === top ? "color:var(--brand);font-weight:600" : ""}">${r.best != null ? r.best.toFixed(4) : "–"}</td>
        <td class="num">${xnum(r, r.epoch)}/${xnum(r, r.total)}${isStep(r) ? " " + t("steps") : ""}</td>
        ${d.keys.map((k) => `<td class="num">${esc(r.args[k] ?? "–")}</td>`).join("")}
        <td class="hint" style="margin:0">${r.tags.map((g) => "#" + esc(g)).join(" ")}</td><td class="hint" style="margin:0">${r.idle != null ? dur(r.idle) + " ago" : "–"}</td></tr>`).join("")}
    </table></div></div>`;
  const q = $("#tq");
  q.oninput = () => { T.q = q.value; const pos = q.selectionStart; paintTable(); const n = $("#tq"); n.focus(); n.setSelectionRange(pos, pos); };
  document.querySelectorAll("th.sortable").forEach((th) => th.onclick = () => {
    const k = th.dataset.sort; if (T.sort === k) T.desc = !T.desc; else { T.sort = k; T.desc = k === "best"; }
    paintTable();
  });
  document.querySelectorAll(".tsel").forEach((c) => c.onclick = (e) => {
    e.stopPropagation();
    const p = c.closest("tr").dataset.path;
    if (c.checked) { if (T.sel.size >= T_MAX) { c.checked = false; toast(`Pick up to ${T_MAX} runs`, true); return; } T.sel.add(p); } else T.sel.delete(p);
    paintTable();
  });
  document.querySelectorAll("tr.pick").forEach((tr) => tr.onclick = () => { S.sel = tr.dataset.path; tab("runs"); });
  $("#tcmp").onclick = () => { S.picks = [...T.sel]; tab("compare"); };
}
