from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from db import get_db
app = FastAPI()

# Allow React dev server
origins = [
    "http://localhost:5173",
]

@app.get("/flights")
async def get_flights(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT"))
    flights = result.mappings().all()
    
    return {"flights": flights}

app.add_middleware(

    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
def read_root():
    return {"message": "Hello from FastAPI 🚀"}
