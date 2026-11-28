# Ankara İli Yol Güvenliği ve Geometrik Kusur Analizi
## (Sadece OpenStreetMap Verisiyle Kara Nokta Modeli)

**Tarih:** 27.11.2026
**Kapsam:** Ankara il sınırları (25 ilçe)
**Veri kaynağı:** OpenStreetMap (Geofabrik `turkey-latest.osm.pbf` + OSM etiketleri)
**Referans metodoloji:** `METODOLOJI_YOL_GUVENLIGI.md` (İstanbul/DGN modeli) → OSM verisine uyarlanmış hali

---

## 1. Yönetici Özeti

| Gösterge | Değer |
| --- | --- |
| Yol ağı (way) | 110,870 parça |
| Toplam yol uzunluğu | 40,511 km |
| Hız modeli | Yol sınıfına göre **kanuni hız** (motorway 120 · trunk 90 · primary/secondary 70 · tertiary 60 · residential 50 · service 40) |
| Tekil tehlike noktası | 98,703 |
| **Kritik Kara Nokta (≥75)** | **22,847** |
| Yüksek Risk (55-74) | 27,051 |
| Orta Risk (35-54) | 37,985 |
| Düşük Risk (<35) | 10,820 |
| Ana arter kusuru | 5,658 |
| Dik boyuna eğim kesimi (g ≥ %8) | 17,613 |
| Kot aralığı (Copernicus DEM) | -9967 – 2029 m |
| En riskli ilçe | Çubuk (2931 kritik nokta) |

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

| Kusur türü | Adet | Medyan değer | Ort. risk | Kritik |
| --- | --- | --- | --- | --- |
| Keskin Viraj (R ≤ 75 m) | 47,536 | 22.8 | 59.9 | 14736 |
| Dik Boyuna Eğim (g ≥ %8) | 17,613 | 10.5 | 61.3 | 2070 |
| Dar Açıllı Kör Kavşak (θ ≤ 45°) | 17,541 | 29.4 | 59.8 | 5453 |
| Ana Yola Çıkmaz Sokak | 12,607 | 0.0 | 50.9 | 4 |
| Dar Kesit / Şişe Boynu (W ≤ 5.5 m) | 3,306 | 5.0 | 51.4 | 584 |
| Dönüş Cebi Manevra Kısıtı | 100 | 5.0 | 25.0 | 0 |

---

## 4. Ana Arter Hız-Risk Matrisi

| Hız bandı | Kusur sayısı | Kritik | Yüksek | Ort. risk |
| --- | --- | --- | --- | --- |
| ≤50 km/s | 178 | 51 | 94 | 66.0 |
| 51-70 km/s | 2,285 | 1199 | 785 | 72.9 |
| 71-90 km/s | 2,508 | 1797 | 711 | 80.6 |
| >90 km/s | 687 | 577 | 110 | 84.2 |

> Ana arterlerde yüksek hız + keskin viraj/dar açılı kavşak birleşimi en yüksek
> risk skorlarını üretir: yüksek hızda savrulma, devrilme ve görüş mesafesi kaybı.

---

## 5. İlçe Dağılımı (İlk 12)

| İlçe | Toplam | Kritik | Yüksek | Ana arter | Ort. hız | Ort. risk |
| --- | --- | --- | --- | --- | --- | --- |
| Çubuk | 11,098 | 2931 | 2890 | 164 | 42.8 | 60.0 |
| Çankaya | 10,454 | 2430 | 2871 | 968 | 49.2 | 58.9 |
| Mamak | 5,858 | 1516 | 2016 | 246 | 50.1 | 62.4 |
| Yenimahalle | 5,824 | 1362 | 1370 | 747 | 51.9 | 57.9 |
| Etimesgut | 5,518 | 1353 | 1360 | 835 | 52.3 | 58.8 |
| Gölbaşı | 6,381 | 1290 | 1519 | 352 | 49.1 | 57.6 |
| Nallıhan | 4,583 | 1260 | 1135 | 81 | 46.3 | 59.0 |
| Kızılcahamam | 5,101 | 1192 | 1350 | 80 | 45.5 | 57.1 |
| Altındağ | 3,847 | 960 | 1068 | 332 | 51.8 | 61.2 |
| Beypazarı | 3,741 | 933 | 1031 | 38 | 47.2 | 59.0 |
| Keçiören | 3,257 | 847 | 1231 | 224 | 53.2 | 63.0 |
| Sincan | 3,572 | 836 | 992 | 351 | 51.7 | 59.1 |

---

## 6. En Kritik 15 Kara Nokta

