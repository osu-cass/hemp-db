# Build Pipeline

This page contains information on the build pipeline for HempDB and is intended for developers.

## GitHub Actions

### CI Workflow

The [Django CI workflow](https://github.com/cmciosu/hemp-db/actions/workflows/migrate-test-lint.yml) is configured by the `migrate-test-lint.yml` file. This workflow runs on PRs opened to main. 

Its purpose is to run migrations on the **CI database**, tests, and the lint check. This workflow must pass before a PR is merged to main. Tests are found in `helloworld/tests.py`.

### Deploy Workflow

The [Django Deploy to Prod workflow](https://github.com/cmciosu/hemp-db/actions/workflows/deploy.yml) is configured by the `deploy.yml` file. This workflow runs on pushes (PR merges) to main.

Its purpose is to run migrations on the **production database** as changes are merged into main and deployed to the production Vercel deployment.

### Pages Workflow

The [pages-build-deployment workflow](https://github.com/cmciosu/hemp-db/actions/workflows/pages/pages-build-deployment) deploys the markdown files in `docs/` to this documentation site.

## Vercel

Vercel runs `build.sh` for the build step. For this to pass, just make sure all dependencies are listed in `requirements.txt` and all versions are correct.

Once the Vercel build passes on a PR, Vercel will create a deployment for the PR. This is a site with your changes. The deployment can be visited by clicking the link highlighted below from the PR.

![EER Diagram](images/vercel_preview.png)

Note that these PR deployments are considered Preview deployments and not a Production deployment. As a result, they will use the `DATABASE_URL` environment variable that is associated with the Preview environment (the development database) on Vercel, not Production.

* The Django CI workflow runs `python manage.py migrate --noinput`.

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
