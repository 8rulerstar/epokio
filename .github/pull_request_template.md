<!-- Thanks for the pull request. CONTRIBUTING.md has the house rules that CI checks. -->

## What this changes

<!-- One or two sentences. Link the issue if there is one: Fixes #123 -->

## Why

<!-- The problem behind the change. If we agreed on an approach in an issue, link it. -->

## How you verified it

- [ ] `pytest -q` passes
- [ ] `cd mac && swift build` passes (if Swift changed)
- [ ] Tried it on a real run folder

<!-- Say what you could not test. Missing a GPU, a Windows machine or a remote agent is
     normal and worth writing down rather than leaving implicit. -->

## House rules

- [ ] No file over 400 lines
- [ ] No em dash anywhere, including comments and UI text
- [ ] Colors, fonts and motion go through the design tokens, not raw system values
- [ ] Generated files (`DesignTokens.swift`, `web/tokens.css`) were regenerated with
      `python3 tools/design_tokens.py`, not hand edited
- [ ] New user visible text is English and goes through `L()` or `msg.py`
