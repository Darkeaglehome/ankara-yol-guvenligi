# -*- coding: utf-8 -*-
"""
aggregate_ankara.py
Ankara OSM yol agindan cikan kusurlari (kurp, dar kesit, dar acili kavsak,
cikmaz sokak, donus cebi) konsolide eder; yol hiyerarsisi, OSM hiz modeli ve
Yol Guvenligi Risk Skorunu (YGE 0-100) uygular.

YOL HIYERARSISI VE HIZ MODELI (KANUNI HIZ - yol sinifina gore):
- Ana Arter / Otoyol : motorway 120, trunk 90, primary 70 km/s
- Toplayici Cadde    : secondary 70, tertiary 60 km/s
- Ara Sokak          : residential 50 (yerlesim yeri ici kanuni sinir)
- Servis / Tarla     : service 40, track 30 km/s
- Dar Bogaz/Cikmaz   : manevra hizi (kanuni sinif hizi korunur)
OSM maxspeed etiketi hiz modelinde KULLANILMAZ; hiz yalnizca yol sinifina
gore kanuni sinirdan alinir (Karayollari Trafik Kanunu).
"""
import json
import math
import os
import re
import time

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from scipy.spatial import cKDTree

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

GEOM = os.path.join(BASE, "ankara_geom_kusurlar.jsonl")
INTS = os.path.join(BASE, "osm_intersections.jsonl")
DEADS = os.path.join(BASE, "osm_deadends.jsonl")
EGIM = os.path.join(BASE, "egim_kusurlar.jsonl")
DEM = os.path.join(BASE, "dem_ankara_utm.tif")
ILCE = os.path.join(ROOT, "ankara_ilce_sinirlari.geojson")

CSV_ALL = os.path.join(BASE, "Ankara_OSM_Tum_Kusurlar.csv")
CSV_BS = os.path.join(BASE, "Ankara_OSM_Kara_Noktalar_Oncelikli.csv")
CSV_ILCE = os.path.join(BASE, "Ankara_OSM_Ilce_Ozeti.csv")

CRS_OUT = 32636  # WGS84 / UTM 36N

ARTEM_HW = {"motorway", "motorway_link", "trunk", "trunk_link",
            "primary", "primary_link"}
TOPLAYICI_HW = {"secondary", "secondary_link", "tertiary", "tertiary_link"}
DAR_HW = {"living_street", "service", "pedestrian", "track", "track_grade1",
          "track_grade2", "track_grade3", "track_grade4", "track_grade5"}

EGIM_ESIK = 8.0   # % - dik egim esigi (rapor/grafik icin)

ARTEM_KW = ["bulvar", "otoyol", "çevre yolu", "çevreyolu", "viyadük",
            "duble", "köprü", "baglantı yolu", "bağlantı yolu"]
CADDE_KW = ["caddesi", "cadde", "cad.", "cd."]

# Yol sinifina gore KANUNI hiz siniri (km/s)
DEF_SPEED = {
    "motorway": 120, "motorway_link": 120,
    "trunk": 90, "trunk_link": 90,
    "primary": 70, "primary_link": 70,
    "secondary": 70, "secondary_link": 70,
    "tertiary": 60, "tertiary_link": 60,
    "unclassified": 40, "residential": 50, "living_street": 30,
    "service": 40, "track": 30, "busway": 80, "pedestrian": 10,
    "turning_circle": 30, "mini_roundabout": 30, "?": 50,
}


def parse_maxspeed(v):
    """OSM maxspeed etiketini km/s tamsayiya cevirir."""
    if v in (None, ""):
        return None
    s = str(v).strip().lower()
    if s in ("walk", "none", "signals"):
        return 10 if s == "walk" else None
    s = s.split(";")[0].strip()
    try:
        if s.endswith("mph"):
            return int(round(float(s[:-3]) * 1.609))
        num = float(s.replace(",", "."))
        if 5 <= num <= 140:
            return int(round(num))
    except Exception:
        return None
    return None


