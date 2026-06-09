import sys
import os
import random
from datetime import datetime, timezone
from decimal import Decimal

# Add the project root directory to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database.session import SessionLocal
from app.models.listing import Listing
from app.models.listing_image import ListingImage
from app.models.user_interaction import UserInteraction
from app.models.user_recommendation_feedback import UserRecommendationFeedback
from app.models.user_behavior import UserBehavior
from app.models.ingestion_record import IngestionRecord

def main():
    print("Database connection opening...")
    db = SessionLocal()
    try:
        print("1) Cleaning up existing listings and related tables...")
        # Delete dependent rows
        deleted_feedback = db.query(UserRecommendationFeedback).delete()
        deleted_interactions = db.query(UserInteraction).delete()
        deleted_images = db.query(ListingImage).delete()
        print(f"Deleted related records: {deleted_feedback} feedbacks, {deleted_interactions} interactions, {deleted_images} images.")
        
        # Set nullable foreign keys to None
        updated_behaviors = db.query(UserBehavior).update({UserBehavior.listing_id: None})
        updated_records = db.query(IngestionRecord).update({IngestionRecord.listing_id: None})
        print(f"Set foreign keys to NULL: {updated_behaviors} user behaviors, {updated_records} ingestion records.")

        # Delete all listings
        deleted_listings = db.query(Listing).delete()
        print(f"Deleted listings: {deleted_listings} rows.")
        db.commit()

        print("2) Generating 100 TOKİ-style listings...")
        
        ankara_locations = [
            {"district": "Mamak", "neighborhood": "Şahintepe", "lat": 39.915, "lon": 32.910},
            {"district": "Sincan", "neighborhood": "Yenikent", "lat": 39.960, "lon": 32.505},
            {"district": "Altındağ", "neighborhood": "Karapürçek", "lat": 39.957, "lon": 32.960},
            {"district": "Etimesgut", "neighborhood": "Yapracık", "lat": 39.870, "lon": 32.540},
            {"district": "Etimesgut", "neighborhood": "Eryaman", "lat": 39.980, "lon": 32.650},
        ]
        
        izmir_locations = [
            {"district": "Çiğli", "neighborhood": "Evka-5", "lat": 38.520, "lon": 27.045},
            {"district": "Bornova", "neighborhood": "Doğanlar", "lat": 38.468, "lon": 27.240},
            {"district": "Karabağlar", "neighborhood": "Limontepe", "lat": 38.380, "lon": 27.100},
            {"district": "Torbalı", "neighborhood": "Ayrancılar", "lat": 38.250, "lon": 27.280},
        ]
        
        istanbul_locations = [
            {"district": "Başakşehir", "neighborhood": "Kayaşehir TOKİ", "lat": 41.125, "lon": 28.740},
            {"district": "Tuzla", "neighborhood": "Aydınlı TOKİ", "lat": 40.875, "lon": 29.310},
        ]
        
        other_cities = [
            {"city": "Bursa", "district": "Nilüfer", "neighborhood": "Görükle TOKİ", "lat": 40.220, "lon": 28.850},
            {"city": "Bursa", "district": "Osmangazi", "neighborhood": "Yunuseli TOKİ", "lat": 40.235, "lon": 29.020},
            {"city": "Antalya", "district": "Kepez", "neighborhood": "Göksu TOKİ", "lat": 36.930, "lon": 30.730},
            {"city": "Adana", "district": "Sarıçam", "neighborhood": "Çarkıpare TOKİ", "lat": 37.030, "lon": 35.430},
            {"city": "Trabzon", "district": "Yomra", "neighborhood": "Sancak TOKİ", "lat": 40.960, "lon": 39.850},
            {"city": "Gaziantep", "district": "Şahinbey", "neighborhood": "Güneykent TOKİ", "lat": 37.015, "lon": 37.330},
            {"city": "Konya", "district": "Selçuklu", "neighborhood": "Yazır TOKİ", "lat": 37.950, "lon": 32.500},
            {"city": "Diyarbakır", "district": "Kayapınar", "neighborhood": "Talaytepe TOKİ", "lat": 37.930, "lon": 40.150},
            {"city": "Eskişehir", "district": "Odunpazarı", "neighborhood": "Ihlamurkent TOKİ", "lat": 39.730, "lon": 30.540},
            {"city": "Samsun", "district": "Atakum", "neighborhood": "Mimar Sinan TOKİ", "lat": 41.330, "lon": 36.260},
            {"city": "Mersin", "district": "Mezitli", "neighborhood": "Akdeniz TOKİ", "lat": 36.780, "lon": 34.530},
            {"city": "Kayseri", "district": "Melikgazi", "neighborhood": "Mimarsinan TOKİ", "lat": 38.710, "lon": 35.580},
            {"city": "Kocaeli", "district": "İzmit", "neighborhood": "Kuruçeşme TOKİ", "lat": 40.780, "lon": 29.890},
            {"city": "Sakarya", "district": "Adapazarı", "neighborhood": "Karaman TOKİ", "lat": 40.820, "lon": 30.370},
            {"city": "Erzurum", "district": "Palandöken", "neighborhood": "Yenişehir TOKİ", "lat": 39.880, "lon": 41.260},
            {"city": "Denizli", "district": "Pamukkale", "neighborhood": "Karşıyaka TOKİ", "lat": 37.800, "lon": 29.110},
            {"city": "Muğla", "district": "Menteşe", "neighborhood": "Kötekli TOKİ", "lat": 37.210, "lon": 28.370},
            {"city": "Ordu", "district": "Altınordu", "neighborhood": "Şirinevler TOKİ", "lat": 40.980, "lon": 37.880},
            {"city": "Şanlıurfa", "district": "Karaköprü", "neighborhood": "Maşuk TOKİ", "lat": 37.230, "lon": 38.800},
            {"city": "Sivas", "district": "Merkez", "neighborhood": "Kılavuz TOKİ", "lat": 39.730, "lon": 37.030},
            {"city": "Çanakkale", "district": "Merkez", "neighborhood": "Kepez TOKİ", "lat": 40.100, "lon": 26.400},
            {"city": "Yalova", "district": "Merkez", "neighborhood": "Kadıköy TOKİ", "lat": 40.630, "lon": 29.250},
            {"city": "Tekirdağ", "district": "Süleymanpaşa", "neighborhood": "Hürriyet TOKİ", "lat": 40.970, "lon": 27.540},
            {"city": "Edirne", "district": "Merkez", "neighborhood": "Fatih TOKİ", "lat": 41.660, "lon": 26.580},
        ]
        
        layouts = [
            {"layout": "1+1", "main": 1, "living": 1, "total": 2, "area": 60, "base_price": 1800000},
            {"layout": "2+1", "main": 2, "living": 1, "total": 3, "area": 85, "base_price": 2400000},
            {"layout": "3+1", "main": 3, "living": 1, "total": 4, "area": 115, "base_price": 3200000},
        ]

        listings_to_add = []
        random.seed(42)
        now = datetime.now(timezone.utc)

        for i in range(100):
            # 1. Determine City and Location
            if i < 20:
                city = "Ankara"
                loc = random.choice(ankara_locations)
            elif i < 30:
                city = "İzmir"
                loc = random.choice(izmir_locations)
            elif i < 32:
                city = "İstanbul"
                loc = istanbul_locations[i - 30] # Exactly 2 items
            else:
                other_loc = other_cities[(i - 32) % len(other_cities)]
                city = other_loc["city"]
                loc = other_loc
            
            # 2. Layout, size, price details
            ly = random.choices(layouts, weights=[25, 45, 30], k=1)[0]
            
            area = round(ly["area"] * random.uniform(0.9, 1.1), 1)
            net = round(area * 0.85, 1)
            
            # Price noise based on city (Istanbul/Izmir are more premium)
            city_multiplier = 1.0
            if city == "İstanbul":
                city_multiplier = 1.35
            elif city == "İzmir":
                city_multiplier = 1.15
            elif city == "Ankara":
                city_multiplier = 1.05
            
            price_val = int(ly["base_price"] * city_multiplier * random.uniform(0.9, 1.15))
            price_val = (price_val // 10000) * 10000 # Round
            
            age = random.choice([0, 1, 2, 3, 5, 7, 10, 12])
            floor = random.randint(0, 10)
            
            # Build title and desc
            title = f"{city} {loc['district']} TOKİ Konutlarında Satılık {ly['layout']} Daire"
            description = (
                f"{city} ili, {loc['district']} ilçesi, {loc['neighborhood']} mevkisinde bulunan "
                f"bu {ly['layout']} TOKİ konutudur. Net {int(net)} m² (Brüt {int(area)} m²) kullanım alanına sahip, "
                f"{age} yıllık binada {floor}. katta yer alan dairemiz toplu ulaşıma ve sosyal olanaklara yakındır. "
                f"TOKİ standartlarına uygun, ısı yalıtımlı ve güvenli bir sitedir. Borcu yoktur, satışı hazırdır."
            )
            
            source_id = f"toki-{city.lower()}-{i+1:03d}"
            
            # Add listing model
            new_listing = Listing(
                title=title,
                description=description,
                listing_type="satilik",
                property_type="daire",
                price=Decimal(price_val),
                currency="TRY",
                area_m2=area,
                net_m2=net,
                gross_m2=area,
                room_layout_raw=ly["layout"],
                room_count_main=ly["main"],
                room_count_living=ly["living"],
                room_count_total=ly["total"],
                city=city,
                district=loc["district"],
                neighborhood=loc["neighborhood"],
                city_canonical=city.lower().replace("ı", "i").replace("ü", "u").replace("ö", "o").replace("ş", "s").replace("ç", "c").replace("ğ", "g"),
                district_canonical=loc["district"].lower().replace("ı", "i").replace("ü", "u").replace("ö", "o").replace("ş", "s").replace("ç", "c").replace("ğ", "g"),
                neighborhood_canonical=loc["neighborhood"].lower().replace("ı", "i").replace("ü", "u").replace("ö", "o").replace("ş", "s").replace("ç", "c").replace("ğ", "g"),
                location_id=None,
                city_code=None,
                district_code=None,
                neighborhood_code=None,
                location_match_confidence=1.0,
                latitude=loc["lat"] + random.uniform(-0.003, 0.003),
                longitude=loc["lon"] + random.uniform(-0.003, 0.003),
                building_age=age,
                floor=floor,
                heating_type=random.choice(["kombi", "merkezi_pay_olcer"]),
                image_count=0,
                images=[],
                published_at=now,
                source_updated_at=now,
                first_seen_at=now,
                last_seen_at=now,
                deactivated_at=None,
                last_ingested_run_id="toki_import_run",
                is_active=True,
                lifestyle_score=round(random.uniform(6.0, 9.0), 1),
                price_market_avg=float(price_val) * random.uniform(0.95, 1.05),
                price_verdict=random.choice(["fair", "underpriced"]),
                price_trend_direction="stable",
                price_comparables_count=random.randint(5, 15),
                source="toki_dataset",
                source_listing_id=source_id,
                source_url=f"https://www.toki.gov.tr/proje/{source_id}"
            )
            listings_to_add.append(new_listing)

        db.add_all(listings_to_add)
        db.commit()
        print("Successfully generated and inserted 100 TOKİ listings!")

    except Exception as e:
        db.rollback()
        print(f"Error occurred: {e}", file=sys.stderr)
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    main()
