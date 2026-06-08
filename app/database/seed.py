import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.models.listing import Listing
from app.models.user import User
from app.models.user_behavior import UserBehavior


# (district, neighborhood, lat, lng) tuples for Istanbul districts.
_DISTRICTS = [
    ("Kadikoy", "Moda", 40.987, 29.028),
    ("Kadikoy", "Caddebostan", 40.965, 29.066),
    ("Kadikoy", "Fenerbahce", 40.969, 29.040),
    ("Besiktas", "Sinanpasa", 41.043, 29.003),
    ("Besiktas", "Levent", 41.082, 29.012),
    ("Besiktas", "Etiler", 41.082, 29.030),
    ("Uskudar", "Altunizade", 41.021, 29.041),
    ("Uskudar", "Cengelkoy", 41.052, 29.057),
    ("Uskudar", "Kuzguncuk", 41.034, 29.038),
    ("Atasehir", "Barbaros", 40.983, 29.124),
    ("Atasehir", "Atatürk", 40.988, 29.108),
    ("Beylikduzu", "Marmara", 41.000, 28.640),
    ("Beylikduzu", "Adnan Kahveci", 41.005, 28.645),
    ("Sisli", "Mecidiyekoy", 41.067, 28.997),
    ("Sisli", "Nisantasi", 41.050, 28.989),
    ("Sariyer", "Tarabya", 41.140, 29.063),
    ("Sariyer", "Maslak", 41.108, 29.018),
    ("Bakirkoy", "Atakoy", 40.985, 28.864),
    ("Bakirkoy", "Yesilkoy", 40.961, 28.823),
    ("Maltepe", "Bagdat", 40.935, 29.131),
    ("Pendik", "Kurtkoy", 40.905, 29.301),
    ("Kartal", "Yakacik", 40.910, 29.196),
    ("Beyoglu", "Cihangir", 41.030, 28.984),
    ("Fatih", "Sultanahmet", 41.005, 28.977),
    ("Bahcelievler", "Sirinevler", 41.000, 28.852),
]

_LAYOUTS = [
    ("1+0", 1, 0, 1, 45.0, 60.0),
    ("1+1", 1, 1, 2, 55.0, 75.0),
    ("2+1", 2, 1, 3, 85.0, 110.0),
    ("3+1", 3, 1, 4, 120.0, 150.0),
    ("4+1", 4, 1, 5, 160.0, 200.0),
    ("5+1", 5, 1, 6, 210.0, 260.0),
]

_HEATING = ["dogalgaz", "merkezi", "kombi", "klima"]
_VERDICTS = ["fair", "underpriced", "overpriced"]
_TRENDS = ["up", "down", "stable"]
_DESCRIPTIONS = [
    "Metroya yakin, yenilenmis, aileye uygun daire.",
    "Merkezde, sahile ve toplu tasimaya yakin.",
    "Sessiz sokakta, aileye uygun, ferah daire.",
    "Yeni binada, yatirimlik, site ici daire.",
    "Genis aileler icin, manzarali ve sosyal alanli.",
    "Okula ve markete yuruyus mesafesinde, modern bina.",
    "Esyali, bakimli ve hemen tasinabilir konumda.",
    "Acik mutfak, geniş balkon ve depolu daire.",
]


