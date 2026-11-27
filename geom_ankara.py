# -*- coding: utf-8 -*-
"""OSM yol geometrisinden keskin kurp ve dar kesit kusurlari (Ankara).

Orijinal DGN modeli (work/geom_lib.py) OSM yol eksen cizgilerine uyarlandi:
  * KURP       : her OSM verteksunde donme acisindan R = ds / dtheta
                 (minimum 2 ardissik donme = kprili viraj VEYA tek vertekste
                  45 derece ustu donus => kritik kirisma)
                 Kavvak dugumundeki 90 derece sokak kosesi viraj sayilmaz
                 (KAVSAK_ACISI tarafindan kapsanir).
  * GENISLIK   : OSM width etiketi / lanes x 3.25 m / sinif varsayimi.
                 Yalnizca kentsel arac siniflarinda W <= 5.5 m tehlike sayilir
                 (tarla yolu / otopark servis yollari istisna).
  * DONUS_CEBI : OSM highway=turning_circle / mini_roundabout dugumleri.

Cikti: work_ankara/ankara_geom_kusurlar.jsonl
"""
import json
import math
import os
import time

import numpy as np
import pyproj

BASE = os.path.dirname(os.path.abspath(__file__))
ROADS = os.path.join(BASE, "osm_roads_ankara.jsonl")
CIRCLES = os.path.join(BASE, "osm_turning_circles.jsonl")
OUT = os.path.join(BASE, "ankara_geom_kusurlar.jsonl")

R_SCAN = 75.0        # m - bu yaricaptan kucuk kurplar tehlikeli
PHI_MIN = 4.0        # derece - gurultu on eleme
CORNER_SKIP = 30.0   # derece - kavvak dugumunde bu ustu donus "sokak kosesi"
NARROW_W = 5.5       # m - dar kesit esigi
HARD_NARROW = 3.5     # m - kritik si?e boyunu

CLASS_WIDTH = {
    "motorway": 14.0, "motorway_link": 8.0,
    "trunk": 14.0, "trunk_link": 8.0,
    "primary": 12.0, "primary_link": 7.0,
    "secondary": 10.0, "secondary_link": 7.0,
    "tertiary": 8.0, "tertiary_link": 7.0,
    "unclassified": 6.0, "residential": 6.0, "living_street": 5.0,
    "busway": 7.0, "service": 4.0, "track": 3.5, "pedestrian": 5.0,
}
# dar kesit tehlikesi uretilecek kentsel arac siniflari
NARROW_CLASSES = {"residential", "living_street", "unclassified", "tertiary",
                  "tertiary_link", "secondary", "secondary_link", "primary",
                  "primary_link", "trunk", "trunk_link", "motorway",
                  "motorway_link", "busway"}
RND = 6
tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)


def k(c):
    return (round(c[0], RND), round(c[1], RND))


def parse_num(s):
    """'6' | '6 m' | '2x3.5' -> float / None"""
    if s in (None, ""):
        return None
    s = str(s).lower().replace(",", ".").strip()
    try:
        if "x" in s or "*" in s:
            parts = [p for p in s.replace("*", "x").split("x")]
            vals = [float("".join(ch for ch in p if ch.isdigit() or ch == ".") or "nan")
                    for p in parts[:2]]
            if all(math.isfinite(v) for v in vals):
                return vals[0] * vals[1]
        num = float("".join(ch for ch in s if ch.isdigit() or ch == ".") or "nan")
        if math.isfinite(num):
            return num
    except Exception:
        return None
    return None


def lane_count(s):
    if s in (None, ""):
        return None
    s = str(s).split(";")[0].strip()
    try:
        v = int(float(s))
        return v if 1 <= v <= 8 else None
    except Exception:
        return None


def way_width(rec, hw):
    w = parse_num(rec.get("width"))
    if w and 1.0 <= w <= 30.0:
        return round(w, 2), "width_etiketi"
    ln = lane_count(rec.get("lanes"))
    if ln:
        # en az serit 3.25 m (TSE/AASHTO asgari serit genisligi)
        return round(ln * 3.25, 2), "lanesx3.25"
    d = CLASS_WIDTH.get(hw)
    if d:
        return d, "sinif_varsayimi"
    return None, ""


