# -*- coding: utf-8 -*-
"""
generate_word_ankara.py
Ankara Yol Guvenligi ve Geometrik Kusur Raporunu (.docx) olusturur.
Tum veriler OSM (Geofabrik PBF) uzerinden uretilmistir.
XY koordinatli problemli noktalar (UTM 36N + WGS84 lon/lat) rapora islenir.
"""
import os
import time

import numpy as np
import pandas as pd
import pyproj
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "rapor_gorselleri")
CSV_ALL = os.path.join(BASE_DIR, "Ankara_OSM_Tum_Kusurlar.csv")
CSV_BS = os.path.join(BASE_DIR, "Ankara_OSM_Kara_Noktalar_Oncelikli.csv")
CSV_ILCE = os.path.join(BASE_DIR, "Ankara_OSM_Ilce_Ozeti.csv")

OUT_DOCX = os.path.join(BASE_DIR, "Ankara_Yol_Guvenligi_ve_Kusur_Analizi_Raporu.docx")

# Renk Paleti (Kurumsal Muhendislik Stili)
COLOR_PRIMARY = RGBColor(27, 54, 93)      # Lacivert (#1B365D)
COLOR_SECONDARY = RGBColor(192, 57, 43)   # Koyu Kirmizi (#C0392B)
COLOR_ACCENT = RGBColor(41, 128, 185)     # Mavi (#2980B9)
COLOR_TEXT = RGBColor(44, 62, 80)         # Antrasit (#2C3E50)
COLOR_MUTED = RGBColor(127, 140, 141)     # Gri (#7F8C8D)

KIND_LABELS = {
    "KURP": "Keskin Viraj (R ≤ 75 m)",
    "GENISLIK": "Dar Kesit / Şişe Boynu (W ≤ 5.5 m)",
    "KAVSAK_ACISI": "Dar Açılı Kör Kavşak (θ ≤ 45°)",
    "CIKMAZ_SOKAK": "Ana Yola Çıkmaz Sokak",
    "DONUS_CEBI": "Dönüş Cebi Manevra Kısıtı",
}


def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def set_cell_margins(cell, top=120, bottom=120, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def add_callout(doc, text, title="ÖNEMLİ TESPİT / MÜHENDİSLİK UYARISI"):
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = tbl.cell(0, 0)
    set_cell_background(c, "F2F4F7")
    set_cell_margins(c, top=160, bottom=160, left=240, right=200)

    tcPr = c._tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    left_b = OxmlElement('w:left')
    left_b.set(qn('w:val'), 'single')
    left_b.set(qn('w:sz'), '36')
    left_b.set(qn('w:space'), '0')
    left_b.set(qn('w:color'), 'C0392B')
    tcBorders.append(left_b)
    for side in ('top', 'bottom', 'right'):
        b = OxmlElement(f'w:{side}')
        b.set(qn('w:val'), 'none')
        tcBorders.append(b)
    tcPr.append(tcBorders)

    p = c.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(4)
    run_t = p.add_run(f"\U0001F4CC {title}\n")
    run_t.font.name = "Arial"
    run_t.font.size = Pt(10.5)
    run_t.font.bold = True
    run_t.font.color.rgb = COLOR_SECONDARY

    run_b = p.add_run(text)
    run_b.font.name = "Calibri"
    run_b.font.size = Pt(10)
    run_b.font.color.rgb = COLOR_TEXT
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_heading_styled(doc, text, level):
    h = doc.add_heading(text, level=level)
    h.paragraph_format.keep_with_next = True
    run = h.runs[0]
    run.font.name = "Arial"
    if level == 1:
        run.font.size = Pt(16)
        run.font.bold = True
        run.font.color.rgb = COLOR_PRIMARY
        h.paragraph_format.space_before = Pt(18)
        h.paragraph_format.space_after = Pt(8)
    elif level == 2:
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = COLOR_SECONDARY
        h.paragraph_format.space_before = Pt(14)
        h.paragraph_format.space_after = Pt(6)
    elif level == 3:
        run.font.size = Pt(11.5)
        run.font.bold = True
        run.font.color.rgb = COLOR_ACCENT
        h.paragraph_format.space_before = Pt(10)
        h.paragraph_format.space_after = Pt(4)
    return h


def add_body_p(doc, text, bold_prefix=None, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(space_after)
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = "Calibri"
        r_pre.font.size = Pt(10.5)
        r_pre.font.bold = True
        r_pre.font.color.rgb = COLOR_PRIMARY
    r_body = p.add_run(text)
    r_body.font.name = "Calibri"
    r_body.font.size = Pt(10.5)
    r_body.font.color.rgb = COLOR_TEXT
    return p


def build_table(doc, headers, data, col_widths=None, align_right_cols=None):
    align_right_cols = align_right_cols or []
    tbl = doc.add_table(rows=len(data) + 1, cols=len(headers))
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr_cells = tbl.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        set_cell_background(hdr_cells[i], "1B365D")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=120, right=120)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = (WD_ALIGN_PARAGRAPH.RIGHT
                       if i in align_right_cols else WD_ALIGN_PARAGRAPH.LEFT)
        for r in p.runs:
            r.font.name = "Arial"
            r.font.size = Pt(9.5)
            r.font.bold = True
            r.font.color.rgb = RGBColor(255, 255, 255)

    for row_idx, row_vals in enumerate(data):
        row_cells = tbl.rows[row_idx + 1].cells
        bg_col = "FFFFFF" if row_idx % 2 == 0 else "F7F9FB"
        for col_idx, val in enumerate(row_vals):
            row_cells[col_idx].text = str(val)
            set_cell_background(row_cells[col_idx], bg_col)
            set_cell_margins(row_cells[col_idx], top=80, bottom=80, left=100, right=100)
            p = row_cells[col_idx].paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.RIGHT
                           if col_idx in align_right_cols else WD_ALIGN_PARAGRAPH.LEFT)
            for r in p.runs:
                r.font.name = "Calibri"
                r.font.size = Pt(9.5)
                r.font.color.rgb = COLOR_TEXT

    if col_widths:
        for row in tbl.rows:
            for idx, width in enumerate(col_widths):
                row.cells[idx].width = width

    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl


