''' 
Extract all flight instances from single row 
first normalizing DOW then 
'''

SELECT
    r.carrier,
    r.flight_number,
    d.flight_date
FROM raw_recurring_schedule r
CROSS JOIN generate_series(
    r.effective_date,
    r.discontinued_date,
    interval '1 day'
) AS d(flight_date)
WHERE
((EXTRACT(DOW FROM d.flight_date) + 6) % 7) + 1
    = ANY(regexp_split_to_array(r.DOW, '\s+')::int[]);
