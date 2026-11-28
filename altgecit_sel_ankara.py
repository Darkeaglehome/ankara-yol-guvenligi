# -*- coding: utf-8 -*-
"""
altgecit_sel_ankara.py
======================
Ankara il sınırları içindeki TÜM OpenStreetMap alt geçit / tünel yapılarını
çıkarır ve Copernicus DEM GLO-30 (30 m) üzerinden su baskını riskini puanlar.

Girdiler
--------
  overpass_altgecit_ankara.json : OSM (Overpass) alt geçit/tünel way kayıtları
  overpass_su_ankara.json      : OSM akarsu/kanal/drenaj çizgileri
  osm_roads_ankara.jsonl       : OSM araç yolu ağı (şehir geneli tarama için)
  dem_ankara_utm.tif           : Copernicus DEM GLO-30, UTM 36N
  egim_ankara_utm.tif          : DEM'den Horn yöntemiyle üretilmiş eğim (x10)
  ../ankara_ilce_sinirlari.geojson : ilçe sınırları

Çıktılar
--------
  osm_altgecitler.jsonl            : yapı bazlı alt geçit envanteri
  Ankara_OSM_Alt_Gecitler.csv      : tüm alt geçitler (öncelik sıralı)
  Ankara_OSM_Sel_Riskli_Noktalar.csv : sel riskli alt geçit + yol kesimleri
  Ankara_OSM_Sel_Ilce_Ozeti.csv    : ilçe bazlı sel riski özeti

Yöntem
------
1) Alt geçitler OSM'den highway + tunnel / layer<0 etiketleriyle alınır;
   ortak düğümler üzerinden bağlı way'ler tek yapıya birleştirilir.
2) Her yapının en düşük kotlu noktası DEM'den bulunur.
3) Yerel hidrolojik analiz (1.2-1.5 km pencere):
   - Priority-Flood ile çukur doldurma ve akış yönü ağacı
   - Akış birikim alanı (ha) ve memba ortalama eğimi
   - Yerel çukur derinliği (150-600 m halka ortalaması - taban kotu)
   - Havza konumu (pencere ortalaması - taban kotu)
4) OSM su yollarına (dere/kanal/drenaj) kuş uçuşu mesafe.
5) 0-100 Sel Risk Skoru: çukur, birikim, eğim, kot konumu, su yakınlığı ve
   maruziyet (yol sınıfı, uzunluk, yaya kullanımı) bileşenleri.
6) Ayrıca tüm araç yolu ağı taranarak düşük kotlu/düz yol kesimleri bulunur;
   bunlar da aynı hidrolojik modelle puanlanır.
"""
import collections
import heapq
import json
import math
import os
import time

import numpy as np
import pandas as pd
import pyproj
import rasterio
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

UP_JSON = os.path.join(BASE, "overpass_altgecit_ankara.json")
WATER_JSON = os.path.join(BASE, "overpass_su_ankara.json")
ROADS = os.path.join(BASE, "osm_roads_ankara.jsonl")
DEM = os.path.join(BASE, "dem_ankara_utm.tif")
SLOPE = os.path.join(BASE, "egim_ankara_utm.tif")
ILCE = os.path.join(ROOT, "ankara_ilce_sinirlari.geojson")

OUT_JSONL = os.path.join(BASE, "osm_altgecitler.jsonl")
OUT_UP_CSV = os.path.join(BASE, "Ankara_OSM_Alt_Gecitler.csv")
OUT_SEL_CSV = os.path.join(BASE, "Ankara_OSM_Sel_Riskli_Noktalar.csv")
OUT_ILCE_CSV = os.path.join(BASE, "Ankara_OSM_Sel_Ilce_Ozeti.csv")
OUT_SUMMARY = os.path.join(BASE, "sel_analiz_ozet.json")

RES = 30.0
CRS = 32636
tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)
tr_inv = pyproj.Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True)

PED_HW = {"footway", "steps", "path", "pedestrian", "corridor"}
VEH_HW = {"motorway", "motorway_link", "trunk", "trunk_link",
          "primary", "primary_link", "secondary", "secondary_link",
          "tertiary", "tertiary_link", "unclassified", "residential",
          "living_street", "service", "track", "busway"}
VEH_ORDER = ["motorway", "trunk", "primary", "secondary", "tertiary",
             "unclassified", "residential", "living_street", "service",
             "track", "busway"]
SKIP_TUNNEL = {"culvert", "canal", "pipe"}
ROAD_SCAN_HW = {"motorway", "motorway_link", "trunk", "trunk_link",
                "primary", "primary_link", "secondary", "secondary_link",
                "tertiary", "tertiary_link", "unclassified", "residential",
                "living_street", "service"}

SEVIYE_RENK = {
    "Çok Yüksek": "#7B241C",
    "Yüksek": "#C0392B",
    "Orta": "#E67E22",
    "Düşük": "#F1C40F",
    "Çok Düşük": "#27AE60",
}


# --------------------------------------------------------------------------- #
#  yardımcılar
# --------------------------------------------------------------------------- #
def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def xy_of(coords):
    """[(lon, lat), ...] -> np.array([[x, y], ...]) UTM 36N"""
    a = np.asarray(coords, dtype=float)
    x, y = tr.transform(a[:, 0], a[:, 1])
    return np.column_stack([x, y])


def line_length(P):
    if len(P) < 2:
        return 0.0
    d = np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))
    return float(d.sum())


