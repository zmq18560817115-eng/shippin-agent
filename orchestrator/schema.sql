PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,
    product_id      TEXT,
    source_link_id  INTEGER,
    status          TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN (
                        'queued','running','awaiting_human','succeeded',
                        'failed','blocked','needs_review','cancelled'
                    )),
    budget_cny      REAL NOT NULL DEFAULT 35.0,
    budget_mode     TEXT NOT NULL DEFAULT 'enforce',
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    stage            TEXT NOT NULL,
    agent            TEXT NOT NULL CHECK (agent IN
                      ('collector','analysis','script','storyboard','asset','media','review')),
    task_type        TEXT NOT NULL DEFAULT 'default',
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN (
                        'queued','running','awaiting_human','succeeded',
                        'failed','blocked','needs_review','cancelled'
                     )),
    priority         INTEGER NOT NULL DEFAULT 100,
    attempt          INTEGER NOT NULL DEFAULT 0,
    max_retries      INTEGER NOT NULL DEFAULT 2,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    result_json      TEXT,
    error_json       TEXT,
    lease_owner      TEXT,
    lease_expires_at TEXT,
    heartbeat_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at       TEXT,
    finished_at      TEXT,
    CHECK (attempt >= 0),
    CHECK (max_retries >= 1)
);

CREATE INDEX IF NOT EXISTS idx_tasks_claim
ON tasks(status, priority, created_at, id);

CREATE INDEX IF NOT EXISTS idx_tasks_agent_status
ON tasks(agent, status, task_type);

CREATE INDEX IF NOT EXISTS idx_tasks_lease
ON tasks(status, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_tasks_project_stage
ON tasks(project_id, stage, status);

CREATE TABLE IF NOT EXISTS task_assignments (
    task_id       INTEGER PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    assignee      TEXT NOT NULL,
    assigned_by   TEXT NOT NULL DEFAULT 'admin',
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS cost_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    agent       TEXT,
    tool        TEXT,
    cost_cny    REAL NOT NULL DEFAULT 0.0,
    meta_json   TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_cost_entries_project
ON cost_entries(project_id, created_at);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    task_id     INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    message     TEXT,
    meta_json   TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_events_project
ON events(project_id, created_at);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name    TEXT NOT NULL DEFAULT '',
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('operator','admin')),
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
    onboarding_completed INTEGER NOT NULL DEFAULT 0 CHECK (onboarding_completed IN (0, 1)),
    last_login_at   TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_users_role_status
ON users(role, status, username);

CREATE TABLE IF NOT EXISTS registration_requests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name    TEXT NOT NULL DEFAULT '',
    password_hash   TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    reviewed_at     TEXT,
    reviewed_by     TEXT,
    review_note     TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_registration_requests_status
ON registration_requests(status, requested_at DESC);

CREATE TABLE IF NOT EXISTS collector_schedules (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    enabled             INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
    target_type         TEXT NOT NULL DEFAULT 'keyword',
    provider            TEXT NOT NULL DEFAULT 'auto',
    target              TEXT NOT NULL DEFAULT '',
    limit_count         INTEGER NOT NULL DEFAULT 3 CHECK (limit_count BETWEEN 1 AND 20),
    interval_minutes    INTEGER NOT NULL DEFAULT 60 CHECK (interval_minutes BETWEEN 10 AND 1440),
    product_id          TEXT NOT NULL DEFAULT '便携恒温杯',
    mock                INTEGER NOT NULL DEFAULT 1 CHECK (mock IN (0, 1)),
    status              TEXT NOT NULL DEFAULT 'idle',
    last_started_at     TEXT,
    last_finished_at    TEXT,
    last_message        TEXT NOT NULL DEFAULT '',
    failure_count       INTEGER NOT NULL DEFAULT 0,
    next_run_at         TEXT,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS collection_jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type         TEXT NOT NULL CHECK (target_type IN ('keyword','account','hashtag','trending')),
    provider            TEXT NOT NULL DEFAULT 'auto'
                        CHECK (provider IN ('auto','browser_search','tiktok_api','apify','yt_dlp')),
    target              TEXT NOT NULL DEFAULT '',
    requested_count     INTEGER NOT NULL DEFAULT 10 CHECK (requested_count BETWEEN 1 AND 100),
    product_id          TEXT NOT NULL,
    mock                INTEGER NOT NULL DEFAULT 1 CHECK (mock IN (0, 1)),
    status              TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','paused','succeeded','partial','failed','cancelled')),
    discovered_count    INTEGER NOT NULL DEFAULT 0,
    relevant_count      INTEGER NOT NULL DEFAULT 0,
    downloaded_count    INTEGER NOT NULL DEFAULT 0,
    analyzed_count      INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    attempt             INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
    next_attempt_at     TEXT,
    lease_owner         TEXT,
    lease_expires_at    TEXT,
    heartbeat_at        TEXT,
    error_message       TEXT NOT NULL DEFAULT '',
    created_by          TEXT NOT NULL DEFAULT 'operator',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    started_at          TEXT,
    finished_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_collection_jobs_status
ON collection_jobs(status, created_at);

CREATE TABLE IF NOT EXISTS collection_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER NOT NULL REFERENCES collection_jobs(id) ON DELETE CASCADE,
    source_url          TEXT NOT NULL,
    source_video_id     TEXT,
    title               TEXT NOT NULL DEFAULT '',
    author_name         TEXT NOT NULL DEFAULT '',
    cover_url           TEXT NOT NULL DEFAULT '',
    local_video_path    TEXT,
    local_cover_path    TEXT,
    transcript_path     TEXT,
    breakdown_path      TEXT,
    relevance_score     REAL,
    status              TEXT NOT NULL DEFAULT 'discovered'
                        CHECK (status IN ('discovered','filtered','downloading','downloaded','transcribing','analyzing','ready','failed')),
    error_message       TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(job_id, source_url)
);

CREATE INDEX IF NOT EXISTS idx_collection_items_job_status
ON collection_items(job_id, status, created_at);
