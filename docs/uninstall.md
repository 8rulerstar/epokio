# Uninstall

[Back to README](../README.md)

Quitting the app also stops the helper it started. A helper you started yourself in a terminal keeps running.

1. Quit Epokio and move `Epokio.app` to the Trash.
2. Delete the data folder: `rm -rf ~/.epokio` (tokens, queue, inbox, run history, and the Python Epokio downloaded, if any).
   If `~/.trainbar` is still there (the old name), you can delete it too.
3. Delete settings: `defaults delete io.github.8rulerstar.epokio`, and the folder `~/Library/Application Support/Epokio` if it exists.
4. Keychain: open Keychain Access and delete the items named `io.github.8rulerstar.epokio`
   (tokens for remote machines and the TypeSafe key, account `typesafe.api`).
   Or: `security delete-generic-password -s io.github.8rulerstar.epokio` (run it again until it says not found).
5. If you installed Epokio with pip: `pip uninstall epokio`.

**Windows:** `py -m epokio autostart --off` (or delete the Epokio shortcut in your Startup folder), quit the tray icon,
delete `Epokio.exe`, then the folder `%USERPROFILE%\.epokio`, and `py -m pip uninstall epokio` if you used pip.
**Linux:** `epokio autostart --off` (removes the tray entry); on a server set up with `--autostart`, also
`systemctl --user disable --now epokio` and `rm ~/.config/systemd/user/epokio.service`. Then `rm -rf ~/.epokio` and `pip uninstall epokio`.
