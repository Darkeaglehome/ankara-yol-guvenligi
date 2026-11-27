# -*- coding: utf-8 -*-
"""
report_ankara.py
Ankara OSM yol guvenligi analiz ciktilarindan:
  * 6 adet yuksek cozunurluklu grafik (rapor_gorselleri/)
  * Cok sayfali Excel calisma kitabi
  * Folium interaktif kara nokta haritasi
  * Markdown analiz raporu
uretir.
"""
import json
import os
import time

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
IMG_DIR = os.path.join(BASE, "rapor_gorselleri")
os.makedirs(IMG_DIR, exist_ok=True)

CSV_ALL = os.path.join(BASE, "Ankara_OSM_Tum_Kusurlar.csv")
CSV_BS = os.path.join(BASE, "Ankara_OSM_Kara_Noktalar_Oncelikli.csv")
CSV_ILCE = os.path.join(BASE, "Ankara_OSM_Ilce_Ozeti.csv")
ROADS = os.path.join(BASE, "osm_roads_ankara.jsonl")
ILCE = os.path.join(ROOT, "ankara_ilce_sinirlari.geojson")

OUT_XLSX = os.path.join(BASE, "Ankara_OSM_Yol_Guvenligi_Raporu.xlsx")
OUT_HTML = os.path.join(BASE, "Ankara_OSM_Kara_Noktalar_Harita.html")
OUT_MD = os.path.join(BASE, "Ankara_OSM_Yol_Guvenligi_Raporu.md")

KIND_LABELS = {
    "KURP": "Keskin Viraj (R ≤ 75 m)",
    "GENISLIK": "Dar Kesit / Şişe Boynu (W ≤ 5.5 m)",
    "KAVSAK_ACISI": "Dar Açıllı Kör Kavşak (θ ≤ 45°)",
    "CIKMAZ_SOKAK": "Ana Yola Çıkmaz Sokak",
    "DONUS_CEBI": "Dönüş Cebi Manevra Kısıtı",
    "EGIM": "Dik Boyuna Eğim (g ≥ %8)",
}
LEVEL_ORDER = ["Kritik Kara Nokta", "Yüksek Risk", "Orta Risk", "Düşük Risk"]
LEVEL_COLORS = {"Kritik Kara Nokta": "#c0392b", "Yüksek Risk": "#e67e22",
                "Orta Risk": "#f1c40f", "Düşük Risk": "#27ae60"}

sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams["axes.edgecolor"] = "#CCCCCC"
plt.rcParams["axes.linewidth"] = 0.8


def network_stats():
    """OSM yol agi ozeti — yalnizca Ankara il siniri icindeki yollar (sadece OSM)."""
    import geopandas as gpd
    from shapely.geometry import LineString

    ilce = gpd.read_file(ILCE)
    geoms, meta = [], []
    with open(ROADS, encoding="utf-8") as fh:
        for line in fh:
            w = json.loads(line)
            cs = w["coords"]
            if len(cs) < 2:
                continue
            geoms.append(LineString(cs))
            meta.append((w.get("highway") or "?", w.get("maxspeed")))
    gdf = gpd.GeoDataFrame(meta, columns=["highway", "maxspeed"],
                           geometry=geoms, crs="EPSG:4326")
    # Ankara disindaki (bbox genisligindeki) yollari ele
    hit = gpd.sjoin(gdf, ilce[["geometry"]], how="inner", predicate="intersects")
    hit = hit[~hit.index.duplicated(keep="first")]
    hit = hit.to_crs("EPSG:32636")
    hit["uzunluk_m"] = hit.length
    n_ms = int(hit["maxspeed"].notna().sum())
    return hit[["highway", "uzunluk_m", "maxspeed"]], n_ms, len(hit)


