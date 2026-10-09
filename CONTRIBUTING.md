# Contributing to Epokio

Thanks for taking a look. Epokio is a menu bar app that shows how far a training run
has got, plus a small Python agent that does the actual work.

## How the repository is laid out

```
src/epokio/    Python agent: scanning runs, monitoring, analysis, reports, HTTP API
mac/           macOS app (SwiftUI). Screens only, it talks to the agent over HTTP
tests/         pytest suite for the Python side
docs/          design system, release procedure and audit notes
design/        design tokens (the single source for colors, fonts, spacing, motion)
tools/         maintenance scripts
```

The rule behind the split: **all logic lives in Python, once.** The macOS app (and a
future Windows app) only draws what `/runs`, `/system` and friends return. If you find
yourself computing something in Swift that a non-Mac user would also need, it belongs
in `src/epokio/` instead.

## Development setup

Python 3.10 or newer.

```bash
git clone https://github.com/8rulerstar/epokio
cd epokio
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

On Windows, `python3` is often only a Microsoft Store shortcut and the venv has no `bin`
folder. In PowerShell or cmd, call the venv's Python directly (no activation, so the
script execution policy does not get in the way):

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

(In Git Bash: `py -m venv .venv && source .venv/Scripts/activate`.)

The agent itself uses only the standard library, so `pip install -e .` pulls in nothing
on macOS and Linux. The `dev` extra adds `pytest`. Optional extras exist for features
that need a third-party package: `tray` (Windows and Linux tray icon), `yaml` (a real
YAML parser instead of the built-in fallback), `mcp` (AI assistant integration). Tests
for those features skip themselves when the package is absent, so you do not need them.

Run the agent from a checkout:

```bash
epokio agent                    # HTTP API on 127.0.0.1:8787
epokio watch                    # terminal view
```

## Building the macOS app

Xcode 16 or newer, macOS 15 or newer.

```bash
cd mac
swift build                     # compile check, fastest feedback
./build_app.sh --no-install     # full Epokio.app bundle
```

`build_app.sh` downloads a standalone CPython (pinned version and SHA-256) to embed in
the bundle. Set `EPOKIO_NO_PYTHON=1` to skip that download while iterating on the UI.

To see a screen without running a training job, use the snapshot mode. It takes a
section name and the file to write:

```bash
swift run Epokio --snapshot-window design /tmp/design.png
```

## House rules

Most of these are checked by `tests/test_house_rules.py`, so a pull request that breaks
one fails CI. The two marked "convention" are not enforced by a test yet:

- **400 lines per source file**, Python and Swift alike. Over that, split by feature.
  The target is around 300.
- **No em dash** anywhere: code, comments, docs, UI strings. Use commas, periods,
  parentheses or a line break.
- **Colors by meaning**, not by system name. Use `.good`, `.warn`, `.bad`, `.mixup`,
  `.gold`, `.brand`. `Color.red` and friends are rejected, and so is `.accentColor`.
- **Motion by token**: `Motion.tap/hover/change/progress/appear/celebrate`. Do not invent
  a new duration inline.
- **Fonts through `.font(.role(...))`** (Swift) and the generated CSS variables (web).
  Convention, no test yet.
- Design values live in `design/tokens.json`. `DesignTokens.swift` and `web/tokens.css`
  are generated from it by `python3 tools/design_tokens.py`. Do not hand edit them.
- New HTTP routes go in `src/epokio/api/`, not in `agent.py`.
- The Python translation tables are `src/epokio/locales/*.json`, one set only, loaded by
  `src/epokio/msg.py`. Do not add a translation dict inside a `.py` file. UI strings on the
  Swift side go through `L()` with the English text as the key.

Two more that are conventions rather than tests: user visible text is English first
(translations live in `mac/Resources/*.lproj` and `src/epokio/locales/`), and every new
screen or feature gets its hover, press, appear and value change animations at the same
time it is written. See `docs/DESIGN.md` for the design system.

## Pull requests

1. One topic per pull request. A bug fix and a refactor in the same diff is two pull
   requests.
2. Add or update a test in `tests/` for behavior changes. `pytest -q` must pass, and
   `cd mac && swift build` must pass if you touched Swift.
3. Describe what you changed and why, and say how you verified it. If you could not test
   something (no NVIDIA GPU, no Windows machine, no remote agent), say so plainly, that
   is useful information and not a problem.
4. For anything larger than a bug fix, open an issue first so we can agree on the shape
   before you write it.

New framework support is the easiest place to start: add a class to
`src/epokio/adapters.py` and a fixture under `tests/fixtures/`.

## A note on how releases work

Development happens in a private repository and is published here in version sized
drops, so your commit will usually reappear in the next release commit rather than as an
individual commit. Issues and pull requests opened here are read, applied upstream and
ship in the following release. Attribution in the release notes is kept.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md).

## License

Epokio is MIT licensed. By contributing you agree that your contribution is licensed
under the same terms.
