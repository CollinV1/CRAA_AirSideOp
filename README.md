# CRAA-Airside Operations AirSide

## installation
  1.**Clone Repo**:

```bash
git clone https://github.com/CollinV1/CRAA-Operations.git
cd CRAA-Backend
   ```
2. **Create and run Virtual environment** :

    `python -m venv venv`

   `.\venv\Scripts\Activate.ps1`
   
4. **Install dependencies**:

    `python -m pip install fastapi uvicorn`
   
6. **Run Server**:

   `python -m uvicorn main:app --reload`

## Change Log
**-Jan 28 2026** Sam uploads *Charleston Terminal Map*

**-Feb 22 2026** Collin uploads *CRAA-Backend* 

**-Mar 4 2026** Alma uploads *CRAA-Database* and *supabase*

**-Mar11 2026** Manny uploads 02_run_algorithm.py


Flight scheduler and scenario builder.

### Supabase CLI

Version control for Supabase db.

**Setup:**
```
npm install -g supabase
supabase login
supabase init
```

**Link to Supabase:**
  `PROJECT_ID` is found in the Projects dashboard on Supabase.
```
supabase link --project-ref PROJECT_ID
```

**Migrate Schema:**
```
supabase migration new schema_name
```

This creates `supabase/migrations/20260304132904_schema_name.sql`.
Paste schema or initial db construction.

```
supabase db push
```
**Problems Migrating to Remote:**
```
1. mkdir local-supabase
2. cd local-supabase
3. git init
4. supabase init
5. supabase link --project-ref <project-ref> 
6. supabase db remote set 'postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres'
7. supabase db remote commit
```
