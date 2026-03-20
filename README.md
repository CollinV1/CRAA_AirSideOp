# CRAA-Airside Operations

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
