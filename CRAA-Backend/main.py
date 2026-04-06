import csv
import io
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from supabase import Client
from db import get_supabase
from expansion import expand_raw_flights_to_instances, replace_flights
from powerBI import get_embed_config
from turnaround import build_and_store_optimal_schedule, export_optimal_schedule_csv, run_turnaround_scenarios

app = FastAPI()

# TODO
GENERATED_DIR = Path(__file__).resolve().parent / "generated"
OPTIMAL_SCHEDULE_CSV = GENERATED_DIR / "optimal_flight_schedule.csv"
RAW_TABLE_NAME = "raw_flights_test"
NORMALIZED_TABLE_NAME = "flights_test"
EXPANDED_TABLE_NAME = "flight_instances_test"

# Allow React dev server
# origins = [
#     "http://localhost:5173",
#     "http://127.0.0.1:5173",
#     "http://127.0.0.1:5500",
#     "http://localhost:5500",
#     "null",
# ]

# TODO: modify allow_origins to be safer, not allow all links, purely for testing

app.add_middleware(

    CORSMiddleware,
    # allow_origins=origins,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TODO Currently expansion is done wholesale on the entire .csv --> modify so expansion is conducted only for the desired timeframe 
class ExpansionRequest(BaseModel):
    # date range for expansion individual expansion
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    # whether to clear existing flight instances
    replace_existing: bool = True

# TODO Once ExpansionRequest is modified to expand only ona given range, modify to run scenario on the entire populated table resulting from expansion
class ScenarioRunRequest(BaseModel):
    start_date: date
    end_date: date
    turnaround_min: int = 45
    replace_existing: bool = True

# defines column names for raw .csv, used for parsing raw flights
RAW_FLIGHT_COLUMNS = [
    "Carrier",
    "FlightNumber",
    "ServiceType",
    "EffectiveDate",
    "DiscontinuedDate",
    "DOW",
    "Departure Airport",
    "DepartureTime",
    "ArrivalAirport",
    "ArrivalTime",
    "SubAircraftTypeCode",
]


def parse_raw_flights_csv(contents: bytes) -> list[dict]:
    """
    Verifies .csv file format matches table layout of raw_flights

    Parameters -->
        contents: dictionary of .csv contents

    Returns -->
        rows: array of .csv contents
    """
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is missing a header row.")

    missing = [col for col in RAW_FLIGHT_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV is missing required columns: {', '.join(missing)}"
        )

    rows = []
    for line_number, row in enumerate(reader, start=2):
        if not any(row.values()):
            continue

        try:
            parsed_row = {
                "Carrier": row["Carrier"],
                "FlightNumber": int(row["FlightNumber"]),
                "ServiceType": row["ServiceType"] or None,
                "EffectiveDate": row["EffectiveDate"],
                "DiscontinuedDate": row["DiscontinuedDate"],
                "DOW": row["DOW"],
                "Departure Airport": row["Departure Airport"],
                "DepartureTime": int(row["DepartureTime"]),
                "ArrivalAirport": row["ArrivalAirport"],
                "ArrivalTime": int(row["ArrivalTime"]),
                "SubAircraftTypeCode": row["SubAircraftTypeCode"],
            }
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid numeric value on line {line_number}: {exc}"
            ) from exc

        rows.append(parsed_row)

    return rows


def replace_raw_flights_table(supabase: Client, rows: list[dict]) -> int:
    '''
    Clears raw_flights tables and populates them with new .csv data.
    Calls Supabase defined function: public.reset_tables

    Parameters -->
        Supabase Client
        list[dict]: incoming .csv data  
        
    Returns -->
        int: number of rows entered
    '''
    # function public.reset_tables defined in Supabase
    supabase.rpc("reset_tables").execute()

    inserted_count = 0
    batch_size = 500
    for index in range(0, len(rows), batch_size):
        batch = rows[index:index + batch_size]
        inserted = supabase.table(RAW_TABLE_NAME).insert(batch).execute().data or []
        inserted_count += len(inserted)
    return inserted_count

