import math
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from app.config import get_settings

TILE_SIZE = 256
MIN_ZOOM = 2
MAX_ZOOM = 16
MAX_TILES = 24
TILE_CACHE_DIR = "map_tiles"


def lonlat_to_mercator(longitude: float, latitude: float) -> tuple[float, float]:
    x = math.radians(longitude) * 6378137.0
    clamped = max(min(latitude, 85.05112878), -85.05112878)
    y = math.log(math.tan(math.pi / 4 + math.radians(clamped) / 2)) * 6378137.0
    return x, y


def _lonlat_to_tile(longitude: float, latitude: float, zoom: int) -> tuple[float, float]:
    n = 2.0**zoom
    x = (longitude + 180.0) / 360.0 * n
    clamped = max(min(latitude, 85.05112878), -85.05112878)
    lat_rad = math.radians(clamped)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _tile_to_lon(x: float, zoom: int) -> float:
    return x / 2.0**zoom * 360.0 - 180.0


def _tile_to_lat(y: float, zoom: int) -> float:
    n = math.pi - 2.0 * math.pi * y / 2.0**zoom
    return math.degrees(math.atan(math.sinh(n)))


def choose_zoom(west: float, south: float, east: float, north: float) -> int:
    for zoom in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        x_min, y_max = _lonlat_to_tile(west, south, zoom)
        x_max, y_min = _lonlat_to_tile(east, north, zoom)
        tiles_x = int(math.floor(x_max)) - int(math.floor(x_min)) + 1
        tiles_y = int(math.floor(y_max)) - int(math.floor(y_min)) + 1
        if tiles_x * tiles_y <= MAX_TILES:
            return zoom
    return MIN_ZOOM


def _cache_path(zoom: int, x: int, y: int) -> Path:
    return get_settings().local_data_dir / TILE_CACHE_DIR / str(zoom) / str(x) / f"{y}.png"


def _fetch_tile(client: httpx.Client, template: str, zoom: int, x: int, y: int) -> Image.Image:
    path = _cache_path(zoom, x, y)
    if path.exists():
        with Image.open(path) as cached:
            return cached.convert("RGB")
    response = client.get(template.format(z=zoom, x=x, y=y))
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    with Image.open(BytesIO(response.content)) as fetched:
        return fetched.convert("RGB")


def fetch_basemap(
    west: float,
    south: float,
    east: float,
    north: float,
) -> tuple[Image.Image, tuple[float, float, float, float]] | None:
    settings = get_settings()
    if not settings.enable_map_tiles:
        return None

    zoom = choose_zoom(west, south, east, north)
    x_min_f, y_max_f = _lonlat_to_tile(west, south, zoom)
    x_max_f, y_min_f = _lonlat_to_tile(east, north, zoom)
    x_min, x_max = int(math.floor(x_min_f)), int(math.floor(x_max_f))
    y_min, y_max = int(math.floor(y_min_f)), int(math.floor(y_max_f))

    columns = x_max - x_min + 1
    rows = y_max - y_min + 1
    canvas = Image.new("RGB", (columns * TILE_SIZE, rows * TILE_SIZE), "#f2efe9")

    headers = {"User-Agent": settings.map_tile_user_agent}
    try:
        with httpx.Client(timeout=settings.map_tile_timeout_seconds, headers=headers) as client:
            for column in range(columns):
                for row in range(rows):
                    tile = _fetch_tile(client, settings.map_tile_url, zoom, x_min + column, y_min + row)
                    canvas.paste(tile, (column * TILE_SIZE, row * TILE_SIZE))
    except (httpx.HTTPError, OSError):
        return None

    left, _ = lonlat_to_mercator(_tile_to_lon(x_min, zoom), 0.0)
    right, _ = lonlat_to_mercator(_tile_to_lon(x_max + 1, zoom), 0.0)
    _, top = lonlat_to_mercator(0.0, _tile_to_lat(y_min, zoom))
    _, bottom = lonlat_to_mercator(0.0, _tile_to_lat(y_max + 1, zoom))
    return canvas, (left, right, bottom, top)
