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
    budget_mode     TEXT NOT NULL DEFAULT 'observe',
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
