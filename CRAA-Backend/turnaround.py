from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from supabase import Client


SIZE_MAP = {
    "CR7": "SMALL", "CR9": "SMALL", "ERJ": "SMALL", "E70": "SMALL", "E75": "SMALL",
    "319": "MEDIUM", "320": "MEDIUM", "321": "MEDIUM", "32A": "MEDIUM", "32B": "MEDIUM", "32N": "MEDIUM",
    "738": "MEDIUM", "739": "MEDIUM", "73W": "MEDIUM", "73H": "MEDIUM", "73J": "MEDIUM", "73G": "MEDIUM",
    "7M8": "MEDIUM", "7M9": "MEDIUM", "E90": "MEDIUM", "E95": "MEDIUM", "E7W": "MEDIUM",
    "717": "MEDIUM", "221": "MEDIUM", "223": "MEDIUM",
    "757": "LARGE",
}

GATE_CONFIG = (
    [("B1", "SMALL"), ("B2", "SMALL"), ("B3", "SMALL"), ("B4", "SMALL")] +
    [("B5", "MEDIUM"), ("B6", "MEDIUM"), ("B7", "MEDIUM"), ("B8", "MEDIUM"),
     ("B9", "MEDIUM"), ("B10", "MEDIUM"), ("B11", "MEDIUM"), ("B12", "MEDIUM")] +
    [("A1", "LARGE"), ("A2", "LARGE"), ("A3", "LARGE"), ("A4", "LARGE"), ("A5", "LARGE")]
)

BATCH_SIZE = 500
EXPANDED_TABLE_NAME = "flight_instances_test"


def gate_fits(gate_type: str, size: str) -> bool:
    if gate_type == "SMALL":
        return size == "SMALL"
    if gate_type == "MEDIUM":
        return size in ("SMALL", "MEDIUM")
    return True


def minutes_since_midnight(value: datetime) -> int:
    return value.hour * 60 + value.minute


def parse_datetime(value: str | None) -> datetime | None:
    if value in (None, "", "None"):
        return None
    return datetime.fromisoformat(value)


def format_db_time(value: datetime) -> str:
    return value.strftime("%H:%M:%S")


