# Contributing

## Development

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_dev.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python script/sync_library.py --check
```

The first commit of this repository is an unmodified copy of core's
`homeassistant/components/iotawatt` and `tests/components/iotawatt` at tag
2026.10.4, so `git diff <first commit> -- custom_components tests` shows every
change made here. Keep that diff small and in core's style.

## Syncing with a new Home Assistant release

Diff `homeassistant/components/iotawatt` and `tests/components/iotawatt` between
the old and new core tags and apply the upstream changes here. Then bump
`hacs.json` `homeassistant` and the `pytest-homeassistant-custom-component` pin
in `requirements_test.txt` (pick the version whose `homeassistant==` requirement
matches the new core version).

HA 2026.11 moves core to `httpx2`: follow core's change in `const.py` and the
tests when moving the base to that release.

## The bundled library

The library is the fork `No-Signal/iotawattpy` (module `iotawattpy_nosignal`),
bundled at `custom_components/iotawatt/iotawattpy_nosignal/`. **Never edit the
bundled copy.** To change the library: change the fork (with tests and a
CHANGELOG entry), tag a new version, push it, then run
`script/sync_library.py --ref <tag>` and commit the result. CI's `--check`
rejects hand edits and `--dev` copies.

While iterating, `script/sync_library.py --dev ../iotawattpy` copies a working
tree; it is marked dirty and cannot be released.

When core bumps `ha-iotawattpy`, merge the matching upstream tag into the fork
(`git fetch upstream --tags && git merge vX.Y.Z`), resolving the rename, then
tag and re-sync. This is **required** before moving the base to HA 2026.11. The
bundled library imports `httpx` and receives HA's HTTP client, so it must follow
upstream's `httpx2` migration. Otherwise the bundle breaks on that release,
because no requirement will pull `httpx` back in.