def generate_charts(df, df_ilce, df_net, n_ms, n_ways):
    print("1. Grafikler...", flush=True)

    # 1) kusur turu donut
    fig, ax = plt.subplots(figsize=(9, 6), dpi=300)
    counts = df["kind"].value_counts()
    labels = [KIND_LABELS.get(k, k) for k in counts.index]
    colors = ["#c0392b", "#e67e22", "#2980b9", "#8e44ad", "#16a085",
              "#2c3e50"]
    wedges, _, autotexts = ax.pie(
        counts.values, labels=labels, autopct="%1.1f%%", pctdistance=0.78,
        colors=colors[:len(counts)], startangle=140,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2))
    for t in autotexts:
        t.set_color("white")
        t.set_fontsize(9)
        t.set_fontweight("bold")
    ax.set_title("Ankara OSM Kusur Türlerine Göre Dağılım", fontsize=13,
                 fontweight="bold", pad=14)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "01_kusur_turleri_dagilimi.png"))
    plt.close(fig)

    # 2) en riskli 15 ilce
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=300)
    top = df_ilce.head(15).sort_values("kritik_kara_nokta")
    ax.barh(top["ilce"], top["kritik_kara_nokta"], color="#c0392b",
            label="Kritik Kara Nokta")
    ax.barh(top["ilce"], top["yuksek_risk"], left=top["kritik_kara_nokta"],
            color="#e67e22", label="Yüksek Risk")
    ax.set_xlabel("Nokta sayısı")
    ax.set_title("Ankara'da En Riskli 15 İlçe (Kritik + Yüksek Risk)",
                 fontsize=13, fontweight="bold")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "02_en_riskli_15_ilce.png"))
    plt.close(fig)

    # 3) risk skoru histogram + seviye
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=300)
    axes[0].hist(df["risk_skoru"], bins=40, color="#2980b9",
                 edgecolor="white")
    axes[0].axvline(75, color="#c0392b", ls="--", lw=1.5,
                    label="Kritik eşiği (75)")
    axes[0].axvline(55, color="#e67e22", ls="--", lw=1.5,
                    label="Yüksek eşiği (55)")
    axes[0].set_title("Risk Skoru Dağılımı (YGE 0-100)")
    axes[0].set_xlabel("Risk skoru")
    axes[0].legend()
    lvl = df["risk_seviyesi"].value_counts().reindex(LEVEL_ORDER).fillna(0)
    axes[1].bar(lvl.index, lvl.values,
                color=[LEVEL_COLORS[k] for k in lvl.index])
    for i, v in enumerate(lvl.values):
        axes[1].text(i, v + max(lvl.values) * 0.01, f"{int(v):,}",
                     ha="center", fontsize=9, fontweight="bold")
    axes[1].set_title("Risk Seviyeleri")
    axes[1].tick_params(axis="x", rotation=15)
    fig.suptitle("Ankara OSM Yol Güvenliği Risk Skorları", fontsize=14,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "03_risk_skoru_ve_seviyeleri.png"))
    plt.close(fig)

    # 4) hiz vs geometri matrisi
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8), dpi=300)
    kp = df[df["kind"] == "KURP"]
    hm = {"Ana Arter": "#c0392b", "Toplayıcı Cadde": "#e67e22",
          "Ara Sokak": "#2980b9", "Kritik Dar Boğaz / Çıkmaz": "#8e44ad"}
    for h, c in hm.items():
        s = kp[kp["yol_hiyerarsisi"] == h]
        if len(s):
            axes[0].scatter(s["val"], s["yol_hizi_kmh"], s=14, alpha=0.55,
                            color=c, label=h, edgecolors="none")
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Kurp yarıçapı R (m) — log")
    axes[0].set_ylabel("Kanuni hız (km/s, yol sınıfı)")
    axes[0].set_title("Viraj Yarıçapı vs Yol Hızı")
    axes[0].legend(fontsize=8)

    kv = df[df["kind"] == "KAVSAK_ACISI"]
    for h, c in hm.items():
        s = kv[kv["yol_hiyerarsisi"] == h]
        if len(s):
            axes[1].scatter(s["val"], s["yol_hizi_kmh"], s=14, alpha=0.55,
                            color=c, label=h, edgecolors="none")
    axes[1].set_xlabel("Kavşak min. açısı (derece)")
    axes[1].set_ylabel("Yol hızı (km/s)")
    axes[1].set_title("Kavşak Açısı vs Yol Hızı")
    axes[1].legend(fontsize=8)
    fig.suptitle("Hız – Geometri Risk Saçılımı (OSM)", fontsize=14,
                 fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "04_hiz_vs_geometri_matrisi.png"))
    plt.close(fig)

    # 5) ilce kusur kompozisyonu
    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=300)
    top = df_ilce.head(15)
    piv = (df[df["ilce"].isin(top["ilce"])]
           .pivot_table(index="ilce", columns="kind", values="val",
                        aggfunc="count").fillna(0))
    piv = piv.reindex(top["ilce"])
    piv.plot(kind="bar", stacked=True, ax=ax,
             color=["#c0392b", "#27ae60", "#2980b9", "#8e44ad", "#16a085",
                    "#2c3e50"])
    ax.set_ylabel("Kusur noktası sayısı")
    ax.set_title("İlçe Bazlı Kusur Kompozisyonu (İlk 15)",
                 fontsize=13, fontweight="bold")
    ax.legend([KIND_LABELS.get(c, c) for c in piv.columns], fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "05_ilce_kusur_kompozisyonu.png"))
    plt.close(fig)

    # 6) ana arter hiz riski
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
    art = df[df["yol_hiyerarsisi"] == "Ana Arter"].copy()
    if len(art):
        art["hiz_bandi"] = pd.cut(art["yol_hizi_kmh"],
                                  bins=[0, 50, 70, 90, 200],
                                  labels=["≤50", "51-70", "71-90", ">90"])
        piv = (art.pivot_table(index="hiz_bandi", columns="risk_seviyesi",
                               values="val", aggfunc="count")
               .fillna(0).reindex(columns=LEVEL_ORDER))
        piv.plot(kind="bar", stacked=True, ax=ax,
                 color=[LEVEL_COLORS[c] for c in piv.columns])
        ax.set_xlabel("Ana arter hız bandı (km/s)")
        ax.set_ylabel("Kusur noktası")
        ax.set_title("Ana Arterlerde Hız Bandına Göre Kusur Riski",
                     fontsize=13, fontweight="bold")
        ax.legend(title="Risk seviyesi", fontsize=8)
        plt.setp(ax.get_xticklabels(), rotation=0)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "06_ana_arter_hiz_dagilimi.png"))
    plt.close(fig)

    # 7) egim analizi
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.8), dpi=300)
    if "egim_yuzde" in df.columns:
        sub = df[df["egim_yuzde"].notna()]
        for h, c in hm.items():
            s = sub[sub["yol_hiyerarsisi"] == h]
            if len(s):
                axes[0].scatter(s["egim_yuzde"], s["risk_skoru"], s=11,
                                alpha=0.45, color=c, label=h, edgecolors="none")
        axes[0].set_xlabel("Eğim (%) — DEM'den")
        axes[0].set_ylabel("Risk skoru (YGE 0-100)")
        axes[0].set_title("Eğim – Risk İlişkisi")
        axes[0].legend(fontsize=8)

        eg = sub[sub["kind"] == "EGIM"]
        if len(eg):
            bant = pd.cut(eg["val"], bins=[8, 10, 12, 15, 100],
                          labels=["%8-10", "%10-12", "%12-15", ">%15"])
            vc = bant.value_counts().reindex(["%8-10", "%10-12", "%12-15",
                                              ">%15"]).fillna(0)
            axes[1].bar(vc.index, vc.values, color="#2c3e50")
            for i, v in enumerate(vc.values):
                axes[1].text(i, v + max(vc.values) * 0.01, f"{int(v):,}",
                             ha="center", fontsize=9, fontweight="bold")
            axes[1].set_title("Dik Boyuna Eğim Kesimleri (g ≥ %8)")
            axes[1].set_xlabel("Boyuna eğim bandı")
            axes[1].set_ylabel("Kesim sayısı")
    fig.suptitle("Ankara OSM — Boyuna Eğim (Copernicus DEM GLO-30) Analizi",
                 fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "07_egim_analizi.png"))
    plt.close(fig)
    print("   -> 7 grafik yazildi", flush=True)


