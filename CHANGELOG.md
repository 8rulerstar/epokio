# Changelog

## 0.7.0 (2026-10-08)

- **Security: a run's page no longer shows secret-looking settings** (`api_key`, tokens, passwords) from `args.yaml`, the environment record or a queued job's settings to anyone who can view the helper. The settings table already hid them.
- **A run with no planned epochs that goes quiet** (for example a Keras `CSVLogger` run that finished normally) gets a calm *Training stopped logging* notice instead of the urgent *may have stopped* alert, and it is not sent to phone webhooks unless you choose it.
- **A score that never moved** (mAP 0 every epoch, usually broken labels) is explained as such, with a pointer to the labels and `data.yaml`, instead of "the best came very early, lower lr0".
- **A wrong `--root` is reported.** `epokio agent` and `epokio watch` warn about each folder that does not exist and drop the stray trailing `"` PowerShell adds, and the web page's empty list names the missing folders.
- **Commands printed by setup, doctor and error messages** use the virtual environment's Python when Epokio is installed in one (`py -m epokio` failed there). The web page's token help shows the command that works on this machine.
- **`epokio agent --stop`** says why when the helper refuses (a different token or home folder) and prints *Stopped.* only when it really stopped.
- **Scores:** Keras and CSV error metrics (`val_mae`, `mse`, `rmse`, `mape` and similar) count as lower-is-better scores instead of losses; Hugging Face's `best_metric` is the best score when nothing else is logged, in the direction `greater_is_better` gives; TensorBoard runs with two evaluations per epoch keep the better one.
- **Windows: run folders with paths over 260 characters** are named on the web page instead of silently missing.
- Web page: `/favicon.ico` and similar paths answer 404 instead of 401, the SSH panel is asked for only with a token (no 401 every 4 seconds), and the lineage and stage panel is translated to Korean. `epokio watch --once` into a pipe or file uses ASCII marks and bars.
- Docs: when no code changes are needed (Keras callbacks, `epokio.start`), when a best score is shown, what sets the planned epochs for Keras and Lightning, that alerts need a running helper, which runs have per-class scores, what webhooks and `/ai` carry, and comparison table updates (dated prices, self-hosted options, one-setting MLflow and Trackio integrations).
- **Alerts for SSH-mirrored and demo runs.** The helper's watch loop now follows the same folders as the run list, so runs mirrored over SSH (`~/.epokio/ssh`) and demo runs send their finished, failed and stalled alerts and webhooks. File watching is re-armed when the folder list changes, and the run list reuses the watch loop's scan again when SSH hosts are set.
- **A loose epoch/loss CSV no longer hides the runs below it.** A folder whose only log is a custom CSV (for example `runs/loss_summary.csv`) counts as a run only when no run folders are found beneath it; otherwise the runs below are listed.
- **Security: webhook addresses are no longer written to logs.** A failed webhook logs only the scheme and host (the path held ntfy topics and Telegram bot tokens, which reached `agent.log` and `epokio doctor`), and `epokio alerts --list` shows the host with a masked path.
- **Hugging Face:** runs that evaluate only `eval_loss` use it as a lower-is-better best score (a loss `best_metric` fills in when no `eval_loss` was logged); runs set by `max_steps` (or with one planned epoch) show step progress `global_step / max_steps` with time left instead of *epoch 0/1*; the curve keeps every logged loss step, not only the evaluation points.
- **Keras:** the planned epochs are read from a `config.json` (and other config files) next to the log, as the README says.
- **`GET /roots`** answers any valid token (read-only too) with the watched folders instead of 404; adding or removing folders with a read-only token is refused with 403 *read-only*.
- **Loss columns with any separator** (`loss/train`, `loss/val`, `loss_val`, `val-loss`) are losses, lower is better, everywhere: the run list, column info, the explanation, the best score and goals. They used to count as higher-is-better scores, so the worst epoch was "best".
- **A crash inside `with epokio.start(...)`** marks the run *failed* right away, with the reason (for example `RuntimeError: CUDA out of memory`) in `/runs` (`error`) and in the phone alert, instead of *stalled* three minutes later. Ctrl+C is not a failure.
- **Fast runs without a time column** (epochs under a second) get their elapsed time and time left. Only a folder whose files all appeared within 0.05 s counts as copied.
- **Lightning runs keep the folder above the experiment** in their name (`alice/exp002/version_0`), so runs from different people no longer share a name.
- **Alerts for SSH-mirrored runs name the server** (`ssh:<host>`) instead of `local`.
- **Hugging Face `eval_loss`-only runs:** the explanation no longer says no validation score was logged, `eval_loss` appears once in the run detail, and step runs name their x column `step` (`x_axis` in `/run`).
- **Windows:** network error messages in `epokio alerts --test`, the helper log and `epokio doctor` are no longer garbled on Korean (and other non-UTF-8) Windows.
- **`--root` accepts a pattern** such as `'/data/*/runs'`, expanded again on every scan so new folders appear without a restart (also through `POST /roots`).
- **`epokio setup` into a notebook or log** prints the address without the token and the command that shows it.
- README: new CPU figures (about 0.67 s per minute idle with 330 run folders, about 1.7 s with one live run) and a note on shared servers.
- **Phone alerts without a helper:** `epokio.start(..., notify=True)` sends the saved webhooks from the training process itself when the run finishes or fails (with the error type and message), for Colab and notebooks. Standard library only; a network failure never stops training; a helper watching the same run does not send the alert again.
- **Tokens limited to folders:** `epokio agent --add-token alice --scope read --root /data/alice/runs` (repeatable, patterns allowed) gives a token that sees only runs under those folders in the run list, run pages, images, events and the table, and gets 403 for everything else. Tokens without `--root` work as before.
- **Lightning resumes are linked:** a `version_N` that continues the epochs of the previous `version_M` in the same `lightning_logs` shows *Resumed from version_M* (`resumed_from` in `/runs`), and the older one no longer sends stalled or finished alerts.
- **Main score for a folder and from the terminal:** a main score chosen for a folder applies to every run under it that logs that column (a run's own choice wins); `epokio score <run or folder> <column> [--lower]`, `--auto`, `--list`. The run page says which column was picked automatically and why (`score_pick` in `/run`).
- **Safer defaults: new tokens are view-only.** `epokio agent --add-token NAME` now makes a read token (`--scope run` for one that can start training), and `epokio setup --lan` prints a fresh view-only token instead of this machine's own token. This machine's token in `~/.epokio/token`, used by the Mac app and the page setup opens here, keeps the run scope, so starting runs locally works as before.
- **Safer defaults: a helper open to the network does not run code** sent over the network (training, evaluation, auto-labeling, export, scripts, predictions, sweeps) unless it is started with `--allow-run` (`epokio setup --lan --allow-run`). The startup banner says which mode it is in. To start runs on a remote helper from your Mac, use `--allow-run` there and a run token.
- README: a new opening (phone alerts for stalled, NaN and finished runs, no code changes, over SSH) with an animated example from the real web page, an honest comparison with TensorBoard, W&B and nvitop, and the exact command and script Epokio runs on a server over SSH. Side features moved to docs/studio.md.
- Web page: Review and Sweeps moved under **More** in the tab bar (remembered per browser).
- The agent's startup line uses ASCII separators on consoles that are not UTF-8, and `/health` shows the token command with `~` instead of your home folder.
- Code comments in the core modules are now in English.

## 0.6.1 (2026-10-08)

- **Fix: one broken log hid every run in its folder.** A CSV row with more columns than the header, or a `trainer_state.json` that is not an object, made the whole watched folder show no runs (and be reported as slow). The broken run is now skipped and written to the helper's log.
- **Fix: time left for step-based runs was far too long.** It multiplied the time between log rows by the steps left, so a run logging every 100 steps showed *1d 1h* for 15 minutes. It now uses the time per step (or per epoch).
- **Releases wait for the full CI** on macOS, Windows and Linux before anything is published.
- Docs: how to open the web page from a phone (`ssh -L`, Tailscale or `--lan`), and the Korean README rewritten to match the English one.
- **SSH servers panel on the web page:** each host's state, a *Read now* button, and how many log files were skipped or cut.
- **Over SSH, a growing text log over the size limit keeps its first line and the tail** and keeps appending, instead of being skipped.
- **Step runs are labeled *step*** in the inbox, the CSV export, Compare and the report.
- Docs: Windows commands for `Epokio.exe` without Python, the SSH size limits, a TensorBoard column and local MLflow and Aim in the comparison, the Python download in the privacy table, and Korean README fixes.

## 0.6.0 (2026-10-01)

- **Send a test alert.** A **Send a test** button on the web page's Alerts (`POST /webhooks/test`), and `epokio alerts --add/--remove/--list/--test` to manage phone alerts from a terminal with no helper running.
- **Over SSH, logs that only grow send just the new tail,** and files over the size limit are reported: the Mac app warns how many log files were skipped.
- **Step-based runs are shown** instead of left out: W&B runs without `epoch` (by `_step`), CSV logs whose first column is `step` or `iter`, and TensorBoard step scalars with a step total such as `max_steps`. Runs carry `x_axis` (`epoch` or `step`).
- README restructured: shorter, with the menu bar GIF (light and dark); details moved to `docs/` (studio, remote, MCP, uninstall, Korean).
- **Fix: a run with no planned epochs was announced as finished** half an hour after it went quiet, even when it had crashed. It now only gets the *may have stopped* alert, since Epokio cannot tell.
- **Fix: two runs with the same folder name** (two `lightning_logs/version_0`) ending close together lost the second alert.
- **Phone alerts say which machine and which score** (*best val_acc 0.6000 · gpu-box-3*). A webhook that fails to send is written to the helper's log.
- **Stopped runs are explained as stopped** (*Training stopped at epoch 6 of 10*), not as finished.
- **The report and the AI-assistant report** no longer give end-of-run advice to runs still training.
- **When the loss became NaN,** that is what the notes say; a score that collapsed with it is no longer called overfitting.
- **Loss-only runs** (MAE-style pretraining) say that only the loss was checked, and warn when the training loss keeps rising.
- **Classes missing from the validation set** go to the bottom of the per-class table without a made-up 0.000 score, with a note to add examples.
- Korean: curve legends and head names are translated, and *Pose* is 포즈.
- Docs: the README says what "fails" and "stalls" cover (a crash shows up as stalled) and which files the SSH view reads and its size limits; docs/studio.md says the machine record uses the first GPU.

## 0.5.4 (2026-10-01)

- **Fix: a run still training was explained as finished.** A run at epoch 60 of 100 was told "best at epoch 60 of 60, train longer". Runs in progress now say *Still training: epoch 60 of 100* and the best score so far, and notes that only make sense at the end (still improving, plateau, early best) wait until it ends. Finished runs count against the planned epochs.
- **Fix: TensorBoard runs that log `epoch` from 1** were shifted by one ("epoch 21 of 20").
- **Fix: your own CSV logs** now also read the planned epochs from a config next to them, so they show progress and turn *done*.
- **Per-class notes for pose and segmentation runs** talk about the pose or mask scores, not the box ones. Classes with no examples in the validation set are left out of the average and marked *not in validation set*.
- **Double-clicking `Epokio.exe` opens the web page** as well as the tray icon (starting at login does not).
- Korean: particles after numbers and names are chosen by sound ("4.860으로", "mAP50-95가"), instead of fixed or shown as "이(가)". The few English labels left in the Korean web page are translated.
- `datasets/` and two stray files that slipped into 0.5.0 to 0.5.3 are removed.
- **TensorBoard runs over SSH.** The SSH view now brings back TensorBoard logs (and Keras-style `train/`, `validation/` folders) and saved configs, not only CSV and JSON logs.
- **Progress for more logs.** The planned epochs are read from a config saved next to the log (`args.yaml/json`, `config.yaml/json`, `hparams.yaml`, `opt.yaml`), so MAE/DeiT `log.txt` and TensorBoard runs can show progress and time left.
- README: a quick start for Mac, Windows and Linux on the first screen; SSH requirements spelled out; which logs are not shown yet (step-only); the comparison table without unsourced prices, with what trackers do better and how to use Epokio alongside one; the Train tab's downloads in the privacy table; uninstall on Windows and Linux. The Korean section now starts with Windows steps and names menu items as they appear in Korean.

## 0.5.3 (2026-10-01)

- Runs from other frameworks no longer show *Where it came from* and *Put in use* with a note that `best.pt` is missing. Those are about Ultralytics weights and now appear only for runs that have them.
- W&B runs show as `project/run-id` and OpenMMLab runs as `config/timestamp`, instead of the long folder name or the timestamp alone.
- **Over SSH, only what changed is sent.** The server skips files that have not changed since the last look, so watching a busy GPU server costs a fraction of the traffic. W&B runs now work over SSH too.
- **GPU fan on Windows and Linux.** Machines with an NVIDIA GPU now report its fan speed (from `nvidia-smi`), shown as *GPU fan* on the web page and in the Mac app when you watch that machine. The warning for fans stuck near full speed during training works there too. Windows and Linux have no standard way to read the other fans without extra drivers.
- **Fix:** in the Mac app, runs from any framework it did not know by name (W&B, OpenMMLab, log.txt) were labelled Ultralytics. They now show their own name, and timm runs show as timm instead of "Your code".
- **Weights & Biases runs** are read from the files W&B keeps on your disk (`wandb/run-*/run-*.wandb`, online or offline), without installing wandb: losses and scores per epoch, the planned epochs and settings from the config. Only runs that log an `epoch` value, since W&B otherwise counts steps. W&B's `latest-run` link no longer shows a run twice.
- **OpenMMLab runs** (MMDetection 3.x, MMPretrain, MMSegmentation) are read from `vis_data/scalars.json`: losses per epoch, COCO mAP and other validation scores, and the planned epochs from the saved config. Iteration-based runs are left out. Also over SSH.
- **Vision research code shows up with no changes.** Runs from the MAE, DeiT, DINO, BEiT and ConvNeXt codebases (a `log.txt` with one JSON line per epoch) are read, with top-1 accuracy as the main score. Also over SSH.
- **Fix: timm runs were invisible.** timm writes an `args.yaml` too, and Epokio took the folder for an Ultralytics run it could not read. `eval_*` and `test_*` columns now count as validation, not training.

## 0.5.2 (2026-09-28)

- README: says up front that no code changes or account are needed, lists your own training loop's CSV among the supported formats, and compares with Trackio.

## 0.5.1 (2026-09-28)

- **Your own training loop shows up without changes.** Any CSV whose first column is `epoch` and that has a loss column (`train_log.csv`, `log.csv`, ...) is read as a run of your code. Keras logs saved with a byte order mark (Windows, Excel, pandas `utf-8-sig`) are no longer missed.
- **Fix:** `epokio setup --root <folder>` run while the helper was already running saved the folder but the helper did not watch it until restarted. It now hands the folder to the running helper.
- **Fix:** a finished Keras, Lightning or TensorBoard run (no planned epoch count in its log) showed as *Stopped* with "stopped before the last one, train again from last.pt". It now shows as *Ended*.
- **Fix:** notes said "resuming will not help, the learning rate has already wound down" for runs with no learning rate record, and for runs that stopped before their planned epochs. A run that stopped early is now told to resume.
- **Fix:** `epokio doctor` said the helper was not running when it ran on a port other than 8787.
- Lightning runs are named by their project (`my_exp/version_0`) instead of all being `version_0`. `epokio setup` on a Mac no longer suggests the Windows/Linux tray. Scores in the API no longer carry float noise (`0.8200000000000001`).

## 0.5.0 (2026-09-28)

- **Notes for Hugging Face, Lightning and Keras runs speak their language.** "Keep the best epoch" now says how in that framework (`load_best_model_at_end`, `ModelCheckpoint`, `restore_best_weights`) instead of `best.pt`, which those runs do not have.
- New notes for every framework: **the score stopped improving** halfway (with that framework's early stopping), and **training loss blew up** without becoming NaN.
- **Fix:** when the best score came in the first epochs and then fell, a note could say the score "did not drop".
- **Data versions.** A run's page names the version of its data (*Data v3 of 4*: the third version of that `data.yaml` Epokio has seen) and warns when the data changed after the run trained, with what changed. Compare offers the same for any two runs trained on different data. Runs started from Epokio keep the data version from the moment they started; before, the version was taken when the page opened, so an old run could show today's data.
- **Predictions by epoch.** Turn on *Save predictions every 5 epochs* when you start a run, and its page gets a slider through the same four validation images as the model learned. It predicts on the CPU inside the training, a second or two each time. Off by default.
- **The machine while training.** While a run trains, the helper records GPU, GPU memory, CPU, memory, temperature and fan every 15 seconds for that run. Its page shows the curves and averages afterwards, and a note when the GPU was busy less than half the time (the GPU is probably waiting for data). Only runs that train after this update have it.
- **Per-class scores.** A run's page shows precision, recall and mAP for each class, weakest first, with the ones well below the class average highlighted and a note naming them. Runs Epokio starts save this at the end of training at no extra cost. For any other Ultralytics run, **Work out per-class scores** runs one validation pass with its `best.pt` from the queue.

## 0.4.4 (2026-09-28)

- **Fan speed** on Macs with a fan: the menu bar popover and the web page show how fast the fastest fan spins, as a share of its maximum (rpm on hover). Turn it off in Settings → General. Macs without a fan show nothing.
- New machine warning: the fans stayed at 90% or more for 5 minutes while training. It goes to your Mac and, if set up, your phone, like the GPU and disk warnings.
- `epokio setup --root <folder>` now remembers the folder. Before, running setup again without `--root`, or restarting the helper, lost it.
- The address `epokio setup` prints now opens the Train and Queue tabs unlocked on this machine, like the page it opens for you. Over SSH it still prints the plain address.
- A run copied from another machine, with no time column in its log, no longer shows "0s/epoch · 0s left" or "took 0s". The time is shown as unknown.
- PyPI links to the GitHub repository, issues and changelog.

## 0.4.3 (2026-09-26)

- **Fix:** the web page installed with `pip install epokio` 0.4.0 to 0.4.2 was blank, because the package left out its scripts and styles. The Windows `Epokio.exe` and the Mac app were not affected.
- Practice mode no longer freezes on Windows when the helper reads its results at the same moment it writes them.

## 0.4.2 (2026-09-26)

- The Windows `Epokio.exe` has the Epokio icon instead of the default one.
- README: the web page section lists what it does today (Review, Sweeps and Table tabs included), the wording matches the app, and the Korean section uses the same terms as the app.

## 0.4.1 (2026-09-26)

Documentation only. No changes to the app or the helper.
- The README and the PyPI page now match 0.4.0: one queue per GPU, the label editor, the languages the app speaks, SSH watching with nothing installed, view-only tokens, practice mode and keyboard shortcuts.
- Building from source needs Xcode 26 or later. Automatic updates are off in current releases (they are not signed with an update key yet).
- New screenshots of a run's page and of Compare.

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
- The helper no longer stalls for half a minute at start when reverse DNS is slow (offline, behind a login page, or on a slow VPN).

**Fixes**
- Windows: error reports and run records now hide your home folder in every form Windows writes it (backslashes, other letter case, escaped backslashes), so your user name is no longer left in them.
- Windows: watching a server over SSH works (Windows OpenSSH cannot share connections), line endings are kept, and odd folder names on the server no longer stop the watcher.
- SSH watching refuses file names that would write outside its own folder.
- Mac app: runs started without a seed, or trained on an NVIDIA machine, open again (the run page failed to load them).
- Comparing the same dataset on a Mac and on Windows no longer marks every file as changed.

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
