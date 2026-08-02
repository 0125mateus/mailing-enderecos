import hashlib
import math
import pickle
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from playwright.sync_api import Page

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}
_memory_index_cache: tuple[str, float, "NioLayerIndex"] | None = None


@dataclass
class NioPolygon:
    layer_name: str
    coordinates: list[tuple[float, float]]
    folder_names: tuple[str, ...] = ()
    min_lat: float = 0.0
    max_lat: float = 0.0
    min_lng: float = 0.0
    max_lng: float = 0.0

    def __post_init__(self) -> None:
        if not self.coordinates:
            return
        lats = [lat for lat, _lng in self.coordinates]
        lngs = [lng for _lat, lng in self.coordinates]
        self.min_lat = min(lats)
        self.max_lat = max(lats)
        self.min_lng = min(lngs)
        self.max_lng = max(lngs)

    def contains_point(self, lat: float, lng: float) -> bool:
        if not (
            self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng
        ):
            return False
        return point_in_polygon(lat, lng, self.coordinates)

    def distance_to_point_km(self, lat: float, lng: float) -> float:
        if self.contains_point(lat, lng):
            return 0.0

        min_distance = float("inf")
        total = len(self.coordinates)
        for index in range(total):
            lat1, lng1 = self.coordinates[index]
            lat2, lng2 = self.coordinates[(index + 1) % total]
            min_distance = min(
                min_distance,
                _distance_point_to_segment_km(lat, lng, lat1, lng1, lat2, lng2),
            )
        return min_distance


@dataclass
class NioPointAnalysis:
    camada_nio: str
    distancia_km: float | None
    viabilidade: str
    destacado: bool


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def _distance_point_to_segment_km(
    lat: float,
    lng: float,
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
) -> float:
    min_distance = min(
        haversine_km(lat, lng, lat1, lng1),
        haversine_km(lat, lng, lat2, lng2),
    )
    for step in range(21):
        ratio = step / 20
        sample_lat = lat1 + ratio * (lat2 - lat1)
        sample_lng = lng1 + ratio * (lng2 - lng1)
        min_distance = min(min_distance, haversine_km(lat, lng, sample_lat, sample_lng))
    return min_distance


def extract_map_mid(map_url: str) -> str | None:
    query = parse_qs(urlparse(map_url).query)
    mid_values = query.get("mid")
    if mid_values:
        return mid_values[0]

    match = re.search(r"mid=([A-Za-z0-9_-]+)", map_url)
    return match.group(1) if match else None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_coordinate_ring(text: str) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        lng = float(parts[0])
        lat = float(parts[1])
        coordinates.append((lat, lng))
    return coordinates


def point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    if len(polygon) < 3:
        return False

    inside = False
    previous = polygon[-1]
    for current in polygon:
        lat_i, lng_i = current
        lat_j, lng_j = previous
        intersects = (lng_i > lng) != (lng_j > lng) and lat < (
            (lat_j - lat_i) * (lng - lng_i) / ((lng_j - lng_i) or 1e-15) + lat_i
        )
        if intersects:
            inside = not inside
        previous = current
    return inside


def _normalize_layer_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"\s+", " ", name.strip())
    return cleaned or None


def _layer_name_from_stack(layer_stack: list[str], placemark_name: str | None) -> str:
    if placemark_name:
        return placemark_name
    for name in reversed(layer_stack):
        if name:
            return name
    return "Sem camada"


def _collect_polygons(element: ET.Element, layer_stack: list[str], polygons: list[NioPolygon]) -> None:
    tag = _local_name(element.tag)

    if tag in {"Document", "Folder"}:
        name = _normalize_layer_name(element.findtext("kml:name", namespaces=KML_NS))
        if name is None:
            name = _normalize_layer_name(element.findtext("name"))
        next_stack = layer_stack + ([name] if name else [])
        for child in list(element):
            _collect_polygons(child, next_stack, polygons)
        return

    if tag != "Placemark":
        for child in list(element):
            _collect_polygons(child, layer_stack, polygons)
        return

    placemark_name = _normalize_layer_name(element.findtext("kml:name", namespaces=KML_NS))
    if placemark_name is None:
        placemark_name = _normalize_layer_name(element.findtext("name"))
    layer_name = _layer_name_from_stack(layer_stack, placemark_name)

    for node in element.iter():
        if _local_name(node.tag) != "Polygon":
            continue
        coords_node = node.find(".//kml:coordinates", KML_NS)
        if coords_node is None:
            coords_node = node.find(".//coordinates")
        if coords_node is None or not coords_node.text:
            continue
        ring = _parse_coordinate_ring(coords_node.text.strip())
        if len(ring) >= 3:
            polygons.append(
                NioPolygon(
                    layer_name=layer_name,
                    folder_names=tuple(name for name in layer_stack if name),
                    coordinates=ring,
                )
            )


