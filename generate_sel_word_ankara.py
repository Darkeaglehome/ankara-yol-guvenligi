# -*- coding: utf-8 -*-
"""
generate_sel_word_ankara.py
Ankara alt gecit / tunel sel riski raporunu (.docx) olusturur.
Veri: OSM (tunnel + layer<0, waterway) + Copernicus DEM GLO-30.
Skorlama: altgecit_sel_ankara.py (Priority-Flood tabanli hidrolojik on degerlendirme).
"""
import os
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor

from generate_word_ankara import (
    COLOR_ACCENT, COLOR_MUTED, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT,
    add_body_p, add_callout, add_figure, add_heading_styled, build_table,
    set_cell_background, set_cell_margins,
)

BASE = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE, "rapor_gorselleri")
CSV_GECIT = os.path.join(BASE, "Ankara_OSM_Alt_Gecitler.csv")
CSV_NOKTA = os.path.join(BASE, "Ankara_OSM_Sel_Riskli_Noktalar.csv")
CSV_ILCE = os.path.join(BASE, "Ankara_OSM_Sel_Ilce_Ozeti.csv")
OUT_DOCX = os.path.join(BASE, "Ankara_Alt_Gecit_Sel_Risk_Raporu.docx")

LEVEL_ORDER = ["Çok Yüksek", "Yüksek", "Orta", "Düşük", "Çok Düşük"]
LEVEL_COLORS = {
    "Çok Yüksek": "#C0392B",
    "Yüksek": "#E67E22",
    "Orta": "#F1C40F",
    "Düşük": "#27AE60",
    "Çok Düşük": "#95A5A6",
}
GMAIL = "https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#BDC3C7",
    "axes.labelcolor": "#2C3E50",
    "text.color": "#2C3E50",
    "xtick.color": "#5D6D7E",
    "ytick.color": "#5D6D7E",
    "figure.dpi": 150,
})


# --------------------------------------------------------------------------
# Grafikler
# --------------------------------------------------------------------------
def make_charts(df, road, ilce):
    os.makedirs(IMG_DIR, exist_ok=True)

    # 1) Yapi tipi x risk seviyesi
    tip_order = df["gecit_tipi"].value_counts().index.tolist()
    pivot = (df.pivot_table(index="gecit_tipi", columns="sel_risk_seviyesi",
                            values="yapi_id", aggfunc="count")
               .reindex(tip_order).fillna(0))
    fig, ax = plt.subplots(figsize=(8.2, 3.9))
    left = np.zeros(len(pivot))
    for lvl in LEVEL_ORDER:
        if lvl not in pivot.columns:
            continue
        vals = pivot[lvl].values
        ax.barh(pivot.index, vals, left=left, color=LEVEL_COLORS[lvl],
                label=lvl, height=0.62, edgecolor="white", linewidth=0.8)
        for i, v in enumerate(vals):
            if v >= 3:
                ax.text(left[i] + v / 2, i, f"{int(v)}", ha="center", va="center",
                        fontsize=8, color="white", fontweight="bold")
        left += vals
    ax.invert_yaxis()
    ax.set_xlabel("Yapı sayısı")
    ax.set_title("Alt geçit / tünel yapılarının tip ve sel riski dağılımı",
                 fontsize=11, fontweight="bold", pad=10)
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="lower right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "sel_01_tip_risk.png"))
    plt.close(fig)

    # 2) Ilce ortalama risk
    d = ilce.sort_values("ortalama_risk", ascending=True)
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    colors = ["#C0392B" if v >= 45 else "#E67E22" if v >= 30 else "#2980B9"
              for v in d["ortalama_risk"]]
    bars = ax.barh(d["ilce"], d["ortalama_risk"], color=colors, height=0.62)
    for b, (_, r) in zip(bars, d.iterrows()):
        ax.text(b.get_width() + 0.8, b.get_y() + b.get_height() / 2,
                f"{r['ortalama_risk']:.1f}  (n={int(r['alt_gecit_sayisi'])})",
                va="center", fontsize=8.5)
    ax.set_xlabel("Ortalama sel risk skoru (0-100)")
    ax.set_xlim(0, max(d["ortalama_risk"]) * 1.35 + 5)
    ax.set_title("İlçe bazında ortalama sel risk skoru",
                 fontsize=11, fontweight="bold", pad=10)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "sel_02_ilce.png"))
    plt.close(fig)

    # 3) En riskli 15 yapi
    top = df.nlargest(15, "sel_risk_skoru").iloc[::-1]
    labels = [f"{r.yapi_id} · {str(r.ad)[:26] if pd.notna(r.ad) else r.gecit_tipi}"
              for r in top.itertuples()]
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    ax.barh(labels, top["sel_risk_skoru"],
            color=[LEVEL_COLORS.get(v, "#7F8C8D") for v in top["sel_risk_seviyesi"]],
            height=0.65)
    for i, v in enumerate(top["sel_risk_skoru"]):
        ax.text(v + 0.8, i, f"{v:.0f}", va="center", fontsize=8.5, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Sel risk skoru")
    ax.set_title("En yüksek sel riskli 15 alt geçit / tünel yapısı",
                 fontsize=11, fontweight="bold", pad=10)
    ax.tick_params(axis="y", labelsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "sel_03_top15.png"))
    plt.close(fig)

    # 4) Yol kesimleri: cukur derinligi - akim birikimi
    fig, ax = plt.subplots(figsize=(8.2, 3.9))
    for lvl in LEVEL_ORDER:
        s = road[road["sel_risk_seviyesi"] == lvl]
        if s.empty:
            continue
        ax.scatter(s["akim_birikim_ha"].clip(lower=0.5), s["cukur_derinligi_m"],
                   s=14 + s["sel_risk_skoru"] / 2.2, c=LEVEL_COLORS[lvl],
                   alpha=0.72, edgecolor="white", linewidth=0.4, label=lvl)
    ax.set_xscale("log")
    ax.set_xlabel("Akış birikimi (ha, log ölçek)")
    ax.set_ylabel("Yerel çukur derinliği (m)")
    ax.set_title("Yol kesimi sel adayları: çukur derinliği – akış birikimi ilişkisi",
                 fontsize=11, fontweight="bold", pad=10)
    ax.legend(ncol=5, fontsize=8, frameon=False, loc="upper left")
    ax.grid(alpha=0.25, linestyle="--", linewidth=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, "sel_04_yol_sacilim.png"))
    plt.close(fig)


