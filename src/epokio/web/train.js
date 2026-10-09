"use strict";
// 잠금(토큰)과 학습 탭(파이썬 자동 설치 · 학습 시작 폼)
/// 학습 시작·대기열은 토큰이 있어야 연다. 토큰은 이 브라우저에만 남고(LS) 요청 머리말로만 간다. 그림용은 HttpOnly 쿠키
function lockedHTML(what) {
  const bad = S.locked && S.token;
  return `<div class="card locked"><div class="ico">🔒</div><h2>${what}</h2>
    <p class="hint">${t("Starting and cancelling runs is locked, so nobody else on your network can run commands here.")}<br>
    ${t("On this machine, open this page from the Epokio tray icon or <code>epokio setup</code> (it unlocks by itself), or find the token in <code>~/.epokio/token</code> (Windows: <code>%USERPROFILE%\\.epokio\\token</code>).")}<br>${S.tokenCmd ? t("From a terminal on this machine: {cmd}. On a Mac: Settings, Machines.", { cmd: `<code>${esc(S.tokenCmd)}</code>` })
      : t("From a terminal on that machine, run Epokio with <code>agent --show-token</code>, for example <code>.\\Epokio.exe agent --show-token</code>, <code>py -m epokio agent --show-token</code> or <code>epokio agent --show-token</code>. On a Mac: Settings, Machines.")}</p>
    ${bad ? `<div class="msg" role="alert" style="--c:var(--red);max-width:460px;margin:12px auto 0"><b>${t("That token did not work.")}</b> ${t("It may have changed on this machine.")}</div>` : ""}
    <div class="inrow"><input class="in" id="tok" type="password" aria-label="${t("Paste the token")}" placeholder="${t("Paste the token")}" autocomplete="off" spellcheck="false"><button class="btn primary" id="unlock">${t("Unlock")}</button></div></div>`;
}
/// 토큰을 넣어 보고 맞으면 이 브라우저에 남긴다
async function unlockWith(tok) {
  S.token = tok; S.locked = false; S.pythons = null; S.schema = {};
  try { await api("jobs"); LS.epokioToken = tok; await login(); }
  catch (e) { if (e instanceof Locked) S.locked = true; }
  return !S.locked;
}
/// 토큰이 필요한 곳에서 그 자리에서 묻는다. ★'대기열 탭에서 잠금을 푸세요'라 하던 일을 두고 탭을 옮겨야 했다
function needToken(why) {
  if (S.token && !S.locked) return Promise.resolve(true);
  return new Promise((done) => {
    const d = document.createElement("dialog");
    d.className = "tokdlg"; d.setAttribute("aria-labelledby", "tokh");
    d.innerHTML = `<form method="dialog"><h3 id="tokh">🔒 ${why || t("This needs this machine's token")}</h3>
      <p class="hint">${t("On this machine, open this page from the Epokio tray icon or <code>epokio setup</code> (it unlocks by itself), or find the token in <code>~/.epokio/token</code> (Windows: <code>%USERPROFILE%\\.epokio\\token</code>).")}</p>
      <div class="inrow"><input class="in" type="password" aria-label="${t("Paste the token")}" placeholder="${t("Paste the token")}" autocomplete="off" spellcheck="false"><button class="btn primary" value="ok">${t("Unlock")}</button><button class="btn" value="no" formnovalidate>${t("Cancel")}</button></div>
      <div role="status" class="tokmsg"></div></form>`;
    document.body.append(d);
    const inp = d.querySelector("input");
    d.querySelector("form").onsubmit = async (e) => {
      if (e.submitter?.value === "no") return;                    // 닫는다
      e.preventDefault();
      const tok = inp.value.trim(); if (!tok) return;
      if (await unlockWith(tok)) { d.close(); refresh(); return; }
      d.querySelector(".tokmsg").innerHTML = `<div class="msg" style="--c:var(--red)"><b>${t("That token did not work.")}</b> ${t("It may have changed on this machine.")}</div>`;
      inp.select();
    };
    d.onclose = () => { d.remove(); done(!!S.token && !S.locked); };
    d.showModal(); inp.focus();
  });
}
function wireLock() {
  const go = async () => {
    const tok = $("#tok").value.trim(); if (!tok) return;             // t라고 쓰지 않는다(번역 함수 t()를 가린다)
    $("#unlock").disabled = true;
    await unlockWith(tok);
    refresh();
  };
  $("#unlock").onclick = go;
  $("#tok").onkeydown = (e) => { if (e.key === "Enter") go(); };
  $("#tok").focus();
}
const forgetHTML = `<button class="more" id="forget" title="${t("Remove the token from this browser")}">${t("Lock this page")}</button>`;
function wireForget() {
  const f = $("#forget"); if (!f) return;
  f.onclick = () => { delete LS.epokioToken; S.asked = false; S.token = ""; S.locked = false; S.jobs = null; S.pythons = null; S.schema = {}; setReadOnly(false); drawBusy(); refresh(); };
}

