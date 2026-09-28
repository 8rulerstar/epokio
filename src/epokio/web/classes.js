"use strict";
// 학습 상세의 클래스별 성능. 계산은 agent(epokio/classes.py), 여기는 /run 의 classes 를 그린다.
// 없으면(밖에서 돌린 학습) "클래스별로 계산" 버튼: POST /classes 가 best.pt 검증 작업을 대기열에 넣는다.

const PER_CLASS_HEADS = { box: "Box", pose: "Pose", mask: "Mask", obb: "OBB" };

function perClassHTML(r, d) {
  const c = d.classes, local = r.source === "local" || r.source === S.label;
  if (!c) {
    if (!d.weights || d.framework !== "ultralytics") return "";
    return `<h3>${t("Per class")}</h3><p class="hint">${t("Which classes pull the score down. Runs Epokio starts save this at the end; for this one it takes one validation pass with best.pt.")}</p>`
      + (local ? `<button class="btn" id="clscalc">${t("Work out per-class scores")}</button>` : `<p class="hint">${t("Start it on the machine that has this run.")}</p>`);
  }
  let h = `<h3>${t("Per class")}</h3><p class="hint">${c.source === "val" ? t("From a validation pass with best.pt.") : t("From the last validation of this run.")} ${t("Weakest first. Highlighted: well below the class average.")}</p>`;
  for (const x of c.heads) {
    const bar = (v) => v == null ? "–" : `<span class="clsbar" style="--w:${Math.round(v * 100)}%"></span>${v.toFixed(3)}`;
    h += (c.heads.length > 1 ? `<div style="font-weight:600;margin-top:8px">${PER_CLASS_HEADS[x.head] || esc(x.head)}</div>` : "")
      + `<table class="cls"><tr><th>${t("Class")}</th><th class="num">${t("Examples")}</th><th class="num">${t("Precision")}</th><th class="num">${t("Recall")}</th><th class="num">mAP50</th><th>${esc(x.main)}</th></tr>`
      + x.rows.map((row, i) => `<tr class="${row.weak ? "weak" : ""}" style="animation-delay:${Math.min(i, 12) * 30}ms"><th>${esc(row.name)}${row.few ? ` <span class="pill" style="--c:var(--orange)" title="${esc(t("Few examples: the score is shaky"))}">${t("few")}</span>` : ""}</th>`
        + `<td class="num">${row.instances ?? "–"}</td><td class="num">${row.precision?.toFixed(3) ?? "–"}</td><td class="num">${row.recall?.toFixed(3) ?? "–"}</td><td class="num">${row.mAP50?.toFixed(3) ?? "–"}</td><td class="num">${bar(row[x.main])}</td></tr>`).join("")
      + `</table><p class="hint">${t("Class average")}: ${x.mean?.toFixed(3) ?? "–"}</p>`;
  }
  return h;
}

function bindPerClass(r, d) {
  const b = $("#clscalc");
  if (b) b.onclick = () => act(b, () => apiPost("classes", { path: r.path }), () => t("Added to the queue. The table appears here when it finishes."));
}
