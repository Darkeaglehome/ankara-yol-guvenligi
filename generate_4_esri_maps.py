# -*- coding: utf-8 -*-
"""
generate_4_esri_maps.py
Generates 4 ESRI basemap variants for Ankara OSM kusur haritalari:
1. ESRI Uydu (Imagery) + Labels
2. ESRI Sokak (Streets)
3. ESRI Topo (Topographic)
4. ESRI Dark Gray Canvas
"""
import json
import os
import time

import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_ALL = os.path.join(BASE, "Ankara_OSM_Tum_Kusurlar.csv")

# 4 ESRI basemap configurations
BASEMAPS = [
    {
        "id": "imagery",
        "title": "ESRI Uydu (Uydu Görüntüleri)",
        "file": "Ankara_OSM_Kusurlar_Esri_Uydu.html",
        "layers": [
            {
                "name": "ESRI World Imagery",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "attribution": "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics",
                "pane": "tilePane"
            },
            {
                "name": "ESRI World Boundaries and Places",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                "attribution": "",
                "pane": "overlayPane"
            }
        ],
        "default": True
    },
    {
        "id": "streets",
        "title": "ESRI Sokak (Cadde/Sokak Haritası)",
        "file": "Ankara_OSM_Kusurlar_Esri_Sokak.html",
        "layers": [
            {
                "name": "ESRI World Street Map",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                "attribution": "© Esri, HERE, Garmin, FAO, NOAA, USGS, OpenStreetMap",
                "pane": "tilePane"
            }
        ],
        "default": False
    },
    {
        "id": "topo",
        "title": "ESRI Topo (Topografik Harita)",
        "file": "Ankara_OSM_Kusurlar_Esri_Topo.html",
        "layers": [
            {
                "name": "ESRI World Topographic Map",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
                "attribution": "© Esri, HERE, Garmin, FAO, NOAA, USGS, OpenStreetMap",
                "pane": "tilePane"
            }
        ],
        "default": False
    },
    {
        "id": "dark",
        "title": "ESRI Dark Gray Canvas (Koyu Tema)",
        "file": "Ankara_OSM_Kusurlar_Esri_Dark.html",
        "layers": [
            {
                "name": "ESRI Dark Gray Canvas Base",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                "attribution": "© Esri, HERE, Garmin, FAO, NOAA, USGS",
                "pane": "tilePane"
            },
            {
                "name": "ESRI Dark Gray Canvas Reference",
                "url": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
                "attribution": "",
                "pane": "overlayPane"
            }
        ],
        "default": False
    }
]

KINDS = ["KURP", "GENISLIK", "KAVSAK_ACISI", "CIKMAZ_SOKAK", "DONUS_CEBI", "EGIM"]
KIND_LABELS = {
    "KURP": "Keskin Viraj (R ≤ 75 m)",
    "GENISLIK": "Dar Kesit / Şişe Boyun (W ≤ 5.5 m)",
    "KAVSAK_ACISI": "Dar Açılı Kör Kavşak (θ ≤ 45°)",
    "CIKMAZ_SOKAK": "Çıkmaz Sokak",
    "DONUS_CEBI": "Dönüş Cebi",
    "EGIM": "Dik Boyuna Eğim (g ≥ %8)",
}
LEVELS = ["Kritik Kara Nokta", "Yüksek Risk", "Orta Risk", "Düşük Risk"]
LEVEL_COLORS = ["#e74c3c", "#e67e22", "#f1c40f", "#27ae60"]


