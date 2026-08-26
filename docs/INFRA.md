# HempDB Infrastructure

This page outlines the infrastructure of the HempDB web app and is intended for developers.

## Website

The website runs as Docker Compose stacks on hosts managed by the OSU Open
Source Lab through the `osl-app` Chef cookbook. Images are published to GitHub
Container Registry at `ghcr.io/osu-cass/hemp-db`: pushes to the `dev` branch
publish the `dev` tag used by staging
(`hemp-db-staging.cass.oregonstate.edu`); pushes to `main` publish `main` and
`latest`, used by production (`hemp-db.cass.oregonstate.edu`). TLS termination
and ingress are handled by OSL-managed HAProxy in front of the
loopback-bound app containers. See [PRODUCTION.md](PRODUCTION.md) for the
deployment stacks and the Chef-owned host responsibilities.

## MySQL Database

The data is stored in a Percona Server for MySQL 8.0 master/master cluster
managed by the OSU Open Source Lab, external to the Compose stacks. The
application connects with the `DATABASE_URL` Docker secret over TLS, verified
against the CA certificate provided by the `database_ca` secret. Local
development runs the same Percona Server 8.0 as a container.

## Cache

The Valkey cache runs as a container inside each deployment stack. It holds
cached data only, is intentionally disposable, and needs no backups.

## Email

Outbound mail goes through the OSL SMTP relay at `smtp.osuosl.org` (port 25,
STARTTLS, no authentication). Staging redirects mail to its bundled Mailpit
instead of the relay.
