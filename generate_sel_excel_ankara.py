# -*- coding: utf-8 -*-
"""
generate_sel_excel_ankara.py
Ankara alt gecit / sel riski analizi icin cok sayfali Excel calisma kitabi.
"""
import os
import time

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.formatting.rule import CellIsRule, FormulaRule

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_GECIT = os.path.join(BASE, "Ankara_OSM_Alt_Gecitler.csv")
CSV_NOKTA = os.path.join(BASE, "Ankara_OSM_Sel_Riskli_Noktalar.csv")
CSV_ILCE = os.path.join(BASE, "Ankara_OSM_Sel_Ilce_Ozeti.csv")
OUT = os.path.join(BASE, "Ankara_Alt_Gecit_Sel_Analizi.xlsx")

NAVY = "1B365D"
RED = "C0392B"
LIGHT = "F2F4F7"
WHITE = "FFFFFF"
LEVEL_FILL = {
    "Çok Yüksek": "F5B7B1",
    "Yüksek": "FAD7A0",
    "Orta": "FCF3CF",
    "Düşük": "D5F5E3",
    "Çok Düşük": "EAEDED",
}

THIN = Side(style="thin", color="D5DBDB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, row, ncols, height=30):
    ws.row_dimensions[row].height = height
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER


def title_block(ws, title, subtitle, ncols):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    c = ws.cell(row=1, column=1, value=title)
    c.font = Font(name="Arial", size=16, bold=True, color=NAVY)
    c.alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    c = ws.cell(row=2, column=1, value=subtitle)
    c.font = Font(name="Calibri", size=9.5, italic=True, color="7F8C8D")
    c.alignment = Alignment(vertical="center")
    ws.row_dimensions[2].height = 20


def write_table(ws, df, start_row, start_col=1, name=None, widths=None,
                level_col=None, num_formats=None):
    headers = [str(c) for c in df.columns]
    for j, h in enumerate(headers, start_col):
        ws.cell(row=start_row, column=j, value=h)
    style_header(ws, start_row, len(headers) + start_col - 1)

    for i, row in enumerate(df.itertuples(index=False), 1):
        for j, val in enumerate(row, start_col):
            if isinstance(val, float) and pd.isna(val):
                val = None
            cell = ws.cell(row=start_row + i, column=j, value=val)
            cell.font = Font(name="Calibri", size=9.5)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center")
            if i % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="FBFCFD")

    end_row = start_row + len(df)
    if name:
        ref = f"A{start_row}:{get_column_letter(len(headers) + start_col - 1)}{end_row}"
        tab = Table(displayName=name, ref=ref)
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=False)
        ws.add_table(tab)

    if level_col is not None:
        ci = headers.index(level_col) + start_col
        for r in range(start_row + 1, end_row + 1):
            v = ws.cell(row=r, column=ci).value
            if v in LEVEL_FILL:
                ws.cell(row=r, column=ci).fill = PatternFill("solid", fgColor=LEVEL_FILL[v])
                ws.cell(row=r, column=ci).font = Font(name="Calibri", size=9.5, bold=True)

    if widths:
        for idx, w in enumerate(widths, start_col):
            ws.column_dimensions[get_column_letter(idx)].width = w

    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if not name:
        ws.auto_filter.ref = (f"A{start_row}:"
                             f"{get_column_letter(len(headers) + start_col - 1)}{end_row}")
    return end_row


