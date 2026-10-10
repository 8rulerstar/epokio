# Uninstall

[Back to README](../README.md)

Quitting the app also stops the helper it started. A helper you started yourself in a terminal keeps running.

1. Quit Epokio and move `Epokio.app` to the Trash.
2. Stop a helper you started yourself: `epokio agent --stop`.
3. Delete the data folder: `rm -rf ~/.epokio` (tokens, queue, inbox, run history, and the Python Epokio downloaded, if any).
   If `~/.trainbar` is still there (the old name), you can delete it too.
4. Delete settings: `defaults delete io.github.8rulerstar.epokio`, and the folder `~/Library/Application Support/Epokio` if it exists.
5. Keychain: open Keychain Access and delete the items named `io.github.8rulerstar.epokio`
   (tokens for remote machines and the TypeSafe key, account `typesafe.api`).
   Or: `security delete-generic-password -s io.github.8rulerstar.epokio` (run it again until it says not found).
6. If you installed Epokio with pip: `pip uninstall epokio`.

**Windows:** `py -m epokio autostart --off`, or `.\Epokio.exe autostart --off` without Python (or delete the Epokio
shortcut in your Startup folder: type `shell:startup` in the Run box). Quit the tray icon, stop the helper
(`py -m epokio agent --stop` or `.\Epokio.exe agent --stop`), delete `Epokio.exe`, then the folder `%USERPROFILE%\.epokio`,
and `py -m pip uninstall epokio` if you used pip.
**Linux:** `epokio autostart --off` (disables and removes the systemd user service, or the tray entry on a Linux without systemd).
Then `epokio agent --stop`, `rm -rf ~/.epokio` and `pip uninstall epokio`.
**macOS with pip:** `epokio autostart --off` removes the LaunchAgent that `setup --autostart` made.
