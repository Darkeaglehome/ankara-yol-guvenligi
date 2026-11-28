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
```

### Çıktılar

| Dosya | Açıklama |
|-------|----------|
| `Ankara_OSM_Kusurlar_Esri_Harita.html` | 4 haritalı interaktif web haritası (Uydu/Sokak/Topo/Koyu) |
| `Ankara_Yol_Guvenligi_ve_Kusur_Analizi_Raporu.docx` | Kapsamlı Word raporu |
| `Ankara_OSM_Yol_Guvenligi_Raporu.xlsx` | 9 sayfalık Excel raporu |
| `Ankara_OSM_Tum_Kusurlar.csv` | 98.703 noktalık ham veri (XY + lon/lat) |

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

### 🗺️ Google Maps Integration

Every hazard point in the map popup includes a **"🗺️ Open in Google Maps"** button. Clicking it opens the selected defect location in Google Maps:

```
https://www.google.com/maps/search/?api=1&query=LAT,LNG
```

in a new tab.

### License

MIT License