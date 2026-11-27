# -*- coding: utf-8 -*-
"""work/turkey-latest.osm.pbf -> Ankara ili OSM yol verisi (JSONL).

Sadece OpenStreetMap verisi kullanilir (DGN / sensor / olcum verisi yok).

Cikti:
  work_ankara/osm_roads_ankara.jsonl        : arac yolu wayleri (etiketlerle)
  work_ankara/osm_turning_circles.jsonl      : donus cepleri / mini kavvak dugumleri
"""
import json
import os
import time

import osmium

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
PBF = os.path.join(ROOT, "work", "turkey-latest.osm.pbf")
OUT = os.path.join(BASE, "osm_roads_ankara.jsonl")
OUT_CIRCLES = os.path.join(BASE, "osm_turning_circles.jsonl")

# Ankara il sinir kutusu (minlon, minlat, maxlon, maxlat)
BBOX = (30.83, 38.69, 33.90, 40.75)

# Yaya/altyazi siniflari (arac guvenligi analizi disi)
SKIP = {"footway", "steps", "path", "cycleway", "bridleway", "corridor",
        "elevator", "platform", "construction", "proposed", "raceway"}

KEEP_TAGS = ("highway", "name", "ref", "lanes", "maxspeed", "maxspeed:forward",
             "maxspeed:backward", "oneway", "surface", "junction", "bridge",
             "tunnel", "width", "service", "access", "lit", "traffic_calming",
             "turning", "sidewalk", "barrier", "area")


class RoadHandler(osmium.SimpleHandler):
    def __init__(self, out, out_circles):
        super().__init__()
        self.out = out
        self.out_circles = out_circles
        self.n = 0
        self.n_circ = 0

    def way(self, w):
        tags = w.tags
        hw = tags.get("highway")
        if hw is None or hw in SKIP:
            return
        try:
            coords = [(n.lon, n.lat) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(coords) < 2:
            return
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        if (max(xs) < BBOX[0] or min(xs) > BBOX[2]
                or max(ys) < BBOX[1] or min(ys) > BBOX[3]):
            return
        rec = {"osm_id": w.id}
        for t in KEEP_TAGS:
            rec[t.replace(":", "_")] = tags.get(t)
        rec["coords"] = [[round(c[0], 7), round(c[1], 7)] for c in coords]
        self.out.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.n += 1

    def node(self, n):
        try:
            hw = n.tags.get("highway")
        except Exception:
            return
        if hw not in ("turning_circle", "mini_roundabout"):
            return
        lon, lat = n.lon, n.lat
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            return
        self.out_circles.write(json.dumps(
            {"osm_id": n.id, "highway": hw, "lon": round(lon, 7),
             "lat": round(lat, 7),
             "radius": n.tags.get("radius")},
            ensure_ascii=False) + "\n")
        self.n_circ += 1


def main():
    t = time.time()
    if not os.path.exists(PBF):
        raise SystemExit(f"PBF bulunamadi: {PBF}")
    print(f"[1/2] PBF okunuyor: {PBF}", flush=True)
    with open(OUT, "w", encoding="utf-8") as fh, \
         open(OUT_CIRCLES, "w", encoding="utf-8") as fc:
        h = RoadHandler(fh, fc)
        h.apply_file(PBF, locations=True, idx="flex_mem")
    print(f"[2/2] yollar: {h.n:,}  donus cebi: {h.n_circ:,}  "
          f"sure: {time.time()-t:.1f} sn")
    print(f"     -> {OUT}")
    print(f"     -> {OUT_CIRCLES}")


if __name__ == "__main__":
    main()
