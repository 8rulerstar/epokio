"use strict";
// 학습 기록 목록 아래의 "SSH 서버": 맥 앱(SSHMachines.swift)과 같은 GET /ssh를 읽어 보여 준다(api/ssh.py).
// 연결·마지막으로 읽은 때·오류·학습 수, 크기 제한을 넘어 건너뛴 로그 파일. 보기 전용 + "지금 읽기"(POST /ssh/refresh)
async function loadSSH() {
  try { S.ssh = (await api("ssh")).hosts || []; } catch { S.ssh = S.ssh || []; }   // 토큰이 없거나 옛 agent면 조용히 비운다
}
const sshSize = (n) => (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB";
function sshHTML() {
  const hosts = S.ssh || [];
  if (!hosts.length) return "";
  const now = Date.now() / 1000, prev = S.sshRuns || {}, next = {};
  const row = (h, i) => {
    const st = h.status || {}, ok = st.ok === true, bad = st.ok === false;
    const c = ok ? "var(--green)" : bad ? "var(--red)" : "var(--soft)";
    const n = st.runs ?? null; next[h.host] = n;
    const bump = n != null && prev[h.host] != null && prev[h.host] !== n ? " bump" : "";   // 학습 수가 바뀌면 숫자가 한 번 튄다
    const seen = st.at ? t("read {d} ago", { d: dur(now - st.at) }) : t("Not read yet");
    const state = ok ? t("Connected") : bad ? esc(st.error || t("Could not connect")) : t("Waiting");
    const all = st.skipped || [], sk = all.filter((x) => x.kept == null), kept = all.length - sk.length;   // kept 있으면 끝부분만 받은 것
    const skip = sk.length ? `<div class="msg" style="--c:var(--orange)"><b>${t("{n} log files over the size limit were skipped", { n: sk.length })}</b>
      <ul>${sk.slice(0, 8).map((x) => `<li title="${esc(x.path + "/" + x.name)}">${esc(x.name)} · ${sshSize(x.size)}</li>`).join("")}${sk.length > 8 ? `<li>${t("and {n} more", { n: sk.length - 8 })}</li>` : ""}</ul></div>` : "";
    const part = kept ? `<div class="msg" style="--c:var(--orange)">${t("{n} large log files: only the last part was loaded", { n: kept })}</div>` : "";
    const trunc = st.truncated ? `<div class="msg" style="--c:var(--orange)">${t("Too many folders to read")}</div>` : "";
    return `<div class="sshrow" style="--c:${c};animation-delay:${Math.min(i, 12) * 20}ms" data-host="${esc(h.host)}"><span class="dot"></span>
      <span class="name">${esc(h.host)}</span><span class="sshn${bump}" title="${t("Runs")}">${n ?? "–"}</span>
      <span class="meta">${state} · ${seen}</span>${skip}${part}${trunc}</div>`;
  };
  const body = hosts.map(row).join("");
  S.sshRuns = next;
  const open = S.sshOpen ?? hosts.some((h) => h.status?.ok === false || h.status?.skipped?.some((x) => x.kept == null));   // 문제가 있으면 펼쳐 둔다
  return `<details class="sshbox" id="sshbox"${open ? " open" : ""}><summary>${t("SSH servers")} <span class="pill" style="--c:var(--soft)">${hosts.length}</span>
    <button type="button" class="btn small" id="sshread" title="${t("Read now")}">${t("Read now")}</button></summary>${body}</details>`;
}
function wireSSH() {
  const b = $("#sshbox"); if (!b) return;
  b.ontoggle = () => { S.sshOpen = b.open; };
  const r = $("#sshread");
  if (r) r.onclick = (e) => { e.preventDefault(); act(r, async () => { await apiPost("ssh/refresh"); await new Promise((ok) => setTimeout(ok, 3000)); await loadSSH(); drawRuns(); }); };
}
