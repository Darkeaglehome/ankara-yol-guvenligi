# -*- coding: utf-8 -*-
"""
generate_sel_map_ankara.py
Ankara alt gecit / sel riski icin interaktif Leaflet haritasi.
4 ESRI altlik (Uydu, Sokak, Topo, Koyu), risk/tip/ilce filtreleri, arama, top-10 listesi.
"""
import json
import os
import time

import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_GECIT = os.path.join(BASE, "Ankara_OSM_Alt_Gecitler.csv")
CSV_NOKTA = os.path.join(BASE, "Ankara_OSM_Sel_Riskli_Noktalar.csv")
OUT = os.path.join(BASE, "Ankara_OSM_Alt_Gecit_Sel_Harita.html")

LEVELS = ["Çok Yüksek", "Yüksek", "Orta", "Düşük", "Çok Düşük"]
COLORS = ["#C0392B", "#E67E22", "#F1C40F", "#27AE60", "#95A5A6"]


def clean(v, nd=None):
    if pd.isna(v):
        return None
    if nd is not None and isinstance(v, (int, float)):
        return round(float(v), nd)
    return v


def main():
    t0 = time.time()
    df = pd.read_csv(CSV_GECIT)
    road = pd.read_csv(CSV_NOKTA)

    records = []
    for r in df.itertuples():
        records.append({
            "id": r.yapi_id, "tip": r.gecit_tipi, "ad": clean(r.ad),
            "ilce": r.ilce, "yol": clean(r.yol_sinifi), "durum": clean(r.durum),
            "boy": clean(r.uzunluk_m, 1), "kmin": clean(r.kot_min_m, 1),
            "kmax": clean(r.kot_max_m, 1),
            "cukur": clean(r.cukur_derinligi_m, 2), "havza": clean(r.havza_derinligi_m, 2),
            "akim": clean(r.akim_birikim_ha, 1), "egim": clean(r.memba_egimi_yuzde, 1),
            "dere": clean(r.dere_mesafe_m, 0), "dere_tip": clean(r.dere_tipi),
            "dere_ad": clean(r.dere_adi), "aydin": clean(r.aydinlatma),
            "mh": clean(r.maxheight), "skor": round(float(r.sel_risk_skoru), 1),
            "lvl": LEVELS.index(r.sel_risk_seviyesi),
            "onc": clean(r.oncelik), "x": round(float(r.x)), "y": round(float(r.y)),
            "lat": round(float(r.lat), 6), "lon": round(float(r.lon), 6),
            "osm": clean(r.osm_idler), "kentsel": None,
        })
    for r in road[road["gecit_tipi"] == "Yol Kesimi"].itertuples():
        records.append({
            "id": r.yapi_id, "tip": "Yol Kesimi", "ad": clean(r.ad),
            "ilce": r.ilce, "yol": clean(r.yol_sinifi), "durum": clean(r.durum),
            "boy": None, "kmin": clean(r.kot_min_m, 1), "kmax": None,
            "cukur": clean(r.cukur_derinligi_m, 2), "havza": clean(r.havza_derinligi_m, 2),
            "akim": clean(r.akim_birikim_ha, 1), "egim": clean(r.memba_egimi_yuzde, 1),
            "dere": clean(r.dere_mesafe_m, 0), "dere_tip": clean(r.dere_tipi),
            "dere_ad": clean(r.dere_adi), "aydin": None, "mh": None,
            "skor": round(float(r.sel_risk_skoru), 1),
            "lvl": LEVELS.index(r.sel_risk_seviyesi),
            "onc": None, "x": round(float(r.x)), "y": round(float(r.y)),
            "lat": round(float(r.lat), 6), "lon": round(float(r.lon), 6),
            "osm": clean(r.osm_idler), "kentsel": bool(r.kentsel_mi),
        })

    tip_counts = {}
    for rec in records:
        if not isinstance(rec["ilce"], str):
            rec["ilce"] = "Belirsiz"
        tip_counts[rec["tip"]] = tip_counts.get(rec["tip"], 0) + 1
    tip_order = [t for t in ["Araç Alt Geçidi", "Yaya Alt Geçidi", "Araç Tüneli",
                             "Yapı Geçişi", "Yapım/Proje Geçişi", "Diğer Geçiş",
                             "Yol Kesimi"] if t in tip_counts]
    ilceler = sorted({r["ilce"] for r in records})

    payload = {
        "noktalar": records,
        "levels": LEVELS,
        "colors": COLORS,
        "tipler": tip_order,
        "tipCounts": tip_counts,
        "ilceler": ilceler,
        "n_gecit": len(df),
        "n_yol": len(roads := road[road["gecit_tipi"] == "Yol Kesimi"]),
        "tarih": "28 Kasım 2026",
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    html = HTML_TEMPLATE.replace("__DATA__", data_json)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Harita yazildi: {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB, "
          f"{len(records)} nokta, {time.time()-t0:.1f} sn)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ankara Alt Geçit ve Sel Riski Haritası</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body { margin:0; padding:0; height:100%; font-family:"Segoe UI",Arial,sans-serif; }
  #map { position:absolute; inset:0; background:#141a22; }

  #panel {
    position:absolute; top:0; left:0; bottom:0; width:342px; z-index:1100;
    background:rgba(20,26,34,.97); color:#ecf0f1; overflow-y:auto;
    box-shadow:4px 0 16px rgba(0,0,0,.45); box-sizing:border-box;
    padding:16px 16px 30px 16px; transition:transform .28s ease;
  }
  #panel.closed { transform:translateX(-342px); }
  #panel h1 { font-size:17px; margin:2px 0 2px; color:#fff; line-height:1.25; }
  #panel h1 small { display:block; font-size:11px; color:#95a5a6; font-weight:400; margin-top:4px; }
  .kicker { font-size:10px; letter-spacing:1.2px; color:#e67e22; font-weight:700; text-transform:uppercase; }
  .badges { margin:8px 0 2px; }
  .badge { display:inline-block; background:#1B365D; color:#fff; font-size:10.5px;
           padding:3px 8px; border-radius:10px; margin:0 5px 4px 0; }
  .badge.red { background:#a93226; }
  .sec { border-top:1px solid #2c3e50; margin-top:14px; padding-top:11px; }
  .sec h2 { font-size:11px; text-transform:uppercase; letter-spacing:.7px;
            color:#5dade2; margin:0 0 8px; }
  .cbrow { display:flex; align-items:center; padding:3px 0; font-size:13px; cursor:pointer; }
  .cbrow input { margin-right:8px; accent-color:#3498db; width:15px; height:15px; cursor:pointer; }
  .cbrow .cnt { margin-left:auto; color:#95a5a6; font-size:11.5px;
                font-variant-numeric:tabular-nums; }
  .dot { width:11px; height:11px; border-radius:50%; display:inline-block;
         margin-right:7px; border:1px solid rgba(255,255,255,.35); flex:none; }
  select, #q { width:100%; background:#22303f; color:#ecf0f1; border:1px solid #34495e;
               border-radius:4px; padding:6px 8px; font-size:13px; box-sizing:border-box; }
  #q { margin-bottom:7px; }
  .btnrow { display:flex; gap:7px; margin-top:9px; }
  .btn { flex:1; background:#2980b9; color:#fff; border:0; border-radius:4px;
         padding:7px 6px; font-size:12px; cursor:pointer; }
  .btn.alt { background:#34495e; }
  .btn:hover { filter:brightness(1.15); }
  .stats { display:flex; gap:7px; margin-top:10px; }
  .stat { background:#22303f; border-radius:5px; padding:7px 9px; flex:1;
          font-size:10.5px; color:#95a5a6; }
  .stat b { display:block; font-size:16px; color:#fff; font-variant-numeric:tabular-nums; }
  .top10 { font-size:12px; }
  .top10 div { display:flex; align-items:center; gap:7px; padding:4px 5px;
               border-radius:4px; cursor:pointer; }
  .top10 div:hover { background:#22303f; }
  .top10 .rk { color:#7f8c8d; width:16px; flex:none; }
  .top10 .nm { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .top10 .sc { font-weight:700; font-variant-numeric:tabular-nums; }
  .foot { font-size:10.5px; color:#7f8c8d; margin-top:16px; line-height:1.5; }
  .foot a { color:#5dade2; }

  #toggle {
    position:absolute; top:50%; left:342px; z-index:1101; transform:translateY(-50%);
    background:#141a22; color:#fff; border:0; border-radius:0 6px 6px 0;
    padding:16px 7px; font-size:15px; cursor:pointer; transition:left .28s ease;
    box-shadow:3px 0 8px rgba(0,0,0,.4); font-weight:700;
  }
  #toggle.closed { left:0; }

  .leaflet-popup-content { font-size:13px; line-height:1.5; min-width:262px; margin:12px 14px; }
  .ptitle { font-size:14.5px; font-weight:700; color:#1B365D; }
  .psub { font-size:11.5px; color:#7f8c8d; margin:1px 0 6px; }
  .chip { display:inline-block; color:#fff; font-size:11px; font-weight:700;
          padding:2px 9px; border-radius:10px; margin-bottom:7px; }
  table.popt { border-collapse:collapse; width:100%; font-size:12px; }
  table.popt td { padding:2.5px 3px; border-bottom:1px solid #eef1f3; }
  table.popt td:first-child { color:#7f8c8d; width:46%; }
  .coord { font-family:Consolas,monospace; font-size:11px; color:#566573; }
  .links { margin-top:8px; display:flex; gap:6px; }
  .links a { flex:1; text-align:center; text-decoration:none; font-size:11.5px;
             padding:6px 4px; border-radius:4px; font-weight:600; }
  .gmaps { background:#1B365D; color:#fff; }
  .osm { background:#eaf2f8; color:#1B365D; }
  .links a:hover { filter:brightness(1.1); }

  @media (max-width:640px) {
    #panel { width:100%; bottom:auto; max-height:46%; }
    #panel.closed { transform:translateY(-100%); }
    #toggle { left:auto; right:10px; top:10px; transform:none; border-radius:6px; }
    #toggle.closed { left:auto; }
  }
</style>
</head>
<body>
<div id="map"></div>
<button id="toggle" title="Paneli aç/kapat">«</button>

<div id="panel">
  <div class="kicker">Ankara · Ulaşım Altyapısı</div>
  <h1>Alt Geçit ve Tünel Sel Riski
    <small>OpenStreetMap + Copernicus DEM GLO-30 · <span id="tarih"></span></small>
  </h1>
  <div class="badges">
    <span class="badge" id="b-gecit"></span>
    <span class="badge" id="b-yol"></span>
    <span class="badge red" id="b-high"></span>
  </div>

  <div class="sec">
    <h2>Sel risk seviyesi</h2>
    <div id="levels"></div>
  </div>

  <div class="sec">
    <h2>Yapı tipi</h2>
    <div id="tipler"></div>
  </div>

  <div class="sec">
    <h2>İlçe ve arama</h2>
    <select id="ilce"><option value="">Tüm ilçeler</option></select>
    <div class="btnrow" style="margin-top:7px">
      <input id="q" type="text" placeholder="ID, ad, dere ara…">
    </div>
    <div class="btnrow">
      <button class="btn" id="reset">Filtreleri sıfırla</button>
      <button class="btn alt" id="fit">Tümünü göster</button>
    </div>
  </div>

  <div class="sec">
    <h2>Görünen noktalar</h2>
    <div class="stats">
      <div class="stat"><b id="s-n">0</b>nokta</div>
      <div class="stat"><b id="s-avg">0</b>ortalama skor</div>
      <div class="stat"><b id="s-max">0</b>en yüksek</div>
    </div>
  </div>

  <div class="sec">
    <h2>En riskli 10 yapı</h2>
    <div class="top10" id="top10"></div>
  </div>

  <div class="foot">
    Skor 0-100: çukur derinliği (25), akış birikimi (25), havza derinliği (12),
    memba eğimi (12), dere yakınlığı (10), maruziyet (16).<br>
    Saha ölçümü içermez; ön değerlendirme amaçlıdır.<br><br>
    Veri: © OpenStreetMap katkıcıları · DEM: Copernicus GLO-30 (ESA) ·
    Altlık: Esri, Maxar, Earthstar Geographics
  </div>
</div>

<script>
const DATA = __DATA__;
const LV = DATA.levels, CL = DATA.colors, TIPS = DATA.tipler;

const map = L.map('map', { preferCanvas:true, zoomControl:false })
             .setView([39.93, 32.86], 10);
L.control.zoom({ position:'topright' }).addTo(map);
L.control.scale({ imperial:false, position:'bottomright' }).addTo(map);

const bUydu = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:19, attribution:'Tiles © Esri — Esri, Maxar, Earthstar Geographics' });
const bUyduEtiket = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:19, pane:'overlayPane' });
const bSokak = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:19, attribution:'© Esri, HERE, Garmin, OpenStreetMap' });
const bTopo = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:19, attribution:'© Esri, HERE, Garmin, USGS, OpenStreetMap' });
const bKoyu = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:16, attribution:'© Esri, HERE, Garmin, OpenStreetMap' });
const bKoyuRef = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
  { maxZoom:16, pane:'overlayPane' });

bUydu.addTo(map);
bUyduEtiket.addTo(map);
L.control.layers({
  'ESRI Uydu': bUydu, 'ESRI Sokak': bSokak, 'ESRI Topo': bTopo, 'ESRI Koyu': bKoyu
}, null, { position:'topright', collapsed:true }).addTo(map);

map.on('baselayerchange', e => {
  if (e.name === 'ESRI Uydu') { bUyduEtiket.addTo(map); }
  else { map.removeLayer(bUyduEtiket); }
  if (e.name === 'ESRI Koyu') { bKoyuRef.addTo(map); }
  else { map.removeLayer(bKoyuRef); }
});

const gGecit = L.layerGroup().addTo(map);
const gYol = L.layerGroup().addTo(map);

function fmt(v, d, suf) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'number') {
    return v.toLocaleString('tr-TR', { minimumFractionDigits:d||0, maximumFractionDigits:d||0 }) + (suf||'');
  }
  return v + (suf||'');
}
function esc(s) {
  return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

const MAXO = 4;
function radius(d) {
  return d.tip === 'Yol Kesimi' ? 4 + d.skor / 32 : 5.5 + d.skor / 20;
}
function style(d) {
  return {
    radius: radius(d), color:'#ffffff', weight:1.1,
    fillColor: CL[d.lvl], fillOpacity: d.tip === 'Yol Kesimi' ? 0.72 : 0.9
  };
}

function popup(d) {
  const gm = `https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}`;
  const om = `https://www.openstreetmap.org/?mlat=${d.lat}&mlon=${d.lon}#map=19/${d.lat}/${d.lon}`;
  const rows = [
    ['Sel risk skoru', `<b>${fmt(d.skor,1)} / 100</b>`],
    ['Çukur derinliği', fmt(d.cukur,1,' m')],
    ['Havza derinliği', fmt(d.havza,1,' m')],
    ['Akış birikimi', fmt(d.akim,1,' ha')],
    ['Memba eğimi', fmt(d.egim,1,' %')],
    ['En yakın su yolu', fmt(d.dere,0,' m') + (d.dere_tip ? ` (${esc(d.dere_tip)})` : '')],
    ['Dere / kanal', esc(d.dere_ad || '—')],
  ];
  if (d.tip !== 'Yol Kesimi') {
    rows.push(['Yol sınıfı', esc(d.yol || '—')]);
    rows.push(['Uzunluk', fmt(d.boy,0,' m')]);
    rows.push(['Kot (min–maks)', fmt(d.kmin,0) + ' – ' + fmt(d.kmax,0) + ' m']);
    rows.push(['Aydınlatma', esc(d.aydin || '—')]);
    if (d.mh !== null) rows.push(['Maxheight', esc(d.mh)]);
  } else {
    rows.push(['Yerel rölyef', fmt(d.kmin,0,' m')]);
    rows.push(['Kentsel', d.kentsel ? 'Evet' : 'Hayır']);
  }
  rows.push(['Koordinat', `<span class="coord">${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}</span>`]);
  const tr = rows.map(r => `<tr><td>${r[0]}</td><td>${r[1]}</td></tr>`).join('');
  return `<div class="ptitle">${esc(d.id)} · ${esc(d.tip)}</div>
    <div class="psub">${esc(d.ilce)}${d.onc ? ' · Öncelik #' + d.onc : ''}${d.ad ? ' · ' + esc(d.ad) : ''}</div>
    <span class="chip" style="background:${CL[d.lvl]}">${LV[d.lvl]}</span>
    <table class="popt">${tr}</table>
    <div class="links">
      <a class="gmaps" href="${gm}" target="_blank" rel="noopener">Google Maps'te Aç</a>
      <a class="osm" href="${om}" target="_blank" rel="noopener">OpenStreetMap</a>
    </div>`;
}

const markers = DATA.noktalar.map(d => {
  const m = L.circleMarker([d.lat, d.lon], style(d)).bindPopup(popup(d), { maxWidth:320 });
  m.__d = d;
  return m;
});

// --- filtre UI ---
const lvCounts = [0,0,0,0,0];
DATA.noktalar.forEach(d => lvCounts[d.lvl]++);
document.getElementById('levels').innerHTML = LV.map((l, i) => `
  <label class="cbrow">
    <input type="checkbox" class="lv" value="${i}" checked>
    <span class="dot" style="background:${CL[i]}"></span>${l}
    <span class="cnt">${lvCounts[i]}</span>
  </label>`).join('');

document.getElementById('tipler').innerHTML = TIPS.map(t => `
  <label class="cbrow">
    <input type="checkbox" class="tp" value="${esc(t)}" checked>
    ${esc(t)}<span class="cnt">${DATA.tipCounts[t]}</span>
  </label>`).join('');

const ilceSel = document.getElementById('ilce');
DATA.ilceler.forEach(i => {
  const o = document.createElement('option');
  o.value = i; o.textContent = i; ilceSel.appendChild(o);
});

document.getElementById('tarih').textContent = DATA.tarih;
document.getElementById('b-gecit').textContent = DATA.n_gecit + ' alt geçit / tünel';
document.getElementById('b-yol').textContent = DATA.n_yol + ' yol kesimi';
const nG = DATA.noktalar.filter(d => d.lvl <= 1 && d.tip !== 'Yol Kesimi').length;
const nY = DATA.noktalar.filter(d => d.lvl <= 1 && d.tip === 'Yol Kesimi').length;
document.getElementById('b-high').textContent = nG + ' yapı · ' + nY + ' yol kesimi yüksek risk';

const gecitBounds = L.latLngBounds(DATA.noktalar.map(d => [d.lat, d.lon]));

function active(name) {
  return [...document.querySelectorAll('.' + name + ':checked')].map(x => x.value);
}

function apply() {
  gGecit.clearLayers(); gYol.clearLayers();
  const lv = new Set(active('lv').map(Number));
  const tp = new Set(active('tp'));
  const il = ilceSel.value;
  const q = document.getElementById('q').value.trim().toLowerCase();
  let n = 0, sum = 0, mx = 0;
  const bounds = [];
  markers.forEach(m => {
    const d = m.__d;
    let ok = lv.has(d.lvl) && tp.has(d.tip);
    if (ok && il && d.ilce !== il) ok = false;
    if (ok && q) {
      const hay = (d.id + ' ' + (d.ad || '') + ' ' + (d.dere_ad || '') + ' ' + d.ilce + ' ' + d.tip).toLowerCase();
      if (!hay.includes(q)) ok = false;
    }
    if (ok) {
      (d.tip === 'Yol Kesimi' ? gYol : gGecit).addLayer(m);
      n++; sum += d.skor; mx = Math.max(mx, d.skor);
      bounds.push([d.lat, d.lon]);
    }
  });
  document.getElementById('s-n').textContent = n.toLocaleString('tr-TR');
  document.getElementById('s-avg').textContent = n ? (sum / n).toFixed(1).replace('.', ',') : '—';
  document.getElementById('s-max').textContent = n ? mx.toFixed(0) : '—';
  return bounds;
}

function refresh(zoom) {
  const b = apply();
  if (zoom && b.length) map.fitBounds(b, { padding:[40, 40], maxZoom:14 });
}

document.querySelectorAll('.lv, .tp').forEach(cb => cb.addEventListener('change', () => refresh(false)));
ilceSel.addEventListener('change', () => refresh(true));
let timer;
document.getElementById('q').addEventListener('input', () => {
  clearTimeout(timer); timer = setTimeout(() => refresh(true), 220);
});
document.getElementById('reset').addEventListener('click', () => {
  document.querySelectorAll('.lv, .tp').forEach(c => c.checked = true);
  ilceSel.value = ''; document.getElementById('q').value = '';
  map.fitBounds(gecitBounds, { padding:[40, 40] });
  apply();
});
document.getElementById('fit').addEventListener('click', () => {
  const b = apply();
  if (b.length) map.fitBounds(b, { padding:[40, 40], maxZoom:14 });
});

// --- top 10 ---
const top10 = DATA.noktalar.filter(d => d.tip !== 'Yol Kesimi')
  .sort((a, b) => b.skor - a.skor).slice(0, 10);
document.getElementById('top10').innerHTML = top10.map((d, i) => `
  <div data-i="${DATA.noktalar.indexOf(d)}">
    <span class="rk">${i + 1}</span>
    <span class="dot" style="background:${CL[d.lvl]};margin-right:0"></span>
    <span class="nm">${esc(d.id)} · ${esc(d.ilce)}</span>
    <span class="sc" style="color:${CL[d.lvl]}">${d.skor.toFixed(0)}</span>
  </div>`).join('');
document.querySelectorAll('#top10 div').forEach(el => {
  el.addEventListener('click', () => {
    const d = DATA.noktalar[+el.dataset.i];
    const m = markers[+el.dataset.i];
    if (!map.hasLayer(m)) { gGecit.addLayer(m); }
    map.flyTo([d.lat, d.lon], 17, { duration:0.9 });
    setTimeout(() => m.openPopup(), 950);
  });
});

// --- panel toggle ---
const panel = document.getElementById('panel');
const toggle = document.getElementById('toggle');
toggle.addEventListener('click', () => {
  panel.classList.toggle('closed');
  toggle.classList.toggle('closed');
  toggle.textContent = panel.classList.contains('closed') ? '»' : '«';
  setTimeout(() => map.invalidateSize(), 300);
});

map.fitBounds(gecitBounds, { padding:[30, 30] });
apply();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