def fetch_flight_instances(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    rows = (
        supabase.table(EXPANDED_TABLE_NAME)
        .select(
            "id,flight_id,flight_number,airline_id,departure_airport,arrival_airport,departure_datetime,arrival_datetime,subaircrafttypecode"
        )
        .order("arrival_datetime")
        .execute()
    ).data or []

    if not start_date and not end_date:
        return rows

    filtered = []
    for row in rows:
        arrival_dt = parse_datetime(row["arrival_datetime"])
        departure_dt = parse_datetime(row["departure_datetime"])
        if arrival_dt is None or departure_dt is None:
            continue
        if start_date and arrival_dt.date() < start_date and departure_dt.date() < start_date:
            continue
        if end_date and arrival_dt.date() > end_date and departure_dt.date() > end_date:
            continue
        filtered.append(row)
    return filtered


def build_turns_for_day(instances: list[dict], service_date: date, turnaround_min: int, shared_gates: bool) -> list[dict]:
    arrivals = []
    departures = []

    for row in instances:
        arrival_dt = parse_datetime(row["arrival_datetime"])
        departure_dt = parse_datetime(row["departure_datetime"])
        if arrival_dt is None or departure_dt is None:
            continue
        row_size = SIZE_MAP.get(str(row["subaircrafttypecode"]), "MEDIUM")

        if row["arrival_airport"] == "CHS" and arrival_dt.date() == service_date:
            arrivals.append({
                **row,
                "event_dt": arrival_dt,
                "event_min": minutes_since_midnight(arrival_dt),
                "size": row_size,
            })

        if row["departure_airport"] == "CHS" and departure_dt.date() == service_date:
            departures.append({
                **row,
                "event_dt": departure_dt,
                "event_min": minutes_since_midnight(departure_dt),
                "size": row_size,
            })

    if not arrivals or not departures:
        return []

    arrivals.sort(key=lambda row: row["event_min"])
    departures.sort(key=lambda row: row["event_min"])

    matched_departures = set()
    turns = []

    for arrival in arrivals:
        candidates = []
        for departure in departures:
            if departure["id"] in matched_departures:
                continue
            if departure["size"] != arrival["size"]:
                continue
            if departure["event_min"] < arrival["event_min"] + turnaround_min:
                continue
            if not shared_gates and departure["airline_id"] != arrival["airline_id"]:
                continue
            candidates.append(departure)

        if not candidates:
            continue

        best = min(candidates, key=lambda row: row["event_min"])
        matched_departures.add(best["id"])
        turns.append({
            "service_date": service_date,
            "inbound_instance_id": arrival["id"],
            "inbound_flight_id": arrival["flight_id"],
            "inbound_carrier": arrival["airline_id"],
            "inbound_flight": int(arrival["flight_number"]),
            "arrival_time": arrival["event_dt"],
            "arr_min": arrival["event_min"],
            "outbound_instance_id": best["id"],
            "outbound_flight_id": best["flight_id"],
            "outbound_carrier": best["airline_id"],
            "outbound_flight": int(best["flight_number"]),
            "departure_time": best["event_dt"],
            "dep_min": best["event_min"],
            "turnaround_minutes": int(best["event_min"] - arrival["event_min"]),
            "aircraft": str(arrival["subaircrafttypecode"]),
            "size": arrival["size"],
            "cross_carrier": arrival["airline_id"] != best["airline_id"],
        })

    turns.sort(key=lambda row: row["turnaround_minutes"])

    gate_free = {gate_id: 0 for gate_id, _ in GATE_CONFIG}
    for turn in turns:
        assigned = False
        for gate_id, gate_type in GATE_CONFIG:
            if gate_fits(gate_type, turn["size"]) and gate_free[gate_id] <= turn["arr_min"]:
                gate_free[gate_id] = turn["dep_min"]
                turn["gate_id"] = gate_id
                turn["conflict"] = False
                assigned = True
                break
        if not assigned:
            turn["gate_id"] = GATE_CONFIG[0][0]
            turn["conflict"] = True

    return turns


def summarize_turns(turns: list[dict]) -> dict:
    conflicts = sum(1 for turn in turns if turn["conflict"])
    scheduled_turns = len(turns) - conflicts
    avg_turnaround = (
        sum(turn["turnaround_minutes"] for turn in turns) / len(turns)
        if turns else 0
    )
    return {
        "total_turns": len(turns),
        "scheduled_turns": scheduled_turns,
        "conflicts": conflicts,
        "avg_turnaround": avg_turnaround,
    }


def choose_optimal_schedule(scenarios: list[dict]) -> dict:
    scored = [{**scenario, "metrics": summarize_turns(scenario["turns"])} for scenario in scenarios]
    return min(
        scored,
        key=lambda scenario: (
            -scenario["metrics"]["scheduled_turns"],
            scenario["metrics"]["conflicts"],
            scenario["metrics"]["avg_turnaround"],
        ),
    )


def clear_existing_schedule_results(supabase: Client) -> None:
    supabase.table("flights_assignment_test").delete().neq("id", 0).execute()
    supabase.table("scenario_runs_test").delete().neq("id", 0).execute()


def insert_flights_and_assignments(
    supabase: Client,
    scenario_id: int,
    turns: list[dict],
) -> dict:
    assignments_inserted = 0
    flights_inserted = 0

    for index in range(0, len(turns), BATCH_SIZE):
        batch = turns[index:index + BATCH_SIZE]
        flight_rows = [{
            "flight_number": turn["inbound_flight"],
            "arrival_time": format_db_time(turn["arrival_time"]),
            "departure_time": format_db_time(turn["departure_time"]),
            "airline_id": turn["inbound_carrier"],
            "turnaround_minutes": turn["turnaround_minutes"],
            "raw_schedule_id": turn["inbound_flight_id"],
        } for turn in batch]

        inserted_flights = supabase.table("flights_test").insert(flight_rows).execute().data or []
        flights_inserted += len(inserted_flights)

        assignment_rows = []
        for turn, inserted in zip(batch, inserted_flights):
            assignment_rows.append({
                "flight_id": inserted["id"],
                "gate_id": turn["gate_id"],
                "scenario_id": scenario_id,
                "is_conflict": 1 if turn["conflict"] else 0,
                "assigned_at": int(turn["arrival_time"].timestamp()),
            })

        if assignment_rows:
            supabase.table("flights_assignment_test").insert(assignment_rows).execute()
            assignments_inserted += len(assignment_rows)

    return {
        "flights_inserted": flights_inserted,
        "assignments_inserted": assignments_inserted,
    }


def run_turnaround_scenarios(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
    turnaround_min: int = 45,
    replace_existing: bool = True,
) -> dict:
    instances = fetch_flight_instances(supabase, start_date=start_date, end_date=end_date)
    if not instances:
        return {
            "scenarios": [],
            "optimal_scenario": None,
            "flight_instances_used": 0,
        }

    service_dates = sorted({
        parse_datetime(row["arrival_datetime"]).date()
        for row in instances if row["arrival_airport"] == "CHS"
    } | {
        parse_datetime(row["departure_datetime"]).date()
        for row in instances if row["departure_airport"] == "CHS"
    })
    if not service_dates:
        return {
            "flight_instances_used": len(instances),
            "scenarios": [],
            "optimal_scenario": None,
        }

    same_carrier_turns = []
    shared_gate_turns = []
    for service_date in service_dates:
        same_carrier_turns.extend(build_turns_for_day(instances, service_date, turnaround_min, shared_gates=False))
        shared_gate_turns.extend(build_turns_for_day(instances, service_date, turnaround_min, shared_gates=True))

    scenarios = [
        {
            "name": "Scenario 1 — Same-Carrier Gate Assignment",
            "parameters": {
                "turnaround_min": turnaround_min,
                "num_gates": 15,
                "shared_gates": False,
                "source_table": EXPANDED_TABLE_NAME,
                "date_range": f"{start_date or min(service_dates)} to {end_date or max(service_dates)}",
            },
            "turns": same_carrier_turns,
        },
        {
            "name": "Scenario 2 — Shared Gates (Cross-Carrier, Size-Compatible)",
            "parameters": {
                "turnaround_min": turnaround_min,
                "num_gates": 15,
                "shared_gates": True,
                "source_table": EXPANDED_TABLE_NAME,
                "date_range": f"{start_date or min(service_dates)} to {end_date or max(service_dates)}",
            },
            "turns": shared_gate_turns,
        },
    ]

    optimal = choose_optimal_schedule(scenarios)

    if replace_existing:
        clear_existing_schedule_results(supabase)

    created_scenarios = []
    for scenario in scenarios:
        inserted = (
            supabase.table("scenario_runs_test")
            .insert({
                "name": scenario["name"],
                "created_at": datetime.now().isoformat(),
                "parameters": scenario["parameters"],
            })
            .execute()
        ).data or []
        if not inserted:
            continue

        scenario_row = inserted[0]
        counts = insert_flights_and_assignments(supabase, scenario_row["id"], scenario["turns"])
        created_scenarios.append({
            "scenario_id": scenario_row["id"],
            "name": scenario["name"],
            "metrics": summarize_turns(scenario["turns"]),
            **counts,
        })

    return {
        "flight_instances_used": len(instances),
        "scenarios": created_scenarios,
        "optimal_scenario": {
            "name": optimal["name"],
            "metrics": optimal["metrics"],
        },
    }

# called in main.py
def export_optimal_schedule_csv(turns: list[dict], output_path: str | Path) -> Path:
    '''
    Generate a .csv that stores the optimal schedule
    '''
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "service_date",
                "gate_id",
                "inbound_carrier",
                "inbound_flight",
                "arrival_time",
                "outbound_carrier",
                "outbound_flight",
                "departure_time",
                "aircraft",
                "size",
                "turnaround_minutes",
                "cross_carrier",
                "scheduled_at_gate",
            ],
        )
        writer.writeheader()
        for turn in sorted(turns, key=lambda row: (row["service_date"], row["gate_id"], row["arr_min"])):
            writer.writerow({
                "service_date": turn["service_date"].isoformat(),
                "gate_id": turn["gate_id"],
                "inbound_carrier": turn["inbound_carrier"],
                "inbound_flight": turn["inbound_flight"],
                "arrival_time": turn["arrival_time"].isoformat(),
                "outbound_carrier": turn["outbound_carrier"],
                "outbound_flight": turn["outbound_flight"],
                "departure_time": turn["departure_time"].isoformat(),
                "aircraft": turn["aircraft"],
                "size": turn["size"],
                "turnaround_minutes": turn["turnaround_minutes"],
                "cross_carrier": turn["cross_carrier"],
                "scheduled_at_gate": not turn["conflict"],
            })

    return output


