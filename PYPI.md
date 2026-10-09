# Epokio

**Get a phone alert when a training run stalls, hits NaN or finishes.**
No code changes: it reads the logs YOLO, Hugging Face, Lightning, Keras and TensorBoard already write. Works over SSH.

![A run goes from Training to Stalled and an ntfy alert arrives on the phone](https://raw.githubusercontent.com/8rulerstar/epokio/main/docs/images/alert.gif)

## Quick start

Python 3.10 or later, on Windows, macOS or Linux. In a terminal in your project folder, on the machine that trains:

```bash
pip install epokio
epokio setup
epokio watch --once
```

`epokio setup` finds your runs, starts the helper (a small background program that reads the logs and sends the alerts) and opens its page. `epokio watch --once` prints the same list in the terminal.
Setup looks in this folder and in Desktop, Documents, Downloads, Projects and `~/runs`, inside your user folder. Runs somewhere else, like `D:\` or `/data`? Name the folder: `epokio setup --root D:\myproject\runs`.
On Windows, if `pip` or `epokio` is not recognized, put `py -m` in front: `py -m epokio setup`.
If pip stops with *externally-managed-environment* (Ubuntu 24.04, Homebrew Python), use a virtual environment or a conda env ([how](https://github.com/8rulerstar/epokio/blob/main/docs/remote.md#on-windows-linux-or-your-phone)).

## Phone alerts in 3 steps

1. Install the [ntfy](https://ntfy.sh) app on your phone and subscribe to a topic only you know (letters, digits, `-` and `_`).
2. Save it on the training machine, with your topic in place of `your-secret-topic`: `epokio alerts --add https://ntfy.sh/your-secret-topic`
3. Check it: `epokio alerts --test`

From then on, the helper sends an alert when a run finishes, fails (NaN loss or a crash) or stalls (no new epoch for well past its usual pace, 3 minutes at least). Slack, Discord and Telegram webhooks work the same way (`https` only).
Alerts go out only while the helper runs, and it does not come back after a reboot by itself. To start it at login, `pip install "epokio[tray]"` and run `epokio setup --autostart` (Windows and Linux; on a server without a desktop it writes a systemd service instead).

## What you get

<p align="center">
  <img src="https://raw.githubusercontent.com/8rulerstar/epokio/main/docs/images/run-detail.gif" height="400" alt="Loss curves gain one epoch at a time; the lowest validation loss is marked at epoch 23, then flagged as overfitting with a note that the score fell">
  <img src="https://raw.githubusercontent.com/8rulerstar/epokio/main/docs/images/phone.gif" height="400" alt="The Epokio page on a phone with a view-only token: a run turns Done, and a Hugging Face run's score goes up when a new checkpoint lands">
</p>

* **One live list** of every run: progress, time left and best score, whatever framework wrote the log.
* **Curves with a plain-language note.** It marks the epoch with the lowest validation loss and says when the score starts to fall.
* **On your phone too.** `epokio setup --lan` prints the address and a view-only token, which shows everything and hides every button that changes something.
* **Also in a terminal** (`epokio watch`, good over SSH), a tray icon on Windows and Linux, and a [macOS menu bar app](https://github.com/8rulerstar/epokio/blob/main/docs/studio.md).
* **No account, no upload.** Only the alerts you add leave the machine.

## Why not just use...

| | Better than Epokio at | What Epokio adds |
|---|---|---|
| **TensorBoard** | Per-step charts, images, histograms, the profiler. | Alerts with no browser tab open. One list for many frameworks' logs, TensorBoard files included. |
| **W&B** | Team dashboards, sweeps, artifacts, a model registry. | No account, no logging calls, no upload. Reads W&B's local files, so you can keep both. |
| **nvitop** | Live GPU, process and memory view. | Knows the run: epoch, time left, best score, stalls and NaN. |

## Remote servers over SSH

Run the quick start on the server (runs under `/data` or `/scratch` need `--root`). In an SSH session setup opens no browser:
it prints a tunnel command for your own computer, such as `ssh -N -L 18787:127.0.0.1:8787 <server>`, and then `http://127.0.0.1:18787/` shows the server's runs.
The helper listens on `127.0.0.1`, so it is not on the network, and `epokio watch` works in a plain SSH session.
The macOS app can also read a server over SSH with nothing installed there ([how](https://github.com/8rulerstar/epokio/blob/main/docs/guide.md#ssh-from-the-mac-app)).

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
* The page can also start training. New tokens are view-only; `epokio agent --add-token NAME --scope run` makes one that can start runs.
* A `--lan` helper runs nothing sent over the network unless it was started with `--allow-run`.
* On a shared server, other accounts can read a helper on `127.0.0.1`. Run it as `epokio agent --require-token` and give each person a token limited to their folders ([how](https://github.com/8rulerstar/epokio/blob/main/docs/guide.md#limits)).
* The helper speaks plain HTTP. Prefer an SSH tunnel or Tailscale over `--lan`. Details: [docs/remote.md](https://github.com/8rulerstar/epokio/blob/main/docs/remote.md).

## Supported formats

Ultralytics YOLO, Hugging Face Trainer, PyTorch Lightning (`CSVLogger`), Keras (`CSVLogger` or the `TensorBoard` callback),
TensorBoard event files and W&B local files (neither needs to be installed), timm, OpenMMLab, MAE/DeiT-style `log.txt`,
and your own loop: `epokio.start`, or a CSV whose first column is `epoch`, `step`, `iter` or `iteration`.
Which file each one reads, planned epochs and best-score rules: [docs/guide.md](https://github.com/8rulerstar/epokio/blob/main/docs/guide.md#supported-formats).

## More

Full docs, the macOS menu bar app and the Windows app: [github.com/8rulerstar/epokio](https://github.com/8rulerstar/epokio)
([guide](https://github.com/8rulerstar/epokio/blob/main/docs/guide.md), [changelog](https://github.com/8rulerstar/epokio/blob/main/CHANGELOG.md)).

Something wrong? Run `epokio doctor` and paste the output into an issue (it never prints your token). MIT licence.
