#!/usr/bin/env python3
"""
GPX 3D Terrain Map Animator
Genera un mapa 3D realista del terreno con textura satelital real
y animación progresiva del recorrido.

Uso:
    python map_animate.py ruta.gpx
    python map_animate.py ruta.gpx --animate --video video.mp4
"""

import sys
import os
import time
import math
import io
import json
import argparse
import hashlib
import requests
import numpy as np
import gpxpy
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
from PIL import Image
import pyvista as pv
import cv2

# ─────────────────────────────────────────────
#  CACHE
# ─────────────────────────────────────────────

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _elev_cache_key(lat_min, lat_max, lon_min, lon_max, grid_size):
    s = f"elev:{lat_min:.6f}:{lat_max:.6f}:{lon_min:.6f}:{lon_max:.6f}:{grid_size}"
    return hashlib.md5(s.encode()).hexdigest()[:16]


def _sat_cache_key(lat_min, lat_max, lon_min, lon_max, zoom):
    s = f"sat:{lat_min:.6f}:{lat_max:.6f}:{lon_min:.6f}:{lon_max:.6f}:{zoom}"
    return hashlib.md5(s.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────
#  PARSEO GPX
# ─────────────────────────────────────────────

def parse_gpx(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append((pt.latitude, pt.longitude, pt.elevation))

    if not points:
        for route in gpx.routes:
            for pt in route.points:
                points.append((pt.latitude, pt.longitude, pt.elevation))

    name = gpx.name or (gpx.tracks[0].name if gpx.tracks else None)
    return points, name


# ─────────────────────────────────────────────
#  ELEVACIÓN (API)
# ─────────────────────────────────────────────

def fetch_opentopodata(locations, dataset="srtm30m"):
    results = []
    batch_size = 100
    total = len(locations)

    for i in range(0, total, batch_size):
        batch = locations[i : i + batch_size]
        loc_str = "|".join(f"{lat},{lon}" for lat, lon in batch)
        url = f"https://api.opentopodata.org/v1/{dataset}?locations={loc_str}"
        try:
            resp = requests.get(url, timeout=30)
            data = resp.json()
            if data.get("status") == "OK":
                results += [r.get("elevation") or 0 for r in data["results"]]
            else:
                results += [None] * len(batch)
        except Exception as e:
            print(f"  ⚠  opentopodata error: {e}")
            results += [None] * len(batch)

        bn = i // batch_size + 1
        pct = min(bn * batch_size, total)
        print(f"  Elevación: {pct}/{total} puntos", end="\r")
        if i + batch_size < total:
            time.sleep(1.1)

    print()
    return results


def fetch_open_elevation(locations):
    results = []
    batch_size = 512
    for i in range(0, len(locations), batch_size):
        batch = locations[i : i + batch_size]
        payload = {"locations": [{"latitude": la, "longitude": lo} for la, lo in batch]}
        try:
            resp = requests.post(
                "https://api.open-elevation.com/api/v1/lookup",
                json=payload, timeout=60
            )
            data = resp.json()
            results += [r.get("elevation") or 0 for r in data["results"]]
        except Exception as e:
            print(f"  ⚠  open-elevation error: {e}")
            results += [None] * len(batch)
        if i + batch_size < len(locations):
            time.sleep(0.5)
    return results


def get_elevation_grid(lat_min, lat_max, lon_min, lon_max, grid_size):
    cache_key = _elev_cache_key(lat_min, lat_max, lon_min, lon_max, grid_size)
    cache_path = os.path.join(_CACHE_DIR, f"elev_{cache_key}.npz")

    if os.path.exists(cache_path):
        print("  Cargando elevación desde cache...")
        data = np.load(cache_path)
        return data["lat_grid"], data["lon_grid"], data["elev_grid"]

    lats = np.linspace(lat_min, lat_max, grid_size)
    lons = np.linspace(lon_min, lon_max, grid_size)
    lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")

    locations = [
        (lat_grid[i, j], lon_grid[i, j])
        for i in range(grid_size)
        for j in range(grid_size)
    ]

    print("  Usando opentopodata.org (SRTM 30m)...")
    elevs = fetch_opentopodata(locations)

    if all(e is None or e == 0 for e in elevs):
        print("  Fallback a open-elevation.com...")
        elevs = fetch_open_elevation(locations)

    arr = np.array([e if e is not None else np.nan for e in elevs])
    if np.isnan(arr).any():
        mean_e = np.nanmean(arr)
        arr = np.where(np.isnan(arr), mean_e, arr)

    elev_grid = arr.reshape(grid_size, grid_size)
    np.savez(cache_path, lat_grid=lat_grid, lon_grid=lon_grid, elev_grid=elev_grid)
    print(f"  Cache guardado: {cache_path}")
    return lat_grid, lon_grid, elev_grid


# ─────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (
        np.sin((phi2 - phi1) / 2) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    )
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c


def cumulative_distance(lats, lons):
    dists = [0.0]
    for i in range(1, len(lats)):
        dists.append(dists[-1] + haversine(lats[i - 1], lons[i - 1], lats[i], lons[i]))
    return np.array(dists)


# ─────────────────────────────────────────────
#  SATÉLITE (ESRI tiles)
# ─────────────────────────────────────────────

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def latlon_to_tilexy(lat, lon, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def tilexy_to_latlon(xtile, ytile, zoom):
    n = 2.0 ** zoom
    lon_deg = xtile / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
    lat_deg = math.degrees(lat_rad)
    return lat_deg, lon_deg


def select_zoom(lat_min, lat_max, lon_min, lon_max):
    ext_ns = haversine(lat_min, lon_min, lat_max, lon_min) / 1000
    ext_ew = haversine(lat_min, lon_min, lat_min, lon_max) / 1000
    extent = max(ext_ns, ext_ew)
    if extent < 2:
        return 16
    elif extent < 5:
        return 15
    elif extent < 10:
        return 14
    elif extent < 25:
        return 13
    elif extent < 60:
        return 12
    else:
        return 11


def download_satellite_image(lat_min, lat_max, lon_min, lon_max, zoom=None):
    if zoom is None:
        zoom = select_zoom(lat_min, lat_max, lon_min, lon_max)

    cache_key = _sat_cache_key(lat_min, lat_max, lon_min, lon_max, zoom)
    cache_path = os.path.join(_CACHE_DIR, f"sat_{cache_key}.png")
    meta_path = os.path.join(_CACHE_DIR, f"sat_{cache_key}.json")

    if os.path.exists(cache_path) and os.path.exists(meta_path):
        print("  Cargando imagen satelital desde cache...")
        img = Image.open(cache_path)
        with open(meta_path, "r") as f:
            meta = json.load(f)
        return img, meta["lon_min"], meta["lon_max"], meta["lat_min"], meta["lat_max"]

    print(f"  Zoom satelital: {zoom}")
    x_min, y_min = latlon_to_tilexy(lat_max, lon_min, zoom)
    x_max, y_max = latlon_to_tilexy(lat_min, lon_max, zoom)

    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min

    nx = x_max - x_min + 1
    ny = y_max - y_min + 1
    print(f"  Tiles: {nx}x{ny} ({nx*ny} total)")

    tile_size = 256
    img = Image.new("RGB", (nx * tile_size, ny * tile_size))

    session = requests.Session()
    for tx in range(x_min, x_max + 1):
        for ty in range(y_min, y_max + 1):
            url = TILE_URL.format(z=zoom, y=ty, x=tx)
            try:
                r = session.get(url, timeout=15)
                r.raise_for_status()
                tile = Image.open(io.BytesIO(r.content))
                px = (tx - x_min) * tile_size
                py = (ty - y_min) * tile_size
                img.paste(tile, (px, py))
            except Exception as e:
                print(f"    ⚠ Tile ({tx},{ty}) error: {e}")

    tile_lat_max, _ = tilexy_to_latlon(x_min, y_min, zoom)
    tile_lat_min, _ = tilexy_to_latlon(x_min, y_max + 1, zoom)
    _, tile_lon_min = tilexy_to_latlon(x_min, y_min, zoom)
    _, tile_lon_max = tilexy_to_latlon(x_max + 1, y_min, zoom)

    img.save(cache_path)
    with open(meta_path, "w") as f:
        json.dump({
            "lon_min": tile_lon_min, "lon_max": tile_lon_max,
            "lat_min": tile_lat_min, "lat_max": tile_lat_max,
        }, f)
    print(f"  Cache guardado: {cache_path}")

    return img, tile_lon_min, tile_lon_max, tile_lat_min, tile_lat_max


# ─────────────────────────────────────────────
#  RENDER PRINCIPAL (PyVista)
# ─────────────────────────────────────────────

def create_terrain_map(
    gpx_file,
    output_file="terrain_map.png",
    grid_size=80,
    title=None,
    view_elev=28,
    view_azim=-55,
    sat_zoom=None,
    z_exaggeration=8.0,
    animate=False,
    video_file="animation.mp4",
    video_duration=10,
    video_fps=30,
    preview=False,
    padding=0.004,
):
    BG = "#060a0e"

    print(f"\n{'━'*52}")
    print("  GPX 3D Terrain Map Animator — PyVista Edition")
    print(f"{'━'*52}\n")

    # 1. Parse
    print("[1/5] Parseando GPX…")
    track_points, gpx_name = parse_gpx(gpx_file)
    lats = np.array([p[0] for p in track_points])
    lons = np.array([p[1] for p in track_points])
    eles = np.array([p[2] if p[2] is not None else np.nan for p in track_points])
    print(f"  {len(track_points)} puntos de track encontrados")

    # 2. Elevación del terreno
    print("\n[2/5] Descargando datos de elevación…")
    pad = padding
    lat_min, lat_max = lats.min() - pad, lats.max() + pad
    lon_min, lon_max = lons.min() - pad, lons.max() + pad

    lat_grid, lon_grid, elev_grid = get_elevation_grid(
        lat_min, lat_max, lon_min, lon_max, grid_size
    )

    grid_pts = np.column_stack([lat_grid.flatten(), lon_grid.flatten()])
    track_pts = np.column_stack([lats, lons])
    interp_eles = griddata(grid_pts, elev_grid.flatten(), track_pts, method="linear")
    track_z = np.where(np.isnan(interp_eles), np.nanmean(elev_grid), interp_eles)

    # 3. Satélite
    print("\n[3/5] Descargando imagen satelital…")
    sat_img, sat_lon_min, sat_lon_max, sat_lat_min, sat_lat_max = download_satellite_image(
        lat_min, lat_max, lon_min, lon_max, zoom=sat_zoom
    )
    print(f"  Imagen satelital: {sat_img.size}")

    # 4. Métricas
    print("\n[4/5] Calculando métricas…")
    dists = cumulative_distance(lats, lons)
    total_dist = dists[-1] / 1000
    gain = np.sum(np.maximum(np.diff(track_z), 0))
    loss = np.sum(np.maximum(-np.diff(track_z), 0))
    print(f"  Distancia total: {total_dist:.1f} km")
    print(f"  Desnivel +{gain:.0f} m / -{loss:.0f} m")
    print(f"  Altitud: {track_z.min():.0f} – {track_z.max():.0f} m")

    # Coordenadas planas
    x_grid = (lon_grid - lon_min) * 111_320 * np.cos(np.radians(lat_grid.mean()))
    y_grid = (lat_grid - lat_min) * 111_320
    track_x = (lons - lon_min) * 111_320 * np.cos(np.radians(lat_grid.mean()))
    track_y = (lats - lat_min) * 111_320

    # 5. Render 3D
    print("\n[5/5] Renderizando escena 3D con PyVista…")
    elev_smooth = gaussian_filter(elev_grid, sigma=0.8)
    elev_min = elev_smooth.min()
    elev_max = elev_smooth.max()
    elev_range = max(elev_max - elev_min, 1)
    elev_base = elev_min - elev_range * 0.35
    exag = z_exaggeration

    z_top = (elev_smooth - elev_min) * exag
    z_base = (elev_base - elev_min) * exag
    track_z_exag = (track_z - elev_min) * exag + (6 * exag)

    # --- Malla terreno (top) ---
    points_3d = np.empty((grid_size, grid_size, 3))
    points_3d[:, :, 0] = x_grid
    points_3d[:, :, 1] = y_grid
    points_3d[:, :, 2] = z_top

    terrain = pv.StructuredGrid()
    terrain.points = points_3d.reshape(-1, 3)
    terrain.dimensions = (grid_size, grid_size, 1)

    origin = [x_grid.min(), y_grid.min(), 0]
    point_u = [x_grid.max(), y_grid.min(), 0]
    point_v = [x_grid.min(), y_grid.max(), 0]
    terrain = terrain.texture_map_to_plane(origin=origin, point_u=point_u, point_v=point_v)

    sat_array = np.array(sat_img)
    texture = pv.numpy_to_texture(sat_array)

    # --- Paredes ---
    walls = []
    def make_wall(xline, yline, zline):
        n = len(xline)
        z_exag_line = (zline - elev_min) * exag
        pts = np.empty((n, 2, 3))
        for i in range(n):
            pts[i, 0] = [xline[i], yline[i], z_exag_line[i]]
            pts[i, 1] = [xline[i], yline[i], z_base]
        wall = pv.StructuredGrid()
        wall.points = pts.reshape(-1, 3)
        wall.dimensions = (n, 2, 1)
        walls.append(wall)

    make_wall(x_grid[0, :],  y_grid[0, :],  elev_smooth[0, :])
    make_wall(x_grid[-1, :], y_grid[-1, :], elev_smooth[-1, :])
    make_wall(x_grid[:, 0],  y_grid[:, 0],  elev_smooth[:, 0])
    make_wall(x_grid[:, -1], y_grid[:, -1], elev_smooth[:, -1])

    max_dim = max(x_grid.max() - x_grid.min(), y_grid.max() - y_grid.min())
    tube_radius = max_dim * 0.003
    glow_radius = max_dim * 0.010
    sph_r = max_dim * 0.012

    # --- Plotter ---
    plotter = pv.Plotter(off_screen=True, window_size=(2560, 1440))
    plotter.background_color = BG

    plotter.add_mesh(terrain, texture=texture, smooth_shading=True,
                     specular=0.15, ambient=0.3, diffuse=0.8, show_scalar_bar=False)

    for wall in walls:
        z_vals = wall.points[:, 2]
        rel_h = np.clip((z_vals - z_base) / max(z_top.max() - z_base, 1), 0, 1)
        wall.point_data["height"] = rel_h
        plotter.add_mesh(wall, scalars="height", cmap=["#3a0000", "#ff2200"],
                         smooth_shading=True, ambient=0.3, diffuse=0.7,
                         show_scalar_bar=False)

    floor = pv.Plane(
        center=((x_grid.min()+x_grid.max())/2, (y_grid.min()+y_grid.max())/2, z_base - 5*exag),
        direction=(0, 0, 1),
        i_size=(x_grid.max()-x_grid.min())*1.1,
        j_size=(y_grid.max()-y_grid.min())*1.1,
    )
    plotter.add_mesh(floor, color="#0a0000", opacity=0.95)

    plotter.add_light(pv.Light(position=(1, 0.5, 1), color='#ffffff', intensity=0.6))
    plotter.add_light(pv.Light(position=(-0.5, -1, 0.8), color='#ffeedd', intensity=0.3))
    plotter.add_light(pv.Light(light_type='headlight', color='#ffffff', intensity=0.2))

    # Cámara
    z_range_vis = z_top.max() - z_base
    center = np.array([
        (x_grid.min() + x_grid.max()) / 2,
        (y_grid.min() + y_grid.max()) / 2,
        z_base + z_range_vis * 0.4,
    ])
    dist = max(x_grid.max() - x_grid.min(), y_grid.max() - y_grid.min()) * 1.5
    elev_rad = math.radians(view_elev)
    azim_rad = math.radians(view_azim)
    cam_x = center[0] + dist * math.cos(elev_rad) * math.cos(azim_rad)
    cam_y = center[1] + dist * math.cos(elev_rad) * math.sin(azim_rad)
    cam_z = center[2] + dist * math.sin(elev_rad) * 0.6

    plotter.camera.position = (cam_x, cam_y, cam_z)
    plotter.camera.focal_point = tuple(center)
    plotter.camera.up = (0, 0, 1)
    plotter.camera.view_angle = 55

    if not animate:
        # --- Modo estático o preview: ruta completa ---
        route_pts = np.column_stack([track_x, track_y, track_z_exag])
        n_r = len(route_pts)
        route_poly = pv.PolyData(route_pts)
        route_poly.lines = np.hstack([[n_r], np.arange(n_r)])

        tube_main = route_poly.tube(radius=tube_radius, n_sides=16)
        tube_glow = route_poly.tube(radius=glow_radius, n_sides=16)

        start_sph = pv.Sphere(radius=sph_r, center=(track_x[0], track_y[0], track_z_exag[0]))
        end_sph = pv.Cube(center=(track_x[-1], track_y[-1], track_z_exag[-1]),
                          x_length=sph_r*1.8, y_length=sph_r*1.8, z_length=sph_r*1.8)

        plotter.add_mesh(tube_glow, color="white", opacity=0.10, smooth_shading=True)
        plotter.add_mesh(tube_main, color="white", opacity=0.95, smooth_shading=True)
        plotter.add_mesh(start_sph, color="#ff6600", smooth_shading=True)
        plotter.add_mesh(end_sph, color="#ff6600", smooth_shading=True)

        plotter.show(auto_close=True)
        out = output_file if not preview else output_file.replace(".png", "_preview.png")
        plotter.screenshot(out, window_size=(2560, 1440))
        print(f"\n✓ {'Preview' if preview else 'Mapa'} guardado en: {out}")
        return

    # --- Modo animación ---
    num_frames = int(video_duration * video_fps)
    print(f"  Generando {num_frames} frames ({video_duration}s @ {video_fps}fps)…")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(video_file, fourcc, video_fps, (2560, 1440))
    if not writer.isOpened():
        print(f"  ERROR: No se pudo abrir el video writer para: {video_file}")
        return

    n_points = len(track_x)
    cam_rotation_total = 25.0

    start_sph = pv.Sphere(radius=sph_r, center=(track_x[0], track_y[0], track_z_exag[0]))
    plotter.add_mesh(start_sph, color="#ff6600", smooth_shading=True)

    txt_actor = plotter.add_text("0%", position="lower_right", font_size=14,
                                 color="white", name="progress_text")

    for f in range(num_frames):
        progress = f / (num_frames - 1) if num_frames > 1 else 1.0
        idx = min(int(progress * (n_points - 1)), n_points - 1)

        # --- Rotación de cámara ---
        current_azim = view_azim + cam_rotation_total * progress
        elev_rad = math.radians(view_elev)
        azim_rad = math.radians(current_azim)
        cam_x = center[0] + dist * math.cos(elev_rad) * math.cos(azim_rad)
        cam_y = center[1] + dist * math.cos(elev_rad) * math.sin(azim_rad)
        cam_z = center[2] + dist * math.sin(elev_rad) * 0.6
        plotter.camera.position = (cam_x, cam_y, cam_z)

        # --- Sub-ruta progresiva ---
        actors = []
        if idx > 0:
            sub_x = track_x[:idx+1]
            sub_y = track_y[:idx+1]
            sub_z = track_z_exag[:idx+1]
            route_pts = np.column_stack([sub_x, sub_y, sub_z])
            n_r = len(route_pts)
            route_poly = pv.PolyData(route_pts)
            route_poly.lines = np.hstack([[n_r], np.arange(n_r)])

            tube_main = route_poly.tube(radius=tube_radius, n_sides=16)
            tube_glow = route_poly.tube(radius=glow_radius, n_sides=16)

            actors.append(plotter.add_mesh(tube_glow, color="white", opacity=0.10, smooth_shading=True))
            actors.append(plotter.add_mesh(tube_main, color="white", opacity=0.95, smooth_shading=True))

        # --- Flecha direccional en la punta ---
        if idx < n_points - 1:
            dx = track_x[idx+1] - track_x[idx]
            dy = track_y[idx+1] - track_y[idx]
            dz = track_z_exag[idx+1] - track_z_exag[idx]
        else:
            dx = track_x[idx] - track_x[idx-1]
            dy = track_y[idx] - track_y[idx-1]
            dz = track_z_exag[idx] - track_z_exag[idx-1]

        direction = np.array([dx, dy, dz])
        norm = np.linalg.norm(direction)
        if norm > 0:
            direction = direction / norm

        arrow = pv.Cone(
            center=(track_x[idx], track_y[idx], track_z_exag[idx]),
            direction=direction,
            radius=sph_r * 1.2,
            height=sph_r * 2.5,
        )
        actors.append(plotter.add_mesh(arrow, color="#ffaa00", smooth_shading=True))

        # --- Marcador de fin ---
        if idx >= n_points - 2:
            end_sph = pv.Cube(center=(track_x[-1], track_y[-1], track_z_exag[-1]),
                              x_length=sph_r*1.8, y_length=sph_r*1.8, z_length=sph_r*1.8)
            actors.append(plotter.add_mesh(end_sph, color="#ff6600", smooth_shading=True))

        # --- Actualizar texto de progreso ---
        pct = int(progress * 100)
        plotter.remove_actor(txt_actor)
        txt_actor = plotter.add_text(f"{pct}%", position="lower_right", font_size=14,
                                     color="white", name="progress_text")

        # --- Renderizar frame ---
        img_rgb = plotter.screenshot(window_size=(2560, 1440))
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        writer.write(img_bgr)

        # --- Limpiar actores dinámicos ---
        for actor in actors:
            plotter.remove_actor(actor)

        print(f"  Frame {f+1}/{num_frames}  ({pct}%)", end="\r")

    writer.release()
    plotter.close()
    print(f"\n✓ Video guardado en: {video_file}")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera un mapa 3D del terreno a partir de un archivo GPX"
    )
    parser.add_argument("gpx_file", help="Ruta al archivo .gpx")
    parser.add_argument("-o", "--output", default="terrain_map.png",
                        help="Archivo de salida (default: terrain_map.png)")
    parser.add_argument("--grid", type=int, default=80,
                        help="Resolución de la grilla (default: 80). 100-150 recomendado para mejor calidad.")
    parser.add_argument("--title", type=str, default=None,
                        help="Título personalizado del mapa")
    parser.add_argument("--elev", type=float, default=28,
                        help="Ángulo vertical de la cámara (default: 28)")
    parser.add_argument("--azim", type=float, default=-55,
                        help="Ángulo horizontal de la cámara (default: -55)")
    parser.add_argument("--sat-zoom", type=int, default=None,
                        help="Zoom de la imagen satelital (auto por defecto)")
    parser.add_argument("--z-exag", type=float, default=8.0,
                        help="Exageración vertical del relieve (default: 8.0). "
                             "Más alto = relieve más dramático.")
    parser.add_argument("--animate", action="store_true",
                        help="Generar video animado en lugar de imagen estática")
    parser.add_argument("--video", type=str, default="animation.mp4",
                        help="Archivo de salida del video (default: animation.mp4)")
    parser.add_argument("--duration", type=float, default=10,
                        help="Duración del video en segundos (default: 10)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Frames por segundo del video (default: 30)")
    parser.add_argument("--preview", action="store_true",
                        help="Genera una imagen de preview rápida (sin video)")
    parser.add_argument("--padding", type=float, default=0.004,
                        help="Margen alrededor de la ruta en grados (default: 0.004). "
                             "Más bajo = mapa más ajustado a la ruta (ej: 0.001).")
    args = parser.parse_args()

    if not os.path.exists(args.gpx_file):
        print(f"ERROR: Archivo no encontrado: {args.gpx_file}")
        sys.exit(1)

    create_terrain_map(
        args.gpx_file,
        output_file=args.output,
        grid_size=args.grid,
        title=args.title,
        view_elev=args.elev,
        view_azim=args.azim,
        sat_zoom=args.sat_zoom,
        z_exaggeration=args.z_exag,
        animate=args.animate,
        video_file=args.video,
        video_duration=args.duration,
        video_fps=args.fps,
        preview=args.preview,
        padding=args.padding,
    )