// ── 파이썬 자동 설치 ──
/// 학습용 파이썬이 없을 때. ~/.epokio/envs/epokio 에 따로 만든다(다른 파이썬은 안 건드린다). 맥 앱 PythonSetupCard와 같은 일
function setupJob() {
  const js = (S.jobs || []).filter((j) => j.kind === "setup");
  return js.find((j) => j.id === S.setupId) || js.find((j) => j.state === "running" || j.state === "queued");
}
function setupHTML(hasEnv) {
  const j = setupJob(), st = j?.state;
  const body = st === "running" || st === "queued"
    ? `<p class="hint" style="margin:8px 0 0">${t("Installing. This downloads 1 to 3 GB and takes 5 to 15 minutes. You can watch it in Queue.")}</p>`
    : `${st === "failed" || st === "cancelled" ? `<p style="margin:8px 0 0;color:var(--red)">${t("Setup did not finish. Open Queue to see the log.")}</p>` : ""}
       <div class="actions"><button class="btn primary" id="setup">${st ? t("Try again") : t("Set up automatically")}</button></div>`;
  return `<div class="msg" id="setupbox"><b>${hasEnv ? t("Or let Epokio set up a Python for training.") : t("Set up Python for training.")}</b>
    ${t("Epokio makes a separate Python environment just for training (<code>~/.epokio/envs/epokio</code>) and installs Ultralytics and PyTorch in it, with CUDA if this PC has an NVIDIA GPU. Your other Python setups are not touched. Delete that folder to remove it.")}${body}</div>`;
}
function wireSetup() {
  const b = $("#setup");
  if (b) b.onclick = async () => {
    b.disabled = true;
    try { S.setupId = (await api("jobs", "POST", { kind: "setup" })).id; await loadJobs(); }
    catch (e) {
      if (e instanceof Locked) S.locked = true;
      else {
        // ★버튼이 꺼진 채로 남아, 파이썬을 깔고 와도 탭을 옮기기 전엔 다시 누를 수 없었다. 메시지도 누를 때마다 쌓였다
        b.disabled = false;
        $("#setupbox .setuperr")?.remove();
        $("#setupbox").insertAdjacentHTML("beforeend", `<div class="setuperr" role="alert"><p style="color:var(--red)">${esc(e.message)}</p>`
          + (/python\.org/i.test(e.message) ? `<p class="hint"><b>python.org/downloads</b> · ${t("Tick \"Add python.exe to PATH\" while installing, then press the button again.")}</p>` : "") + `</div>`);
        return;
      }
    }
    drawBusy(); drawTrain();
  };
}
/// 설치가 끝나면 파이썬 목록을 다시 찾는다. 주기 갱신이 부른다(폼은 안 건드리고 설치 카드가 있을 때만)
function watchSetup() {
  const j = setupJob();
  if (!j || !$("#setupbox") || S.tab !== "train") return;
  if (j.state === "done") { S.setupId = null; S.pythons = null; S.schema = {}; S.python = ""; delete LS.epokioPython; drawTrain(); }
  else if (!$("#setup") !== (j.state === "running" || j.state === "queued")) drawTrain();   // 상태가 바뀌었을 때만 다시 그린다
}

