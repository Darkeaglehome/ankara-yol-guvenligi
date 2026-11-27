# -*- coding: utf-8 -*-
"""Ankara icin sayisal yukseklik modeli (DEM) indirme ve egim rasteri uretimi.

Kaynak : Copernicus DEM GLO-30 (30 m) - AWS Open Data
         https://copernicus-dem-30m.s3.amazonaws.com
Yontem : Ankara il sinirini kapsayan 1x1 derecelik COG dosyalarindan yalnizca
         gerekli pencere /vsicurl ile okunur, tek mozaikte birlestirilir;
         UTM 36N (30 m) izgara ya yeniden projekte edilir ve Horn (1981)
         3x3 egim operatoru ile egim (%) hesaplanir.

Cikti :
  dem_ankara.tif          EPSG:4326 1 arcsec  yukseklik (m, float32)
  dem_ankara_utm.tif      EPSG:32636 30 m      yukseklik (m, float32)
  egim_ankara_utm.tif     EPSG:32636 30 m      egim (%, uint16 x10)
  dem_manifest.json       kaynak / kapsam / istatistik
"""
import json
import math
import os
import time

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject
from rasterio.windows import from_bounds

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_LL = os.path.join(BASE, "dem_ankara.tif")
OUT_UTM = os.path.join(BASE, "dem_ankara_utm.tif")
OUT_SLOPE = os.path.join(BASE, "egim_ankara_utm.tif")
OUT_MANIFEST = os.path.join(BASE, "dem_manifest.json")

# Ankara il siniri + 5 km emniyet payi
LON_MIN, LON_MAX = 30.75, 34.00
LAT_MIN, LAT_MAX = 38.60, 40.80
RES = 1.0 / 3600.0                    # 1 arcsec ~ 30 m
S3 = "https://copernicus-dem-30m.s3.amazonaws.com"
NODATA = -9999.0


def tile_url(lat_i, lon_i):
    ns = "N" if lat_i >= 0 else "S"
    ew = "E" if lon_i >= 0 else "W"
    name = (f"Copernicus_DSM_COG_10_{ns}{abs(lat_i):02d}_00_"
            f"{ew}{abs(lon_i):03d}_00_DEM")
    return f"/vsicurl/{S3}/{name}/{name}.tif"


def download_mosaic():
    rows = int(round((LAT_MAX - LAT_MIN) / RES))
    cols = int(round((LON_MAX - LON_MIN) / RES))
    print(f"mozaik: {rows:,} x {cols:,} px  ({rows*cols/1e6:.1f} Mpx)", flush=True)
    mosaic = np.full((rows, cols), np.nan, dtype=np.float32)

    tiles = []
    for lat_i in range(int(math.floor(LAT_MIN)), int(math.floor(LAT_MAX)) + 1):
        for lon_i in range(int(math.floor(LON_MIN)), int(math.floor(LON_MAX)) + 1):
            tiles.append((lat_i, lon_i))

    for n, (lat_i, lon_i) in enumerate(tiles, 1):
        t0 = time.time()
        url = tile_url(lat_i, lon_i)
        try:
            with rasterio.open(url) as ds:
                b_lon0 = max(LON_MIN, lon_i)
                b_lon1 = min(LON_MAX, lon_i + 1)
                b_lat0 = max(LAT_MIN, lat_i)
                b_lat1 = min(LAT_MAX, lat_i + 1)
                if b_lon1 <= b_lon0 or b_lat1 <= b_lat0:
                    continue
                win = from_bounds(b_lon0, b_lat0, b_lon1, b_lat1, ds.transform)
                arr = ds.read(1, window=win, out_dtype="float32")
                # pencereyi tam hucreye hizala
                c0 = int(round((b_lon0 - LON_MIN) / RES))
                c1 = c0 + arr.shape[1]
                r0 = int(round((LAT_MAX - b_lat1) / RES))
                r1 = r0 + arr.shape[0]
                mosaic[r0:r1, c0:c1] = arr
            print(f"  [{n}/{len(tiles)}] {lat_i},{lon_i} -> {arr.shape} "
                  f"({time.time()-t0:.1f}s)", flush=True)
        except Exception as exc:                      # noqa: BLE001
            print(f"  [{n}/{len(tiles)}] HATA {lat_i},{lon_i}: {exc}", flush=True)

    mosaic[np.isnan(mosaic)] = NODATA
    transform = from_origin(LON_MIN, LAT_MAX, RES, RES)
    prof = dict(driver="GTiff", height=rows, width=cols, count=1,
                dtype="float32", crs="EPSG:4326", transform=transform,
                nodata=NODATA, tiled=True, blockxsize=512, blockysize=512,
                compress="deflate", predictor=3, BIGTIFF="IF_SAFER")
    with rasterio.open(OUT_LL, "w", **prof) as dst:
        dst.write(mosaic, 1)
        dst.update_tags(source="Copernicus DEM GLO-30", area="Ankara")
    print(f"-> {OUT_LL} ({os.path.getsize(OUT_LL)/1e6:.0f} MB)", flush=True)
    return OUT_LL


