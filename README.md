# Ankara Yol Güvenliği ve Geometrik Kusur Analizi

> OpenStreetMap verileriyle Ankara il sınırları içindeki yol ağının geometrik ve topolojik kusurlarını tespit eden, 98.703 tekil tehlike bölgesini YGE 0-100 risk modeli ile sınıflandıran kapsamlı analiz ve interaktif harita projesi.

---

## 🇹🇷 Türkçe

### Proje Hakkında

Bu proje, Ankara ilindeki yol ağının **geometrik ve topolojik kusurlarını** OpenStreetMap (OSM) verileri üzerinden otomatik olarak tespit eder ve risk skorlarıyla önceliklendirir. **Kazayı beklemek yerine, kazayı tetikleyen fiziksel altyapı kusurlarını önceden belirleyen proaktif bir mühendislik yaklaşımıdır.**

### Kusur Türleri

| Kusur | Açıklama | Eşik |
|-------|----------|------|
| **Keskin Viraj** | Viraj yarıçapı R ≤ 75 m | R = ds/dθ |
| **Dar Kesit** | Yol genişliği W ≤ 5.5 m | Şişe boynu |
| **Dar Açılı Kavşak** | Kavşak kol açısı θ ≤ 45° | Kör nokta |
| **Çıkmaz Sokak** | Ana yola çıkmaz sokak | Acil müdahale engeli |
| **Dönüş Cebi** | U dönüşü kısıtlı ada | Manevra kısıtı |
| **Dik Boyuna Eğim** | Eğim g ≥ %8 | DEM GLO-30 |

### Risk Skoru (YGE 0-100)

| Seviye | Skor | Renk |
|--------|------|------|
| 🔴 **Kritik Kara Nokta** | ≥ 75 | Kırmızı |
| 🟠 **Yüksek Risk** | 55-74 | Turuncu |
| 🟡 **Orta Risk** | 35-54 | Sarı |
| 🟢 **Düşük Risk** | < 35 | Yeşil |

### Veri Kaynakları

- **Yol Ağı:** OpenStreetMap (Geofabrik Turkey PBF) — 110.870 way / ~40.511 km
- **Yükseklik/Eğim:** Copernicus DEM GLO-30 (30 m, ESA)
- **Hız Modeli:** Yol sınıfına göre kanuni hız (motorway 120 → residential 50 km/s)

### Teknolojiler

- Python 3.12+, GeoPandas, Shapely, Rasterio
- Leaflet.js + ESRI World Imagery/Street/Topo/Dark
- Matplotlib, Seaborn (grafikler)
- python-docx, openpyxl (raporlar)

### Kurulum

```bash
git clone https://github.com/Darkeaglehome/ankara-yol-guvenligi.git
cd ankara-yol-guvenligi
pip install geopandas shapely rasterio numpy pandas scipy matplotlib seaborn folium pyproj openpyxl python-docx
```

### Kullanım

```bash
python aggregate_ankara.py          # Kusurları tespit et, risk skorla
python generate_word_ankara.py      # Word raporu oluştur
python generate_esri_map_ankara.py  # İnteraktif harita oluştur

python altgecit_sel_ankara.py             # Alt geçit envanteri + sel riski analizi
python generate_sel_word_ankara.py        # Sel riski Word raporu
python generate_sel_excel_ankara.py       # Sel riski Excel kitabı
python generate_sel_map_ankara.py         # İnteraktif sel riski haritası
```

### Çıktılar

| Dosya | Açıklama |
|-------|----------|
| `Ankara_OSM_Kusurlar_Esri_Harita.html` | 4 haritalı interaktif web haritası (Uydu/Sokak/Topo/Koyu) |
| `Ankara_Yol_Guvenligi_ve_Kusur_Analizi_Raporu.docx` | Kapsamlı Word raporu |
| `Ankara_OSM_Yol_Guvenligi_Raporu.xlsx` | 9 sayfalık Excel raporu |
| `Ankara_OSM_Tum_Kusurlar.csv` | 98.703 noktalık ham veri (XY + lon/lat) |

### 🚧 Alt Geçit ve Tünel Sel Riski Analizi

