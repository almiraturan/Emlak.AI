from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.location_text import to_canonical_location


RawPayload = dict[str, Any]


def _to_clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().replace(" ", "")
    # _to_float para alani degil; sadece saf sayisal deger kabul eder.
    if re.search(r"[A-Za-z₺$€]", text):
        return None

    if "," in text and "." in text:
        # Son gorulen ayirac ondalik kabul edilir.
        if text.rindex(",") > text.rindex("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") > 1:
            text = text.replace(",", "")
        else:
            comma_idx = text.rfind(",")
            digits_after = len(text) - comma_idx - 1
            if digits_after == 3:
                text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
    elif "." in text:
        if text.count(".") > 1:
            text = text.replace(".", "")
        else:
            dot_idx = text.rfind(".")
            digits_after = len(text) - dot_idx - 1
            if digits_after == 3:
                text = text.replace(".", "")

    try:
        return float(text)
    except ValueError:
        return None


def _to_decimal(value: Any) -> Decimal | None:
    # Para alanları için hassas dönüş (Float yerine Decimal).
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))  # Float'tan doğrudan Decimal yapma (hassasiyet riski)
        except (InvalidOperation, ValueError):
            return None

    text = str(value).strip().replace(" ", "")
    text = text.replace("TL", "").replace("TRY", "").replace("₺", "")
    text = text.replace("USD", "").replace("EUR", "").replace("GBP", "")
    text = text.replace("$", "").replace("€", "").replace("£", "")

    if "," in text and "." in text:
        # Son gorulen ayirac ondalik kabul edilir.
        if text.rindex(",") > text.rindex("."):
            # 2.500,50 -> 2500.50
            text = text.replace(".", "").replace(",", ".")
        else:
            # 2,500.50 -> 2500.50
            text = text.replace(",", "")
    elif "," in text:
        if text.count(",") > 1:
            # 2,500,000 -> 2500000
            text = text.replace(",", "")
        else:
            comma_idx = text.rfind(",")
            digits_after = len(text) - comma_idx - 1
            # Para alaninda 1-2 hane ondalik kabul edilir, 3+ hane binliktir.
            if digits_after <= 2:
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
    elif "." in text:
        if text.count(".") > 1:
            # 2.500.000 -> 2500000
            text = text.replace(".", "")
        else:
            dot_idx = text.rfind(".")
            digits_after = len(text) - dot_idx - 1
            if digits_after > 2:
                # 2.500 -> 2500 (para icin 3+ hane ondalik beklenmez)
                text = text.replace(".", "")

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    as_float = _to_float(value)
    if as_float is None:
        return None
    return int(as_float)


def _parse_room_layout(value: Any) -> tuple[str | None, int | None, int | None, int | None]:
    if value is None:
        return None, None, None, None

    if isinstance(value, int):
        return str(value), value, None, value

    text = str(value).strip().lower()
    if not text:
        return None, None, None, None

    match = re.match(r"^(\d+)\s*\+\s*(\d+)$", text)
    if match:
        main = int(match.group(1))
        living = int(match.group(2))
        return f"{main}+{living}", main, living, main + living

    numeric = _to_int(text)
    if numeric is None:
        return text, None, None, None
    return str(numeric), numeric, None, numeric


def _normalize_currency(value: Any) -> str | None:
    text = _to_clean_str(value)
    if text is None:
        return None

    code = text.upper()
    mapping = {
        "TRY": "TRY",
        "TL": "TRY",
        "₺": "TRY",
        "USD": "USD",
        "$": "USD",
        "EUR": "EUR",
        "€": "EUR",
        "GBP": "GBP",
        "£": "GBP",
    }
    return mapping.get(code, code)


def _normalize_listing_type(value: Any) -> str | None:
    text = _to_clean_str(value)
    if text is None:
        return None

    normalized = text.lower()
    mapping = {
        "satilik": "satilik",
        "satılık": "satilik",
        "for_sale": "satilik",
        "sale": "satilik",
        "kiralik": "kiralik",
        "kiralık": "kiralik",
        "rent": "kiralik",
        "for_rent": "kiralik",
    }
    return mapping.get(normalized, normalized)


def _normalize_property_type(value: Any) -> str | None:
    text = _to_clean_str(value)
    if text is None:
        return None

    normalized = text.lower()
    mapping = {
        "daire": "daire",
        "apartment": "daire",
        "villa": "villa",
        "arsa": "arsa",
        "land": "arsa",
        "isyeri": "isyeri",
        "işyeri": "isyeri",
        "office": "isyeri",
        "mustakil": "mustakil",
        "müstakil": "mustakil",
    }
    return mapping.get(normalized, normalized)


def _title_case(value: Any) -> str | None:
    text = _to_clean_str(value)
    if text is None:
        return None
    return text.title()


def _to_canonical_location(value: Any) -> str | None:
    text = _to_clean_str(value)
    return to_canonical_location(text)


