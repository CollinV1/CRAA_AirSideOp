from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable

from supabase import Client


RAW_DATE_FORMAT = "%d%b%y"
BATCH_SIZE = 500
DEFAULT_START_DATE = date(2025, 1, 1)
DEFAULT_END_DATE = date(2025, 1, 31)
RAW_TABLE_NAME = "raw_flights_test"
NORMALIZED_TABLE_NAME = "flights_test"
EXPANDED_TABLE_NAME = "flight_instances_test"


def parse_raw_date(value: str) -> date:
    return datetime.strptime(value, RAW_DATE_FORMAT).date()


def parse_hhmm(value: int | str) -> time:
    if isinstance(value, str):
        stripped = value.strip()
        if ":" in stripped:
            parts = stripped.split(":")
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            return time(hour=hour, minute=minute, second=second)
        value = stripped

    hhmm = str(int(value)).zfill(4)
    return time(hour=int(hhmm[:2]), minute=int(hhmm[2:]))


def format_time(value: int | str) -> str:
    return parse_hhmm(value).strftime("%H:%M:%S")


def normalize_dow_array(raw_value: str) -> list[int]:
    cleaned = str(raw_value).replace(" ", "")
    values = []
    for char in cleaned:
        if char.isdigit():
            day = int(char)
            if 1 <= day <= 7:
                values.append(day)
    return values


def coerce_dow_array(dow_array: object) -> list[int]:
    if dow_array is None:
        return []
    if isinstance(dow_array, int):
        return [dow_array]
    if isinstance(dow_array, list):
        return [int(day) for day in dow_array]
    if isinstance(dow_array, tuple):
        return [int(day) for day in dow_array]
    if isinstance(dow_array, str):
        cleaned = dow_array.strip().strip("{}[]()")
        if not cleaned:
            return []
        parts = [part.strip() for part in cleaned.replace(" ", ",").split(",")]
        return [int(part) for part in parts if part]
    return []


def dow_array_to_postgres_dow(dow_array: object) -> set[int]:
    values = set()
    for day in coerce_dow_array(dow_array):
        if day == 7:
            values.add(0)
        elif 1 <= day <= 6:
            values.add(day)
    return values


def daterange(start_date: date, end_date: date) -> Iterable[date]:
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def combine_flight_datetime(flight_date: date, hhmm_value: str | int) -> datetime:
    return datetime.combine(flight_date, parse_hhmm(hhmm_value))


def postgres_dow(flight_date: date) -> int:
    return (flight_date.weekday() + 1) % 7


def replace_flights(supabase: Client) -> dict:
    raw_rows = (
        supabase.table(RAW_TABLE_NAME)
        .select("*")
        .order("id")
        .execute()
    ).data or []

    if not raw_rows:
        supabase.table(EXPANDED_TABLE_NAME).delete().neq("id", 0).execute()
        supabase.table(NORMALIZED_TABLE_NAME).delete().neq("id", 0).execute()
        return {
            "raw_rows": 0,
            "normalized_rows_created": 0,
            "raw_table": RAW_TABLE_NAME,
            "normalized_table": NORMALIZED_TABLE_NAME,
        }

    normalized_rows = []
    for row in raw_rows:
        normalized_rows.append({
            "id": row["id"],
            "flight_number": int(row["FlightNumber"]),
            "arrival_time": format_time(row["ArrivalTime"]),
            "departure_time": format_time(row["DepartureTime"]),
            "airline_id": row["Carrier"],
            "turnaround_minutes": None,
            "raw_schedule_id": row.get("id"),
            "dow_array": normalize_dow_array(row["DOW"]),
            "effective_date": parse_raw_date(row["EffectiveDate"]).isoformat(),
            "discontinued_date": parse_raw_date(row["DiscontinuedDate"]).isoformat() if row.get("DiscontinuedDate") else None,
            "departure_airport": row["Departure Airport"],
            "arrival_airport": row["ArrivalAirport"],
            "subaircrafttypecode": row["SubAircraftTypeCode"],
        })

    inserted_count = 0
    for index in range(0, len(normalized_rows), BATCH_SIZE):
        batch = normalized_rows[index:index + BATCH_SIZE]
        inserted = supabase.table(NORMALIZED_TABLE_NAME).insert(batch).execute().data or []
        inserted_count += len(inserted)

    return {
        "raw_rows": len(raw_rows),
        "normalized_rows_created": inserted_count,
        "raw_table": RAW_TABLE_NAME,
        "normalized_table": NORMALIZED_TABLE_NAME,
    }


def expand_raw_flights_to_instances(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
    replace_existing: bool = True,
) -> dict:
    params_start_date = start_date or DEFAULT_START_DATE
    params_end_date = end_date or DEFAULT_END_DATE

    normalized_rows = (
        supabase.table(NORMALIZED_TABLE_NAME)
        .select("*")
        .order("id")
        .execute()
    ).data or []

    if replace_existing:
            supabase.table(EXPANDED_TABLE_NAME).delete().neq("id", 0).execute()

    if not normalized_rows:
        return {
            "normalized_rows": 0,
            "expanded_rows_created": 0,
            "normalized_table": NORMALIZED_TABLE_NAME,
            "expanded_table": EXPANDED_TABLE_NAME,
            "start_date": str(params_start_date),
            "end_date": str(params_end_date),
            "replace_existing": replace_existing,
        }

    instances = []
    for row in normalized_rows:
        effective_date = date.fromisoformat(str(row["effective_date"]))
        discontinued_raw = row.get("discontinued_date")
        discontinued_date = date.fromisoformat(str(discontinued_raw)) if discontinued_raw else params_end_date

        window_start = max(effective_date, params_start_date)
        window_end = min(discontinued_date, params_end_date)
        if window_start > window_end:
            continue

        operating_days = dow_array_to_postgres_dow(row.get("dow_array"))
        for flight_date in daterange(window_start, window_end):
            if postgres_dow(flight_date) not in operating_days:
                continue

            departure_datetime = combine_flight_datetime(flight_date, row["departure_time"])
            arrival_datetime = combine_flight_datetime(flight_date, row["arrival_time"])
            if arrival_datetime < departure_datetime:
                arrival_datetime += timedelta(days=1)

            instances.append({
                "flight_id": row["id"],
                "flight_number": row["flight_number"],
                "airline_id": row["airline_id"],
                "departure_airport": row["departure_airport"],
                "arrival_airport": row["arrival_airport"],
                "departure_datetime": departure_datetime.isoformat(),
                "arrival_datetime": arrival_datetime.isoformat(),
                "subaircrafttypecode": row["subaircrafttypecode"],
            })

    inserted_count = 0
    for index in range(0, len(instances), BATCH_SIZE):
        batch = instances[index:index + BATCH_SIZE]
        inserted = supabase.table(EXPANDED_TABLE_NAME).insert(batch).execute().data or []
        inserted_count += len(inserted)

    return {
        "normalized_rows": len(normalized_rows),
        "expanded_rows_created": inserted_count,
        "normalized_table": NORMALIZED_TABLE_NAME,
        "expanded_table": EXPANDED_TABLE_NAME,
        "start_date": str(params_start_date if start_date is None else start_date),
        "end_date": str(params_end_date if end_date is None else end_date),
        "replace_existing": replace_existing,
    }
