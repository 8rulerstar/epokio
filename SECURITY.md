# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately through GitHub's
[Report a vulnerability](https://github.com/8rulerstar/epokio/security/advisories/new)
form, which opens a draft advisory only the maintainer can see.

Tell us what you can: the version, what an attacker can do, and how to reproduce it.
Expect a first reply within a week. Epokio is maintained by one person, so a fix may
take longer than that, and the acknowledgement will say what the plan is. When a fix
ships you will be credited in the release notes unless you would rather not be.

## Supported versions

Only the latest release gets fixes. There are no maintained older branches.

## Trust boundary

Most of what Epokio does is "read files and show them", but two parts are worth
understanding before you decide how to run it.

**The agent's token is a key to running code on that machine.** The agent
(`epokio agent`, also started automatically by the macOS app) exposes an HTTP API. Read
requests return run folders, metrics and log files. Write requests queue jobs, and a
job's whole purpose is to start a process: a training command, an evaluation, an export,
or a generated Python script. So whoever holds the token can execute code on the machine
as the user who runs the agent. Treat the token like an SSH key, not like a session
cookie.

How that is contained by default:

- The agent binds **127.0.0.1**. Nothing outside the machine can reach it unless you
  pass `--host 0.0.0.0` yourself.
- The token lives in `~/.epokio/token`, created with owner-only permissions. A token
  file left world readable by an older version is corrected on startup.
- Writes always require the token, including over loopback.
- When the agent is bound to a non-loopback address, reads require the token too. The
  web page itself and `/health` stay open so you have somewhere to enter it.
  `--open-reads` relaxes read requests, and is meant only for a network you trust.
- The browser session cookie is `HttpOnly` and `SameSite=Strict`.
- Tokens for other machines (multi-machine sweeps) are kept **in memory only**. The app
  holds them in the keychain and pushes them to the agent periodically. Restarting the
  agent drops them, and the machine is reported as `needs_tokens` until the app pushes
  them again. Sweep files on disk contain machine addresses and paths, never tokens.

If you expose the agent beyond your own machine, put it on a LAN you control or behind
SSH port forwarding. It is not designed to be a public internet service.

**Run folders and model files are untrusted input.** Epokio parses whatever is in the
folders you point it at: `args.yaml`, CSV metric files, TensorBoard event files, label
files, images. A malformed or hostile file should produce an error, not code execution
or a write outside the run folder. Parsing bugs of that kind are in scope for a report.

**The MCP server is for an AI assistant, and assistants can be talked into things.**
`epokio mcp` marks data that came from run folders as untrusted, clips tool output,
requires confirmation for write tools, and refuses to drive a Python interpreter outside
the environments it knows about. If you find a way around one of those, that is a
report worth sending.

**Updates** are wired through Sparkle 2. The updater only starts when the build carries
both `SUFeedURL` and a `SUPublicEDKey` in its Info.plist, so a build without the public
key never checks for or installs anything, and an appcast that is not signed with the
matching EdDSA key is rejected. No release has shipped yet: signing and notarizing the
DMG are steps in `docs/RELEASE.md` that have not been run, and the downloads currently
available are unsigned local builds.

## Out of scope

- The agent giving its own user access to their own files. That is the feature.
- Anything that needs the token to already be known, unless the point of the report is
  how the token leaked.
- Vulnerabilities in third party components listed in [NOTICE](NOTICE). Report those
  upstream. If Epokio ships an outdated copy of one, that is worth telling us.