def hierarchy(kind, val, hw, name, ref=None):
    hw = (hw or "?").lower()
    name = (name or "").lower()
    ref = (ref or "").upper()
    if re.match(r"^(D|K|M|O)-?\d", ref):
        return "Ana Arter"
    if hw in ARTEM_HW or any(k in name for k in ARTEM_KW):
        return "Ana Arter"
    if hw in TOPLAYICI_HW or any(k in name for k in CADDE_KW):
        return "Toplayıcı Cadde"
    # "Kritik Dar Boğaz / Çıkmaz" yalnizca gercek bogaz (W<=3.5) ve
    # cikmaz/donus cebi kayitlari icin ayrilir; track/service viraji
    # buraya girmez (Ara Sokak + asagidaki dusuk sinif carpani ile lenetilir)
    if kind in ("CIKMAZ_SOKAK", "DONUS_CEBI"):
        return "Kritik Dar Boğaz / Çıkmaz"
    if kind == "GENISLIK" and val <= 3.5:
        return "Kritik Dar Boğaz / Çıkmaz"
    return "Ara Sokak"


def class_speed(hw):
    return DEF_SPEED.get((hw or "?").lower(), 30)


# sinif bazli makul hiz tavanlari (OSM hatali/excessif etiket korumasi)
SPEED_CAP = {
    "motorway": 140, "motorway_link": 100,
    "trunk": 110, "trunk_link": 90,
    "primary": 100, "primary_link": 80,
    "secondary": 80, "secondary_link": 70,
    "tertiary": 70, "tertiary_link": 60,
    "unclassified": 70, "residential": 60, "living_street": 30,
    "service": 40, "track": 50, "busway": 60, "pedestrian": 15,
}


def speed_for_row(r):
    """Yol sinifina gore KANUNI hiz. OSM maxspeed etiketi kullanilmaz."""
    hw = (r.get("highway") or "?").lower()
    if r.get("kind") == "DONUS_CEBI":
        hw = "turning_circle"
    return class_speed(hw), "kanuni hiz (yol sinifi)"


def safe_curve_speed(R):
    """Kurp icin denge hizi: V = sqrt(127 * f * R), f = 0.28 (AASHTO)."""
    return round(math.sqrt(127.0 * 0.28 * max(float(R), 1.0)), 1)


def cluster_hazards(records, radius=30.0):
    if not records:
        return []
    by_kind = {}
    for r in records:
        by_kind.setdefault(r["kind"], []).append(r)

    clustered = []
    for k, pts in by_kind.items():
        if len(pts) == 1:
            p = pts[0]
            p["sample_count"] = 1
            clustered.append(p)
            continue
        coords = np.array([[p["x"], p["y"]] for p in pts])
        tree = cKDTree(coords)
        visited = set()
        for i in range(len(pts)):
            if i in visited:
                continue
            idxs = tree.query_ball_point(coords[i], radius)
            group = [pts[idx] for idx in idxs if idx not in visited]
            for idx in idxs:
                visited.add(idx)
            if not group:
                continue
            vals = [g["val"] for g in group]
            if k in ("KURP", "GENISLIK", "KAVSAK_ACISI"):
                rep_val = min(vals)
            elif k == "EGIM":
                rep_val = max(vals)
            else:
                rep_val = vals[0]
            names = [g["name"] for g in group if g.get("name")]
            hws = [g.get("highway") for g in group if g.get("highway")]
            mss = [g.get("maxspeed") for g in group if g.get("maxspeed")]
            clustered.append({
                "kind": k,
                "x": round(float(np.mean([g["x"] for g in group])), 2),
                "y": round(float(np.mean([g["y"] for g in group])), 2),
                "val": round(float(rep_val), 2),
                "min_val": round(float(min(vals)), 2),
                "max_val": round(float(max(vals)), 2),
                "sample_count": len(group),
                "name": names[0] if names else "",
                "highway": hws[0] if hws else "",
                "maxspeed": mss[0] if mss else None,
                "osm_id": group[0].get("osm_id"),
                "yay": group[0].get("yay"),
                "aci_derece": group[0].get("aci_derece"),
                "kaynak": group[0].get("kaynak"),
                "ref": group[0].get("ref"),
                "n_roads": group[0].get("n_roads"),
                "yon": group[0].get("yon"),
                "uzunluk_m": max([g.get("uzunluk_m") or 0 for g in group]),
                "egim_kirilma": max([g.get("egim_kirilma") or 0 for g in group]),
                "z_bas": group[0].get("z_bas"),
                "z_son": group[-1].get("z_son"),
            })
    return clustered


