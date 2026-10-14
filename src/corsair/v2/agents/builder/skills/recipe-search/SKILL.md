---
name: recipe-search
description: How to find a minimal dependency setup and one passing baseline test.
---
# Finding a recipe

**Look before running.** List the working directory and read the manifests and lock files at the root and
around the component under test. The framework guidance names the usual manifest files and commands for this
framework; the repository's own README, CI files and Makefile often show the exact install and test commands.

**Check what is already there.** The image ships a language runtime and pinned test frameworks. Run the
framework's version command first, then try the baseline test before installing anything: some projects
need no setup at all.

**Install as declared.** Use the project's own install command against its lock file or manifest (for
example an install that honours the lock file). Do not name individual packages yourself, do not upgrade,
do not loosen a pin. If an install needs the network, say so in network_during_setup.

**Choose the baseline test.** Pick one existing, fast, self-contained test near the component under test and
run it alone with the framework's run-one-test form. If it fails for reasons unrelated to setup, pick another.
If the project has no tests, use the framework's smoke test.

**When nothing works.** Stop after a few distinct attempts. A recipe is accepted only when its setup commands
and baseline test each exited 0 here; trusted replay then decides whether it holds in a fresh workspace.
