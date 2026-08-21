# Build pipeline

This page describes HempDB's GitHub Actions workflows. Docker staging and
production operations are documented in [PRODUCTION.md](PRODUCTION.md).

## GitHub Actions

### CI workflow

The [Django CI workflow](https://github.com/osu-cass/hemp-db/actions/workflows/migrate-test-lint.yml) is configured by `migrate-test-lint.yml`. It runs on pull requests targeting `main` or `dev`.

It builds the development image from `compose.yaml`, runs Ruff, then runs
migrations and the test suite against ephemeral Percona MySQL and Valkey
containers — no external database or repository secrets are involved. The
workflow must pass before a pull request is merged. Tests are in
`helloworld/tests.py` and the `hempdb/tests/` package.

### Container workflow

The `container.yml` workflow has two jobs. `validate` checks the local,
staging, and production Compose configurations, including the build override.
`build` builds the production image; same-repo pull requests publish a
`pr-<number>` tag for pre-merge testing (fork PRs build without publishing),
pushes to `dev` publish the `dev` tag to GitHub Container Registry, and pushes
to `main` publish `main` and `latest`. A weekly scheduled run rebuilds both
branches so published images pick up base-image fixes.

### Pages workflow

The [pages-build-deployment workflow](https://github.com/osu-cass/hemp-db/actions/workflows/pages/pages-build-deployment) deploys the markdown files in `docs/` to this documentation site.

## Migrations

The `helloworld` migrations `0001`–`0017` are squashed into a single migration,
`0001_squashed_0017_pendingchanges_status`. It carries `initial = True` and a
`replaces` list covering all 17 original names, so Django treats it as
interchangeable with the original chain.

* **Fresh database:** run `python manage.py migrate --noinput`. The squashed
  migration builds the whole schema on its own.
* **Existing database already at `0017`:** run `python manage.py migrate
  --noinput`. Django recognizes the replaced history and inserts one
  migration-history row. No DDL runs and no application data changes.
* **Never use `--fake` or `--fake-initial` on `helloworld`.** Because
  `initial = True` now covers all 17 migrations rather than just
  `0001_initial`, faking makes Django skip the entire schema history —
  including `Latitude`/`Longitude`, the `PendingChanges` foreign-key rework,
  `Resources.priority`, `dateCreated`/`lastUpdated`, and
  `PendingChanges.status` — while still recording every row as applied. The
  resulting schema drift is permanent and later `migrate` runs will not detect
  it. This applies to restoring from a backup: restore the data, then let
  `migrate` run normally.
* **New migrations** must depend on
  `0001_squashed_0017_pendingchanges_status`, not on any `00XX` name it
  replaces.

MySQL does not roll back DDL when a migration fails partway through, so a
failed run against a fresh database can leave tables behind with no
migration-history row. Drop and recreate the empty database and retry; do not
fake the migration.
