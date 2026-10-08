# Epokio

**Get a phone alert when the training run on your GPU box or server stalls, NaNs or finishes.**
No code changes: it reads the logs you already write. Works over SSH.

![A run goes from Training to Stalled and an ntfy alert arrives on the phone](https://raw.githubusercontent.com/8rulerstar/epokio/main/docs/images/alert.gif)

| | What it does better than Epokio | What Epokio adds |
|---|---|---|
| **TensorBoard** | Rich charts per step, images, histograms, embeddings and the profiler. | Alerts when a run stalls, hits NaN or finishes, with no browser tab open; one list for many frameworks' logs; remote boxes over SSH with nothing installed. |
| **W&B** | Team dashboards, history across machines, sweeps, artifacts and a model registry. | No account, no logging calls, no upload; works without internet; reads W&B's local files, so you can keep both. |
| **nvitop** | A live view of each GPU, its processes and memory. | Knows about the run: epoch, time left, best score, stall and NaN detection, phone alerts. |

There is no account and no cloud, and no logging code to add when your framework writes a supported file (Keras needs a
`CSVLogger` or `TensorBoard` callback; a hand-written loop uses `epokio.start`, below). It also has a web page, a tray icon,
a terminal view and a macOS menu bar app.

## What it does

* **See every run** on this machine or a remote GPU box: state, epoch, time left, best score, curves,
  plain-language notes ("recall is much higher than precision…") and the result images your framework saved.
* **Get told** when a run finishes, fails (NaN loss), stalls or reaches a target score: on the Mac, in the
  tray, or as a phone push (ntfy, Slack, Discord, Telegram) sent by the helper while it runs.
* **Compare runs**: only the settings that differ, a settings table for a whole sweep next to each run's
  main score, CSV export and Markdown reports.
* **Start and queue runs** (Ultralytics YOLO) from the web page, one at a time on each GPU, with a data check before
  starting, a one-button Python setup (CUDA PyTorch on NVIDIA machines), resume from `weights/last.pt`,
  and failure causes in plain words.
* **AI assistants** can read and queue runs through the MCP server (`pip install "epokio[mcp]"`).

Reads Ultralytics (`results.csv`), Hugging Face Trainer (`trainer_state.json`), PyTorch Lightning
(`metrics.csv`), Keras (`CSVLogger`) and TensorBoard event files (read without TensorFlow). The best score
appears when a run logs a validation metric (or Hugging Face's `best_metric`); loss-only runs show none (Hugging Face runs that evaluate only `eval_loss` use the lowest `eval_loss`). A hand-written
loop shows up with two lines:

```python
import epokio
with epokio.start("runs/my-model", epochs=50, lr=1e-4) as run:
    for epoch in range(50):
        ...
        run.log(val_loss=vl, accuracy=acc)
```

## Start

```
pip install epokio
epokio setup            # finds your runs, starts the helper, opens the page
epokio setup --lan      # also let your phone or another computer watch this machine
```

Other commands: `epokio watch` (terminal view, good over SSH), `epokio tray` (`pip install "epokio[tray]"`),
`epokio doctor` (what Epokio sees, for a bug report), `epokio agent --stop`.

Viewing is open on this machine; anything that starts, stops or changes something needs the machine's token
(`epokio agent --show-token`). The helper uses only the Python standard library.

MIT licence.
