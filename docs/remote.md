# Remote machines, Windows, Linux and your phone

[Back to README](../README.md)

## Remote GPU

Train on a Windows or Linux machine, watch from your Mac.

```bash
# on a Linux training machine
pip install epokio
epokio setup --lan --autostart
```

```powershell
# on a Windows training machine (Python installed with "Add python.exe to PATH")
py -m pip install "epokio[tray]"
py -m epokio setup --lan --autostart
```

No Python on Windows: run `Epokio.exe setup --lan --autostart` instead.

`epokio setup` finds your training folders, starts the helper without a console window, prints a
view-only token to paste into the Mac app (with `--lan`), and opens the page. `--lan` lets other machines on your network
reach it; `--autostart` brings the tray back when you log in. Run it again any time, it changes
nothing that is already right.

**Nothing to install on the server?** In the Mac app, open **Settings → Machines → Over SSH** and pick a host
from your `~/.ssh/config`. Epokio uses your SSH keys to check every 15 seconds and copy the log files that changed
(`results.csv`, TensorBoard and W&B files and similar), never images or weights. The server only needs `python3` (3.6 or later)
and key-based login (no password or one-time-code prompts). Nothing is written on the server and it needs no internet.
It looks under your home folder; add other paths such as `/scratch/you/runs` under *Other folders* in the same settings. Hosts from `~/.ssh/config`,
including `ProxyJump`, go through your own `ssh`. Over SSH it reads the file names the supported formats use
(`results.csv`, `log.txt`, `summary.csv`, `metrics.csv`, `trainer_state.json`, TensorBoard and W&B files and a few more),
not any CSV name. The size limit is 4 MB for text logs and 20 MB for TensorBoard and W&B files (for a file it already has,
the limit applies to the new part). A growing text log over the limit keeps its first line and the last 4 MB, then keeps
appending. TensorBoard, W&B and config files over the limit are skipped. The Mac app and the web page's SSH panel say
how many files were skipped or cut. This is view only: to start training there, install the helper as above.

Without `--lan` the helper listens on this machine only, which is what you want if you just came
for the web page and the tray.

`--label lab-07` sets the name this machine shows as (handy when a class or a team watches many
machines; the default is the computer name). Over SSH, setup prints an `ssh -L` tunnel command
instead of opening a browser.

The helper answers when you reach it by IP address, `localhost`, or a name whose first part is this
machine's name (`pc`, `pc.lan`, `pc.tailXXXX.ts.net`; not `pc2.lan`). This blocks DNS-rebinding pages. For any other
name, set `EPOKIO_ALLOWED_HOSTS=trainer.example,other.name` on this machine, or send the token.

Install it wherever you like. The helper needs no third-party packages, so a small separate
virtual environment is the safe choice if you would rather not touch the Python your training uses.

* Watching on this machine needs no token: runs, scores, curves, notes and result images. Result
  images are served only from the folders the helper watches.
* A helper opened to the network (`--lan`) asks for the token to view as well, not only to start things.
* **A helper opened to the network does not run code by default.** Training, evaluation, auto-labeling, export,
  scripts and predictions sent over the network are refused (403) unless it was started with `--allow-run`
  (`epokio setup --lan --allow-run`). The startup banner says which mode it is in. On `127.0.0.1` nothing changes.
* **New tokens are view-only by default.** `epokio agent --add-token alex` makes a read token; add `--scope run`
  for one that can start and stop training. `setup --lan` prints a fresh view-only token (named `setup-lan`)
  for the Mac app or another computer. This machine's own token in `~/.epokio/token`, which the Mac app and the
  page opened by setup on this machine use, keeps the run scope. Add `--root /data/alex/runs` (repeatable) to limit a token to runs under those folders.
  It is shown once and stored hashed; `--list-tokens` and `--revoke-token alex` manage them. A read token
  can watch but cannot start or stop anything.
* **Everything else needs the token**, including requests that only look like reading: listing your
  Python environments, reading a training log, and checking a dataset folder all run a process or
  read outside the watched folders.
* Traffic is plain HTTP. Prefer an SSH tunnel (`ssh -L 8787:127.0.0.1:8787 gpu-pc`) or Tailscale over `--lan`, and keep it off shared or public networks.
* On a machine other people can log in to, turn on **Settings → General → Ask for the token even on this Mac** (or start the helper with `--require-token`). Otherwise anyone with an account there can read your runs over `127.0.0.1`.
* Korean and other non-ASCII file names are normalized between macOS (NFD) and Windows (NFC),
  so a path chosen on the Mac is found on the PC.

## On Windows, Linux or your phone

**You do not need a Mac.** Install on the machine that trains, run one command, and you have the
progress, scores, curves, result images, comparisons and phone alerts.

