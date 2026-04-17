-- ============================================================
--  ClinAssist — Supabase Schema
--  Run this entire file in:
--  Supabase Dashboard → SQL Editor → New Query → Run
-- ============================================================


-- ── 1. Users table ───────────────────────────────────────────
--  Stores registered ClinAssist users (clinicians / patients)

CREATE TABLE IF NOT EXISTS public.users (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT        NOT NULL,
  user_id       TEXT        UNIQUE NOT NULL,   -- custom staff/clinic ID e.g. "DR-0042"
  email         TEXT        UNIQUE NOT NULL,
  password_hash TEXT        NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast email lookups (login)
CREATE INDEX IF NOT EXISTS idx_users_email   ON public.users (email);
CREATE INDEX IF NOT EXISTS idx_users_user_id ON public.users (user_id);


-- ── 2. Session history table ──────────────────────────────────
--  Links each completed ClinAssist local session to a user

CREATE TABLE IF NOT EXISTS public.session_history (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         TEXT        NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
  session_id      TEXT        UNIQUE NOT NULL,   -- ClinAssist local SQLite session ID
  chief_complaint TEXT,
  risk_level      TEXT,
  summary         TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast per-user history queries
CREATE INDEX IF NOT EXISTS idx_session_history_user_id
  ON public.session_history (user_id, created_at DESC);


-- ── 3. Row Level Security ─────────────────────────────────────
--  Prevents one user from reading another user's data
--  (Note: the backend uses the service-role key which bypasses RLS,
--   but these policies protect against accidental anon-key leaks)

ALTER TABLE public.users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.session_history ENABLE ROW LEVEL SECURITY;

-- Drop policies if re-running this script
DROP POLICY IF EXISTS "service_role_bypass_users"          ON public.users;
DROP POLICY IF EXISTS "service_role_bypass_session_history" ON public.session_history;

-- Allow service role full access (backend uses service role key)
CREATE POLICY "service_role_bypass_users"
  ON public.users
  USING (auth.role() = 'service_role');

CREATE POLICY "service_role_bypass_session_history"
  ON public.session_history
  USING (auth.role() = 'service_role');


-- ── 4. Verification queries ───────────────────────────────────
--  Run these separately after the above to confirm tables exist:
--
--  SELECT table_name FROM information_schema.tables
--  WHERE table_schema = 'public';
--
--  SELECT column_name, data_type FROM information_schema.columns
--  WHERE table_name = 'users';
--
--  SELECT column_name, data_type FROM information_schema.columns
--  WHERE table_name = 'session_history';
