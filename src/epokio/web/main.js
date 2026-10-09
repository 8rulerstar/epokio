"use strict";
// 마지막에 불러온다: 탭·언어 버튼을 달고, 트레이가 넘긴 토큰을 받고, 새로 고침을 시작한다
document.querySelectorAll("nav button[data-tab]").forEach((b) => b.onclick = () => tab(b.dataset.tab));
// 탭은 화살표·Home·End로 옮긴다(WAI-ARIA 탭 방식: 고른 탭만 Tab 순서에 있다). ★Tab으로 아홉 번 지나야 했고 화살표는 먹지 않았다
$("#tabs").addEventListener("keydown", (e) => {
  const tabs = [...document.querySelectorAll("#tabs [role=tab]")].filter((b) => b.offsetParent !== null);   // 숨긴 탭(더 보기)은 건너뛴다
  const i = tabs.indexOf(document.activeElement), j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
  if (i < 0 || j == null) return;
  e.preventDefault(); const b = tabs[(j + tabs.length) % tabs.length]; b.focus(); tab(b.dataset.tab);
});
$("#tabs").setAttribute("aria-label", t("Sections"));
// 곁가지 기능(검수·스윕)은 기본 탭에서 숨긴다. '더 보기'로 켜고 끄며 이 브라우저에 기억한다(코드는 그대로)
{ const more = $("#more");
  const show = (on) => { document.body.classList.toggle("adv", on); more.setAttribute("aria-pressed", on);
    more.textContent = on ? t("Fewer") : t("More");
    if (!on && document.querySelector("nav [data-adv].on")) tab("runs"); };
  let on = false; try { on = LS.epokioAdv === "1"; } catch { }
  show(on);
  more.onclick = () => { on = !on; try { LS.epokioAdv = on ? "1" : "0"; } catch { } show(on); }; }
// 탭 이름과 언어 버튼. 탭 버튼 안의 뱃지(span)는 그대로 두고 앞 글자만 바꾼다
{ const NAV = { runs: t("Runs"), table: t("Table"), train: t("Train"), queue: t("Queue"), compare: t("Compare"), review: t("Review"), sweeps: t("Sweeps"), inbox: t("Alerts") };
  document.querySelectorAll("nav button").forEach((b) => { if (NAV[b.dataset.tab]) b.firstChild.textContent = NAV[b.dataset.tab]; });
  const l = $("#lang");
  l.textContent = LANG === "ko" ? "English" : "한국어";
  l.lang = LANG === "ko" ? "en" : "ko";
  l.title = t("Change the language of this page");
  l.onclick = () => { try { LS.epokioLang = LANG === "ko" ? "en" : "ko"; } catch { } location.reload(); }; }
document.addEventListener("keydown", (e) => {
  // 키보드로도 학습·알림·그림을 고른다(div라 원래는 Tab으로 갈 수도 Enter로 누를 수도 없었다)
  if ((e.key === "Enter" || e.key === " ") && e.target.getAttribute?.("role") === "button") { e.preventDefault(); e.target.click(); }
});
// 이 기계의 트레이·setup이 연 주소면 '#t=토큰'이 붙어 온다(auth.page_url, 같은 기계 주소일 때만).
// '#' 뒤는 서버로 가지 않는다. 저장하고 주소창에서 바로 지운 뒤, 그림용 HttpOnly 쿠키를 받는다
function takeHashToken() {
  const m = location.hash.match(/[#&]t=([\w-]+)/);
  if (!m) return false;
  S.token = m[1]; S.locked = false; LS.epokioToken = m[1]; history.replaceState(null, "", location.pathname + location.search); login();
  return true;
}
if (!takeHashToken() && S.token) login();      // 저장된 토큰도 무엇을 할 수 있는지 묻는다(보기 전용이면 바꾸는 단추를 숨긴다)
// 이미 열린 탭에 새 '#t='가 오면(트레이에서 또 열거나 주소를 붙여 넣음) 그 토큰으로 바꾼다. ★처음 열 때만 읽어서 옛 토큰(잠김)이 그대로였다
addEventListener("hashchange", () => { if (takeHashToken()) { S.lastMain = ""; refresh(); } });
{ const ro = $("#ro"); if (ro) { ro.textContent = t("view only"); ro.title = t("This token can only view. Changing things needs a token that can run."); } }
{ const sk = $("#skeltext"); if (sk) sk.textContent = t("Loading…"); }     // 처음 불러오는 동안 화면 읽기 프로그램에도(role=status)
// 토큰을 보는 명령(autostart.cli 모양). 이 기계에서 연 화면에만 온다. ★잠금 카드가 윈도우 PATH에 없는 명령(epokio-agent)을 안내했다
api("health").then((h) => { S.tokenCmd = h.token_cmd || ""; }).catch(() => {});
refresh();
setInterval(() => { if (!document.hidden && !document.querySelector(".lightbox, .modal, dialog[open]")) refresh(true); }, 4000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(true); });   // 돌아오면 4초를 기다리지 않고 바로