**Never used a terminal? On Windows:** download `Epokio.exe` from
[Releases](https://github.com/8rulerstar/epokio/releases/latest) and double-click it. It needs no Python to watch.
To train from the Train tab, install Python 3.10 or later first; the tab then sets up PyTorch and Ultralytics with one button. Windows SmartScreen may warn about an
unsigned app the first time: choose **More info → Run anyway**.

**With Python** (3.10 or later; from [python.org](https://www.python.org/downloads/), tick **Add python.exe to PATH**):

```bash
py -m pip install "epokio[tray]"
py -m epokio setup --autostart
```

(If typing `epokio` says "not recognized", use `py -m epokio` instead; it is the same command.)

That finds your training folders, starts the helper with no console window, opens the page already
unlocked, and makes the tray come back when you log in. With `--lan`, Windows asks whether Python may
use the network: tick **Private networks** and click **Allow**, or your phone cannot connect. Turn that last part off again with
`py -m epokio autostart --off`, or from the tray menu (*Start when I log in*). The entry is an ordinary
shortcut in your Startup folder (`shell:startup` in the Run box), so you can also just delete it.

**`Epokio.exe` without Python** accepts `setup`, `autostart`, `agent` and `tray`. In PowerShell, in the folder
that holds it: `.\Epokio.exe setup --lan --autostart`, `.\Epokio.exe autostart --off`,
`.\Epokio.exe agent --show-token`, `.\Epokio.exe agent --add-token alex --scope read`, `.\Epokio.exe agent --stop`.
`doctor`, `alerts` and `watch` need `py -m pip install epokio`.

**On a Linux server (Ubuntu 22.04 or 24.04, no desktop, over SSH):** on 24.04 the system `pip` refuses to install
(PEP 668), so use a small virtual environment (on 22.04 it is optional but still tidy):

```bash
sudo apt install python3-venv
python3 -m venv ~/.epokio-venv
~/.epokio-venv/bin/pip install epokio            # no tray needed
~/.epokio-venv/bin/python -m epokio setup --root /data/runs --autostart
```

On a machine without a display, `--autostart` writes a systemd user service instead of a tray entry
and prints the two commands that turn it on. Setup does not open a browser there; it prints an
`ssh -L 8787:127.0.0.1:8787 <server>` command, and then `http://127.0.0.1:8787/` works on your own
computer. That tunnel is the safest way in. If you use `--lan` instead and ufw is on, allow your
network only: `sudo ufw allow from 192.168.0.0/16 to any port 8787 proto tcp`. Runs outside your home
folder (`/data`, `/mnt`, `/workspace`) are not found on their own, so pass `--root`. A quoted pattern such as
`--root '/data/*/runs'` is expanded again on every scan, so a new person's or experiment's folder shows up
without restarting the helper. To log from your
own training code with `epokio.start`, install Epokio into the **training** environment too.

## What you get without a Mac

The label editor and starting auto-label jobs are in the Mac app. The web page, terminal view, tray and
phone push below work without one.

**Your own training loop.** Not using Ultralytics, Hugging Face, Lightning or Keras? Two lines make it show up like any other run:

```python
import epokio
with epokio.start("runs/detr-small", epochs=50, lr=1e-4, batch=16) as run:
    for epoch in range(1, 51):
        ...
        run.log(train_loss=tl, val_loss=vl, precision=p, recall=r, mAP50=m)   # tensors are fine
```

Logging never stops your training, even when the file is busy. In multi-GPU training only rank 0 writes. In a notebook, use the `with` block or call `run.finish()` after the loop, so the run shows as done; a run that ends with an error is never marked done. With `epokio.start(..., notify=True)` the training process sends the phone alert itself when it finishes or fails (for Colab and notebooks with no helper; see the README).

**A web page.** On the training PC open `http://127.0.0.1:8787/` (setup opens it for you). From your phone or another computer, use the address setup printed (needs `--lan`). Any browser works, with nothing to install and no account.

* **Runs and Table:** progress, scores, curves, notes and result images for every run, and a sortable table you can filter (`lr0<0.01 batch>=16 tag:sample`).
* **Train and Queue:** pick what the model should learn and how big it is. Epokio checks the dataset first and stops you if it is broken. With no Python for training yet, one button sets one up (CUDA PyTorch on a PC with an NVIDIA GPU). The queue shows each job's log, epoch, time left and finish time; reorder or cancel what is waiting, and stop the running job after a confirmation. When a job fails, it says why and what to change (GPU out of memory, data loader workers on Windows, CPU-only PyTorch, wrong dataset paths and more).
* **Train again and Resume:** an Ultralytics run's page trains again with the same settings, and a run stopped before its last epoch resumes from `weights/last.pt` in the same folder with the Python that first ran it.
* **Main score:** choose which logged value counts as the score, whether lower is better (loss, error rate), and a target that sends a phone alert. The list, ranking and alerts follow it. The page says which column was picked automatically and why. From a terminal: `epokio score <run> <column> [--lower]` for one run, or give a folder of runs to set the default for every run under it (`--auto` forgets the choice, `--list` shows the columns).
* **Compare:** up to eight runs on one chart with only the settings that differ, a warning when they used different data, a settings table for every run shown, and CSV export.
* **Review and Sweeps:** rank validation images by score and mark what went wrong, or run a sweep and see which values led to the best score.
* **Alerts:** turn on phone alerts (ntfy, Slack, Discord or Telegram) without the Mac app.

On the training PC the page opens unlocked from the tray or setup. On another device it asks for the machine's token once (setup prints it with `--lan`, or run `py -m epokio agent --show-token`; `Epokio.exe agent --show-token` without Python), and the token stays in that browser. Train finds the Python environments on the machine (conda, python.org installs, project `.venv`s) and builds its settings from that environment's own Ultralytics.

**A terminal view.** On a server over SSH:

```bash
epokio watch                               # reads the helper on this machine, or the current folder
epokio watch --root runs/                  # no helper needed: read a folder directly
epokio watch --agent http://gpu-pc:8787    # watch another machine
```

Arrow keys to pick a run, Enter for scores, curves and notes, Tab to switch loss and scores, q to quit.

**A system tray icon on Windows and Linux.** `pip install "epokio[tray]"`, then `epokio tray`. The Epokio icon fills with progress, the tooltip shows what you pick (progress, time left, finish time, epoch, best score, GPU), and the menu lists runs and opens the dashboard. It starts the helper for you.

**Phone push.** Add an [ntfy](https://ntfy.sh) address such as `https://ntfy.sh/your-secret-topic` as a webhook (Settings → Notifications in the Mac app, or **Alerts** on the web page) and install the free ntfy app. The training machine pushes to your phone directly, even when your Mac is off. You can also run your own ntfy server.
