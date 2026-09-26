# Epokio

Watch, compare, queue and report machine learning training runs from a web page, a tray icon, a terminal
or the macOS menu bar. Epokio reads the files your framework already writes, so there is no logging code
to add, no account and no cloud.

## What it does

* **See every run** on this machine or a remote GPU box: state, epoch, time left, best score, curves,
  plain-language notes ("recall is much higher than precision…") and the result images your framework saved.
* **Get told** when a run finishes, fails (NaN loss), stalls or reaches a target score: on the Mac, in the
  tray, or as a phone push (ntfy, Slack, Discord, Telegram).
* **Compare runs**: only the settings that differ, a settings table for a whole sweep next to each run's
  main score, CSV export and Markdown reports.
* **Start and queue runs** (Ultralytics YOLO) from the web page, one at a time, with a data check before
  starting, a one-button Python setup (CUDA PyTorch on NVIDIA machines), resume from `weights/last.pt`,
  and failure causes in plain words.
* **AI assistants** can read and queue runs through the MCP server (`pip install "epokio[mcp]"`).

Reads Ultralytics (`results.csv`), Hugging Face Trainer (`trainer_state.json`), PyTorch Lightning
(`metrics.csv`), Keras (`CSVLogger`) and TensorBoard event files (read without TensorFlow). A hand-written
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
