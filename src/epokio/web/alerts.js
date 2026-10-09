"use strict";
// 알림 탭: 사건 목록 + 폰 알림(웹후크) 설정
const EV = { finished: [t("Training finished"), "var(--green)", "✓"], failed: [t("Training failed"), "var(--red)", "✕"], stalled: [t("Training may have stopped"), "var(--orange)", "‖"],
             quiet: [t("Training stopped logging"), "var(--soft)", "■"],     // 계획 에폭을 모르는 학습: 끝났거나 멈췄다(급하지 않다)
             stopped_early: [t("Stopped before the last epoch"), "var(--orange)", "■"], started: [t("Training started"), "var(--accent)", "▶"],
             job_done: [t("Job finished"), "var(--green)", "✓"], job_failed: [t("Job failed"), "var(--red)", "✕"], goal: [t("Goal reached"), "var(--green)", "◎"],
             disk_low: [t("Disk almost full"), "var(--orange)", "!"], gpu_hot: [t("GPU is very hot"), "var(--orange)", "!"], gpu_mem: [t("GPU memory is full"), "var(--orange)", "!"], fan_max: [t("Fans at full speed"), "var(--orange)", "!"], recovered: [t("Training resumed"), "var(--accent)", "↻"],
             pruned: [t("Sweep stopped a run that fell behind"), "var(--purple)", "✂"] };
