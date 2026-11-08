-- 005_executions_started_index.sql — istanti uniformi a UTC e indice per la retention
-- (spec 09, BR-7). C-09 scrive UTC, C-19 scrive l'offset locale e C-02 confronta
-- stringhe: senza normalizzazione ordinamento e retention sarebbero errati.

UPDATE executions
SET started_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', started_at)
WHERE datetime(started_at) IS NOT NULL;

UPDATE executions
SET finished_at = strftime('%Y-%m-%dT%H:%M:%S+00:00', finished_at)
WHERE finished_at IS NOT NULL AND datetime(finished_at) IS NOT NULL;

CREATE INDEX idx_executions_started ON executions(started_at);
