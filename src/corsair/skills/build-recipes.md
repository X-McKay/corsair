# Build recipes

The build script runs once in a clean container with network, then the network is removed for every probe run.

| Repository shape | build_script |
| --- | --- |
| Plain modules, stdlib only | *(empty)* |
| `requirements.txt` | `pip install -r requirements.txt` |
| `pyproject.toml` / `setup.py` package | `pip install -e .` (add `.[test]` or `.[dev]` only if the probe imports those extras) |
| Lock file for a tool (poetry, pdm) | `pip install -e .` is usually enough; do not install the tool itself |

Keep it minimal: install only what `run_target` imports. A failing build script is returned to you with its last
output lines; fix the script, not the probe. Never use `--trusted-host`, `--index-url`, `--extra-index-url`, `sudo`,
`curl | sh` or package managers other than `pip`. Do not download or run repository scripts.
