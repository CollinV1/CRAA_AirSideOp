import csv
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import Client
from db import get_supabase

app = FastAPI()

origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Aircraft MGT (minimum ground time in minutes) ─────────────────────────────
# Source: Delta Corporate Network MGT chart eff. 11Nov24
MGT_MAP = {
    'CR7':40,'CR9':40,'ERJ':40,'E70':40,'E75':40,'E7W':40,
    '319':55,'320':55,'321':55,'32A':55,'32B':55,'32N':55,
    '738':55,'739':55,'73W':55,'73H':55,'73J':55,'73G':55,
    '7M8':55,'7M9':55,'E90':45,'E95':45,'717':45,'221':45,'223':45,
    '757':60,
}
DEFAULT_MGT = 45
PLANE_MATCH_BONUS = 20
SAME_AIRLINE_BONUS = 5
LONG_EXCESS_THRESHOLD = 90
LONG_EXCESS_PENALTY = 3
MAX_EXCESS_BUFFER = 75

# ── Size classification ────────────────────────────────────────────────────────
SIZE_MAP = {
    'CR7':'SMALL','CR9':'SMALL','ERJ':'SMALL','E70':'SMALL','E75':'SMALL','E7W':'SMALL',
    '319':'MEDIUM','320':'MEDIUM','321':'MEDIUM','32A':'MEDIUM','32B':'MEDIUM','32N':'MEDIUM',
    '738':'MEDIUM','739':'MEDIUM','73W':'MEDIUM','73H':'MEDIUM','73J':'MEDIUM','73G':'MEDIUM',
    '7M8':'MEDIUM','7M9':'MEDIUM','E90':'MEDIUM','E95':'MEDIUM',
    '717':'MEDIUM','221':'MEDIUM','223':'MEDIUM','757':'LARGE',
}

# ── Gate config matches Supabase gates table (text IDs, concourse A and B) ────
# Gates are stored as text IDs like "A1", "B3" in Supabase
GATE_SIZE = {
    'B1':'SMALL','B2':'SMALL','B3':'SMALL','B4':'SMALL',
    'B5':'MEDIUM','B6':'MEDIUM','B7':'MEDIUM','B8':'MEDIUM',
    'B9':'MEDIUM','B10':'MEDIUM','B11':'MEDIUM','B12':'LARGE',
    'A1':'MEDIUM','A2':'MEDIUM','A3':'MEDIUM','A4':'LARGE','A5':'LARGE',
}

GATE_ASSIGNMENT_ORDER = {
    'SMALL': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'A1', 'A2', 'A3'],
    'MEDIUM': ['A1', 'A2', 'A3', 'B5', 'B6', 'B7', 'A4', 'A5', 'B8', 'B9', 'B10', 'B11', 'B12'],
    'LARGE': ['A4', 'A5', 'B12', 'A1', 'A2', 'A3'],
}

def gate_fits(gate_id, aircraft_size):
    gate_size = GATE_SIZE.get(gate_id, 'MEDIUM')
    if gate_size == 'SMALL':  return aircraft_size == 'SMALL'
    if gate_size == 'MEDIUM': return aircraft_size in ('SMALL', 'MEDIUM')
    return True  # LARGE fits all


def candidate_gates_for_size(aircraft_size):
    # Start with a preferred concourse mix by aircraft size, then fall back to any
    # remaining compatible gates so we still produce a complete schedule.
    preferred = GATE_ASSIGNMENT_ORDER.get(aircraft_size, list(GATE_SIZE.keys()))
    remaining = [gate_id for gate_id in GATE_SIZE.keys() if gate_id not in preferred]
    return preferred + remaining


def score_connection_match(arrival, departure, turnaround, turnaround_min):
    # Build turns around the tighter of the user threshold and the aircraft MGT so
    # we reduce excess ground time rather than just accepting the first legal pair.
    aircraft = str(arrival.get("subaircrafttypecode", "")).strip()
    mgt = MGT_MAP.get(aircraft, DEFAULT_MGT)
    target_turnaround = max(turnaround_min, mgt)
    excess_minutes = max(0, turnaround - target_turnaround)
    score = excess_minutes

    # Once a turn gets far beyond target, penalize it more aggressively so long idle
    # gaps lose to more realistic pairings.
    if excess_minutes > LONG_EXCESS_THRESHOLD:
        score += (excess_minutes - LONG_EXCESS_THRESHOLD) * LONG_EXCESS_PENALTY

    # Same-plane and same-airline continuity usually yields more operationally
    # realistic assignments, so we bias toward those pairings when available.
    if arrival.get("plane_id") and arrival.get("plane_id") == departure.get("plane_id"):
        score -= PLANE_MATCH_BONUS

    if arrival.get("airline_id") == departure.get("airline_id"):
        score -= SAME_AIRLINE_BONUS

    return score, excess_minutes, target_turnaround

