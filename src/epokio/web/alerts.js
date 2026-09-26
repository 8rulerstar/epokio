"use strict";
// 알림 탭: 사건 목록 + 폰 알림(웹후크) 설정
const EV = { finished: [t("Training finished"), "var(--green)", "✓"], failed: [t("Training failed"), "var(--red)", "✕"], stalled: [t("Training may have stopped"), "var(--orange)", "‖"],
             stopped_early: [t("Stopped before the last epoch"), "var(--orange)", "■"], started: [t("Training started"), "var(--accent)", "▶"],
             job_done: [t("Job finished"), "var(--green)", "✓"], job_failed: [t("Job failed"), "var(--red)", "✕"], goal: [t("Goal reached"), "var(--green)", "◎"],
             disk_low: [t("Disk almost full"), "var(--orange)", "!"], gpu_hot: [t("GPU is very hot"), "var(--orange)", "!"], gpu_mem: [t("GPU memory is full"), "var(--orange)", "!"], recovered: [t("Training resumed"), "var(--accent)", "↻"],
             pruned: [t("Sweep stopped a run that fell behind"), "var(--purple)", "✂"] };
/// 폰 알림(ntfy·Slack·Discord·Telegram 웹후크). 학습 기계의 agent가 직접 보낸다(맥이 꺼져 있어도 온다).
/// ★예전엔 맥 앱 설정에만 있어서 윈도우·폰만 쓰는 사람은 켤 방법이 없었다
function phoneHTML() {
  const h = S.hooks;
  const now = h && h.count ? t("On: sends to {hosts}.", { hosts: h.hosts.map(esc).join(", ") }) : t("Off.");
  return `<details class="card" id="phone" style="padding:12px 16px;margin-bottom:12px" ${S.phoneOpen ? "open" : ""}>
    <summary style="cursor:pointer;font-weight:600">${t("Phone alerts")} <span class="hint" style="font-weight:400">${now}</span></summary>
    <p class="hint">${t("Easiest: install the free <b>ntfy</b> app on your phone, subscribe to a topic with a long random name, and paste <code>https://ntfy.sh/your-topic</code> here. Slack, Discord and Telegram webhook addresses work too. Anyone who knows the topic can read it, so make it hard to guess.")}</p>
    <div class="inrow"><input class="in" id="hookurl" aria-label="${t("Webhook address")}" placeholder="https://ntfy.sh/epokio-7f3k9q" spellcheck="false">
      <button class="btn primary" id="hooksave">${t("Save")}</button>${h && h.count ? `<button class="btn" id="hookoff">${t("Turn off")}</button>` : ""}</div>
    <div id="hookmsg" role="status"></div></details>`;
}
function wirePhone() {
  const d = $("#phone"); if (!d) return;
  d.ontoggle = () => { S.phoneOpen = d.open; };
  const save = async (urls) => {
    const box = $("#hookmsg");
    if (!await needToken(t("Changing alerts needs this machine's token"))) return;
    // 더하기(add): 슬랙 등 이미 있는 웹후크를 지우지 않는다. 끄기는 빈 목록을 그대로 보낸다
    try { await api("webhooks", "POST", urls.length ? { urls, add: true } : { urls }); S.hooks = await api("webhooks"); S.lastMain = ""; drawInbox(); }
    catch (e) { box.innerHTML = `<div class="msg" style="--c:var(--red)"><b>${t("Not saved.")}</b> ${esc(e instanceof Locked ? t("The token did not work.") : e.message)}</div>`; }
  };
  $("#hooksave").onclick = () => { const u = cleanPath($("#hookurl").value); if (u) save([u]); };
  const off = $("#hookoff"); if (off) off.onclick = () => save([]);
}
async function drawInbox(periodic) {
  if (!periodic || !S.hooks) { try { S.hooks = await api("webhooks"); } catch { S.hooks = null; } if (S.tab !== "inbox") return; }
  const items = S.events, runs = new Set(S.runs.map((x) => x.path));
  const wired = setMain(phoneHTML() + `<div class="card inbox">${items.length ? items.map((e, i) => {
    // ★이름을 t로 두면 번역 함수 t()를 가려서, 학습이 붙은 알림이 하나라도 있으면 알림 탭 전체가 TypeError로 안 그려졌다
    const [title, c, ic] = EV[e.kind] || [esc(e.kind), "var(--soft)", "•"]; const r = e.run || {};
    // 기계 경고·작업 알림은 에폭이 없다(★'epoch 0/?'가 찍혔다). 학습 목록에 있는 것만 누르면 그 학습으로 간다
    const ep = r.total != null ? " · " + t("epoch {e}/{n}", { e: r.epoch ?? "?", n: r.total }) : "";
    return `<div class="item" ${runs.has(r.path) ? 'role="button" tabindex="0"' : ""} style="animation-delay:${Math.min(i, 12) * 20}ms;${runs.has(r.path) ? "" : "cursor:default"}" data-path="${runs.has(r.path) ? esc(r.path) : ""}"><span class="ico" style="--c:${c}">${ic}</span>
      <div style="flex:1;min-width:0"><div style="font-weight:${e.seq > S.seen ? 700 : 500}">${title}</div>
      <div class="hint" style="margin:0;overflow-wrap:anywhere">${esc(r.name ? display(r) : "")}${ep}${r.best != null ? " · " + t("best {v}", { v: r.best.toFixed(4) }) : ""}</div></div>
      <span class="hint when" style="margin:0">${new Date(e.at * 1000).toLocaleString(LOCALE, { hour12: false })}</span></div>`; }).join("")
    : `<div class="empty">${t("No notifications yet. When a run finishes, fails or stalls, it shows up here.")}</div>`}</div>`, periodic);
  if (wired) wirePhone();
  document.querySelectorAll(".inbox .item").forEach((el) => el.onclick = () => { if (el.dataset.path) { S.sel = el.dataset.path; tab("runs"); } });
  if (items[0]) { S.seen = items[0].seq; LS.epokioSeen = S.seen; drawBadge(); }
}
