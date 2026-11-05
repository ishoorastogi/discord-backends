# TTKZ Database — Local Development Setup

This guide explains how to run the TTKZ PostgreSQL 17 + pgvector database locally with Docker. You do **not** need to install PostgreSQL or pgvector directly on your computer.

Each developer gets their **own local database and records**. Cloning the repository does not connect you to another developer's database. The Docker image should be pinned to a verified immutable digest in `docker-compose.yml` so teammates use the same published image version.

## Repository layout

```text
discord-backends/
├── db/
│   ├── docker/
│   │   ├── docker-compose.yml
│   │   ├── build-container.sh
│   │   ├── connect-db.sh
│   │   ├── stop-container.sh
│   │   └── reset-db.sh
│   ├── schema.sql
│   ├── .env.example
│   └── .env                 # local only; never commit
└── .gitignore
```

All commands below assume your terminal is in the **repository root** (`discord-backends/`). The scripts resolve their own paths and can also be launched from elsewhere.

## 1. Install Docker

### macOS

1. Download and install Docker Desktop from the official Docker website: https://www.docker.com/products/docker-desktop/
2. Open Docker Desktop and wait until the Docker engine is running.
3. Verify in Terminal:

```bash
docker --version
docker compose version
docker info
```

### Linux (Ubuntu/Debian)

Install Docker Engine and the Docker Compose plugin using the official instructions for your distribution: https://docs.docker.com/engine/install/

After installation, start the Docker service if needed and verify:

```bash
docker --version
docker compose version
docker info
```

If Docker requires `sudo`, follow Docker's official post-installation instructions: https://docs.docker.com/engine/install/linux-postinstall/. Note that membership in the `docker` group grants root-equivalent privileges.

### Windows

Install Docker Desktop with the WSL 2 backend using the official instructions: https://docs.docker.com/desktop/setup/install/windows-install/. Run the scripts from a Bash environment such as WSL, with Docker integration enabled.

## 2. Clone the repository and configure credentials

Clone the TTKZ backend repository using its actual Git remote, then enter its root directory.

Create your local database environment file:

```bash
cp db/.env.example db/.env
```

Edit `db/.env` and set your own values:

```dotenv
POSTGRES_USER=ttkz_user
POSTGRES_PASSWORD=replace_with_a_strong_unique_password
POSTGRES_DB=ttkz_db
POSTGRES_PORT=5432
```

Use the variable names above; your actual values can differ. Avoid leaving placeholder credentials unchanged. Do **not** commit `db/.env`. Make sure `.gitignore` excludes `.env` files (for example, `**/.env`) but permits `.env.example`.

**Important:** PostgreSQL uses `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB` to initialize a *new* database volume. Changing these values in `.env` later does not automatically rename an existing database or change its stored password.

## 3. Check the Docker image version

The Compose file should reference a **verified, pinned** pgvector image digest, not just a moving tag such as `pgvector/pgvector:pg17`. A manifest-list digest is preferred if teammates use both Apple Silicon and x86-64 machines.

Do not substitute a guessed digest. A project maintainer should verify the image and commit the pinned reference to `db/docker/docker-compose.yml`. Everyone should pull that same committed configuration.

## 4. Start and initialize the database

Make the scripts executable if necessary:

```bash
chmod +x db/docker/*.sh
```

Start the database:

```bash
./db/docker/build-container.sh
```

On first initialization, the script should pull the configured image, start PostgreSQL, wait for it to become healthy, and verify pgvector and the five schema tables. The Compose configuration mounts `db/schema.sql` into `/docker-entrypoint-initdb.d/`, so PostgreSQL runs it **only when the data volume is empty**.

Expected tables: `users`, `resumes`, `internships`, `matches`, and `finances`.

The script can be run again to start an existing database without erasing records. A healthy container by itself does not guarantee that schema initialization succeeded; the build script also checks the extension and tables.

## 5. Connect using the terminal

```bash
./db/docker/connect-db.sh
```

This opens the PostgreSQL `psql` client **inside** the running container. Useful commands:

```sql
\dt                 -- list tables
\d users            -- inspect the users table
\di                 -- list indexes
\dx                 -- list extensions
SELECT * FROM users;
\q                  -- leave psql
```

Leaving `psql` with `\q` **does not stop PostgreSQL**. The container keeps running in the background.

## 6. Verify pgvector and schema

In `psql`, run:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

