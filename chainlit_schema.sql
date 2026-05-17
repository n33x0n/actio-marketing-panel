-- Chainlit Data Layer schema (SQLite-adapted from official Chainlit Postgres schema)
-- https://docs.chainlit.io/data-layers/sqlalchemy
--
-- Adapter notes:
--   UUID    → TEXT (Chainlit generuje UUID strings)
--   JSONB   → TEXT (Chainlit serializes JSON to TEXT)
--   TEXT[]  → TEXT (Chainlit stores comma-joined lub JSON)
--   BOOLEAN → INTEGER (0/1)

CREATE TABLE IF NOT EXISTS users (
    "id"         TEXT PRIMARY KEY,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata"   TEXT NOT NULL DEFAULT '{}',
    "createdAt"  TEXT
);

CREATE TABLE IF NOT EXISTS threads (
    "id"             TEXT PRIMARY KEY,
    "createdAt"      TEXT,
    "name"           TEXT,
    "userId"         TEXT,
    "userIdentifier" TEXT,
    "tags"           TEXT,
    "metadata"       TEXT DEFAULT '{}',
    FOREIGN KEY ("userId") REFERENCES users("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_threads_user ON threads("userId");
CREATE INDEX IF NOT EXISTS idx_threads_created ON threads("createdAt");

CREATE TABLE IF NOT EXISTS steps (
    "id"            TEXT PRIMARY KEY,
    "name"          TEXT NOT NULL,
    "type"          TEXT NOT NULL,
    "threadId"      TEXT NOT NULL,
    "parentId"      TEXT,
    "streaming"     INTEGER NOT NULL DEFAULT 0,
    "waitForAnswer" INTEGER DEFAULT 0,
    "isError"       INTEGER DEFAULT 0,
    "metadata"      TEXT DEFAULT '{}',
    "tags"          TEXT,
    "input"         TEXT,
    "output"        TEXT,
    "createdAt"     TEXT,
    "command"       TEXT,
    "start"         TEXT,
    "end"           TEXT,
    "generation"    TEXT,
    "showInput"    TEXT,
    "language"     TEXT,
    "indent"       INTEGER,
    "defaultOpen"  INTEGER DEFAULT 0,
    "modes"        TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_steps_thread ON steps("threadId");

CREATE TABLE IF NOT EXISTS elements (
    "id"          TEXT PRIMARY KEY,
    "threadId"    TEXT,
    "type"        TEXT,
    "url"         TEXT,
    "chainlitKey" TEXT,
    "name"        TEXT NOT NULL,
    "display"     TEXT,
    "objectKey"   TEXT,
    "size"        TEXT,
    "page"        INTEGER,
    "language"    TEXT,
    "forId"       TEXT,
    "mime"        TEXT,
    "props"       TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_elements_thread ON elements("threadId");

CREATE TABLE IF NOT EXISTS feedbacks (
    "id"       TEXT PRIMARY KEY,
    "forId"    TEXT NOT NULL,
    "threadId" TEXT NOT NULL,
    "value"    INTEGER NOT NULL,
    "comment"  TEXT,
    FOREIGN KEY ("threadId") REFERENCES threads("id") ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedbacks_thread ON feedbacks("threadId");