def add_lonlat(df):
    """UTM 36N (x, y) -> WGS84 (lon, lat) koordinatlari ekler."""
    import pyproj
    tr = pyproj.Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(df["x"].values, df["y"].values)
    out = df.copy()
    out["lon"] = np.round(lon, 6)
    out["lat"] = np.round(lat, 6)
    return out


def generate_excel(df, df_ilce, net_summary):
    print("2. Excel...", flush=True)
    df = add_lonlat(df)
    df_bs = df[df["risk_seviyesi"].isin(["Kritik Kara Nokta", "Yüksek Risk"])]

    ozet = [
        ("Analiz kapsami", "Ankara il sinirlari (sadece OpenStreetMap)"),
        ("Veri kaynagi", "Geofabrik/OSM Turkey PBF + OSM etiketleri"),
        ("Yol sayisi (way)", f"{net_summary['n_way']:,}"),
        ("Yol agi uzunlugu", f"{net_summary['km']:,.0f} km"),
        ("Hiz modeli", "Yol sinifina gore kanuni hiz (motorway 120 -> residential 50)"),
        ("OSM maxspeed etiketli yol (bilgi)", f"{net_summary['n_ms']:,} "
         f"({net_summary['ms_pct']:.1f}%)"),
        ("Tekil tehlike noktasi", f"{len(df):,}"),
        ("Kritik Kara Nokta", f"{int((df.risk_seviyesi=='Kritik Kara Nokta').sum()):,}"),
        ("Yüksek Risk", f"{int((df.risk_seviyesi=='Yüksek Risk').sum()):,}"),
        ("Orta Risk", f"{int((df.risk_seviyesi=='Orta Risk').sum()):,}"),
        ("Düşük Risk", f"{int((df.risk_seviyesi=='Düşük Risk').sum()):,}"),
        ("Keskin viraj (R≤75m)", f"{int((df.kind=='KURP').sum()):,}"),
        ("Dar kesit (W≤5.5m)", f"{int((df.kind=='GENISLIK').sum()):,}"),
        ("Dar açılı kavşak (θ≤45°)", f"{int((df.kind=='KAVSAK_ACISI').sum()):,}"),
        ("Çıkmaz sokak", f"{int((df.kind=='CIKMAZ_SOKAK').sum()):,}"),
        ("Dönüş cebi", f"{int((df.kind=='DONUS_CEBI').sum()):,}"),
        ("Dik boyuna eğim kesimi (g ≥ %8)",
         f"{int((df.kind=='EGIM').sum()):,}"),
        ("Kot aralığı (Copernicus DEM)",
         f"{df.kot_m.min():.0f} - {df.kot_m.max():.0f} m"),
        ("Ortalama arazi eğimi", f"%{df.arazi_egimi_yuzde.mean():.1f}"),
        ("En dik boyuna eğim", f"%{df.boyuna_egim_yuzde.max():.1f}"),
        ("Ortalama risk skoru", f"{df.risk_skoru.mean():.1f}"),
        ("En yüksek risk skoru", f"{df.risk_skoru.max():.1f}"),
        ("Ana arter kusuru", f"{int((df.yol_hiyerarsisi=='Ana Arter').sum()):,}"),
        ("Kanuni hiz (sinif) kaynakli kusur",
         f"{int(df.hiz_kaynak.astype(str).str.startswith('kanuni').sum()):,}"),
    ]
    df_ozet = pd.DataFrame(ozet, columns=["Gösterge", "Değer"])

    art = df[df["yol_hiyerarsisi"] == "Ana Arter"].sort_values(
        "risk_skoru", ascending=False)

    cols_all = ["kind", "risk_skoru", "risk_seviyesi", "val", "yol_hiyerarsisi",
                "yol_hizi_kmh", "hiz_kaynak", "kurp_guvenli_hiz_kmh",
                "hiz_kurp_fark_kmh", "ilce", "name", "highway", "maxspeed",
                "ref", "x", "y", "lon", "lat", "sample_count",
                "kot_m", "arazi_egimi_yuzde", "boyuna_egim_yuzde",
                "egim_yuzde", "egim_sinifi", "yon", "uzunluk_m",
                "egim_kirilma"]
    cols_all = [c for c in cols_all if c in df.columns]

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as w:
        df_ozet.to_excel(w, sheet_name="Yonetici_Ozeti", index=False)
        df_ilce.to_excel(w, sheet_name="Ilce_Dagilimi", index=False)
        art.head(1000)[cols_all].to_excel(w, sheet_name="Ana_Arter_Hiz_Riski",
                                          index=False)
        df_bs.head(1000)[cols_all].to_excel(
            w, sheet_name="Top1000_Kritik_Kara_Nokta", index=False)
        df[df.kind == "KURP"].sort_values("val")[cols_all].to_excel(
            w, sheet_name="Keskin_Virajlar", index=False)
        df[df.kind == "GENISLIK"].sort_values("val")[cols_all].to_excel(
            w, sheet_name="Dar_Kesitler_Sise_Boynu", index=False)
        df[df.kind == "KAVSAK_ACISI"].sort_values("val")[cols_all].to_excel(
            w, sheet_name="Dar_Acili_Kavsaklar", index=False)
        df[df.kind == "CIKMAZ_SOKAK"][cols_all].to_excel(
            w, sheet_name="Cikmaz_Sokaklar", index=False)
        df[df.kind == "EGIM"].sort_values("val", ascending=False)[cols_all].to_excel(
            w, sheet_name="Dik_Egim_Kesimleri", index=False)
    print(f"   -> {OUT_XLSX}", flush=True)