def build_and_store_optimal_schedule(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
    turnaround_min: int = 45,
    replace_existing: bool = True,
) -> dict:
    
    instances = fetch_flight_instances(supabase, start_date=start_date, end_date=end_date)
    if not instances:
        return {
            "scenarios": [],
            "optimal_scenario": None,
            "optimal_turns": [],
            "flight_instances_used": 0,
        }

    service_dates = sorted({
        parse_datetime(row["arrival_datetime"]).date()
        for row in instances if row["arrival_airport"] == "CHS"
    } | {
        parse_datetime(row["departure_datetime"]).date()
        for row in instances if row["departure_airport"] == "CHS"
    })
    if not service_dates:
        return {
            "scenarios": [],
            "optimal_scenario": None,
            "optimal_turns": [],
            "flight_instances_used": len(instances),
        }

    scenarios = [
        {
            "name": "Scenario 1 — Same-Carrier Gate Assignment",
            "parameters": {
                "turnaround_min": turnaround_min,
                "num_gates": 15,
                "shared_gates": False,
                "source_table": "flight_instances",
                "date_range": f"{start_date or min(service_dates)} to {end_date or max(service_dates)}",
            },
            "turns": [
                turn
                for service_date in service_dates
                for turn in build_turns_for_day(instances, service_date, turnaround_min, shared_gates=False)
            ],
        },
        {
            "name": "Scenario 2 — Shared Gates (Cross-Carrier, Size-Compatible)",
            "parameters": {
                "turnaround_min": turnaround_min,
                "num_gates": 15,
                "shared_gates": True,
                "source_table": "flight_instances",
                "date_range": f"{start_date or min(service_dates)} to {end_date or max(service_dates)}",
            },
            "turns": [
                turn
                for service_date in service_dates
                for turn in build_turns_for_day(instances, service_date, turnaround_min, shared_gates=True)
            ],
        },
    ]

    optimal = choose_optimal_schedule(scenarios)
    stored = run_turnaround_scenarios(
        supabase,
        start_date=start_date,
        end_date=end_date,
        turnaround_min=turnaround_min,
        replace_existing=replace_existing,
    )
    stored["optimal_turns"] = optimal["turns"]
    stored["optimal_scenario"] = {
        "name": optimal["name"],
        "metrics": optimal["metrics"],
    }
    return stored
