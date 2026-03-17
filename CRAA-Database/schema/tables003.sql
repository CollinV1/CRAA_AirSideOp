-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.airlines (
  id text NOT NULL,
  avg_buffer integer,
  CONSTRAINT airlines_pkey PRIMARY KEY (id)
);
CREATE TABLE public.flights (
  id integer NOT NULL DEFAULT nextval('flights_id_seq'::regclass),
  flight_number bigint NOT NULL,
  arrival_time timestamp without time zone NOT NULL,
  departure_time timestamp without time zone NOT NULL,
  airline_id text NOT NULL,
  turnaround_minutes bigint,
  raw_schedule_id bigint,
  CONSTRAINT flights_pkey PRIMARY KEY (id),
  CONSTRAINT raw_schedule_id FOREIGN KEY (id) REFERENCES public.raw_flights(id),
  CONSTRAINT airline_id FOREIGN KEY (airline_id) REFERENCES public.airlines(id)
);
CREATE TABLE public.flights_assignment (
  id integer NOT NULL DEFAULT nextval('flights_assignment_id_seq'::regclass),
  flight_id bigint NOT NULL,
  gate_id text NOT NULL,
  scenario_id bigint NOT NULL,
  is_conflict bigint NOT NULL,
  assigned_at bigint NOT NULL,
  CONSTRAINT flights_assignment_pkey PRIMARY KEY (id),
  CONSTRAINT flights_assignment_flight_id_foreign FOREIGN KEY (flight_id) REFERENCES public.flights(id),
  CONSTRAINT flights_assignment_scenario_id_foreign FOREIGN KEY (scenario_id) REFERENCES public.scenario_runs(id),
  CONSTRAINT gate_id FOREIGN KEY (gate_id) REFERENCES public.gates(id)
);
CREATE TABLE public.gates (
  id text NOT NULL,
  flight_id bigint,
  is_active boolean,
  concourse character NOT NULL,
  CONSTRAINT gates_pkey PRIMARY KEY (id)
);
CREATE TABLE public.plane_mappings (
  flight_id integer GENERATED ALWAYS AS IDENTITY NOT NULL,
  plane_id bigint NOT NULL,
  CONSTRAINT plane_mappings_pkey PRIMARY KEY (flight_id),
  CONSTRAINT plane mappings_flight_id_fkey FOREIGN KEY (flight_id) REFERENCES public.raw_flights(id),
  CONSTRAINT plane_mappings_plane_fk FOREIGN KEY (plane_id) REFERENCES public.planes(id)
);
CREATE TABLE public.planes (
  id bigint NOT NULL DEFAULT nextval('planes_id_seq'::regclass),
  Carrier text NOT NULL,
  FlightNumber bigint NOT NULL,
  EffectiveDate text,
  DiscontinuedDate text,
  DOW text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT planes_pkey PRIMARY KEY (id)
);
CREATE TABLE public.raw_flights (
  Carrier text NOT NULL,
  FlightNumber bigint NOT NULL,
  ServiceType text,
  EffectiveDate text NOT NULL,
  DiscontinuedDate text NOT NULL,
  DOW text NOT NULL,
  Departure Airport text NOT NULL,
  DepartureTime bigint NOT NULL,
  ArrivalAirport text NOT NULL,
  ArrivalTime bigint NOT NULL,
  SubAircraftTypeCode text NOT NULL,
  id integer GENERATED ALWAYS AS IDENTITY NOT NULL UNIQUE,
  CONSTRAINT raw_flights_pkey PRIMARY KEY (id)
);
CREATE TABLE public.scenario_runs (
  id integer NOT NULL DEFAULT nextval('scenario_runs_id_seq'::regclass),
  name text NOT NULL,
  created_at timestamp without time zone NOT NULL,
  parameters json NOT NULL,
  CONSTRAINT scenario_runs_pkey PRIMARY KEY (id)
);