def load_data():
    print("1. Veri yukleniyor...", flush=True)
    df = pd.read_csv(CSV_ALL, low_memory=False)

    import pyproj
    tr = pyproj.Transformer.from_crs("EPSG:32636", "EPSG:4326", always_xy=True)
    lon, lat = tr.transform(df["x"].values, df["y"].values)
    lon = np.round(lon, 5)
    lat = np.round(lat, 5)

    kind_idx = df["kind"].map({k: i for i, k in enumerate(KINDS)})
    kind_idx = kind_idx.fillna(len(KINDS) - 1).astype(np.uint8).values

    level_idx = df["risk_seviyesi"].map({l: i for i, l in enumerate(LEVELS)}).fillna(3)
    level_idx = level_idx.astype(np.uint8).values

    risk = np.round(df["risk_skoru"].values, 1).astype(np.float32)
    vals = np.round(df["val"].values, 1).astype(np.float32)
    ux = np.round(df["x"].values, 0).astype(np.int32)
    uy = np.round(df["y"].values, 0).astype(np.int32)
    speed = np.round(df["yol_hizi_kmh"].values, 0).astype(np.int16)
    egim = np.round(df["egim_yuzde"].fillna(-1).values, 1).astype(np.float32)
    kot = np.round(df["kot_m"].fillna(-1).values, 0).astype(np.int32)

    ilceler = sorted(df["ilce"].fillna("Belirsiz").unique().tolist())
    ilce_idx = df["ilce"].fillna("Belirsiz").map({n: i for i, n in enumerate(ilceler)}).astype(np.uint8).values

    names = df["name"].fillna("").astype(str).values
    highways = df["highway"].fillna("").astype(str).values

    name_dict = {}
    name_ids = np.zeros(len(df), dtype=np.int32)
    hw_dict = {}
    hw_ids = np.zeros(len(df), dtype=np.int16)
    for i, s in enumerate(names):
        if s not in name_dict:
            name_dict[s] = len(name_dict)
        name_ids[i] = name_dict[s]
    for i, s in enumerate(highways):
        if s not in hw_dict:
            hw_dict[s] = len(hw_dict)
        hw_ids[i] = hw_dict[s]

    osm_ids = df["osm_id"].fillna(0).astype(np.int64).tolist()

    payload = {
        "lat": lat.tolist(),
        "lon": lon.tolist(),
        "x": ux.tolist(),
        "y": uy.tolist(),
        "r": risk.tolist(),
        "v": vals.tolist(),
        "k": kind_idx.tolist(),
        "l": level_idx.tolist(),
        "i": ilce_idx.tolist(),
        "s": speed.tolist(),
        "e": egim.tolist(),
        "z": kot.tolist(),
        "m": name_ids.tolist(),
        "h": hw_ids.tolist(),
        "names": list(name_dict.keys()),
        "hws": list(hw_dict.keys()),
        "osmid": osm_ids,
        "ilceler": ilceler,
        "kinds": KINDS,
        "kindLabels": [KIND_LABELS[k] for k in KINDS],
        "levels": LEVELS,
        "levelColors": LEVEL_COLORS,
        "n_kusur": len(df),
    }
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    print(f"   -> {len(df):,} nokta, {len(ilceler)} ilce, JSON: {len(data_json)/1e6:.1f} MB", flush=True)
    return data_json, len(df), ilceler


