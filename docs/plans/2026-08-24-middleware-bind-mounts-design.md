# Middleware Bind Mounts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give PostgreSQL, Redis, and MinIO predictable local bind mounts with deployment-only configuration kept outside the application `.env`.

**Architecture:** `deploy/docker-compose-middleware.yml` provides relative default data paths under `deploy/volumes/`. `deploy/.env` overrides those paths and holds middleware startup values; the root `.env` remains the configuration used by directly started application processes. The local and NAS Compose overrides continue to support explicit host paths.

**Tech Stack:** Docker Compose, PostgreSQL 18, Redis 7, MinIO.

---

### Task 1: Define middleware deployment variables

**Files:**
- Create: `deploy/.env.example`
- Modify: `.gitignore`
- Create: `deploy/volumes/.gitkeep`

**Step 1: Define the deployment contract**

Document ports, PostgreSQL credentials and data directory, Redis password and data directory, and MinIO credentials, bucket and data directory in `deploy/.env.example`.

**Step 2: Keep generated state out of Git**

Ignore the contents of `deploy/volumes/` while retaining `.gitkeep`, and rely on the existing `.env` ignore rule for `deploy/.env`.

### Task 2: Make all middleware persistence paths configurable

**Files:**
- Modify: `deploy/docker-compose-middleware.yml`
- Modify: `deploy/docker-compose-local.yml`
- Modify: `deploy/docker-compose-nas.example.yml`

**Step 1: Set relative defaults**

Use `./volumes/postgres`, `./volumes/redis`, and `./volumes/minio` as the Compose defaults, with `POSTGRES_DATA_DIR`, `REDIS_DATA_DIR`, and `MINIO_DATA_DIR` as overrides.

**Step 2: Align local and NAS overrides**

Make local and NAS override files define all three data directories, preserving the established Mac MinIO location for local use.

### Task 3: Document and validate the split

**Files:**
- Modify: `deploy/README.md`
- Modify: `CHANGELOG.md`

**Step 1: Document commands**

Use `--env-file deploy/.env`, distinguish middleware configuration from root application `.env`, and document local/NAS data locations.

**Step 2: Verify resolved Compose configuration**

Run `docker compose config` with the middleware, local, and NAS example configurations. Confirm that all three services resolve to bind mounts and no named data volumes remain.

**Step 3: Commit**

Commit the configuration, documentation, and validation additions together.
