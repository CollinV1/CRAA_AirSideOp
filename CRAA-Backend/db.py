'''
Sets up access point for Supabase 
'''
from dotenv import load_dotenv
import os

# load variables from .env
load_dotenv() 

DATABASE_URL = os.getenv("DATABASE_URL")
