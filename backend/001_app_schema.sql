-- Only new app tables. TeslaMate source tables and Supabase platform objects are untouched.
BEGIN;
CREATE TABLE IF NOT EXISTS public.app_drives (
  owner_id uuid NOT NULL REFERENCES auth.users(id),
  id bigint NOT NULL,
  car_id bigint NOT NULL,
  started_at timestamptz NOT NULL,
  ended_at timestamptz,
  start_address text,
  end_address text,
  distance_km double precision CHECK (distance_km IS NULL OR distance_km >= 0),
  synced_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_id, id)
);
CREATE INDEX IF NOT EXISTS app_drives_owner_started ON public.app_drives(owner_id, started_at DESC, id DESC);
CREATE TABLE IF NOT EXISTS public.app_sync_status (
  owner_id uuid PRIMARY KEY REFERENCES auth.users(id),
  last_success_at timestamptz NOT NULL,
  latest_drive_at timestamptz,
  synced_rows integer NOT NULL CHECK (synced_rows >= 0)
);
ALTER TABLE public.app_drives ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_sync_status ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.app_drives, public.app_sync_status FROM anon, authenticated;
GRANT SELECT ON public.app_drives, public.app_sync_status TO authenticated;
GRANT ALL ON public.app_drives, public.app_sync_status TO service_role;
DROP POLICY IF EXISTS owner_read ON public.app_drives;
CREATE POLICY owner_read ON public.app_drives FOR SELECT TO authenticated USING ((SELECT auth.uid()) = owner_id);
DROP POLICY IF EXISTS owner_read ON public.app_sync_status;
CREATE POLICY owner_read ON public.app_sync_status FOR SELECT TO authenticated USING ((SELECT auth.uid()) = owner_id);
COMMIT;
NOTIFY pgrst, 'reload schema';
