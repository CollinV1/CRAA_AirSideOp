
WITH params AS (
  SELECT 
    DATE '2025-01-01' AS start_date,
    DATE '2025-01-31' AS end_date
)

INSERT INTO flight_instances (
  flight_id,
  flight_number,
  airline_id,
  departure_airport,
  arrival_airport,
  departure_datetime,
  arrival_datetime,
  subaircrafttypecode
)

SELECT
  f.id,
  f.flight_number,
  f.airline_id,
  f.departure_airport,
  f.arrival_airport,

  -- departure datetime
  (d.date + f.departure_time) AS departure_datetime,

  -- arrival datetime (handle overnight flights)
  (d.date + f.arrival_time)
    + CASE
        WHEN f.arrival_time < f.departure_time THEN INTERVAL '1 day'
        ELSE INTERVAL '0'
      END AS arrival_datetime,

  f.subaircrafttypecode

FROM flights f
CROSS JOIN params p

JOIN generate_series(
  GREATEST(f.effective_date, p.start_date),
  LEAST(
    COALESCE(f.discontinued_date, p.end_date),
    p.end_date
  ),
  INTERVAL '1 day'
) AS d(date)
ON TRUE

WHERE EXTRACT(DOW FROM d.date) = ANY(f.dow_array);