def classify_score(s):
    if s >= 70:
        return "Çok Yüksek"
    if s >= 55:
        return "Yüksek"
    if s >= 40:
        return "Orta"
    if s >= 25:
        return "Düşük"
    return "Çok Düşük"


# --------------------------------------------------------------------------- #
#  raster örnekleme (blok blok, düşük bellek)
# --------------------------------------------------------------------------- #
def _bilinear_block(arr, r, c):
    """arr: blok dizisi, r/c: blok içi piksel koordinatları (0 tabanlı)."""
    h, w = arr.shape
    r = np.clip(r, 0, h - 2)
    c = np.clip(c, 0, w - 2)
    r0 = np.floor(r).astype("int64")
    c0 = np.floor(c).astype("int64")
    dr = r - r0
    dc = c - c0
    v = (arr[r0, c0] * (1 - dc) * (1 - dr) +
         arr[r0, c0 + 1] * dc * (1 - dr) +
         arr[r0 + 1, c0] * (1 - dc) * dr +
         arr[r0 + 1, c0 + 1] * dc * dr)
    return v


def sample_rasters(xy, tpi_radii=(500, 1500)):
    """DEM kot, eğim (%) ve çok ölçekli TPI değerlerini noktalarda örnekler.

    TPI = yerel ortalama kot - nokta kotu (pozitif = çukurda).
    """
    from scipy.ndimage import uniform_filter

    n = len(xy)
    z = np.full(n, np.nan, dtype="float32")
    egim = np.full(n, np.nan, dtype="float32")
    tpi = {r: np.full(n, np.nan, dtype="float32") for r in tpi_radii}
    std = {r: np.full(n, np.nan, dtype="float32") for r in tpi_radii}

    with rasterio.open(DEM) as dd, rasterio.open(SLOPE) as sd:
        T = dd.transform
        W, H = dd.width, dd.height
        cols = (xy[:, 0] - T.c) / T.a - 0.5
        rows = (T.f - xy[:, 1]) / abs(T.e) - 0.5
        halo = int(max(tpi_radii) / RES) + 3
        STEP = 512
        for r0 in range(0, H, STEP):
            r1 = min(H, r0 + STEP)
            sel = np.where((rows >= r0 - 1) & (rows < r1 + 1) &
                           (cols >= -1) & (cols <= W))[0]
            if len(sel) == 0:
                continue
            hr0 = max(0, r0 - halo)
            hr1 = min(H, r1 + halo)
            dem = dd.read(1, window=((hr0, hr1), (0, W))).astype("float32")
            dem[dem == dd.nodata] = np.nan
            filled = np.where(np.isfinite(dem), dem, np.nanmedian(dem))

            lr = rows[sel] - hr0
            lc = cols[sel]
            z[sel] = _bilinear_block(dem, lr, lc)

            sl = sd.read(1, window=((hr0, hr1), (0, W))).astype("float32") / 10.0
            sl[sl == 0] = np.nan
            egim[sel] = _bilinear_block(sl, lr, lc)

            for rad in tpi_radii:
                size = int(round(2 * rad / RES)) + 1
                mean = uniform_filter(filled, size=size, mode="nearest")
                sq = uniform_filter(filled * filled, size=size, mode="nearest")
                var = np.maximum(sq - mean * mean, 0.0)
                sigma = np.sqrt(var)
                mean = np.where(np.isfinite(dem), mean, np.nan)
                sigma = np.where(np.isfinite(dem), sigma, np.nan)
                tpi[rad][sel] = _bilinear_block(mean, lr, lc) - z[sel]
                std[rad][sel] = _bilinear_block(sigma, lr, lc)
    return z, egim, tpi, std


# --------------------------------------------------------------------------- #
#  yerel hidroloji: Priority-Flood + akış ağacı
# --------------------------------------------------------------------------- #
def hydrology(dem, egim, out_r, out_c):
    """Pencere DEM üzerinde çukur doldurma, akış birikimi ve memba analizi."""
    h, w = dem.shape
    valid = np.isfinite(dem)
    if valid.sum() < 100:
        return None
    work = np.where(valid, dem, np.nanmax(dem) + 50.0).astype("float32")
    flat = work.ravel()

    parent = np.full(h * w, -1, dtype="int64")
    vis = np.zeros(h * w, dtype=bool)
    order = []
    heap = []

    for r in range(h):
        for c in (0, w - 1):
            heapq.heappush(heap, (flat[r * w + c], r * w + c, -1))
    for c in range(w):
        for r in (0, h - 1):
            heapq.heappush(heap, (flat[r * w + c], r * w + c, -1))

    while heap:
        zc, idx, pidx = heapq.heappop(heap)
        if vis[idx]:
            continue
        vis[idx] = True
        parent[idx] = pidx
        order.append(idx)
        r, c = divmod(idx, w)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w:
                    ni = nr * w + nc
                    if not vis[ni]:
                        heapq.heappush(heap, (max(flat[ni], zc), ni, idx))

    acc = np.ones(h * w, dtype="float32")
    ssum = np.where(np.isfinite(egim), egim, 0.0).astype("float32").ravel()
    for idx in reversed(order):
        p = parent[idx]
        if p >= 0:
            acc[p] += acc[idx]
            ssum[p] += ssum[idx]

    outlet = out_r * w + out_c
    if not vis[outlet]:
        return None
    akim_ha = float(acc[outlet]) * (RES * RES) / 10000.0
    yamac = float(ssum[outlet] / max(acc[outlet], 1.0))

    # yerel çukur ve havza konumu
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot((yy - out_r) * RES, (xx - out_c) * RES)
    z0 = float(dem[out_r, out_c])
    ring = valid & (dist >= 150) & (dist <= 600)
    havza = valid & (dist <= 1500)
    cukur = float(np.median(dem[ring]) - z0) if ring.sum() > 20 else 0.0
    havza_d = float(np.mean(dem[havza]) - z0) if havza.sum() > 50 else 0.0
    tpi500 = float(np.mean(dem[valid & (dist <= 500)]) - z0) if valid.any() else 0.0
    return {
        "kot_m": round(z0, 1),
        "cukur_m": round(max(0.0, cukur), 2),
        "havza_m": round(max(0.0, havza_d), 2),
        "tpi500": round(tpi500, 2),
        "relief_m": round(float(np.percentile(dem[valid & (dist <= 300)], 90) -
                                np.percentile(dem[valid & (dist <= 300)], 10)), 1)
        if (valid & (dist <= 300)).sum() > 20 else 0.0,
        "akim_ha": round(akim_ha, 1),
        "yamac_pct": round(yamac, 1),
    }


