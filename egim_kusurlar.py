# -*- coding: utf-8 -*-
"""DEM'den yol boyuna egim (boyuna profil) kusurlarini cikarir (Ankara).

Yontem
------
* dem_ankara_utm.tif (Copernicus GLO-30, 30 m) her OSM way verteksinde
  bilineer orneklenir.
* Way boyunca 30 m araliklarla yukseklik yeniden orneklenir; 90 m'lik
  pencerede boyuna egim  g = dz / ds  (%) hesaplanir (DEM gurultusunu
  bastirmak icin).
* |g| >= %8 olan ve en az 120 m suren ardil kesimler tek bir EGIM kaydi
  olarak yazilir; kayit degeri en dik egim yuzdesidir. Egim kirilma
  (Δ) degeri, kesim basi/sonu egim farki olarak kayda eklenir.

Cikti : egim_kusurlar.jsonl   (kind=EGIM)
"""
import json
import math
import os
import time

import numpy as np
import pyproj
import rasterio

BASE = os.path.dirname(os.path.abspath(__file__))
ROADS = os.path.join(BASE, "osm_roads_ankara.jsonl")
DEM = os.path.join(BASE, "dem_ankara_utm.tif")
OUT = os.path.join(BASE, "egim_kusurlar.jsonl")

EGIM_ESIK = 8.0        # % - dik egim esigi (KGM: %6-8 kritik rampa)
MIN_UZUNLUK = 120.0    # m - en kisa dik egim kesimi
STATION = 30.0         # m - ornekleme araligi
PENCERE = 150.0        # m - egim hesap penceresi (DSM gurultusunu bastirir)
YOL_SUZGEC = {"motorway", "motorway_link", "trunk", "trunk_link", "primary",
              "primary_link", "secondary", "secondary_link", "tertiary",
              "tertiary_link", "residential", "unclassified", "living_street",
              "service"}

tr = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)


class DemSampler:
    """UTM DEM uzerinde vektorize bilineer ornekleme."""

    def __init__(self, path=DEM):
        with rasterio.open(path) as ds:
            self.z = ds.read(1).astype("float32")
            self.t = ds.transform
            self.nodata = ds.nodata
        self.x0, self.y0 = self.t.c, self.t.f
        self.res = abs(self.t.a)
        self.h, self.w = self.z.shape
        self.z[self.z == self.nodata] = np.nan

    def sample(self, x, y):
        x = np.asarray(x, dtype="float64")
        y = np.asarray(y, dtype="float64")
        fc = (x - self.x0) / self.res - 0.5
        fr = (self.y0 - y) / self.res - 0.5
        c0 = np.floor(fc).astype("int64")
        r0 = np.floor(fr).astype("int64")
        c0 = np.clip(c0, 0, self.w - 2)
        r0 = np.clip(r0, 0, self.h - 2)
        dc = np.clip(fc - c0, 0, 1)
        dr = np.clip(fr - r0, 0, 1)
        z00 = self.z[r0, c0]
        z01 = self.z[r0, c0 + 1]
        z10 = self.z[r0 + 1, c0]
        z11 = self.z[r0 + 1, c0 + 1]
        return ((z00 * (1 - dc) + z01 * dc) * (1 - dr) +
                (z10 * (1 - dc) + z11 * dc) * dr)


def load_ways():
    ways = []
    with open(ROADS, encoding="utf-8") as fh:
        for line in fh:
            w = json.loads(line)
            if (w.get("highway") or "") not in YOL_SUZGEC:
                continue
            cs = w.get("coords") or []
            if len(cs) < 3:
                continue
            ways.append(w)
    return ways


