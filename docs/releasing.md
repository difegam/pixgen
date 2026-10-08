# Releasing pixgen

Releases are published to PyPI by `.github/workflows/release.yml` when a version
tag is pushed. Publishing uses PyPI trusted publishing (OIDC), so no API token is
stored anywhere.

## One-time setup

1. **Register the trusted publisher on PyPI** with these values:

   | Field             | Value         |
   | ----------------- | ------------- |
   | Owner             | `difegam`     |
   | Repository        | `pixgen`      |
   | Workflow filename | `release.yml` |
   | Environment       | `pypi`        |

   - If `pixgen` has never been published, add a *pending publisher* at
     <https://pypi.org/manage/account/publishing/>. The first successful publish
     creates the project.
   - Otherwise, open the project on PyPI and go to **Manage → Publishing**.
   - The workflow filename is the bare name, not the `.github/workflows/` path.
     The environment name is case-sensitive.

2. **Create the `pypi` environment** in the GitHub repository under
   **Settings → Environments**. Add required reviewers if you want a manual
   approval gate before publishing.

## Cutting a release

```bash
just release patch      # or minor / major: bump, commit, and tag vX.Y.Z
git push origin main vX.Y.Z
```

The workflow runs CI, checks that the tag matches the version in
`pyproject.toml`, builds with `uv build --no-sources`, smoke tests the wheel and
source distribution, then publishes.

## Troubleshooting

### `ModuleNotFoundError` in a smoke test

The wheel or source distribution is tested in a clean environment, so an import
that is not listed in `[project].dependencies` fails there even though it works
locally through a transitive dependency. Declare the package, then reproduce
the check locally:

```bash
uv run --isolated --no-project --with . pixgen --help
```

### Publish fails with 422 "no corresponding publisher"

PyPI accepted the GitHub OIDC token but has no publisher matching its claims.
Compare the publisher entry on PyPI with the table above. A wrong repository,
workflow filename, or environment name all produce this error, as does a missing
`pypi` environment in GitHub.

### Retrying a failed release

- If the build succeeded and only publishing failed, fix the cause and re-run
  the failed jobs from the Actions page. The `dist` artifact is reused.
- If the fix needs a code change, you can move the tag:

  ```bash
  git tag -f vX.Y.Z
  git push --force origin refs/tags/vX.Y.Z
  ```

  Only do this while nothing has been published to PyPI. PyPI versions are
  immutable, so after a successful upload you must bump the version instead.