def window_around(ds, x, y, radius_m):
    T = ds.transform
    col = (x - T.c) / T.a
    row = (T.f - y) / abs(T.e)
    half = int(radius_m / RES)
    c0 = max(0, int(col) - half)
    c1 = min(ds.width, int(col) + half + 1)
    r0 = max(0, int(row) - half)
    r1 = min(ds.height, int(row) + half + 1)
    return r0, r1, c0, c1


# --------------------------------------------------------------------------- #
#  alt geçit yapıları
# --------------------------------------------------------------------------- #
def build_structures(elements):
    ways = []
    for e in elements:
        t = e.get("tags", {})
        hw = t.get("highway")
        if not hw or hw in ("construction", "proposed"):
            # yapım/proje kapsamı ayrı işaretlenir, envanterde tutulur
            pass
        if not hw:
            continue
        if t.get("tunnel") in SKIP_TUNNEL:
            continue
        geom = e.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [(g["lon"], g["lat"]) for g in geom]
        ways.append({
            "osm_id": e["id"],
            "nodes": e.get("nodes") or [],
            "tags": t,
            "coords": coords,
        })

    # bağlı bileşenler (ortak OSM düğümü)
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for w in ways:
        ns = w["nodes"]
        for n in ns[1:]:
            union(ns[0], n)

    comps = collections.defaultdict(list)
    for w in ways:
        ns = w["nodes"]
        key = find(ns[0]) if ns else ("way", w["osm_id"])
        comps[key].append(w)

    structures = []
    for i, (key, ws) in enumerate(sorted(comps.items(), key=lambda kv: str(kv[0]))):
        tags = [w["tags"] for w in ws]
        hws = [t.get("highway") for t in tags if t.get("highway")]
        names = [t.get("name") for t in tags if t.get("name")]
        tunnels = [t.get("tunnel") for t in tags if t.get("tunnel")]
        coords = []
        for w in ws:
            coords.extend(w["coords"])
        P = xy_of(coords)
        # her way'in kendi uzunluğu (segmentler arası atlama sayılmaz)
        L = sum(line_length(xy_of(w["coords"])) for w in ws)

        hw = ""
        for cand in VEH_ORDER:
            if cand in hws:
                hw = cand
                break
        if not hw and hws:
            hw = hws[0]

        is_ped = hw in PED_HW
        tunnel = next((t for t in tunnels if t != "no"), None)
        name = collections.Counter(names).most_common(1)[0][0] if names else ""
        layer = None
        for t in tags:
            try:
                lv = int(float(t.get("layer")))
                layer = lv if layer is None else min(layer, lv)
            except (TypeError, ValueError):
                pass

        if is_ped:
            tip = "Yaya Alt Geçidi"
        elif tunnel == "building_passage":
            tip = "Yapı Geçişi"
        elif hw in VEH_HW and L >= 300:
            tip = "Araç Tüneli"
        elif hw in VEH_HW:
            tip = "Araç Alt Geçidi"
        else:
            tip = "Diğer Geçiş"

        durum = "Mevcut"
        if any(t.get("highway") in ("construction", "proposed") for t in tags):
            durum = "Yapım/Proje"
            if tip == "Diğer Geçiş":
                tip = "Yapım/Proje Geçişi"

        lit_vals = [t.get("lit") for t in tags if t.get("lit")]
        lit = "yes" if "yes" in lit_vals else ("no" if lit_vals else "")
        surface = next((t.get("surface") for t in tags if t.get("surface")), "")
        otag = {}
        for t in tags:
            for k in ("maxheight", "lanes", "maxspeed", "width", "ref",
                      "sidewalk", "covered", "flooded", "incline"):
                if t.get(k) and k not in otag:
                    otag[k] = t.get(k)

        structures.append({
            "yapi_id": f"AG{i+1:04d}",
            "osm_ids": [w["osm_id"] for w in ws],
            "n_way": len(ws),
            "ad": name,
            "gecit_tipi": tip,
            "yol_sinifi": hw,
            "tunnel": tunnel,
            "layer": layer,
            "durum": durum,
            "uzunluk_m": round(L, 1),
            "lit": lit,
            "surface": surface,
            "etiketler": otag,
            "coords": coords,
        })
    return structures


