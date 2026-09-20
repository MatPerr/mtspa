import os
from collections.abc import Sequence

import httpx

from app.optimization.datamodel import Matrix

DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"


class RoutingServiceError(RuntimeError):
    pass


async def get_travel_matrices(
    coordinates: Sequence[tuple[float, float]],
) -> tuple[Matrix[int], Matrix[int]]:
    if not coordinates:
        raise ValueError("At least one coordinate is required")

    coordinate_path = ";".join(
        f"{longitude:.7f},{latitude:.7f}"
        for latitude, longitude in coordinates
    )
    base_url = os.getenv("OSRM_BASE_URL", DEFAULT_OSRM_BASE_URL).rstrip("/")
    url = f"{base_url}/table/v1/driving/{coordinate_path}"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "mtspa-26/0.1"},
        ) as client:
            response = await client.get(
                url,
                params={"annotations": "distance,duration"},
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise RoutingServiceError(
            f"OSRM request failed: {error}"
        ) from error

    payload = response.json()
    if payload.get("code") != "Ok":
        message = payload.get("message", "Unknown OSRM error")
        raise RoutingServiceError(f"OSRM rejected the request: {message}")

    return (
        _integer_matrix(payload.get("distances"), "distance"),
        _integer_matrix(payload.get("durations"), "duration"),
    )


def _integer_matrix(values: object, label: str) -> Matrix[int]:
    if not isinstance(values, list):
        raise RoutingServiceError(f"OSRM returned no {label} matrix")

    matrix = []
    for row in values:
        if not isinstance(row, list) or any(value is None for value in row):
            raise RoutingServiceError(
                f"OSRM returned an incomplete {label} matrix"
            )
        matrix.append([round(float(value)) for value in row])
    return matrix