def main():
    t0 = time.time()
    ways = []
    with open(ROADS, encoding="utf-8") as fh:
        for line in fh:
            ways.append(json.loads(line))
    print(f"way: {len(ways):,}", flush=True)

    # --- ortak (kavvak) dugum anahtarlari ---
    owner = {}
    for wi, w in enumerate(ways):
        for c in w["coords"]:
            kk = k(c)
            if kk in owner:
                if owner[kk] != wi:
                    owner[kk] = -1
            else:
                owner[kk] = wi
    shared = {kk for kk, v in owner.items() if v == -1}
    print(f"ortak dugum: {len(shared):,}  ({time.time()-t0:.1f}s)", flush=True)

    # --- koordinatlari tek seferde UTM 36N'e projekte et ---
    all_pts, index = [], []
    for i, w in enumerate(ways):
        cs = w["coords"]
        all_pts.extend(cs)
        index.extend([i] * len(cs))
    arr = np.asarray(all_pts, dtype=float)
    xy = np.column_stack(tr.transform(arr[:, 0], arr[:, 1]))
    cursor = 0
    xy_by_way = []
    for w in ways:
        n = len(w["coords"])
        xy_by_way.append(xy[cursor:cursor + n])
        cursor += n
    print(f"projekte edildi: {len(arr):,} nokta ({time.time()-t0:.1f}s)",
          flush=True)

    recs = []
    n_kurp = 0
    n_dar = 0
    dar_kaynak = {"width_etiketi": 0, "lanesx3.25": 0, "sinif_varsayimi": 0}

    for wi, w in enumerate(ways):
        P = xy_by_way[wi]
        n = len(P)
        hw = w.get("highway") or "?"
        nm = w.get("name")
        ms = w.get("maxspeed")
        oid = w.get("osm_id")

        # ---------------- GENISLIK ----------------
        if hw in NARROW_CLASSES:
            W, src = way_width(w, hw)
            if W is not None and W <= NARROW_W:
                step = 200.0
                L = float(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])).sum()) if n > 1 else 0.0
                n_pts = max(1, min(25, int(L // step) + 1))
                if n_pts == 1 or n < 2:
                    idxs = [n // 2]
                else:
                    s_targets = np.linspace(0, L, n_pts)
                    d = np.r_[0.0, np.cumsum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))]
                    idxs = [int(np.argmin(np.abs(d - st))) for st in s_targets]
                dar_kaynak[src] = dar_kaynak.get(src, 0) + 1
                for ii in sorted(set(idxs)):
                    recs.append(dict(kind="GENISLIK", x=float(P[ii, 0]),
                                     y=float(P[ii, 1]), val=float(W),
                                     name=nm, highway=hw, maxspeed=ms,
                                     ref=w.get("ref"), osm_id=oid,
                                     kaynak=src))

        # yaya bolgesi geometrisi arac guvenligi analizi disi
        if hw == "pedestrian":
            continue
        if n < 3:
            continue

        # ---------------- KURP ----------------
        v = np.diff(P, axis=0)
        L = np.hypot(v[:, 0], v[:, 1])
        ok_seg = L >= 0.3
        phi_all = np.zeros(n - 2)
        R_all = np.full(n - 2, 1e9)
        for i in range(1, n - 1):
            if not (ok_seg[i - 1] and ok_seg[i]):
                continue
            a = v[i - 1]
            b = v[i]
            na, nb = L[i - 1], L[i]
            cos = (a[0] * b[0] + a[1] * b[1]) / (na * nb)
            cos = max(-1.0, min(1.0, cos))
            phi = math.acos(cos)                       # 0..pi
            cross = a[0] * b[1] - a[1] * b[0]
            if cross < 0:
                phi = -phi
            ds = 0.5 * (na + nb)
            phi_all[i - 1] = phi
            if abs(phi) > 1e-6:
                R_all[i - 1] = ds / abs(phi)

        cand = np.zeros(n - 2, dtype=bool)
        cand[:] = (R_all <= R_SCAN) & (np.degrees(np.abs(phi_all)) >= PHI_MIN)
        # kavvak kosesi kurali: ortak dugumde sert donus viraj degildir
        for i in range(1, n - 1):
            if cand[i - 1] and k(w["coords"][i]) in shared \
                    and abs(math.degrees(phi_all[i - 1])) >= CORNER_SKIP:
                cand[i - 1] = False

        # ardissik adaylari grupla (verteks indisinda komsuluk)
        i0 = None
        groups = []
        for i in range(n - 2):
            if cand[i]:
                if i0 is None:
                    i0 = i
            else:
                if i0 is not None:
                    groups.append((i0, i - 1))
                    i0 = None
        if i0 is not None:
            groups.append((i0, n - 3))

        for (a, b) in groups:
            seg_len = float(L[a:b + 1].sum())   # [a..b+1] segmentleri
            sub = R_all[a:b + 1]
            cnt = b - a + 1
            if cnt >= 2:
                if seg_len < 20.0:
                    continue                     # kisa yay: viraj degil
                rel = int(np.argmin(sub))
                kmin = a + rel
                Rk = float(sub[rel])
            else:
                ph = abs(math.degrees(phi_all[a]))
                if R_all[a] > 30.0 or ph < 45.0:
                    continue                     # tek donus: keskin kirisma olmali
                kmin = a
                Rk = float(R_all[a])
            if not np.isfinite(Rk) or Rk > R_SCAN:
                continue
            pt = P[kmin + 1]
            recs.append(dict(kind="KURP", x=float(pt[0]), y=float(pt[1]),
                             val=round(Rk, 1), name=nm, highway=hw,
                             maxspeed=ms, ref=w.get("ref"), osm_id=oid,
                             yay=round(seg_len, 1),
                             yon="sol" if phi_all[kmin] > 0 else "sag",
                             aci_derece=round(abs(math.degrees(phi_all[kmin])), 1)))
            n_kurp += 1

    # ---------------- DONUS CEBI ----------------
    n_circ = 0
    if os.path.exists(CIRCLES):
        with open(CIRCLES, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                x, y = tr.transform(r["lon"], r["lat"])
                rv = parse_num(r.get("radius")) or 5.0
                recs.append(dict(kind="DONUS_CEBI", x=round(x, 2), y=round(y, 2),
                                 val=round(float(rv), 1), name=None,
                                 highway=r.get("highway"), maxspeed=None,
                                 osm_id=r.get("osm_id")))
                n_circ += 1

    with open(OUT, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"KURP olayi   : {n_kurp:,}")
    print(f"GENISLIK     : {sum(1 for r in recs if r['kind']=='GENISLIK'):,} "
          f"(yol bazli kaynak: {dar_kaynak})")
    print(f"DONUS_CEBI   : {n_circ:,}")
    kurp_r = [r["val"] for r in recs if r["kind"] == "KURP"]
    if kurp_r:
        arr_r = np.array(kurp_r)
        print(f"R dagilimi   : <=15m:{(arr_r<=15).sum():,}  15-30m:{((arr_r>15)&(arr_r<=30)).sum():,}"
              f"  30-50m:{((arr_r>30)&(arr_r<=50)).sum():,}  50-75m:{((arr_r>50)&(arr_r<=75)).sum():,}"
              f"  medyan={np.median(arr_r):.1f}")
    print(f"toplam sure  : {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
