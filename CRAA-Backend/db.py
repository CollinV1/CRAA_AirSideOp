from supabase import create_client, Client
from dotenv import load_dotenv
import os

'''
Set up access point for Supabase 
'''

# load variables from .env
load_dotenv() 

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase():
    return supabase