// ── 학습 시작 ──
/// 칸은 그 파이썬에 깔린 ultralytics의 cfg/default.yaml에서 만든다(/schema). 손으로 만든 칸이 없다
const SECT = { general: t("General"), train: tc("section", "Training"), val: t("Validation"), all: t("Other"), other: t("Other") };
const LABELS = { model: t("Model"), epochs: t("Epochs (passes over the data)"), imgsz: t("Image size (px)"), batch: t("Batch size (-1 = automatic)"), device: t("Device (0 = first GPU, cpu)") };
const SAMPLE = "coco8.yaml";            // 8장짜리 공개 샘플. ultralytics가 알아서 받는다
// 작업 종류·모델 크기를 고르면 모델 파일 이름을 대신 만든다(맥 앱 TrainView와 같은 규칙)
const TASKS = [["detect", t("Detect"), ""], ["segment", t("Segment"), "-seg"], ["pose", t("Pose"), "-pose"], ["classify", t("Classify"), "-cls"]];
const SIZES = [["n", t("Nano")], ["s", t("Small")], ["m", t("Medium")], ["l", t("Large")], ["x", t("X-Large")]];
function modelName() { return "yolo11" + S.size + (TASKS.find((x) => x[0] === S.task) || TASKS[0])[2] + ".pt"; }
// "다시 학습"이 옮기지 않는 값: 결과 폴더(새 학습은 새 폴더에), 이어 하기, 모드
// device도 옮기지 않는다(★CUDA 기계의 학습을 다른 기계에서 다시 하면 "Invalid CUDA device"로 죽었다)
const AGAIN_SKIP = ["project", "name", "exist_ok", "resume", "save_dir", "mode", "device"];
const argText = (v) => v == null || v === "null" || v === "None" ? "" : String(v).replace(/^True$|^False$/, (b) => b.toLowerCase());
function segHTML(id, items, on) {
  return `<div class="seg" id="${id}" style="align-self:flex-start;flex-wrap:wrap">${items.map(([k, t]) => `<button type="button" class="${k === on ? "on" : ""}" aria-pressed="${k === on}" data-v="${k}">${t}</button>`).join("")}</div>`;
}
/// 자주 쓰는 설정은 우리 말로 설명한다(번역된다). ★Ultralytics 설명 원문('# (int) number of epochs...')이 한국어 화면에도 그대로 나왔다
const HELP = {
  model: "The starting model file. A .pt file continues from trained weights; a .yaml file starts from scratch.",
  epochs: "How many times to go over all the training images.",
  time: "Stop after this many hours, even if epochs remain. Overrides epochs.",
  patience: "Stop early if the score has not improved for this many epochs.",
  batch: "Images per step. -1 picks the largest that fits in GPU memory.",
  imgsz: "Images are resized to this many pixels on the long side. Bigger finds small objects but is slower.",
  save_period: "Also save a checkpoint every this many epochs. -1 saves only the best and last.",
  cache: "Keep images in memory (ram) or on disk to load them faster.",
  device: "Which GPU to use: 0 is the first, 0,1 uses two, cpu uses no GPU.",
  workers: "Processes that load images. Lower it if the machine runs out of memory.",
  project: "Folder that holds the run folders.",
  name: "Name of this run's folder.",
  exist_ok: "Write into the run folder even if it already exists.",
  pretrained: "Start from weights trained on a large dataset. Usually better than starting from nothing.",
  optimizer: "How the weights are updated. auto picks one for you.",
  seed: "Random seed. The same seed gives more repeatable results.",
  deterministic: "Make results repeatable, at some cost in speed.",
  single_cls: "Treat every class as one class.",
  rect: "Keep each batch's image shape instead of squares. Less padding, less augmentation.",
  cos_lr: "Lower the learning rate along a cosine curve.",
  close_mosaic: "Turn off mosaic augmentation for the last this many epochs.",
  resume: "Continue from the last checkpoint of this run.",
  amp: "Mixed precision. Faster and uses less GPU memory.",
  fraction: "Train on only this share of the images (1.0 = all).",
  freeze: "Keep the first this many layers fixed.",
  val: "Check the score on the validation images during training.",
  plots: "Save charts and example images in the run folder.",
  dropout: "Randomly drop connections to fight overfitting (classify only).",
  lr0: "Starting learning rate.",
  lrf: "Final learning rate as a share of the starting one.",
  momentum: "How much each update keeps from the previous one.",
  weight_decay: "Keeps weights small to fight overfitting.",
  warmup_epochs: "Epochs spent slowly raising the learning rate at the start.",
  hsv_h: "Random change of hue.",
  hsv_s: "Random change of saturation.",
  hsv_v: "Random change of brightness.",
  degrees: "Random rotation, in degrees.",
  translate: "Random shift, as a share of the image size.",
  scale: "Random zoom in or out.",
  fliplr: "Chance of flipping an image left to right.",
  flipud: "Chance of flipping an image upside down.",
  mosaic: "Chance of stitching four images into one.",
  mixup: "Chance of blending two images together.",
  verbose: "Print more in the log.",
};
function fieldHTML(f, i) {
  const id = "f_" + esc(f.key), own = HELP[f.key], help = esc(own ? t(own) : (f.help || "").replace(/^\([^)]*\)\s*/, ""));   // '(int) ' 같은 형식 표시는 뺀다
  const hlang = !own && LANG !== "en" ? ' lang="en"' : "";              // 원문 그대로면 영어라고 표시한다
  let v = f.default;
  if (f.key === "model" && v == null) v = modelName();               // 위에서 고른 작업·크기로
  if (f.type === "bool") return `<label class="field bool" style="animation-delay:${Math.min(i, 12) * 15}ms" title="${help}">
    <input type="checkbox" class="check" id="${id}" data-k="${esc(f.key)}" data-t="bool" ${v ? "checked" : ""}><span>${esc(f.key)}</span></label>`;
  const num = f.type === "int" || f.type === "float";
  const input = `<input class="in" id="${id}" ${f.key === "data" ? 'aria-labelledby="l_data"' : ""} data-k="${esc(f.key)}" data-t="${esc(f.type)}" ${num ? `type="number" step="${f.type === "int" ? 1 : "any"}"` : `type="text" spellcheck="false"`}
    value="${v == null ? "" : esc(v)}" placeholder="${v == null ? t("not set") : ""}">`;
  if (f.key === "data") return `<div class="field wide" style="animation-delay:${Math.min(i, 12) * 15}ms"><span id="l_data">${t("Data")}</span>
    <div class="inrow">${input}<button class="btn" id="chk" type="button">${t("Check data")}</button><button class="btn" id="sample" type="button" title="${t("8 public images, downloaded by Ultralytics")}">${t("Tiny sample")}</button></div>
    <small>${t("Path to a data.yaml on {machine}.", { machine: esc(S.label || t("this machine")) })}</small><div id="health" role="status"></div></div>`;
  // 기본 칸은 사람 말로(★imgsz·batch·device만 보여 처음 쓰는 사람이 몰랐다). ultralytics 이름은 작게 남긴다
  const nice = LABELS[f.key];
  return `<label class="field" style="animation-delay:${Math.min(i, 12) * 15}ms" title="${help}"><span>${nice ? esc(nice) + ` <code style="font-weight:400;color:var(--soft)">${esc(f.key)}</code>` : esc(f.key)}</span>${input}<small${hlang}>${help}</small></label>`;
}
async function drawTrain() {
  $("#main").classList.remove("static"); S.lastMain = "";               // 학습 폼은 setMain을 거치지 않는다(주기 갱신이 안 그린다)
  if (!S.token || S.locked) { $("#main").innerHTML = lockedHTML(t("Starting a run needs this machine's token")); wireLock(); return; }
  // 보기 전용 토큰: 폼을 채워 봐야 시작에서 403이다. ★폼이 그대로 나와 다 채운 뒤에야 영어 오류를 봤다
  if (S.readOnly) {
    $("#main").innerHTML = `<div class="card locked"><div class="ico">👀</div><h2>${t("This token can only view")}</h2>
      <p class="hint">${t("Starting runs needs a token that can run. Ask whoever gave you this token, or use the token of the training machine itself.")}</p>${forgetHTML}</div>`;
    return wireForget();
  }
  if (!S.pythons) {
    $("#main").innerHTML = `<div class="card pane"><h2>${t("Train")}</h2><p class="hint">${t("Looking for Python environments on {machine}. The first time can take a few seconds.", { machine: esc(S.label || t("this machine")) })}</p></div>`;
    try { S.pythons = (await api("pythons")).envs; }
    catch (e) { if (e instanceof Locked) { S.locked = true; return drawTrain(); } S.pythons = []; }
    if (S.tab !== "train") return;                                 // 찾는 동안 다른 탭으로 갔다
  }
  const envs = S.pythons;
  if (!envs.length) {
    $("#main").innerHTML = `<div class="card pane"><h2>${t("Train")}</h2>${setupHTML(false)}${forgetHTML}</div>`;
    wireSetup(); return wireForget();
  }
  if (!envs.some((e) => e.path === S.python)) S.python = (envs.find((e) => e.ready) || envs[0]).path;
  const env = envs.find((e) => e.path === S.python), again = S.again;
  let sc = S.schema[S.python];
  if (!sc && env.ready) {
    try { sc = S.schema[S.python] = await api("schema?python=" + encodeURIComponent(S.python) + "&mode=train"); }
    catch (e) { if (e instanceof Locked) { S.locked = true; return drawTrain(); } sc = { ok: false, reason: e.message }; }
    if (S.tab !== "train") return;
  }
  const accel = (e) => e.cuda ? " · CUDA" : e.mps ? " · Apple GPU" : "";
  const opts = envs.map((e) => `<option value="${esc(e.path)}" ${e.path === S.python ? "selected" : ""}>${esc(e.name)} · Python ${esc(e.python || "?")}${
    e.ready ? " · Ultralytics " + esc(e.ultralytics) + accel(e) : " · " + t("needs {pkg}", { pkg: e.ultralytics ? "torch" : "ultralytics" })}</option>`).join("");
  const machine = esc(S.label || t("this machine"));
  let h = `<div class="card pane"><h2>${t("Train")}</h2><p class="hint">${t("Runs one at a time on {machine}. If something is already training, this waits in the queue.", { machine })}</p>
    <div class="fields"><label class="field wide"><span>${t("Python")}</span><select class="in" id="py">${opts}</select><small>${esc(env.path)}</small></label>
    <label class="field wide"><span>${t("Name")}</span><input class="in" id="jobname" spellcheck="false" placeholder="${t("Taken from the data folder if empty")}"><small>${t("Shown in the queue.")}</small></label></div>
    <label class="hint" style="display:flex;align-items:center;gap:8px;margin:8px 0" title="${esc(t("Predicts 4 validation images on the CPU every 5 epochs, so you can watch the model learn. Costs a second or two each time."))}">
      <input type="checkbox" id="snapshots"> ${t("Save predictions every 5 epochs")}</label>`;
  if (!env.ready) {
    h += `<div class="msg" style="--c:var(--orange)"><b>${t("This environment cannot train yet.")}</b> ${t("It needs {pkg}.", { pkg: env.ultralytics ? "PyTorch" : "Ultralytics" })}
      ${t("Pick another one, run {cmd}, or let Epokio set one up.", { cmd: `<code>${esc(env.path)} -m pip install ultralytics</code>` })}</div>`;
    if (!envs.some((e) => e.ready)) h += setupHTML(true);
  } else if (!sc?.ok) {
    h += `<div class="msg" style="--c:var(--red)"><b>${t("Could not read the settings.")}</b> ${esc(sc?.reason || "")}</div>`;
  } else {
    if (again) {                                  // "다시 학습": 그 학습의 작업·크기를 고르고, 기본값과 다른 설정이 있으면 전부 펼친다
      const m = String(again.args.model || "").match(/([nsmlx])(-seg|-pose|-cls)?\.pt$/i);
      if (m) { S.size = m[1].toLowerCase(); S.task = (TASKS.find((x) => x[2] === (m[2] || "").toLowerCase()) || TASKS[0])[0]; }
      if (sc.fields.some((f) => !f.basic && !AGAIN_SKIP.includes(f.key) && f.key in again.args && argText(again.args[f.key]) !== argText(f.default))) S.all = true;
    }
    const basic = sc.fields.filter((f) => f.basic), rest = sc.fields.filter((f) => !f.basic);
    const order = ["data", "model", "epochs", "imgsz", "batch", "device"];
    basic.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    h += `<div class="fields"><div class="field wide"><span>${t("What should the model learn?")}</span>${segHTML("task", TASKS, S.task)}</div>
      <div class="field wide"><span>${t("Model size")}</span>${segHTML("size", SIZES, S.size)}<small>${t("Bigger is more accurate but slower. Nano is enough to try things out.")}</small></div></div>`;
    h += `<div class="fields">${basic.map(fieldHTML).join("")}</div>`;
    h += `<button class="more" id="all">${S.all ? t("Hide the other settings") : t("Show all {n} settings", { n: rest.length })}</button>`;
    if (S.all) {
      const groups = {};
      for (const f of rest) (groups[SECT[f.section] || t("Other")] ||= []).push(f);
      for (const [g, fs] of Object.entries(groups)) h += `<div class="sect">${g}</div><div class="fields">${fs.map(fieldHTML).join("")}</div>`;
    }
    h += `<div id="trainmsg" role="status"></div><div class="actions"><button class="btn primary" id="go">${t("Start training")}</button>
      <span class="hint" style="margin:0">${t("Ultralytics {version} runs it. Only the values you changed are sent.", { version: esc(sc.ultralytics || "") })}</span></div>`;
  }
  $("#main").innerHTML = h + forgetHTML + `</div>`;
  wireForget();
  $("#py").onchange = () => { S.python = $("#py").value; LS.epokioPython = S.python; drawTrain(); };
  wireSetup();
  if (!sc?.ok || !env.ready) return;
  const pick = (id, key, store) => document.querySelectorAll("#" + id + " button").forEach((b) => b.onclick = () => {
    S[key] = b.dataset.v; LS[store] = S[key];
    document.querySelectorAll("#" + id + " button").forEach((x) => x.classList.toggle("on", x === b));
    $("#f_model").value = modelName();
  });
  pick("task", "task", "epokioTask"); pick("size", "size", "epokioSize");
  if (again) {
    S.again = null;
    document.querySelectorAll("[data-k]").forEach((el) => {
      const k = el.dataset.k; if (AGAIN_SKIP.includes(k) || !(k in again.args)) return;
      if (el.type === "checkbox") el.checked = argText(again.args[k]) === "true"; else el.value = argText(again.args[k]);
    });
    $("#trainmsg").innerHTML = `<div class="msg"><b>${t("Filled in from {name}.", { name: esc(again.name) })}</b> ${t("Change anything, then start. It trains as a new run and leaves the old one as it is.")}</div>`;
  }
  $("#all").onclick = () => { const keep = values(); S.all = !S.all; drawTrain().then(() => restore(keep)); };
  $("#chk").onclick = checkData;
  // 샘플은 8장이라 기본 100에폭이면 오래 걸리기만 한다. 맥 앱처럼 탐지·Nano·10에폭으로 맞춘다
  $("#sample").onclick = () => {
    $("#f_data").value = SAMPLE; $("#health").innerHTML = "";
    $('#task [data-v="detect"]').click(); $('#size [data-v="n"]').click(); $("#f_epochs").value = 10;
  };
  $("#go").onclick = () => startTraining(sc);
}
/// 폼의 현재 값 (펼치기·접기로 다시 그려도 입력이 남게)
function values() {
  const out = {};
  document.querySelectorAll("[data-k]").forEach((el) => out[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value);
  out.__name = $("#jobname")?.value || "";
  return out;
}
function restore(v) {
  document.querySelectorAll("[data-k]").forEach((el) => { if (!(el.dataset.k in v)) return; if (el.type === "checkbox") el.checked = v[el.dataset.k]; else el.value = v[el.dataset.k]; });
  if ($("#jobname")) $("#jobname").value = v.__name || "";
}
async function checkData() {
  const p = cleanPath($("#f_data").value), box = $("#health");
  $("#f_data").value = p;
  if (!p) { box.innerHTML = `<div class="msg" style="--c:var(--orange)">${t("Type the path to a data.yaml first.")}</div>`; return; }
  if (p === SAMPLE) { box.innerHTML = `<div class="msg" style="--c:var(--green)"><b>${t("Sample data.")}</b> ${t("Ultralytics downloads it on the first run.")}</div>`; return; }
  $("#chk").disabled = true; box.innerHTML = `<p class="hint" style="margin-top:8px">${t("Checking…")}</p>`;
  let r;
  try { r = await api("health-check?data=" + encodeURIComponent(p)); }
  catch (e) { r = { ok: false, error: e instanceof Locked ? t("The token stopped working.") : e.message }; }
  $("#chk").disabled = false;
  if (!r.ok) { box.innerHTML = `<div class="msg" style="--c:var(--red)"><b>${esc(r.error || t("Could not read it."))}</b></div>`; return; }
  if (r.data && r.data !== p) $("#f_data").value = r.data;              // 폴더를 적었으면 찾은 data.yaml로 바꿔 둔다
  const [title, c] = { good: [t("Looks good."), "var(--green)"], check: [t("Worth a look."), "var(--orange)"], problems: [t("Has problems."), "var(--red)"] }[r.score] || [t("Checked."), "var(--accent)"];
  // 분할 이름(train·val·test)은 agent가 준 키 그대로. 알려진 것만 화면 말로 바꾼다
  const SPLIT = { train: t("train"), val: t("val"), test: t("test") };
  const counts = Object.entries(r.splits).filter(([k, s]) => s.images || k !== "test")   // 없는 test 분할은 잡음
    .map(([k, s]) => t("{n} {split}", { n: s.images, split: SPLIT[k] || esc(k) })).join(" · ");
  const lines = [...r.warnings.map((w) => (w.level === "error" ? "✕ " : "! ") + w.text), ...r.tips.map((x) => "💡 " + x)];
  box.innerHTML = `<div class="msg" style="--c:${c}"><b>${title}</b> ${t("{counts} images", { counts })} · ${r.classes.length === 1 ? t("1 class") : t("{n} classes", { n: r.classes.length })}
    ${lines.length ? `<ul>${lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}</div>`;
}
async function startTraining(sc, anyway) {
  const box = $("#trainmsg"), fields = Object.fromEntries(sc.fields.map((f) => [f.key, f]));
  const params = {};
  document.querySelectorAll("[data-k]").forEach((el) => {
    const f = fields[el.dataset.k]; if (!f) return;
    let v;
    if (el.type === "checkbox") v = el.checked;
    else if (el.value.trim() === "") return;                          // 비워 둔 칸은 ultralytics 기본값
    else if (f.type === "int") v = parseInt(el.value, 10);
    else if (f.type === "float") v = parseFloat(el.value);
    else v = f.key === "data" || f.key === "model" ? cleanPath(el.value) : el.value.trim();
    if (typeof v === "number" && Number.isNaN(v)) return;
    const always = ["data", "model", "epochs"].includes(f.key);
    if (always || v !== f.default) params[f.key] = v;                  // 바꾼 값만 (맥 앱의 overrides와 같다)
  });
  if (!params.data) { box.innerHTML = `<div class="msg" style="--c:var(--orange)"><b>${t("Choose the data first.")}</b> ${t("Type a data.yaml path, or use the tiny sample.")}</div>`; $("#f_data").focus(); return; }
  const folder = params.data === SAMPLE ? "sample" : params.data.split(/[\\/]/).slice(-2, -1)[0] || "train";
  const name = $("#jobname").value.trim() || folder;
  $("#go").disabled = true;
  // 출발 전 점검: 데이터에 진짜 오류가 있으면 대기열에 넣기 전에 막는다(몇 분 뒤 실패하는 것보다 낫다)
  if (!anyway && /[\\/]/.test(params.data)) {                          // coco128.yaml 같은 내장 이름은 ultralytics가 받는다. 경로만 본다
    box.innerHTML = `<p class="hint">${t("Checking the data first…")}</p>`;
    let r = null;
    try { r = await api("health-check?data=" + encodeURIComponent(params.data)); } catch { }
    const errs = !r ? [] : !r.ok ? [r.error || t("The data.yaml could not be read.")] : r.warnings.filter((w) => w.level === "error").map((w) => w.text);
    if (errs.length) {
      box.innerHTML = `<div class="msg" style="--c:var(--red)"><b>${errs.length === 1 ? t("Not started. The data has a problem.") : t("Not started. The data has {n} problems.", { n: errs.length })}</b>
        <ul>${errs.map((x) => `<li>✕ ${esc(x)}</li>`).join("")}</ul>
        <div class="actions"><button class="btn small" id="anyway">${t("Start anyway")}</button></div></div>`;
      $("#anyway").onclick = () => startTraining(sc, true);
      $("#go").disabled = false;
      return;
    }
    if (r?.data) params.data = r.data;                                  // 폴더를 적었으면 그 안에서 찾은 data.yaml로
  }
  try {
    if ($("#snapshots")?.checked) params.epokio_snapshots = 5;         // 학습 틀이 빼서 쓴다(에폭별 예측 사진)
    await api("jobs", "POST", { kind: "train", name, python: S.python, params });
    box.innerHTML = `<div class="msg" style="--c:var(--green)"><b>${t("Added to the queue.")}</b> ${esc(name)}</div>`;
    setTimeout(() => { if (S.tab === "train") tab("queue"); }, 700);
  } catch (e) {
    box.innerHTML = `<div class="msg" style="--c:var(--red)"><b>${t("Not started.")}</b> ${esc(e instanceof Locked ? t("The token stopped working. Unlock again.") : e.message)}</div>`;
    if (e instanceof Locked) { S.locked = true; setTimeout(drawTrain, 1200); }
  }
  if ($("#go")) $("#go").disabled = false;
}