def _bilinear(arr, transform, nodata, x, y):
    """UTM izgarasinda vektorize bilineer ornekleme."""
    res = abs(transform.a)
    fc = (x - transform.c) / res - 0.5
    fr = (transform.f - y) / res - 0.5
    c0 = np.clip(np.floor(fc).astype("int64"), 0, arr.shape[1] - 2)
    r0 = np.clip(np.floor(fr).astype("int64"), 0, arr.shape[0] - 2)
    dc = np.clip(fc - c0, 0, 1)
    dr = np.clip(fr - r0, 0, 1)
    z00 = arr[r0, c0].astype("float64")
    z01 = arr[r0, c0 + 1].astype("float64")
    z10 = arr[r0 + 1, c0].astype("float64")
    z11 = arr[r0 + 1, c0 + 1].astype("float64")
    v = ((z00 * (1 - dc) + z01 * dc) * (1 - dr) +
         (z10 * (1 - dc) + z11 * dc) * dr)
    v[v == nodata] = np.nan
    return v


def egim_sinifi(p):
    if not np.isfinite(p):
        return "Bilinmiyor"
    if p < 2.0:
        return "Düz (<%2)"
    if p < 4.0:
        return "Hafif (%2-4)"
    if p < 7.0:
        return "Orta (%4-7)"
    if p < 10.0:
        return "Dik (%7-10)"
    return "Çok Dik (>%10)"


