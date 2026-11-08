-- 002_task_name_nocase.sql — nome compito univoco senza distinzione di maiuscole
-- (spec 02, piano 02 D3: il nome è la chiave di /pause, /resume, /delete, /rename)

CREATE UNIQUE INDEX idx_tasks_name_nocase ON tasks(name COLLATE NOCASE);
