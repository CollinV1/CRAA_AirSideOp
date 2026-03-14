INSERT INTO raw_flights (
    id,
    Carrier,
    FlightNumber,
    ServiceType,
    EffectiveDate,
    DiscontinuedDate,
    DOW,
    Departure Airport, 
    DepartureTime, 
    ArrivalAirport, 
    ArrivalTime, 
    SubAircraftTypeCode
)
SELECT
    ROW_NUMBER() OVER () AS id,
    Carrier,
    FlightNumber,
    ServiceType,
    EffectiveDate,
    DiscontinuedDate,
    DOW,
    Departure Airport, 
    DepartureTime, 
    ArrivalAirport, 
    ArrivalTime, 
    SubAircraftTypeCode
FROM raw_flights_stage
-- INSERT INTO gates (

-- )
-- SELECT

-- INSERT INTO airlines (
--     carrier
-- )
-- SELECT DISTINCT carrier 
-- FROM raw_flights
