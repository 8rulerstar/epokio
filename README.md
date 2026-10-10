<p align="center"><img src="docs/images/icon.png" width="96" alt="Epokio icon"></p>
<h1 align="center">Epokio</h1>
<p align="center"><b>Epokio reads the training logs you already have and alerts your phone when a run stalls, hits NaN, or finishes.</b><br>
No code changes, no account: it reads what YOLO, Hugging Face, Lightning, Keras and TensorBoard already write. Works over SSH.</p>
<p align="center"><a href="https://pypi.org/project/epokio/"><img src="https://img.shields.io/pypi/v/epokio" alt="PyPI"></a> <a href="https://github.com/8rulerstar/epokio/actions/workflows/ci.yml"><img src="https://github.com/8rulerstar/epokio/actions/workflows/ci.yml/badge.svg" alt="CI"></a> <a href="LICENSE"><img src="https://img.shields.io/pypi/l/epokio" alt="License"></a> · <a href="docs/README.ko.md">한국어</a></p>

<p align="center"><img src="docs/images/alert.gif" width="720" alt="A run on the Epokio web page goes from Training to Stalled, and an ntfy alert with the run, epoch and best score arrives on the phone"></p>

## Quick start

Python 3.10 or later, on Windows, macOS or Linux (the `python3` that ships with macOS can be 3.9; check with `python3 --version`). Training folder outside Desktop, Documents, Downloads, Projects and `~/runs` in your user folder? Add it: `epokio setup --root <folder>`.
In a terminal in your project folder, on the machine that trains:

```bash
pip install epokio
epokio setup
epokio watch --once
```

