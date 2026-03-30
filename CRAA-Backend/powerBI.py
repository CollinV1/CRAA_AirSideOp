from dotenv import load_dotenv
import msal, requests, os

''' 
Set up access point for Power BI 
'''
# Microsoft's multi-tenant public client ID for Power BI
# This is a well-known public client ID — safe to use as-is
CLIENT_ID = "ea0616ba-638b-4df5-95b9-636659ae5121"
AUTHORITY  = "https://login.microsoftonline.com/common"
SCOPES     = ["https://analysis.windows.net/powerbi/api/.default"]

def get_access_token():