| # | Kusur | Risk | Değer | Hiyerarşi | Hız | İlçe | Yol |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Keskin Viraj (R ≤ 75 m) | 100.0 | 15.0 | Ara Sokak | 50 | Elmadağ | - |
| 2 | Keskin Viraj (R ≤ 75 m) | 100.0 | 9.0 | Ana Arter | 70 | Çankaya | Çetin Emeç Bulvarı |
| 3 | Keskin Viraj (R ≤ 75 m) | 100.0 | 13.4 | Ara Sokak | 50 | Elmadağ | - |
| 4 | Keskin Viraj (R ≤ 75 m) | 100.0 | 12.3 | Ara Sokak | 50 | Nallıhan | - |
| 5 | Keskin Viraj (R ≤ 75 m) | 100.0 | 11.3 | Ana Arter | 70 | Çankaya | Angora Bulvarı |
| 6 | Keskin Viraj (R ≤ 75 m) | 100.0 | 11.2 | Toplayıcı Cadde | 60 | Çankaya | 2. Yol |
| 7 | Keskin Viraj (R ≤ 75 m) | 100.0 | 13.7 | Ara Sokak | 50 | Elmadağ | - |
| 8 | Keskin Viraj (R ≤ 75 m) | 100.0 | 14.9 | Ana Arter | 90 | Elmadağ | - |
| 9 | Keskin Viraj (R ≤ 75 m) | 100.0 | 9.1 | Ara Sokak | 50 | Çankaya | Han Sokak |
| 10 | Keskin Viraj (R ≤ 75 m) | 100.0 | 10.6 | Ara Sokak | 50 | Çankaya | - |
| 11 | Keskin Viraj (R ≤ 75 m) | 100.0 | 11.9 | Ana Arter | 70 | Çankaya | - |
| 12 | Keskin Viraj (R ≤ 75 m) | 100.0 | 4.4 | Ara Sokak | 50 | Mamak | - |
| 13 | Keskin Viraj (R ≤ 75 m) | 100.0 | 10.3 | Ara Sokak | 50 | Altındağ | - |
| 14 | Keskin Viraj (R ≤ 75 m) | 100.0 | 14.2 | Ara Sokak | 50 | Altındağ | - |
| 15 | Keskin Viraj (R ≤ 75 m) | 100.0 | 9.2 | Toplayıcı Cadde | 60 | Haymana | - |

---

## 7. Boyuna Eğim (Rampa) Analizi

OSM'de kot bulunmadığı için önceki sürümde hesaplanamayan boyuna eğim modülü,
**Copernicus DEM GLO-30 (30 m)** yükseklik mozaiği indirilerek devreye alındı.
Her OSM yol ekseni boyunca 30 m aralıklarla kot örneklenmiş, 90 m'lik pencerede
`g = Δz / Δs` boyuna eğimi hesaplanmış ve **|g| ≥ %8** olan, en az 90 m süren
kesimler `EGIM` kusuru olarak modele eklenmiştir. Eğim, aynı zamanda tüm
diğer kusurların risk skoruna zemin tutunma kaybı çarpanı olarak yansıtılır.

**Kot / eğim kapsamı:** -9967–2029 m kot aralığı ·
ortalama arazi eğimi %13.7 · en dik boyuna eğim
%65.7 · 17,613 dik eğim kesimi.

| Boyuna eğim bandı | Kesim | Kritik | Ort. risk | Toplam uzunluk (km) |
| --- | --- | --- | --- | --- |
| %8-10 | 7,429 | 20 | 53.9 | 1,419.4 |
| %10-12 | 4,362 | 12 | 59.8 | 1,135.8 |
| %12-15 | 3,545 | 1366 | 72.2 | 1,145.4 |
| >%15 | 2,277 | 672 | 71.6 | 840.8 |

| Yol hiyerarşisi | Dik eğim kesimi | Ort. eğim |
| --- | --- | --- |
| Ana Arter | 597 | %10.4 |
| Ara Sokak | 10,576 | %11.6 |
| Toplayıcı Cadde | 6,440 | %11.1 |

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

- **Öncelik 1:** Çubuk ve Çankaya ilçelerinde
  kritik noktaların yoğunlaşması, bu ilçelerde hızlı arter + keskin viraj/dar açılı
  kavşak bileşiminin çok olduğunu gösterir.
- **Öncelik 2:** Ana arterlerde `hiz_kurp_fark_kmh > 40` olan noktalar (Excel:
  `Ana_Arter_Hiz_Riski`) hız düşürme, kenar şeridi, uyarı tabelası ve aydınlatma ile
  önceliklendirilmelidir.
- **Öncelik 3:** Dar açılı (≤35°) kavşaklarda görüş üçgeni temizliği, ayna ve
  yavaşlatma elemanları uygulanmalıdır.
- **Öncelik 4:** Dik boyuna eğimli (%8 ve üzeri) **17,613** kesimde ıslak/karlı
  zemin tutunma kaybı, inişlerde fren kaybı ve viraj içi savrulma riski artar;
  bu kesimlerde hız yönetimi, yüksek tutunmalı (tırmandırıcı) kaplama, drenaj ve
  kış bakım (tuzlama) planı önceliklendirilmelidir. Kot verisi artık
  Copernicus DEM GLO-30'dan üretilmekte olup 1/1000 DGN ile doğrulanabilir.