def get_status(turnaround_min, mgt):
    excess = turnaround_min - mgt
    if excess >= 195: return 'CRITICAL'
    if excess >= 90:  return 'LONG'
    if excess >= 45:  return 'MODERATE'
    return 'OK'

STATUS_COLORS = {
    'OK':       '#C6EFCE',
    'MODERATE': '#FFEB9C',
    'LONG':     '#FFC7CE',
    'CRITICAL': '#C00000',
    'CONFLICT': '#C00000',
}

BATCH_SIZE = 500
EXPANDED_TABLE_NAME = "flight_instances_test"

def assign_gates(connections):
    """
    Core gate assignment algorithm.
    Input: list of flight connection rows from flight_connections table
    Output: same rows with gate_id and status added
    """
    # Schedule the tightest turns first so scarce gate windows are claimed by the
    # pairings with the least slack.
    valid = [c for c in connections if c.get('has_departure') and c.get('turnaround_minutes')]
    valid.sort(key=lambda x: float(x['turnaround_minutes']))

    gate_free = {gid: None for gid in GATE_SIZE.keys()}  # gate -> departure_datetime
    results = []

    for conn in valid:
        aircraft  = str(conn.get('subaircrafttypecode', '')).strip()
        size      = SIZE_MAP.get(aircraft, 'MEDIUM')
        mgt       = MGT_MAP.get(aircraft, DEFAULT_MGT)
        arr_time  = conn.get('arrival_datetime')
        dep_time  = conn.get('departure_datetime')
        turnaround= float(conn.get('turnaround_minutes', 0))

        assigned_gate = None

        # Walk the preferred gate order for this aircraft size and take the first
        # compatible gate that is free through the departure time.
        for gate_id in candidate_gates_for_size(size):
            if not gate_fits(gate_id, size):
                continue
            # Gate is free if no previous flight or previous flight already departed
            prev_dep = gate_free[gate_id]
            if prev_dep is None or arr_time >= prev_dep:
                gate_free[gate_id] = dep_time
                assigned_gate = gate_id
                break

        status = get_status(turnaround, mgt) if assigned_gate else 'CONFLICT'
        excess = turnaround - mgt

        results.append({
            'arrival_id':            conn.get('arrival_id'),
            'arrival_flight_number': conn.get('arrival_flight_number'),
            'arrival_datetime':      arr_time,
            'departure_flight_number':conn.get('departure_flight_number'),
            'departure_datetime':    dep_time,
            'subaircrafttypecode':   aircraft,
            'plane_id':              conn.get('plane_id'),
            'turnaround_minutes':    turnaround,
            'mgt_minutes':           mgt,
            'excess_minutes':        round(excess, 1),
            'gate_id':               assigned_gate or 'CONFLICT',
            'status':                status,
            'color':                 STATUS_COLORS.get(status, '#FFFFFF'),
            'has_departure':         conn.get('has_departure'),
        })

    # Also include flights with no departure
    no_dep = [c for c in connections if not c.get('has_departure')]
    for conn in no_dep:
        results.append({
            'arrival_id':            conn.get('arrival_id'),
            'arrival_flight_number': conn.get('arrival_flight_number'),
            'arrival_datetime':      conn.get('arrival_datetime'),
            'departure_flight_number': None,
            'departure_datetime':    None,
            'subaircrafttypecode':   conn.get('subaircrafttypecode'),
            'plane_id':              conn.get('plane_id'),
            'turnaround_minutes':    None,
            'mgt_minutes':           None,
            'excess_minutes':        None,
            'gate_id':               'PARKED',
            'status':                'NO_DEPARTURE',
            'color':                 '#D9D2E9',
            'has_departure':         False,
        })

    return results


