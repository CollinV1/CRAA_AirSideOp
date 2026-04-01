import csv
import io
from datetime import date
from typing import Optional

from fastapi import FastAPI, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import Client
from db import get_supabase
from expansion import expand_raw_flights_to_instances
from powerBI import get_embed_config
from turnaround import run_turnaround_scenarios

app = FastAPI()

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

class ExpansionRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    replace_existing: bool = True


class ScenarioRunRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    turnaround_min: int = 45


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


@app.post("/upload-raw-data")
async def upload_raw_data(
    file: UploadFile = File(...),
    supabase: Client = Depends(get_supabase),
):
    """
    Updates raw_flights

    Parameters -->
        file: .csv file user wishes to upload
        supabase: calls get_supabase to get client

    Returns -->
        message and filename, raw_flights is populated with data from .csv
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    contents = await file.read()
    rows = parse_raw_flights_csv(contents)

    if not rows:
        raise HTTPException(status_code=400, detail="Uploaded CSV contains no data rows.")

    # TODO: change raw_flights_test to raw_flights
    supabase.table("raw_flights_test").delete().neq("Carrier", "").execute()

    result = supabase.table("raw_flights_test").insert(rows).execute()

    return {
        "message": "Raw CSV uploaded to raw_flights.",
        "file_name": file.filename,
        # "rows_inserted": len(result.data or []),
    }

''' 
TODO: PowerBI Embedded link

Dependencies: MSAL, requests
Purpose: Create PowerBI endpoint callable by frontend
Output: json embedToken + embedURL 

'''


@app.get("/get-embed-token")
def get_embed_token():
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
    res = supabase.table("flight_instances").select("*").execute()
    return res.data

@app.post("/expansion/run")
def run_expansion(
    request: ExpansionRequest,
    supabase: Client = Depends(get_supabase),
):
    try:
        return expand_raw_flights_to_instances(
            supabase,
            start_date=request.start_date,
            end_date=request.end_date,
            replace_existing=request.replace_existing,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to expand raw flights into flight_instances: {exc}") from exc

@app.post("expansion/upload")

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
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run turnaround scenarios from flight_instances: {exc}") from exc


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
        supabase.table("flights_assignment")
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


' ============================== '

@app.get("/hello")
def read_root():
    return {"message": "Hello from FastAPI"}
