from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
import ssl

from supabase import create_client, Client

'''
Sets up access point for Supabase 
'''

# load variables from .env
load_dotenv() 

# DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase():
    return supabase


# # create sll context variable
# ssl_context = ssl.create_default_context()
# # disable full certificate verification
# ssl_context.check_hostname = False
# ssl_context.verify_mode = ssl.CERT_NONE

# engine = create_async_engine(
#     DATABASE_URL,
#     connect_args={"ssl": ssl_context},
#     echo=True,
# )

# AsyncSessionLocal = sessionmaker(
#     engine, class_=AsyncSession, expire_on_commit=False
# )

# async def get_db():
#     async with AsyncSessionLocal() as session:
#         yield session