SELECT indexname, indexdef
FROM pg_indexes
WHERE indexname IN ('resumes_vector_idx', 'internships_embedding_idx');

SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector AS cosine_distance;
```

The last query should return `0` (or an equivalent zero value).

## 7. Test an insert and clean up

In `psql`:

```sql
INSERT INTO users (discord_id, name, major, grad_year)
VALUES ('local_test_001', 'Local Test', 'Computer Science', 2027);

SELECT * FROM users WHERE discord_id = 'local_test_001';

DELETE FROM users WHERE discord_id = 'local_test_001';
```

The insert, query, and delete should all succeed.

## 8. Stop and restart without deleting data

Stop PostgreSQL:

```bash
./db/docker/stop-container.sh
```

Start it again:

```bash
./db/docker/build-container.sh
```

**Stopping preserves database records.** `docker compose down` also preserves named volumes by default, but removes the container and network. The `restart: unless-stopped` policy does not normally restart a container you explicitly stopped until you start it again.

## 9. Reset the database (destructive)

```bash
./db/docker/reset-db.sh
```

Read the warning and type `RESET` only if you intend to delete the database's data. This script uses `docker compose down -v`, which **permanently removes the Compose project's named database volume**, then invokes `build-container.sh` to initialize a new one from `schema.sql`.

**Never run this against a database with data you need to keep.** Back up important data first. The SQL schema itself also contains `DROP TABLE` statements, so manually rerunning it on an existing database will destroy table data.

## 10. Inspect container status and logs

From the repository root:

```bash
docker compose --env-file db/.env -f db/docker/docker-compose.yml ps

docker compose --env-file db/.env -f db/docker/docker-compose.yml logs --tail=100 postgres
```

To follow logs live:

```bash
docker compose --env-file db/.env -f db/docker/docker-compose.yml logs -f postgres
```

Press `Ctrl+C` to stop following logs; this does **not** stop the database.

## 11. Troubleshooting

### Docker engine is not running

Start Docker Desktop (macOS/Windows) or the Docker service (Linux), then rerun the build script.

### Port 5432 is already in use

Another PostgreSQL server or container may be using that port. Stop the conflicting service or change `POSTGRES_PORT` in `db/.env` to an unused port such as `5433`, then restart the container configuration.

### `\dt` reports no relations

The database volume may have been initialized before `schema.sql` was mounted. Inspect container logs and verify the schema mount. If there is no data to preserve, use `reset-db.sh`. Otherwise, plan a non-destructive migration; do not blindly rerun the destructive schema.

### `pgvector` is missing

Check that the configured Docker image contains pgvector and that schema initialization completed. Inspect logs for extension or SQL errors.

### Password changes do not work

Changing `POSTGRES_PASSWORD` in `.env` does not update an already-initialized PostgreSQL role. Change the role password with SQL or reset the database **only if data loss is acceptable**.

### Another clone uses the same Docker resources

On the same Docker host, clones with the same Compose project name and `container_name` may target or conflict with the same resources. Use distinct Compose project names and container names if you need independent databases on one machine. Different developers on different computers do not share data automatically.

## 12. Database access and security

The database port is published to `127.0.0.1`, so it is intended for local development, not direct public access. Keep credentials out of Git and use distinct credentials for production.

The current schema grants privileges on several tables to `PUBLIC`. Before deploying or allowing other services to connect, replace these broad grants with dedicated, least-privileged database roles. The `finances` table needs explicit access controls, and API-level authentication and authorization are also required.

## 13. Future TTKZ API integration

The database will primarily be accessed through a **separate TTKZ API layer**, which will serve multiple backend services, including the internship bot. For local development, that API can connect to PostgreSQL at `127.0.0.1:<POSTGRES_PORT>` using a dedicated application role. If the API itself runs in Docker on the same Compose network, it should connect to the service hostname `postgres` on port `5432` instead of `localhost`.

Keep SQL access and connection pooling inside the API's database layer. Backend services should use authenticated API endpoints rather than sharing administrator credentials.

## Quick command reference

```bash
./db/docker/build-container.sh    # initialize/start; preserve existing data
./db/docker/connect-db.sh        # enter psql
./db/docker/stop-container.sh    # stop; preserve data
./db/docker/reset-db.sh         # DELETE data and recreate database
```

---

**Scope:** Local developer setup. This guide does not configure shared production storage, backups, migrations, TLS, or remote database access.