class NioLayerIndex:
    def __init__(self, polygons: list[NioPolygon]):
        self.polygons = polygons

    @classmethod
    def from_kml_bytes(cls, kml_bytes: bytes) -> "NioLayerIndex":
        root = ET.fromstring(kml_bytes)
        polygons: list[NioPolygon] = []
        _collect_polygons(root, [], polygons)
        return cls(polygons)

    @staticmethod
    def _matches_prefix(polygon: NioPolygon, prefix: str) -> bool:
        if not prefix:
            return True
        prefix_upper = prefix.upper()
        if prefix_upper in polygon.layer_name.upper():
            return True
        return any(prefix_upper in folder.upper() for folder in polygon.folder_names)

    @property
    def layer_names(self) -> list[str]:
        return sorted({polygon.layer_name for polygon in self.polygons})

    def find_layer(self, lat: float, lng: float) -> str | None:
        prefix = getattr(settings, "GOOGLE_MAPS_NIO_LAYER_PREFIX", "NIO").upper()
        matches: list[str] = []

        for polygon in self.polygons:
            if not polygon.contains_point(lat, lng):
                continue
            if prefix and not self._matches_prefix(polygon, prefix):
                continue
            matches.append(polygon.layer_name)

        if not matches:
            for polygon in self.polygons:
                if polygon.contains_point(lat, lng):
                    matches.append(polygon.layer_name)

        if not matches:
            return None

        unique_matches = list(dict.fromkeys(matches))
        return unique_matches[0] if len(unique_matches) == 1 else " / ".join(unique_matches)

    def analyze_point(self, lat: float, lng: float) -> NioPointAnalysis:
        prefix = getattr(settings, "GOOGLE_MAPS_NIO_LAYER_PREFIX", "NIO").upper()
        proximity_km = float(getattr(settings, "GOOGLE_MAPS_NIO_PROXIMITY_KM", 15))
        margin_deg = proximity_km / 111.0

        inside_layers: list[str] = []
        nearby_polygons: list[NioPolygon] = []

        for polygon in self.polygons:
            if prefix and not self._matches_prefix(polygon, prefix):
                continue
            if polygon.contains_point(lat, lng):
                inside_layers.append(polygon.layer_name)
                continue
            if (
                polygon.min_lat - margin_deg <= lat <= polygon.max_lat + margin_deg
                and polygon.min_lng - margin_deg <= lng <= polygon.max_lng + margin_deg
            ):
                nearby_polygons.append(polygon)

        if inside_layers:
            unique_matches = list(dict.fromkeys(inside_layers))
            layer_name = (
                unique_matches[0]
                if len(unique_matches) == 1
                else " / ".join(unique_matches)
            )
            return NioPointAnalysis(
                camada_nio=layer_name,
                distancia_km=0.0,
                viabilidade="Dentro da mancha",
                destacado=True,
            )

        best_layer: str | None = None
        best_distance = float("inf")
        for polygon in nearby_polygons:
            distance = polygon.distance_to_point_km(lat, lng)
            if distance < best_distance:
                best_distance = distance
                best_layer = polygon.layer_name

        if best_layer is None:
            return NioPointAnalysis(
                camada_nio="—",
                distancia_km=None,
                viabilidade="Fora da área",
                destacado=False,
            )

        if best_distance <= proximity_km:
            viabilidade = "Próximo da mancha"
            destacado = True
        else:
            viabilidade = "Fora da área"
            destacado = False

        return NioPointAnalysis(
            camada_nio=best_layer,
            distancia_km=round(best_distance, 2),
            viabilidade=viabilidade,
            destacado=destacado,
        )


def extract_network_link_href(kml_bytes: bytes) -> str | None:
    try:
        root = ET.fromstring(kml_bytes)
    except ET.ParseError:
        return None

    for element in root.iter():
        if _local_name(element.tag) != "NetworkLink":
            continue
        link = element.find("kml:Link", KML_NS) or element.find("Link")
        if link is None:
            continue
        href_node = link.find("kml:href", KML_NS) or link.find("href")
        if href_node is not None and href_node.text:
            return href_node.text.strip()
    return None


def fetch_kml_with_page(page: Page, kml_url: str, timeout_ms: int = 60000) -> bytes | None:
    try:
        response = page.context.request.get(kml_url, timeout=timeout_ms)
        if not response.ok:
            return None
        body = response.body()
        if body and b"<kml" in body.lower():
            return body
    except Exception:
        return None
    return None


