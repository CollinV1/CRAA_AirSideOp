CREATE TABLE "raw_recurring_schedule"(
    "id" SERIAL NOT NULL,
    "Carrier" TEXT NOT NULL,
    "FlightNum" BIGINT NOT NULL,
    "ServiceType" TEXT NOT NULL,
    "EffectiveDate" TEXT NOT NULL,
    "DiscontinuedDate" TEXT NOT NULL,
    "DOW" BIGINT NOT NULL,
    "DepartureAirport" BIGINT NOT NULL,
    "DepartureTime" BIGINT NOT NULL,
    "ArrivalAirport" BIGINT NOT NULL,
    "ArrivalTime" TEXT NOT NULL,
    "SubAircraftTypeCode" INTEGER NOT NULL
);
ALTER TABLE
    "raw_recurring_schedule" ADD PRIMARY KEY("id");
CREATE TABLE "gates"(
    "id" BIGINT NOT NULL,
    "flight_id" BIGINT NOT NULL,
    "is_active" BOOLEAN NOT NULL
);
ALTER TABLE
    "gates" ADD PRIMARY KEY("id");
CREATE TABLE "airlines"(
    "id" SERIAL NOT NULL,
    "carrier" VARCHAR(255) NOT NULL,
    "avg_buffer" INTEGER NOT NULL
);
ALTER TABLE
    "airlines" ADD PRIMARY KEY("id");
CREATE TABLE "flights"(
    "id" SERIAL NOT NULL,
    "flight_number" BIGINT NOT NULL,
    "arrival_time" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "departure_time" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "airline_id" BIGINT NOT NULL,
    "service_type" BIGINT NOT NULL,
    "aircraft_type_id" BIGINT NOT NULL,
    "days_of_week" BIGINT NOT NULL,
    "turnaround_minutes" BIGINT NOT NULL
);
ALTER TABLE
    "flights" ADD PRIMARY KEY("id");
CREATE TABLE "flights_assignment"(
    "id" SERIAL NOT NULL,
    "flight_id" BIGINT NOT NULL,
    "gate_id" BIGINT NOT NULL,
    "scenario_id" BIGINT NOT NULL,
    "is_conflict" BIGINT NOT NULL,
    "assigned_at" BIGINT NOT NULL
);
ALTER TABLE
    "flights_assignment" ADD PRIMARY KEY("id");
CREATE TABLE "scenario_runs"(
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "created_at" TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
    "parameters" JSON NOT NULL
);
ALTER TABLE
    "scenario_runs" ADD PRIMARY KEY("id");
ALTER TABLE
    "raw_recurring_schedule" ADD CONSTRAINT "raw_recurring_schedule_departuretime_foreign" FOREIGN KEY("DepartureTime") REFERENCES "flights"("arrival_time");
ALTER TABLE
    "flights" ADD CONSTRAINT "flights_airline_id_foreign" FOREIGN KEY("airline_id") REFERENCES "airlines"("id");
ALTER TABLE
    "flights_assignment" ADD CONSTRAINT "flights_assignment_flight_id_foreign" FOREIGN KEY("flight_id") REFERENCES "flights"("id");
ALTER TABLE
    "flights_assignment" ADD CONSTRAINT "flights_assignment_gate_id_foreign" FOREIGN KEY("gate_id") REFERENCES "gates"("id");
ALTER TABLE
    "flights" ADD CONSTRAINT "flights_airline_id_foreign" FOREIGN KEY("airline_id") REFERENCES "raw_recurring_schedule"("Carrier");
ALTER TABLE
    "flights_assignment" ADD CONSTRAINT "flights_assignment_scenario_id_foreign" FOREIGN KEY("scenario_id") REFERENCES "scenario_runs"("id");
ALTER TABLE
    "flights" ADD CONSTRAINT "flights_departure_time_foreign" FOREIGN KEY("departure_time") REFERENCES "raw_recurring_schedule"("ArrivalAirport");
