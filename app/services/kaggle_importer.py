from __future__ import annotations

import io
import zipfile
from typing import Any

import requests

from app.core.config import settings


KAGGLE_DATASET_OWNER = "brahimenesulusoy"
KAGGLE_DATASET_SLUG = "istanbul-apartment-prices-2026"

# Minimum number of listings per district to ensure spread
TARGET_TOTAL = 50
# Columns that we expect; used for normalization
_ROOM_MAP = {
    "1+0": "1+0", "1+1": "1+1", "2+1": "2+1", "3+1": "3+1",
    "4+1": "4+1", "4+2": "4+2", "5+1": "5+1",
}


def _kaggle_auth() -> tuple[str, str]:
    username = settings.kaggle_username
    key = settings.kaggle_key
    if not username or not key:
        raise RuntimeError(
            "Kaggle credentials not configured. Set KAGGLE_USERNAME and KAGGLE_KEY "
            "environment variables."
        )
    return username, key


def _download_dataset_zip() -> bytes:
    """Downloads the full dataset zip from the Kaggle API."""
    auth = _kaggle_auth()
    url = (
        f"https://www.kaggle.com/api/v1/datasets/download/"
        f"{KAGGLE_DATASET_OWNER}/{KAGGLE_DATASET_SLUG}"
    )
    resp = requests.get(url, auth=auth, timeout=120, stream=True)
    if resp.status_code == 401:
        raise RuntimeError("Kaggle authentication failed — check KAGGLE_USERNAME / KAGGLE_KEY.")
    if resp.status_code == 404:
        raise RuntimeError(f"Kaggle dataset not found: {KAGGLE_DATASET_OWNER}/{KAGGLE_DATASET_SLUG}")
    resp.raise_for_status()
    return resp.content


def _read_csv_from_zip(zip_bytes: bytes) -> "Any":  # returns pd.DataFrame
    import pandas as pd

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise RuntimeError("No CSV file found in Kaggle dataset zip.")
        # Prefer the largest CSV (the main dataset file)
        main_csv = sorted(csv_names, key=lambda n: zf.getinfo(n).file_size, reverse=True)[0]
        with zf.open(main_csv) as f:
            df = pd.read_csv(f, low_memory=False)

    return df


