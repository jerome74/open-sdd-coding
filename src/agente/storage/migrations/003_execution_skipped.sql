-- 003_execution_skipped.sql — esito `saltata` (spec 03, decisione D1 2026-10-24).
-- SQLite non modifica un CHECK: la tabella viene ricostruita e i dati copiati.

CREATE TABLE executions_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    requested_by INTEGER,
    trigger TEXT NOT NULL CHECK (trigger IN ('scheduled', 'manual', 'recovery')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    outcome TEXT CHECK (outcome IN ('ok', 'errore', 'interrotto', 'saltata')),
    summary TEXT
);

INSERT INTO executions_new
    (id, task_id, requested_by, trigger, started_at, finished_at, outcome, summary)
SELECT id, task_id, requested_by, trigger, started_at, finished_at, outcome, summary
FROM executions;

DROP TABLE executions;

ALTER TABLE executions_new RENAME TO executions;

CREATE INDEX idx_executions_task_started ON executions(task_id, started_at);
