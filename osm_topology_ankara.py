# -*- coding: utf-8 -*-
"""OSM yol topolojisinden kavvak acilari ve cikmaz sokaklari (Ankara).

Yontem (work/osm_topology.py ornegi uzerine genisletilmis):
  - Her way verteks dugumu paylasan (en az 2 farkli way) ise kavvak kabul edilir
    (ornek sadece uc noktalari kullanir; burada ara dugumler de dahildir).
  - Kavvakta birlesen kol vektorlerinin farkli yollardan dar acisi hesaplanir.
  - Tek kullanimi olan ve baska bir yolla paylasilmayan uc nokta = cikmaz sokak.

Cikti:
  work_ankara/osm_intersections.jsonl   (kind=KAVSAK_ACISI)
  work_ankara/osm_deadends.jsonl        (kind=CIKMAZ_SOKAK)
"""
import collections
import json
import math
import os
import time

import pyproj

BASE = os.path.dirname(os.path.abspath(__file__))
ROADS = os.path.join(BASE, "osm_roads_ankara.jsonl")
OUT_INT = os.path.join(BASE, "osm_intersections.jsonl")
OUT_DEAD = os.path.join(BASE, "osm_deadends.jsonl")

# Ankara icin UTM 36N (metre)
tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)

RND = 6
CAR_HIER = ["motorway", "motorway_link", "trunk", "trunk_link", "primary",
            "primary_link", "secondary", "secondary_link", "tertiary",
            "tertiary_link", "residential", "unclassified", "living_street",
            "service", "track"]


def key(c):
    return (round(c[0], RND), round(c[1], RND))


def pick_highway(hws):
    for h in CAR_HIER:
        if h in hws:
            return h
    return hws[0] if hws else ""


def main():
    t0 = time.time()
    ways = []
    with open(ROADS, encoding="utf-8") as fh:
        for line in fh:
            ways.append(json.loads(line))
    print(f"yuklenen way: {len(ways):,}  ({time.time()-t0:.1f}s)", flush=True)

    # --- 1. dugum sahipligi (1. gecis) ---
    owner = {}            # key -> way idx  veya -1 (paylasimli)
    interior = set()      # ara dugum anahtarlari
    ep_count = collections.Counter()
    ep_ways = collections.defaultdict(list)

    for wi, w in enumerate(ways):
        cs = w["coords"]
        if len(cs) < 2:
            continue
        for ci, c in enumerate(cs):
            k = key(c)
            if ci == 0:
                ep_count[k] += 1
                ep_ways[k].append((wi, True))
                if k in owner and owner[k] != wi:
                    owner[k] = -1
                else:
                    owner.setdefault(k, wi)
            elif ci == len(cs) - 1:
                ep_count[k] += 1
                ep_ways[k].append((wi, False))
                if k in owner and owner[k] != wi:
                    owner[k] = -1
                else:
                    owner.setdefault(k, wi)
            else:
                interior.add(k)
                if k in owner and owner[k] != wi:
                    owner[k] = -1
                else:
                    owner.setdefault(k, wi)

    print(f"tekil dugum: {len(owner):,}  paylasimli dugum: "
          f"{sum(1 for v in owner.values() if v == -1):,}  "
          f"({time.time()-t0:.1f}s)", flush=True)

    # --- 2. paylasimli (kavvak) dugumlerde kol vektorleri ---
    node_dirs = collections.defaultdict(list)   # key -> [(dx,dy,wi), ...]
    for wi, w in enumerate(ways):
        cs = w["coords"]
        n = len(cs)
        if n < 2:
            continue
        for ci in range(n):
            k = key(cs[ci])
            if owner.get(k) != -1:
                continue
            if ci > 0:
                node_dirs[k].append((cs[ci - 1][0] - cs[ci][0],
                                     cs[ci - 1][1] - cs[ci][1], wi))
            if ci < n - 1:
                node_dirs[k].append((cs[ci + 1][0] - cs[ci][0],
                                     cs[ci + 1][1] - cs[ci][1], wi))

    key2exact = {}
    for w in ways:
        for c in w["coords"]:
            kk = key(c)
            if kk not in key2exact:
                key2exact[kk] = c

    # --- 3. dar acili kavvaklar ---
    ints = []
    for k, dirs in node_dirs.items():
        ways_at = {}
        for dx, dy, wi in dirs:
            ways_at.setdefault(wi, []).append((dx, dy))
        if len(ways_at) < 2:
            continue
        vecs = list(ways_at.values())
        minang = 180.0
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                for a in vecs[i]:
                    for b in vecs[j]:
                        na = math.hypot(a[0], a[1])
                        nb = math.hypot(b[0], b[1])
                        if na < 1e-9 or nb < 1e-9:
                            continue
                        cos = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
                        cos = max(-1.0, min(1.0, cos))
                        ang = math.degrees(math.acos(cos))
                        # ang: dallarin birbirinden uzaklastigi aci.
                        # 180 = duz devam eden ayni yol (kavvak degil),
                        # kucuk aci = keskin ayrilma / carisma acisi.
                        if ang < minang:
                            minang = ang
        if minang >= 70.0:
            continue
        c = key2exact.get(k)
        if c is None:
            continue
        x, y = tr.transform(c[0], c[1])
        wnames = [ways[wi].get("name") for wi in ways_at]
        name = next((nm for nm in wnames if nm), None)
        hws = {ways[wi].get("highway") or "?" for wi in ways_at}
        ints.append({"kind": "KAVSAK_ACISI", "x": round(x, 2), "y": round(y, 2),
                     "lon": c[0], "lat": c[1], "name": name,
                     "highway": pick_highway(list(hws)),
                     "angle_deg": round(minang, 1),
                     "n_roads": len(ways_at),
                     "yollar": ";".join(sorted(hws))})

    # --- 4. cikmaz sokaklar ---
    dead = []
    for k, cnt in ep_count.items():
        if cnt != 1:
            continue
        if k in interior or owner.get(k) == -1:
            continue
        wi, is_start = ep_ways[k][0]
        w = ways[wi]
        cs = w["coords"]
        pt = cs[0] if is_start else cs[-1]
        x, y = tr.transform(pt[0], pt[1])
        dead.append({"kind": "CIKMAZ_SOKAK", "x": round(x, 2), "y": round(y, 2),
                     "lon": pt[0], "lat": pt[1], "name": w.get("name"),
                     "highway": w.get("highway"), "osm_id": w.get("osm_id")})

    with open(OUT_INT, "w", encoding="utf-8") as fh:
        for r in ints:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT_DEAD, "w", encoding="utf-8") as fh:
        for r in dead:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    ac = collections.Counter(round(r["angle_deg"] / 5) * 5 for r in ints)
    print(f"kavvak (<70deg): {len(ints):,}  <=45deg: "
          f"{sum(1 for r in ints if r['angle_deg'] <= 45):,}")
    print(f"ac histogram (5'lik dilim): {dict(sorted(ac.items()))}")
    print(f"cikmaz sokak: {len(dead):,}")
    print(f"cikmaz highway: {collections.Counter(d['highway'] for d in dead).most_common(8)}")
    print(f"toplam sure: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
