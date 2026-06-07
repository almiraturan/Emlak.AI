# EmlakAI Backend

## Teknoloji Yigini
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Redis + Dramatiq
- Docker

## Katki Rehberi
- Ekip ici kurulum, gelistirme akisi ve PR checklist'i icin: CONTRIBUTING.md

## Ekip Icin Hızlı Kurulum (Docker)

### 1) Repoyu cek
1. Repo klasorune girin.
2. Ortam dosyasini olusturun:
   - Linux/macOS:
     - cp .env.example .env
   - Windows PowerShell:
     - Copy-Item .env.example .env

### 2) Servisleri kaldir
1. Asagidaki komutu calistirin:
   - docker compose up -d --build

Bu komut su servisleri baslatir:
- backend (FastAPI)
- worker (Dramatiq)
- postgres (PostGIS)
- redis

### 3) Calistigini dogrula
1. Health:
   - http://127.0.0.1:8000/
2. Swagger:
   - http://127.0.0.1:8000/docs
3. QA Panel:
   - http://127.0.0.1:8000/qa

Not: Container restartindan hemen sonra baglanti hatasi gorulebilir.
Bu durum genelde gecicidir; 5-10 saniye sonra tekrar deneyin.

## Hızlı Test URL ve Endpointleri

### Listing
- Liste:
  - http://127.0.0.1:8000/listings
- Tek kayit:
  - http://127.0.0.1:8000/listings/1
- Filtre ornegi:
  - http://127.0.0.1:8000/listings?city=Istanbul&min_price=3000000&sort_by=price&sort_order=asc&page=1&page_size=5

### Ingestion
- Senkron:
  - POST /ingestion/demo-sync
- Asenkron:
  - POST /ingestion/demo-async

PowerShell ornekleri:
- Invoke-WebRequest -Method POST http://127.0.0.1:8000/ingestion/demo-sync
- Invoke-WebRequest -Method POST "http://127.0.0.1:8000/ingestion/demo-async?provider_name=emlakjet"

## Kapatma ve Temiz Baslangic
- Durdur:
  - docker compose down
- Durdur + volume temizle:
  - docker compose down -v
- Log izle:
  - docker compose logs -f backend
  - docker compose logs -f worker

## Lokal Calistirma (Docker olmadan)
1. Bagimliliklari yukleyin:
   - python -m pip install -r requirements.txt
2. .env icinde DATABASE_URL ve REDIS_URL degerlerini lokal ortama gore ayarlayin.
3. Migrationlari calistirin:
   - alembic upgrade head
4. API'yi baslatin:
   - python -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000

## Ingestion Akisi (Guncel)
- Provider katmani ham veriyi ceker ve normalize eder.
- Ingestion katmani source + source_listing_id ile upsert yapar.
- Kayıt yoksa insert, varsa update veya degisim yoksa skipped olur.
- Full sync acik providerlarda bu turda gorunmeyen eski kayitlar deactivated olur.
- Tum sonuc ve ham payload ingestion_records tablosuna yazilir.

## Notlar
- Mock/seed listing verisi kod tabanindan kaldirildi; startup seed fonksiyonu no-op olarak korunur.
- Tablo olusturma ve schema degisiklikleri Alembic ile yonetilir.
