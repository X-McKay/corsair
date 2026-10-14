.PHONY: test test-v2 eval eval-baseline baseline-commit eval-live-baselines canary toolchain-images maven-hashes
export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
# pytest otherwise infers its root from argument paths, so an evidence dir inside another checkout (for example
# the main repository's .runs from a worktree) would load that checkout's config and code.
PYTEST_ROOT := -c $(CURDIR)/pyproject.toml --rootdir=$(CURDIR)

# The offline suite is CPU-bound; pytest-xdist spreads it over the cores. `TEST_WORKERS=0 make test-v2` runs it
# serially. No model, no cluster; Docker-backed tests skip when Docker is unavailable.
TEST_WORKERS ?= auto
test-v2:
	uv run --locked python -m pytest $(PYTEST_ROOT) -n $(TEST_WORKERS) tests

test: test-v2

# One agent's isolated eval suite on the host; results under .runs/evals/<agent>/.
# AGENT=grounding|builder|investigator|control_prober|exploit_prober|reviewer (cases, sets and release policy in
# src/corsair/v2/agents/<agent>/evals/; summary.json, comparison.md and policy.json per run). Optional SET,
# EVAL_LANGUAGE (one language of a per-case set: python|java|javascript|ruby|perl|common), PROVIDER_CONFIG, REPEAT, NOTE.
eval:
	uv run --locked python -m evals.run "$(AGENT)" $(if $(SET),--set "$(SET)") $(if $(EVAL_LANGUAGE),--language "$(EVAL_LANGUAGE)") $(if $(PROVIDER_CONFIG),--provider-config "$(PROVIDER_CONFIG)") $(if $(REPEAT),--repeat "$(REPEAT)") $(if $(NOTE),--note "$(NOTE)")

eval-baseline:
	uv run --locked python -m evals.run "$(AGENT)" --promote "$(RUN)"

# v2: promote RUN and write <agent evals>/baselines/<set>-<mode>.json for committing (whole set, clean checkout).
baseline-commit:
	uv run --locked python -m evals.run "$(AGENT)" --commit-baseline "$(RUN)"

# Live baselines, one agent after another (one live inference user at a time). AGENTS defaults to the six v2
# agents; the chain (AGENTS=chain) also needs Docker. Prints each run id; commit the ones you choose with
# baseline-commit.
eval-live-baselines:
	@test -n "$(PROVIDER_CONFIG)" || { echo "PROVIDER_CONFIG is required"; exit 2; }
	@for agent in $(or $(AGENTS),grounding investigator builder control_prober exploit_prober reviewer); do \
	  uv run --locked python -m evals.run "$$agent" --provider-config "$(PROVIDER_CONFIG)" $(if $(NOTE),--note "$(NOTE)") || true; \
	  tail -n 1 ".runs/evals/$$agent/index.jsonl"; \
	done

# Classify each runtime-matrix row's known-passing and known-failing canary on its image (evidence under .runs/canary/).
canary:
	uv run --locked python tools/v2_canary.py

# Build toolchain images from deploy/qualification/toolchains/<name> and run each one's trusted control; TOOLCHAINS
# limits preparation to the named image directories, e.g. TOOLCHAINS=python37 or TOOLCHAINS="java python".
toolchain-images:
	uv run --locked python tools/toolchain_images.py $(foreach language,$(TOOLCHAINS),--language $(language))

# Refresh each Java image's reviewed Maven cache list (SPEC-0064) from a clean build of its preparation stage, then
# review the diff: the image build fails on any difference from the checked-in list. TOOLCHAINS names the Java images
# (default: both).
maven-hashes:
	for dir in $(or $(TOOLCHAINS),java java8); do \
	  docker --host=unix:///var/run/docker.sock build --no-cache --target cache --tag corsair-m2-$$dir deploy/qualification/toolchains/$$dir \
	  && docker --host=unix:///var/run/docker.sock run --rm --network=none corsair-m2-$$dir cat /opt/corsair-m2.sha256 > deploy/qualification/toolchains/$$dir/m2.sha256.new \
	  && mv deploy/qualification/toolchains/$$dir/m2.sha256.new deploy/qualification/toolchains/$$dir/m2.sha256 \
	  || { rm -f deploy/qualification/toolchains/$$dir/m2.sha256.new; exit 1; }; \
	done
