# CRAA-Operations

### Create Supabase User:
**Remember your password**, this is needed to connect to FastAPI using the `DATABASE_URL`.
```
CREATE ROLE your_user_name WITH LOGIN PASSWORD 'password';
GRANT CONNECT ON DATABASE postgres TO your_user_name;
GRANT USAGE ON SCHEMA public TO your_user_name;
GRANT CREATE ON SCHEMA public TO your_user_name;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO your_user_name;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO your_user_name;
```
Create a **.env** file in the root directory (include **.env** in **.gitignore**) containing...
```
DATABASE_URL=postgresql+asyncpg://postgres:[PASSWORD]@db.[PROJECT_ID].supabase.co:5432/postgres?sslmode=require
```
`PROJECT_ID` can be found in Supabase Connection String.