/// 폰 알림(ntfy·Slack·Discord·Telegram 웹후크). 학습 기계의 agent가 직접 보낸다(맥이 꺼져 있어도 온다).
/// ★예전엔 맥 앱 설정에만 있어서 윈도우·폰만 쓰는 사람은 켤 방법이 없었다
function phoneHTML() {
  const h = S.hooks;
  const now = h && h.count ? t("On: sends to {hosts}.", { hosts: h.hosts.map(esc).join(", ") }) : t("Off.");
  return `<details class="card" id="phone" style="padding:12px 16px;margin-bottom:12px" ${S.phoneOpen ? "open" : ""}>
    <summary style="cursor:pointer;font-weight:600">${t("Phone alerts")} <span class="hint" style="font-weight:400">${now}</span></summary>
    <p class="hint">${t("Easiest: install the free <b>ntfy</b> app on your phone, subscribe to a topic with a long random name, and paste <code>https://ntfy.sh/your-topic</code> here. Slack, Discord and Telegram webhook addresses work too. Anyone who knows the topic can read it, so make it hard to guess.")}</p>
    <div class="inrow needs-run"><input class="in" id="hookurl" aria-label="${t("Webhook address")}" placeholder="https://ntfy.sh/epokio-7f3k9q" spellcheck="false">
      <button class="btn primary" id="hooksave">${t("Save")}</button>${h && h.count ? `<button class="btn" id="hooktest">${t("Send a test")}</button><button class="btn" id="hookoff">${t("Turn off")}</button>` : ""}</div>
    <p class="ro-note">🔒 ${t("This token can only view, so alerts cannot be changed here.")}</p><div id="hookmsg" role="status"></div></details>`;
}
function hostOf(u) { try { return new URL(u).hostname; } catch { return ""; } }      // 주소 전체는 비밀이라 호스트만
function wirePhone() {
  const d = $("#phone"); if (!d) return;
  d.ontoggle = () => { S.phoneOpen = d.open; };
  const save = async (body) => {
    const box = $("#hookmsg");
    if (!await needToken(t("Changing alerts needs this machine's token"))) return false;
    try { await api("webhooks", "POST", body); S.hooks = await api("webhooks"); S.lastMain = ""; drawInbox(); return true; }
    catch (e) { (box || {}).innerHTML = `<div class="msg" style="--c:var(--red)"><b>${t("Not saved.")}</b> ${esc(e instanceof Locked ? t("The token did not work.") : e.message)}</div>`; return false; }
  };
  // 더하기(add): 슬랙 등 이미 있는 웹후크를 지우지 않는다
  $("#hooksave").onclick = () => { const u = cleanPath($("#hookurl").value); if (u) save({ urls: [u], add: true }); };
  // 시험 보내기: 저장된 주소마다 결과를 한 줄씩(성공 초록 ✓, 실패 빨강 ✕와 이유). 줄은 차례로 떠오른다
  const test = $("#hooktest");
  if (test) test.onclick = async () => {
    if (!await needToken(t("Changing alerts needs this machine's token"))) return;
    const r = await act(test, () => api("webhooks/test", "POST", {}), (x) => x.results.every((y) => y.ok) ? t("Test sent.") : t("Some alerts did not go through."));
    if (!r) return;
    $("#hookmsg").innerHTML = r.results.map((y, i) => `<div class="msg" style="--c:var(${y.ok ? "--green" : "--red"});animation-delay:${i * 60}ms">
      <b>${y.ok ? "✓" : "✕"} ${esc(hostOf(y.url))}</b> ${y.ok ? t("Delivered") : esc(y.error || "")}${y.status ? ` (${y.status})` : ""}</div>`).join("");
  };
  // 끄기는 저장된 주소를 전부 지운다(맥 앱·터미널에서 넣은 슬랙·텔레그램까지). 묻고, 되돌리기를 준다(agent가 지운 목록을 남긴다).
  //   ★한 번 누르면 확인 없이 다 지워졌고, 웹은 호스트만 알아 다시 넣을 수도 없었다
  const off = $("#hookoff");
  if (off) off.onclick = async () => {
    if (!confirm(t("Turn off phone alerts? This removes every saved address ({hosts}), including ones added in the Mac app or the terminal.", { hosts: (S.hooks?.hosts || []).join(", ") }))) return;
    if (await save({ urls: [] })) toast(t("Phone alerts are off."), false, { title: t("Undo"), run: () => save({ restore: true }).then((ok) => ok && toast(t("Phone alerts are back on."))) });
  };
}
async function drawInbox(periodic) {
  if (!periodic || !S.hooks) { try { S.hooks = await api("webhooks"); } catch { S.hooks = null; } if (S.tab !== "inbox") return; }
  const items = S.events, runs = new Set(S.runs.map((x) => x.path));
  const wired = setMain(phoneHTML() + `<div class="card inbox">${items.length ? items.map((e, i) => {
    // ★이름을 t로 두면 번역 함수 t()를 가려서, 학습이 붙은 알림이 하나라도 있으면 알림 탭 전체가 TypeError로 안 그려졌다
    const [title, c, ic] = EV[e.kind] || [esc(e.kind), "var(--soft)", "•"]; const r = e.run || {};
    // 기계 경고·작업 알림은 에폭이 없다(★'epoch 0/?'가 찍혔다). 학습 목록에 있는 것만 누르면 그 학습으로 간다
    const ep = r.total != null ? " · " + xprog(r) : "";
    return `<div class="item" ${runs.has(r.path) ? 'role="button" tabindex="0"' : ""} style="animation-delay:${Math.min(i, 12) * 20}ms;${runs.has(r.path) ? "" : "cursor:default"}" data-path="${runs.has(r.path) ? esc(r.path) : ""}"><span class="ico" style="--c:${c}">${ic}</span>
      <div style="flex:1;min-width:0"><div style="font-weight:${e.seq > S.seen ? 700 : 500}">${title}</div>
      <div class="hint" style="margin:0;overflow-wrap:anywhere">${esc(r.name ? display(r) : "")}${ep}${r.best != null ? " · " + t("best {v}", { v: r.best.toFixed(4) }) : ""}${originOf(r) ? " · " + esc(originOf(r)) : ""}</div></div>
      <span class="hint when" style="margin:0">${new Date(e.at * 1000).toLocaleString(LOCALE, { hour12: false })}</span></div>`; }).join("")
    : `<div class="empty">${ART.bell}${t("No notifications yet. When a run finishes, fails or stalls, it shows up here.")}</div>`}</div>`, periodic);
  if (wired) wirePhone();
  document.querySelectorAll(".inbox .item").forEach((el) => el.onclick = () => { if (el.dataset.path) { S.sel = el.dataset.path; tab("runs"); } });
  if (items[0]) { S.seen = items[0].seq; LS.epokioSeen = S.seen; drawBadge(); }
}