`epokio setup` finds your runs, starts the helper (a small background program that reads the logs and sends the alerts) and opens its page. `epokio watch --once` prints the same list in the terminal.
Setup looks in this folder and in those folders. For runs in `D:\` or `/data`, for example: `epokio setup --root D:\myproject\runs`.
On Windows, if `pip` or `epokio` is not recognized, put `py -m` in front: `py -m epokio setup`.
If pip stops with *externally-managed-environment* (Ubuntu 24.04, Homebrew Python), use a virtual environment or a conda env ([how](docs/remote.md#on-windows-linux-or-your-phone)).

## On a shared GPU server over SSH

No sudo needed. In your own account on the server (a conda env works too):

```bash
python3 -m venv ~/.epokio-venv && ~/.epokio-venv/bin/pip install epokio
~/.epokio-venv/bin/epokio setup --root /data/you/runs --autostart
```

`--autostart` writes a systemd user service, so the helper survives SSH logout and reboots. To keep it running after you log out,
setup turns on linger (`loginctl enable-linger $USER`); if the server refuses, an admin runs `sudo loginctl enable-linger <you>` once.
`epokio doctor` says in one line whether the helper runs now and comes back. Setup prints an SSH tunnel such as
`ssh -N -L 18787:127.0.0.1:8787 <server>` for your own computer, then `http://127.0.0.1:18787/` shows the server's runs; `epokio watch` works in plain SSH.
Other accounts on the server can read a helper on `127.0.0.1`, so on a shared machine see [limits](docs/guide.md#limits).

## Phone alerts in 3 steps

1. Install the [ntfy](https://ntfy.sh) app on your phone and subscribe to a topic only you know (letters, digits, `-` and `_`). On ntfy.sh the topic name works like a password: anyone who knows it can read the alerts, so make it long, or [run your own ntfy server](https://docs.ntfy.sh/install/).
2. Save it on the training machine, with your topic in place of `your-secret-topic`: `epokio alerts --add https://ntfy.sh/your-secret-topic`
3. Check it: `epokio alerts --test`

From then on, the helper sends an alert when a run finishes, hits a NaN loss, or stalls: no new log row for 1.5 times its recent epoch time when the planned epochs are known (3 times plus a minute otherwise), and for 1.25 times a long gap that has already happened twice (a periodic evaluation, say), 3 minutes at least, a floor you can raise with `epokio config stall_min 10`. A crash shows up as a stall, or right away as a failure if your script calls `epokio.start()`. A run that dies before it logs its first epoch (a data loader error, say) cannot be told apart from a long first epoch, so it gets no alert unless it uses `epokio.start()`. Each alert carries the run name, its progress and best score, and this machine's name (`epokio setup --label NAME` to choose another). Slack, Discord and Telegram webhooks work the same way (`https` only).
Alerts go out only while the helper runs. `epokio setup --autostart` starts it again without sudo: on Linux a systemd user service that keeps running after logout and reboot; on macOS a LaunchAgent and on Windows the Startup folder, which start it when you log in.
`epokio doctor` shows whether it runs now and starts again; `epokio doctor --test-alert` sends a real test alert.

## What you get

<p align="center">
  <img src="docs/images/run-detail.gif" height="400" alt="Loss curves of a YOLO run gain one epoch at a time. The lowest validation loss is marked at epoch 23, then flagged as overfitting, and a note says the score peaked at epoch 23 and fell">
  <img src="docs/images/phone.gif" height="400" alt="The Epokio page on a phone with a view-only token: a run turns Done, a tap opens a Hugging Face run, and its score goes up when a new checkpoint lands">
</p>

* **One live list** of every run: progress, time left and best score, whatever framework wrote the log.
* **Curves with a plain-language note.** It marks the epoch with the lowest validation loss and says when the score starts to fall.
* **On your phone too.** `epokio setup --lan` prints the address and a view-only token, which shows everything and hides every button that changes something.
* **Also in a terminal** (`epokio watch`, good over SSH), a tray icon on Windows and Linux, and a [macOS menu bar app](docs/studio.md).
* **No account, no upload.** From the pip install, only the alerts you add leave the machine. The Mac app also checks for updates and, if you turn it on with your own key, sends metric summaries to an AI service.

## Notebooks and Colab

Where no helper can run, the training process sends the alert itself:

```python
!pip install epokio
!epokio alerts --add https://ntfy.sh/your-secret-topic

import epokio
with epokio.start("runs/colab-exp", epochs=20, notify=True) as run:
    for epoch in range(20):
        ...
        run.log(train_loss=tl, val_loss=vl, acc=acc)
```

You get an alert when the block ends, or when it raises (with the error). A network failure never stops training.

## Security defaults

* The helper listens on `127.0.0.1` only. `setup --lan` opens it to your network and then asks for a token.
* Starting training, queue jobs and sweeps from the page (and from MCP) is off. `epokio config launch_runs on` turns it on and shows the Train, Queue and Sweeps tabs. The helper the Mac app starts for itself has it on, so the app's training screens work.
* New tokens are view-only; `epokio agent --add-token NAME --scope run` makes one that can change things.
* A `--lan` helper runs nothing sent over the network unless it was started with `--allow-run`.
* On a shared server, other accounts can read a helper on `127.0.0.1`. Over SSH on Linux, `epokio setup` asks to make viewing need a token too (`reads_token always`, on by default without a terminal, `--no-lock-reads` skips it; the page then asks for `epokio agent --show-token` once). Elsewhere run `epokio config reads_token always`. Then give each person a token limited to their folders ([how](docs/guide.md#limits)).
* The helper speaks plain HTTP. Prefer an SSH tunnel or Tailscale over `--lan`. Details: [docs/remote.md](docs/remote.md).

## Compared with other tools

Checked against each project's README and docs in October 2026. Epokio can read TensorBoard event files and W&B's local files, so it can sit next to them.

| | Code changes | Account | Alerts | Pick it instead when |
|---|---|---|---|---|
| **Epokio** | None if your framework writes a supported file (Keras: a `CSVLogger` or `TensorBoard` callback) | No | Stall (a crash shows up as one), NaN, finish | |
| **TensorBoard** | Your code or framework writes event files | No | None | You want per-step charts, images, histograms or the profiler |
| **W&B** | `wandb.init`/`log` or a framework integration | Yes | Run finished or crashed (Slack, email, a per-user setting); `run.alert()` from your code; Automations to Slack or a webhook (run-metric ones only on Forge and Dedicated Cloud) | A team shares dashboards, sweeps, artifacts and a model registry |
| **Trackio** (Hugging Face) | `trackio.init`/`log` (W&B-style API) or HF Trainer `report_to="trackio"` | No (optional HF Space) | `trackio.alert()` from your code, to webhooks | You want a free local W&B-style dashboard you can share on a Space |
| **healthchecks.io** | A ping (HTTP request) from your script when it succeeds (start and fail pings optional) | Yes on the hosted service (open source, self-hostable) | A ping missing past a fixed period or cron schedule plus a grace time; email, Slack, webhooks, SMS, PagerDuty and more | You want one watchdog for cron jobs and scheduled tasks, not only training. |
| **knockknock** | A decorator around your training function | No (needs the chat service's credentials) | Start, finish, crash on 12 services (last release 2020) | You only need a finish or crash ping on email, Teams, SMS and the like |
| **runmon** | None: wraps the command or attaches to tmux | No (ntfy, Telegram, Bark or a webhook directly; its app pairs through a relay you can self-host) | Done, failed, error output, GPU idle, log silence, disk full | You want GPU-per-process views, or alerts for any command, not just training logs |

More columns (MLflow, Aim, Ultralytics Platform, price): [docs/guide.md](docs/guide.md#how-it-compares).

## Supported formats

Ultralytics YOLO, Hugging Face Trainer, PyTorch Lightning (`CSVLogger`), Keras (`CSVLogger` or the `TensorBoard` callback),
TensorBoard event files and W&B local files (neither needs to be installed), timm, OpenMMLab, MAE/DeiT-style `log.txt`,
and your own loop: `epokio.start`, or a CSV whose first column is `epoch`, `step`, `iter` or `iteration`.
Which file each one reads, planned epochs and best-score rules: [docs/guide.md](docs/guide.md#supported-formats).

## More

[Guide](docs/guide.md) (alerts, limits, full comparison, privacy, troubleshooting) ·
[Mac app](docs/studio.md) · [Remote helpers, Windows app, tray, phone](docs/remote.md) · [AI assistants (MCP)](docs/mcp.md) ·
[Uninstall](docs/uninstall.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

Something wrong? Run `epokio doctor` and paste the output into an issue (it never prints your token). License: [MIT](LICENSE).
