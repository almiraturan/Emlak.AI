import sys, os, time, math
import httpx
import psycopg

DB_URL = "postgresql://postgres:postgres@postgres:5432/emlakai"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

POI_WEIGHTS = {"school":1.5,"hospital":2.0,"bus":1.5,"subway":2.5,"park":1.0,"supermarket":1.5,"restaurant":0.5}
MAX_SCORE = 5.0 * sum(POI_WEIGHTS.values())  # 52.5

CATEGORY_SEARCH_RADIUS_M = {"school":5000,"hospital":5000,"bus":5000,"subway":5000,"park":5000,"supermarket":2000,"restaurant":2000}
CATEGORY_COUNT_RADIUS_M  = {"school":1000,"hospital":3000,"bus":1000,"subway":1000,"park":1000,"supermarket":1000,"restaurant":1000}

TAG_MAP = [
    (("amenity","school"),"school"), (("amenity","university"),"school"),
    (("amenity","college"),"school"), (("amenity","kindergarten"),"school"),
    (("amenity","hospital"),"hospital"),
    (("highway","bus_stop"),"bus"), (("railway","subway_entrance"),"subway"),
    (("leisure","park"),"park"), (("shop","supermarket"),"supermarket"),
    (("amenity","restaurant"),"restaurant"),
]

def haversine(lat1,lon1,lat2,lon2):
    R=6371.0; dl=math.radians(lat2-lat1); dlo=math.radians(lon2-lon1)
    a=math.sin(dl/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlo/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def fetch_pois(lat, lon):
    sr = CATEGORY_SEARCH_RADIUS_M
    q = (
        "[out:json][timeout:30];\n(\n"
        f'  nwr["amenity"="school"](around:{sr["school"]},{lat},{lon});\n'
        f'  nwr["amenity"="university"](around:{sr["school"]},{lat},{lon});\n'
        f'  nwr["amenity"="college"](around:{sr["school"]},{lat},{lon});\n'
        f'  nwr["amenity"="kindergarten"](around:{sr["school"]},{lat},{lon});\n'
        f'  nwr["amenity"="hospital"](around:{sr["hospital"]},{lat},{lon});\n'
        f'  node["highway"="bus_stop"](around:{sr["bus"]},{lat},{lon});\n'
        f'  node["railway"="subway_entrance"](around:{sr["subway"]},{lat},{lon});\n'
        f'  nwr["leisure"="park"](around:{sr["park"]},{lat},{lon});\n'
        f'  node["shop"="supermarket"](around:{sr["supermarket"]},{lat},{lon});\n'
        f'  node["amenity"="restaurant"](around:{sr["restaurant"]},{lat},{lon});\n'
        ");\nout center tags qt;"
    )
    headers = {"User-Agent": "EmlakAI/1.0 (contact: dev@localhost)", "Accept": "application/json"}
    for ep in OVERPASS_ENDPOINTS:
        try:
            r = httpx.post(ep, data={"data":q}, headers=headers, timeout=35)
            if r.status_code == 200:
                return r.json().get("elements", [])
        except Exception:
            continue
    return None

def score_from_elements(lat, lon, elements):
    counts = {k:0 for _,k in TAG_MAP}
    for el in elements:
        tags = el.get("tags") or {}
        for (tk,tv),cat in TAG_MAP:
            if tags.get(tk)==tv:
                elat = el.get("lat") or (el.get("center") or {}).get("lat")
                elon = el.get("lon") or (el.get("center") or {}).get("lon")
                if elat and elon:
                    d = haversine(lat,lon,elat,elon)
                    if d <= CATEGORY_COUNT_RADIUS_M[cat]/1000.0:
                        counts[cat] += 1
                break
    total = sum(min(v,5)*POI_WEIGHTS[k] for k,v in counts.items())
    raw = 1.0 + (total / MAX_SCORE) * 9.0
    return round(min(9.9, max(1.0, raw)), 1), counts

def main():
    conn = psycopg.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT id, latitude, longitude FROM listings WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY id")
    rows = cur.fetchall()
    total = len(rows)
    print(f"Toplam {total} ilan isleniyor...", flush=True)

    updated = 0
    failed = 0
    for i, (lid, lat, lon) in enumerate(rows):
        elements = fetch_pois(lat, lon)
        if elements is None:
            print(f"[{i+1}/{total}] ID={lid} HATA", flush=True)
            failed += 1
            time.sleep(3)
            continue
        score, counts = score_from_elements(lat, lon, elements)
        cur.execute("UPDATE listings SET lifestyle_score=%s WHERE id=%s", (score, lid))
        conn.commit()
        updated += 1
        print(f"[{i+1}/{total}] ID={lid} -> {score} | sch={counts['school']} hos={counts['hospital']} bus={counts['bus']} park={counts['park']}", flush=True)
        time.sleep(1.2)

    cur.close()
    conn.close()
    print(f"\nTamamlandi: {updated} guncellendi, {failed} basarisiz", flush=True)

if __name__ == "__main__":
    main()
