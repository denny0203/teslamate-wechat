-- Additive migration. A detail snapshot is published atomically as one row.
BEGIN;
CREATE TABLE IF NOT EXISTS public.app_drive_details (
 owner_id uuid NOT NULL,
 id bigint NOT NULL,
 car_id bigint NOT NULL,
 version text NOT NULL,
 status text NOT NULL CHECK (status IN ('ready','empty','unfinished')),
 payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
 synced_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (owner_id,id),
 FOREIGN KEY (owner_id,id) REFERENCES public.app_drives(owner_id,id) ON DELETE CASCADE
);
ALTER TABLE public.app_drive_details ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.app_drive_details FROM anon, authenticated;
GRANT SELECT ON public.app_drive_details TO authenticated;
GRANT ALL ON public.app_drive_details TO service_role;
DROP POLICY IF EXISTS owner_read ON public.app_drive_details;
CREATE POLICY owner_read ON public.app_drive_details FOR SELECT TO authenticated
 USING ((SELECT auth.uid()) = owner_id);
COMMIT;
NOTIFY pgrst, 'reload schema';