def attach_dem(df):
    """DEM'den kot ve egim degerlerini noktalara ekler."""
    import rasterio
    x = df["x"].values.astype("float64")
    y = df["y"].values.astype("float64")
    with rasterio.open(DEM) as ds:
        dem = ds.read(1)
        tr = ds.transform
        nd = ds.nodata
    with rasterio.open(DEM.replace("dem_ankara_utm.tif",
                                   "egim_ankara_utm.tif")) as ds:
        slope = ds.read(1).astype("float32") / 10.0
        nd2 = ds.nodata

    df["kot_m"] = np.round(_bilinear(dem, tr, nd, x, y), 1)
    arazi = _bilinear(slope, tr, 0.0, x, y)
    arazi[np.isnan(arazi) | (arazi == nd2)] = np.nan
    df["arazi_egimi_yuzde"] = np.round(arazi, 1)

    boyuna = np.full(len(df), np.nan)
    m = (df["kind"] == "EGIM").values
    if m.any():
        boyuna[m] = df.loc[m, "val"].astype(float).values
    df["boyuna_egim_yuzde"] = np.round(boyuna, 1)
    df["egim_yuzde"] = np.where(m, df["boyuna_egim_yuzde"],
                                df["arazi_egimi_yuzde"])
    df["egim_sinifi"] = df["egim_yuzde"].apply(egim_sinifi)
    for c in ("yon", "uzunluk_m", "egim_kirilma"):
        if c not in df.columns:
            df[c] = None
    return df


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main():
    t0 = time.time()
    print("1. OSM kusur kayitlari yukleniyor...", flush=True)
    recs = load_jsonl(GEOM)
    print(f"   -> geometrik kusur: {len(recs):,}")

    ints = [r for r in load_jsonl(INTS) if float(r.get("angle_deg", 90)) <= 45.0]
    print(f"   -> dar acili kavvak (<=45 derece): {len(ints):,}")
    # cluster_hazards 'val' bekler: kavsakta min kol acisi, cikmazda sabit 0
    for r in ints:
        r["val"] = round(float(r.get("angle_deg", 90)), 1)
        r.setdefault("aci_derece", r["val"])

    IMPORTANT_HW = {"motorway", "motorway_link", "trunk", "trunk_link",
                    "primary", "primary_link", "secondary", "secondary_link",
                    "tertiary", "tertiary_link", "residential", "living_street",
                    "unclassified"}
    dead = [r for r in load_jsonl(DEADS) if (r.get("highway") or "") in IMPORTANT_HW]
    print(f"   -> onemli cikmaz sokak: {len(dead):,}")
    for r in dead:
        r.setdefault("val", 0.0)

    # boyuna egim kusurlari (DEM / Copernicus GLO-30)
    egim = load_jsonl(EGIM)
    print(f"   -> dik egim kesimi (>=%8): {len(egim):,}")

    # maxspeed'i yol kayitlarindan kavsaklara da tasi (hiz modeli icin)
    for r in ints + dead:
        r.setdefault("maxspeed", None)

    all_recs = recs + ints + dead + egim

    print("2. Mekansal kumelenme (30 m)...", flush=True)
    cl = cluster_hazards(all_recs, radius=30.0)
    print(f"   -> tekil tehlike bolgesi: {len(cl):,}  ({time.time()-t0:.1f}s)")

    df = pd.DataFrame(cl)
    df["name"] = df["name"].fillna("")
    df["highway"] = df["highway"].fillna("?")

    print("3. DEM kot / egim ornekleme...", flush=True)
    df = attach_dem(df)
    print(f"   -> kot {df['kot_m'].min():.0f}-{df['kot_m'].max():.0f} m, "
          f"egim medyan %{df['egim_yuzde'].median():.1f}", flush=True)

    print("4. Yol hiyerarsisi + OSM hiz modeli...", flush=True)
    df["yol_hiyerarsisi"] = df.apply(
        lambda r: hierarchy(r["kind"], r["val"], r.get("highway"),
                            r.get("name"), r.get("ref")),
        axis=1)
    sp = df.apply(speed_for_row, axis=1)
    df["yol_hizi_kmh"] = [s[0] for s in sp]
    df["hiz_kaynak"] = [s[1] for s in sp]

    # kirp guvenli hizi (sadece KURP)
    df["kurp_guvenli_hiz_kmh"] = np.nan
    m = df["kind"] == "KURP"
    df.loc[m, "kurp_guvenli_hiz_kmh"] = df.loc[m, "val"].apply(safe_curve_speed)
    df["hiz_kurp_fark_kmh"] = (df["yol_hizi_kmh"] - df["kurp_guvenli_hiz_kmh"]).round(1)

    print("5. Risk skorlari (YGE 0-100)...", flush=True)
    df["risk_skoru"] = df.apply(compute_risk, axis=1).round(1)
    df["risk_seviyesi"] = df["risk_skoru"].apply(classify)

    print("6. Ilce mekansal atama...", flush=True)
    ilce = gpd.read_file(ILCE).to_crs(CRS_OUT)
    gdf = gpd.GeoDataFrame(df.copy(),
                           geometry=[Point(xy) for xy in zip(df.x, df.y)],
                           crs=CRS_OUT)
    j = gpd.sjoin(gdf, ilce[["ilce", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    # sinir hizasindaki noktalar (500 m'ye kadar) en yakin ilceye atanir
    miss = j["ilce"].isna()
    if miss.any():
        near = gpd.sjoin_nearest(gdf[miss], ilce[["ilce", "geometry"]],
                                 how="left", max_distance=500.0,
                                 distance_col="_dist")
        near = near[~near.index.duplicated(keep="first")]
        j.loc[near.index, "ilce"] = near["ilce"]
    n_out = int(j["ilce"].isna().sum())
    df = df.loc[j["ilce"].notna()].copy()
    df["ilce"] = j.loc[df.index, "ilce"]
    print(f"   -> Ankara il siniri disi cikarildi: {n_out:,}  "
          f"kalan: {len(df):,}", flush=True)

    # ---------------- kayitlar ----------------
    df.sort_values("risk_skoru", ascending=False, inplace=True)
    df.to_csv(CSV_ALL, index=False, encoding="utf-8-sig")

    bs = df[df["risk_seviyesi"].isin(["Kritik Kara Nokta", "Yüksek Risk"])].copy()
    bs.to_csv(CSV_BS, index=False, encoding="utf-8-sig")

    ilce_sum = df.groupby("ilce").agg(
        toplam_kusur=("kind", "count"),
        kritik_kara_nokta=("risk_seviyesi", lambda s: (s == "Kritik Kara Nokta").sum()),
        yuksek_risk=("risk_seviyesi", lambda s: (s == "Yüksek Risk").sum()),
        orta_risk=("risk_seviyesi", lambda s: (s == "Orta Risk").sum()),
        dusuk_risk=("risk_seviyesi", lambda s: (s == "Düşük Risk").sum()),
        ana_arter_kusur=("yol_hiyerarsisi", lambda s: (s == "Ana Arter").sum()),
        ana_arter_kritik=("yol_hiyerarsisi", lambda s: 0),
        cadde_kusur=("yol_hiyerarsisi", lambda s: (s == "Toplayıcı Cadde").sum()),
        dar_bogaz=("yol_hiyerarsisi", lambda s: (s == "Kritik Dar Boğaz / Çıkmaz").sum()),
        kurp_kusuru=("kind", lambda s: (s == "KURP").sum()),
        dar_kesit=("kind", lambda s: (s == "GENISLIK").sum()),
        dar_kavsak=("kind", lambda s: (s == "KAVSAK_ACISI").sum()),
        cikmaz_sokak=("kind", lambda s: (s == "CIKMAZ_SOKAK").sum()),
        egim_kusuru=("kind", lambda s: (s == "EGIM").sum()),
        ortalama_hiz=("yol_hizi_kmh", "mean"),
        ortalama_egim=("egim_yuzde", "mean"),
        maksimum_egim=("egim_yuzde", "max"),
        ortalama_risk=("risk_skoru", "mean"),
        maksimum_risk=("risk_skoru", "max"),
    ).reset_index()
    crit = df[(df["risk_seviyesi"] == "Kritik Kara Nokta") &
              (df["yol_hiyerarsisi"] == "Ana Arter")]
    if len(crit):
        cnt = crit.groupby("ilce").size()
        ilce_sum["ana_arter_kritik"] = ilce_sum["ilce"].map(cnt).fillna(0).astype(int)

    ilce_sum["ortalama_hiz"] = ilce_sum["ortalama_hiz"].round(1)
    ilce_sum["ortalama_risk"] = ilce_sum["ortalama_risk"].round(1)
    ilce_sum["ortalama_egim"] = ilce_sum["ortalama_egim"].round(1)
    ilce_sum["maksimum_egim"] = ilce_sum["maksimum_egim"].round(1)
    ilce_sum.sort_values("kritik_kara_nokta", ascending=False, inplace=True)
    ilce_sum.to_csv(CSV_ILCE, index=False, encoding="utf-8-sig")

    # ---------------- ozet ----------------
    print("\n================= ANKARA OSM YOL GUVENLIGI OZETI =================")
    print(df.groupby("kind").agg(n=("val", "count"), medyan_val=("val", "median"))
          .round(1).to_string())
    print("\nRisk seviyeleri:")
    print(df["risk_seviyesi"].value_counts().to_string())
    print("\nYol hiyerarsisi:")
    print(df["yol_hiyerarsisi"].value_counts().to_string())
    print("\nHiz kaynagi:")
    print(df["hiz_kaynak"].value_counts().to_string())
    print("\nEn riskli 10 ilce:")
    print(ilce_sum.head(10)[["ilce", "toplam_kusur", "kritik_kara_nokta",
                             "ortalama_risk"]].to_string(index=False))
    print(f"\nSure: {time.time()-t0:.1f} sn")
    print(f"-> {CSV_ALL}")
    print(f"-> {CSV_BS}")
    print(f"-> {CSV_ILCE}")


def classify(s):
    if s >= 75.0:
        return "Kritik Kara Nokta"
    if s >= 55.0:
        return "Yüksek Risk"
    if s >= 35.0:
        return "Orta Risk"
    return "Düşük Risk"


# tarla/servis yolu gibi dusuk sinifli yollar: viraj/kavsak riski dusuk
LOW_HW = {"track", "service", "pedestrian", "busway"}


def compute_risk(r):
    k = r["kind"]
    val = float(r["val"])
    h = r["yol_hiyerarsisi"]
    v = float(r["yol_hizi_kmh"])
    hw = (r.get("highway") or "?").lower()
    score = 0.0

    if k == "KURP":
        if val <= 15.0:
            score += 62
        elif val <= 30.0:
            score += 48
        elif val <= 50.0:
            score += 35
        else:
            score += 22
        # HIZ CARPANI (OSM maxspeed ana arter hizlari on planda)
        if h == "Ana Arter":
            if v > 90:
                score += 30
            elif v > 70:
                score += 25
            elif v > 50:
                score += 18
            else:
                score += 10
        elif h == "Toplayıcı Cadde":
            score += 22 if v > 50 else (15 if v > 40 else 8)
        elif h == "Ara Sokak":
            score += 15 if v >= 40 else (8 if v >= 30 else 0)
            if val <= 15.0:
                score += 10   # buyuk arac donemez
        else:  # Dar bogaz / cikmaz (tarla/yol servis yolu): viraj normali
            score = score * 0.7 + 5
        # hiz - kurp denge hizi uyumsuzlugu
        gap = v - safe_curve_speed(val)
        if gap >= 40:
            score += 12
        elif gap >= 25:
            score += 7

    elif k == "GENISLIK":
        if val <= 3.2:
            score += 65
        elif val <= 4.0:
            score += 48
        elif val <= 5.0:
            score += 32
        else:
            score += 20
        if h in ("Ana Arter", "Toplayıcı Cadde"):
            score += 20
            if v > 70:
                score += 8
        elif h == "Ara Sokak" and val <= 3.5:
            score += 18

    elif k == "KAVSAK_ACISI":
        if val <= 25.0:
            score += 56
        elif val <= 35.0:
            score += 42
        else:
            score += 28
        if h in ("Ana Arter", "Toplayıcı Cadde"):
            score += 20
            if v > 70:
                score += 8
        elif h == "Ara Sokak" and val <= 25.0:
            score += 12

    elif k == "CIKMAZ_SOKAK":
        score += 35
        if h in ("Ana Arter", "Toplayıcı Cadde"):
            score += 35
        else:
            score += 15
        if v > 70:
            score += 10

    elif k == "DONUS_CEBI":
        score += 25
        if h in ("Ana Arter", "Toplayıcı Cadde"):
            score += 20

    elif k == "EGIM":
        # boyuna egim (DEM'den, 90 m pencerede dz/ds)
        if val >= 12.0:
            score += 58
        elif val >= 9.0:
            score += 45
        elif val >= 7.0:
            score += 34
        else:
            score += 24
        if h == "Ana Arter":
            score += 26 if v > 90 else (22 if v > 70 else 16)
        elif h == "Toplayıcı Cadde":
            score += 18
        elif h == "Ara Sokak":
            score += 10
        if (r.get("yon") or "") == "iniş":
            score += 6          # inis egimi: fren kaybi / savrulma

    # arazi egimi carpani: egimli zeminde tutunma kaybi ve gorus mesafesi
    if k in ("KURP", "KAVSAK_ACISI", "GENISLIK"):
        e = r.get("egim_yuzde")
        try:
            e = float(e)
        except (TypeError, ValueError):
            e = float("nan")
        if math.isfinite(e):
            if e >= 10.0:
                score += 12
            elif e >= 7.0:
                score += 9
            elif e >= 4.0:
                score += 5
            elif e >= 2.0:
                score += 2

    # tarla/yol servisi gibi dusuk sinifli yollarda viraj, dar acili
    # kavsak ve rampa normal trafik kosulu sayilir -> riski orantili dusur
    if hw in LOW_HW and k in ("KURP", "KAVSAK_ACISI", "EGIM"):
        score = score * 0.55

    return min(100.0, score)


if __name__ == "__main__":
    main()
