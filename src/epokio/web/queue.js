"use strict";
// 대기열 탭: 작업 목록·순서·로그·실패 원인·취소
const JOB = { queued: [t("Waiting"), "var(--soft)"], running: [t("Running"), "var(--green)"], done: [t("Done"), "var(--accent)"],
              failed: [t("Failed"), "var(--red)"], cancelled: [t("Cancelled"), "var(--soft)"] };
const KIND = { train: tc("kind", "Training"), evaluate: t("Evaluation"), autolabel: t("Auto-labelling"), export: t("Export"), script: t("Script"), setup: t("Python setup") };
const JRANK = { running: 0, queued: 1 };
async function drawQueue(periodic) {
  // ★잠금 카드도 4초마다 다시 그리면 붙여 넣던 토큰이 지워진다
  if (!S.token || S.locked) { if (setMain(lockedHTML(t("The queue needs this machine's token")), periodic)) wireLock(); return; }
  if (!S.jobs) await loadJobs();
  if (S.locked) return drawQueue(periodic);
  const now = Date.now() / 1000;
  // 도는 것 → 기다리는 것(대기열 순서 그대로) → 끝난 것(최근부터)
  const jobs = (S.jobs || []).map((j, i) => ({ ...j, i })).sort((a, b) =>
    (JRANK[a.state] ?? 2) - (JRANK[b.state] ?? 2) || ((JRANK[a.state] ?? 2) < 2 ? a.i - b.i : (b.ended || b.created) - (a.ended || a.created)));
  const waiting = jobs.filter((j) => j.state === "queued").map((j) => j.id);
  const g = ++S.gen, wait = [];
  for (const id of Object.keys(S.logs)) {                               // 펼쳐 둔 로그는 도는 동안 새로
    const j = jobs.find((x) => x.id === id);
    if (j && (j.state === "running" || S.logs[id] == null))
      wait.push(api("jobs/" + id + "/log?lines=200").then((x) => { if (id in S.logs) S.logs[id] = x.log; }, () => { }));
  }
  for (const j of jobs) {                                              // 실패한 작업은 원인·고칠 방법을 한 번만 물어 둔다
    if (j.state === "failed" && !(j.id in S.diag)) {
      S.diag[j.id] = [];                                                // ★먼저 자리를 잡는다. 안 그러면 받는 사이 다음 갱신이 또 물었다
      wait.push(api("jobs/" + j.id + "/diagnose").then((x) => S.diag[j.id] = x.hints, () => { }));
    }
  }
  await Promise.all(wait);                                              // 하나씩 기다리지 않고 한꺼번에
  if (g !== S.gen || S.tab !== "queue") return;
  // 도는 학습의 진행은 감시기가 이미 안다(Runs와 같은 값). 작업 출력 폴더로 짝을 찾는다
  const norm = (p) => (p || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  const progress = (j) => {
    // 도는 학습과만 짝짓는다(★이름이 겹치면 끝난 옛 학습이 잡혀 50/50이 보였다)
    const r = j.state === "running" && j.output && S.runs.find((x) => norm(x.path) === norm(j.output) && ["running", "starting", "stalled"].includes(x.state));
    if (!r || !r.total) return "";
    return " · " + xprog(r) + (r.eta ? " · " + t("about {d} left, done around {time}", { d: dur(r.eta), time: new Date(Date.now() + r.eta * 1000).toLocaleTimeString(LOCALE, HM) }) : "");   // ★[]면 브라우저 언어라 영어 화면에 '오후 11:15'가 섞인다
  };
  const hints = (j) => (S.diag[j.id] || []).map((h) => `<div class="msg" style="--c:var(--red);margin:6px 0 0"><b>${esc(h.title)}.</b> ${esc(h.fix)}</div>`).join("");
  const row = (j, k) => {
    const [st, c] = JOB[j.state] || [esc(j.state), "var(--soft)"];
    const when = j.state === "running" ? t("for {d}", { d: dur(now - (j.started || now)) }) : j.state === "queued" ? t("added {d} ago", { d: dur(now - j.created) })
      : j.ended ? (j.started ? dur(j.ended - j.started) + " · " : "") + t("ended {d} ago", { d: dur(now - j.ended) }) : "";   // 시작도 못 한 건 걸린 시간이 없다
    const exit = j.returncode && j.state !== "cancelled" ? " · " + t("exit {code}", { code: j.returncode }) : "";   // 멈추면 죽인 흔적으로 1이 남는다. 실패가 아니다
    const w = waiting.indexOf(j.id);
    const ops = [
      w > 0 ? `<button class="btn small needs-run" data-op="up" title="${t("Move up")}" aria-label="${t("Move up")}: ${esc(j.name)}">↑</button>` : "",
      w >= 0 && w < waiting.length - 1 ? `<button class="btn small needs-run" data-op="down" title="${t("Move down")}" aria-label="${t("Move down")}: ${esc(j.name)}">↓</button>` : "",
      `<button class="btn small" data-op="log" aria-expanded="${j.id in S.logs}" aria-label="${j.id in S.logs ? t("Hide log") : t("Log")}: ${esc(j.name)}">${j.id in S.logs ? t("Hide log") : t("Log")}</button>`,
      j.state === "running" || j.state === "queued" ? `<button class="btn small danger needs-run" data-op="cancel" data-stop="${j.state === "running" ? 1 : ""}" aria-label="${j.state === "running" ? t("Stop") : t("Cancel")}: ${esc(j.name)}">${j.state === "running" ? t("Stop") : t("Cancel")}</button>` : "",
    ].join("");
    return `<div class="job ${j.state}" style="--c:${c};animation-delay:${Math.min(k, 12) * 20}ms" data-id="${esc(j.id)}"><span class="dot"></span>
      <span class="name">${esc(j.name)}</span><span class="ops">${ops}</span>
      <span class="meta"><span class="pill" style="--c:${c}">${st}</span> ${KIND[j.kind] || esc(j.kind)} · ${when}${progress(j)}${exit}${j.output ? " · " + esc(j.output) : ""}</span>${hints(j)}
      ${j.id in S.logs ? `<pre class="log" data-keep="log-${esc(j.id)}">${esc(S.logs[j.id] ?? t("Loading…")) || t("No output yet.")}</pre>` : ""}</div>`;
  };
  if (!setMain(`<div class="card pane" style="max-width:none;padding:6px 0 0"><div style="display:flex;align-items:center;padding:12px 20px 6px">
      <h2>${t("Queue")}</h2><span class="hint" style="margin:0 0 0 auto">${t("One at a time on {machine}", { machine: esc(S.label || t("this machine")) })}</span>
      <button class="btn small needs-run" style="margin-left:12px" id="newrun">${t("New run")}</button></div>
    ${jobs.length ? jobs.map(row).join("") : `<div class="empty">${ART.queue}${t("Nothing here yet. Start a run from Train, or from the Mac app.")}</div>`}
    <div style="padding:0 20px 14px">${forgetHTML}</div></div>`, periodic)) return;
  wireForget();
  $("#newrun").onclick = () => tab("train");
  document.querySelectorAll(".job .btn").forEach((b) => b.onclick = async () => {
    const id = b.closest(".job").dataset.id, op = b.dataset.op;
    if (op === "log") { if (id in S.logs) delete S.logs[id]; else S.logs[id] = null; return drawQueue(); }
    if (op === "cancel" && b.dataset.stop && !confirm(t("Stop this run? The epochs it has finished stay on disk, but it will not continue."))) return;
    // 기다리는 작업도 묻는다. ★'제거'가 바로 취소돼 되돌릴 수 없었고, 목록에서 없어지지도 않았다
    if (op === "cancel" && !b.dataset.stop && !confirm(t("Cancel {name}? It will not run, and you would have to add it again.", { name: b.closest(".job").querySelector(".name")?.textContent || "" }))) return;
    b.disabled = true;
    try { await api("jobs/" + id + "/" + op, "POST", {}); } catch (e) { if (e instanceof Locked) S.locked = true; else alert(e.message); }
    await loadJobs(); drawBusy(); drawQueue();
  });
}
