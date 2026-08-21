# Deploying HempDB with Docker Compose

Use this page to configure and run the staging and production Compose stacks.
See [DEVELOP.md](DEVELOP.md) for local development. Compose does not define
host TLS or ingress; it runs Django, Gunicorn, Valkey, migrations, and the
optional cron job. Staging and production hosts are managed by the OSU Open
Source Lab through the `osl-app` Chef cookbook, which owns the repository
checkout, the `.env` file, the secret files, and the deploy runs described
below.

## Compose files

| File | Role | Docker-managed services |
| --- | --- | --- |
| `compose.yaml` | Local development | Django, Percona MySQL, Valkey, Mailpit; optional phpMyAdmin |
| `compose.deploy.yaml` | Shared deployment base | Migration gate, Django production image, Valkey cache, optional cron |
| `compose.prod.yaml` | Production overlay | Production project name and env wiring |
| `compose.staging.yaml` | Staging overlay | Staging project name and loopback Mailpit |
| `compose.build.yaml` | Local build override | Builds and tags `hempdb:local-production` |

The deployment base has no `build:` section. Production defaults to
`ghcr.io/osu-cass/hemp-db:latest` and staging to `ghcr.io/osu-cass/hemp-db:dev`;
set `HEMPDB_IMAGE` only to pin or override. The `operations` profile keeps cron out of
the normal web stack. phpMyAdmin exists only in the local `dev-tools` profile,
and Mailpit exists only in local development or staging.

Compose resolves relative paths from the first file in each command, so run
the commands from the repository root and keep the file order shown below.

## Environment and secrets

Each deployment host has its own checkout with a single `.env` file that
Compose loads automatically — no `--env-file` flag is needed. Copy the
matching example to create it:

```sh
cp .env.production.example .env   # or .env.staging.example on staging
chmod 600 .env
```

Set these values in `.env`:

- production: `PRODUCTION_URL` and the three secret paths;
- staging: the same, with the staging hostname;
- both environments: optional `SENTRY_DSN` and an optional `HEMPDB_IMAGE`
  override of the default branch tag.

`PRODUCTION_URL` is a hostname without a scheme. When the related variables
are not overridden, Django derives `ALLOWED_HOSTS`, the HTTPS CSRF origin, and
the email link from it.

Email goes through the OSL SMTP relay (`smtp.osuosl.org`, port 25, STARTTLS,
no authentication), so there is no SMTP credential anywhere in the stack.
Staging overrides mail delivery to its bundled Mailpit instead.

### `env_file` and Docker secrets

Compose uses two environment mechanisms for deployment. The overlays attach
`.env` with `env_file` to `migrate`, `app`, and `cron`. The file carries
non-secret runtime and deployment configuration, including paths to secret
source files, and also supplies the values Compose interpolates into image
names, hostnames, and secret source paths.

Compose `secrets` are different: Compose reads each configured host file and
mounts it as a read-only file under `/run/secrets/` only into services that list
that secret. Secret contents do not automatically become environment
variables. The shared deployment base maps these settings:

| Environment variable | Mounted file |
| --- | --- |
| `SECRET_KEY_FILE` | `/run/secrets/django_secret_key` |
| `DATABASE_URL_FILE` | `/run/secrets/database_url` |
| `MYSQL_ATTR_SSL_CA` | `/run/secrets/database_ca` |

Django reads the `*_FILE` values through its secret-aware settings helper, and
uses the CA path for verified MySQL TLS. `REDIS_URL` is not a secret: it
points at the Valkey container inside the stack (`redis://valkey:6379/0`). Do
not put secret contents in an env file.

| Secret | Purpose |
| --- | --- |
| `secret_key` | Django signing key |
| `database_url` | Complete external MySQL URL |
| `database_ca` | CA certificate for MySQL hostname verification |

Chef writes the secret files into `docker/secrets/` inside the checkout with
`0400` permissions owned by the container user. To stage them by hand:

```sh
mkdir -p docker/secrets
chmod 700 docker/secrets
# create docker/secrets/{secret_key,database_url,database_ca}, then:
chmod 400 docker/secrets/*
```

### Defaults and optional tuning

Stable deployment values are kept out of the example files. The production
overlay binds the app to loopback port `8000`; it and the shared base default
to `DEBUG=false`, verified database TLS, secure cookies, HTTPS proxy handling,
HSTS settings, and an audit log directory at
`/var/lib/hempdb/auditlogs`. Staging fixes its loopback app port at `8001` and
Mailpit UI port at `8025`.

These variables are optional overrides:

