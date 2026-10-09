"use strict";
// 학습 상세의 "에폭별 예측": 같은 검증 이미지 4장을 몇 에폭마다 예측한 사진(jobs_templates.add_snapshots). 슬라이더로 넘긴다.

function snapshotsHTML(r, d) {
  const s = d.snapshots; if (!s) return "";
  const last = s.epochs.length - 1;
  return `<h3>${t("Predictions by epoch")}</h3><p class="hint">${t("The same validation images, predicted as training went on. Drag to compare.")}</p>
    <div class="toolbar"><input id="snapx" type="range" min="0" max="${last}" value="${last}" style="flex:1" aria-label="${esc(t("Epoch"))}"><b id="snapep" class="num">${t("epoch {n}", { n: s.epochs[last] })}</b></div>
    <div class="gallery snaps" id="snapg">${snapFigures(r, s, last)}</div>`;
}

function snapFigures(r, s, k) {
  return (s.files[String(s.epochs[k])] || []).map((n) => { const src = "file?path=" + encodeURIComponent(r.path + "/epokio_snapshots/" + n);
    return `<figure role="button" tabindex="0" aria-label="${esc(n)}" data-src="${src}"><img src="${src}" alt=""></figure>`; }).join("");
}

function bindSnapshots(r, d) {
  const x = $("#snapx"); if (!x) return;
  x.oninput = () => {
    const k = +x.value; $("#snapep").textContent = t("epoch {n}", { n: d.snapshots.epochs[k] });
    const g = $("#snapg"); g.innerHTML = snapFigures(r, d.snapshots, k);
    g.querySelectorAll("figure").forEach((f) => f.onclick = () => lightbox(f.dataset.src, f.getAttribute("aria-label")));
  };
}