def _generate_listing_payload(index: int) -> dict:
    rng = random.Random(1000 + index)
    district, neighborhood, lat_base, lng_base = rng.choice(_DISTRICTS)
    layout_raw, main, living, total, area_min, area_max = rng.choice(_LAYOUTS)
    area = round(rng.uniform(area_min, area_max), 1)
    net = round(area * rng.uniform(0.82, 0.92), 1)
    price_per_m2 = rng.randint(35000, 95000)
    price = Decimal(str(int(area * price_per_m2 / 1000) * 1000))
    market_avg = float(price) * rng.uniform(0.92, 1.08)
    now = datetime.now(timezone.utc)

    return {
        "title": f"{district} {neighborhood} {layout_raw} Daire",
        "description": rng.choice(_DESCRIPTIONS),
        "listing_type": "satilik",
        "property_type": "daire",
        "price": price,
        "currency": "TRY",
        "area_m2": area,
        "net_m2": net,
        "gross_m2": area,
        "room_layout_raw": layout_raw,
        "room_count_main": main,
        "room_count_living": living,
        "room_count_total": total,
        "city": "Istanbul",
        "district": district,
        "neighborhood": neighborhood,
        "city_canonical": "istanbul",
        "district_canonical": district.lower(),
        "neighborhood_canonical": neighborhood.lower(),
        "location_id": None,
        "city_code": None,
        "district_code": None,
        "neighborhood_code": None,
        "location_match_confidence": round(rng.uniform(0.85, 0.99), 2),
        "latitude": round(lat_base + rng.uniform(-0.01, 0.01), 5),
        "longitude": round(lng_base + rng.uniform(-0.01, 0.01), 5),
        "building_age": rng.randint(0, 35),
        "floor": rng.randint(0, 18),
        "heating_type": rng.choice(_HEATING),
        "image_count": rng.randint(2, 12),
        "images": [],
        "published_at": now,
        "source_updated_at": now,
        "first_seen_at": now,
        "last_seen_at": now,
        "deactivated_at": None,
        "last_ingested_run_id": None,
        "is_active": True,
        "lifestyle_score": round(rng.uniform(5.5, 9.5), 1),
        "price_market_avg": round(market_avg, 2),
        "price_verdict": rng.choice(_VERDICTS),
        "price_trend_direction": rng.choice(_TRENDS),
        "price_comparables_count": rng.randint(3, 18),
        "source": "seed",
        "source_listing_id": f"sample-{district.lower()}-{index:03d}",
        "source_url": None,
    }


def get_seed_sample_payloads(limit: int | None = None) -> list[dict]:
    payloads = [_generate_listing_payload(i) for i in range(100)]
    if limit is None:
        return payloads
    return payloads[:limit]


def seed_listings_if_empty(db: Session) -> None:
    existing_count = db.query(func.count(Listing.id)).scalar() or 0
    if existing_count == 0:
        seed_listings(db)
    seed_demo_user_and_behavior(db)


def seed_demo_user_and_behavior(db: Session) -> None:
    """Ensure the default user Almira (id=1) exists and has some example behavior records."""
    demo = db.query(User).filter(User.id == 1).first()
    if demo is None:
        demo = User(
            id=1,
            name="Almira",
            budget_min=2_000_000.0,
            budget_max=6_000_000.0,
            preferred_rooms=3,
            prefers_quiet=False,
            prefers_central=True,
            purpose="ikamet",
            password="12345"
        )
        db.add(demo)
        db.commit()
    else:
        if demo.name != "Almira":
            demo.name = "Almira"
            demo.password = "12345"
            db.commit()

    if db.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1))"))
        db.commit()

    existing_behaviors = (
        db.query(func.count(UserBehavior.id))
        .filter(UserBehavior.user_id == 1)
        .scalar()
        or 0
    )
    if existing_behaviors > 0:
        return

    listings = db.query(Listing.id).limit(40).all()
    if not listings:
        return

    rng = random.Random(42)
    listing_ids = [lid for (lid,) in listings]
    now = datetime.now(timezone.utc)
    weighted_types = (
        ["click"] * 6
        + ["save"] * 3
        + ["skip"] * 2
        + ["search"] * 1
    )

    records = []
    for i in range(30):
        b_type = rng.choice(weighted_types)
        listing_id = rng.choice(listing_ids) if b_type != "search" else None
        meta = None
        if b_type == "search":
            meta = {
                "budget_max": rng.choice([3_500_000, 5_000_000, 7_000_000]),
                "rooms": rng.choice([2, 3, 4]),
            }
        records.append(
            UserBehavior(
                user_id=1,
                behavior_type=b_type,
                listing_id=listing_id,
                search_metadata=meta,
                timestamp=now - timedelta(days=rng.randint(0, 25), hours=rng.randint(0, 23)),
            )
        )

    db.add_all(records)
    db.commit()


def seed_listings(db: Session) -> int:
    existing_source_ids = {
        source_id
        for (source_id,) in db.query(Listing.source_listing_id).all()
        if source_id
    }

    inserted = 0
    for payload in get_seed_sample_payloads():
        if payload["source_listing_id"] in existing_source_ids:
            continue
        db.add(Listing(**payload))
        inserted += 1

    if inserted > 0:
        db.commit()

    return inserted


def run_seed_command() -> None:
    db = SessionLocal()
    try:
        seed_listings(db)
        seed_demo_user_and_behavior(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seed_command()