def _normalize_room(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if s in _ROOM_MAP:
        return s
    # Handles numeric-only room count like "3"
    if s.isdigit():
        return f"{s}+1"
    return s or None


def _safe_float(val: Any) -> float | None:
    try:
        f = float(str(val).replace(",", ".").strip())
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _safe_int(val: Any) -> int | None:
    try:
        f = float(str(val).strip())
        return int(f) if f >= 0 else None
    except (TypeError, ValueError):
        return None


def _map_row_to_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    """Maps a Kaggle dataset row to IncomingListingPayload-compatible dict."""
    # Try multiple column name variants since dataset schema can vary
    price = _safe_float(
        row.get("price") or row.get("Price") or row.get("fiyat") or row.get("Fiyat")
    )
    if price is None or price <= 0:
        return None

    area = _safe_float(
        row.get("net_m2") or row.get("Net M2") or row.get("m2") or
        row.get("netSquareMeter") or row.get("net_sqm") or row.get("area")
    )
    if area is None or area <= 0:
        return None

    district = str(
        row.get("district") or row.get("District") or row.get("ilce") or
        row.get("İlçe") or row.get("ilçe") or ""
    ).strip()
    if not district:
        return None

    neighborhood = str(
        row.get("neighborhood") or row.get("Neighborhood") or row.get("mahalle") or
        row.get("Mahalle") or district
    ).strip()

    rooms_raw = (
        row.get("rooms") or row.get("Rooms") or row.get("oda_sayisi") or
        row.get("room") or row.get("Oda Sayısı")
    )
    room_layout = _normalize_room(rooms_raw)

    room_count = _safe_int(
        row.get("room_count") or row.get("roomCount")
    ) or (int(room_layout.split("+")[0]) if room_layout and "+" in room_layout else None)

    building_age = _safe_int(
        row.get("building_age") or row.get("Building Age") or row.get("bina_yasi")
    )
    floor_number = _safe_int(
        row.get("floor") or row.get("Floor") or row.get("kat")
    )
    total_floors = _safe_int(
        row.get("total_floors") or row.get("Total Floors") or row.get("kat_sayisi")
    )
    lat = _safe_float(row.get("latitude") or row.get("lat"))
    lon = _safe_float(row.get("longitude") or row.get("lon") or row.get("lng"))

    # Build a synthetic title
    title_parts = []
    if room_layout:
        title_parts.append(room_layout)
    if area:
        title_parts.append(f"{int(area)}m²")
    title_parts.append(f"{district} Daire")
    title = " ".join(title_parts)

    source_id = str(
        row.get("id") or row.get("ID") or row.get("listing_id") or ""
    ).strip()
    if not source_id:
        import hashlib
        source_id = hashlib.sha1(
            f"{district}_{neighborhood}_{price}_{area}_{room_layout}".encode()
        ).hexdigest()[:16]

    source_url = str(row.get("url") or row.get("link") or "").strip() or None

    return {
        "source": "kaggle_istanbul_2026",
        "source_listing_id": source_id,
        "title": title,
        "description": None,
        "price": price,
        "currency": "TRY",
        "listing_type": "satilik",
        "property_type": "daire",
        "city": "İstanbul",
        "city_canonical": "istanbul",
        "district": district,
        "neighborhood": neighborhood,
        "area_m2": area,
        "room_layout_raw": room_layout,
        "room_count_total": room_count if room_count is not None else 0,
        "floor": floor_number,
        "building_age": building_age,
        "source_url": source_url,
        "latitude": lat,
        "longitude": lon,
        "images": [],
        "image_count": 0,
    }


def fetch_istanbul_listings(target_count: int = TARGET_TOTAL) -> list[dict[str, Any]]:
    """Downloads Kaggle dataset and returns ~target_count listings from diverse districts."""
    import pandas as pd

    zip_bytes = _download_dataset_zip()
    df = _read_csv_from_zip(zip_bytes)

    # Ensure district column exists
    district_col = next(
        (c for c in df.columns if c.lower() in {"district", "ilce", "i̇lçe", "ilçe", "borough"}),
        None
    )
    if district_col is None:
        raise RuntimeError(f"Could not find district column. Columns: {list(df.columns)}")

    # Drop rows with null price or area
    price_col = next((c for c in df.columns if c.lower() in {"price", "fiyat"}), None)
    area_col = next(
        (c for c in df.columns if c.lower() in {"net_m2", "m2", "netsquaremeter", "net sqm", "area", "net m2"}),
        None
    )

    df = df.dropna(subset=[c for c in [price_col, area_col, district_col] if c])

    # Select evenly from each district
    districts = df[district_col].dropna().unique()
    per_district = max(1, target_count // max(len(districts), 1))

    sampled_rows: list[dict] = []
    for dist in districts:
        district_df = df[df[district_col] == dist]
        n = min(per_district, len(district_df))
        sample = district_df.sample(n=n, random_state=42) if len(district_df) >= n else district_df
        sampled_rows.extend(sample.to_dict(orient="records"))
        if len(sampled_rows) >= target_count:
            break

    # If still short, top-up from any remaining rows
    if len(sampled_rows) < target_count:
        remaining = df[~df.index.isin([r.get("index") for r in sampled_rows])]
        shortfall = target_count - len(sampled_rows)
        extra = remaining.sample(n=min(shortfall, len(remaining)), random_state=99)
        sampled_rows.extend(extra.to_dict(orient="records"))

    results: list[dict] = []
    for row in sampled_rows[:target_count]:
        payload = _map_row_to_payload(row)
        if payload is not None:
            results.append(payload)

    return results
