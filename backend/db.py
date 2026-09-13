"""
Supabase persistence layer for AutoChain.
-----------------------------------------
Wraps the Supabase Postgres tables (vehicles, cases, tips) and Storage
buckets (vehicle-photos public, ownership-documents private) so main.py can
stay focused on the API/business logic instead of database plumbing.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from storage3.exceptions import StorageApiError
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

VEHICLE_PHOTOS_BUCKET = "vehicle-photos"
OWNERSHIP_DOCS_BUCKET = "ownership-documents"
OWNER_ID_PHOTOS_BUCKET = "owner-id-photos"

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY) if SUPABASE_URL and SUPABASE_SECRET_KEY else None


def _create_bucket_if_missing(name: str, public: bool) -> None:
    try:
        supabase.storage.create_bucket(name, options={"public": public})
    except StorageApiError as e:
        # Supabase's storage API can 409 here even when list_buckets() didn't
        # show the bucket yet (listing lags behind a just-created bucket) —
        # either way, the bucket existing is exactly what we want.
        if str(e.status) != "409":
            raise


def _ensure_buckets() -> None:
    existing = {b.name for b in supabase.storage.list_buckets()}
    if VEHICLE_PHOTOS_BUCKET not in existing:
        _create_bucket_if_missing(VEHICLE_PHOTOS_BUCKET, public=True)
    if OWNERSHIP_DOCS_BUCKET not in existing:
        _create_bucket_if_missing(OWNERSHIP_DOCS_BUCKET, public=False)
    if OWNER_ID_PHOTOS_BUCKET not in existing:
        _create_bucket_if_missing(OWNER_ID_PHOTOS_BUCKET, public=False)


if supabase:
    _ensure_buckets()


def is_configured() -> bool:
    return supabase is not None


# --- vehicles ---------------------------------------------------------------

def insert_vehicle(fields: dict) -> dict:
    res = supabase.table("vehicles").insert(fields).execute()
    return res.data[0]


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    res = supabase.table("vehicles").select("*").eq("id", vehicle_id).execute()
    return res.data[0] if res.data else None


def upload_vehicle_photo(vehicle_id: str, index: int, content: bytes, content_type: str) -> None:
    path = f"{vehicle_id}/{index}.jpg"
    supabase.storage.from_(VEHICLE_PHOTOS_BUCKET).upload(
        path, content, file_options={"content-type": content_type, "upsert": "true"}
    )


def vehicle_photo_public_url(vehicle_id: str, index: int) -> str:
    return supabase.storage.from_(VEHICLE_PHOTOS_BUCKET).get_public_url(f"{vehicle_id}/{index}.jpg")


def upload_ownership_document(vehicle_id: str, content: bytes, content_type: str, filename: str) -> None:
    ext = Path(filename or "document").suffix or ""
    path = f"{vehicle_id}/document{ext}"
    supabase.storage.from_(OWNERSHIP_DOCS_BUCKET).upload(
        path, content, file_options={"content-type": content_type, "upsert": "true"}
    )


def download_ownership_document(vehicle_id: str) -> Optional[tuple[bytes, str]]:
    """Returns (content, filename) or None if nothing was uploaded."""
    files = supabase.storage.from_(OWNERSHIP_DOCS_BUCKET).list(vehicle_id)
    if not files:
        return None
    filename = files[0]["name"]
    content = supabase.storage.from_(OWNERSHIP_DOCS_BUCKET).download(f"{vehicle_id}/{filename}")
    return content, filename


def upload_owner_id_photo(owner_wallet: str, content: bytes, content_type: str) -> None:
    # KYC selfie of the owner's ID card/credential — keyed by wallet (one per
    # person, done once), not by vehicle. Private bucket, same treatment as
    # the ownership document (never linked from the public board).
    path = f"{owner_wallet.lower()}/id_photo.jpg"
    supabase.storage.from_(OWNER_ID_PHOTOS_BUCKET).upload(
        path, content, file_options={"content-type": content_type, "upsert": "true"}
    )


def download_owner_id_photo(owner_wallet: str) -> Optional[bytes]:
    files = supabase.storage.from_(OWNER_ID_PHOTOS_BUCKET).list(owner_wallet.lower())
    if not files:
        return None
    filename = files[0]["name"]
    return supabase.storage.from_(OWNER_ID_PHOTOS_BUCKET).download(f"{owner_wallet.lower()}/{filename}")


# --- users (standalone KYC, independent from vehicles) ------------------------

def upsert_user(fields: dict) -> dict:
    fields = {**fields, "owner_wallet": fields["owner_wallet"].lower()}
    res = supabase.table("users").upsert(fields, on_conflict="owner_wallet").execute()
    return res.data[0]


def get_user(owner_wallet: str) -> Optional[dict]:
    res = supabase.table("users").select("*").eq("owner_wallet", owner_wallet.lower()).execute()
    return res.data[0] if res.data else None


# --- cases -------------------------------------------------------------------

def insert_case(fields: dict) -> dict:
    res = supabase.table("cases").insert(fields).execute()
    return res.data[0]


def get_case(case_id: str) -> Optional[dict]:
    res = supabase.table("cases").select("*").eq("id", case_id).execute()
    return res.data[0] if res.data else None


def update_case(case_id: str, fields: dict) -> None:
    supabase.table("cases").update(fields).eq("id", case_id).execute()


def list_cases_joined(owner_wallet: Optional[str] = None) -> list[dict]:
    query = supabase.table("cases").select("*, vehicles(*)").order("reported_at", desc=True)
    res = query.execute()
    rows = res.data
    if owner_wallet:
        rows = [r for r in rows if r["vehicles"]["owner_wallet"].lower() == owner_wallet.lower()]
    return rows


# --- tips ----------------------------------------------------------------------

def insert_tip(fields: dict) -> dict:
    res = supabase.table("tips").insert(fields).execute()
    return res.data[0]


def list_tips_for_case(case_id: str) -> list[dict]:
    res = supabase.table("tips").select("*").eq("case_id", case_id).order("created_at", desc=True).execute()
    return res.data


def update_tip(tip_id: str, fields: dict) -> None:
    supabase.table("tips").update(fields).eq("id", tip_id).execute()


def list_recent_tips_joined(limit: int = 10) -> list[dict]:
    res = (
        supabase.table("tips")
        .select("*, cases(*, vehicles(*))")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data
