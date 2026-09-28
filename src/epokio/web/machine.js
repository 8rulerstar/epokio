"use strict";
// 학습 상세의 "학습하는 동안의 기계": GPU·CPU·메모리·팬 사용률 곡선과 평균. 기록은 agent(epokio/sysrec.py).

const MACHINE_COLS = [["gpu", "GPU", "var(--accent)"], ["gmem", "GPU memory", "var(--purple)"], ["cpu", "CPU", "var(--green)"],
                      ["mem", "MEM", "var(--orange)"], ["fan", "Fan", "var(--soft)"]];

function machineHTML(r, d) {
  const m = d.system; if (!m) return "";
  const x = m.minutes, series = MACHINE_COLS.filter(([k]) => m.columns[k]).map(([k, name, color]) => ({ name: t(name) + " %", x, y: m.columns[k], color }));
  const avg = (k, unit) => m.avg[k] == null ? "" : `<div class="tile"><b>${Math.round(m.avg[k])}${unit}</b><span>${esc(t(MACHINE_COLS.find((c) => c[0] === k)?.[1] || (k === "temp" ? "SoC temperature" : "GPU temperature")))}</span></div>`;
  return `<h3>${t("Machine while training")}</h3><p class="hint">${t("Recorded every 15 seconds while this run trained. Averages below.")}${m.shared ? " " + t("Other runs trained at the same time, so these are shared numbers.") : ""}</p>`
    + chart(series, { xname: (v) => t("{n} min", { n: Math.round(v) }), digits: 0, range: [0, 100] })
    + `<div class="tiles">${avg("gpu", "%")}${avg("gmem", "%")}${avg("cpu", "%")}${avg("mem", "%")}${avg("fan", "%")}${avg("gtemp", "°C")}${avg("temp", "°C")}</div>`;
}