def parse_datetime(value):
    return datetime.fromisoformat(value)


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

    if rows:
        flight_ids = sorted({row["flight_id"] for row in rows if row.get("flight_id") is not None})
        flights = []
        if flight_ids:
            flights = (
                supabase.table("flights_test")
                .select("id,raw_schedule_id")
                .in_("id", flight_ids)
                .execute()
            ).data or []

        raw_schedule_by_flight = {row["id"]: row.get("raw_schedule_id") for row in flights}

        for row in rows:
            raw_schedule_id = raw_schedule_by_flight.get(row["flight_id"])
            row["plane_id"] = raw_schedule_id or row["flight_id"]

    filtered = []
    for row in rows:
        arrival_dt = parse_datetime(row["arrival_datetime"])
        departure_dt = parse_datetime(row["departure_datetime"])
        if start_date and arrival_dt.date() < start_date and departure_dt.date() < start_date:
            continue
        if end_date and arrival_dt.date() > end_date and departure_dt.date() > end_date:
            continue
        filtered.append(row)
    return filtered


def build_connections_for_day(instances: list[dict], service_date: date, turnaround_min: int) -> list[dict]:
    arrivals = []
    departures = []

    for row in instances:
        arrival_dt = parse_datetime(row["arrival_datetime"])
        departure_dt = parse_datetime(row["departure_datetime"])
        row_size = SIZE_MAP.get(str(row["subaircrafttypecode"]), "MEDIUM")

        if row["arrival_airport"] == "CHS" and arrival_dt.date() == service_date:
            arrivals.append({
                **row,
                "arrival_dt": arrival_dt,
                "size": row_size,
            })

        if row["departure_airport"] == "CHS" and departure_dt.date() == service_date:
            departures.append({
                **row,
                "departure_dt": departure_dt,
                "size": row_size,
            })

    arrivals.sort(key=lambda row: row["arrival_dt"])
    departures.sort(key=lambda row: row["departure_dt"])

    matched_departures = set()
    connections = []

    for arrival in arrivals:
        candidates = []
        aircraft = str(arrival.get("subaircrafttypecode", "")).strip()
        mgt = MGT_MAP.get(aircraft, DEFAULT_MGT)
        max_allowed_turnaround = max(turnaround_min, mgt) + MAX_EXCESS_BUFFER
        for departure in departures:
            if departure["id"] in matched_departures:
                continue
            if departure["size"] != arrival["size"]:
                continue
            turnaround = (departure["departure_dt"] - arrival["arrival_dt"]).total_seconds() / 60
            if turnaround < turnaround_min:
                continue
            # Skip departures that would leave the aircraft sitting far beyond a
            # reasonable post-MGT window; it is better to leave the arrival unmatched
            # than to inflate the schedule with unrealistic excess ground time.
            if turnaround > max_allowed_turnaround:
                continue
            score, excess_minutes, target_turnaround = score_connection_match(
                arrival,
                departure,
                turnaround,
                turnaround_min,
            )
            candidates.append((departure, turnaround, score, excess_minutes, target_turnaround))

        if candidates:
            # Pick the pairing with the lowest turnaround-quality score, then break
            # ties toward the shorter actual turn.
            best, turnaround, _, _, _ = min(candidates, key=lambda item: (item[2], item[1]))
            matched_departures.add(best["id"])
            connections.append({
                "arrival_id": arrival["id"],
                "arrival_flight_number": int(arrival["flight_number"]),
                "arrival_datetime": arrival["arrival_dt"].isoformat(),
                "departure_flight_number": int(best["flight_number"]),
                "departure_datetime": best["departure_dt"].isoformat(),
                "subaircrafttypecode": str(arrival["subaircrafttypecode"]),
                "plane_id": arrival.get("plane_id"),
                "turnaround_minutes": round(turnaround, 1),
                "has_departure": True,
            })
        else:
            connections.append({
                "arrival_id": arrival["id"],
                "arrival_flight_number": int(arrival["flight_number"]),
                "arrival_datetime": arrival["arrival_dt"].isoformat(),
                "departure_flight_number": None,
                "departure_datetime": None,
                "subaircrafttypecode": str(arrival["subaircrafttypecode"]),
                "plane_id": arrival.get("plane_id"),
                "turnaround_minutes": None,
                "has_departure": False,
            })

    return connections


def summarize_assigned_turns(rows: list[dict]) -> dict:
    conflicts = sum(1 for row in rows if row["status"] == "CONFLICT")
    valid_turns = [row for row in rows if row.get("turnaround_minutes") is not None]
    avg_turnaround = round(
        sum(float(row["turnaround_minutes"]) for row in valid_turns) / len(valid_turns),
        1,
    ) if valid_turns else 0
    return {
        "total_turns": len(rows),
        "scheduled_turns": len(rows) - conflicts,
        "conflicts": conflicts,
        "avg_turnaround": avg_turnaround,
    }


