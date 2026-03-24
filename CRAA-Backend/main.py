from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from supabase import Client
from db import get_supabase

import ssl 


app = FastAPI()

# Allow React dev server
origins = [
    "http://localhost:5173",
]

@app.get("/flights")
def get_flights(supabase: Client = Depends(get_supabase)):
    res = supabase.table("flight_instances").select("*").execute()
    return res.data


# @app.get("/flights")
# async def get_flights(db: AsyncSession = Depends(get_db)):
#     a = 10
#     testing = "SELECT flight_id FROM flight_instances LIMIT " + str(a)
#     result = await db.execute(text(testing))
#     flights = result.mappings().all()
    
#     return {"flights": flights}

app.add_middleware(

    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
def read_root():
    return {"message": "Hello from FastAPI"}
