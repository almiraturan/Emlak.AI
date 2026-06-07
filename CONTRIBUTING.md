# Contributing

Bu dokuman, projeyi yeni ceken ekip uyelerinin hizlica calisabilmesi ve tutarli sekilde katkida bulunabilmesi icin hazirlandi.

## 1) Hizli Baslangic (Docker)

1. Repo klasorune girin.
2. Ortam dosyasini olusturun:
   - Linux/macOS: `cp .env.example .env`
   - Windows PowerShell: `Copy-Item .env.example .env`
3. Servisleri baslatin:
   - `docker compose up -d --build`
4. Calistigini dogrulayin:
   - Health: http://127.0.0.1:8000/
   - Swagger: http://127.0.0.1:8000/docs
   - QA Panel: http://127.0.0.1:8000/qa

Not: Konteyner restart sonrasi ilk 5-10 saniye gecici baglanti hatasi alinabilir.

## 2) Gelistirme Akisi

1. Yeni branch acin:
   - `git checkout -b feature/<kisa-aciklama>`
2. Kod degisikligini yapin.
3. Servisleri yeniden build edip test edin:
   - `docker compose up -d --build`
4. Temel smoke test:
   - `GET /`
   - `GET /qa`
   - `GET /listings?page=1&page_size=5`

## 3) Ingestion Test Ornekleri

- Senkron ingestion:
  - `Invoke-WebRequest -Method POST http://127.0.0.1:8000/ingestion/demo-sync`
- Asenkron ingestion:
   - `Invoke-WebRequest -Method POST "http://127.0.0.1:8000/ingestion/demo-async?provider_name=emlakjet"`

## 4) Kodlama ve PR Kurallari

- Kucuk, odakli commit atmaya calisin.
- Alakasiz dosya degisikliklerini PR'a dahil etmeyin.
- API davranisini degistiren degisikliklerde README veya ilgili dokumani guncelleyin.
- DB semasi degisiyorsa Alembic migration ekleyin.

## 5) PR Checklist

PR acmadan once asagidakileri kontrol edin:

- [ ] Servisler localde basariyla kalkiyor (`docker compose up -d --build`)
- [ ] Health endpoint 200 donuyor (`GET /`)
- [ ] QA panel aciliyor (`GET /qa`)
- [ ] Ingestion endpointleri hata vermiyor
- [ ] Gerekli dokumantasyon guncellendi (README/CONTRIBUTING)

## 6) Faydalı Komutlar

- Sadece loglar:
  - `docker compose logs -f backend`
  - `docker compose logs -f worker`
- Servisleri durdur:
  - `docker compose down`
- Tam sifirla (volume dahil):
  - `docker compose down -v`