def generate_map(df):
    print("3. Folium harita...", flush=True)
    import folium
    import pyproj
    tr_inv = pyproj.Transformer.from_crs("EPSG:32636", "EPSG:4326",
                                         always_xy=True)
    lons, lats = tr_inv.transform(df["x"].values, df["y"].values)
    df = df.copy()
    df["lon"] = lons
    df["lat"] = lats
    center = [39.9334, 32.8597]
    m = folium.Map(location=center, zoom_start=10, tiles="cartodbpositron")
    for lvl, color in LEVEL_COLORS.items():
        sub = df[df["risk_seviyesi"] == lvl].head(250)
        grp = folium.FeatureGroup(name=f"{lvl} ({len(sub)})")
        for _, r in sub.iterrows():
            popup = (f"<b>{KIND_LABELS.get(r['kind'], r['kind'])}</b><br>"
                     f"Risk: {r['risk_skoru']}<br>"
                     f"İlçe: {r['ilce']}<br>"
                     f"Sokak: {r.get('name') or '-'}<br>"
                     f"Hız: {r['yol_hizi_kmh']} km/s<br>"
                     f"Kot: {float(r.get('kot_m', 'nan')):.0f} m · "
                     f"Eğim: %{float(r.get('egim_yuzde', 'nan')):.1f}")
            folium.CircleMarker(
                location=[r["lat"], r["lon"]], radius=max(3, r["risk_skoru"] / 15),
                color=color, fill=True, fill_opacity=0.6, weight=1,
                popup=popup).add_to(grp)
        grp.add_to(m)
    folium.LayerControl().add_to(m)
    m.save(OUT_HTML)
    print(f"   -> {OUT_HTML}", flush=True)


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def generate_report(df, df_ilce, net, n_ms, n_ways):
    print("4. Markdown rapor...", flush=True)
    n_kritik = int((df.risk_seviyesi == "Kritik Kara Nokta").sum())
    n_yuksek = int((df.risk_seviyesi == "Yüksek Risk").sum())
    n_orta = int((df.risk_seviyesi == "Orta Risk").sum())
    n_dusuk = int((df.risk_seviyesi == "Düşük Risk").sum())
    km = net["km"]

    rows_ilce = df_ilce.head(12)[["ilce", "toplam_kusur", "kritik_kara_nokta",
                                  "yuksek_risk", "ana_arter_kusur",
                                  "ortalama_hiz", "ortalama_risk"]].values.tolist()
    rows_ilce = [[r[0], f"{int(r[1]):,}", int(r[2]), int(r[3]), int(r[4]),
                  f"{r[5]:.1f}", f"{r[6]:.1f}"] for r in rows_ilce]

    top = df.head(15)
    rows_top = [[i + 1, KIND_LABELS.get(r["kind"], r["kind"]), r["risk_skoru"],
                 f"{r['val']:.1f}", r["yol_hiyerarsisi"], r["yol_hizi_kmh"],
                 r["ilce"], (str(r["name"]) if pd.notna(r["name"]) else "-")[:34]]
                for i, (_, r) in enumerate(top.iterrows())]

    kind_rows = []
    for k, sub in df.groupby("kind"):
        kind_rows.append([KIND_LABELS.get(k, k), f"{len(sub):,}",
                          f"{sub['val'].median():.1f}",
                          f"{sub['risk_skoru'].mean():.1f}",
                          int((sub.risk_seviyesi == "Kritik Kara Nokta").sum())])
    kind_rows.sort(key=lambda r: -int(r[1].replace(",", "")))

    # egim istatistikleri
    n_egim = int((df.kind == "EGIM").sum())
    eg = df[df.kind == "EGIM"]
    eg_rows = []
    for lab, lo, hi in [("%8-10", 8, 10), ("%10-12", 10, 12),
                        ("%12-15", 12, 15), (">%15", 15, 999)]:
        s = eg[(eg.val >= lo) & (eg.val < hi)]
        eg_rows.append([lab, f"{len(s):,}",
                        int((s.risk_seviyesi == "Kritik Kara Nokta").sum()),
                        f"{s.risk_skoru.mean():.1f}" if len(s) else "-",
                        f"{s.uzunluk_m.sum()/1000:,.1f}" if len(s) else "-"])
    eg_h = eg.groupby("yol_hiyerarsisi").agg(
        n=("val", "count"), ort_egim=("val", "mean")).round(1) \
        if len(eg) else pd.DataFrame()
    eg_h_rows = [[i, f"{int(r['n']):,}", f"%{r['ort_egim']:.1f}"]
                 for i, r in eg_h.iterrows()]

    art = df[df.yol_hiyerarsisi == "Ana Arter"]
    art_rows = []
    for band, lab in [((0, 51), "≤50 km/s"), ((51, 71), "51-70 km/s"),
                      ((71, 91), "71-90 km/s"), ((91, 999), ">90 km/s")]:
        s = art[(art.yol_hizi_kmh > band[0]) & (art.yol_hizi_kmh <= band[1])]
        art_rows.append([lab, f"{len(s):,}",
                         int((s.risk_seviyesi == "Kritik Kara Nokta").sum()),
                         int((s.risk_seviyesi == "Yüksek Risk").sum()),
                         f"{s.risk_skoru.mean():.1f}" if len(s) else "-"])

    md = f"""# Ankara İli Yol Güvenliği ve Geometrik Kusur Analizi
## (Sadece OpenStreetMap Verisiyle Kara Nokta Modeli)

**Tarih:** {time.strftime('%d.%m.%Y')}
**Kapsam:** Ankara il sınırları (25 ilçe)
**Veri kaynağı:** OpenStreetMap (Geofabrik `turkey-latest.osm.pbf` + OSM etiketleri)
**Referans metodoloji:** `METODOLOJI_YOL_GUVENLIGI.md` (İstanbul/DGN modeli) → OSM verisine uyarlanmış hali

---

## 1. Yönetici Özeti

| Gösterge | Değer |
| --- | --- |
| Yol ağı (way) | {n_ways:,} parça |
| Toplam yol uzunluğu | {km:,.0f} km |
| Hız modeli | Yol sınıfına göre **kanuni hız** (motorway 120 · trunk 90 · primary/secondary 70 · tertiary 60 · residential 50 · service 40) |
| Tekil tehlike noktası | {len(df):,} |
| **Kritik Kara Nokta (≥75)** | **{n_kritik:,}** |
| Yüksek Risk (55-74) | {n_yuksek:,} |
| Orta Risk (35-54) | {n_orta:,} |
| Düşük Risk (<35) | {n_dusuk:,} |
| Ana arter kusuru | {len(art):,} |
| Dik boyuna eğim kesimi (g ≥ %8) | {n_egim:,} |
| Kot aralığı (Copernicus DEM) | {df.kot_m.min():.0f} – {df.kot_m.max():.0f} m |
| En riskli ilçe | {df_ilce.iloc[0]['ilce']} ({int(df_ilce.iloc[0]['kritik_kara_nokta'])} kritik nokta) |

---

## 2. Metodoloji (OSM Uyarlaması)

Referans model İstanbul için 1/1000 DGN + trafik sensörü + durak verisiyle kurulmuştu.
Bu analiz **yalnızca OSM** üzerinden aynı risk mantığını yeniden kurar:

| Kusur | İstanbul Modeli (DGN) | Ankara OSM Uyarlaması |
| --- | --- | --- |
| Keskin viraj (R) | 3B yol kenarı çizgisinden `R = ds/dθ` | OSM yol ekseni vertekslerinden `R = ds/dθ`; kavşak köşeleri (≥30°) viraj sayılmaz, kavşak açısı modülüne devredilir |
| Dar kesit (W) | Bordür/KD-Tree ile ölçüm | OSM `width` etiketi → `lanes × 3.25 m` → sınıf varsayımı (sırayla) |
| Kavşak açısı (θ) | Düğüm kol vektörleri | OSM paylaşımlı düğümlerde kol vektörleri (uç + ara düğüm) |
| Çıkmaz sokak | OSM topolojisi | Aynısı: tek uçlu, paylaşılmayan düğüm |
| Boyuna eğim (g) | DGN kotları | **Copernicus DEM GLO-30 (30 m)** üzerinden `g = Δz/Δs` (90 m pencere, %8 eşik); eğim kırılması Δ ayrıca hesaplanır |
| Hız çarpanı | İBB sensör medyan hızı | **Yol sınıfına göre kanuni hız sınırı** (motorway 120 … residential 50 km/s) |
| Trafik hacmi çarpanı | Geohash sensör hacmi | **YOK** (sınırlama) |

**Hız modeli (yol sınıfına göre kanuni hızlar):**
- Hız, OSM `maxspeed` etiketinden değil **yol sınıfından** alınır: `motorway` 120 · `trunk` 90 · `primary` 70 · `secondary` 70 · `tertiary` 60 · `residential` 50 · `service` 40 · `living_street` 30 · `unclassified` 40 · `track` 30 · `pedestrian` 10 km/s (`*_link` sınıfları ana sınıfla aynıdır).
- Bu değerler Karayolları Trafik Kanunu'ndaki yerleşim yeri içi/dışı ve otoyol sınırlarına karşılık gelir; etiket boşluğu veya hatalı `maxspeed` değeri analizi etkilemez.
- Virajda **denge hızı** `V = √(127·f·R)`, f = 0.28 (AASHTO) hesaplanır; kanuni hız ile denge hızı arasındaki fark (hız-kurp uyumsuzluğu) risk skoruna eklenir.
- Risk skorunda hız çarpanı hiyerarşiye göre güçlendirilir: Ana arterde >90 km/s → +30, 71-90 → +25, 51-70 → +18 puan.

**Risk seviyeleri:** ≥75 Kritik Kara Nokta · 55-74 Yüksek Risk · 35-54 Orta Risk · <35 Düşük Risk.

---

## 3. Kusur Türü Bazlı Sonuçlar

{md_table(["Kusur türü", "Adet", "Medyan değer", "Ort. risk", "Kritik"],
           kind_rows)}

---

## 4. Ana Arter Hız-Risk Matrisi

{md_table(["Hız bandı", "Kusur sayısı", "Kritik", "Yüksek", "Ort. risk"], art_rows)}

> Ana arterlerde yüksek hız + keskin viraj/dar açılı kavşak birleşimi en yüksek
> risk skorlarını üretir: yüksek hızda savrulma, devrilme ve görüş mesafesi kaybı.

---

## 5. İlçe Dağılımı (İlk 12)

{md_table(["İlçe", "Toplam", "Kritik", "Yüksek", "Ana arter", "Ort. hız", "Ort. risk"],
           rows_ilce)}

---

## 6. En Kritik 15 Kara Nokta

{md_table(["#", "Kusur", "Risk", "Değer", "Hiyerarşi", "Hız", "İlçe", "Yol"],
           rows_top)}

---

## 7. Boyuna Eğim (Rampa) Analizi

OSM'de kot bulunmadığı için önceki sürümde hesaplanamayan boyuna eğim modülü,
**Copernicus DEM GLO-30 (30 m)** yükseklik mozaiği indirilerek devreye alındı.
Her OSM yol ekseni boyunca 30 m aralıklarla kot örneklenmiş, 90 m'lik pencerede
`g = Δz / Δs` boyuna eğimi hesaplanmış ve **|g| ≥ %8** olan, en az 90 m süren
kesimler `EGIM` kusuru olarak modele eklenmiştir. Eğim, aynı zamanda tüm
diğer kusurların risk skoruna zemin tutunma kaybı çarpanı olarak yansıtılır.

**Kot / eğim kapsamı:** {df.kot_m.min():.0f}–{df.kot_m.max():.0f} m kot aralığı ·
ortalama arazi eğimi %{df.arazi_egimi_yuzde.mean():.1f} · en dik boyuna eğim
%{df.boyuna_egim_yuzde.max():.1f} · {n_egim:,} dik eğim kesimi.

{md_table(["Boyuna eğim bandı", "Kesim", "Kritik", "Ort. risk", "Toplam uzunluk (km)"],
           eg_rows)}

{md_table(["Yol hiyerarşisi", "Dik eğim kesimi", "Ort. eğim"], eg_h_rows)}

> Dik eğimli iniş kesimlerinde fren kaybı, ıslak/karlı zeminde tutunma kaybı ve
> viraj içinde savrulma riski artar; bu kesimlerde hız yönetimi, tırmandırıcı
> kaplama, drenaj ve tuzlama/kumlama planlaması önceliklidir.

---

## 8. Grafikler

| Grafik | Dosya |
| --- | --- |
| Kusur türü dağılımı | `rapor_gorselleri/01_kusur_turleri_dagilimi.png` |
| En riskli 15 ilçe | `rapor_gorselleri/02_en_riskli_15_ilce.png` |
| Risk skoru ve seviyeleri | `rapor_gorselleri/03_risk_skoru_ve_seviyeleri.png` |
| Hız–geometri saçılımı | `rapor_gorselleri/04_hiz_vs_geometri_matrisi.png` |
| İlçe kusur kompozisyonu | `rapor_gorselleri/05_ilce_kusur_kompozisyonu.png` |
| Ana arter hız riski | `rapor_gorselleri/06_ana_arter_hiz_dagilimi.png` |
| Eğim–risk ilişkisi ve dik eğim kesimleri | `rapor_gorselleri/07_egim_analizi.png` |

**İnteraktif harita:** `Ankara_OSM_Kara_Noktalar_Harita.html`
**Excel:** `Ankara_OSM_Yol_Guvenligi_Raporu.xlsx` (9 sayfa)
**Ham veri:** `Ankara_OSM_Tum_Kusurlar.csv`, `Ankara_OSM_Kara_Noktalar_Oncelikli.csv`, `Ankara_OSM_Ilce_Ozeti.csv`

---

## 9. Sınırlamalar

1. **Boyuna eğim Copernicus DEM GLO-30'dan türetilir** — 30 m DSM (yüzey modeli)
   kullanıldığı için köprü/alt geçit, tünel ve bina gölgeli kesimlerde yerel
   sapmalar olabilir; eğim 90 m pencerede hesaplanarak gürültü azaltılmıştır.
   Hassas proje (1/1000) için DGN kotları ile doğrulama önerilir.
2. **Gerçek trafik hacmi yok** — sensör verisi olmadığından hacim çarpanı (S_hacim)
   kullanılmamıştır; yoğunluk yerine yol sınıfı hiyerarşisi dolaylı gösterge olarak kullanılır.
3. **Genişlik etiketleri kısmi** — OSM'de `width`/`lanes` etiketi olmayan yollarda sınıf
   varsayımı kullanılır (`hiz_kaynak`/`kaynak` sütunlarından izlenebilir).
4. **Hızlar yol sınıfına göre kanuni sınırlardır** — OSM `maxspeed` etiketi yerine sınıf
   tabanlı yasal hız kullanılmıştır; ölçüm hızı değil, tasarım/güvenlik analizi için üst
   sınır kabul edilmiştir.
5. Kavşak açıları OSM topolojisine dayanır; çift yol/ayrı carrefour geometrisi
   kavşakları ayrı düğümler olarak modellenebilir.

---

## 10. Sonuç ve Öneriler

- **Öncelik 1:** {df_ilce.iloc[0]['ilce']} ve {df_ilce.iloc[1]['ilce']} ilçelerinde
  kritik noktaların yoğunlaşması, bu ilçelerde hızlı arter + keskin viraj/dar açılı
  kavşak bileşiminin çok olduğunu gösterir.
- **Öncelik 2:** Ana arterlerde `hiz_kurp_fark_kmh > 40` olan noktalar (Excel:
  `Ana_Arter_Hiz_Riski`) hız düşürme, kenar şeridi, uyarı tabelası ve aydınlatma ile
  önceliklendirilmelidir.
- **Öncelik 3:** Dar açılı (≤35°) kavşaklarda görüş üçgeni temizliği, ayna ve
  yavaşlatma elemanları uygulanmalıdır.
- **Öncelik 4:** Dik boyuna eğimli (%8 ve üzeri) **{n_egim:,}** kesimde ıslak/karlı
  zemin tutunma kaybı, inişlerde fren kaybı ve viraj içi savrulma riski artar;
  bu kesimlerde hız yönetimi, yüksek tutunmalı (tırmandırıcı) kaplama, drenaj ve
  kış bakım (tuzlama) planı önceliklendirilmelidir. Kot verisi artık
  Copernicus DEM GLO-30'dan üretilmekte olup 1/1000 DGN ile doğrulanabilir.
"""
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(md)
    print(f"   -> {OUT_MD}", flush=True)


def main():
    t0 = time.time()
    df = pd.read_csv(CSV_ALL)
    df_ilce = pd.read_csv(CSV_ILCE)
    df_net, n_ms, n_ways = network_stats()
    km = df_net["uzunluk_m"].sum() / 1000.0
    net = {"km": km, "n_way": n_ways, "n_ms": n_ms,
           "ms_pct": 100.0 * n_ms / max(n_ways, 1)}
    print(f"sebeke: {n_ways:,} way, {km:,.0f} km, kanuni hiz modeli",
          flush=True)
    generate_charts(df, df_ilce, df_net, n_ms, n_ways)
    generate_excel(df, df_ilce, net)
    generate_map(df)
    generate_report(df, df_ilce, net, n_ms, n_ways)
    print(f"toplam sure: {time.time()-t0:.1f} sn")


if __name__ == "__main__":
    main()