Aynı proje kapsamında Ankara'daki **204 alt geçit/tünel yapısı** ve şehir genelinde **400 riskli yol kesimi** su baskını açısından değerlendirildi. Envanter OpenStreetMap'in `tunnel` / `layer<0` etiketlerinden, hidrolojik model ise Copernicus DEM GLO-30'dan üretildi.

| Gösterge | Değer |
|----------|-------|
| Alt geçit / tünel yapısı | 204 (117 araç alt geçidi, 49 yaya, 22 tünel, 16 diğer) |
| Çok Yüksek / Yüksek riskli yapı | 2 / 20 |
| Taranan riskli yol kesimi | 400 (22 çok yüksek, 91 yüksek) |
| Hidrolojik referans | 5.450 su yolu çizgisi |

**Sel Risk Skoru (0-100)** altı bileşenden oluşur: çukur derinliği (25), akış birikimi (25), havza derinliği (12), memba eğimi (12), dere yakınlığı (10) ve maruziyet (16). Her yapının en düşük kotlu noktası DEM üzerinde bulunur; 1,2–1,5 km pencerede Priority-Flood akış birikimi hesaplanır.

| Seviye | Skor | Renk |
|--------|------|------|
| 🔴 **Çok Yüksek** | 70-100 | Kırmızı |
| 🟠 **Yüksek** | 55-69 | Turuncu |
| 🟡 **Orta** | 35-54 | Sarı |
| 🟢 **Düşük** | 20-34 | Yeşil |
| ⚪ **Çok Düşük** | 0-19 | Gri |

| Dosya | Açıklama |
|-------|----------|
| `Ankara_OSM_Alt_Gecit_Sel_Harita.html` | İnteraktif sel riski haritası (4 ESRI altlık, filtre, Google Maps) |
| `Ankara_Alt_Gecit_Sel_Risk_Raporu.docx` | Word raporu (yöntem, sıralamalar, öneriler) |
| `Ankara_Alt_Gecit_Sel_Analizi.xlsx` | 5 sayfalık Excel çalışma kitabı |
| `Ankara_OSM_Alt_Gecitler.csv` | 204 yapının envanteri ve skor bileşenleri |
| `Ankara_OSM_Sel_Riskli_Noktalar.csv` | Yapılar + 400 yol kesimi, öncelik sıralı |
| `Ankara_OSM_Sel_Ilce_Ozeti.csv` | İlçe bazında risk özeti |

