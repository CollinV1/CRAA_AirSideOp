# CRAA-Airside Operations

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

**Load Data Into Tables:**
