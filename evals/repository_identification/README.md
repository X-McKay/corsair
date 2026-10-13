# Repository-scale identification

SPEC-0038 harness for the identification agent's repository mode. The agent sees the issue, scope, repository identity, root listing and byte budget; the tree arrives through `list_source`, `search_source` and `read_source`. `cases.yaml` holds one JSPWiki smoke case whose accepted targets are evaluator-only metadata.

Both modes need a complete private operator bare repository containing the case commit (for example `git clone --bare https://github.com/apache/jspwiki.git` then `chmod 700`). The harness captures the commit with `GitSource` into `<evidence>/capture/` and refuses an existing evidence path.

```sh
# Deterministic: tree profile and bytes returned by a fixed probe through the real toolset; no model.
PYTHONPATH=src:. uv run --locked python -m evals.repository_identification.evaluate measure \
  --repository /path/to/jspwiki.git --evidence .runs/repository-measure-001

# Local provider: three repeats with selection, budget, unknown-tool and usage checks.
PYTHONPATH=src:. uv run --locked python -m evals.repository_identification.evaluate live \
  --repository /path/to/jspwiki.git --provider-config provider.json --evidence .runs/repository-live-001
```

Evidence holds captured source, native messages and reports; keep it under `.runs/` and never commit it. One case on one repository is a smoke, not qualification.