def reproject_utm():
    with rasterio.open(OUT_LL) as src:
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:32636", src.width, src.height, *src.bounds,
            resolution=30.0)
        prof = src.profile.copy()
        prof.update(crs="EPSG:32636", transform=transform,
                    width=width, height=height, dtype="float32",
                    nodata=NODATA, compress="deflate", predictor=3,
                    BIGTIFF="IF_SAFER")
        print(f"UTM izgara: {width:,} x {height:,}", flush=True)
        with rasterio.open(OUT_UTM, "w", **prof) as dst:
            reproject(source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=dst.crs,
                      resampling=Resampling.bilinear,
                      src_nodata=NODATA, dst_nodata=NODATA)
    print(f"-> {OUT_UTM} ({os.path.getsize(OUT_UTM)/1e6:.0f} MB)", flush=True)
    return OUT_UTM


def horn_slope():
    """Horn (1981) 3x3 pencere ile egim yuzdesi (UTM, 30 m)."""
    with rasterio.open(OUT_UTM) as src:
        z = src.read(1).astype("float64")
        transform = src.transform
        prof = src.profile.copy()
    z[z == NODATA] = np.nan
    res = abs(transform.a)
    # kenarlari tekrarla
    zp = np.pad(z, 1, mode="edge")
    a, b, c = zp[0:-2, 0:-2], zp[0:-2, 1:-1], zp[0:-2, 2:]
    d, f = zp[1:-1, 0:-2], zp[1:-1, 2:]
    g, h, i = zp[2:, 0:-2], zp[2:, 1:-1], zp[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8.0 * res)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8.0 * res)
    slope_pct = np.hypot(dzdx, dzdy) * 100.0
    slope_pct = np.clip(slope_pct, 0, 300)
    out = np.where(np.isnan(slope_pct), 0, np.round(slope_pct * 10)).astype("uint16")
    prof.update(dtype="uint16", nodata=0, compress="deflate",
                predictor=2, BIGTIFF="IF_SAFER")
    with rasterio.open(OUT_SLOPE, "w", **prof) as dst:
        dst.write(out, 1)
        dst.update_tags(unit="egim yuzde x10", method="Horn 1981",
                        source="Copernicus DEM GLO-30")
    print(f"-> {OUT_SLOPE} ({os.path.getsize(OUT_SLOPE)/1e6:.0f} MB)", flush=True)
    valid = zp[1:-1, 1:-1][~np.isnan(zp[1:-1, 1:-1])]
    return {
        "egim_yuzde_medyan": round(float(np.median(slope_pct[np.isfinite(slope_pct)])), 2),
        "egim_yuzde_p95": round(float(np.percentile(slope_pct[np.isfinite(slope_pct)], 95)), 2),
        "egim_yuzde_max": round(float(np.nanmax(slope_pct)), 2),
        "kot_min_m": round(float(np.nanmin(valid)), 1) if valid.size else None,
        "kot_max_m": round(float(np.nanmax(valid)), 1) if valid.size else None,
    }


def main():
    t0 = time.time()
    if not os.path.exists(OUT_LL):
        download_mosaic()
    else:
        print(f"mevcut mozaik kullaniliyor: {OUT_LL}", flush=True)
    reproject_utm()
    stats = horn_slope()
    man = {
        "kaynak": "Copernicus DEM GLO-30 (AWS Open Data, copernicus-dem-30m)",
        "lisans": "Copernicus DEM - ESA, serbest kullanim (atıf ile)",
        "kapsam": {"lon": [LON_MIN, LON_MAX], "lat": [LAT_MIN, LAT_MAX]},
        "cozunurluk_m": 30,
        "egim_yontemi": "Horn (1981) 3x3, UTM 36N",
        "uretim_tarihi": time.strftime("%Y-%m-%d"),
        "dosyalar": [os.path.basename(OUT_LL), os.path.basename(OUT_UTM),
                     os.path.basename(OUT_SLOPE)],
        "istatistik": stats,
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"tamam ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