# --------------------------------------------------------------------------- #
#  su yolları
# --------------------------------------------------------------------------- #
def build_water_tree():
    data = load_json(WATER_JSON)
    lines, types, names = [], [], []
    for e in data["elements"]:
        t = e.get("tags", {})
        geom = e.get("geometry") or []
        if len(geom) < 2:
            continue
        coords = [(g["lon"], g["lat"]) for g in geom]
        P = xy_of(coords)
        if len(P) < 2:
            continue
        lines.append(LineString(P))
        types.append(t.get("waterway", "?"))
        names.append(t.get("name", ""))
    return STRtree(lines), lines, types, names


def water_distance(pt, tree, lines, types, names):
    if not lines:
        return None, "", ""
    i = int(tree.nearest(pt))
    return round(float(lines[i].distance(pt)), 1), types[i], names[i]


# --------------------------------------------------------------------------- #
#  puanlama
# --------------------------------------------------------------------------- #
def exposure_score(tip, hw, L):
    if tip == "Yaya Alt Geçidi":
        s = 6
    else:
        s = {"motorway": 8, "motorway_link": 8, "trunk": 8, "trunk_link": 7,
             "primary": 7, "primary_link": 6, "secondary": 6,
             "secondary_link": 5, "tertiary": 5, "tertiary_link": 4,
             "unclassified": 4, "residential": 4, "living_street": 3,
             "service": 3, "track": 2, "busway": 5}.get(hw, 2)
    s += 4 if L >= 200 else (3 if L >= 100 else (2 if L >= 50 else 1))
    return min(s, 16)


def flood_score(cukur, havza, akim, yamac, su_m, expo, flooded_flag=False):
    s = 0.0
    # 1) yerel çukur derinliği (0-25)
    if cukur >= 6:
        s += 25
    elif cukur >= 4:
        s += 20
    elif cukur >= 2.5:
        s += 15
    elif cukur >= 1.2:
        s += 9
    elif cukur >= 0.5:
        s += 4
    # 2) havza / vadi konumu (0-12)
    if havza >= 10:
        s += 12
    elif havza >= 6:
        s += 9
    elif havza >= 3:
        s += 6
    elif havza >= 1:
        s += 3
    # 3) akış birikim alanı (0-25)
    if akim >= 400:
        s += 25
    elif akim >= 200:
        s += 21
    elif akim >= 100:
        s += 17
    elif akim >= 50:
        s += 12
    elif akim >= 20:
        s += 7
    elif akim >= 5:
        s += 3
    # 4) memba yamaç eğimi - ani akış (0-12)
    if yamac >= 15:
        s += 12
    elif yamac >= 10:
        s += 9
    elif yamac >= 7:
        s += 6
    elif yamac >= 4:
        s += 3
    # 5) dere / kanal yakınlığı (0-10)
    if su_m is not None:
        if su_m <= 25:
            s += 10
        elif su_m <= 75:
            s += 8
        elif su_m <= 150:
            s += 5
        elif su_m <= 300:
            s += 3
    # 6) maruziyet
    s += expo
    if flooded_flag:
        s += 10
    # akış birikimi çok düşükse derinlik tek başına sel riski doğurmaz
    if akim < 2:
        s *= 0.70
    elif akim < 5:
        s *= 0.85
    return round(min(100.0, s), 1)


def road_hotspot_score(cukur, relief, havza, akim, yamac, su_m, hw, density):
    """Düz ve alçak yol kesimleri için sel eğilim skoru (0-100)."""
    s = 0.0
    c = min(max(cukur, 0.0), 6.0)
    if c >= 4.0:
        s += 24
    elif c >= 2.5:
        s += 19
    elif c >= 1.2:
        s += 13
    elif c >= 0.5:
        s += 7
    # düzlük: taşkın yatağının en güçlü göstergesi
    if relief <= 4:
        s += 14
    elif relief <= 8:
        s += 11
    elif relief <= 12:
        s += 7
    elif relief <= 18:
        s += 3
    if akim >= 600:
        s += 28
    elif akim >= 300:
        s += 24
    elif akim >= 150:
        s += 19
    elif akim >= 70:
        s += 13
    elif akim >= 30:
        s += 8
    elif akim >= 10:
        s += 4
    if yamac >= 15:
        s += 10
    elif yamac >= 10:
        s += 7
    elif yamac >= 7:
        s += 5
    elif yamac >= 4:
        s += 2
    if su_m is not None:
        if su_m <= 20:
            s += 14
        elif su_m <= 60:
            s += 11
        elif su_m <= 120:
            s += 8
        elif su_m <= 250:
            s += 5
        elif su_m <= 500:
            s += 2
    if havza >= 10:
        s += 6
    elif havza >= 5:
        s += 4
    elif havza >= 2:
        s += 2
    s += {"motorway": 4, "trunk": 4, "primary": 3, "secondary": 2,
          "tertiary": 2, "residential": 1, "unclassified": 1}.get(hw, 0)
    # kentsel yoğunluk (maruz kalan nüfus/trafik proxy'si)
    if density >= 800:
        s += 12
    elif density >= 400:
        s += 10
    elif density >= 200:
        s += 7
    elif density >= 100:
        s += 4
    elif density >= 50:
        s += 2
    return round(min(100.0, s), 1)


