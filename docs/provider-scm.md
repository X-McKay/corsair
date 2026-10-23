# Source-control providers

`GitSource.provider` selects one implementation: `git` (the backwards-compatible default), `github`, or `azure_devops`. The application uses only the `SourceControl.acquire()` port. SDKs and credentials are opened lazily, only for an acquisition that is not already cached. These adapters perform source reads, not pull-request, issue, hook, or repository-write operations.

```json
{
  "provider": "github",
  "url": "https://github.com/owner/project",
  "commit": "<exact 40-character commit SHA>",
  "subdir": "src"
}
```

Place that object in a case request's `source` field. Omit `subdir` to investigate the entire source tree. Azure uses `"provider": "azure_devops"` with a canonical `https://dev.azure.com/organization/project/_git/repository` URL. Provider URLs must be HTTPS and cannot contain credentials, queries or fragments.

## GitHub

The native PyGithub adapter verifies `Repository.get_commit(sha)` before obtaining `get_archive_link("zipball", sha)`. Archives requested by commit have stable extracted contents while that commit remains available.[^github-archives] Authentication uses `GITHUB_TOKEN`, then an existing `gh auth token` session; neither is written into cache markers. Enterprise API endpoints are operator-owned configuration through `CORSAIR_GITHUB_API_URL`.

## Azure DevOps

The official `azure-devops` Git client verifies `get_commit()` and requests `get_item_zip()` with `GitVersionDescriptor(version=<sha>, version_type="commit")`, root scope and full recursion. The documented read permission is `vso.code`.[^azure-items] Authentication uses `AZURE_DEVOPS_PAT`; endpoint overrides use `CORSAIR_AZURE_DEVOPS_API_URL`. Missing credentials are an explicit error, not a fallback to generic Git.

**Live Azure DevOps validation is deferred at the user's request (2026-10-23).** The adapter is implemented and exercised through native-SDK contract and archive-safety tests, but no successful authenticated Azure service acquisition is claimed. Anonymous exploratory endpoints redirected to sign-in. Before enabling Azure in production, validate an authorized repository and exact commit with a least-privilege read-only credential.

## Cache and archive boundaries

Acquisitions are bound to the requested immutable commit and published atomically after extraction succeeds. Standard ZIP/tar primitives are bounded to 128 MiB compressed, 10,000 entries and 512 MiB extracted. Traversal, escaping links, duplicate paths, hard links and special files are rejected. Provider archive credentials and signed download URLs must not appear in cache metadata.

Installed SDK pins are `PyGithub==2.10.0`, `azure-devops==7.1.0b4`, `httpx==0.28.1` and `openshell==0.1.5`. SDK and transport ownership, provider-root handling and redirect safety are regression-tested. See [provider integration validation](provider-integrations.md) for the final verified evidence and remaining limitations.

[^github-archives]: [GitHub source-code archive stability](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives).
[^azure-items]: [Azure DevOps Git Items API](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/items/get?view=azure-devops-rest-7.1).

Additional API references: [PyGithub Repository](https://pygithub.readthedocs.io/en/latest/github_objects/Repository.html) and [generated Azure DevOps Git client](https://github.com/microsoft/azure-devops-python-api/blob/dev/azure-devops/azure/devops/released/git/git_client_base.py).
