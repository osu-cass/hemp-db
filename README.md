# HempDB

![](https://github.com/osu-cass/hemp-db/actions/workflows/migrate-test-lint.yml/badge.svg)
![](https://github.com/osu-cass/hemp-db/actions/workflows/container.yml/badge.svg)

This repository hosts all code and documentation for the HempDB Senior Capstone Project, CS46X at Oregon State University.

## Contents
- [Project Identity](#project-identity)
- [Value Proposition](#value-proposition)
- [Technical Implementation](#technical-implementation)
- [Local Development](#local-development)
- [Access and Usage](#access-and-usage)
- [Service Architecture](#service-architecture)

## Project Identity

This web application is intended to aid the Oregon State University Center for Marketing and Consumer Insights in performing market research in the hemp industry. This research is supported by **USDA AFRI SAS Grant# 2021-68012-35957**. To learn more about the project, visit the [About Us](https://hempdb.cass.oregonstate.edu/about/) page.

### People

Dr. Johnny Chen, CMCI - *Project Partner* \
Cherish Despain, CMCI - *Research Assistant*

**2024-25 Software Team**
- Cameron Canfield - *Deployment Lead*
- Colton Melhase - *Product Manager*
- Joshua Henninger - *Backend Lead*
- Mason Rosenau - *Project Manager*
- Stryder Garrett - *Frontend Lead*
- Tanner Choy - *Infrastructure Researcher*

**2023-24 Software Team**
- Dylan Meithof
- Gabriele Falchini
- Paul Lipp
- Zachary Smith

### Project Status

The development of HempDB has gone through two iterations of the Oregon State University Senior Capstone Project, and it is expected to go through one more iteration during the 2025-2026 school year.

## Value Proposition

Previously, collation of industrial hemp companies and stakeholders was done using a shared spreadsheet. This solution was difficult to manage, prone to errors, and had no auditing or tracking to ensure data integrity. These issues, along with the magnitude of the data, led to the creation of HempDB.

### Features and Benefits

HempDB uses a relational database to store and model company data. It helps
researchers manage the repository and share their research publicly. User roles
and permissions, change approvals, geographic visualizations, and audit tools
support data integrity and market research beyond a shared spreadsheet.

#### Permissions

HempDB allows site administrators to customize the permissions of users and groups on the site. These groups and permissions dictate the pages each user can view and the actions they can perform. This approach has introduced the public-facing aspect of HempDB and contributes to the security of the data.

![groups and users](docs/images/groups_and_users.png)

Above is the Django administration portal, where site administrators can easily delegate permissions to users and groups.

For more information, see [Users, Groups, and Permissions](docs/ADMIN.md#users-groups-and-permissions).

#### Data Integrity

HempDB allows users and researchers to edit company data on the site. In order to ensure all changes are accurate and necessary, these changes go through a transaction approval process. Changes, whether they are edits, deletions, or creations, must be viewed and approved by an administrator.

![pending changes](docs/images/pending_changes.png)

Above is the pending changes page where site administrators can review changes submitted to companies.

In addition to this transaction approval process that ensures the accuracy of data, HempDB also features an auditing functionality to flag database entries that are incomplete. These features contribute to the goal of HempDB being an accurate, complete, and up-to-date source of data centralized around the industrial hemp industry.

For more information, see [Transaction Approvals](docs/ADMIN.md#transaction-approvals) and [Auditing Database Entries](docs/AUDIT.md#auditing-database-entries).

#### Data Insights and Visualization

HempDB allows users to filter companies in the database by any of their attributes. Users can also export data, filtered or in its entirety, to spreadsheets for other research needs.

In addition to filtering and exporting, insights into the industry can be made geographically with the company map.

![company map](docs/images/map.png)

Above is the HempDB map that allows anyone to filter companies by any of their attributes and displays markers in heatmaps to see regional trends and density.

### Target Audience

HempDB aims to bring visibility to the industrial hemp industry. As a result, the target audience is individuals performing research in the industry, along with the general population.

## Technical Implementation

| Technology                                                                                             | Description                                                                                                                                                                         | HempDB Documentation                                                                                       |
|:------------------------------------------------------------------------------------------------------:|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| [![Django](https://skillicons.dev/icons?i=django)](https://www.djangoproject.com/)                     | The frontend and backend of HempDB are constructed using Django. Django has templated frontend interfaces, backend logic written in Python, and more features that HempDB utilizes. | [File Structure](docs/FILES.md), [Django Admin Portal](docs/ADMIN.md#user-management-django-admin-portal ) |
| [![MySQL](https://skillicons.dev/icons?i=mysql)](https://www.mysql.com/)                               | HempDB uses MySQL to store all of its data. This is the backbone of the application, and it allows for more complex relational data.                                                | [Models](docs/MODELS.md), [MySQL Database](docs/INFRA.md#mysql-database)                                   |
| [![Docker](https://skillicons.dev/icons?i=docker)](https://www.docker.com/)                            | HempDB is deployed as Docker Compose stacks from images published to GitHub Container Registry.                                                                                     | [Production Deployment](docs/PRODUCTION.md), [Website](docs/INFRA.md#website)                              |
| [![GitHub Actions](https://skillicons.dev/icons?i=githubactions)](https://github.com/features/actions) | GitHub Actions hosts workflows like continuous integration testing and deploying the documentation site.                                                                            | [GitHub Actions](docs/BUILD.md#github-actions)                                                             |

More technical information, including architecture, local development, and feature documentation, can be found in the [Developer Documentation](https://osu-cass.github.io/hemp-db/) (sourced from the [`docs/`](docs/) directory).

## Local Development

The local development environment runs Django and its supporting services with Docker Compose. The default stack includes the Django app, Percona Server for MySQL 8.0 (matching production), Valkey, and Mailpit. It uses safe local credentials. The first run starts with an empty database and applies migrations automatically.

Build and start the default stack:

```sh
docker compose up --build
```

- HempDB: <http://localhost:8000>
- Mailpit: <http://localhost:8025>
- Percona Server for MySQL: `127.0.0.1:3307`

phpMyAdmin is available through the optional `dev-tools` profile:

```sh
# Start only phpMyAdmin and its Percona Server dependency
docker compose --profile dev-tools up phpmyadmin

# Start the full stack with phpMyAdmin
docker compose --profile dev-tools up --build
```

Open phpMyAdmin at <http://localhost:8081>. No production database, Gmail, or Sentry credentials are required for local development. See [Developing on HempDB](docs/DEVELOP.md) for management commands, configuration overrides, and database reset instructions.

## Access and Usage

- See [DEVELOP.md](docs/DEVELOP.md) for local setup, development commands, and configuration overrides.
- See [PRODUCTION.md](docs/PRODUCTION.md) for production container configuration and deployment operations.
- User guides for public users and administrators are located in [USER.md](docs/USER.md) and [ADMIN.md](docs/ADMIN.md) respectively.
- To submit a bug report or feature request, please create a new issue [here](https://github.com/osu-cass/hemp-db/issues).

## Service Architecture

These diagrams use blue for Docker-managed services, green for external
services, and dashed edges for optional services or paths.

### Development: `compose.yaml`

<details>
<summary>
Expand this dropdown to see the local service architecture.
</summary>

```mermaid
flowchart LR
    subgraph docker["Docker-managed: local development"]
        app[Django app]
        mysql["Percona MySQL 8.0"]
        valkey[Valkey]
        mailpit["Mailpit<br/>SMTP 1025 / UI 8025"]
        phpmyadmin["phpMyAdmin<br/>dev-tools profile"]
    end

    subgraph external["External services used by the app"]
        maps["Map APIs and tiles"]
        cdn["Fonts and CDN assets"]
    end

    mysql --> app
    valkey --> app
    mailpit --> app
    phpmyadmin -. "optional admin UI" .-> mysql
    maps --> app
    cdn --> app

    classDef externalService fill:#111,stroke:#28a745,color:#28a745,stroke-width:2px
    classDef dockerService fill:#111,stroke:#3fa7ff,color:#3fa7ff,stroke-width:2px
    class maps,cdn externalService
    class app,mysql,valkey,mailpit,phpmyadmin dockerService
```

</details>

### Staging: `compose.deploy.yaml` + `compose.staging.yaml`

<details>
<summary>
Expand this dropdown to see the staging service architecture.
</summary>

```mermaid
flowchart LR
    subgraph docker["Docker-managed: published production image"]
        migrate["migrate<br/>one-shot gate"]
        app["Django + Gunicorn<br/>published image (dev)"]
        cron["cron<br/>operations profile"]
        valkey["Valkey cache"]
        mailpit["Mailpit<br/>staging overlay"]
    end

    subgraph external["External services"]
        mysql[MySQL]
        sentry[Sentry]
        ingress["Existing HTTPS ingress"]
    end

    migrate --> app
    migrate --> cron
    app --> mysql
    app --> valkey
    app --> mailpit
    cron --> mailpit
    app --> sentry
    ingress --> app

    classDef externalService fill:#111,stroke:#28a745,color:#28a745,stroke-width:2px
    classDef dockerService fill:#111,stroke:#3fa7ff,color:#3fa7ff,stroke-width:2px
    class mysql,sentry,ingress externalService
    class migrate,app,cron,valkey,mailpit dockerService
```

</details>

Mailpit is staging-only; its web UI is published through the load balancer
and protected with the basic-auth credentials in `MAILPIT_UI_AUTH`. Staging
has no phpMyAdmin and does not mount a production SMTP secret.

### Production: `compose.deploy.yaml` + `compose.prod.yaml`

<details>
<summary>
Expand this dropdown to see the production service architecture.
</summary>

```mermaid
flowchart LR
    subgraph docker["Docker-managed: published production image"]
        migrate["migrate<br/>one-shot gate"]
        app["Django + Gunicorn<br/>published image (latest)"]
        cron["cron<br/>operations profile"]
        valkey["Valkey cache"]
    end

    subgraph external["External services"]
        mysql[MySQL]
        smtp[SMTP]
        sentry[Sentry]
        ingress["Existing HTTPS ingress"]
    end

    migrate --> app
    migrate --> cron
    app --> mysql
    app --> valkey
    app --> smtp
    app --> sentry
    ingress --> app

    classDef externalService fill:#111,stroke:#28a745,color:#28a745,stroke-width:2px
    classDef dockerService fill:#111,stroke:#3fa7ff,color:#3fa7ff,stroke-width:2px
    class mysql,smtp,sentry,ingress externalService
    class migrate,app,cron,valkey dockerService
```

</details>

Production runs no Mailpit, phpMyAdmin, or MySQL containers; Valkey runs inside the stack as a disposable cache. The
environment commands and secret contract are in
[Deploying HempDB with Docker Compose](docs/PRODUCTION.md).