# --------------------------------------------------------------------------- #
#  ana akış
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    print("[1/7] OSM alt geçit kayıtları okunuyor...", flush=True)
    up_data = load_json(UP_JSON)
    structures = build_structures(up_data["elements"])
    print(f"      -> {len(structures):,} alt geçit/tünel yapısı", flush=True)

    # tüm yapı köşe noktaları için DEM örnekleme
    print("[2/7] DEM kot / eğim örnekleme...", flush=True)
    verts, ranges = [], []
    for s in structures:
        P = xy_of(s["coords"])
        ranges.append((len(verts), len(verts) + len(P)))
        verts.append(P)
    allv = np.vstack(verts) if verts else np.zeros((0, 2))
    zv, egv, _, _ = sample_rasters(allv)
    for si, (s, (a, b)) in enumerate(zip(structures, ranges)):
        zz = zv[a:b]
        if np.isfinite(zz).any():
            j = int(np.nanargmin(zz))
            s["_low_xy"] = (float(allv[a + j, 0]), float(allv[a + j, 1]))
            s["kot_min_m"] = round(float(zz[j]), 1)
            s["kot_max_m"] = round(float(np.nanmax(zz)), 1)
            s["egim_yuzde"] = round(float(np.nanmedian(egv[a:b])), 1)
        else:
            P = verts[si]
            s["_low_xy"] = (float(np.mean(P[:, 0])), float(np.mean(P[:, 1])))
            s["kot_min_m"] = np.nan
            s["kot_max_m"] = np.nan
            s["egim_yuzde"] = np.nan
    print(f"      -> {len(allv):,} köşe noktası ({time.time()-t0:.0f}s)", flush=True)

    # aynı konumdaki (80 m) aynı tip parçaları tek yapıda birleştir:
    # büyük yaya alt geçidi ağlarının ayrı giriş/segmentleri tek noktaya iner.
    groups = collections.defaultdict(list)
    for s in structures:
        key = (int(round(s["_low_xy"][0] / 80.0)),
               int(round(s["_low_xy"][1] / 80.0)), s["gecit_tipi"])
        groups[key].append(s)
    merged = []
    for g in groups.values():
        if len(g) == 1:
            merged.append(g[0])
            continue
        base = dict(g[0])
        base["osm_ids"] = [i for x in g for i in x["osm_ids"]]
        base["n_way"] = sum(x["n_way"] for x in g)
        base["uzunluk_m"] = round(sum(x["uzunluk_m"] for x in g), 1)
        base["coords"] = [c for x in g for c in x["coords"]]
        base["kot_min_m"] = float(np.nanmin([x["kot_min_m"] for x in g]))
        base["kot_max_m"] = float(np.nanmax([x["kot_max_m"] for x in g]))
        base["egim_yuzde"] = round(float(np.nanmean(
            [x["egim_yuzde"] for x in g])), 1)
        nm = collections.Counter(x["ad"] for x in g if x["ad"])
        base["ad"] = nm.most_common(1)[0][0] if nm else ""
        et = {}
        for x in g:
            for k, v in (x.get("etiketler") or {}).items():
                et.setdefault(k, v)
        base["etiketler"] = et
        base["lit"] = "yes" if any(x["lit"] == "yes" for x in g) else (
            "no" if any(x["lit"] == "no" for x in g) else "")
        base["surface"] = next((x["surface"] for x in g if x["surface"]), "")
        lv = [x["layer"] for x in g if x["layer"] is not None]
        base["layer"] = min(lv) if lv else None
        base["durum"] = ("Mevcut" if any(x["durum"] == "Mevcut" for x in g)
                         else "Yapım/Proje")
        base["_low_xy"] = min(
            (x["_low_xy"] for x in g),
            key=lambda p: (p[0] - base["_low_xy"][0]) ** 2 +
                          (p[1] - base["_low_xy"][1]) ** 2)
        merged.append(base)
    structures = merged
    for i, s in enumerate(structures):
        s["yapi_id"] = f"AG{i+1:04d}"
    print(f"      -> aynı konum birleştirmesi sonrası {len(structures):,} yapı",
          flush=True)

    print("[3/7] Su yolu ağı hazırlanıyor...", flush=True)
    tree, wlines, wtypes, wnames = build_water_tree()
    print(f"      -> {len(wlines):,} dere/kanal çizgisi", flush=True)

    print("[4/7] Yerel hidrolojik analiz (alt geçitler)...", flush=True)
    dem_ds = rasterio.open(DEM)
    sl_ds = rasterio.open(SLOPE)
    for i, s in enumerate(structures):
        x, y = s["_low_xy"]
        r0, r1, c0, c1 = window_around(dem_ds, x, y, 1200)
        dem = dem_ds.read(1, window=((r0, r1), (c0, c1))).astype("float32")
        dem[dem == dem_ds.nodata] = np.nan
        eg = sl_ds.read(1, window=((r0, r1), (c0, c1))).astype("float32") / 10.0
        T = dem_ds.transform
        outc = int(round((x - T.c) / T.a)) - c0
        outr = int(round((T.f - y) / abs(T.e))) - r0
        outc = min(max(outc, 0), dem.shape[1] - 1)
        outr = min(max(outr, 0), dem.shape[0] - 1)
        hm = hydrology(dem, eg, outr, outc) if dem.size else None
        s.update(hm or {"kot_m": s["kot_min_m"], "cukur_m": 0.0,
                        "havza_m": 0.0, "tpi500": 0.0, "akim_ha": 0.0,
                        "yamac_pct": 0.0})
        d, wt, wn = water_distance(Point(x, y), tree, wlines, wtypes, wnames)
        s["su_mesafe_m"] = d
        s["su_tipi"] = wt
        s["su_adi"] = wn
        s["x"], s["y"] = round(x, 2), round(y, 2)
        lon, lat = tr_inv.transform(x, y)
        s["lon"], s["lat"] = round(lon, 6), round(lat, 6)
        s["expo"] = exposure_score(s["gecit_tipi"], s["yol_sinifi"],
                                   s["uzunluk_m"])
        flag = (str(s["tunnel"]).lower() == "flooded" or
                str(s["etiketler"].get("flooded")).lower() in ("yes", "true"))
        s["sel_etiketi"] = bool(flag)
        s["sel_risk_skoru"] = flood_score(
            s["cukur_m"], s["havza_m"], s["akim_ha"], s["yamac_pct"],
            s["su_mesafe_m"], s["expo"], flag)
        s["sel_risk_seviyesi"] = classify_score(s["sel_risk_skoru"])
        if (i + 1) % 100 == 0:
            print(f"      {i+1:,}/{len(structures):,} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    dem_ds.close()
    sl_ds.close()

    # ilçe ataması
    print("[5/7] İlçe ataması...", flush=True)
    import geopandas as gpd
    ilce = gpd.read_file(ILCE).to_crs(CRS)
    pts = [Point(s["x"], s["y"]) for s in structures]
    gdf = gpd.GeoDataFrame({"i": range(len(pts))}, geometry=pts, crs=CRS)
    j = gpd.sjoin(gdf, ilce[["ilce", "geometry"]], how="left",
                  predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    ilceler = dict(zip(j["i"], j["ilce"]))
    for i, s in enumerate(structures):
        s["ilce"] = ilceler.get(i) or ""
    print(f"      -> {sum(1 for s in structures if s['ilce']):,} yapı ilçeye atandı",
          flush=True)

    # ------------------------------------------------------------------ #
    #  şehir geneli: alçak / düz yol kesimleri
    # ------------------------------------------------------------------ #
    print("[6/7] Şehir geneli düşük kotlu yol taraması...", flush=True)
    ways = load_jsonl(ROADS)
    coords, way_idx = [], []
    for wi, w in enumerate(ways):
        hw = w.get("highway") or ""
        if hw not in ROAD_SCAN_HW:
            continue
        if w.get("bridge") or w.get("tunnel"):
            continue
        cs = w.get("coords") or []
        if len(cs) < 2:
            continue
        coords.extend(cs)
        way_idx.extend([wi] * len(cs))
    road_xy = xy_of(coords) if coords else np.zeros((0, 2))
    print(f"      -> {len(road_xy):,} yol noktası", flush=True)
    rz, reg, rtpi, rstd = sample_rasters(road_xy, tpi_radii=(500, 1500))
    way_arr = np.asarray(way_idx)

    # Düz, alçak ve drenaj hattına yakın yol noktaları:
    #   - eğim <= %4, TPI500 0.5-18 m (aşırı kanyon değil)
    #   - yerel yükseklik standart sapması <= 14 m (dağ vadisini eler)
    cand = (np.isfinite(rz) & np.isfinite(rstd[500]) &
            (reg <= 4.0) &
            (rtpi[500] >= 0.5) & (rtpi[500] <= 18.0) &
            (rstd[500] <= 14.0))
    ci = np.where(cand)[0]
    print(f"      -> aday: {len(ci):,}", flush=True)

    # 120 m ızgarada tekilleştir; her hücrenin en düşük kotlu noktası
    cell = {}
    for i in ci:
        key = (int(road_xy[i, 0] // 120), int(road_xy[i, 1] // 120))
        cur = cell.get(key)
        if cur is None or rz[i] < rz[cur]:
            cell[key] = int(i)
    reps = list(cell.values())
    # yol noktası yoğunluğu: kentsel alan proxy'si (500 m yarıçap)
    from scipy.spatial import cKDTree
    road_tree = cKDTree(road_xy)
    dens_arr = road_tree.query_ball_point(road_xy[reps], r=500,
                                          return_length=True)
    dens = {i: int(d) for i, d in zip(reps, dens_arr)}
    # düz + çukur + düşük zemin + kentsel yoğunluk önceliği
    reps.sort(key=lambda i: -(min(float(rtpi[500][i]), 10.0) * 2.0
                              - float(rstd[500][i]) * 0.8
                              + min(dens[i] / 100.0, 8.0)))
    # 600 m aralıkla seyrelt (aynı dere koridorunda yığılmayı önler)
    chosen, pts_sel = [], []
    for i in reps:
        p = (road_xy[i, 0], road_xy[i, 1])
        if pts_sel:
            d = np.hypot(np.array(pts_sel)[:, 0] - p[0],
                         np.array(pts_sel)[:, 1] - p[1]).min()
            if d < 600:
                continue
        chosen.append(int(i))
        pts_sel.append(p)
        if len(chosen) >= 400:
            break
    reps = chosen
    print(f"      -> 120 m ızgarada {len(cell):,} tekil nokta, "
          f"hidroloji için {len(reps):,} nokta seçildi", flush=True)

    dem_ds = rasterio.open(DEM)
    sl_ds = rasterio.open(SLOPE)
    hotspots = []
    for k, i in enumerate(reps):
        x, y = float(road_xy[i, 0]), float(road_xy[i, 1])
        r0, r1, c0, c1 = window_around(dem_ds, x, y, 1500)
        dem = dem_ds.read(1, window=((r0, r1), (c0, c1))).astype("float32")
        dem[dem == dem_ds.nodata] = np.nan
        eg = sl_ds.read(1, window=((r0, r1), (c0, c1))).astype("float32") / 10.0
        T = dem_ds.transform
        outc = int(round((x - T.c) / T.a)) - c0
        outr = int(round((T.f - y) / abs(T.e))) - r0
        outc = min(max(outc, 0), dem.shape[1] - 1)
        outr = min(max(outr, 0), dem.shape[0] - 1)
        hm = hydrology(dem, eg, outr, outc) if dem.size else None
        if not hm:
            continue
        wi = int(way_arr[i])
        w = ways[wi]
        hw = w.get("highway") or ""
        d, wt, wn = water_distance(Point(x, y), tree, wlines, wtypes, wnames)
        score = road_hotspot_score(hm["cukur_m"], hm["relief_m"],
                                   hm["havza_m"], hm["akim_ha"],
                                   hm["yamac_pct"], d, hw, dens[i])
        lon, lat = tr_inv.transform(x, y)
        hotspots.append({
            "nokta_id": f"SN{k+1:04d}",
            "tur": "Yol Kesimi",
            "ad": w.get("name") or "",
            "yol_sinifi": hw,
            "ilce": "",
            "x": round(x, 2), "y": round(y, 2),
            "lon": round(lon, 6), "lat": round(lat, 6),
            "kot_m": hm["kot_m"],
            "cukur_m": hm["cukur_m"],
            "havza_m": hm["havza_m"],
            "relief_m": hm["relief_m"],
            "akim_ha": hm["akim_ha"],
            "yamac_pct": hm["yamac_pct"],
            "su_mesafe_m": d,
            "su_tipi": wt,
            "su_adi": wn,
            "kentsel_mi": bool(dens[i] >= 200),
            "yogunluk_500m": dens[i],
            "sel_risk_skoru": score,
            "sel_risk_seviyesi": classify_score(score),
            "osm_id": w.get("osm_id"),
        })
        if (k + 1) % 100 == 0:
            print(f"      {k+1:,}/{len(reps):,} ({time.time()-t0:.0f}s)",
                  flush=True)
    dem_ds.close()
    sl_ds.close()

    if hotspots:
        pts = [Point(h["x"], h["y"]) for h in hotspots]
        gdf = gpd.GeoDataFrame({"i": range(len(pts))}, geometry=pts, crs=CRS)
        j = gpd.sjoin(gdf, ilce[["ilce", "geometry"]], how="left",
                      predicate="within")
        j = j[~j.index.duplicated(keep="first")]
        ilc = dict(zip(j["i"], j["ilce"]))
        for i, h in enumerate(hotspots):
            h["ilce"] = ilc.get(i) or ""

    # ------------------------------------------------------------------ #
    #  çıktılar
    # ------------------------------------------------------------------ #
    print("[7/7] Çıktılar yazılıyor...", flush=True)
    structures.sort(key=lambda s: -s["sel_risk_skoru"])
    for i, s in enumerate(structures):
        s["oncelik"] = i + 1

    json_recs = []
    for s in structures:
        r = {k: v for k, v in s.items() if not k.startswith("_")}
        json_recs.append(r)
    with open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for r in json_recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def up_row(s):
        et = s.get("etiketler") or {}
        return {
            "yapi_id": s["yapi_id"],
            "gecit_tipi": s["gecit_tipi"],
            "ad": s["ad"],
            "yol_sinifi": s["yol_sinifi"],
            "ilce": s["ilce"],
            "durum": s["durum"],
            "uzunluk_m": s["uzunluk_m"],
            "kot_min_m": s["kot_min_m"],
            "kot_max_m": s["kot_max_m"],
            "cukur_derinligi_m": s["cukur_m"],
            "havza_derinligi_m": s["havza_m"],
            "akim_birikim_ha": s["akim_ha"],
            "memba_egimi_yuzde": s["yamac_pct"],
            "dere_mesafe_m": s["su_mesafe_m"],
            "dere_tipi": s["su_tipi"],
            "dere_adi": s["su_adi"],
            "aydinlatma": s["lit"],
            "maxheight": et.get("maxheight", ""),
            "sel_risk_skoru": s["sel_risk_skoru"],
            "sel_risk_seviyesi": s["sel_risk_seviyesi"],
            "oncelik": s["oncelik"],
            "x": s["x"], "y": s["y"], "lon": s["lon"], "lat": s["lat"],
            "osm_idler": ";".join(str(v) for v in s["osm_ids"]),
        }

    df_up = pd.DataFrame([up_row(s) for s in structures])
    df_up.to_csv(OUT_UP_CSV, index=False, encoding="utf-8-sig")

    sel_rows = [up_row(s) for s in structures
                if s["sel_risk_seviyesi"] in ("Çok Yüksek", "Yüksek", "Orta")]
    for h in hotspots:
        sel_rows.append({
            "yapi_id": h["nokta_id"], "gecit_tipi": h["tur"], "ad": h["ad"],
            "yol_sinifi": h["yol_sinifi"], "ilce": h["ilce"],
            "durum": "Mevcut", "uzunluk_m": np.nan,
            "kot_min_m": h["kot_m"], "kot_max_m": np.nan,
            "cukur_derinligi_m": h["cukur_m"],
            "havza_derinligi_m": h["havza_m"],
            "yerel_rolyef_m": h.get("relief_m"),
            "kentsel_mi": h.get("kentsel_mi"),
            "yogunluk_500m": h.get("yogunluk_500m"),
            "akim_birikim_ha": h["akim_ha"],
            "memba_egimi_yuzde": h["yamac_pct"],
            "dere_mesafe_m": h["su_mesafe_m"], "dere_tipi": h["su_tipi"],
            "dere_adi": h["su_adi"], "aydinlatma": "", "maxheight": "",
            "sel_risk_skoru": h["sel_risk_skoru"],
            "sel_risk_seviyesi": h["sel_risk_seviyesi"],
            "oncelik": np.nan, "x": h["x"], "y": h["y"],
            "lon": h["lon"], "lat": h["lat"], "osm_idler": str(h["osm_id"]),
        })
    df_sel = pd.DataFrame(sel_rows)
    if len(df_sel):
        df_sel = df_sel.sort_values("sel_risk_skoru", ascending=False)
    df_sel.to_csv(OUT_SEL_CSV, index=False, encoding="utf-8-sig")

    # ilçe özeti
    df_ilce = pd.DataFrame(structures)
    ozet = df_ilce.groupby("ilce").agg(
        alt_gecit_sayisi=("yapi_id", "count"),
        cok_yuksek=("sel_risk_seviyesi", lambda s: (s == "Çok Yüksek").sum()),
        yuksek=("sel_risk_seviyesi", lambda s: (s == "Yüksek").sum()),
        orta=("sel_risk_seviyesi", lambda s: (s == "Orta").sum()),
        ortalama_risk=("sel_risk_skoru", "mean"),
        maksimum_risk=("sel_risk_skoru", "max"),
        ortalama_cukur_m=("cukur_m", "mean"),
        ortalama_akim_ha=("akim_ha", "mean"),
    ).reset_index().sort_values("maksimum_risk", ascending=False)
    ozet["ortalama_risk"] = ozet["ortalama_risk"].round(1)
    ozet["ortalama_cukur_m"] = ozet["ortalama_cukur_m"].round(2)
    ozet["ortalama_akim_ha"] = ozet["ortalama_akim_ha"].round(1)
    ozet.to_csv(OUT_ILCE_CSV, index=False, encoding="utf-8-sig")

    summary = {
        "tarih": time.strftime("%Y-%m-%d"),
        "alt_gecit_yapisi": len(structures),
        "alt_gecit_way": int(sum(s["n_way"] for s in structures)),
        "yaya_alt_gecidi": int(sum(1 for s in structures
                                  if s["gecit_tipi"] == "Yaya Alt Geçidi")),
        "arac_alt_gecidi": int(sum(1 for s in structures
                                  if s["gecit_tipi"] == "Araç Alt Geçidi")),
        "arac_tuneli": int(sum(1 for s in structures
                               if s["gecit_tipi"] == "Araç Tüneli")),
        "yapi_gecisi": int(sum(1 for s in structures
                               if s["gecit_tipi"] == "Yapı Geçişi")),
        "cok_yuksek": int(sum(1 for s in structures
                              if s["sel_risk_seviyesi"] == "Çok Yüksek")),
        "yuksek": int(sum(1 for s in structures
                          if s["sel_risk_seviyesi"] == "Yüksek")),
        "orta": int(sum(1 for s in structures
                        if s["sel_risk_seviyesi"] == "Orta")),
        "yol_sel_noktasi": len(hotspots),
        "yol_sel_yuksek": int(sum(1 for h in hotspots
                                  if h["sel_risk_skoru"] >= 55)),
        "yol_sel_kentsel": int(sum(1 for h in hotspots if h["kentsel_mi"])),
        "ortalama_risk": round(float(np.mean([s["sel_risk_skoru"]
                                              for s in structures])), 1),
        "en_yuksek_risk": max(s["sel_risk_skoru"] for s in structures),
        "su_yolu_sayisi": len(wlines),
        "ilce_sayisi": int(df_ilce["ilce"].replace("", np.nan).nunique()),
    }
    with open(OUT_SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    print("\n=============== ALT GEÇİT / SEL RİSK ÖZETİ ===============")
    print(f"Alt geçit yapısı        : {len(structures):,}")
    print(f"  Yaya                  : {summary['yaya_alt_gecidi']:,}")
    print(f"  Araç alt geçidi       : {summary['arac_alt_gecidi']:,}")
    print(f"  Araç tüneli           : {summary['arac_tuneli']:,}")
    print(f"Sel riski Çok Yüksek    : {summary['cok_yuksek']:,}")
    print(f"Sel riski Yüksek        : {summary['yuksek']:,}")
    print(f"Sel riskli yol noktası  : {len(hotspots):,}")
    print(f"Süre                    : {time.time()-t0:.0f} sn")
    for p in (OUT_JSONL, OUT_UP_CSV, OUT_SEL_CSV, OUT_ILCE_CSV, OUT_SUMMARY):
        print(f"-> {p}")


if __name__ == "__main__":
    main()