def run_turnaround_scenarios(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
    turnaround_min: int = 45,
    replace_existing: bool = True,
) -> dict:
    del replace_existing

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
    })
    if not service_dates:
        return {
            "scenarios": [],
            "optimal_scenario": None,
            "optimal_turns": [],
            "flight_instances_used": len(instances),
        }

    assigned_rows = []
    for service_date in service_dates:
        connections = build_connections_for_day(instances, service_date, turnaround_min)
        assigned_rows.extend(assign_gates(connections))

    metrics = summarize_assigned_turns(assigned_rows)
    return {
        "flight_instances_used": len(instances),
        "scenarios": [{
            "scenario_id": None,
            "name": "Turnaround Example Gate Assignment",
            "metrics": metrics,
        }],
        "optimal_scenario": {
            "name": "Turnaround Example Gate Assignment",
            "metrics": metrics,
        },
        "optimal_turns": assigned_rows,
    }


def export_optimal_schedule_csv(rows: list[dict], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "arrival_id",
        "arrival_flight_number",
        "arrival_datetime",
        "departure_flight_number",
        "departure_datetime",
        "subaircrafttypecode",
        "plane_id",
        "turnaround_minutes",
        "mgt_minutes",
        "excess_minutes",
        "gate_id",
        "status",
        "color",
        "has_departure",
    ]

    with output.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})

    return output


def build_and_store_optimal_schedule(
    supabase: Client,
    start_date: date | None = None,
    end_date: date | None = None,
    turnaround_min: int = 45,
    replace_existing: bool = True,
) -> dict:
    return run_turnaround_scenarios(
        supabase,
        start_date=start_date,
        end_date=end_date,
        turnaround_min=turnaround_min,
        replace_existing=replace_existing,
    )


# ══════════════════════════════════════════════════════════════════════════════
# EXISTING ROUTES — kept from AL's work
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/hello")
def read_root():
    return {"message": "Hello from FastAPI"}

@app.get("/flights")
def get_flights(supabase: Client = Depends(get_supabase)):
    res = supabase.table("flight_instances").select("*").execute()
    return res.data


# ══════════════════════════════════════════════════════════════════════════════
# GATE ASSIGNMENT ROUTES — Emmanuel's contribution
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/gates")
def get_gates(supabase: Client = Depends(get_supabase)):
    """
    Returns all gates from Supabase with their size class.
    Used by the frontend map.
    """
    res = supabase.table("gates").select("*").execute()
    gates = res.data or []
    for g in gates:
        g['size_class'] = GATE_SIZE.get(g['id'], 'MEDIUM')
    return {"gates": gates}


@app.get("/gates/schedule")
def get_gate_schedule(
    date: str = Query(..., description="Date in YYYY-MM-DD format e.g. 2025-01-15"),
    supabase: Client = Depends(get_supabase)
):
    """
    Returns gate assignments for a specific date.
    Reads from flight_connections_jan2025, runs gate assignment algorithm,
    returns results grouped by gate for the frontend map.
    """
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD format")

    # Pull from flight_connections for the target date
    # Filter arrivals on that date
    date_start = f"{date}T00:00:00"
    date_end   = f"{date}T23:59:59"

    res = supabase.table("flight_connections")\
        .select("*")\
        .gte("arrival_datetime", date_start)\
        .lte("arrival_datetime", date_end)\
        .execute()

    if not res.data:
        raise HTTPException(
            status_code=404,
            detail=f"No flight connections found for {date}. Make sure flight_connections has data for this date."
        )

    connections = res.data

    # Run gate assignment
    assigned = assign_gates(connections)

    # Group by gate for the map
    gate_schedule = {gid: [] for gid in GATE_SIZE.keys()}
    gate_schedule['CONFLICT'] = []
    gate_schedule['PARKED']   = []

    for turn in assigned:
        gid = turn['gate_id']
        gate_schedule.setdefault(gid, []).append(turn)

    # Build gate summary for map coloring
    priority = ['CONFLICT', 'CRITICAL', 'LONG', 'MODERATE', 'OK', 'NO_DEPARTURE']
    gates_result = []
    for gate_id, size in GATE_SIZE.items():
        turns = sorted(gate_schedule.get(gate_id, []), key=lambda x: x['arrival_datetime'] or '')
        statuses = [t['status'] for t in turns]
        overall  = next((s for s in priority if s in statuses), 'EMPTY')
        gates_result.append({
            "gate_id":    gate_id,
            "concourse":  gate_id[0],
            "size_class": size,
            "status":     overall,
            "color":      STATUS_COLORS.get(overall, '#E0E0E0'),
            "turn_count": len(turns),
            "turns":      turns,
        })

    # Summary stats
    conflicts = sum(1 for t in assigned if t['status'] == 'CONFLICT')
    ok_turns  = sum(1 for t in assigned if t['status'] == 'OK')
    long_turns= sum(1 for t in assigned if t['status'] in ('LONG', 'CRITICAL'))
    valid_t   = [t for t in assigned if t['turnaround_minutes']]
    avg_turn  = round(sum(float(t['turnaround_minutes']) for t in valid_t) / len(valid_t), 1) if valid_t else 0

    return {
        "date":     date,
        "day":      target.strftime("%A"),
        "gates":    gates_result,
        "summary": {
            "total_turns":    len(assigned),
            "avg_turnaround": avg_turn,
            "ok_turns":       ok_turns,
            "long_turns":     long_turns,
            "conflicts":      conflicts,
        }
    }