def add_figure(doc, filename, caption):
    pth = os.path.join(IMG_DIR, filename)
    if not os.path.exists(pth):
        return
    doc.add_paragraph().paragraph_format.space_before = Pt(8)
    doc.add_picture(pth, width=Inches(6.2))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    c_run = cp.add_run(caption)
    c_run.font.size = Pt(8.5)
    c_run.font.italic = True
    c_run.font.color.rgb = COLOR_MUTED


def fmt_xy(r):
    """UTM 36N (x, y) + WGS84 (lon, lat) koordinat metni."""
    return (f"X:{r['x']:,.0f} Y:{r['y']:,.0f} / "
            f"lon:{r['lon']:.5f} lat:{r['lat']:.5f}")


def main():
    t0 = time.time()
    print("Veriler yukleniyor...", flush=True)
    df = pd.read_csv(CSV_ALL, low_memory=False)
    df_bs = pd.read_csv(CSV_BS, low_memory=False)
    df_ilce = pd.read_csv(CSV_ILCE, low_memory=False)

    # XY -> WGS84
    tr = pyproj.Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True)
    for d in (df, df_bs):
        lon, lat = tr.transform(d["x"].values, d["y"].values)
        d["lon"] = np.round(lon, 6)
        d["lat"] = np.round(lat, 6)

    # Ankara ici (sinir disi kayitlar ana analizden cikarildi)
    df_ic = df[df["ilce"] != "Ankara Disi / Sinir Disi"].copy()
    df_ilce_ic = df_ilce[df_ilce["ilce"] != "Ankara Disi / Sinir Disi"].copy()

    n_total = len(df)
    n_ic = len(df_ic)
    n_kritik = int((df_ic.risk_seviyesi == "Kritik Kara Nokta").sum())
    n_yuksek = int((df_ic.risk_seviyesi == "Yüksek Risk").sum())
    n_orta = int((df_ic.risk_seviyesi == "Orta Risk").sum())
    n_dusuk = int((df_ic.risk_seviyesi == "Düşük Risk").sum())
    n_ilce = df_ilce_ic.shape[0]
    max_risk = df_ic.risk_skoru.max()
    ort_risk = df_ic.risk_skoru.mean()

    # yol agi buyuklugu (report_ankara.py markdown ozetinden okunur)
    n_ways, km_net = 0, 0
    try:
        import re as _re
        _md = open(os.path.join(BASE_DIR, "Ankara_OSM_Yol_Guvenligi_Raporu.md"),
                   encoding="utf-8").read()
        m1 = _re.search(r"Yol ağı \(way\) \| ([\d.,]+)", _md)
        m2 = _re.search(r"Toplam yol uzunluğu \| ([\d.,]+)", _md)
        def _num(s):
            return int(s.replace(".", "").replace(",", "").strip())
        n_ways = _num(m1.group(1)) if m1 else 0
        km_net = _num(m2.group(1)) if m2 else 0
    except Exception:
        pass
    n_raw = int(df["sample_count"].sum()) if "sample_count" in df.columns else n_total

    print("Word dokumani hazirlaniyor...", flush=True)
    doc = Document()

    # Sayfa yapisi (A4)
    for s in doc.sections:
        s.top_margin = Cm(2.0)
        s.bottom_margin = Cm(2.0)
        s.left_margin = Cm(2.0)
        s.right_margin = Cm(2.0)
        s.different_first_page_header_footer = True

        hp = s.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run(
            "T.C. ANKARA BÜYÜKŞEHİR BELEDİYESİ | YOL GÜVENLİĞİ VE "
            "GEOMETRİK KUSUR ANALİZ RAPORU (OSM)")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = COLOR_MUTED

        fp = s.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run(
            "Sayfa - Ankara Yol Güvenliği ve Kara Nokta Analizi Raporu")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = COLOR_MUTED

    # -------------------------------------------------------------
    # KAPAK SAYFASI
    # -------------------------------------------------------------
    p_pre = doc.add_paragraph()
    p_pre.paragraph_format.space_before = Pt(30)
    p_pre.paragraph_format.space_after = Pt(10)
    r_sub = p_pre.add_run(
        "T.C. ANKARA BÜYÜKŞEHİR BELEDİYESİ\nULAŞIM VE YOL ALTYAPISI "
        "DENETİM DAİRESİ")
    r_sub.font.name = "Arial"
    r_sub.font.size = Pt(12)
    r_sub.font.bold = True
    r_sub.font.color.rgb = COLOR_MUTED

    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(20)
    p_title.paragraph_format.space_after = Pt(15)
    r_title = p_title.add_run(
        "ANKARA İLİ YOL AĞI VE GEOMETRİSİ\nKAPSAMLI GÜVENLİK ANALİZ RAPORU")
    r_title.font.name = "Arial"
    r_title.font.size = Pt(24)
    r_title.font.bold = True
    r_title.font.color.rgb = COLOR_PRIMARY

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(30)
    r_desc = p_sub.add_run(
        f"OpenStreetMap (Geofabrik Turkey PBF) Yol Ağı Topolojisi Üzerinden "
        f"{n_ways:,} Yol Ekseni, {n_total:,} Tekil Tehlike Bölgesi, XY Koordinatlı "
        f"Kara Nokta Tespiti ve 25 İlçe Bazlı Risk Sınıflandırması")
    r_desc.font.name = "Calibri"
    r_desc.font.size = Pt(13)
    r_desc.font.italic = True
    r_desc.font.color.rgb = COLOR_TEXT

    cover_info = [
        ["Analiz Kapsamı", "Ankara İl Sınırları (25 İlçe)"],
        ["Veri Kaynağı", "OpenStreetMap - Geofabrik turkey-latest.osm.pbf"],
        ["Yol Ağı Boyutu", f"{n_ways:,} yol (way) / yaklaşık {km_net:,} km"],
        ["İncelenen Kusur Kaydı", f"{n_raw:,} ham geometrik/topolojik/eğim anomalisi"],
        ["Tekil Tehlike Bölgesi", f"{n_total:,} nokta (30 m kümeleme sonrası)"],
        ["Kot / Eğim Kaynağı",
         "Copernicus DEM GLO-30 (30 m, ESA) — boyuna eğim g = Δz/Δs"],
        ["Kot Aralığı", f"{df.kot_m.min():.0f} – {df.kot_m.max():.0f} m"],
        ["Kritik Kara Nokta", f"{n_kritik:,} nokta (Risk Skoru ≥ 75)"],
        ["Koordinat Sistemi",
         "WGS84 / UTM 36N (EPSG:32636) + WGS84 coğrafi (lon/lat)"],
        ["Raporlama Tarihi", time.strftime("%d.%m.%Y")],
    ]
    build_table(doc, ["İnceleme Parametresi", "Teknik Detay ve Kapsam"],
                cover_info, [Cm(5.5), Cm(11.0)])

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 1: YÖNETİCİ ÖZETİ
    # -------------------------------------------------------------
    add_heading_styled(doc, "1. YÖNETİCİ ÖZETİ (EXECUTIVE SUMMARY)", level=1)

    add_body_p(doc,
        "Ankara ili, hızlı kentsel büyüme, ana arterlerdeki yüksek işletme "
        "hızları, arazinin engebeli yapısı ve tarihi dokunun korunması "
        "nedeniyle geometrik kusurlar barındıran geniş bir yol ağına sahiptir. "
        f"Bu çalışma kapsamında OpenStreetMap (OSM) veri tabanından elde edilen "
        f"{n_ways:,} adet yol ekseni (way) üzerinde; keskin viraj, dar kesit, dar "
        f"açılı kavşak, çıkmaz sokak ve dönüş cebi olmak üzere beş farklı kusur "
        f"türü otomatik olarak taranmış, kusurlar 30 metrelik mekansal kümeleme "
        f"ile birleştirilerek {n_total:,} adet tekil tehlike bölgesi belirlenmiştir. "
        f"Buna ek olarak, OSM'de bulunmayan yol kotları **Copernicus DEM GLO-30 "
        f"(30 m)** yükseklik modelinden indirilerek modele dahil edilmiş; "
        f"%8 ve üzeri dik boyuna eğimli "
        f"{int((df_ic.kind=='EGIM').sum()):,} kesim ayrıca kusur olarak "
        f"işaretlenmiştir.")

    add_callout(doc,
        f"Ankara genelinde tespit edilen {n_total:,} tehlike bölgesinden "
        f"{n_kritik:,} adeti 'Kritik Kara Nokta' (Risk Skoru ≥ 75), "
        f"{n_yuksek:,} adeti 'Yüksek Risk' (55-74) olarak sınıflandırılmıştır. "
        f"Ana arterlerde kritik kara nokta sayısı "
        f"{int(((df_ic.risk_seviyesi=='Kritik Kara Nokta') & (df_ic.yol_hiyerarsisi=='Ana Arter')).sum()):,} "
        f"olup, yüksek hız ile geometrik kusurun birleştiği bu noktalar acil "
        f"müdahale önceliğindedir.",
        title="STRATEJİK DENETİM BULGUSU")

    add_heading_styled(doc, "1.1. Temel Göstergeler ve Risk Dağılımı", level=2)
    sum_table_data = [
        ["Kritik Kara Nokta (≥ 75)", f"{n_kritik:,}",
         f"%{100*n_kritik/max(n_ic,1):.1f}",
         "Savrulma/devrilme ve ağır çarpışma potansiyeli en yüksek noktalar"],
        ["Yüksek Risk (55 - 74)", f"{n_yuksek:,}",
         f"%{100*n_yuksek/max(n_ic,1):.1f}",
         "Hızlı müdahale gerektiren öncelikli kara nokta adayları"],
        ["Orta Risk (35 - 54)", f"{n_orta:,}",
         f"%{100*n_orta/max(n_ic,1):.1f}",
         "İşaretleme ve hız yönetimi ile düşürülebilir risk bölgeleri"],
        ["Düşük Risk (< 35)", f"{n_dusuk:,}",
         f"%{100*n_dusuk/max(n_ic,1):.1f}",
         "İzleme kapsamında tutulacak düşük öncelikli noktalar"],
        ["TOPLAM (Ankara içi)", f"{n_ic:,}", "%100.0",
         f"{n_ilce} ilçede tescillenen toplam kusurlu nokta"],
    ]
    build_table(doc, ["Risk Sınıfı", "Nokta Sayısı", "Oran (%)",
                      "Mühendislik Değerlendirmesi"],
                sum_table_data, [Cm(4.2), Cm(2.6), Cm(2.0), Cm(8.2)],
                align_right_cols=[1, 2])

    # Kusur turu ozeti
    kind_rows = []
    for k, sub in df_ic.groupby("kind"):
        kind_rows.append([
            KIND_LABELS.get(k, k), f"{len(sub):,}",
            f"%{100*len(sub)/max(n_ic,1):.1f}",
            f"{sub['risk_skoru'].mean():.1f}",
            f"{int((sub.risk_seviyesi=='Kritik Kara Nokta').sum()):,}"])
    kind_rows.sort(key=lambda r: -int(r[1].replace(",", "")))
    add_body_p(doc,
        "Ankara içi teknik bölgede tespit edilen kusurların tür bazlı "
        "dağılımı aşağıda özetlenmiştir:")
    build_table(doc, ["Kusur Türü", "Adet", "Oran (%)", "Ort. Risk",
                      "Kritik Kara Nokta"],
                kind_rows, [Cm(6.0), Cm(2.4), Cm(2.2), Cm(2.4), Cm(3.0)],
                align_right_cols=[1, 2, 3, 4])

    add_figure(doc, "01_kusur_turleri_dagilimi.png",
               "Şekil 1.1: Ankara geneli kusur türlerine göre dağılım (tüm kayıt).")
    add_figure(doc, "03_risk_skoru_ve_seviyeleri.png",
               "Şekil 1.2: Risk skoru (YGE 0-100) dağılımı ve risk seviyeleri.")

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 2: METODOLOJİ
    # -------------------------------------------------------------
    add_heading_styled(doc,
        "2. METODOLOJİ VE VERİ TABANI MİMARİSİ", level=1)

    add_body_p(doc,
        "Bu rapor, kazayı geriye dönük istatistiklerle değil; kazayı doğrudan "
        "tetikleyen fiziksel ve geometrik altyapı kusurlarını önceden "
        "belirleyen proaktif (önleyici) bir mühendislik yaklaşımıyla "
        "hazırlanmıştır. Referans model (İstanbul DGN tabanlı) yalnızca OSM "
        "verisi kullanılarak Ankara için yeniden kurulmuştur.")

    add_heading_styled(doc,
        "2.1. OpenStreetMap Yol Ağı ve Geometrik Kusur Çıkarımı", level=2)
    add_body_p(doc,
        f"Geofabrik `turkey-latest.osm.pbf` dosyasından Ankara ili sınırları "
        f"süzülerek {n_ways:,} adet yol ekseni ve yaklaşık {km_net:,} km yol ağı "
        f"elde edilmiştir. Yol geometrileri WGS84 / UTM 36N (EPSG:32636) "
        "koordinatlarına projekte edildikten sonra aşağıdaki kusurlar "
        "otomatik olarak taranmıştır:",
        bold_prefix="• Taranan Kusur Kategorileri: ")
    add_body_p(doc,
        "a) Keskin Viraj (KURP): Her OSM verteksinde dönüş açısı θ'dan "
        "R = ds/dθ hesaplanarak R ≤ 75 m olan virajlar tespit edilmiştir. "
        "Kavşak düğümlerindeki 30° üzerindeki sert dönüşler 'sokak köşesi' "
        "olarak dışlanıp kavşak açısı modülüne devredilmiştir.")
    add_body_p(doc,
        "b) Dar Kesit / Şişe Boynu (GENISLIK): OSM `width` etiketi → "
        "`lanes × 3.25 m` → sınıf varsayımı sıralamasıyla genişlik tahmini "
        "yapılmış; W ≤ 5.5 m olan kentsel yol kesitleri tehlike sayılmıştır.")
    add_body_p(doc,
        "c) Dar Açılı Kör Kavşak (KAVSAK_ACISI): Paylaşımlı OSM düğümlerinde "
        "yol kollarının yön vektörleri hesaplanarak θ ≤ 45° olan kavşak "
        "kolları tespit edilmiştir.")
    add_body_p(doc,
        "d) Çıkmaz Sokak (CIKMAZ_SOKAK): Ağ topolojisinde tek uçlu, "
        "paylaşılmayan ve ana yola bağlanan kör sokaklar belirlenmiştir.")
    add_body_p(doc,
        "e) Dönüş Cebi (DONUS_CEBI): `highway=turning_circle` ve "
        "`mini_roundabout` düğümleri manevra kısıtı olarak modellenmiştir.")
    add_body_p(doc,
        "f) Dik Boyuna Eğim (EGIM): Copernicus DEM GLO-30 (30 m) mozaiği "
        "indirilmiş, her yol ekseni boyunca 30 m aralıklı kot örneklenmiş ve "
        "90 m'lik pencerede boyuna eğim g = Δz/Δs hesaplanmıştır. |g| ≥ %8 "
        "olan ve en az 90 m süren kesimler kusur kabul edilmiş; eğim "
        "kırılması (Δ) da kayda eklenmiştir. Aynı DEM'den her kusur noktasının "
        "kotu ve arazi eğimi de türetilmiş, risk skoruna zemin tutunma kaybı "
        "çarpanı olarak yansıtılmıştır.")

    add_heading_styled(doc,
        "2.2. Mekansal Kümeleme, Yol Hiyerarşisi ve Hız Modeli", level=2)
    add_body_p(doc,
        f"{n_raw:,} ham kusur kaydı, 30 metrelik yarıçap içinde aynı türden "
        f"kümelenerek {n_total:,} tekil tehlike bölgesine indirgenmiştir. Her "
        f"nokta dört kademeli yol hiyerarşisine atanmıştır:",
        bold_prefix="• Kademeli Hiyerarşi: ")
    add_body_p(doc,
        "1. Ana Arter / Otoyol (motorway, trunk, primary, bulvar/çevre yolu): "
        "kanuni hız sınıfı — motorway 120, trunk 90, primary 70 km/s.")
    add_body_p(doc,
        "2. Toplayıcı Cadde (secondary, tertiary, cadde): kanuni hız — "
        "secondary 70, tertiary 60 km/s.")
    add_body_p(doc,
        "3. Ara Sokak (residential, unclassified, service): kanuni hız — "
        "residential 50, unclassified 40, service 40 km/s (yerleşim yeri içi sınır).")
    add_body_p(doc,
        "4. Kritik Dar Boğaz / Çıkmaz (W ≤ 3.5 m, çıkmaz, dönüş cebi): "
        "manevra kısıtı; hız yol sınıfının kanuni sınırında kalır "
        "(living_street 30, pedestrian 10 km/s).")

    add_heading_styled(doc,
        "2.3. Yol Güvenliği Risk Skoru (YGE 0-100) Formülasyonu", level=2)
    add_body_p(doc,
        "AASHTO ve KGM standartlarına göre normalize edilen Yol Güvenliği "
        "Risk Endeksi (0-100), geometrik kusurun şiddeti, yol hiyerarşisi ve "
        "işletme hızının birleşimi üzerinden hesaplanmıştır:")
    add_callout(doc,
        "• ANA ARTERLERDE RİSK = Kanuni Hız (motorway 120 / trunk 90 / "
        "primary 70 km/s) × Geometrik Kusur "
        "(R ≤ 75 m / θ ≤ 45°) → Savrulma, Devrilme ve Görüş Mesafesi Kaybı\n"
        "• ARA SOKAKLARDA RİSK = Geometrik İmkansızlık (W ≤ 3.5 m / çıkmaz) "
        "× Acil Müdahale Engeli → İtfaiye/Ambulans Giriş Kısıtı\n\n"
        "Virajda denge hızı V = √(127·f·R), f = 0.28 (AASHTO) hesaplanır; "
        "yol hızı ile denge hızı arasındaki fark risk skoruna eklenir.\n\n"
        "Sınıflandırma: ≥ 75: KRİTİK KARA NOKTA | 55-74: YÜKSEK RİSK | "
        "35-54: ORTA RİSK | < 35: DÜŞÜK RİSK",
        title="YOL GÜVENLİĞİ RİSK SKORU (YGE) HESAPLAMA MODELİ")

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 3: KUSUR TÜRLERİ DETAYLI ANALİZ
    # -------------------------------------------------------------
    add_heading_styled(doc,
        "3. GEOMETRİK VE AĞ KUSURLARI DETAYLI ANALİZİ", level=1)

    def kind_stat(k):
        s = df_ic[df_ic.kind == k]
        return len(s), s

    n_kurp, s_kurp = kind_stat("KURP")
    n_gen, s_gen = kind_stat("GENISLIK")
    n_kav, s_kav = kind_stat("KAVSAK_ACISI")
    n_cik, s_cik = kind_stat("CIKMAZ_SOKAK")
    n_don, s_don = kind_stat("DONUS_CEBI")
    n_eg, s_eg = kind_stat("EGIM")

    add_heading_styled(doc, "3.1. Keskin Virajlar (R ≤ 75 m)", level=2)
    r_le15 = int((s_kurp.val <= 15).sum())
    r_1530 = int(((s_kurp.val > 15) & (s_kurp.val <= 30)).sum())
    add_body_p(doc,
        f"Ankara içi bölgede {n_kurp:,} adet keskin viraj noktası tespit "
        f"edilmiştir; viraj yarıçapı medyanı {s_kurp.val.median():.1f} m'dir. "
        f"KGM/AASHTO standartlarına göre toplayıcı arterlerde minimum kurp "
        f"yarıçapı tasarım hızına bağlı olarak 80-150 m aralığında olmalıdır.",
        bold_prefix="• Standart ve Risk Değerlendirmesi: ")
    add_body_p(doc,
        f"1. Saç Tokası / Kritik Viraj (R ≤ 15 m): {r_le15:,} noktada "
        f"tespit edilmiştir. Otobüs ve ağır vasıtaların dönüşte karşı şeridi "
        f"ihlal ettiği, yüksek merkezkaç kuvveti nedeniyle devrilme riski "
        f"taşır.")
    add_body_p(doc,
        f"2. Dar Viraj (15 m < R ≤ 30 m): {r_1530:,} noktada sürücü viraj "
        f"apeksinde şerit tutturamaz; kafa kafaya çarpışma tehlikesi yüksektir.")

    add_heading_styled(doc,
        "3.2. Dar Kesit ve Şişe Boyunları (W ≤ 5.5 m)", level=2)
    w_le32 = int((s_gen.val <= 3.2).sum())
    add_body_p(doc,
        f"{n_gen:,} noktada yol genişliğinin 5.5 metrenin altında olduğu "
        f"tespit edilmiştir (medyan W = {s_gen.val.median():.1f} m). "
        f"Çift yönlü kentsel trafik için asgari platform genişliği 6.50-7.00 m "
        f"olmalıdır.",
        bold_prefix="• Standart ve Risk Değerlendirmesi: ")
    add_body_p(doc,
        f"1. Kritik Şişe Boyunu (W ≤ 3.2 m): {w_le32:,} noktada tek bir "
        f"itfaiye veya ambulans aracının bile sığamadığı, parklanma durumunda "
        f"yolun tamamen kilitlendiği koridorlar mevcuttur.")
    add_body_p(doc,
        "2. Yetersiz Geçiş (3.2 m < W ≤ 5.5 m): İki binek aracın yan yana "
        "geçemediği, yandan sürtünme ve ayna çarpması kazalarının "
        "yoğunlaştığı alanlardır.")

    add_heading_styled(doc,
        "3.3. Dar Açılı Kör Kavşaklar (θ ≤ 45°) ve Çıkmaz Sokaklar", level=2)
    add_body_p(doc,
        f"OSM topolojik analizinde {n_kav:,} adet dar açılı kavşak kolu "
        f"(θ ≤ 45°) belirlenmiştir. Bu kollarda sürücünün boyun çevirme "
        f"açısının ötesinde kör nokta oluşur; ana yola katılımda açılı "
        f"çarpışma riski yüksektir. Ayrıca {n_cik:,} adet önemli çıkmaz "
        f"sokakta acil durum araçlarının dönmesini sağlayacak manevra alanı "
        f"bulunmamaktadır.")
    add_body_p(doc,
        f"Manevra kısıtı olan {n_don:,} adet dönüş cebi noktası ise büyük "
        f"araçların U dönüşü yapamadığı dar adalar olarak modellenmiştir.")

    add_heading_styled(doc,
        "3.4. Dik Boyuna Eğim Kesimleri (g ≥ %8)", level=2)
    if n_eg:
        add_body_p(doc,
            f"Copernicus DEM GLO-30 yükseklik modelinden türetilen boyuna "
            f"profilde {n_eg:,} kesimde eğim %8 ve üzerinde hesaplanmıştır "
            f"(medyan %{s_eg.val.median():.1f}, en dik %{s_eg.val.max():.1f}). "
            f"KGM geometrik standartlarına göre %6-8 aralığı kritik rampa "
            f"eşiğidir; bu eşik aşıldığında ağır vasıtalarda fren mesafesi "
            f"belirgin şekilde artar, ıslak/karlı zeminde tutunma kaybı ve "
            f"viraj içinde savrulma riski yükselir.",
            bold_prefix="• Standart ve Risk Değerlendirmesi: ")
        add_body_p(doc,
            f"1. İniş eğimli kesimler ({int((s_eg.yon=='iniş').sum()):,} kesim): "
            f"Uzun inişlerde fren kaybı (fading) ve kaçış rampası ihtiyacı "
            f"doğar; ağır vasıta trafiği olan arterlerde önceliklidir.")
        add_body_p(doc,
            f"2. Yokuş eğimli kesimler ({int((s_eg.yon=='yokuş').sum()):,} kesim): "
            f"Yavaş seyreden ağır araçlar nedeniyle hız farkı ve arkadan "
            f"çarpma riski artar; tırmanma şeridi ve sollama yasağı "
            f"değerlendirilmelidir.")
        add_body_p(doc,
            f"3. Eğim kırılması yüksek kesimler: Görüş mesafesinin aniden "
            f"kısaldığı tepe üstü/çukur geçişlerde uyarı tabelası ve hız "
            f"yönetimi uygulanmalıdır.")

    add_figure(doc, "07_egim_analizi.png",
               "Şekil 3.3: Eğim–risk ilişkisi ve dik boyuna eğim kesimlerinin "
               "dağılımı (Copernicus DEM GLO-30).")

    add_figure(doc, "04_hiz_vs_geometri_matrisi.png",
               "Şekil 3.1: İşletme hızı ile kurp yarıçapı / kavşak açısı "
               "arasındaki risk korelasyonu.")
    add_figure(doc, "06_ana_arter_hiz_dagilimi.png",
               "Şekil 3.2: Ana arterlerde hız bandına göre kusur riski.")

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 4: İLÇE BAZLI DEĞERLENDİRME
    # -------------------------------------------------------------
    add_heading_styled(doc,
        f"4. İLÇE BAZLI YOL GÜVENLİĞİ DEĞERLENDİRMESİ ({n_ilce} İLÇE)",
        level=1)

    add_body_p(doc,
        "Ankara'nın ilçeleri yol uzunluğu, topoğrafya, yerleşim yoğunluğu ve "
        "yol standardı açısından belirgin farklılıklar göstermektedir. "
        "Aşağıdaki tabloda tüm ilçelerin kusur ve risk dökümü sunulmuştur.")

    add_figure(doc, "02_en_riskli_15_ilce.png",
               "Şekil 4.1: En yüksek kritik kara nokta yoğunluğuna sahip "
               "15 ilçe sıralaması.")

    ilce_table_data = []
    for _, r in df_ilce_ic.iterrows():
        ilce_table_data.append([
            r["ilce"],
            f"{int(r['toplam_kusur']):,}",
            f"{int(r['kritik_kara_nokta']):,}",
            f"{int(r['yuksek_risk']):,}",
            f"{int(r['ana_arter_kusur']):,}",
            f"{int(r['kurp_kusuru']):,}",
            f"{int(r['dar_kesit']):,}",
            f"{int(r['dar_kavsak']):,}",
            f"{float(r['ortalama_risk']):.1f}",
        ])

    build_table(doc,
        ["İlçe", "Toplam Kusur", "Kritik Kara Nokta", "Yüksek Risk",
         "Ana Arter", "Keskin Viraj", "Dar Kesit", "Dar Kavşak", "Ort. Risk"],
        ilce_table_data,
        [Cm(2.9), Cm(1.9), Cm(2.1), Cm(1.8), Cm(1.6), Cm(1.7), Cm(1.6),
         Cm(1.6), Cm(1.4)],
        align_right_cols=[1, 2, 3, 4, 5, 6, 7, 8])

    add_figure(doc, "05_ilce_kusur_kompozisyonu.png",
               "Şekil 4.2: İlçeler bazında kusur türlerinin yapısal dağılımı.")

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 5: XY KOORDINATLI PROBLEMLI NOKTALAR
    # -------------------------------------------------------------
    add_heading_styled(doc,
        "5. XY KOORDİNATLI PROBLEMLİ NOKTALAR (KARA NOKTALARI)", level=1)

    add_body_p(doc,
        "Aşağıdaki tablo, risk skoru en yüksek 25 problemlı noktayı UTM 36N "
        "(EPSG:32636) metre cinsinden X/Y ve WGS84 coğrafi (lon/lat) "
        "koordinatlarıyla listelemektedir. Koordinatlar saha ekipleri, "
        "CBS katmanları ve iş emri sistemleri için doğrudan kullanılabilir. "
        "Tüm kritik noktaların tamamı Excel raporunda "
        "`Top1000_Kritik_Kara_Nokta` sayfasında yer almaktadır.",
        bold_prefix="• Kullanım Amacı: ")

    top25 = df_bs.head(25)
    top25_data = []
    for i, (_, r) in enumerate(top25.iterrows(), 1):
        name = (str(r["name"]) if pd.notna(r["name"]) and str(r["name"]).strip()
                else "İsimsiz Aks")
        top25_data.append([
            i, r["ilce"], name[:20],
            KIND_LABELS.get(r["kind"], r["kind"])[:26],
            f"{float(r['val']):.1f}",
            f"{float(r['yol_hizi_kmh']):.0f}",
            f"{float(r['risk_skoru']):.1f}",
            f"{r['x']:,.0f} / {r['y']:,.0f}",
            f"{r['lon']:.5f} / {r['lat']:.5f}",
        ])

    build_table(doc,
        ["#", "İlçe", "Yol Adı", "Kusur Türü", "Değer", "Hız", "Risk",
         "X / Y (m, UTM 36N)", "Lon / Lat (WGS84)"],
        top25_data,
        [Cm(0.7), Cm(2.0), Cm(2.2), Cm(2.7), Cm(1.3), Cm(1.1), Cm(1.1),
         Cm(3.0), Cm(2.9)],
        align_right_cols=[4, 5, 6])

    # Kritik ana arter noktalari
    art_crit = df_ic[(df_ic.risk_seviyesi == "Kritik Kara Nokta") &
                     (df_ic.yol_hiyerarsisi == "Ana Arter")].head(15)
    add_heading_styled(doc,
        "5.1. Ana Arterlerdeki Kritik Noktalar (Hız × Geometri Çakışması)",
        level=2)
    add_body_p(doc,
        "Ana arterlerde işletme hızı yüksek olduğu için geometrik kusurların "
        "kaza riski katlanarak artar. Aşağıdaki 15 nokta, hız-kurp "
        "uyumsuzluğunun (hiz_kurp_fark_kmh) en yoğun olduğu kritik "
        "kavşak/viraj bölgeleridir:")

    art_data = []
    for i, (_, r) in enumerate(art_crit.iterrows(), 1):
        name = (str(r["name"]) if pd.notna(r["name"]) and str(r["name"]).strip()
                else "İsimsiz Aks")
        gap = r["hiz_kurp_fark_kmh"]
        art_data.append([
            i, r["ilce"], name[:20],
            KIND_LABELS.get(r["kind"], r["kind"])[:26],
            f"{float(r['yol_hizi_kmh']):.0f}",
            f"{float(r['kurp_guvenli_hiz_kmh']) if pd.notna(r['kurp_guvenli_hiz_kmh']) else 0:.0f}",
            f"{float(gap) if pd.notna(gap) else 0:.0f}",
            f"{float(r['risk_skoru']):.1f}",
            f"{r['x']:,.0f} / {r['y']:,.0f}",
        ])

    build_table(doc,
        ["#", "İlçe", "Yol Adı", "Kusur Türü", "Yol Hızı",
         "Güvenli Hız", "Fark", "Risk", "X / Y (m, UTM 36N)"],
        art_data,
        [Cm(0.7), Cm(2.2), Cm(2.4), Cm(2.7), Cm(1.5), Cm(1.5), Cm(1.2),
         Cm(1.1), Cm(3.0)],
        align_right_cols=[4, 5, 6, 7])

    n_gap40 = int((df_ic.hiz_kurp_fark_kmh > 40).sum())
    add_callout(doc,
        f"Ankara genelinde yol hızı ile viraj denge hızı arasındaki fark "
        f"40 km/s'i aşan {n_gap40:,} nokta bulunmaktadır. Bu bölgelerde "
        f"sürücü, viraja yasal hızla girdiğinde fiziksel olarak savrulma "
        f"eşiğini aşar; hız düşürme, kenar şeridi, uyarı tabelası ve "
        f"aydınlatma gibi hızlı önlemlerle önceliklendirilmelidir.",
        title="HIZ - KURP UYUMSUZLUĞU TESPİTİ")

    # Excel dosya bilgisi
    add_body_p(doc,
        f"XY koordinatlı tüm problemlı noktalar ({n_total:,} kayıt) şu Excel "
        "sayfalarında yer almaktadır: Yonetici_Ozeti, Ilce_Dagilimi, "
        "Ana_Arter_Hiz_Riski, Top1000_Kritik_Kara_Nokta, Keskin_Virajlar, "
        "Dar_Kesitler_Sise_Boynu, Dar_Acili_Kavsaklar, Cikmaz_Sokaklar. "
        "Her kayıt `x`, `y` (UTM 36N), `lon`, `lat` (WGS84) ve `osm_id` "
        "sütunlarını içerir.")

    doc.add_page_break()

    # -------------------------------------------------------------
    # BÖLÜM 6: SINIRLAMALAR
    # -------------------------------------------------------------
    add_heading_styled(doc, "6. ANALİZ SINIRLAMALARI", level=1)
    add_body_p(doc,
        "1. Boyuna eğim Copernicus DEM GLO-30 (30 m) yüzey modelinden "
        "türetilmiştir; köprü/alt geçit, tünel ve bina gölgeli kesimlerde yerel "
        "sapmalar olabilir. Eğim 90 m pencerede hesaplanarak gürültü "
        "azaltılmıştır; 1/1000 ölçekli proje için DGN kotlarıyla doğrulama "
        "önerilir.")
    add_body_p(doc,
        "2. Gerçek trafik hacmi verisi kullanılmamıştır — sensör bulunmadığından "
        "hacim çarpanı (S_hacim) yoktur; yoğunluk yerine yol sınıfı "
        "hiyerarşisi dolaylı gösterge olarak kullanılmıştır.")
    add_body_p(doc,
        "3. DEM çözünürlüğü 30 m'dir; 30 m'den kısa yerel eğim değişimleri "
        "(kasis, hendek, köprü rampası) modellenemez.")
    add_body_p(doc,
        "4. Genişlik etiketleri kısmidir — OSM'de `width`/`lanes` etiketi "
        "olmayan yollarda sınıf varsayımı devreye girer (kaynak sütunu "
        "`kaynak` ile izlenebilir).")
    add_body_p(doc,
        "5. Hızlar yol sınıfına göre kanuni sınırlardır (motorway 120, trunk 90, "
        "primary/secondary 70, tertiary 60, residential 50 km/s) — OSM "
        "`maxspeed` etiketi kullanılmamıştır; ölçüm hızı değildir, tasarım/"
        "güvenlik analizi için üst sınır kabul edilmiştir.")
    add_body_p(doc,
        "6. Kavşak açıları OSM topolojisine dayanır — çift yol / ayrı "
        "carrefour geometrisi kavşakları ayrı düğümler olarak "
        "modellenebilir.")

    # -------------------------------------------------------------
    # BÖLÜM 7: SONUÇ VE ÖNERİLER
    # -------------------------------------------------------------
    add_heading_styled(doc, "7. SONUÇ VE EYLEM ÖNERİLERİ", level=1)

    ilk3 = df_ilce_ic.head(3)["ilce"].tolist()
    add_body_p(doc,
        f"• Öncelik 1: {', '.join(ilk3)} ilçelerinde kritik noktaların "
        f"yoğunlaşması, bu ilçelerde yüksek hızlı arter ile keskin viraj / dar "
        f"açılı kavşak bileşiminin yoğun olduğunu gösterir. Bu üç ilçede "
        f"saha doğrulaması (vidyo/kaza kaydı) ilk olarak yapılmalıdır.")

    add_heading_styled(doc, "7.1. Kısa Vadeli (0 - 6 Ay)", level=2)
    add_body_p(doc,
        "1. R ≤ 30 m olan tüm virajlarda reflektif viraj yön levhaları "
        "(T-33a/b) ve hız tahdit levhaları tesis edilmelidir.")
    add_body_p(doc,
        "2. θ ≤ 45° olan kavşak kollarında kör nokta güvenlik aynaları "
        "monte edilmeli, görüş üçgeni ağaç/bina engellerinden temizlenmelidir.")
    add_body_p(doc,
        "3. W ≤ 4.5 m olan çift yönlü dar sokaklar tek yöne çevrilmeli, "
        "karşılıklı kilitlenmeler önlenmelidir.")
    add_body_p(doc,
        f"4. Hız-kurp farkı 40 km/s'i aşan {n_gap40:,} noktaya optik hız "
        f"kesici çizgiler ve transvers termoplastik uyarı çizgileri "
        f"çekilmelidir.")
    add_body_p(doc,
        "5. Dik eğimli (%8+) iniş kesimlerinde fren kaybına karşı ağır vasıta "
        "hız denetimi, motor freni uyarı levhası ve kaçış rampası "
        "değerlendirilmelidir; yokuş kesimlerinde tırmanma şeridi "
        "planlanmalıdır.")

    add_heading_styled(doc, "7.2. Orta Vadeli (6 - 24 Ay)", level=2)
    add_body_p(doc,
        "1. Keskin virajlarda KGM standartlarına uygun %6-%8 ters dever "
        "verilerek merkezkaç kuvveti dengelenmelidir.")
    add_body_p(doc,
        "2. Şişe boyunlarında kaçak yapı tecavüzleri ve köşe çıkıntıları "
        "kamulaştırılarak yol genişliği minimum 6.00 m'ye çıkarılmalıdır.")
    add_body_p(doc,
        "3. Uzun çıkmaz sokakların sonuna asgari 12 m çapında itfaiye/"
        "çöp kamyonu manevra çemberleri inşa edilmelidir.")

    add_heading_styled(doc, "7.3. Uzun Vadeli (2 - 5 Yıl)", level=2)
    add_body_p(doc,
        "1. Eğim modülü Copernicus DEM GLO-30 ile devreye alınmıştır; 1/1000 "
        "DGN kotları ve saha ölçümleriyle doğrulanarak eğim kırılması "
        "(Δ) eşikleri ilçe bazında kalibre edilmelidir.")
    add_body_p(doc,
        f"2. Üretilen {n_total:,} noktalık XY koordinatlı veri tabanı, Büyükşehir "
        "Belediyesi CBS ve Yol Bakım Dairesi altyapısına dinamik 'Yol Kusur "
        "İzleme Platformu' olarak entegre edilmelidir.")
    add_body_p(doc,
        "3. Kritik kara noktalarında kaza istatistikleri (EGM/KGM) ile "
        "korele edilerek model doğrulaması ve önceliklendirme iyileştirilmelidir.")

    # Ek cikti bilgisi
    add_heading_styled(doc, "7.4. Üretilen Çıktılar", level=2)
    build_table(doc, ["Çıktı", "Dosya Adı"],
                [                 ["Excel Raporu (9 sayfa, XY + kot/eğim)",
                  "Ankara_OSM_Yol_Guvenligi_Raporu.xlsx"],
                 ["Word Raporu (bu belge)",
                  "Ankara_Yol_Guvenligi_ve_Kusur_Analizi_Raporu.docx"],
                 ["İnteraktif Kara Nokta Haritası (Folium)",
                  "Ankara_OSM_Kara_Noktalar_Harita.html"],
                 ["Esri Tabanlı Kusur Haritası (açılır/kapanır panel)",
                  "Ankara_OSM_Kusurlar_Esri_Harita.html"],
                 ["Markdown Analiz Özeti",
                  "Ankara_OSM_Yol_Guvenligi_Raporu.md"],
                 ["Ham Veri (tüm kusurlar, XY + lon/lat)",
                  "Ankara_OSM_Tum_Kusurlar.csv"],
                 ["Öncelikli Kara Noktalar",
                  "Ankara_OSM_Kara_Noktalar_Oncelikli.csv"],
                 ["İlçe Özeti", "Ankara_OSM_Ilce_Ozeti.csv"],
                 ["Dik Eğim Kesimleri (DEM)",
                  "Excel: Dik_Egim_Kesimleri sayfası"],
                 ["Yükseklik / Eğim Rasterleri",
                  "dem_ankara.tif, dem_ankara_utm.tif, egim_ankara_utm.tif"],
                 ["Grafikler (7 adet, 300 dpi)", "rapor_gorselleri/*.png"]],
                [Cm(7.0), Cm(9.5)])

    doc.add_paragraph().paragraph_format.space_before = Pt(16)
    add_body_p(doc,
        "Bu teknik rapor, Ankara yol altyapısının geometrik güvenliğinin "
        "artırılması ve can/mal kayıplarının sıfıra indirilmesi (Vision Zero) "
        "hedefi doğrultusunda, yalnızca OpenStreetMap verisiyle "
        "hazırlanmıştır. Sahada doğrulama sonrası nihai yatırım programı "
        "çıkarılmalıdır.",
        bold_prefix="DENETİM VE ONAY: ")

    print(f"Rapor kaydediliyor: {OUT_DOCX}...", flush=True)
    doc.save(OUT_DOCX)
    print(f"   -> {OUT_DOCX} basariyla olusturuldu.")
    print(f"Word raporu uretimi tamamlandi. Sure: {time.time()-t0:.1f} sn.")


if __name__ == "__main__":
    main()
