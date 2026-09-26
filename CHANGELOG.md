# Changelog

## 0.4.0 (2026-09-26)

**Mac app**
- A menu bar character that runs at the speed of your training. When nothing is training it can follow CPU, GPU or AI tool use instead (Settings, Appearance). Pick from a gallery of characters and icons.
- A one-paragraph explanation after each run (what the score means, where it peaked, what to try next).
- Labeling: draw and edit boxes, zoom and pan, saves as you go, a searchable class palette for more than ten classes, and a clear mark for boxes a model made versus boxes you checked.
- Practice mode that fakes a training run, and a short tour for your first real one. It never starts real training by itself.
- Almost everything has a keyboard shortcut, with a command palette.
- The run page shows the recorded environment (Python, PyTorch, Ultralytics, CUDA, git commit).
- Python is bundled inside the app, so a Mac without Python can run the helper.
- Optional awards for milestones (off by default).
- Watch runs on a server over SSH with nothing installed there (view only).

**Scores**
- Lower-is-better scores (loss, RMSE) are shown, sorted and marked "best" correctly in the Mac app and on the web page. A group that mixes different scores no longer shows one "best".
- Hugging Face runs evaluated mid-epoch no longer count as finished (19.33 of 20 is 19, not 20). A failed or stopped run is not drawn as complete.

**Agent**
- More than one NVIDIA GPU: each GPU runs its own queue, and a job can ask for any GPU, a specific one, or the CPU. Machines without `nvidia-smi` keep the single queue. Not yet tested on a real multi-GPU machine.
- Named tokens with read-only or run permission: `epokio-agent --add-token NAME --scope read`, `--list-tokens`, `--revoke-token`. Tokens are stored hashed and shown once.
- Viewing the queue, models, SSH machines and sweeps now needs a token too. The run list and images stay open on this machine.
- Protection against DNS rebinding (unknown `Host` names are refused) and a signed `/health` reply so the app only trusts its own helper.
- Rescanning adapts: quick while training, slower when idle, slower on battery, or only when asked.
- "Train again" no longer fails when the original run named a GPU this machine or queue slot does not have.
- AI tools can report their activity (`POST /ai/report`, MCP `report_ai_activity`) for the menu bar character.

**Known limits**
- The Mac app is still not notarized. Automatic updates are built in but stay off until a release is signed with an update key.

## 0.3.0 (2026-09-26)

**Web page (Windows, Linux, phone)**
- Train and Queue tabs: start runs, reorder, stop after asking, logs, time left and finish time.
- One-button Python setup for training, with CUDA PyTorch on a PC with an NVIDIA GPU.
- Pre-start data check that stops a broken dataset, and plain-language failure causes with fixes.
- Compare shows only the settings that differ, warns when runs used different data, filters, and exports CSV.
- Phone alerts (ntfy, Slack, Discord, Telegram) can be turned on from the web page.
- Korean, with a language button. Agent messages follow the page language.
- Opening the page from the tray or `epokio setup` unlocks Train and Queue by itself.
- Works at phone width, keeps scroll and focus across refreshes, clearer contrast, keyboard use.
- **Resume** a stopped Ultralytics run from `weights/last.pt` (same folder, same Python; refused while the run may still be training).
- **Main score** per run: pick the logged value that counts as the score, whether lower is better, and a target for alerts.
- Long run lists draw 200 rows at first and fetch a lighter list.
- Settings table in Compare: every shown run's differing settings next to its score (sortable, in the CSV and as the `sweep_table` MCP tool). Sort the run list by score, add tags and export a report from the web.
- Filter the run list by name or #tag, and add another folder to watch at any time with **+ Folder**.
- Anything that needs the token asks for it right there instead of sending you to the Queue tab.
- The common training settings are explained in plain words (and in Korean) instead of Ultralytics' comments.
- Cancelling a waiting job asks first. The header counts running and waiting queue jobs.
- A lost connection is shown in red with the time of the last update; old numbers are cleared and buttons are disabled until it is back.

**Agent**
- `epokio doctor` for bug reports, `~/.epokio/agent.log` with error details, `epokio agent --stop`, and `setup`/the tray restart a helper left running from an older version. `/health` reports the version.
- TensorBoard event files (`events.out.tfevents.*`) are read without TensorFlow, so Lightning's default logger and Hugging Face runs without `trainer_state.json` show up.
- Hugging Face runs are no longer marked done at their first evaluation; loss-like and learning-rate values are not taken as the score; "stalled" waits for about one epoch's time.
- Security: network paths (`\\server\share`, `\??\UNC\...`) are refused before touching the network, requests from unknown host names need the token (set `EPOKIO_ALLOWED_HOSTS` for extra names), every new route is locked by default.
- The queue survives a failing job, cp949 file names, agent restarts (it waits for a training that is still running) and reused process IDs.
- Only one helper per machine runs the queue, so a second helper (another port, an older version) cannot run the same job twice. A broken `jobs.json` is kept aside instead of being overwritten, and only the latest 500 finished jobs are kept.
- A job that finished while Epokio was off is marked done, with a note in its log, instead of failed.
- Much lighter with many runs: about 500 MB less memory at 2,000 runs, `/runs` reuses the last scan and is gzip-compressed.
- Data check: truncated label rows, classes only in validation, `names: {0: a}` and `train: [a, b]` forms, validation images copied from training.
- Notes no longer say "overfitting" and "train longer" about the same run, and confidence advice matches how the scores were measured.
- Segmentation evaluation reads polygons correctly and matches predictions by confidence.

**Reproducibility and custom code**
- Every training started from the queue records its environment (`epokio_env.json`: Python, PyTorch, Ultralytics, CUDA, GPU, git commit, a hash of installed packages). Web run pages show it and Compare lists what differs (the Mac app does not show it yet).
- `with epokio.start("runs/exp", epochs=50, lr=1e-4) as run:` then `run.log(val_loss=..., mAP50=...)` makes a hand-written training loop show up like any other run. It never stops training (busy files are retried), accepts tensors, and only rank 0 writes in multi-GPU runs.
- `python -m epokio setup` works when the `epokio` command is not on PATH; `--autostart` says so when the tray package is missing.

**Terminal and setup**
- Linux servers without a desktop: `--autostart` writes a systemd user service, the helper survives SSH logout, folder discovery repeats every 5 minutes.
- `epokio setup --label lab-07` names a machine. Over SSH it prints a tunnel command instead of opening a browser.
- `epokio watch --once` no longer crashes when its output is piped; the list scrolls and keeps the selection.
- `epokio --version`.

**Mac app**
- Queue, Python list, settings and the data check work again (GET requests now carry the token).
- Stopping a running job from the queue asks first. Notification switches take effect. Saving webhooks no longer wipes them.
- Remote training sends the Windows data path as typed.
- A machine that cannot be reached says why (wrong token, host name not allowed, older version, not running) in Settings, Machines and in the menu bar popover, instead of just "offline".

## 0.2.0

Mac app release with the Studio window, queue, auto-labeling, review and remote machines.
