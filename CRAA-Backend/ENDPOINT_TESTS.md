# CRAA Backend Endpoint Tests

This document provides quick manual tests for the current FastAPI endpoints in [`main.py`](/Users/almalutas/Documents/website/CRAA-Operations/CRAA-Backend/main.py).

## Start The API

From the repo root:

```bash
cd CRAA-Backend
uvicorn main:app --reload
```

Default local base URL:

```text
http://127.0.0.1:8000
```

## Required Environment Variables

For Supabase-backed endpoints:

```env
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
```

For Power BI embed endpoint:

```env
POWERBI_TENANT_ID=...
POWERBI_CLIENT_ID=...
POWERBI_CLIENT_SECRET=...
POWERBI_WORKSPACE_ID=...
POWERBI_REPORT_ID=...
POWERBI_AUTHORITY=https://login.microsoftonline.com/<tenant_id>
POWERBI_SCOPE=https://analysis.windows.net/powerbi/api/.default
```

## 1. Health Check

Endpoint:

```http
GET /hello
```

Test with `curl`:

```bash
curl http://127.0.0.1:8000/hello
```

Expected response:

```json
{"message":"Hello from FastAPI"}
```

## 2. Raw Flights Endpoint

Endpoint:

```http
GET /flights
```

Test with `curl`:

```bash
curl http://127.0.0.1:8000/flights
```

Expected behavior:

- Returns a JSON array from the `flight_instances` table in Supabase.
- If Supabase credentials are missing or invalid, the request should fail.

Example response shape:

```json
[
  {
    "id": 1,
    "flight_id": 15018,
    "flight_number": 1869,
    "airline_id": "WN",
    "departure_airport": "CHS",
    "arrival_airport": "DEN",
    "departure_datetime": "2025-01-04T06:40:00",
    "arrival_datetime": "2025-01-04T08:35:00",
    "subaircrafttypecode": "73H"
  }
]
```

## 3. Power BI Embed Token Endpoint

Endpoint:

```http
GET /get-embed-token
```

Test with `curl`:

```bash
curl http://127.0.0.1:8000/get-embed-token
```

Expected behavior:

- Returns Power BI embed metadata if all Power BI credentials are valid.
- Returns `500` if required environment variables are missing.
- Returns `502` if the Power BI API call fails.

Example response shape:

```json
{
  "reportId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "reportName": "CRAA Operations Dashboard",
  "embedUrl": "https://app.powerbi.com/reportEmbed?reportId=...",
  "embedToken": "<token>",
  "tokenId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "expiration": "2026-03-30T15:00:00Z",
  "groupId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "workspaceId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

## 4. Canonical Optimized Schedule Endpoint

Before this endpoint returns useful data, run the two backend stages below:

1. `POST /expansion/run`
2. `POST /scenarios/run`

## 4. Expansion Stage

Endpoint:

```http
POST /expansion/run
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/expansion/run \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-02-01",
    "end_date": "2025-01-31",
    "replace_existing": true
  }'
```

Expected behavior:

- Reads recurring raw rows from `raw_flights`
- Expands them into concrete rows in `flight_instances`
- Stores those instances in Supabase

Example response shape:

```json
{
  "raw_rows": 1200,
  "flight_instances_created": 56000,
  "start_date": "2024-02-01",
  "end_date": "2025-01-31",
  "replace_existing": true
}
```

## 5. Turnaround Scheduling Stage

Endpoint:

```http
POST /scenarios/run
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/scenarios/run \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2024-02-01",
    "end_date": "2025-01-31",
    "turnaround_min": 45
  }'
```

Expected behavior:

- Reads concrete flights from `flight_instances`
- Builds turnaround pairings and gate assignments
- Stores canonical results in `scenario_runs`, `flights`, and `flights_assignment`

Example response shape:

```json
{
  "flight_instances_used": 56000,
  "scenarios": [
    {
      "scenario_id": 11,
      "name": "Scenario 1 — Same-Carrier Gate Assignment",
      "metrics": {
        "total_turns": 12000,
        "scheduled_turns": 11850,
        "conflicts": 150,
        "avg_turnaround": 62.4
      },
      "flights_inserted": 12000,
      "assignments_inserted": 12000
    }
  ],
  "optimal_scenario": {
    "name": "Scenario 2 — Shared Gates (Cross-Carrier, Size-Compatible)",
    "metrics": {
      "total_turns": 12100,
      "scheduled_turns": 12020,
      "conflicts": 80,
      "avg_turnaround": 58.1
    }
  }
}
```

## 6. Canonical Optimized Schedule Endpoint

Endpoint:

```http
GET /powerbi/optimized-schedule
```

Optional query parameter:

```http
GET /powerbi/optimized-schedule?scenario_id=2
```

Test with `curl`:

```bash
curl http://127.0.0.1:8000/powerbi/optimized-schedule
```

Specific scenario:

```bash
curl "http://127.0.0.1:8000/powerbi/optimized-schedule?scenario_id=2"
```

Expected behavior:

- If `scenario_id` is omitted, the endpoint returns the most recently created scenario from `scenario_runs`.
- If `scenario_id` is provided, it returns that specific scenario.
- If no scenarios exist, it returns `404`.
- If the scenario exists but has no assignments, it returns a valid response with `count: 0`.

Example response shape:

```json
{
  "scenario": {
    "id": 2,
    "name": "Scenario 2 - Shared Gates",
    "created_at": "2026-03-30T12:00:00",
    "parameters": {
      "turnaround_min": 45,
      "shared_gates": true
    }
  },
  "count": 2,
  "data": [
    {
      "scenario_id": 2,
      "scenario_name": "Scenario 2 - Shared Gates",
      "scenario_created_at": "2026-03-30T12:00:00",
      "assignment_id": 10,
      "flight_id": 101,
      "flight_number": 217,
      "airline_id": "AA",
      "arrival_time": "2024-03-05T10:34:00",
      "departure_time": "2024-03-05T11:27:00",
      "turnaround_minutes": 53,
      "raw_schedule_id": 1,
      "gate_id": "5",
      "concourse": "A",
      "gate_is_active": true,
      "is_conflict": 0,
      "assigned_at": 1709634840
    }
  ]
}
```

## Suggested Test Order

1. Test `/hello` to confirm the API is running.
2. Test `/flights` to confirm Supabase access works.
3. Run `/expansion/run` to populate `flight_instances`.
4. Run `/scenarios/run` to create optimized schedule results.
5. Test `/powerbi/optimized-schedule` to confirm canonical schedule data is available.
6. Test `/get-embed-token` to confirm Power BI authentication and embed config work.

## Common Failure Cases

- `500` on `/get-embed-token`:
  Missing one or more `POWERBI_*` environment variables.

- `502` on `/get-embed-token`:
  Power BI rejected the credentials, tenant, workspace, or report access.

- `404` on `/powerbi/optimized-schedule`:
  No rows exist yet in `scenario_runs`, or the requested `scenario_id` does not exist.

- Empty array or empty `data`:
  The schedule has not been written into Supabase/Postgres yet.

## Notes

- The backend pipeline is now split into two stages:
  `raw_flights` -> `/expansion/run` -> `flight_instances` -> `/scenarios/run` -> canonical schedule tables -> `/powerbi/optimized-schedule`
- The frontend CSV upload step can now focus on writing raw schedule data into Supabase before the two backend stages run.
