import os
from collections import OrderedDict
from dataclasses import dataclass

import httpx

DEFAULT_PHOTON_BASE_URL = "https://photon.komoot.io"
DEFAULT_PHOTON_USER_AGENT = "mtspa-26/0.1 (address autocomplete)"
MAX_CACHE_SIZE = 256


class GeocodingServiceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeocodedLocation:
    latitude: float
    longitude: float
    label: str


_cache: OrderedDict[tuple[str, int], tuple[GeocodedLocation, ...]] = (
    OrderedDict()
)


async def search_addresses(
    query: str,
    limit: int = 5,
) -> list[GeocodedLocation]:
    """Search for addresses using a bounded least-recently-used result cache.

    Args:
        query: Address text; whitespace is normalized before searching.
        limit: Positive maximum number of suggestions to return.

    Returns:
        Address suggestions with coordinates and display labels. Cached entries
        are keyed by case-insensitive normalized query and requested limit.

    Raises:
        GeocodingServiceError: The provider cannot be reached or returns an
            invalid response.
    """
    normalized_query = " ".join(query.split())
    cache_key = (normalized_query.casefold(), limit)
    if cache_key in _cache:
        _cache.move_to_end(cache_key)
        return list(_cache[cache_key])

    results = await _request_suggestions(normalized_query, limit)
    _cache[cache_key] = tuple(results)
    _cache.move_to_end(cache_key)
    if len(_cache) > MAX_CACHE_SIZE:
        _cache.popitem(last=False)
    return results


async def _request_suggestions(
    query: str,
    limit: int,
) -> list[GeocodedLocation]:
    """Fetch French-language Photon suggestions and discard invalid duplicates.

    Read the provider URL and user agent from PHOTON_BASE_URL and
    PHOTON_USER_AGENT when set. Request extra candidates to allow filtering.

    Args:
        query: Normalized address text to send to Photon.
        limit: Positive maximum number of distinct suggestions to return.

    Returns:
        Valid suggestions in provider order, deduplicated by label and by
        coordinates rounded to five decimal places.

    Raises:
        GeocodingServiceError: An HTTP request fails, JSON cannot be decoded,
            or the response does not contain a feature list.
    """
    base_url = os.getenv(
        "PHOTON_BASE_URL",
        DEFAULT_PHOTON_BASE_URL,
    ).rstrip("/")
    user_agent = os.getenv(
        "PHOTON_USER_AGENT",
        DEFAULT_PHOTON_USER_AGENT,
    )

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": user_agent},
        ) as client:
            response = await client.get(
                f"{base_url}/api",
                params={
                    "q": query,
                    "limit": min(limit * 2, 20),
                    "lang": "fr",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise GeocodingServiceError(
            f"Address search failed: {error}"
        ) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise GeocodingServiceError(
            "Address search returned invalid JSON"
        ) from error

    if not isinstance(payload, dict) or not isinstance(
        payload.get("features"),
        list,
    ):
        raise GeocodingServiceError("Address search returned an invalid response")

    results = []
    seen_labels = set()
    seen_coordinates = set()
    for feature in payload["features"]:
        location = _parse_feature(feature)
        if location is None:
            continue
        label_key = location.label.casefold()
        coordinate_key = (
            round(location.latitude, 5),
            round(location.longitude, 5),
        )
        if label_key in seen_labels or coordinate_key in seen_coordinates:
            continue
        seen_labels.add(label_key)
        seen_coordinates.add(coordinate_key)
        results.append(location)
        if len(results) == limit:
            break
    return results


def _parse_feature(feature: object) -> GeocodedLocation | None:
    """Convert a Photon feature into a usable address suggestion.

    Args:
        feature: Untrusted feature object decoded from the provider response.

    Returns:
        A location with valid latitude, longitude, and a nonempty label, or
        None if any required feature data is missing or invalid.
    """
    if not isinstance(feature, dict):
        return None
    geometry = feature.get("geometry")
    properties = feature.get("properties")
    if not isinstance(geometry, dict) or not isinstance(properties, dict):
        return None
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    try:
        longitude = float(coordinates[0])
        latitude = float(coordinates[1])
    except (TypeError, ValueError):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None

    label = _address_label(properties)
    if not label:
        return None
    return GeocodedLocation(
        latitude=latitude,
        longitude=longitude,
        label=label,
    )


def _address_label(properties: dict[object, object]) -> str:
    """Build a display label from available Photon address properties.

    Args:
        properties: Feature properties containing optional name, street,
            locality, postcode, and country fields.

    Returns:
        Comma-separated address parts with case-insensitive duplicates removed,
        or an empty string when no usable parts exist.
    """
    name = _text_property(properties, "name")
    street = _text_property(properties, "street")
    house_number = _text_property(properties, "housenumber")
    locality = (
        _text_property(properties, "city")
        or _text_property(properties, "town")
        or _text_property(properties, "village")
        or _text_property(properties, "district")
    )
    postcode = _text_property(properties, "postcode")
    country = _text_property(properties, "country")

    street_address = " ".join(
        part for part in (house_number, street) if part
    )
    parts = []
    for part in (name, street_address, locality, postcode, country):
        if part and part.casefold() not in {item.casefold() for item in parts}:
            parts.append(part)
    return ", ".join(parts)


def _text_property(properties: dict[object, object], key: str) -> str:
    """Read a trimmed string property, treating missing or non-string data as empty.

    Args:
        properties: Provider feature properties.
        key: Property name to retrieve.

    Returns:
        Trimmed text, or an empty string for a missing or non-string value.
    """
    value = properties.get(key)
    return value.strip() if isinstance(value, str) else ""
