# Developing on HempDB

The local development environment runs Django and its supporting services with Docker Compose using safe development-only credentials.

## Requirements

- Docker Desktop or Docker Engine with Docker Compose
- Git

No application API keys or production secrets are required for the default stack. Internet access is still needed for image downloads and for the application's external map assets, map tiles, and ArcGIS geocoding requests.

## Local Setup

1. Clone the repository.
2. Build and start the stack:

   ```sh
   docker compose up --build
   ```

3. Open the application at <http://localhost:8000>.
4. Open Mailpit at <http://localhost:8025> to inspect locally generated email.

The app waits for Percona Server and Valkey to become healthy and for Mailpit to start, applies pending migrations, and then starts Django's autoreloading development server. Source changes are available immediately through the bind mount; dependency changes require an image rebuild.

The database starts with an empty migrated schema. Create a local administrator when needed:

```sh
docker compose exec app python manage.py createsuperuser
```

## Service Architecture

| Service | Purpose | Host access |
| --- | --- | --- |
| `app` | Django development server and management commands | <http://localhost:8000> |
| `mysql` | Percona Server for MySQL 8.4 LTS application and test databases | `127.0.0.1:3307` by default |
| `valkey` | Django map cache | Compose network only |
| `mailpit` | Captures all development email | <http://localhost:8025> |
| `phpmyadmin` | Optional MySQL administration UI | <http://localhost:8081> |

Percona Server data is stored in the `mysql_data` named volume. Valkey is intentionally disposable because it contains cached data only, and Mailpit messages are not preserved across container replacement.

## phpMyAdmin

phpMyAdmin is disabled by default. Start the full stack with the development tools profile:

```sh
docker compose --profile dev-tools up --build
```

Or start only phpMyAdmin and its Percona Server dependency:

```sh
docker compose --profile dev-tools up phpmyadmin
```

Sign in with the local credentials from `.env.docker`:

- Server: `mysql`
- Username: `hempdb` / Password: `hempdb` (application database only)
- Or `root` / `root` for full administration across all databases

## Django Commands

Run management commands inside the app container:

```sh
docker compose exec app python manage.py makemigrations
docker compose exec app python manage.py migrate
docker compose exec app python manage.py audit_email
```

Pending migrations are also applied automatically whenever the app container starts.

Run the test suite and lint checks with:

```sh
docker compose exec app python manage.py test
docker compose exec app ruff check .
```

The local MySQL-compatible user is allowed to create and remove Django's `test_hempdb` database.

## Configuration and Ports

`.env.docker` is committed because it contains local-only values. Never reuse its credentials outside this Compose stack. Production and preview deployments continue to use platform-managed environment variables based on `.env.example`.

Override published ports or the container user's IDs from the shell when necessary:

```sh
APP_PORT=8001 MYSQL_PORT=3308 MAILPIT_PORT=8026 PHPMYADMIN_PORT=8082 docker compose --profile dev-tools up
APP_UID=$(id -u) APP_GID=$(id -g) docker compose build app
```

The default UID and GID are `1000`. Developers whose host account uses different IDs should rebuild the app image with the second command before creating migrations from inside the container.

## Stopping and Resetting

Stop the stack while preserving Percona Server data:

```sh
docker compose down
```

Remove the stack and permanently delete the local Percona Server volume:

```sh
docker compose down -v
```

The next startup recreates an empty database and reapplies all migrations.

## Dependency and Configuration Changes

- After editing `requirements.txt`, run `docker compose build app` and restart the app service.
- Add production environment variables to `.env.example` and the deployment platform.
- Add safe, local equivalents to `.env.docker` only when the local stack needs them.
- Never place real credentials in `.env.docker` or `compose.yaml`.
