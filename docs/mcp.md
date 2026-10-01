# AI assistants (MCP) and plain-word commands

[Back to README](../README.md)

## Use with AI assistants (MCP)

Epokio ships an MCP server, so Claude, ChatGPT or any MCP client can read your runs and queue jobs.

```bash
pip install "epokio[mcp]"
claude mcp add epokio -- epokio-mcp
```

Then ask things like *"How did last night's training go?"* or *"Auto-label this folder with my best model."*

| Look | Do (the tools tell your assistant to ask you first; whether it does is up to the assistant) |
|---|---|
| `list_runs`, `analyze_run`, `system_status`, `queue_status`, `job_log`, `python_envs`, `check_filenames` | `start_training`, `auto_label`, `cancel_job`, `export_report` |

## Commands in plain words (optional)

Turn on **Settings → Assistant** and type what you want in the menu bar: *"retrain coco8 for 100 epochs"*, *"compare coco8 and defect_det"*, *"show me how the bert run did"*. Epokio shows what it understood and waits for you to confirm. It uses [TypeSafe](https://typesafe.ai) Jev with your own API key. It sends the sentence you type and the names of up to 12 recent runs, never images, training data or file paths. Off by default.