def build_html(basemap, data_json, N, ilceler):
    """Build HTML for a single basemap configuration."""
    # Build basemap layer definitions for Leaflet
    layer_defs = []
    base_layers_js = []
    overlay_layers_js = []

    for idx, lyr in enumerate(basemap["layers"]):
        pane = lyr.get("pane", "tilePane")
        attr = lyr.get("attribution", "")
        if pane == "overlayPane":
            overlay_layers_js.append(f'''
    var {lyr["name"].replace(" ", "").replace("-", "")} = L.tileLayer(
      '{lyr["url"]}',
      {{ maxZoom:19, pane:'overlayPane'{f", attribution:'{attr}'" if attr else ""} }}
    ).addTo(map);''')
        else:
            base_layers_js.append(f'''
    var {lyr["name"].replace(" ", "").replace("-", "")} = L.tileLayer(
      '{lyr["url"]}',
      {{ maxZoom:19{f", attribution:'{attr}'" if attr else ""} }}
    );''')
            layer_defs.append(f"'{lyr['name']}': {lyr['name'].replace(' ', '').replace('-', '')}")

    base_layers_js_str = "\n".join(base_layers_js)
    overlay_layers_js_str = "\n".join(overlay_layers_js)
    base_layers_dict = ",\n      ".join(layer_defs)

    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{basemap['title']}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html, body {{ margin:0; padding:0; height:100%; font-family:"Segoe UI",Arial,sans-serif; }}
  #map {{ position:absolute; left:0; top:0; right:0; bottom:0; background:#1a1a1a; }}

  /* ---------- SOL PANEL ---------- */
  #panel {{
    position:absolute; top:0; left:0; bottom:0; width:330px; z-index:1100;
    background:rgba(20,26,34,0.96); color:#ecf0f1; overflow-y:auto;
    transform:translateX(0); transition:transform .3s ease;
    box-shadow:4px 0 14px rgba(0,0,0,.45); box-sizing:border-box;
    padding:14px 16px 26px 16px;
  }}
  #panel.closed {{ transform:translateX(-330px); }}
  #panel h1 {{ font-size:16px; margin:4px 0 2px 0; color:#fff; line-height:1.25; }}
  #panel h1 small {{ display:block; font-size:11px; color:#95a5a6; font-weight:normal; margin-top:3px; }}
  .badge {{ display:inline-block; background:#1B365D; color:#fff; font-size:10px;
           padding:2px 7px; border-radius:10px; margin:6px 6px 0 0; }}
  .badge.red {{ background:#c0392b; }}
  .sec {{ border-top:1px solid #34495e; margin-top:14px; padding-top:10px; }}
  .sec h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.6px;
             color:#3498db; margin:0 0 8px 0; }}
  .cbrow {{ display:flex; align-items:center; padding:3px 0; font-size:13px; cursor:pointer; }}
  .cbrow input {{ margin-right:8px; accent-color:#3498db; width:15px; height:15px; cursor:pointer; }}
  .dot {{ width:11px; height:11px; border-radius:50%; display:inline-block;
          margin-right:7px; border:1px solid rgba(255,255,255,.35); flex:none; }}
  .cnt {{ margin-left:auto; color:#95a5a6; font-size:12px; font-variant-numeric:tabular-nums; }}
  select {{ width:100%; background:#22303f; color:#ecf0f1; border:1px solid #34495e;
            border-radius:4px; padding:6px 8px; font-size:13px; }}
  .btnrow {{ display:flex; gap:8px; margin-top:9px; }}
  .btn {{ flex:1; background:#2980b9; color:#fff; border:0; border-radius:4px;
          padding:7px 6px; font-size:12px; cursor:pointer; }}
  .btn.alt {{ background:#34495e; }}
  .btn:hover {{ filter:brightness(1.15); }}
  .stats {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
  .stat {{ background:#22303f; border-radius:5px; padding:6px 9px; flex:1 1 44%;
          font-size:11px; color:#95a5a6; }}
  .stat b {{ display:block; font-size:15px; color:#fff; font-variant-numeric:tabular-nums; }}
  .legend {{ font-size:12px; line-height:1.7; color:#bdc3c7; }}
  .foot {{ font-size:10.5px; color:#7f8c8d; margin-top:14px; line-height:1.5; }}

  /* acilir/kapanir buton */
  #toggle {{
    position:absolute; top:50%; left:330px; z-index:1101; transform:translateY(-50%);
    background:#141a22; color:#fff; border:0; border-left:0; border-radius:0 6px 6px 0;
    padding:16px 7px; font-size:15px; cursor:pointer; transition:left .3s ease;
    box-shadow:3px 0 8px rgba(0,0,0,.4); font-weight:bold;
  }}
  #toggle.closed {{ left:0; }}

  #search {{
    position:absolute; top:12px; right:12px; z-index:1100; width:250px;
    background:rgba(20,26,34,.95); border-radius:6px; padding:8px 10px;
    color:#ecf0f1; border:1px solid #34495e; font-size:13px;
    box-shadow:0 2px 8px rgba(0,0,0,.4);
  }}
  #search input {{ width:100%; background:#22303f; border:1px solid #34495e;
    border-radius:4px; padding:5px 7px; color:#fff; font-size:13px; box-sizing:border-box; }}
  #searchres {{ max-height:190px; overflow-y:auto; margin-top:6px; }}
  #searchres div {{ padding:4px 6px; font-size:12px; cursor:pointer; border-radius:3px; }}
  #searchres div:hover {{ background:#2980b9; }}

  .leaflet-popup-content {{ font-size:13px; line-height:1.55; min-width:240px; }}
  .leaflet-popup-content b {{ color:#1B365D; }}
  .ptitle {{ font-size:14px; font-weight:bold; color:#c0392b; margin-bottom:4px; }}
  table.popt {{ border-collapse:collapse; width:100%; font-size:12px; }}
  table.popt td {{ padding:2px 4px; border-bottom:1px solid #ecf0f1; }}
  table.popt td:first-child {{ color:#7f8c8d; width:44%; }}
  .coord {{ font-family:Consolas,monospace; font-size:11.5px; }}
</style>
</head>
<body>
<div id="map"></div>

<button id="toggle" title="Paneli aç/kapat">«</button>

<div id="search">
  <input id="q" type="text" placeholder="Yol / ilçe ara ve git...">
  <div id="searchres"></div>
</div>

<div id="panel">
  <h1>ANKARA YOL GÜVENLİĞİ<small>{basemap['title']}</small></h1>
  <div>
    <span class="badge red" id="bTotal">-</span>
    <span class="badge">EPSG:4326 / UTM 36N</span>
    <span class="badge">__TARIH__</span>
  </div>

  <div class="stats">
    <div class="stat">Görünen nokta<b id="sVis">-</b></div>
    <div class="stat">Kritik kara nokta<b id="sKritik">-</b></div>
    <div class="stat">Yüksek risk<b id="sYuksek">-</b></div>
    <div class="stat">Ortalama risk<b id="sOrt">-</b></div>
  </div>

  <div class="sec">
    <h2>Risk Seviyesi</h2>
    <div id="levelRows"></div>
  </div>

  <div class="sec">
    <h2>Kusur Türü</h2>
    <div id="kindRows"></div>
  </div>

  <div class="sec">
    <h2>İlçe Filtresi</h2>
    <select id="ilceSel"><option value="-1">Tüm ilçeler</option></select>
    <div class="btnrow">
      <button class="btn" id="btnKritik">Sadece Kritik + Yüksek</button>
      <button class="btn alt" id="btnAll">Tümünü Göster</button>
    </div>
    <div style="margin-top:10px">
      <h2 style="font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:#3498db;margin:0 0 6px 0">Eğim Filtresi (DEM)</h2>
      <select id="egimSel">
        <option value="-1">Tüm eğimler</option>
        <option value="0">Düz zeminde (< %2)</option>
        <option value="2">Hafif eğimli (≥ %2)</option>
        <option value="5">Eğimli (≥ %5)</option>
        <option value="8">Dik (≥ %8)</option>
        <option value="12">Çok dik (≥ %12)</option>
      </select>
    </div>
  </div>

  <div class="sec">
    <h2>Lejant</h2>
    <div class="legend" id="legend"></div>
  </div>

  <div class="foot">
    Veri: OpenStreetMap (Geofabrik Turkey PBF) — geometrik ve topolojik kusur
    taraması, 30 m kümeleme, YGE 0-100 risk modeli. Kot/eğim: Copernicus DEM
    GLO-30 (30 m, ESA) — boyuna eğim g = Δz/Δs. Nokta koordinatları WGS84
    (lon/lat) ve WGS84 / UTM 36N (EPSG:32636) olarak verilmiştir.
    ESRI altlıkları © Esri, HERE, Garmin, FAO, NOAA, USGS, OpenStreetMap
    katkıda bulunanlar.
  </div>
</div>

<script>
var D = /*__DATA__*/null;

/* ---------- harita ---------- */
var map = L.map('map', {{ zoomControl:false, preferCanvas:true }})
          .setView([39.9334, 32.8597], 11);
L.control.zoom({{ position:'bottomright' }}).addTo(map);
L.control.scale({{ imperial:false, position:'bottomright' }}).addTo(map);

{base_layers_js_str}
{overlay_layers_js_str}

var basemap = '{basemap['id']}';
L.control.layers({{
  {base_layers_dict}
}}, {{}}, {{ collapsed:true, position:'bottomright' }}).addTo(map);

/* ---------- veri ---------- */
var N = D.n_kusur;
var vis = new Int32Array(N);
var nVis = N;

function computeVisible(){{
  var lvOn = levelOn, kdOn = kindOn, il = ilceSel;
  var n = 0;
  for (var i = 0; i < N; i++){{
    if (!lvOn[D.l[i]]) continue;
    if (!kdOn[D.k[i]]) continue;
    if (il >= 0 && D.i[i] !== il) continue;
    var eg = D.e ? D.e[i] : -1;
    if (egimSel === 0 && !(eg >= 0 && eg < 2)) continue;
    if (egimSel > 0 && !(eg >= egimSel)) continue;
    vis[n++] = i;
  }}
  nVis = n;
}}

/* ---------- canvas layer ---------- */
var CanvasLayer = L.Layer.extend({{
  onAdd: function(m){{
    this._map = m;
    this._c = L.DomUtil.create('canvas', 'leaflet-zoom-hide');
    this._c.style.position = 'absolute';
    this._c.style.left = '0';
    this._c.style.top = '0';
    this._c.style.pointerEvents = 'none';
    m.getPanes().overlayPane.appendChild(this._c);
    m.on('move zoom viewreset resize moveend zoomend', this._draw, this);
    this._draw();
  }},
  onRemove: function(m){{
    L.DomUtil.remove(this._c);
    m.off('move zoom viewreset resize moveend zoomend', this._draw, this);
  }},
  _draw: function(){{
    var m = this._map, c = this._c;
    var size = m.getSize();
    var dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(size.x*dpr) || c.height !== Math.round(size.y*dpr)){{
      c.width = Math.round(size.x*dpr); c.height = Math.round(size.y*dpr);
      c.style.width = size.x+'px'; c.style.height = size.y+'px';
    }}
    var ctx = c.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.clearRect(0,0,size.x,size.y);

    var z = m.getZoom();
    var rad = z >= 14 ? 4.2 : (z >= 12 ? 3.2 : (z >= 10 ? 2.4 : 1.8));
    var cols = D.levelColors;

    var bounds = m.getBounds();
    var maxLat = bounds.getNorth(), minLat = bounds.getSouth();
    var maxLng = bounds.getEast(), minLng = bounds.getWest();

    for (var lvl = 3; lvl >= 0; lvl--){{ 
      if (!levelOn[lvl]) continue;
      ctx.fillStyle = cols[lvl];
      ctx.beginPath();
      for (var vi = 0; vi < nVis; vi++){{
        var i = vis[vi];
        if (D.l[i] !== lvl) continue;
        var lat = D.lat[i], lng = D.lon[i];
        if (lat < minLat || lat > maxLat || lng < minLng || lng > maxLng) continue;
        var pt = m.latLngToLayerPoint([lat, lng]);
        var cx = pt.x, cy = pt.y;
        if (cx < -6 || cx > size.x+6 || cy < -6 || cy > size.y+6) continue;
        ctx.moveTo(cx+rad, cy);
        ctx.arc(cx, cy, rad, 0, 6.2832);
      }}
      ctx.fill();
    }}
    if (levelOn[0]){{
      ctx.strokeStyle = 'rgba(255,255,255,.85)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (var vj = 0; vj < nVis; vj++){{
        var j = vis[vj];
        if (D.l[j] !== 0) continue;
        var lat = D.lat[j], lng = D.lon[j];
        if (lat < minLat || lat > maxLat || lng < minLng || lng > maxLng) continue;
        var pt = m.latLngToLayerPoint([lat, lng]);
        var px = pt.x, py = pt.y;
        if (px < -6 || px > size.x+6 || py < -6 || py > size.y+6) continue;
        ctx.moveTo(px+rad, py);
        ctx.arc(px, py, rad, 0, 6.2832);
      }}
      ctx.stroke();
    }}
  }}
}});

/* ---------- panel durumu ---------- */
var levelOn = [true,true,true,true];
var kindOn  = D.kinds.map(function(){{ return true; }});
var ilceSel = -1;
var egimSel = -1;

var layer = new CanvasLayer();
layer.addTo(map);

function fmt(n){{ return n.toLocaleString('tr-TR'); }}

function refreshStats(){{
  var counts = [0,0,0,0], kcounts = D.kinds.map(function(){{ return 0; }});
  var sum = 0;
  for (var vi = 0; vi < nVis; vi++){{
    var i = vis[vi];
    counts[D.l[i]]++;
    kcounts[D.k[i]]++;
    sum += D.r[i];
  }}
  document.getElementById('sVis').textContent = fmt(nVis);
  document.getElementById('sKritik').textContent = fmt(counts[0]);
  document.getElementById('sYuksek').textContent = fmt(counts[1]);
  document.getElementById('sOrt').textContent = nVis ? (sum/nVis).toFixed(1) : '-';
  for (var l = 0; l < 4; l++){{
    var el = document.getElementById('lc'+l);
    if (el) el.textContent = fmt(counts[l]);
  }}
  for (var k = 0; k < D.kinds.length; k++){{
    var ek = document.getElementById('kc'+k);
    if (ek) ek.textContent = fmt(kcounts[k]);
  }}
}}

function refresh(){{ computeVisible(); layer._draw(); refreshStats(); }}

/* ---------- panel kurulumu ---------- */
(function(){{
  var lr = document.getElementById('levelRows');
  for (var l = 0; l < D.levels.length; l++){{
    (function(l){{
      var row = document.createElement('label');
      row.className = 'cbrow';
      row.innerHTML = '<input type="checkbox" checked>' +
        '<span class="dot" style="background:'+D.levelColors[l]+'"></span>' +
        D.levels[l] + '<span class="cnt" id="lc'+l+'">-</span>';
      row.querySelector('input').addEventListener('change', function(e){{
        levelOn[l] = e.target.checked; refresh();
      }});
      lr.appendChild(row);
    }})(l);
  }}

  var kr = document.getElementById('kindRows');
  var kcolors = ['#c0392b','#2980b9','#8e44ad','#16a085','#7f8c8d','#2c3e50'];
  for (var k = 0; k < D.kinds.length; k++){{
    (function(k){{
      var row = document.createElement('label');
      row.className = 'cbrow';
      row.innerHTML = '<input type="checkbox" checked>' +
        '<span class="dot" style="background:'+kcolors[k]+'"></span>' +
        D.kindLabels[k] + '<span class="cnt" id="kc'+k+'">-</span>';
      row.querySelector('input').addEventListener('change', function(e){{
        kindOn[k] = e.target.checked; refresh();
      }});
      kr.appendChild(row);
    }})(k);
  }}

  var sel = document.getElementById('ilceSel');
  for (var i = 0; i < {len(ilceler)}; i++){{
    var o = document.createElement('option');
    o.value = i; o.textContent = D.ilceler[i];
    sel.appendChild(o);
  }}
  sel.addEventListener('change', function(e){{
    ilceSel = parseInt(e.target.value, 10); refresh();
  }});

  document.getElementById('egimSel').addEventListener('change', function(e){{
    egimSel = parseInt(e.target.value, 10); refresh();
  }});

  document.getElementById('btnKritik').addEventListener('click', function(){{
    levelOn = [true,true,false,false];
    var boxes = document.querySelectorAll('#levelRows input');
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = levelOn[i];
    refresh();
  }});
  document.getElementById('btnAll').addEventListener('click', function(){{
    levelOn = [true,true,true,true];
    kindOn = D.kinds.map(function(){{ return true; }});
    ilceSel = -1;
    egimSel = -1;
    document.getElementById('egimSel').value = '-1';
    document.getElementById('ilceSel').value = '-1';
    var b1 = document.querySelectorAll('#levelRows input');
    for (var i = 0; i < b1.length; i++) b1[i].checked = true;
    var b2 = document.querySelectorAll('#kindRows input');
    for (var j = 0; j < b2.length; j++) b2[j].checked = true;
    refresh();
  }});

  document.getElementById('legend').innerHTML =
    '<span class="dot" style="background:#e74c3c"></span> Kritik Kara Nokta (≥75)<br>' +
    '<span class="dot" style="background:#e67e22"></span> Yüksek Risk (55-74)<br>' +
    '<span class="dot" style="background:#f1c40f"></span> Orta Risk (35-54)<br>' +
    '<span class="dot" style="background:#27ae60"></span> Düşük Risk (<35)<br>' +
    '<span style="color:#95a5a6">Nokta boyutu yaklaştıkça büyür; kritik noktalar beyaz halkalıdır.</span>';

  document.getElementById('bTotal').textContent = fmt(N) + ' tehlike bölgesi';
}})();

/* ---------- panel ac/kapat ---------- */
document.getElementById('toggle').addEventListener('click', function(){{
  var p = document.getElementById('panel');
  var t = document.getElementById('toggle');
  var closed = p.classList.toggle('closed');
  t.classList.toggle('closed', closed);
  t.textContent = closed ? '»' : '«';
  setTimeout(function(){{ map.invalidateSize(); }}, 320);
}});

/* ---------- tiklama -> popup ---------- */
function popupHtml(i){{
  var name = D.names[D.m[i]] || 'İsimsiz Aks';
  var hw = D.hws[D.h[i]] || '-';
  var kindL = D.kindLabels[D.k[i]];
  var lvlL = D.levels[D.l[i]];
  var lvlC = D.levelColors[D.l[i]];
  var unit = ['m', 'm', '°', '', 'm', '%'][D.k[i]];
  return '<div class="ptitle">' + kindL + '</div>' +
    '<table class="popt">' +
    '<tr><td>Kusur değeri</td><td>' + D.v[i] + ' ' + unit + '</td></tr>' +
    '<tr><td>Risk seviyesi</td><td><b style="color:'+lvlC+'">' + lvlL +
      ' (' + D.r[i].toFixed(1) + ')</b></td></tr>' +
    '<tr><td>İlçe</td><td>' + D.ilceler[D.i[i]] + '</td></tr>' +
    '<tr><td>Yol / Sokak</td><td>' + name + '</td></tr>' +
    '<tr><td>OSM sınıfı</td><td>' + hw + '</td></tr>' +
    '<tr><td>İşletme hızı</td><td>' + D.s[i] + ' km/s</td></tr>' +
    '<tr><td>Kot (DEM)</td><td>' + (D.z && D.z[i] >= 0 ? D.z[i] + ' m' : '-') + '</td></tr>' +
    '<tr><td>Eğim (DEM)</td><td>' + (D.e && D.e[i] >= 0 ? '%' + D.e[i].toFixed(1) : '-') + '</td></tr>' +
    '<tr><td>Koordinat (UTM 36N)</td><td class="coord">X: ' + D.x[i] +
      ' m<br>Y: ' + D.y[i] + ' m</td></tr>' +
    '<tr><td>Koordinat (WGS84)</td><td class="coord">lon: ' +
      D.lon[i].toFixed(5) + '<br>lat: ' + D.lat[i].toFixed(5) + '</td></tr>' +
    '<tr><td>OSM id</td><td>' + (D.osmid ? D.osmid[i] : '-') + '</td></tr>' +
    '</table>';
}}

map.on('click', function(e){{
  var best = -1, bestD = 12*12;
  for (var vi = 0; vi < nVis; vi++){{
    var i = vis[vi];
    var pt = map.latLngToLayerPoint([D.lat[i], D.lon[i]]);
    var dx = pt.x - e.layerPoint.x;
    var dy = pt.y - e.layerPoint.y;
    var d = dx*dx + dy*dy;
    if (d < bestD){{ bestD = d; best = i; }}
  }}
  if (best >= 0){{
    L.popup().setLatLng([D.lat[best], D.lon[best]]).setContent(popupHtml(best)).openOn(map);
  }}
}});

/* ---------- arama ---------- */
document.getElementById('q').addEventListener('input', function(e){{
  var q = e.target.value.trim().toLocaleLowerCase('tr');
  var box = document.getElementById('searchres');
  box.innerHTML = '';
  if (q.length < 2) return;
  var shown = 0;
  for (var i = 0; i < N && shown < 12; i++){{
    var nm = D.names[D.m[i]];
    var il = D.ilceler[D.i[i]];
    if ((nm && nm.toLocaleLowerCase('tr').indexOf(q) >= 0) ||
        il.toLocaleLowerCase('tr').indexOf(q) >= 0){{
      var d = document.createElement('div');
      d.textContent = (nm || 'İsimsiz') + ' — ' + il;
      (function(idx){{
        d.addEventListener('click', function(){{
          map.setView([D.lat[idx], D.lon[idx]], 16);
          L.popup().setLatLng([D.lat[idx], D.lon[idx]])
                   .setContent(popupHtml(idx)).openOn(map);
        }});
      }})(i);
      box.appendChild(d);
      shown++;
    }}
  }}
}});

refresh();
</script>
</body>
</html>"""
    return html.replace("/*__DATA__*/null", data_json).replace("__TARIH__", time.strftime("%d.%m.%Y"))


def main():
    t0 = time.time()
    data_json, N, ilceler = load_data()

    print("2. 4 ESRI haritası yazılıyor...", flush=True)
    for bm in BASEMAPS:
        out_path = os.path.join(BASE, bm["file"])
        html = build_html(bm, data_json, N, ilceler)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"   -> {bm['file']} ({bm['title']})", flush=True)

    print(f"Toplam sure: {time.time()-t0:.1f} sn", flush=True)


if __name__ == "__main__":
    main()