"""
SCRIPT 2 — Run Scheduling Algorithm & Write to Database
=========================================================
Runs the Greedy Interval Scheduling algorithm across the full year,
exports the optimal gate schedule to CSV, and optionally populates:
  - scenario_runs       (one row per algorithm run)
  - flights             (each matched inbound/outbound turn)
  - flights_assignment  (gate assignment result for each flight)

Two scenarios are inserted automatically:
  Scenario 1 — Same-Carrier only (original algorithm)
  Scenario 2 — Shared Gates with aircraft size compatibility (improved)

Usage:
    python 02_run_algorithm.py

Primary output:
    optimal_flight_schedule.csv

Requirements:
    pip install psycopg2-binary pandas
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:  # Database export is optional for CSV-only runs.
    psycopg2 = None
    execute_values = None

'''
TODO
1. retrieve data from database, not local .csv
2. take size from db instead of hardcoding it
3. retrieve turnaround minutes from frontend

'''

# ── Database connection ───────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "craa_operations",
    "user":     "postgres",
    "password": "your_password",
}

CSV_PATH = "supabase/seeds/s01FEB2431JAN25.csv"
OUTPUT_CSV_PATH = "optimal_flight_schedule.csv"

# ── Aircraft size classification ──────────────────────────────────────────────
SIZE_MAP = {
    "CR7":"SMALL","CR9":"SMALL","ERJ":"SMALL","E70":"SMALL","E75":"SMALL",
    "319":"MEDIUM","320":"MEDIUM","321":"MEDIUM","32A":"MEDIUM","32B":"MEDIUM","32N":"MEDIUM",
    "738":"MEDIUM","739":"MEDIUM","73W":"MEDIUM","73H":"MEDIUM","73J":"MEDIUM","73G":"MEDIUM",
    "7M8":"MEDIUM","7M9":"MEDIUM","E90":"MEDIUM","E95":"MEDIUM","E7W":"MEDIUM",
    "717":"MEDIUM","221":"MEDIUM","223":"MEDIUM",
    "757":"LARGE",
}

GATE_CONFIG = (
    [(g, "SMALL")  for g in range(1,  5)] +
    [(g, "MEDIUM") for g in range(5, 13)] +
    [(g, "LARGE")  for g in range(13, 16)]
)

def gate_fits(gate_type, size):
    """
    Checks the compatubiility between an aircrafts size and gate

    Parameters -->
        gate_type : "SMALL", "MEDIUM", or "LARGE"
            gate we want to fit the plane in
        size : "SMALL", "MEDIUM", or "LARGE"
            size of the plane we want to fit in gate

    Returns -->
        Boolean value telling if plane will fit in provided gate 
    """
    if gate_type == "SMALL":  return size == "SMALL"
    if gate_type == "MEDIUM": return size in ("SMALL", "MEDIUM") # MEDIUM fits SMALL & MEDIUM
    return True  # LARGE fits all

TURNAROUND_MIN = 45

# ── Helpers ───────────────────────────────────────────────────────────────────
def to_min(t):
    """
    Makes time comparison easier by changing timestamp to minutes after midnight
    
    Parameters -->
        t : int flight time 
    
    Returns -->
        int : minutes after midnight
    """
    t = str(int(t)).zfill(4)
    return int(t[:2]) * 60 + int(t[2:])

def to_timestamp(date, minutes):
    """Convert a date + minute-of-day into a full timestamp."""
    return datetime(date.year, date.month, date.day) + timedelta(minutes=int(minutes))

def get_day_flights(df, date, dow):
    """
    Filters the raw schedule df to valid flights on one specific calendar day

    Parameters -->
        df : pandas df containing raw schedule
        date : PostgreSQL date 
         
    """
    mask = (
        (df["EffectiveDate"]    <= date) &
        (df["DiscontinuedDate"] >= date) &
        (df["DOW"].astype(str).apply(lambda x: str(dow) in x.replace(" ", "")))
    )
    return df[mask].copy()

# ── Core algorithm ────────────────────────────────────────────────────────────
def build_turns(df, date, dow, shared_gates=False):
    """
    Returns a list of turn dicts for a given date.
    shared_gates=False → same carrier matching only (Scenario 1)
    shared_gates=True  → cross-carrier, size-compatible matching (Scenario 2)
    """
    day_df     = get_day_flights(df, date, dow)
    arrivals   = day_df[day_df["ArrivalAirport"]    == "CHS"].copy()
    departures = day_df[day_df["Departure Airport"] == "CHS"].copy()
    if arrivals.empty or departures.empty:
        return []

    arrivals["arr_min"]   = arrivals["ArrivalTime"].apply(to_min)
    departures["dep_min"] = departures["DepartureTime"].apply(to_min)
    arrivals["size"]      = arrivals["SubAircraftTypeCode"].map(SIZE_MAP).fillna("MEDIUM")
    departures["size"]    = departures["SubAircraftTypeCode"].map(SIZE_MAP).fillna("MEDIUM")

    arrivals   = arrivals.sort_values("arr_min").reset_index(drop=True)
    departures = departures.sort_values("dep_min").reset_index(drop=True)

    matched_dep = set()
    turns = []

    for _, arr in arrivals.iterrows():
        # Filter candidates: size match + min turnaround gap
        size_match = departures["size"] == arr["size"]
        time_match = departures["dep_min"] >= arr["arr_min"] + TURNAROUND_MIN
        not_matched = ~departures.index.isin(matched_dep)

        if shared_gates:
            # Any carrier, size-compatible
            candidates = departures[size_match & time_match & not_matched]
        else:
            # Same carrier only
            carrier_match = departures["Carrier"] == arr["Carrier"]
            candidates = departures[carrier_match & time_match & not_matched]

        candidates = candidates.sort_values("dep_min")
        if candidates.empty:
            continue

        best = candidates.iloc[0]
        matched_dep.add(best.name)
        turns.append({
            "date":             date,
            "in_carrier":       arr["Carrier"],
            "inbound_flight":   int(arr["FlightNumber"]),
            "arr_min":          arr["arr_min"],
            "arr_ts":           to_timestamp(date, arr["arr_min"]),
            "out_carrier":      best["Carrier"],
            "outbound_flight":  int(best["FlightNumber"]),
            "dep_min":          best["dep_min"],
            "dep_ts":           to_timestamp(date, best["dep_min"]),
            "turnaround_min":   int(best["dep_min"] - arr["arr_min"]),
            "aircraft":         str(arr["SubAircraftTypeCode"]),
            "size":             arr["size"],
            "cross_carrier":    arr["Carrier"] != best["Carrier"],
            "raw_in_id":        int(arr.name) + 1,   # row index → raw_recurring_schedule id
            "raw_out_id":       int(best.name) + 1,
        })

    if not turns:
        return []

    # Sort by shortest turnaround for gate priority (tightest window first)
    turns.sort(key=lambda x: x["turnaround_min"])

    # Gate assignment
    gate_free = {g: 0 for g, _ in GATE_CONFIG}
    for turn in turns:
        assigned = False
        for g, gt in GATE_CONFIG:
            if gate_fits(gt, turn["size"]) and gate_free[g] <= turn["arr_min"]:
                gate_free[g] = turn["dep_min"]
                turn["gate_id"]  = g
                turn["conflict"] = False
                assigned = True
                break
        if not assigned:
            turn["gate_id"]  = -1   # no gate available
            turn["conflict"] = True

    return turns


def summarize_turns(turns):
    conflicts = sum(1 for turn in turns if turn["conflict"])
    scheduled = len(turns) - conflicts
    avg_turnaround = (
        sum(turn["turnaround_min"] for turn in turns) / len(turns)
        if turns else 0
    )
    return {
        "total_turns": len(turns),
        "scheduled_turns": scheduled,
        "conflicts": conflicts,
        "avg_turnaround": avg_turnaround,
    }


def choose_optimal_schedule(scenarios):
    """
    Prefer the scenario that schedules the most flights at real gates.
    Break ties by fewer conflicts, then lower average turnaround time.
    """
    scored = []
    for scenario in scenarios:
        metrics = summarize_turns(scenario["turns"])
        scored.append({**scenario, "metrics": metrics})

    return min(
        scored,
        key=lambda scenario: (
            -scenario["metrics"]["scheduled_turns"],
            scenario["metrics"]["conflicts"],
            scenario["metrics"]["avg_turnaround"],
        ),
    )

def export_turns_to_csv(turns, scenario_name, output_path):
    rows = []
    for turn in sorted(turns, key=lambda item: (item["date"], item["gate_id"], item["arr_min"])):
        rows.append({
            "date": turn["date"].strftime("%Y-%m-%d"),
            "gate_id": "" if turn["conflict"] else turn["gate_id"],
            "inbound_carrier": turn["in_carrier"],
            "inbound_flight": turn["inbound_flight"],
            "arrival_time": turn["arr_ts"].strftime("%Y-%m-%d %H:%M"),
            "outbound_carrier": turn["out_carrier"],
            "outbound_flight": turn["outbound_flight"],
            "departure_time": turn["dep_ts"].strftime("%Y-%m-%d %H:%M"),
            "aircraft": turn["aircraft"],
            "size": turn["size"],
            "turnaround_minutes": turn["turnaround_min"],
            "cross_carrier": turn["cross_carrier"],
            "scheduled_at_gate": not turn["conflict"],
            "scenario": scenario_name,
        })

    output = Path(output_path)
    pd.DataFrame(rows).to_csv(output, index=False)
    return output.resolve()

# ── Database write ────────────────────────────────────────────────────────────
def write_scenario(cur, scenario_name, parameters, all_turns, airline_id_map):
    """Insert one scenario + all its flights and assignments."""

    # 1. Insert scenario_run
    cur.execute("""
        INSERT INTO scenario_runs (name, created_at, parameters)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (scenario_name, datetime.now(), json.dumps(parameters)))
    scenario_id = cur.fetchone()[0]
    print(f"  Created scenario_run id={scenario_id}: {scenario_name}")

    # 2. Insert flights + assignments
    flight_rows      = []
    assignment_rows  = []

    # Fetch current max flight id to offset correctly
    cur.execute("SELECT COALESCE(MAX(id), 0) FROM flights;")
    base_flight_id = cur.fetchone()[0]

    for i, turn in enumerate(all_turns):
        fid = base_flight_id + i + 1
        airline_id = airline_id_map.get(turn["in_carrier"], 1)

        flight_rows.append((
            turn["inbound_flight"],      # flight_number (inbound as reference)
            turn["arr_ts"],              # arrival_time
            turn["dep_ts"],              # departure_time
            airline_id,                  # airline_id
            turn["turnaround_min"],      # turnaround_minutes
            turn["raw_in_id"],           # raw_schedule_id
        ))

        assignment_rows.append((
            fid,                         # flight_id (matches SERIAL sequence)
            max(turn["gate_id"], 1),     # gate_id (use gate 1 as placeholder for conflicts)
            scenario_id,                 # scenario_id
            1 if turn["conflict"] else 0,# is_conflict
            int(turn["arr_ts"].timestamp()), # assigned_at (unix timestamp)
        ))

    execute_values(cur, """
        INSERT INTO flights
            (flight_number, arrival_time, departure_time, airline_id,
             turnaround_minutes, raw_schedule_id)
        VALUES %s
    """, flight_rows)

    execute_values(cur, """
        INSERT INTO flights_assignment
            (flight_id, gate_id, scenario_id, is_conflict, assigned_at)
        VALUES %s
    """, assignment_rows)

    conflicts = sum(1 for t in all_turns if t["conflict"])
    cross     = sum(1 for t in all_turns if t.get("cross_carrier"))
    avg_turn  = sum(t["turnaround_min"] for t in all_turns) / len(all_turns) if all_turns else 0

    print(f"  Flights inserted:     {len(flight_rows):,}")
    print(f"  Assignments inserted: {len(assignment_rows):,}")
    print(f"  Avg turnaround:       {avg_turn:.1f} min")
    print(f"  Conflicts:            {conflicts:,}")
    if cross:
        print(f"  Cross-carrier turns:  {cross:,}")

# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print("Loading CSV...")
    df = pd.read_csv(CSV_PATH)
    df.columns = df.columns.str.strip()
    df["EffectiveDate"]    = pd.to_datetime(df["EffectiveDate"],    format="%d%b%y")
    df["DiscontinuedDate"] = pd.to_datetime(df["DiscontinuedDate"], format="%d%b%y")

    # Build full year of turns for both scenarios
    start = datetime(2024, 2, 1)
    turns_same   = []   # Scenario 1: same-carrier
    turns_shared = []   # Scenario 2: shared gates

    print("Running algorithm across full year (Feb 2024 – Jan 2025)...")
    for i in range(366):
        date = start + timedelta(days=i)
        dow  = date.isoweekday()
        turns_same.extend(  build_turns(df, date, dow, shared_gates=False))
        turns_shared.extend(build_turns(df, date, dow, shared_gates=True))

    scenario_1 = {
        "name": "Scenario 1 — Same-Carrier Gate Assignment",
        "parameters": {
            "turnaround_min": TURNAROUND_MIN,
            "num_gates": 15,
            "shared_gates": False,
            "priority": "earliest_departure",
            "date_range": "2024-02-01 to 2025-01-31",
        },
        "turns": turns_same,
    }
    scenario_2 = {
        "name": "Scenario 2 — Shared Gates (Cross-Carrier, Size-Compatible)",
        "parameters": {
            "turnaround_min": TURNAROUND_MIN,
            "num_gates": 15,
            "shared_gates": True,
            "priority": "shortest_turnaround_first",
            "size_classes": {"SMALL": [1, 2, 3, 4], "MEDIUM": [5, 6, 7, 8, 9, 10, 11, 12], "LARGE": [13, 14, 15]},
            "date_range": "2024-02-01 to 2025-01-31",
        },
        "turns": turns_shared,
    }
    scenarios = [scenario_1, scenario_2]

    for scenario in scenarios:
        metrics = summarize_turns(scenario["turns"])
        print(
            f'{scenario["name"]}: {metrics["total_turns"]:,} turns, '
            f'{metrics["scheduled_turns"]:,} gate assignments, '
            f'{metrics["conflicts"]:,} conflicts, '
            f'{metrics["avg_turnaround"]:.1f} avg turnaround minutes'
        )

    optimal = choose_optimal_schedule(scenarios)
    output_path = export_turns_to_csv(optimal["turns"], optimal["name"], OUTPUT_CSV_PATH)

    print(f"\nOptimal schedule selected: {optimal['name']}")
    print(f"CSV exported to: {output_path}")

    if psycopg2 is None:
        print("\npsycopg2 is not installed, so database writes were skipped.")
        return str(output_path)

    try:
        print("\nConnecting to database...")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        cur.execute("SELECT carrier, id FROM airlines;")
        airline_id_map = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("TRUNCATE TABLE flights_assignment RESTART IDENTITY CASCADE;")
        cur.execute("TRUNCATE TABLE flights           RESTART IDENTITY CASCADE;")
        cur.execute("TRUNCATE TABLE scenario_runs     RESTART IDENTITY CASCADE;")

        for scenario in scenarios:
            print(f"\n--- Writing {scenario['name']} ---")
            write_scenario(
                cur,
                scenario_name=scenario["name"],
                parameters=scenario["parameters"],
                all_turns=scenario["turns"],
                airline_id_map=airline_id_map,
            )

        conn.commit()
        cur.close()
        conn.close()
        print("\nAll done! Scenarios written to database and optimal CSV exported.")
    except Exception as exc:
        print(f"\nDatabase write skipped due to error: {exc}")
        print("The optimal CSV schedule was still generated successfully.")

    return str(output_path)

if __name__ == "__main__":
    run()