# --------------------------------------------------------------------------
# Yardimcilar
# --------------------------------------------------------------------------
def fmt_tr(v, nd=1, suffix=""):
    if pd.isna(v):
        return "—"
    return f"{v:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".") + suffix


def add_page_number(section):
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)
    run.font.size = Pt(8.5)
    run.font.color.rgb = COLOR_MUTED


def add_bullets(doc, items):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.1
        head, _, rest = it.partition("|")
        r1 = p.add_run(head.strip())
        r1.font.name = "Calibri"
        r1.font.size = Pt(10)
        r1.font.bold = True
        r1.font.color.rgb = COLOR_PRIMARY
        if rest:
            r2 = p.add_run(" — " + rest.strip())
            r2.font.name = "Calibri"
            r2.font.size = Pt(10)
            r2.font.color.rgb = COLOR_TEXT


def kv_table(doc, rows):
    tbl = doc.add_table(rows=len(rows), cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (k, v) in enumerate(rows):
        c0, c1 = tbl.rows[i].cells
        c0.text = k
        c1.text = v
        set_cell_background(c0, "1B365D")
        set_cell_background(c1, "F7F9FB" if i % 2 == 0 else "FFFFFF")
        for c in (c0, c1):
            set_cell_margins(c, top=90, bottom=90, left=130, right=130)
        p0 = c0.paragraphs[0]
        for r in p0.runs:
            r.font.name = "Arial"
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)
        p1 = c1.paragraphs[0]
        for r in p1.runs:
            r.font.name = "Calibri"
            r.font.size = Pt(9.5)
            r.font.color.rgb = COLOR_TEXT
        c0.width = Cm(7.2)
        c1.width = Cm(9.4)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


