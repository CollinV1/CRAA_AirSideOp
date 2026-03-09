
CREATE TABLE IF NOT EXISTS public.planes (
  id BIGSERIAL PRIMARY KEY,
  "Carrier" text NOT NULL,
  "FlightNumber" bigint NOT NULL,
  "EffectiveDate" text,
  "DiscontinuedDate" text,
  "DOW" text,
  created_at timestamptz DEFAULT now(),
  UNIQUE ("Carrier", "FlightNumber", "EffectiveDate", "DiscontinuedDate", "DOW")
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'plane_mappings' AND column_name = 'plane_id'
  ) THEN
    ALTER TABLE public.plane_mappings ADD COLUMN plane_id bigint;
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'Could not ensure plane_id column: %', SQLERRM;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_schema = 'public' AND tc.table_name = 'plane_mappings' AND tc.constraint_type = 'FOREIGN KEY' AND kcu.column_name = 'flight_id'
  ) THEN
    ALTER TABLE public.plane_mappings ADD CONSTRAINT plane_mappings_flight_fk FOREIGN KEY (flight_id) REFERENCES public.raw_flights(id) ON DELETE CASCADE;
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'Could not add flight_id FK: %', SQLERRM;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
    WHERE tc.table_schema = 'public' AND tc.table_name = 'plane_mappings' AND tc.constraint_type = 'FOREIGN KEY' AND kcu.column_name = 'plane_id'
  ) THEN
    ALTER TABLE public.plane_mappings ADD CONSTRAINT plane_mappings_plane_fk FOREIGN KEY (plane_id) REFERENCES public.planes(id) ON DELETE RESTRICT;
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'Could not add plane_id FK: %', SQLERRM;
END$$;

 
INSERT INTO public.planes ("Carrier", "FlightNumber", "EffectiveDate", "DiscontinuedDate", "DOW")
SELECT DISTINCT "Carrier", "FlightNumber", "EffectiveDate", "DiscontinuedDate", "DOW"
FROM public.raw_flights
ON CONFLICT ("Carrier", "FlightNumber", "EffectiveDate", "DiscontinuedDate", "DOW") DO NOTHING;


INSERT INTO public.plane_mappings (flight_id, plane_id)
SELECT rf.id, p.id
FROM public.raw_flights rf
JOIN public.planes p
  ON p."Carrier" = rf."Carrier"
  AND p."FlightNumber" = rf."FlightNumber"
  AND (p."EffectiveDate" IS NOT DISTINCT FROM rf."EffectiveDate")
  AND (p."DiscontinuedDate" IS NOT DISTINCT FROM rf."DiscontinuedDate")
  AND (p."DOW" IS NOT DISTINCT FROM rf."DOW")
ON CONFLICT (flight_id) DO UPDATE
SET plane_id = EXCLUDED.plane_id
WHERE public.plane_mappings.plane_id IS DISTINCT FROM EXCLUDED.plane_id;

CREATE INDEX IF NOT EXISTS idx_raw_flights_grouping ON public.raw_flights("Carrier", "FlightNumber", "EffectiveDate", "DiscontinuedDate", "DOW");