def summarize_layer_index(index: NioLayerIndex) -> dict[str, Any]:
    by_name: dict[str, int] = {}
    for polygon in index.polygons:
        by_name[polygon.layer_name] = by_name.get(polygon.layer_name, 0) + 1

    folders: set[str] = set()
    for polygon in index.polygons:
        folders.update(polygon.folder_names)

    return {
        "polygon_count": len(index.polygons),
        "layer_count": len(by_name),
        "folder_count": len(folders),
        "layers": sorted(by_name.items(), key=lambda item: item[0].lower()),
        "folders": sorted(folders, key=str.lower),
    }


def _kml_cache_path(map_mid: str) -> Path:
    cache_dir = Path(settings.BASE_DIR) / "playwright" / "kml-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{map_mid}.kml"


def _index_cache_path(kml_path: Path) -> Path:
    cache_dir = Path(settings.BASE_DIR) / "playwright" / "kml-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(kml_path.resolve()).encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"index-{digest}.pkl"


def _load_local_kml() -> NioLayerIndex | None:
    global _memory_index_cache

    configured = getattr(settings, "GOOGLE_MAPS_KML_PATH", "") or ""
    if not configured:
        return None

    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        return None

    mtime = path.stat().st_mtime
    path_key = str(path)
    if (
        _memory_index_cache
        and _memory_index_cache[0] == path_key
        and _memory_index_cache[1] == mtime
    ):
        return _memory_index_cache[2]

    cache_path = _index_cache_path(path)
    if cache_path.is_file():
        try:
            cached_mtime, index = pickle.loads(cache_path.read_bytes())
            if cached_mtime == mtime and index.polygons:
                _memory_index_cache = (path_key, mtime, index)
                return index
        except Exception:
            cache_path.unlink(missing_ok=True)

    index = NioLayerIndex.from_kml_bytes(path.read_bytes())
    if not index.polygons:
        return None

    try:
        cache_path.write_bytes(pickle.dumps((mtime, index), protocol=pickle.HIGHEST_PROTOCOL))
    except OSError:
        pass

    _memory_index_cache = (path_key, mtime, index)
    return index


def load_local_layer_index() -> NioLayerIndex | None:
    return _load_local_kml()


def load_layer_index_from_page(page: Page, map_url: str) -> NioLayerIndex | None:
    try:
        local_index = _load_local_kml()
        if local_index and local_index.polygons:
            return local_index

        map_mid = extract_map_mid(map_url)
        if not map_mid:
            return None

        cache_path = _kml_cache_path(map_mid)
        if cache_path.is_file():
            try:
                cached = NioLayerIndex.from_kml_bytes(cache_path.read_bytes())
                if cached.polygons:
                    return cached
            except ET.ParseError:
                cache_path.unlink(missing_ok=True)

        timeout_ms = getattr(settings, "PLAYWRIGHT_KML_TIMEOUT_MS", 15000)
        kml_urls = (
            f"https://www.google.com/maps/d/u/0/kml?mid={map_mid}&forcekml=1",
            f"https://www.google.com/maps/d/kml?mid={map_mid}&forcekml=1",
        )

        for kml_url in kml_urls:
            try:
                response = page.context.request.get(kml_url, timeout=timeout_ms)
                if not response.ok:
                    continue
                body = response.body()
                if not body or b"<kml" not in body.lower():
                    continue
                cache_path.write_bytes(body)
                index = NioLayerIndex.from_kml_bytes(body)
                if index.polygons:
                    return index
            except Exception:
                continue

        return _load_local_kml()
    except Exception:
        return None


def get_search_coordinates(page: Page, timeout_ms: int = 2500) -> tuple[float, float] | None:
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        coords: dict[str, Any] | None = page.evaluate(
            """
            () => {
                const params = new URLSearchParams(window.location.search);
                const ll = params.get("ll");
                if (ll) {
                    const parts = ll.split(",");
                    if (parts.length >= 2) {
                        const lat = parseFloat(parts[0]);
                        const lng = parseFloat(parts[1]);
                        if (Number.isFinite(lat) && Number.isFinite(lng)) {
                            return { lat, lng, source: "ll" };
                        }
                    }
                }

                const hrefMatch = window.location.href.match(/@(-?\\d+(?:\\.\\d+)?),(-?\\d+(?:\\.\\d+)?)/);
                if (hrefMatch) {
                    const lat = parseFloat(hrefMatch[1]);
                    const lng = parseFloat(hrefMatch[2]);
                    if (Number.isFinite(lat) && Number.isFinite(lng)) {
                        return { lat, lng, source: "href" };
                    }
                }

                return null;
            }
            """
        )
        if coords and coords.get("lat") is not None and coords.get("lng") is not None:
            return float(coords["lat"]), float(coords["lng"])

        page.wait_for_timeout(250)

    return None
