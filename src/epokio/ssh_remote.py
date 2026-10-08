"""SSH 가벼운 모드의 서버 쪽 스크립트(ssh_source.py가 표준 입력으로 넘긴다). 400줄 상한 때문에 따로 둔다.

★표준 라이브러리만, python3.6에서도 돌게(f-string 없이).
파일 한 개의 응답 모양:
  [시각, None]                     안 바뀜
  [시각, 글자] / [시각, b64, "b64"]  통째
  [시각, 글자, "append", 위치] / [시각, b64, "append_b64", 위치]   위치(이 Mac이 가진 크기)부터 뒤만
  [시각, None, "too_large", 크기]   한도(글자 4MB, 바이너리 20MB)를 넘어 건너뜀. 이어 받기면 한도는 붙은 조각에만
  [시각, 글자, "tail", 시작, 첫 줄 길이, 크기]   처음 보는 늘어나는 글자 기록이 한도를 넘음: 첫 줄(CSV 머리) + 끝 한도만큼
      (줄 경계부터). 시작 = 서버 파일에서 끝 조각이 시작하는 위치. 바이너리(tfevents·wandb)는 레코드를 안전하게
      다시 맞출 수 없어 too_large 그대로
  HAVE의 처음 4KB 지문이 None이면 끝 조각만 가진 쪽이다: 마지막 k바이트(HAVE 다섯째 값) 지문만 맞춰 본다
"""