@app.post("/gates/assign")
def run_gate_assignment(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    save: bool = Query(False, description="Set true to save results to flights_assignment table"),
    scenario_name: str = Query("Gate Assignment Run", description="Name for this scenario run"),
    supabase: Client = Depends(get_supabase)
):
    """
    Runs gate assignment algorithm for a date and optionally saves
    results to flights_assignment and scenario_runs tables in Supabase.
    """
    try:
        target = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date must be YYYY-MM-DD format")

    date_start = f"{date}T00:00:00"
    date_end   = f"{date}T23:59:59"

    res = supabase.table("flight_connections")\
        .select("*")\
        .gte("arrival_datetime", date_start)\
        .lte("arrival_datetime", date_end)\
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail=f"No data found for {date}")

    assigned = assign_gates(res.data)

    if save:
        # Create scenario run
        scenario_res = supabase.table("scenario_runs").insert({
            "name":       scenario_name,
            "created_at": datetime.now().isoformat(),
            "parameters": {
                "date":           date,
                "algorithm":      "V5 Greedy Interval Scheduling",
                "mgt_source":     "Delta MGT chart 11Nov24",
                "total_turns":    len(assigned),
            }
        }).execute()

        scenario_id = scenario_res.data[0]['id']

        # Save gate assignments
        records = [
            {
                "flight_id":   t['arrival_id'],
                "gate_id":     t['gate_id'] if t['gate_id'] not in ('CONFLICT','PARKED') else 'B1',
                "scenario_id": scenario_id,
                "is_conflict": 1 if t['status'] == 'CONFLICT' else 0,
                "assigned_at": int(datetime.now().timestamp()),
            }
            for t in assigned if t.get('arrival_id')
        ]

        supabase.table("flights_assignment").insert(records).execute()

        return {
            "message":     f"Gate assignments saved for {date}",
            "scenario_id": scenario_id,
            "total_turns": len(assigned),
            "conflicts":   sum(1 for t in assigned if t['status'] == 'CONFLICT'),
        }

    return {
        "date":      date,
        "day":       target.strftime("%A"),
        "assigned":  assigned,
        "total_turns": len(assigned),
        "conflicts": sum(1 for t in assigned if t['status'] == 'CONFLICT'),
    }


@app.get("/scenarios")
def get_scenarios(supabase: Client = Depends(get_supabase)):
    """Returns all scenario runs — for Power BI dashboard."""
    res = supabase.table("scenario_runs").select("*").execute()
    return {"scenarios": res.data}

@app.get("/gates/schedule/export")
def export_gate_schedule(
    date: str = Query(...),
    supabase: Client = Depends(get_supabase)
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    date_start = f"{date}T00:00:00"
    date_end   = f"{date}T23:59:59"

    res = supabase.table("flight_connections")\
        .select("*")\
        .gte("arrival_datetime", date_start)\
        .lte("arrival_datetime", date_end)\
        .execute()

    if not res.data:
        raise HTTPException(status_code=404, detail=f"No data found for {date}")

    assigned = assign_gates(res.data)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=assigned[0].keys())
    writer.writeheader()
    writer.writerows(assigned)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=gate_schedule_{date}.csv"}
    )
