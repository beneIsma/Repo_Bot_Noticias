-- ═══════════════════════════════════════════════════════
-- Tech Digest Bot — Schema para Supabase
-- Ejecuta esto en: Supabase Dashboard → SQL Editor
-- ═══════════════════════════════════════════════════════

-- FUENTES DE NOTICIAS
CREATE TABLE IF NOT EXISTS sources (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    url         TEXT NOT NULL,
    category    TEXT NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    added_at    TIMESTAMPTZ DEFAULT NOW(),
    last_fetch  TIMESTAMPTZ
);

-- NOTICIAS RECOPILADAS
CREATE TABLE IF NOT EXISTS news (
    id           BIGSERIAL PRIMARY KEY,
    title        TEXT NOT NULL,
    url          TEXT,
    source       TEXT NOT NULL,
    category     TEXT NOT NULL,
    summary      TEXT,
    status       TEXT DEFAULT 'pending',
    approved     BOOLEAN DEFAULT FALSE,
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    approved_at  TIMESTAMPTZ,
    sent_at      TIMESTAMPTZ
);

-- CONFIGURACIÓN DEL BOT
CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- LOGS DEL SISTEMA
CREATE TABLE IF NOT EXISTS logs (
    id        BIGSERIAL PRIMARY KEY,
    level     TEXT NOT NULL,
    message   TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- URLS YA ENVIADAS (deduplicación visual bot)
CREATE TABLE IF NOT EXISTS sent_items (
    url     TEXT PRIMARY KEY,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- CACHE HANDLES YOUTUBE → CHANNEL IDS
CREATE TABLE IF NOT EXISTS youtube_handles (
    handle      TEXT PRIMARY KEY,
    channel_id  TEXT NOT NULL,
    resolved_at TIMESTAMPTZ DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════
-- DESACTIVAR ROW LEVEL SECURITY (uso personal, bot propio)
-- ═══════════════════════════════════════════════════════
ALTER TABLE sources       DISABLE ROW LEVEL SECURITY;
ALTER TABLE news          DISABLE ROW LEVEL SECURITY;
ALTER TABLE config        DISABLE ROW LEVEL SECURITY;
ALTER TABLE logs          DISABLE ROW LEVEL SECURITY;
ALTER TABLE sent_items    DISABLE ROW LEVEL SECURITY;
ALTER TABLE youtube_handles DISABLE ROW LEVEL SECURITY;