🌐 **[Alt Geçit ve Sel Riski Haritası](https://darkeaglehome.github.io/ankara-yol-guvenligi/Ankara_OSM_Alt_Gecit_Sel_Harita.html)**

> Rapor saha ölçümü içermez; karar destek amaçlı ön değerlendirmedir. Yüksek riskli noktalarda kesin kot, drenaj ve pompa kapasitesi ölçülmelidir.

### 🗺️ Google Maps Entegrasyonu

Haritanın her kusur noktasında **"🗺️ Google Maps'te Aç"** butonu bulunur. Butona tıkladığınızda ilgili konum:

```
https://www.google.com/maps/search/?api=1&query=LAT,LNG
```

adresi yeni sekmede açılır.

### Lisans

MIT License

---

## 🇬🇧 English

### About

This project automatically detects **geometric and topological defects** in Ankara's road network using OpenStreetMap (OSM) data and classifies 98,703 unique hazard zones with a YGE 0-100 risk model. **A proactive engineering approach that identifies physical infrastructure defects before accidents happen.**

### Defect Types

| Defect | Description | Threshold |
|--------|-------------|-----------|
| **Sharp Curve** | Curve radius R ≤ 75 m | R = ds/dθ |
| **Narrow Section** | Road width W ≤ 5.5 m | Bottleneck |
| **Acute Intersection** | Intersection angle θ ≤ 45° | Blind spot |
| **Dead End** | Dead-end street off main road | Emergency access blocked |
| **Turning Circle** | U-turn restricted island | Maneuver constraint |
| **Steep Grade** | Longitudinal slope g ≥ 8% | DEM GLO-30 |

### Risk Score (YGE 0-100)

| Level | Score | Color |
|-------|-------|-------|
| 🔴 **Critical Black Spot** | ≥ 75 | Red |
| 🟠 **High Risk** | 55-74 | Orange |
| 🟡 **Medium Risk** | 35-54 | Yellow |
| 🟢 **Low Risk** | < 35 | Green |

### Data Sources

- **Road Network:** OpenStreetMap (Geofabrik Turkey PBF) — 110,870 ways / ~40,511 km
- **Elevation/Slope:** Copernicus DEM GLO-30 (30 m, ESA)
- **Speed Model:** Legal speed by road class (motorway 120 → residential 50 km/h)

### Technologies

- Python 3.12+, GeoPandas, Shapely, Rasterio
- Leaflet.js + ESRI World Imagery/Street/Topo/Dark
- Matplotlib, Seaborn (charts)
- python-docx, openpyxl (reports)

### Installation

```bash
git clone https://github.com/Darkeaglehome/ankara-yol-guvenligi.git
cd ankara-yol-guvenligi
pip install geopandas shapely rasterio numpy pandas scipy matplotlib seaborn folium pyproj openpyxl python-docx
```

### Usage

```bash
python aggregate_ankara.py       # Detect defects, compute risk scores
python generate_word_ankara.py   # Generate Word report
python generate_esri_map_ankara.py  # Generate interactive map
```

### Outputs

| File | Description |
|------|-------------|
| `Ankara_OSM_Kusurlar_Esri_Harita.html` | Interactive web map with 4 basemaps (Imagery/Street/Topo/Dark) |
| `Ankara_Yol_Guvenligi_ve_Kusur_Analizi_Raporu.docx` | Comprehensive Word report |
| `Ankara_OSM_Yol_Guvenligi_Raporu.xlsx` | 9-sheet Excel report |
| `Ankara_OSM_Tum_Kusurlar.csv` | 98,703-point raw data (XY + lon/lat) |

### Interactive Demo

🌐 **[Ankara Yol Güvenliği Haritası](https://darkeaglehome.github.io/ankara-yol-guvenligi/Ankara_OSM_Kusurlar_Esri_Harita.html)**

### 🚧 Underpass and Tunnel Flood Risk Analysis

The same project assesses **204 underpass/tunnel structures** and **400 flood-prone road segments** across Ankara. The inventory comes from OpenStreetMap `tunnel` / `layer<0` tags, and the hydrological model uses Copernicus DEM GLO-30.

| Indicator | Value |
|-----------|-------|
| Underpass / tunnel structures | 204 (117 road, 49 pedestrian, 22 tunnels, 16 other) |
| Very High / High risk structures | 2 / 20 |
| Flood-prone road segments screened | 400 (22 very high, 91 high) |
| Hydrological reference | 5,450 waterway lines |

**Flood Risk Score (0-100)** combines pit depth (25), flow accumulation (25), basin depth (12), upstream slope (12), waterway proximity (10) and exposure (16), computed with a Priority-Flood accumulation model on 30 m DEM.

| File | Description |
|------|-------------|
| `Ankara_OSM_Alt_Gecit_Sel_Harita.html` | Interactive flood risk map (4 ESRI basemaps, filters, Google Maps) |
| `Ankara_Alt_Gecit_Sel_Risk_Raporu.docx` | Word report (method, rankings, recommendations) |
| `Ankara_Alt_Gecit_Sel_Analizi.xlsx` | 5-sheet Excel workbook |
| `Ankara_OSM_Alt_Gecitler.csv` | Inventory of 204 structures with score components |
| `Ankara_OSM_Sel_Riskli_Noktalar.csv` | Structures + 400 road segments, priority-sorted |
| `Ankara_OSM_Sel_Ilce_Ozeti.csv` | District-level risk summary |

🌐 **[Underpass & Flood Risk Map](https://darkeaglehome.github.io/ankara-yol-guvenligi/Ankara_OSM_Alt_Gecit_Sel_Harita.html)**

> No field measurements are included; this is a screening-level assessment. Verify levels, drainage and pump capacity on site before design.

### 🗺️ Google Maps Integration

Every hazard point in the map popup includes a **"🗺️ Open in Google Maps"** button. Clicking it opens the selected defect location in Google Maps:

```
https://www.google.com/maps/search/?api=1&query=LAT,LNG
```

in a new tab.

### License

MIT License