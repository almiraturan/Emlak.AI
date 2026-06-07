# EmlakAI - Sifirdan Kurulum ve Calistirma

Bu dokuman, projeyi hic kurulu olmayan bir makinede sifirdan ayaga kaldirmak icin hazirlandi.

## 1) Gereksinimler

### Zorunlu
- Git
- Docker Desktop (Docker Engine + Docker Compose)

### Kontrol komutlari
- Windows PowerShell:
  - `git --version`
  - `docker --version`
  - `docker compose version`

Eger bu komutlardan biri calismiyorsa once ilgili araci kurun.

## 2) Projeyi cek

1. Repoyu klonlayin:
   - `git clone <REPO_URL>`
2. Proje klasorune girin:
   - `cd backend`

## 3) Ortam dosyasi (.env)

1. `.env.example` dosyasini `.env` olarak kopyalayin.

- Windows PowerShell:
  - `Copy-Item .env.example .env`

- Linux/macOS:
  - `cp .env.example .env`

2. Baslangicta varsayilan degerler yeterlidir.

## 4) Uygulamayi Docker ile kaldir

1. Build + run:
   - `docker compose up -d --build`

Bu komut sunlari baslatir:
- postgres
- redis
- backend
- worker

Not:
- `backend` container baslarken `alembic upgrade head` calisir.
- Yani migrationlar otomatik uygulanir ve tablolar otomatik olusur.

## 5) Calistigini dogrula

Tarayicidan ac:
- Health: http://127.0.0.1:8000/
- Swagger: http://127.0.0.1:8000/docs
- QA Panel: http://127.0.0.1:8000/qa

Beklenen health cevabi:
- `{"status":"ok","message":"EmlakAI backend is running"}`

## 6) Ingestion testi

### Senkron
- Swagger uzerinden `POST /ingestion/demo-sync` cagir
veya
- PowerShell:
  - `Invoke-WebRequest -Method POST "http://127.0.0.1:8000/ingestion/demo-sync?provider_name=emlakjet"`

### Asenkron
- Swagger uzerinden `POST /ingestion/demo-async` cagir
veya
- PowerShell:
  - `Invoke-WebRequest -Method POST "http://127.0.0.1:8000/ingestion/demo-async?provider_name=emlakjet"`

## 7) Gunluk komutlar

### Log izle
- `docker compose logs -f backend`
- `docker compose logs -f worker`

### Sadece yeniden baslat
- `docker compose restart backend worker`

### Tam kapat
- `docker compose down`

### Tam sifirla (volume dahil)
- `docker compose down -v`

## 8) SIK karsilasilan problemler

### Problem 1: "Baglanti beklenmedik sekilde kapatildi"
Sebep:
- Container restart/build sonrasi backend henuz ayaga kalkmamis olabilir.

Cozum:
1. 5-10 saniye bekle
2. Tekrar dene
3. Durumu kontrol et:
   - `docker compose ps`
4. Backend loguna bak:
   - `docker compose logs backend --tail 100`

### Problem 2: Port cakismasi
Sebep:
- 8000/5432/6379 portlarini baska servis kullaniyor.

Cozum:
- Cakisan servisi kapat veya `docker-compose.yml` icinde port maplerini degistir.

### Problem 3: Docker komutu bulunamiyor
Sebep:
- Docker Desktop kurulu degil veya calismiyor.

Cozum:
1. Docker Desktop kur
2. Docker Desktop'i ac
3. Komutlari tekrar calistir

## 9) Docker olmadan calistirmak (opsiyonel)

Docker olmayan ortam icin gerekenler:
- Python 3.12
- PostgreSQL
- Redis

Adimlar:
1. `py -3.12 -m venv .venv`
2. `.\.venv\Scripts\Activate.ps1`
3. `python -m pip install --upgrade pip`
4. `pip install -r requirements.txt`
5. `.env` icinde:
   - `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/emlakai`
   - `REDIS_URL=redis://localhost:6379/0`
6. `alembic upgrade head`
7. API baslat:
   - `python -m uvicorn app.main:app --app-dir . --host 127.0.0.1 --port 8000`
8. Worker baslat (ayri terminal):
   - `python -m dramatiq app.services.background --processes 1 --threads 4`

## 10) Kisa checklist (ekip arkadasi icin)

- [ ] Repo cekildi
- [ ] `.env` olusturuldu
- [ ] `docker compose up -d --build` calisti
- [ ] `/` endpoint 200 verdi
- [ ] `/docs` acildi
- [ ] `/qa` acildi