def main():
    t0 = time.time()
    print("1. Yollar ve DEM yukleniyor...", flush=True)
    ways = load_ways()
    print(f"   -> {len(ways):,} way (surucu sinifi)", flush=True)
    sampler = DemSampler()
    print(f"   -> DEM {sampler.w}x{sampler.h} @ {sampler.res:.0f} m "
          f"({time.time()-t0:.1f}s)", flush=True)

    # tum koordinatlari tek seferde projekte et
    lens = [len(w["coords"]) for w in ways]
    flat = np.array([c for w in ways for c in w["coords"]], dtype="float64")
    print(f"   -> {len(flat):,} verteks ({time.time()-t0:.1f}s)", flush=True)
    xy = np.column_stack(tr.transform(flat[:, 0], flat[:, 1]))
    z_all = sampler.sample(xy[:, 0], xy[:, 1])
    print(f"   -> kot ornekleme tamam ({time.time()-t0:.1f}s)", flush=True)

    recs = []
    n_way_egim = 0
    cursor = 0
    grade_hist = {"8-10": 0, "10-12": 0, "12-15": 0, ">15": 0}

    for wi, w in enumerate(ways):
        n = lens[wi]
        P = xy[cursor:cursor + n]
        Z = z_all[cursor:cursor + n]
        cursor += n
        if not np.all(np.isfinite(Z)):
            continue
        seg = np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))
        if seg.sum() < MIN_UZUNLUK:
            continue
        s = np.r_[0.0, np.cumsum(seg)]
        # 30 m istasyonlar
        st = np.arange(0.0, s[-1] + 1e-6, STATION)
        if len(st) < 5:
            continue
        zs = np.interp(st, s, Z)
        px = np.interp(st, s, P[:, 0])
        py = np.interp(st, s, P[:, 1])
        step = int(round(PENCERE / STATION))
        if len(zs) <= step:
            continue
        g = (zs[step:] - zs[:-step]) / (step * STATION) * 100.0
        absg = np.abs(g)
        flag = absg >= EGIM_ESIK
        if not flag.any():
            continue
        # ardil dik kesimleri grupla (istasyon indeksi uzerinden)
        i = 0
        groups = []
        while i < len(flag):
            if not flag[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(flag) and flag[j + 1]:
                j += 1
            groups.append((i, j))
            i = j + 1
        for (a, b) in groups:
            length = (b - a + step) * STATION
            if length < MIN_UZUNLUK:
                continue
            rel = a + int(np.argmax(absg[a:b + 1]))
            gmax = float(g[rel])
            mid = min(len(st) - 1, rel + step // 2)
            # egim kirilma: kesim oncesi/sonrasi egim farki
            before = float(g[a - 1]) if a > 0 else 0.0
            after = float(g[b + 1]) if b + 1 < len(g) else 0.0
            kirilma = round(max(abs(float(g[a]) - before),
                                abs(float(g[b]) - after)), 1)
            recs.append({
                "kind": "EGIM", "x": round(float(px[mid]), 2),
                "y": round(float(py[mid]), 2), "val": round(abs(gmax), 1),
                "yon": "yokuş" if gmax > 0 else "iniş",
                "uzunluk_m": round(length, 0),
                "egim_kirilma": kirilma,
                "z_bas": round(float(zs[a]), 1),
                "z_son": round(float(zs[min(b + step, len(zs) - 1)]), 1),
                "name": w.get("name"), "highway": w.get("highway"),
                "ref": w.get("ref"), "maxspeed": w.get("maxspeed"),
                "osm_id": w.get("osm_id"),
            })
            n_way_egim += 1
            v = abs(gmax)
            k = ("8-10" if v < 10 else "10-12" if v < 12 else
                 "12-15" if v < 15 else ">15")
            grade_hist[k] += 1

    with open(OUT, "w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    vals = np.array([r["val"] for r in recs])
    print(f"\nEGIM kaydi: {len(recs):,} kesim ({n_way_egim:,} way)")
    if len(vals):
        print(f"egim medyan: {np.median(vals):.1f}%  maks: {vals.max():.1f}%")
        print(f"sinif dagilimi: {grade_hist}")
        print(f"yokus/iniş: {sum(1 for r in recs if r['yon']=='yokuş'):,} / "
              f"{sum(1 for r in recs if r['yon']=='iniş'):,}")
    print(f"-> {OUT}")
    print(f"sure: {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
