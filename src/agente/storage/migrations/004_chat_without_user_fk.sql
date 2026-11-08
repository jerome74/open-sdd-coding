-- 004_chat_without_user_fk.sql — chat dell'amministratore (spec 05, decisione D2).
-- L'admin è definito in configurazione e non è un record `users` (spec 01): con
-- la FK verso `users` la sua conversazione non potrebbe essere registrata.
-- Le due tabelle non hanno riferimenti entranti, quindi la ricostruzione è
-- sicura anche con `foreign_keys=ON`; dati, id, sequenza e indice sono preservati.

CREATE TABLE conversations_new (
    user_id INTEGER PRIMARY KEY,
    updated_at TEXT NOT NULL
);

INSERT INTO conversations_new (user_id, updated_at)
SELECT user_id, updated_at FROM conversations;

CREATE TABLE messages_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO messages_new (id, user_id, role, content, created_at)
SELECT id, user_id, role, content, created_at FROM messages;

DROP TABLE messages;

DROP TABLE conversations;

ALTER TABLE conversations_new RENAME TO conversations;

ALTER TABLE messages_new RENAME TO messages;

CREATE INDEX idx_messages_user_created ON messages(user_id, created_at);