- `APP_CPUS=1.0`, `APP_MEMORY_LIMIT=1g`, and `APP_PIDS_LIMIT=256` are Compose
  resource defaults;
- `LOG_MAX_SIZE=10m` and `LOG_MAX_FILE=5` are Compose log-rotation defaults;
- `GUNICORN_WORKERS`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`,
  `GUNICORN_GRACEFUL_TIMEOUT`, and `GUNICORN_KEEPALIVE` override the defaults
  in `gunicorn.conf.py`;
- `DATABASE_CONN_MAX_AGE`, `DATABASE_CONN_HEALTH_CHECKS`, and Sentry's
  `SENTRY_TRACES_SAMPLE_RATE` / `SENTRY_PROFILES_SAMPLE_RATE` override Django
  defaults;
- `DEFAULT_FROM_EMAIL`, `AUDIT_RECIPIENT`, and `CSP_REPORT_URI` are optional
  application overrides;
- `SENTRY_DSN` enables the SDK. The matching overlay sets
  `SENTRY_ENVIRONMENT` to `development`, `staging`, or `production`.

Set overrides deliberately and run `docker compose ... config` after making
changes.

## Staging

Staging (`hemp-db-staging.cass.oregonstate.edu`) tracks
`ghcr.io/osu-cass/hemp-db:dev`, published on every push to `dev`. Deploying
means pulling the refreshed tag and restarting the stack; Chef does this on
its regular runs when the image or configuration changes. The overlay adds
Mailpit, whose web UI binds to loopback:

```sh
docker compose -f compose.deploy.yaml -f compose.staging.yaml config --quiet
docker compose -f compose.deploy.yaml -f compose.staging.yaml pull
docker compose -f compose.deploy.yaml -f compose.staging.yaml up --detach --wait
```

The app and cron containers use `mailpit:1025` with TLS and credentials
disabled. The staging Mailpit UI is reachable only from the host at
<http://127.0.0.1:8025> until an ingress/access path is agreed.

## Production

Production (`hemp-db.cass.oregonstate.edu`) tracks
`ghcr.io/osu-cass/hemp-db:latest`, published on every push to `main`. Set
`HEMPDB_IMAGE` in `.env` only to pin a specific tag, such as for a rollback.
Validate and start the production overlay:

```sh
docker compose -f compose.deploy.yaml -f compose.prod.yaml config --quiet
docker compose -f compose.deploy.yaml -f compose.prod.yaml pull
docker compose -f compose.deploy.yaml -f compose.prod.yaml up --detach --wait
```

The one-shot `migrate` service must complete before `app` starts. Static files
are collected into the image at build time and served by WhiteNoise. Valkey
runs inside the stack as a disposable cache. MySQL, SMTP, Sentry, TLS
termination, ingress, and backups remain external to this Compose project.
Mailpit and phpMyAdmin are absent.

Run the optional cron job after the migration gate completes. Explicitly
targeting the service activates its `operations` profile, so no `--profile`
flag is needed:

```sh
docker compose -f compose.deploy.yaml -f compose.prod.yaml run --rm --no-deps cron
```

Use one external scheduler, such as a Chef-managed host crontab entry:

```crontab
0 3 * * * cd /path/to/hemp-db && docker compose -f compose.deploy.yaml -f compose.prod.yaml run --rm --no-deps cron
```

Do not schedule the job independently in each web replica. Audit CSVs are
stored in the `audit_logs` named volume and attached to the notification
email.

## Build validation

Use the build override to validate a local production image. It tags the
result `hempdb:local-production`, so it never overwrites a pulled published
image:

```sh
docker compose -f compose.deploy.yaml -f compose.prod.yaml -f compose.build.yaml config --quiet
docker compose -f compose.deploy.yaml -f compose.prod.yaml -f compose.build.yaml build app
```

Same-repo pull requests publish a `pr-<number>` tag for pre-merge testing;
fork PRs build without publishing. Pushes to `dev` publish the `dev` tag;
pushes to `main` publish `main` and `latest`. A weekly scheduled workflow
rebuilds both branches so published images pick up base-image fixes.

## Host responsibilities (Chef)

The staging and production hosts are managed by the `osl-app` Chef cookbook,
which owns everything outside this repository:

- the repository checkout and its `.env` file (templated from Chef data);
- the secret files under `docker/secrets/`;
- pulling published images and running `up --detach --wait` on chef-client
  runs when the image or configuration changes;
- TLS termination and ingress through OSL-managed HAProxy (the app binds to
  loopback only);
- the cron schedule (host crontab running the command above);
- the external MySQL cluster and its backups.
