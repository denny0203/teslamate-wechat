BEGIN;
ALTER TABLE public.app_drives ADD COLUMN IF NOT EXISTS energy_used_kwh double precision;
ALTER TABLE public.app_drives ADD COLUMN IF NOT EXISTS range_used_km double precision;
CREATE TABLE IF NOT EXISTS public.app_vehicles (
 owner_id uuid NOT NULL REFERENCES auth.users(id), car_id bigint NOT NULL,
 payload jsonb NOT NULL, synced_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(owner_id,car_id)
);
ALTER TABLE public.app_vehicles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.app_vehicles FROM anon,authenticated;
GRANT SELECT ON public.app_vehicles TO authenticated;
GRANT ALL ON public.app_vehicles TO service_role;
DROP POLICY IF EXISTS owner_read ON public.app_vehicles;
CREATE POLICY owner_read ON public.app_vehicles FOR SELECT TO authenticated USING ((SELECT auth.uid())=owner_id);
COMMIT;
NOTIFY pgrst,'reload schema';
