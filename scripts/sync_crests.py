import os
import csv
import json
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

# Load service account credentials from secret
sa_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
scopes = ["https://www.googleapis.com/auth/drive.readonly"]
creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
authed_session = AuthorizedSession(creds)

# Ensure output directory exists
out_dir = "assets/crests"
os.makedirs(out_dir, exist_ok=True)

# Read CSV mapping
with open("crest_mapping.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        town = row.get("Town") or row.get("town") or row.get("TOWN")
        file_id = row.get("FileID") or row.get("file_id") or row.get("FILEID")

        if not town or not file_id:
            continue

        town_slug = town.strip().replace(" ", "_").upper()
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

        print(f"Downloading crest for {town} ({file_id})...")
        resp = authed_session.get(url)
        if resp.status_code == 200:
            out_path = os.path.join(out_dir, f"{town_slug}.png")
            with open(out_path, "wb") as img_f:
                img_f.write(resp.content)
        else:
            print(f"Failed to download {town}: {resp.status_code} {resp.text[:200]}")
