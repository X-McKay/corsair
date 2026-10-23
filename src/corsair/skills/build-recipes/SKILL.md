---
name: build-recipes
description: Prepare the minimum replayable dependencies for a clean runtime. Use when a probe needs packages installed.
---

# Build recipes

The build script runs once in a clean container with network, then the network is removed for every probe run.

| Repository shape | build_script |
| --- | --- |
| Plain modules, stdlib only | *(empty)* |
| `requirements.txt` | `pip install -r requirements.txt` |
| `pyproject.toml` / `setup.py` package | `pip install -e .` (add `.[test]` or `.[dev]` only if the probe imports those extras) |
| Lock file for a tool (poetry, pdm) | `pip install -e .` is usually enough; do not install the tool itself |
| JavaScript with `package-lock.json` | `npm ci --ignore-scripts --no-audit --no-fund` |
| JavaScript without a lockfile | `npm install --ignore-scripts --no-audit --no-fund` (dependency resolution is not pinned) |
| Plain Java source | `mkdir -p /work/.corsair-java/classes && javac -d /work/.corsair-java/classes <sources>` |
| Java Maven wrapper | `./mvnw -DskipTests package`, then copy main classes to `/work/.corsair-java/classes` and required jars to `/work/.corsair-java/lib` |
| Java Gradle wrapper | `./gradlew classes`, then copy main classes and required jars to the same directories |
| Plain Perl modules | *(empty; `/work` is already on `PERL5LIB`)* |
| Perl `cpanfile` | `cpanm --installdeps --notest .` |

Keep it minimal: install only what `run_target` imports. A failing build script is returned to you with its last
output lines; fix the script, not the probe. Never use `--trusted-host`, `--index-url`, `--extra-index-url`, `sudo`,
`curl | sh` or package managers outside the selected runtime's documented recipe. Use only checked-in Maven/Gradle
wrappers. Do not download or run unrelated repository scripts.
