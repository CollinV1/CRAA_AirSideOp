import os

import msal
import requests
from dotenv import load_dotenv

''' 
Set up access point for Power BI 
'''
load_dotenv()

TENANT_ID = os.getenv("POWERBI_TENANT_ID")
CLIENT_ID = os.getenv("POWERBI_CLIENT_ID")
CLIENT_SECRET = os.getenv("POWERBI_CLIENT_SECRET")
AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"

SCOPE = "https://analysis.windows.net/powerbi/api/.default" # fixed Microsoft scope so doesn't change
API_ROOT = "https://api.powerbi.com/v1.0/myorg"
POWERBI_WORKSPACE_ID = os.getenv("POWERBI_WORKSPACE_ID") or os.getenv("POWERBI_GROUP_ID")
POWERBI_REPORT_ID = os.getenv("POWERBI_REPORT_ID")

def get_access_token():
    missing = [
        name for name, value in (
            ("POWERBI_TENANT_ID", TENANT_ID),
            ("POWERBI_CLIENT_ID", CLIENT_ID),
            ("POWERBI_CLIENT_SECRET", CLIENT_SECRET),
            ("POWERBI_AUTHORITY", AUTHORITY),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"Missing Power BI environment variables: {', '.join(missing)}")

    confidential_client = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID,
        client_credential=CLIENT_SECRET,
        authority=AUTHORITY,
    )

    token_result = confidential_client.acquire_token_for_client(scopes=[SCOPE])

    if "access_token" not in token_result:
        raise RuntimeError(
            f"Failed to acquire Power BI access token: {token_result.get('error_description', token_result)}"
        )

    return token_result["access_token"]



def get_embed_config():
    if not POWERBI_WORKSPACE_ID or not POWERBI_REPORT_ID:
        raise ValueError("Missing POWERBI_WORKSPACE_ID/POWERBI_GROUP_ID or POWERBI_REPORT_ID in environment.")

    access_token = get_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    report_response = requests.get(
        f"{API_ROOT}/groups/{POWERBI_WORKSPACE_ID}/reports/{POWERBI_REPORT_ID}",
        headers=headers,
        timeout=30,
    )
    report_response.raise_for_status()
    report = report_response.json()

    token_response = requests.post(
        f"{API_ROOT}/groups/{POWERBI_WORKSPACE_ID}/reports/{POWERBI_REPORT_ID}/GenerateToken",
        headers=headers,
        json={"accessLevel": "View"},
        timeout=30,
    )
    token_response.raise_for_status()
    embed_token = token_response.json()

    return {
        "reportId": report["id"],
        "reportName": report.get("name"),
        "embedUrl": report["embedUrl"],
        "embedToken": embed_token["token"],
        "tokenId": embed_token.get("tokenId"),
        "expiration": embed_token.get("expiration"),
        "groupId": POWERBI_WORKSPACE_ID,
        "workspaceId": POWERBI_WORKSPACE_ID,
    }


