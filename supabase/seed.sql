BEGIN;

TRUNCATE TABLE
  raw_recurring_schedule,
  raw_airline_buffers,
  gates,
  airlines,
  flights
RESTART IDENTITY CASCADE;

COPY raw_recurring_schedule (...)
FROM '/docker-entrypoint-initdb.d/seeds/recurring_schedule.csv'
WITH (FORMAT csv, HEADER true);

COPY raw_airline_buffers (...)
FROM '/docker-entrypoint-initdb.d/seeds/airline_buffers.csv'
WITH (FORMAT csv, HEADER true);

COPY gates (...)
FROM '/docker-entrypoint-initdb.d/seeds/gates.csv'
WITH (FORMAT csv, HEADER true);

-- transform raw -> normalized
INSERT INTO airlines (... )
SELECT ...;

INSERT INTO flights (... )
SELECT ...;

COMMIT;
