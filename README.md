# deb2repo

> Turn any public Git repository with `.deb` releases into a self-hosted APT repository.

[![Build and publish backend](https://github.com/Brozi/deb2repo/actions/workflows/deploy.yml/badge.svg)](https://github.com/Brozi/deb2repo/actions/workflows/deploy.yml)

`deb2repo` watches GitHub-hosted release assets, downloads matching Debian packages, builds signed APT metadata, and serves the resulting repository through a lightweight Nginx container. It is designed for maintainers who publish `.deb` packages but want a private, self-hosted, or organization-controlled package distribution channel.

> **Project status:** deb2repo is under active development. Review the configuration, security, and operational notes below before exposing an instance to the public internet.

> [!WARNING]
> **Compatibility untested!**  
> `deb2repo` is designed to work with other Git repository hostings, such as Gitlab, Codeberg and similar.
> The compatibility however, is not guaranteed, and is **not** tested. Please report any bugs you might find when using `deb2repo` with
> providers other than Github.

## Contents

- [Features](#features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Quick start with Docker Compose](#quick-start-with-docker-compose)
- [Configuration](#configuration)
- [Managing tracked repositories](#managing-tracked-repositories)
- [Using the generated APT repository](#using-the-generated-apt-repository)
- [HTTP API](#http-api)
- [Repository layout](#repository-layout)
- [Release and package selection](#release-and-package-selection)
- [Local development](#local-development)
- [Operations and maintenance](#operations-and-maintenance)
- [Troubleshooting](#troubleshooting)
- [Security considerations](#security-considerations)
- [Contributing](#contributing)
- [Roadmap ideas](#roadmap-ideas)
- [License](#license)

## Features

- Polls GitHub releases for new package assets.
- Supports tracking multiple upstream repositories and distributions.
- Filters release assets by Debian distribution codename, package name, architecture, and stability keywords.
- Normalizes common architecture names such as `x86_64`, `aarch64`, `armv7`, and `noarch`.
- Generates `Packages` and compressed `Packages.gz` indexes with Debian tooling.
- Generates and GPG-signs APT `Release` metadata.
- Retains a configurable number of package versions per package and architecture.
- Provides a FastAPI administration API for listing, adding, and removing tracked repositories.
- Runs scheduled synchronization every 15 minutes, with endpoints for manual sync and rebuild operations.
- Persists tracking state in SQLite by default.
- Ships with Docker Compose configuration for the backend and an Nginx repository server.
- Publishes the backend container image to GitHub Container Registry through GitHub Actions.

## How it works

1. You register an upstream repository, package name, and target distribution through the API.
2. The scheduler periodically checks the upstream repository for its latest release.
3. Matching `.deb` assets are downloaded into the repository pool.
4. Older packages are pruned according to `KEEP_COUNT`.
5. Debian package indexes are regenerated with `dpkg-scanpackages`.
6. The distribution `Release` file is generated and signed with GPG.
7. Nginx serves the repository files to APT clients.

The backend and repository server are intentionally separate:

- **Backend:** manages polling, downloads, package pruning, metadata generation, signing, and administration.
- **Nginx:** serves the generated repository as static files and exposes the optional repository landing page.

## Architecture

```text
                 +----------------------+
                 |  GitHub releases     |
                 |  containing .deb     |
                 +----------+-----------+
                            |
                            | poll every 15 minutes
                            v
+---------------------------+----------------------------+
| deb2repo backend container                             |
|                                                        |
| FastAPI admin API -> APScheduler -> release poller    |
|                         |                              |
|                         +-> package pool               |
|                         +-> prune old versions        |
|                         +-> build Packages indexes    |
|                         +-> sign Release metadata     |
|                         +-> SQLite state               |
+---------------------------+----------------------------+
                            |
                            | shared read-only volume
                            v
                 +----------+-----------+
                 | Nginx repository    |
                 | server               |
                 +----------+-----------+
                            |
                            v
                    Debian / Ubuntu APT clients
```

## Requirements

### Runtime requirements

The recommended deployment uses Docker and Docker Compose. The backend image requires Debian package tooling and GPG support, including:

- `dpkg-deb`
- `dpkg-scanpackages`
- `apt-ftparchive`
- `gpg`
- `gzip`

### Development requirements

- Python 3.11 or newer 
- A GPG key available to the backend container.
- Docker and Docker Compose for the full integration environment.
- A GitHub token when polling private repositories or when unauthenticated GitHub API limits are insufficient.

## Quick start with Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/Brozi/deb2repo.git
cd deb2repo/server
```

### 2. Prepare persistent directories

```bash
mkdir -p state repo
```

The Compose configuration uses these directories as persistent mounts:

- `./state` stores the SQLite database.
- `./repo` stores the generated APT repository.
- `~/.gnupg` provides the GPG keychain used for signing.

### 3. Create the environment file

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```dotenv
GPG_KEY_ID=YOUR_GPG_KEY_ID
REPO_ORIGIN=deb2repo
```

If the upstream repository is private, or if you expect to make many GitHub API requests, also configure `GITHUB_TOKEN`.

### 4. Verify the signing key

The configured key must be available to the user running Docker and visible inside the container through the `~/.gnupg:/root/.gnupg` mount.

```bash
gpg --list-secret-keys --keyid-format LONG
```

Use the long key ID as `GPG_KEY_ID`.

### 5. Start the services

```bash
docker compose up -d
```

The default ports are:

- `http://localhost:8889` — FastAPI administration API.
- `http://localhost:8888` — generated APT repository served by Nginx.

View logs with:

```bash
docker compose logs -f deb2repo
docker compose logs -f repo-server
```

### 6. Register an upstream repository

For example, to track the `deb2repo` package from the `Brozi/deb2repo` GitHub repository for Ubuntu 24.04 (`noble`):

```bash
curl -X POST http://localhost:8889/api/repos/add \
  -H 'Content-Type: application/json' \
  -d '{
    "host": "github.com",
    "owner": "Brozi",
    "package_name": "deb2repo",
    "distro": "noble"
  }'
```

Trigger an immediate synchronization instead of waiting for the next scheduled cycle:

```bash
curl -X POST http://localhost:8889/api/sync/
```

## Configuration

Configuration is loaded from environment variables and can be provided through `server/.env` or Docker Compose's `env_file` configuration.

| Variable | Default | Description |
| --- | --- | --- |
| `GITHUB_TOKEN` | empty | Optional GitHub access token. Recommended for private repositories and higher API limits. |
| `GPG_KEY_ID` | required | GPG key ID used to sign APT `Release` metadata. |
| `REPO_ORIGIN` | `My Custom Repo` | Repository origin and label written into release metadata. |
| `BASE_REPO_PATH` | `/app/repo` | Root directory of the generated APT repository inside the backend container. |
| `DB_URL` | `sqlite:////app/state/repo_state.db` | SQLAlchemy database URL used for tracking state. |
| `KEEP_COUNT` | `2` | Number of versions retained per package and architecture. Set to `0` to disable pruning. |
| `HOSTED_ARCHS` | `amd64, arm64, i386, all` | Comma-separated architectures accepted from release assets. |
| `KNOWN_CODENAMES` | Debian and Ubuntu codenames | Comma-separated distribution codenames accepted by the poller. |
| `UNSTABLE_KEYWORDS` | `rc,alpha,beta,dev,pre,nightly,test,snapshot` | Comma-separated release keywords treated as unstable and excluded from stable selection. |

Example configuration:

```dotenv
GITHUB_TOKEN=ghp_example
GPG_KEY_ID=0123456789ABCDEF
REPO_ORIGIN=Example Packages
BASE_REPO_PATH=/app/repo
DB_URL=sqlite:////app/state/repo_state.db
KEEP_COUNT=3
HOSTED_ARCHS=amd64,arm64,all
KNOWN_CODENAMES=bookworm,noble
UNSTABLE_KEYWORDS=rc,alpha,beta,dev,nightly
```

### Adding a new distribution codename

A codename must be included in `KNOWN_CODENAMES` before it can be used in an API request. The API also requires distribution names to contain only lowercase letters and numbers.

For example:

```dotenv
KNOWN_CODENAMES=bookworm,noble,trixie
```

Restart the backend after changing environment variables:

```bash
docker compose up -d --force-recreate deb2repo
```

## Managing tracked repositories

### List tracked repositories

```bash
curl http://localhost:8889/api/repos/list
```

### Add a repository

```bash
curl -X POST http://localhost:8889/api/repos/add \
  -H 'Content-Type: application/json' \
  -d '{
    "host": "github.com",
    "owner": "example",
    "package_name": "example-package",
    "distro": "noble"
  }'
```

The same upstream repository can be tracked for multiple distributions. Duplicate registrations for the same host, owner, package, and distribution are rejected.

### Remove a repository

Replace `REPO_ID` with the numeric ID returned by the list or add endpoint:

```bash
curl -X DELETE http://localhost:8889/api/repos/delete/REPO_ID/
```

### Force a synchronization

```bash
curl -X POST http://localhost:8889/api/sync/
```

This queues a normal polling cycle in the background.

### Force a rebuild

```bash
curl -X POST http://localhost:8889/api/rebuild/
```

A rebuild regenerates repository metadata even when no new upstream release is detected. This is useful after changing repository files, signing configuration, or package-retention settings.

## Using the generated APT repository

The example landing page is available at `server/index.html.example`. Copy it to the repository root if you want a browser-friendly installation page:

```bash
cp index.html.example repo/index.html
```

On an APT client, install the repository's public signing key. Replace `REPO_HOST` with the hostname serving the repository:

```bash
sudo apt update
sudo apt install -y curl gnupg
sudo mkdir -p /etc/apt/keyrings

curl -fsSL http://REPO_HOST:8888/repo-key.pub \
  | sudo gpg --dearmor -o /etc/apt/keyrings/deb2repo.gpg
```

Add a source list entry. Replace `noble` with the distribution codename used when registering the upstream repository:

```bash
echo "deb [signed-by=/etc/apt/keyrings/deb2repo.gpg] http://REPO_HOST:8888/ noble main" \
  | sudo tee /etc/apt/sources.list.d/deb2repo.list
```

Then update APT and install a package:

```bash
sudo apt update
sudo apt install PACKAGE_NAME
```

### Publishing the public key

APT clients need the public key corresponding to `GPG_KEY_ID`. Export it into the repository root so Nginx can serve it:

```bash
gpg --armor --export YOUR_GPG_KEY_ID > repo/repo-key.pub
```

Do not publish the private key. Only the ASCII-armored public key belongs in the served repository directory.

> **Production recommendation:** serve the repository over HTTPS and use a trusted certificate. Plain HTTP is suitable only for local testing or a deliberately isolated network.

## HTTP API

The backend exposes the following endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/repos/list` | Return all tracked upstream repositories. |
| `POST` | `/api/repos/add` | Register a repository for polling. |
| `DELETE` | `/api/repos/delete/{repo_id}/` | Stop tracking a repository. |
| `POST` | `/api/sync/` | Queue a normal background polling cycle. |
| `POST` | `/api/rebuild/` | Queue a polling cycle that rebuilds indexes regardless of release changes. |

FastAPI's interactive API documentation is also available at:

- `http://localhost:8889/docs`
- `http://localhost:8889/redoc`

### Add request schema

```json
{
  "host": "github.com",
  "owner": "example",
  "package_name": "example-package",
  "distro": "noble"
}
```

The `distro` field must be lowercase alphanumeric text, such as `bookworm` or `noble`.

> **API security note:** the current administration API does not provide built-in authentication or authorization. Place it behind a private network, firewall, VPN, reverse proxy, or an authentication layer before exposing it beyond a trusted network.

## Repository layout

A generated repository follows the conventional Debian archive structure:

```text
repo/
├── dists/
│   └── <codename>/
│       ├── Release
│       ├── Release.gpg
│       └── main/
│           └── binary-<architecture>/
│               ├── Packages
│               └── Packages.gz
├── pool/
│   └── <codename>/
│       └── main/
│           └── *.deb
├── index.html
└── repo-key.pub
```

The backend uses temporary files and atomic replacements while writing generated metadata to reduce the chance of clients observing incomplete index files.

## Release and package selection

The poller is designed for release assets published by GitHub repositories. It understands common architecture aliases, including:

| Input aliases | APT architecture |
| --- | --- |
| `noarch`, `universal`, `all` | `all` |
| `x86_64`, `amd64`, `x64`, `64bit` | `amd64` |
| `x86_32`, `i386`, `i486`, `i586`, `i686`, `32bit`, `x86` | `i386` |
| `aarch64`, `arm64`, `armv8` | `arm64` |
| `armhf`, `armv7l`, `armv7` | `armhf` |
| `armel`, `armv6l`, `armv6` | `armel` |
| `riscv64`, `rv64` | `riscv64` |
| `ppc64le`, `ppc64el` | `ppc64el` |
| `s390x` | `s390x` |
| `mips64le`, `mips64el` | `mips64el` |

Release assets containing configured unstable keywords such as `rc`, `alpha`, `beta`, `nightly`, or `snapshot` are excluded by default. Adjust `UNSTABLE_KEYWORDS` if your release naming convention differs.

Package retention is controlled by `KEEP_COUNT`. For example, `KEEP_COUNT=2` keeps the two newest versions for each package and architecture, while `KEEP_COUNT=0` disables garbage collection.

## Local development

### Server

```bash
cd server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set `GPG_KEY_ID` and ensure the required Debian tools are installed on your development machine. Start the FastAPI application with:

```bash
uvicorn deb2repo_server.main:app --reload --host 127.0.0.1 --port 8000
```

The server package is configured for Python 3.11 or newer.

### Client package

The repository also contains a `deb2repo-client` Python package with a `repo-cli` console entry point. Its package metadata targets Python 3.10 or newer:

```bash
cd client
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .
```

The client package is intended to provide a CLI/SDK interface to the server. Refer to the package source and `repo-cli --help` for the currently implemented commands.

### Code quality and tests

Before opening a pull request, run the checks available in the repository and verify the full Docker Compose flow locally. Contributions should add or update tests when changing polling, package selection, metadata generation, persistence, or API behavior.

## Operations and maintenance

### Backups

Back up both of these locations:

- `server/state/` — tracked repository state and last-seen release tags.
- `server/repo/` — downloaded packages, generated indexes, signatures, and the public key.

Example:

```bash
tar -czf deb2repo-backup-$(date +%F).tar.gz state repo
```

### Updating the backend

The default Compose file uses the published image:

```yaml
image: ghcr.io/brozi/deb2repo:latest
```

Pull and restart it with:

```bash
docker compose pull deb2repo
docker compose up -d deb2repo
```

For reproducible production deployments, prefer pinning a version tag or image digest rather than relying on `latest`.

### Monitoring

At minimum, monitor:

- Backend container logs.
- Nginx access and error logs.
- Available disk space under `repo/`.
- GPG signing failures.
- Failed package downloads.
- APT client errors after repository updates.

### Disk usage

Package retention limits reduce growth but do not replace capacity monitoring. Set `KEEP_COUNT` based on rollback requirements and periodically inspect the size of the repository pool:

```bash
du -sh repo/pool repo/dists state
```

## Troubleshooting

### No packages are downloaded

1. Confirm the tracked repository exists and is spelled correctly.
2. Check that `GITHUB_TOKEN` is available when required.
3. Confirm the release contains `.deb` assets.
4. Check that the asset architecture is included in `HOSTED_ARCHS`.
5. Confirm the release asset matches the configured distribution codename.
6. Inspect backend logs:

```bash
docker compose logs --tail=200 deb2repo
```

### APT reports `NO_PUBKEY`

Export the public key to `repo/repo-key.pub`, install it into the client keyring, and verify that the key matches the private key configured by `GPG_KEY_ID`.

### APT reports missing or stale package indexes

Force a rebuild and inspect the generated files:

```bash
curl -X POST http://localhost:8889/api/rebuild/
find repo/dists -type f -maxdepth 5 -print
```

Also verify that Nginx is serving the same `repo/` directory mounted by the backend.

### Signing fails

Check that:

- `GPG_KEY_ID` is correct.
- The secret key exists inside the backend container.
- The mounted GPG home is readable by the container process.
- The key is not expired or revoked.
- The container has permission to create temporary signature files.

### The administration API is unreachable

Check that port `8889` is published, the container is running, and the application is listening on port `8000` inside the container:

```bash
docker compose ps
docker compose logs --tail=200 deb2repo
```

## Security considerations

- Treat `GITHUB_TOKEN` as a secret. Never commit it to the repository or expose it through logs.
- Protect the GPG private key and restrict access to the host's GPG home.
- Do not expose the unauthenticated administration API directly to the public internet.
- Serve APT metadata and packages over HTTPS in production.
- Consider putting Nginx behind a TLS-terminating reverse proxy with access controls.
- Pin container image versions or digests for production deployments.
- Review upstream release assets before allowing them into a trusted package source.
- Keep the host, Docker engine, Python dependencies, Nginx image, and Debian tooling patched.
- Back up the repository and SQLite state before upgrades or configuration changes.

## Contributing

Contributions are welcome. A good contribution should:

1. Explain the problem and proposed behavior change.
2. Include focused tests or reproducible validation steps.
3. Preserve backward compatibility where practical.
4. Update documentation and examples when configuration or API behavior changes.
5. Avoid committing credentials, private keys, generated package repositories, or local state.

Suggested workflow:

```bash
git checkout -b feature/describe-your-change
# make and test your changes
git add .
git commit -m "Describe the change"
git push -u origin feature/describe-your-change
```

Then open a pull request with:

- A concise summary.
- Implementation details.
- Test commands and results.
- Operational or migration notes, if applicable.

Please use GitHub Issues for bug reports and feature requests. Include relevant logs, configuration details with secrets removed, distribution codename, architecture, and reproduction steps.

## Roadmap ideas

Potential future improvements include:

## Roadmap ideas

Potential future improvements include:

- [x] Authentication and authorization for the administration API.
- [ ] HTTPS and repository access-control guidance built into the deployment examples.
- [ ] Support for GitLab, Gitea, and generic release feeds.
- [ ] Webhook-triggered synchronization in addition to polling.
- [ ] Native `InRelease` generation and stronger repository metadata validation.
- [ ] Health, readiness, and metrics endpoints.
- [ ] Structured logging and retry/backoff handling.
- [ ] Automated database migrations.
- [ ] Multi-tenant repository namespaces.
- [ ] Published, versioned client releases and documented CLI commands.
- [ ] Automated unit, integration, and container smoke tests.

## License

This project is licensed under the [MIT](LICENSE) license.

## Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com/) for the administration API.
- [APScheduler](https://apscheduler.readthedocs.io/) for scheduled polling.
- [SQLAlchemy](https://www.sqlalchemy.org/) for persistence.
- [Nginx](https://nginx.org/) for static repository hosting.
- Debian APT tooling, including `dpkg-scanpackages` and `apt-ftparchive`, for repository metadata generation.
