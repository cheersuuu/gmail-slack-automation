"""
Gmail refresh token 발급 스크립트 (최초 1회 실행)
실행: python get_refresh_token.py
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\n=== GitHub Secrets에 추가할 값 ===")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")

info = json.loads(open("credentials.json").read())
installed = info.get("installed") or info.get("web")
print(f"GMAIL_CLIENT_ID={installed['client_id']}")
print(f"GMAIL_CLIENT_SECRET={installed['client_secret']}")