# --------------------------------------------------------------------------
# Rapor
# --------------------------------------------------------------------------
def main():
    t0 = time.time()
    df = pd.read_csv(CSV_GECIT)
    road = pd.read_csv(CSV_NOKTA)
    ilce = pd.read_csv(CSV_ILCE)
    gecitler = road[road["gecit_tipi"] != "Yol Kesimi"].copy()
    yol_kesim = road[road["gecit_tipi"] == "Yol Kesimi"].copy()

    make_charts(df, yol_kesim, ilce)

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(1.9)
    sec.top_margin = Cm(2.0)
    sec.bottom_margin = Cm(1.9)
    add_page_number(sec)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    # ---------------- Kapak ----------------
    for _ in range(4):
        doc.add_paragraph()

    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kr = kicker.add_run("ANKARA İLİ · ULAŞIM ALTYAPISI RİSK ANALİZİ")
    kr.font.name = "Arial"
    kr.font.size = Pt(10)
    kr.font.bold = True
    kr.font.color.rgb = COLOR_SECONDARY

    t = doc.add_paragraph()
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = t.add_run("Alt Geçit ve Tünellerde\nSel Baskını Risk Analizi")
    tr.font.name = "Arial"
    tr.font.size = Pt(30)
    tr.font.bold = True
    tr.font.color.rgb = COLOR_PRIMARY

    s = doc.add_paragraph()
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = s.add_run("OpenStreetMap envanteri + Copernicus DEM GLO-30 tabanlı\n"
                   "hidrolojik ön değerlendirme ve önceliklendirme raporu")
    sr.font.name = "Calibri"
    sr.font.size = Pt(12.5)
    sr.font.color.rgb = COLOR_TEXT
    s.paragraph_format.space_after = Pt(26)

    # Metrik bandi
    band = doc.add_table(rows=2, cols=4)
    band.alignment = WD_TABLE_ALIGNMENT.CENTER
    metrics = [
        (f"{len(df)}", "Alt geçit / tünel yapısı"),
        (f"{int((df['sel_risk_seviyesi'].isin(['Çok Yüksek', 'Yüksek'])).sum())}",
         "Yüksek öncelikli yapı"),
        (f"{len(yol_kesim)}", "Taranan riskli yol kesimi"),
        (f"{fmt_tr(df['sel_risk_skoru'].max(), 0)}", "En yüksek risk skoru"),
    ]
    for i, (val, lab) in enumerate(metrics):
        c_val = band.cell(0, i)
        c_lab = band.cell(1, i)
        c_val.text = val
        c_lab.text = lab
        set_cell_background(c_val, "1B365D")
        set_cell_background(c_lab, "1B365D")
        pv = c_val.paragraphs[0]
        pv.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in pv.runs:
            r.font.name = "Arial"
            r.font.size = Pt(22)
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)
        pl = c_lab.paragraphs[0]
        pl.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in pl.runs:
            r.font.name = "Calibri"
            r.font.size = Pt(8.5)
            r.font.color.rgb = RGBColor(214, 219, 233)

    doc.add_paragraph()
    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    mr = meta.add_run("28 Kasım 2026  ·  Veri: OpenStreetMap katkıcıları, Copernicus DEM GLO-30 (ESA)\n"
                      "Saha ölçümü içermez; karar destek amaçlı ön tarama niteliğindedir.")
    mr.font.name = "Calibri"
    mr.font.size = Pt(9)
    mr.font.color.rgb = COLOR_MUTED

    doc.add_page_break()

    # ---------------- 1. Yonetici ozeti ----------------
    add_heading_styled(doc, "1. Yönetici Özeti", 1)
    add_body_p(doc,
               "Bu çalışma, Ankara il sınırları içindeki karayolu ve yaya alt geçitleri ile "
               "tünellerin su baskını (sel) riskini, yalnızca açık veri kullanarak önceliklendirir. "
               "OpenStreetMap üzerindeki tüneller ve negatif katmanlı (layer<0) geçiş yapıları "
               "envantere alınmış; her yapının en düşük kotlu noktası 30 m çözünürlüklü "
               "Copernicus DEM üzerinde bulunmuş, ardından Priority-Flood algoritmasıyla "
               "akış yönü ve birikim havzası çıkarılmıştır. Sonuçlar 0-100 aralığında bir "
               "Sel Risk Skoru ile sıralanmıştır.")
    add_body_p(doc,
               f"Toplam {len(df)} alt geçit/tünel yapısı değerlendirilmiş; bunlardan "
               f"{int((df['sel_risk_seviyesi'] == 'Çok Yüksek').sum())} tanesi çok yüksek, "
               f"{int((df['sel_risk_seviyesi'] == 'Yüksek').sum())} tanesi yüksek riskli "
               "bulunmuştur. Aynı yöntemle 1,6 milyon yol noktası taranmış, düşük kotlu ve "
               f"çevresine göre çukurda kalan {len(yol_kesim)} kesim hidrolojik olarak test edilmiş; "
               f"{int((yol_kesim['sel_risk_seviyesi'] == 'Çok Yüksek').sum())} kesim çok yüksek "
               "risk sınıfına girmiştir.")
    add_body_p(doc,
               "Riskin mekânsal dağılımı tek merkezde toplanmamaktadır: Çankaya ilçesi yapı "
               "sayısı ve yüksek riskli yapı adediyle öne çıkarken, Mamak ilçesi ortalama skor "
               "bakımından en yüksek değere sahiptir. Bu iki ilçe, dere ağlarıyla kesişen "
               "ana arter alt geçitlerini barındırdığı için birinci öncelikli müdahale "
               "programına alınmalıdır.")

    top = df.nlargest(1, "sel_risk_skoru").iloc[0]
    add_callout(
        doc,
        f"En yüksek skorlu yapı {top['yapi_id']} ({top['gecit_tipi']}, {top['ilce']}) "
        f"kodlu geçittir: skor {top['sel_risk_skoru']:.0f}, yerel çukur derinliği "
        f"{top['cukur_derinligi_m']:.1f} m, akış birikimi {top['akim_birikim_ha']:.0f} ha, "
        f"en yakın su yoluna {top['dere_mesafe_m']:.0f} m. Yapı, dere yatağına komşu düşük "
        f"kotlu bir çanakta yer aldığı için yoğun yağışta hızlı su toplama potansiyeli taşır. "
        "Saha doğrulaması ve drenaj kapasitesi ölçümü ilk sırada yapılmalıdır.",
        title="ÖNCELİKLİ BULGU",
    )

    kv_table(doc, [
        ("Değerlendirilen yapı", f"{len(df)} adet (Yaya {int((df['gecit_tipi'] == 'Yaya Alt Geçidi').sum())}, "
                                 f"Araç {int((df['gecit_tipi'] == 'Araç Alt Geçidi').sum())}, "
                                 f"Tünel {int((df['gecit_tipi'] == 'Araç Tüneli').sum())})"),
        ("Çok Yüksek / Yüksek riskli yapı",
         f"{int((df['sel_risk_seviyesi'] == 'Çok Yüksek').sum())} / "
         f"{int((df['sel_risk_seviyesi'] == 'Yüksek').sum())} adet"),
        ("Ortalama / en yüksek skor",
         f"{fmt_tr(df['sel_risk_skoru'].mean())} / {fmt_tr(df['sel_risk_skoru'].max(), 0)}"),
        ("Taranan riskli yol kesimi", f"{len(yol_kesim)} nokta "
                                      f"({int((yol_kesim['sel_risk_seviyesi'] == 'Yüksek').sum())} yüksek, "
                                      f"{int((yol_kesim['sel_risk_seviyesi'] == 'Çok Yüksek').sum())} çok yüksek)"),
        ("Hidrolojik referans", "5.450 su yolu (dere, kanal, ark) çizgisi"),
        ("En riskli ilçeler (ortalama skor)",
         ", ".join(f"{r.ilce} ({r.ortalama_risk:.1f})"
                   for r in ilce.nlargest(3, "ortalama_risk").itertuples())),
    ])

    # ---------------- 2. Veri ve yontem ----------------
    add_heading_styled(doc, "2. Veri Kaynakları ve Yöntem", 1)
    add_heading_styled(doc, "2.1 Kullanılan veri setleri", 2)
    add_bullets(doc, [
        "Alt geçit / tünel envanteri|OpenStreetMap Overpass API; `tunnel=yes|building_passage` "
        "ve `layer<0` etiketli 1.448 way (%100 açık veri)",
        "Su yolu ağı|OSM `waterway=river|stream|canal|ditch` — 5.450 çizgi, dere/kanal yakınlığı için",
        "Yükseklik modeli|Copernicus DEM GLO-30 (30 m, ESA) — UTM 36N'e yeniden projeksiyon",
        "İdari sınırlar|Ankara ilçe sınırları (GeoJSON) — ilçe ataması ve özet tablolar",
        "Yol ağı|OSM yol merkez çizgileri — şehir geneli düşük kotlu kesim taraması",
    ])

    add_heading_styled(doc, "2.2 Yapı tespiti ve birleştirme", 2)
    add_body_p(doc,
               "Overpass sorgusu, aynı alt geçidin farklı bölümlerini (giriş rampası, gövde, "
               "çıkış rampası) ayrı way'ler olarak döndürür. Bu parçaların her biri ayrı "
               "değerlendirildiğinde aynı yapı birden fazla kez risk listesine girmektedir. "
               "Bunu önlemek için 80 m'lik bir ızgara kullanılmış; aynı hücreye düşen ve aynı "
               "tip etiketini taşıyan parçalar tek yapı altında birleştirilmiştir. Böylece "
               "1.448 ham way, mükerrer kayıt içermeyen 204 yapıya indirgenmiştir. Her yapı "
               "için en düşük kotlu nokta temsil noktası olarak seçilmiş, uzunluk ve kot "
               "aralığı korunmuştur.")

    add_heading_styled(doc, "2.3 Hidrolojik model", 2)
    add_body_p(doc,
               "Her yapının temsil noktası çevresinde 1,2-1,5 km yarıçaplı bir pencere "
               "kesilmiştir. Bu pencerede DEM üzerine Priority-Flood algoritması uygulanarak "
               "çukurlar doldurulmuş, akış yönleri ve her hücreye düşen birikim alanı (ha) "
               "hesaplanmıştır. Yapı için dört hidrolojik gösterge üretilmiştir:")
    add_bullets(doc, [
        "Yerel çukur derinliği|Yapı kotu ile çevresindeki drenaj çıkış kotu arasındaki fark (m)",
        "Akış birikimi|Yapının memba havzasında toplanan efektif drenaj alanı (ha)",
        "Memba eğimi|Üst havuzun ortalama eğimi (%) — dik yamaçlar hızlı yüzeysel akış üretir",
        "Dere yakınlığı|En yakın su yoluna kuş uçuşu mesafe (m) ve su yolu tipi",
    ])
    add_body_p(doc,
               "Akış birikimi 2 ha'nın altında kalan yapılarda skor %30, 2-5 ha aralığında "
               "%15 indirilmiştir. Bunun nedeni, 30 m çözünürlüklü DEM'de küçük havzaların "
               "yapay çukurlar üretmesi ve yanlış pozitif risk yaratmasıdır.")

    add_heading_styled(doc, "2.4 Sel Risk Skoru (0-100)", 2)
    build_table(
        doc,
        ["Bileşen", "Ağırlık", "Ne ölçüyor?", "Yüksek puan ne anlama gelir?"],
        [
            ["Çukur derinliği", "0-25", "Yapının çevresine göre ne kadar çukurda kaldığı",
             "Su yapıya yönelir, birikme süresi uzar"],
            ["Akış birikimi", "0-25", "Memba havzasının büyüklüğü (ha)",
             "Geniş havza = yüksek debi ve debi süresi"],
            ["Havza derinliği", "0-12", "Yapının bulunduğu çanağın derinliği",
             "Kapalı çanak, drenajsız birikim riski"],
            ["Memba eğimi", "0-12", "Üst havuz eğimi (%)",
             "Dik yamaç, ani ve hızlı yüzeysel akış"],
            ["Dere yakınlığı", "0-10", "En yakın su yoluna mesafe",
             "Taşkın anında doğrudan su girişi"],
            ["Maruziyet", "0-16", "Yol sınıfı, uzunluk, yaya/araç kullanımı",
             "Kesinti ve can kaybı etkisinin büyüklüğü"],
        ],
        col_widths=[Cm(3.6), Cm(1.7), Cm(6.3), Cm(5.4)],
    )
    build_table(
        doc,
        ["Seviye", "Skor aralığı", "Renk", "Önerilen aksiyon"],
        [
            ["Çok Yüksek", "70-100", "Kırmızı", "Saha ölçümü + acil drenaj/pompa projesi"],
            ["Yüksek", "55-69", "Turuncu", "Detaylı hidrolik model + 1 yıl içinde iyileştirme"],
            ["Orta", "35-54", "Sarı", "Periyodik temizlik, izleme, erken uyarı"],
            ["Düşük", "20-34", "Yeşil", "Bakım programına dahil et"],
            ["Çok Düşük", "0-19", "Gri", "Rutin denetim yeterli"],
        ],
        col_widths=[Cm(3.0), Cm(2.8), Cm(2.6), Cm(8.6)],
    )

    add_heading_styled(doc, "2.5 Şehir geneli yol kesimi taraması", 2)
    add_body_p(doc,
               "Alt geçitlerle sınırlı kalmamak için tüm yol ağı da taranmıştır. 1.598.584 yol "
               "noktasından önce düşük kot ve düşük yerel rölyef kriteriyle 177.689 aday "
               "seçilmiş, 120 m ızgarada tekilleştirilerek 45.744 noktaya indirilmiştir. Bu "
               "noktalardan kentsel yoğunluk ve çukur koşulunu sağlayan 400 tanesi hidrolojik "
               "modele sokulmuştur. Tarama, alt geçit envanterinde görünmeyen düz ve kapalı "
               "kesimlerdeki birikim riskini yakalamayı amaçlar.")

    # ---------------- 3. Envanter ----------------
    doc.add_page_break()
    add_heading_styled(doc, "3. Alt Geçit ve Tünel Envanteri", 1)
    add_body_p(doc,
               f"Envanterdeki {len(df)} yapının tip dağılımı ve risk profili aşağıdadır. "
               "Araç alt geçitleri sayıca baskın olmakla birlikte, en yüksek skorlar dere "
               "yataklarına yakın yaya geçitlerinde ve derin çanaklardaki araç geçitlerinde "
               "görülmektedir.")

    tip_rows, tip_stat = [], []
    for tip, g in df.groupby("gecit_tipi"):
        tip_stat.append((tip, len(g), g["sel_risk_skoru"].mean(),
                         g["sel_risk_skoru"].max(), g["cukur_derinligi_m"].mean()))
    tip_stat.sort(key=lambda x: -x[1])
    for tip, n, avg, mx, pit in tip_stat:
        hi = int(df[(df["gecit_tipi"] == tip) &
                    (df["sel_risk_seviyesi"].isin(["Çok Yüksek", "Yüksek"]))].shape[0])
        tip_rows.append([tip, str(n), str(hi), fmt_tr(avg), fmt_tr(mx, 0), fmt_tr(pit)])
    build_table(doc, ["Yapı tipi", "Adet", "Yüksek öncelikli", "Ort. skor", "Maks. skor", "Ort. çukur (m)"],
                tip_rows, col_widths=[Cm(5.4), Cm(1.8), Cm(3.2), Cm(2.4), Cm(2.4), Cm(2.7)],
                align_right_cols=[1, 2, 3, 4, 5])
    add_figure(doc, "sel_01_tip_risk.png",
               "Şekil 1 — Yapı tiplerine göre sel risk seviyesi dağılımı")

    add_heading_styled(doc, "3.1 İlçe bazında dağılım", 2)
    add_body_p(doc,
               "Yapıların %49'u Çankaya ilçesinde yer almaktadır; bunu Etimesgut ve "
               "Yenimahalle izler. Ancak ortalama risk sıralaması farklıdır: Mamak, az sayıda "
               "yapı barındırmasına karşın yüksek ortalama skorla dikkat çeker. Bu durum, "
               "ilçedeki geçitlerin Hatip Çayı ve kollarıyla doğrudan ilişkili derin "
               "vadilerde konumlanmasından kaynaklanır.")
    ilce_rows = []
    for r in ilce.sort_values("alt_gecit_sayisi", ascending=False).itertuples():
        ilce_rows.append([r.ilce, str(int(r.alt_gecit_sayisi)), str(int(r.cok_yuksek)),
                          str(int(r.yuksek)), fmt_tr(r.ortalama_risk), fmt_tr(r.maksimum_risk, 0),
                          fmt_tr(r.ortalama_cukur_m)])
    build_table(doc, ["İlçe", "Yapı", "Çok Yüksek", "Yüksek", "Ort. skor", "Maks. skor", "Ort. çukur (m)"],
                ilce_rows, col_widths=[Cm(4.2), Cm(1.6), Cm(2.4), Cm(2.0), Cm(2.2), Cm(2.2), Cm(2.6)],
                align_right_cols=[1, 2, 3, 4, 5, 6])
    add_figure(doc, "sel_02_ilce.png",
               "Şekil 2 — İlçe bazında ortalama sel risk skoru (n = yapı sayısı)")

    # ---------------- 4. En riskli yapilar ----------------
    doc.add_page_break()
    add_heading_styled(doc, "4. En Yüksek Riskli Yapılar", 1)
    add_body_p(doc,
               "Aşağıdaki tablo, skora göre sıralanmış ilk 20 yapıyı göstermektedir. "
               "Koordinatlar WGS84 (lon/lat) ve UTM 36N (X/Y) olarak verilmiştir; her satır "
               "için Google Maps bağlantısı interaktif haritada ve CSV dosyasında yer alır.")

    top20 = df.nlargest(20, "sel_risk_skoru")
    rows = []
    for i, r in enumerate(top20.itertuples(), 1):
        ad = str(r.ad) if pd.notna(r.ad) and str(r.ad).strip() else "—"
        rows.append([str(i), r.yapi_id, r.gecit_tipi.replace(" Alt Geçidi", "").replace("Araç Tüneli", "Tünel"),
                     r.ilce, fmt_tr(r.sel_risk_skoru, 0), r.sel_risk_seviyesi,
                     fmt_tr(r.cukur_derinligi_m), fmt_tr(r.akim_birikim_ha, 0),
                     fmt_tr(r.dere_mesafe_m, 0),
                     f"{r.lat:.4f}, {r.lon:.4f}"])
    build_table(doc, ["#", "ID", "Tip", "İlçe", "Skor", "Seviye", "Çukur (m)", "Akım (ha)", "Dere (m)", "lat, lon"],
                rows, col_widths=[Cm(0.8), Cm(1.6), Cm(2.2), Cm(2.2), Cm(1.2), Cm(1.9),
                                  Cm(1.5), Cm(1.5), Cm(1.4), Cm(2.7)],
                align_right_cols=[0, 4, 6, 7, 8])
    add_figure(doc, "sel_03_top15.png",
               "Şekil 3 — En yüksek skorlu 15 yapı ve risk seviyesi renkleri")

    # Dere bazli kume
    near_river = df[(df["dere_mesafe_m"] < 60) & (df["sel_risk_skoru"] >= 45)]
    if len(near_river):
        add_callout(
            doc,
            f"{len(near_river)} yapı, en yakın su yoluna 60 m'den daha yakın ve 45 üzeri skora "
            "sahip. Bu yapıların tamamı taşkın anında doğrudan yüzey suyu girişine açıktır; "
            "giriş rampalarının ters eğimle korunması, yağmur suyu ızgaralarının kapasite "
            "artırımı ve su seviyesi sensörü ile erken uyarı bu grupta öncelikli olmalıdır.",
            title="DERE KOMŞULUĞU RİSKİ",
        )

    add_heading_styled(doc, "4.1 Öne çıkan yapı grupları", 2)
    add_bullets(doc, [
        "Kızılay – Çankaya kümesi|Aynı kavşak çevresinde birleştirilen altı parça, 75 ve 72 "
        "skorla listenin başında; İncesu Deresi'ne 6-202 m mesafede",
        "Şehit Ömer Halisdemir Bulvarı (Mamak)|Hatip Çayı üzerinde, 14,8 m çukur derinliği ve "
        "%15 memba eğimi ile yüksek debiye maruz",
        "Etimesgut – Eryaman aksı|Otoyol alt geçitleri düşük rölyefli düzlükte; akış birikimi "
        "sınırlı ancak drenajsız çanak nedeniyle orta-yüksek skorlu",
        "Kuzey ilçeleri (Kızılcahamam, Çubuk)|Dere vadilerine yerleşen yol kesimleri, dik memba "
        "eğimi nedeniyle 90 üzeri skorlara ulaşan istisnai noktalar içeriyor",
    ])

    # ---------------- 5. Yol kesimleri ----------------
    doc.add_page_break()
    add_heading_styled(doc, "5. Şehir Geneli Yol Kesimi Bulguları", 1)
    add_body_p(doc,
               f"Hidrolojik modele sokulan {len(yol_kesim)} yol kesiminin "
               f"{int((yol_kesim['sel_risk_seviyesi'] == 'Çok Yüksek').sum())} tanesi çok yüksek, "
               f"{int((yol_kesim['sel_risk_seviyesi'] == 'Yüksek').sum())} tanesi yüksek risk "
               f"sınıfındadır. Kesimlerin {int(yol_kesim['kentsel_mi'].sum())} tanesi kentsel "
               "yoğunluk eşiğini aşan bölgelerde bulunur; bu, riskin yalnızca kırsal derelerde "
               "değil, yapılaşmanın yoğun olduğu düzlüklerde de biriktiğini gösterir.")

    lvl_rows = []
    for lvl in LEVEL_ORDER:
        s = yol_kesim[yol_kesim["sel_risk_seviyesi"] == lvl]
        if s.empty:
            continue
        lvl_rows.append([lvl, str(len(s)), fmt_tr(s["sel_risk_skoru"].mean()),
                         fmt_tr(s["cukur_derinligi_m"].mean()), fmt_tr(s["akim_birikim_ha"].mean(), 0),
                         fmt_tr(s["yerel_rolyef_m"].mean())])
    build_table(doc, ["Seviye", "Nokta", "Ort. skor", "Ort. çukur (m)", "Ort. akım (ha)", "Ort. rölyef (m)"],
                lvl_rows, col_widths=[Cm(3.6), Cm(2.0), Cm(2.8), Cm(3.4), Cm(3.4), Cm(3.4)],
                align_right_cols=[1, 2, 3, 4, 5])
    add_figure(doc, "sel_04_yol_sacilim.png",
               "Şekil 4 — Yol kesimi adaylarında çukur derinliği ve akış birikimi ilişkisi")

    add_heading_styled(doc, "5.1 En yüksek riskli yol kesimleri", 2)
    rows = []
    for i, r in enumerate(yol_kesim.nlargest(12, "sel_risk_skoru").itertuples(), 1):
        rows.append([str(i), r.yapi_id, str(r.ilce), fmt_tr(r.sel_risk_skoru, 0),
                     fmt_tr(r.cukur_derinligi_m), fmt_tr(r.akim_birikim_ha, 0),
                     fmt_tr(r.dere_mesafe_m, 0), "Evet" if r.kentsel_mi else "Hayır",
                     f"{r.lat:.4f}, {r.lon:.4f}"])
    build_table(doc, ["#", "ID", "İlçe", "Skor", "Çukur (m)", "Akım (ha)", "Dere (m)", "Kentsel", "lat, lon"],
                rows, col_widths=[Cm(0.8), Cm(1.8), Cm(2.9), Cm(1.3), Cm(1.7), Cm(1.7), Cm(1.6), Cm(1.5), Cm(3.0)],
                align_right_cols=[0, 3, 4, 5, 6])

    add_callout(
        doc,
        "Kızılcahamam'daki Berçin Çayı üzerinde yer alan kesim 94 puanla en yüksek skoru alır: "
        "62 m havza derinliği, %21 memba eğimi ve 370 ha akış birikimi bir arada. Bu tür "
        "noktalar yerleşim dışı görünse de ana yol bağlantısını kesintiye uğratma potansiyeli "
        "nedeniyle ulaşım ağı riski olarak ele alınmalıdır.",
        title="YÜKSEK RÖLYEFLİ VADİ KESİMLERİ",
    )

    # ---------------- 6. Oneriler ----------------
    doc.add_page_break()
    add_heading_styled(doc, "6. Mühendislik ve İşletme Önerileri", 1)
    add_body_p(doc,
               "Öneriler risk seviyesine göre kademelendirilmiştir. Amaç, sınırlı yatırım "
               "bütçesini en yüksek fayda/maliyet oranına sahip noktalara yönlendirmektir.")

    add_heading_styled(doc, "6.1 Çok yüksek ve yüksek riskli yapılar (22 adet)", 2)
    add_bullets(doc, [
        "Saha doğrulaması|Kot, giriş rampası eğimi, mevcut drenaj ızgarası ve pompa kapasitesi ölçülmeli",
        "Hidrolik model|1B/2B yağış-akış modeli ile 10, 50 ve 100 yıllık yağış senaryoları test edilmeli",
        "Giriş koruması|Ters eğim, yükseltilmiş bordür ve yüksek kapasiteli ızgara ile yüzey suyu yönlendirilmeli",
        "Pompa ve enerji|Yedek enerjili drenaj pompası, otomatik seviye anahtarı ve bakım sözleşmesi",
        "Erken uyarı|Su seviyesi sensörü + değişken mesaj panosu; kritik seviyede geçit otomatik kapatılmalı",
    ])
    add_heading_styled(doc, "6.2 Orta riskli yapılar (32 adet)", 2)
    add_bullets(doc, [
        "Periyodik bakım|Yılda iki kez ızgara ve kanal temizliği, mevsim öncesi kontrol",
        "İzleme|Yağış sonrası görsel denetim kaydı ve tekrarlayan su birikimi raporlaması",
        "Küçük ölçekli iyileştirme|Eksik ızgara tamamlama, yağmur suyu hattı bağlantısı",
    ])
    add_heading_styled(doc, "6.3 Şehir geneli", 2)
    add_bullets(doc, [
        "Veri güncellemesi|OSM etiketlerinin (tunnel, layer, maxheight) saha ile eşleştirilmesi",
        "Yağış verisi entegrasyonu|MGM yağış istatistikleri ve sayısal hava tahmini ile dinamik risk",
        "Kurumsal izleme|Risk skorlarının yıllık güncellenmesi ve yatırım programına bağlanması",
    ])

    # ---------------- 7. Sinirlamalar ----------------
    add_heading_styled(doc, "7. Sınırlamalar ve Doğrulama İhtiyacı", 1)
    add_bullets(doc, [
        "DEM çözünürlüğü|GLO-30 dikey doğruluğu birkaç metre mertebesinde; kesin kot için saha ölçümü gerekir",
        "OSM etiket kalitesi|Eksik veya hatalı `layer`/`tunnel` etiketleri envanteri sınırlar",
        "Yağış senaryosu|Model statik drenaj alanına dayanır; tasarım yağışı ve iklim projeksiyonu içermez",
        "Kanal kapasitesi|Mevcut yağmur suyu hattı, pompa ve menfez kapasitesi veri setinde yoktur",
        "Yanlış pozitif|Küçük havzalarda DEM gürültüsü skoru şişirebilir; indirim uygulanmıştır",
    ])
    add_body_p(doc,
               "Bu nedenle rapor, yatırım kararı yerine önceliklendirme ve saha doğrulama "
               "programı için gerekçe olarak kullanılmalıdır. Her yüksek riskli nokta için "
               "yerinde ölçüm yapılmadan nihai proje tasarımına geçilmemelidir.")

    # ---------------- 8. Ciktilar ----------------
    add_heading_styled(doc, "8. Çıktı Dosyaları ve Erişim", 1)
    build_table(doc, ["Dosya", "İçerik"],
                [["Ankara_OSM_Alt_Gecit_Sel_Harita.html",
                  "İnteraktif Leaflet haritası (ESRI Uydu/Sokak/Topo/Koyu), filtre ve Google Maps bağlantıları"],
                 ["Ankara_OSM_Alt_Gecitler.csv", "204 yapının tam envanteri ve skor bileşenleri"],
                 ["Ankara_OSM_Sel_Riskli_Noktalar.csv", "Yapılar + 400 yol kesimi, öncelik sıralı"],
                 ["Ankara_OSM_Sel_Ilce_Ozeti.csv", "İlçe bazında özet metrikler"],
                 ["Ankara_Alt_Gecit_Sel_Analizi.xlsx", "Çok sayfalı Excel çalışma kitabı"],
                 ["sel_analiz_ozet.json", "Makine okunur analiz özeti"]],
                col_widths=[Cm(7.4), Cm(9.6)])
    add_body_p(doc,
               "Canlı harita: https://darkeaglehome.github.io/ankara-yol-guvenligi/"
               "Ankara_OSM_Alt_Gecit_Sel_Harita.html")
    add_body_p(doc,
               "Yöntem, skor ağırlıkları ve tüm ara çıktılar `altgecit_sel_ankara.py` "
               "dosyasında açık kaynak olarak yer alır; analiz tek komutla yeniden üretilebilir.")

    doc.save(OUT_DOCX)
    print(f"Word raporu yazildi: {OUT_DOCX}  ({time.time()-t0:.1f} sn)")


if __name__ == "__main__":
    main()