def main():
    t0 = time.time()
    df = pd.read_csv(CSV_GECIT)
    road = pd.read_csv(CSV_NOKTA)
    ilce = pd.read_csv(CSV_ILCE)
    yol = road[road["gecit_tipi"] == "Yol Kesimi"].copy()

    df["google_maps"] = df.apply(
        lambda r: f"https://www.google.com/maps/search/?api=1&query={r['lat']:.6f},{r['lon']:.6f}", axis=1)
    road["google_maps"] = road.apply(
        lambda r: f"https://www.google.com/maps/search/?api=1&query={r['lat']:.6f},{r['lon']:.6f}", axis=1)

    wb = Workbook()

    # ---------------------------------------------------------------- Özet
    ws = wb.active
    ws.title = "Özet"
    ws.sheet_view.showGridLines = False
    title_block(
        ws,
        "Ankara Alt Geçit ve Tünel Sel Riski Analizi",
        "OpenStreetMap + Copernicus DEM GLO-30 · 28 Kasım 2026 · Saha ölçümü içermeyen ön değerlendirme",
        8)

    metrics = [
        ("Alt geçit / tünel yapısı", len(df), NAVY),
        ("Çok yüksek riskli", int((df["sel_risk_seviyesi"] == "Çok Yüksek").sum()), RED),
        ("Yüksek riskli", int((df["sel_risk_seviyesi"] == "Yüksek").sum()), "E67E22"),
        ("Ortalama skor", round(df["sel_risk_skoru"].mean(), 1), "2980B9"),
        ("Riskli yol kesimi", len(yol), NAVY),
        ("En yüksek skor", float(df["sel_risk_skoru"].max()), RED),
    ]
    r0 = 4
    for i, (label, value, color) in enumerate(metrics):
        col = 1 + (i % 3) * 2
        row = r0 + (i // 3) * 3
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        c = ws.cell(row=row, column=col, value=value)
        c.font = Font(name="Arial", size=20, bold=True, color=color)
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
        c = ws.cell(row=row + 1, column=col, value=label)
        c.font = Font(name="Calibri", size=9, color="566573")
        c.alignment = Alignment(horizontal="center")

    # Seviye dağılımı
    ws.cell(row=11, column=1, value="Risk seviyesi dağılımı").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    dist = (df["sel_risk_seviyesi"].value_counts()
            .reindex(["Çok Yüksek", "Yüksek", "Orta", "Düşük", "Çok Düşük"]).fillna(0).astype(int))
    ws.cell(row=12, column=1, value="Seviye")
    ws.cell(row=12, column=2, value="Yapı")
    ws.cell(row=12, column=3, value="Oran")
    style_header(ws, 12, 3, height=22)
    for i, (lvl, n) in enumerate(dist.items(), 1):
        r = 12 + i
        ws.cell(row=r, column=1, value=lvl).fill = PatternFill("solid", fgColor=LEVEL_FILL[lvl])
        ws.cell(row=r, column=2, value=int(n)).alignment = Alignment(horizontal="right")
        pc = ws.cell(row=r, column=3, value=n / len(df))
        pc.number_format = "0.0%"
        for c in range(1, 4):
            ws.cell(row=r, column=c).border = BORDER
            ws.cell(row=r, column=c).font = Font(name="Calibri", size=9.5)

    # İlçe tablosu
    ws.cell(row=11, column=5, value="İlçe özeti").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    ilce_t = ilce.sort_values("alt_gecit_sayisi", ascending=False)
    hdrs = ["İlçe", "Yapı", "Çok Yüksek", "Yüksek", "Ort. skor", "Maks. skor"]
    for j, h in enumerate(hdrs, 5):
        ws.cell(row=12, column=j, value=h)
    style_header(ws, 12, 8, height=22)
    for i, row in enumerate(ilce_t.itertuples(), 1):
        r = 12 + i
        vals = [row.ilce, int(row.alt_gecit_sayisi), int(row.cok_yuksek), int(row.yuksek),
                round(row.ortalama_risk, 1), round(row.maksimum_risk, 1)]
        for j, v in enumerate(vals, 5):
            c = ws.cell(row=r, column=j, value=v)
            c.font = Font(name="Calibri", size=9.5)
            c.border = BORDER
            if j > 5:
                c.alignment = Alignment(horizontal="right")

    r_notes = 22
    ws.cell(row=r_notes, column=1, value="Skor bileşenleri (0-100)").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    notes = [
        "Çukur derinliği (0-25): yapının çevresine göre çukurda kalma derecesi",
        "Akış birikimi (0-25): memba havzasında toplanan efektif drenaj alanı",
        "Havza derinliği (0-12): yapının bulunduğu çanağın derinliği",
        "Memba eğimi (0-12): üst havuz eğimi, yüzeysel akış hızı",
        "Dere yakınlığı (0-10): en yakın su yoluna mesafe",
        "Maruziyet (0-16): yol sınıfı, uzunluk, yaya/araç kullanımı",
    ]
    for i, n in enumerate(notes, 1):
        c = ws.cell(row=r_notes + i, column=1, value="• " + n)
        c.font = Font(name="Calibri", size=9.5, color="2C3E50")

    ws.cell(row=r_notes + len(notes) + 2, column=1,
            value="Canlı harita: https://darkeaglehome.github.io/ankara-yol-guvenligi/"
                  "Ankara_OSM_Alt_Gecit_Sel_Harita.html").font = Font(
        name="Calibri", size=9.5, color="2980B9", underline="single")

    for col, w in zip("ABCDEFGH", [22, 12, 12, 11, 15, 12, 12, 12]):
        ws.column_dimensions[col].width = w

    # ------------------------------------------------- Alt Geçit Envanteri
    ws2 = wb.create_sheet("Alt Geçit Envanteri")
    ws2.sheet_view.showGridLines = False
    title_block(ws2, "Alt Geçit / Tünel Envanteri",
                f"{len(df)} yapı · öncelik sıralı · koordinatlar UTM 36N ve WGS84", 5)
    cols = ["oncelik", "yapi_id", "gecit_tipi", "ad", "ilce", "yol_sinifi", "durum",
            "uzunluk_m", "kot_min_m", "kot_max_m", "cukur_derinligi_m", "havza_derinligi_m",
            "akim_birikim_ha", "memba_egimi_yuzde", "dere_mesafe_m", "dere_tipi", "dere_adi",
            "aydinlatma", "maxheight", "sel_risk_skoru", "sel_risk_seviyesi",
            "x", "y", "lon", "lat", "google_maps"]
    d2 = df[cols].copy()
    d2.columns = ["Öncelik", "Yapı ID", "Tip", "Ad", "İlçe", "Yol sınıfı", "Durum",
                  "Uzunluk (m)", "Min kot (m)", "Maks kot (m)", "Çukur (m)", "Havza der. (m)",
                  "Akım (ha)", "Memba eğimi (%)", "Dere mes. (m)", "Dere tipi", "Dere adı",
                  "Aydınlatma", "Maxheight", "Skor", "Seviye",
                  "X (UTM)", "Y (UTM)", "lon", "lat", "Google Maps"]
    end2 = write_table(ws2, d2, 4, name="AltGecitEnvanteri",
                       widths=[8, 9, 20, 30, 12, 11, 10, 11, 11, 11, 10, 12, 10, 13, 12,
                               10, 20, 11, 10, 8, 12, 11, 12, 11, 11, 55],
                       level_col="Seviye")
    for r in range(5, end2 + 1):
        ws2.cell(row=r, column=26).hyperlink = ws2.cell(row=r, column=26).value
        ws2.cell(row=r, column=26).font = Font(name="Calibri", size=9, color="2980B9", underline="single")
        for c in (20,):
            ws2.cell(row=r, column=c).font = Font(name="Calibri", size=9.5, bold=True)

    # -------------------------------------------------- Sel Riskli Noktalar
    ws3 = wb.create_sheet("Sel Riskli Noktalar")
    ws3.sheet_view.showGridLines = False
    title_block(ws3, "Sel Riskli Noktalar (Yapılar + Yol Kesimleri)",
                f"{len(road)} kayıt · {len(yol)} yol kesimi + "
                f"{len(road) - len(yol)} alt geçit yapısı · skora göre azalan", 5)
    cols3 = ["yapi_id", "gecit_tipi", "ad", "ilce", "yol_sinifi", "cukur_derinligi_m",
             "havza_derinligi_m", "akim_birikim_ha", "memba_egimi_yuzde", "dere_mesafe_m",
             "dere_tipi", "dere_adi", "yerel_rolyef_m", "kentsel_mi", "yogunluk_500m",
             "sel_risk_skoru", "sel_risk_seviyesi", "lon", "lat", "google_maps"]
    d3 = road[cols3].copy()
    d3.columns = ["ID", "Tip", "Ad", "İlçe", "Yol sınıfı", "Çukur (m)", "Havza der. (m)",
                  "Akım (ha)", "Memba eğimi (%)", "Dere mes. (m)", "Dere tipi", "Dere adı",
                  "Yerel rölyef (m)", "Kentsel", "Yoğunluk (500 m)", "Skor", "Seviye",
                  "lon", "lat", "Google Maps"]
    d3["Kentsel"] = d3["Kentsel"].map({True: "Evet", False: "Hayır"})
    end3 = write_table(ws3, d3, 4, name="SelRiskliNoktalar",
                       widths=[10, 20, 28, 12, 11, 10, 12, 10, 13, 12, 10, 20, 13, 9, 14,
                               8, 12, 11, 11, 55],
                       level_col="Seviye")
    for r in range(5, end3 + 1):
        ws3.cell(row=r, column=20).hyperlink = ws3.cell(row=r, column=20).value
        ws3.cell(row=r, column=20).font = Font(name="Calibri", size=9, color="2980B9", underline="single")
        ws3.cell(row=r, column=16).font = Font(name="Calibri", size=9.5, bold=True)

    # ----------------------------------------------------------- İlçe Özet
    ws4 = wb.create_sheet("İlçe Özeti")
    ws4.sheet_view.showGridLines = False
    title_block(ws4, "İlçe Bazında Sel Riski Özeti",
                "Ortalama ve maksimum skorlar, çukur derinliği ve akış birikimi ortalamaları", 8)
    d4 = ilce.rename(columns={
        "ilce": "İlçe", "alt_gecit_sayisi": "Yapı", "cok_yuksek": "Çok Yüksek",
        "yuksek": "Yüksek", "orta": "Orta", "ortalama_risk": "Ort. skor",
        "maksimum_risk": "Maks. skor", "ortalama_cukur_m": "Ort. çukur (m)",
        "ortalama_akim_ha": "Ort. akım (ha)"})
    end4 = write_table(ws4, d4.sort_values("Ort. skor", ascending=False), 4,
                       name="IlceOzet", widths=[16, 9, 12, 9, 9, 11, 11, 14, 14])
    for c in range(2, 10):
        for r in range(5, end4 + 1):
            ws4.cell(row=r, column=c).alignment = Alignment(horizontal="right")
    ws4.conditional_formatting.add(
        f"F5:F{end4}", CellIsRule(operator="greaterThanOrEqual", formula=["45"],
                                  fill=PatternFill("solid", fgColor="F5B7B1")))
    ws4.conditional_formatting.add(
        f"F5:F{end4}", CellIsRule(operator="between", formula=["30", "44.99"],
                                  fill=PatternFill("solid", fgColor="FAD7A0")))

    # ----------------------------------------------------------- Metodoloji
    ws5 = wb.create_sheet("Metodoloji")
    ws5.sheet_view.showGridLines = False
    title_block(ws5, "Metodoloji ve Sınırlamalar",
                "Skor ağırlıkları, seviye eşikleri ve veri kaynakları", 5)

    ws5.cell(row=4, column=1, value="Sel Risk Skoru bileşenleri").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    comp = pd.DataFrame([
        ["Çukur derinliği", "0-25", "Yapı kotu ile çevresindeki drenaj çıkış kotu farkı"],
        ["Akış birikimi", "0-25", "Memba havzasında toplanan efektif drenaj alanı (ha)"],
        ["Havza derinliği", "0-12", "Yapının bulunduğu çanağın derinliği"],
        ["Memba eğimi", "0-12", "Üst havuzun ortalama eğimi (%)"],
        ["Dere yakınlığı", "0-10", "En yakın su yoluna mesafe (m)"],
        ["Maruziyet", "0-16", "Yol sınıfı, uzunluk, yaya/araç kullanımı"],
    ], columns=["Bileşen", "Ağırlık", "Açıklama"])
    write_table(ws5, comp, 5, name="SkorBilesenleri", widths=[22, 10, 70])

    ws5.cell(row=14, column=1, value="Risk seviyeleri").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    lv = pd.DataFrame([
        ["Çok Yüksek", "70-100", "Saha ölçümü + acil drenaj/pompa projesi"],
        ["Yüksek", "55-69", "Detaylı hidrolik model + 1 yıl içinde iyileştirme"],
        ["Orta", "35-54", "Periyodik temizlik, izleme, erken uyarı"],
        ["Düşük", "20-34", "Bakım programına dahil et"],
        ["Çok Düşük", "0-19", "Rutin denetim yeterli"],
    ], columns=["Seviye", "Skor", "Önerilen aksiyon"])
    end_lv = write_table(ws5, lv, 15, name="RiskSeviyeleri", widths=[22, 10, 70],
                         level_col="Seviye")

    ws5.cell(row=end_lv + 2, column=1, value="Veri kaynakları").font = Font(
        name="Arial", size=12, bold=True, color=NAVY)
    src = [
        "OpenStreetMap Overpass API — tunnel/layer<0 etiketli 1.448 way, 5.450 su yolu",
        "Copernicus DEM GLO-30 (30 m, ESA) — UTM 36N",
        "Ankara ilçe sınırları (GeoJSON)",
        "Yöntem: Priority-Flood akış birikimi, 1,2-1,5 km pencere, 80 m yapı birleştirme",
    ]
    for i, s in enumerate(src, 1):
        ws5.cell(row=end_lv + 2 + i, column=1, value="• " + s).font = Font(
            name="Calibri", size=9.5)

    ws5.cell(row=end_lv + 8, column=1, value="Sınırlamalar").font = Font(
        name="Arial", size=12, bold=True, color=RED)
    lims = [
        "DEM dikey doğruluğu birkaç metre; kesin kot için saha ölçümü gerekir.",
        "OSM etiketleri eksik/hatalı olabilir; envanter buna bağlıdır.",
        "Model statik drenaj alanına dayanır; tasarım yağışı senaryosu içermez.",
        "Mevcut yağmur suyu hattı, pompa ve menfez kapasitesi veri setinde yoktur.",
    ]
    for i, s in enumerate(lims, 1):
        ws5.cell(row=end_lv + 8 + i, column=1, value="• " + s).font = Font(
            name="Calibri", size=9.5, color="2C3E50")

    for sheet in wb.worksheets:
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0

    wb.save(OUT)
    print(f"Excel yazildi: {OUT}  ({time.time()-t0:.1f} sn)")


if __name__ == "__main__":
    main()