REMOTE = r'''
import base64, hashlib, json, os, sys, time
cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
try: HAVE = json.loads(HAVE_JSON)       # 지난번에 받은 {폴더: {파일: [수정 시각, 크기, 처음 4KB 지문, 마지막 4KB 지문]}}. 그대로면 내용을 다시 보내지 않는다
except NameError: HAVE = {}
HOME = os.path.expanduser("~")
FILES = ["results.csv", "args.yaml", "trainer_state.json", "metrics.csv", "hparams.yaml", "epokio_log.csv",
         "training.log", "history.csv", "training.csv", "keras_log.csv", "summary.csv", "log.txt",
         "vis_data/scalars.json", "vis_data/config.py", "args.json", "config.yaml", "config.json", "opt.yaml"]
APPEND = set(["log.txt", "training.log"])     # 늘기만 하는 파일(이름으로). 그 밖에 *.csv·.wandb·tfevents
MARK = set(["results.csv", "trainer_state.json", "metrics.csv", "epokio_log.csv", "history.csv", "training.log", "training.csv",
            "keras_log.csv", "summary.csv"])
def jsonlog(d):
    # MAE·DeiT·DINO의 log.txt(에폭마다 JSON 한 줄). 흔한 이름이라 첫 줄이 epoch 있는 JSON일 때만 학습으로 본다
    try:
        with open(os.path.join(d, "log.txt"), "rb") as f: head = f.readline(20000).decode("utf-8", "replace").strip()
        return head.startswith("{") and "epoch" in json.loads(head)
    except (OSError, ValueError): return False
def digest(f, start, end):
    f.seek(start)
    return hashlib.md5(f.read(end - start)).hexdigest()[:16]
def grab(p, n, st, h, limit, binary):
    # 늘기만 하는 파일: 이 Mac이 가진 앞부분(크기·처음 4KB·마지막 4KB 지문)이 그대로면 뒤에 붙은 것만 보낸다
    with open(p, "rb") as f:
        if len(h) >= 4 and appendable(n) and 0 < h[1] <= st.st_size and \
                (h[2] is None or digest(f, 0, min(4096, h[1])) == h[2]) and digest(f, max(0, h[1] - (h[4] if len(h) > 4 else 4096)), h[1]) == h[3]:
            if st.st_size - h[1] > limit: return [st.st_mtime, None, "too_large", st.st_size - h[1]]
            f.seek(h[1])
            data = f.read(st.st_size - h[1])
            if not binary:
                try: return [st.st_mtime, data.decode("utf-8"), "append", h[1]]
                except UnicodeDecodeError: pass        # 글자 중간에서 잘렸다: 바이트 그대로
            return [st.st_mtime, base64.b64encode(data).decode("ascii"), "append_b64", h[1]]
        if st.st_size > limit and appendable(n) and not binary:     # 늘어나는 글자 기록: 끝부분만 받아 이어 간다
            f.seek(0)
            first = f.readline(65536)
            f.seek(st.st_size - limit)
            f.readline()                                     # 잘린 첫 줄은 버린다
            start = f.tell()
            if first.endswith(b"\n") and len(first) < start < st.st_size:
                try: return [st.st_mtime, (first + f.read(st.st_size - start)).decode("utf-8"), "tail", start, len(first), st.st_size]
                except UnicodeDecodeError: pass              # 바이트가 바뀌면 이어 받기 위치가 어긋난다
        if st.st_size > limit: return [st.st_mtime, None, "too_large", st.st_size]   # 말없이 건너뛰지 않고 알린다
        f.seek(0)
        data = f.read()
    return [st.st_mtime, base64.b64encode(data).decode("ascii"), "b64"] if binary else [st.st_mtime, data.decode("utf-8", "replace")]
def appendable(n):
    b = n.rsplit("/", 1)[-1]
    return b.endswith(".csv") or b.endswith(".wandb") or b.startswith("events.out.tfevents.") or b in APPEND
SKIP = set(["images", "labels", "weights", "dataset", "datasets", ".git", ".venv", "venv", "node_modules", "__pycache__",
            ".cache", "anaconda3", "miniconda3", ".conda", "site-packages", "Library", "snap"])
roots = [os.path.expanduser(p) for p in cfg.get("paths", [])]
if cfg.get("auto", True):
    roots += [HOME]
out, seen, budget, cut = [], set(), [4000], [False]
def walk(d, depth):
    if depth < 0 or budget[0] <= 0 or len(out) >= 300:
        if budget[0] <= 0 or len(out) >= 300: cut[0] = True     # 다 못 봤다는 표시(앱이 경고하고, 지우기를 건너뛴다)
        return
    budget[0] -= 1
    try: names = os.listdir(d)
    except OSError: return
    ns = set(names)
    ck = sorted([n for n in names if n.startswith("checkpoint-")], key=lambda n: int("".join(c for c in n if c.isdigit()) or 0))
    wb = [n for n in names if n.startswith("run-") and n.endswith(".wandb")]   # W&B 기록(바이너리)
    wb += [n for n in names if n.startswith("events.out.tfevents.")]          # TensorBoard 기록(바이너리)
    for sub in ("train", "validation"):                                          # Keras식 하위 폴더
        if sub in ns and os.path.isdir(os.path.join(d, sub)):
            try: wb += [sub + "/" + n for n in os.listdir(os.path.join(d, sub)) if n.startswith("events.out.tfevents.")]
            except OSError: pass
    if ns & MARK or wb or ("log.txt" in ns and jsonlog(d)) or os.path.isfile(os.path.join(d, "vis_data", "scalars.json")) or (ck and os.path.exists(os.path.join(d, ck[-1], "trainer_state.json"))):
        rp = os.path.realpath(d)
        if rp in seen: return
        seen.add(rp)
        files = {}
        for n in FILES + ([ck[-1] + "/trainer_state.json"] if ck else []) + wb:
            p = os.path.join(d, n)
            try:
                st = os.stat(p)
                limit = 20000000 if n in wb else 4000000
                h = HAVE.get(d, {}).get(n)
                h = h if isinstance(h, list) else [h]       # 예전 모양(시각 하나)도 받는다
                if h[0] == st.st_mtime:
                    files[n] = [st.st_mtime, None]      # 안 바뀌었다: 내용은 빼고 시각만
                    continue
                files[n] = grab(p, n, st, h, limit, n in wb)
            except OSError: pass
        out.append({"path": d, "files": files})
        return
    for n in names:
        if n in SKIP or n.startswith("."): continue
        p = os.path.join(d, n)
        if os.path.isdir(p) and not os.path.islink(p): walk(p, depth - 1)
for r in roots:
    walk(r, 5 if r == HOME else 6)
print(json.dumps({"now": time.time(), "runs": out, "truncated": cut[0], "python": sys.version.split()[0], "home": HOME}))
'''

