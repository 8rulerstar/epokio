"use strict";
// 마지막에 불러온다: 탭·언어 버튼을 달고, 트레이가 넘긴 토큰을 받고, 새로 고침을 시작한다
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => tab(b.dataset.tab));
// 탭 이름과 언어 버튼. 탭 버튼 안의 뱃지(span)는 그대로 두고 앞 글자만 바꾼다
{ const NAV = { runs: t("Runs"), table: t("Table"), train: t("Train"), queue: t("Queue"), compare: t("Compare"), review: t("Review"), sweeps: t("Sweeps"), inbox: t("Alerts") };
  document.querySelectorAll("nav button").forEach((b) => { if (NAV[b.dataset.tab]) b.firstChild.textContent = NAV[b.dataset.tab]; });
  const l = $("#lang");
  l.textContent = LANG === "ko" ? "English" : "한국어";
  l.lang = LANG === "ko" ? "en" : "ko";
  l.title = t("Change the language of this page");
  l.onclick = () => { try { LS.epokioLang = LANG === "ko" ? "en" : "ko"; } catch { } location.reload(); }; }
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelector(".lightbox")?.remove();
  // 키보드로도 학습·알림·그림을 고른다(div라 원래는 Tab으로 갈 수도 Enter로 누를 수도 없었다)
  if ((e.key === "Enter" || e.key === " ") && e.target.getAttribute?.("role") === "button") { e.preventDefault(); e.target.click(); }
});
// 이 기계의 트레이·setup이 연 주소면 '#t=토큰'이 붙어 온다(auth.page_url, 같은 기계 주소일 때만).
// '#' 뒤는 서버로 가지 않는다. 저장하고 주소창에서 바로 지운 뒤, 그림용 HttpOnly 쿠키를 받는다
{ const m = location.hash.match(/[#&]t=([\w-]+)/);
  if (m) { S.token = m[1]; LS.epokioToken = m[1]; history.replaceState(null, "", location.pathname + location.search); login(); } }
refresh();
setInterval(() => { if (!document.hidden && !document.querySelector(".lightbox, .modal, dialog[open]")) refresh(true); }, 4000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(true); });   // 돌아오면 4초를 기다리지 않고 바로