def replace_flight_instances_table(supabase: Client, rows: list[dict]):
    '''
    Clears flight instances
    '''
    supabase.rpc("reset_flight_instances").execute()

@app.get("/get-embed-token")
def get_embed_token():
    '''
    Retrievies the embed token. Calls get_embed_config() defined in powerBI.py
    '''
    try:
        return get_embed_config()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate Power BI embed config: {exc}") from exc


'''
TODO: retrieve flight information from Supabase 

Dependencies: Client
Purpose: access flight info from flight_instances table  
Output: 

'''
@app.get("/flights")
def get_flights(supabase: Client = Depends(get_supabase)):
    '''
    Skeleton function for retreiving flight information from Supabase
    '''
    res = supabase.table(EXPANDED_TABLE_NAME).select("*").execute()
    return res.data

@app.post("/expansion/run")
def run_expansion(
    request: ExpansionRequest,
    supabase: Client = Depends(get_supabase),
):
    '''
    Expands flight information. NORMALIZED_TABLE_NAME (flights) into EXPANDED_TABLE_NAME (flight_instances)
    '''
    try:
        return expand_raw_flights_to_instances(
            supabase,
            start_date=request.start_date,
            end_date=request.end_date,
            replace_existing=request.replace_existing,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to expand {NORMALIZED_TABLE_NAME} into {EXPANDED_TABLE_NAME}: {exc}") from exc

@app.post("/scenarios/run")
def run_scenarios(
    request: ScenarioRunRequest,
    supabase: Client = Depends(get_supabase),
):
    try:
        return run_turnaround_scenarios(
            supabase,
            start_date=request.start_date,
            end_date=request.end_date,
            turnaround_min=request.turnaround_min,
            replace_existing=request.replace_existing,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run turnaround scenarios from {EXPANDED_TABLE_NAME}: {exc}") from exc


@app.post("/pipeline/upload-and-run")
async def upload_and_run_pipeline(
    file: UploadFile = File(...),
    supabase: Client = Depends(get_supabase),
):
    '''
    Upload pipeline
    user uploads .csv --> raw_flights_test populated --> flights_test populated 

    TODO: automate pipeline to include
    --> user selects date range --> flight_instances populated --> flight_connections populated --> schedule scenario build --> data sent to supabase
    '''

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    try:
        contents = await file.read()
        rows = parse_raw_flights_csv(contents)
        if not rows:
            raise HTTPException(status_code=400, detail="Uploaded CSV contains no data rows.")

        raw_inserted = replace_raw_flights_table(supabase, rows)
        normalization_result = replace_flights(supabase)
        return {
            "message": "Upload and normalization completed successfully.",
            "file_name": file.filename,
            "raw_rows_inserted": raw_inserted,
            "raw_table": RAW_TABLE_NAME,
            "normalized_table": NORMALIZED_TABLE_NAME,
            "normalization": normalization_result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {exc}") from exc


@app.post("/pipeline/build-schedule")
def build_schedule_pipeline(
    request: ScenarioRunRequest,
    supabase: Client = Depends(get_supabase),
):
    """
    Schedule pipeline:
    flights_test -> flight_instances_test (for requested date range) -> schedule tables -> downloadable CSV
    """
    try:
        if request.start_date > request.end_date:
            raise HTTPException(status_code=400, detail="start_date must be on or before end_date.")

        expansion_result = expand_raw_flights_to_instances(
            supabase,
            start_date=request.start_date,
            end_date=request.end_date,
            replace_existing=True,
        )

        schedule_result = build_and_store_optimal_schedule(
            supabase,
            start_date=request.start_date,
            end_date=request.end_date,
            turnaround_min=request.turnaround_min,
            replace_existing=request.replace_existing,
        )

        optimal_turns = schedule_result.pop("optimal_turns", [])
        if not optimal_turns:
            raise HTTPException(status_code=404, detail="No optimal schedule could be generated from flight_instances_test.")

        csv_path = export_optimal_schedule_csv(optimal_turns, OPTIMAL_SCHEDULE_CSV)
        return {
            "message": "Schedule build completed successfully.",
            "normalized_table": NORMALIZED_TABLE_NAME,
            "expanded_table": EXPANDED_TABLE_NAME,
            "date_range": {
                "start_date": str(request.start_date) if request.start_date else None,
                "end_date": str(request.end_date) if request.end_date else None,
            },
            "turnaround_min": request.turnaround_min,
            "expansion": expansion_result,
            "scheduling": schedule_result,
            "schedule_csv_path": str(csv_path),
            "download_url": "/downloads/optimal-flight-schedule.csv",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Schedule build failed: {exc}") from exc


@app.get("/downloads/optimal-flight-schedule.csv")
def download_optimal_schedule_csv():
    if not OPTIMAL_SCHEDULE_CSV.exists():
        raise HTTPException(status_code=404, detail="No generated schedule CSV is available yet.")

    return FileResponse(
        path=OPTIMAL_SCHEDULE_CSV,
        media_type="text/csv",
        filename="optimal_flight_schedule.csv",
    )

# TODO
@app.get("/powerbi/optimized-schedule")
def get_powerbi_optimized_schedule(
    scenario_id: Optional[int] = None,
    supabase: Client = Depends(get_supabase),
):
    """
    Returns the canonical optimized gate schedule for Power BI.
    If no scenario_id is provided, the most recently created scenario is used.
    """
    if scenario_id is None:
        scenario_res = (
            supabase.table("scenario_runs")
            .select("id,name,created_at,parameters")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not scenario_res.data:
            raise HTTPException(status_code=404, detail="No optimized schedule found in scenario_runs.")
        scenario = scenario_res.data[0]
    else:
        scenario_res = (
            supabase.table("scenario_runs")
            .select("id,name,created_at,parameters")
            .eq("id", scenario_id)
            .limit(1)
            .execute()
        )
        if not scenario_res.data:
            raise HTTPException(status_code=404, detail=f"Scenario {scenario_id} not found.")
        scenario = scenario_res.data[0]

    assignments_res = (
        supabase.table("flights_assignment_test")
        .select("id,flight_id,gate_id,scenario_id,is_conflict,assigned_at")
        .eq("scenario_id", scenario["id"])
        .order("flight_id")
        .execute()
    )
    assignments = assignments_res.data or []
    if not assignments:
        return {
            "scenario": scenario,
            "count": 0,
            "data": [],
        }

    flight_ids = sorted({assignment["flight_id"] for assignment in assignments})
    flights_res = (
        supabase.table("flights")
        .select("id,flight_number,arrival_time,departure_time,airline_id,turnaround_minutes,raw_schedule_id")
        .in_("id", flight_ids)
        .execute()
    )
    flights = {flight["id"]: flight for flight in (flights_res.data or [])}

    gate_ids = sorted({assignment["gate_id"] for assignment in assignments if assignment.get("gate_id")})
    gates = {}
    if gate_ids:
        gates_res = (
            supabase.table("gates")
            .select("id,concourse,is_active")
            .in_("id", gate_ids)
            .execute()
        )
        gates = {gate["id"]: gate for gate in (gates_res.data or [])}

    rows = []
    for assignment in assignments:
        flight = flights.get(assignment["flight_id"])
        if not flight:
            continue
        gate = gates.get(assignment["gate_id"], {})
        rows.append({
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "scenario_created_at": scenario["created_at"],
            "assignment_id": assignment["id"],
            "flight_id": assignment["flight_id"],
            "flight_number": flight["flight_number"],
            "airline_id": flight["airline_id"],
            "arrival_time": flight["arrival_time"],
            "departure_time": flight["departure_time"],
            "turnaround_minutes": flight.get("turnaround_minutes"),
            "raw_schedule_id": flight.get("raw_schedule_id"),
            "gate_id": assignment["gate_id"],
            "concourse": gate.get("concourse"),
            "gate_is_active": gate.get("is_active"),
            "is_conflict": assignment["is_conflict"],
            "assigned_at": assignment["assigned_at"],
        })

    rows.sort(key=lambda row: (row["arrival_time"], row["gate_id"], row["flight_number"]))

    return {
        "scenario": scenario,
        "count": len(rows),
        "data": rows,
    }

