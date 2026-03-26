from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import text
from supabase import Client
from db import get_supabase
import ssl 
import msal 

app = FastAPI()

# Allow React dev server
origins = [
    "http://localhost:5173",
]
''' 
TODO: PowerBI Embedded link

Dependencies: MSAL, requests
Purpose: Create PowerBI endpoint callable by frontend
Output: json embedToken + embedURL 

'''
@app.get("/get-embed-token")
def get_embed_token():
    # initialize MSAL client
    app_id = msal.ConfidentialClientApplication(CLIENT_ID, client_credential=None, authority=None, validate_authority=True, token_cache=None, http_client=None, verify=True, proxies=None, timeout=None, client_claims=None, app_name=None, app_version=None, client_capabilities=None, azure_region=None, exclude_scopes=None, http_cache=None, instance_discovery=None, allow_broker=None, enable_pii_log=None, oidc_authority=None)
    # retrieve token as application using username and password [acquire_token_by_username_password()]
    # not as secure as client credentials [acquire_token_for_client()] since the school does not grant access to Entra ID
    token = app.acquire_token_for_client(scopes="")
    # call PowerBI REST API using access token


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