def normalize_listing_payload(
    raw_payload: RawPayload,
    fallback_source: str,
    fallback_source_listing_id: str,
) -> tuple[RawPayload, dict[str, Any]]:
    warnings: list[str] = []
    normalized: RawPayload = dict(raw_payload)
    room_layout_source = raw_payload.get("room_layout_raw")

    parsed_layout_raw, parsed_main, parsed_living, parsed_total = _parse_room_layout(room_layout_source)

    explicit_main = _to_int(raw_payload.get("room_count_main"))
    explicit_living = _to_int(raw_payload.get("room_count_living"))
    explicit_total = _to_int(raw_payload.get("room_count_total"))

    room_count_main = explicit_main if explicit_main is not None else parsed_main
    room_count_living = explicit_living if explicit_living is not None else parsed_living

    if explicit_total is not None:
        room_count_total = explicit_total
    elif room_count_main is not None and room_count_living is not None:
        room_count_total = room_count_main + room_count_living
    elif parsed_total is not None:
        room_count_total = parsed_total
    else:
        room_count_total = room_count_main

    room_layout_raw = _to_clean_str(raw_payload.get("room_layout_raw")) or parsed_layout_raw
    if room_layout_raw is None and room_count_main is not None and room_count_living is not None:
        room_layout_raw = f"{room_count_main}+{room_count_living}"
    elif room_layout_raw is None and room_count_total is not None:
        room_layout_raw = str(room_count_total)

    source = _to_clean_str(raw_payload.get("source")) or fallback_source
    if _to_clean_str(raw_payload.get("source")) is None:
        warnings.append("source missing, fallback value used")

    source_listing_id = _to_clean_str(raw_payload.get("source_listing_id")) or fallback_source_listing_id
    if _to_clean_str(raw_payload.get("source_listing_id")) is None:
        warnings.append("source_listing_id missing, fallback value used")

    images = raw_payload.get("images")
    if images is None:
        normalized_images: list[str] = []
    elif isinstance(images, list):
        normalized_images = [str(item).strip() for item in images if str(item).strip()]
    else:
        normalized_images = [str(images).strip()] if str(images).strip() else []
        warnings.append("images was not a list, converted into a list")

    normalized.update(
        {
            "source": source,
            "source_listing_id": source_listing_id,
            "title": _to_clean_str(raw_payload.get("title")),
            "description": _to_clean_str(raw_payload.get("description")),
            "listing_type": _normalize_listing_type(raw_payload.get("listing_type")) or "satilik",
            "property_type": _normalize_property_type(raw_payload.get("property_type")) or "daire",
            "price": _to_decimal(raw_payload.get("price")),
            "currency": _normalize_currency(raw_payload.get("currency")) or "TRY",
            "area_m2": _to_float(raw_payload.get("area_m2")),
            "net_m2": _to_float(raw_payload.get("net_m2")),
            "gross_m2": _to_float(raw_payload.get("gross_m2")),
            "room_layout_raw": room_layout_raw,
            "room_count_main": room_count_main,
            "room_count_living": room_count_living,
            "room_count_total": room_count_total,
            "city": _title_case(raw_payload.get("city")),
            "district": _title_case(raw_payload.get("district")),
            "neighborhood": _title_case(raw_payload.get("neighborhood")),
            "city_canonical": _to_canonical_location(raw_payload.get("city")),
            "district_canonical": _to_canonical_location(raw_payload.get("district")),
            "neighborhood_canonical": _to_canonical_location(raw_payload.get("neighborhood")),
            "city_code": _to_clean_str(raw_payload.get("city_code")),
            "district_code": _to_clean_str(raw_payload.get("district_code")),
            "neighborhood_code": _to_clean_str(raw_payload.get("neighborhood_code")),
            "latitude": _to_float(raw_payload.get("latitude")),
            "longitude": _to_float(raw_payload.get("longitude")),
            "building_age": _to_int(raw_payload.get("building_age")),
            "floor": _to_int(raw_payload.get("floor")),
            "heating_type": _title_case(raw_payload.get("heating_type")),
            "image_count": _to_int(raw_payload.get("image_count")),
            "images": normalized_images,
            "source_url": _to_clean_str(raw_payload.get("source_url")),
            "published_at": raw_payload.get("published_at"),
            "source_updated_at": raw_payload.get("source_updated_at"),
            "is_active": bool(raw_payload.get("is_active", True)),
        }
    )

    if normalized["gross_m2"] is None and normalized["area_m2"] is not None:
        normalized["gross_m2"] = normalized["area_m2"]
        warnings.append("gross_m2 missing, area_m2 copied")

    if normalized["net_m2"] is None and normalized["gross_m2"] is not None:
        normalized["net_m2"] = round(float(normalized["gross_m2"]) * 0.88, 1)
        warnings.append("net_m2 missing, estimated from gross_m2")

    if normalized["image_count"] is None:
        normalized["image_count"] = len(normalized_images)
        warnings.append("image_count missing, derived from images")
    elif normalized["image_count"] != len(normalized_images):
        warnings.append("image_count does not match images length")

    critical_fields = [
        "title",
        "price",
        "currency",
        "area_m2",
        "room_count_total",
        "city",
        "district",
        "neighborhood",
        "listing_type",
        "property_type",
        "source",
        "source_listing_id",
    ]
    optional_fields = ["description", "latitude", "longitude", "source_url", "published_at", "source_updated_at"]

    missing_fields = [field for field in critical_fields + optional_fields if normalized.get(field) in (None, "")]
    missing_critical = [field for field in critical_fields if field in missing_fields]
    missing_optional = [field for field in optional_fields if field in missing_fields]

    quality_score = 100
    quality_score -= len(missing_critical) * 15
    quality_score -= len(missing_optional) * 3
    quality_score -= len(warnings) * 4
    quality_score = max(0, min(100, quality_score))

    report = {
        "source": source,
        "source_listing_id": source_listing_id,
        "quality_score": quality_score,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }

    return normalized, report