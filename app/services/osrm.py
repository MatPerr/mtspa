import asyncio
import os
from collections.abc import Sequence

import httpx

from app.optimization.datamodel import Matrix

DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"
MAX_TABLE_COORDINATES = 100


class RoutingServiceError(RuntimeError):
    pass


async def get_travel_matrices(
    coordinates: Sequence[tuple[float, float]],
) -> tuple[Matrix[int], Matrix[int]]:
    if not coordinates:
        raise ValueError("At least one coordinate is required")

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": "mtspa-26/0.1"},
    ) as client:
        if len(coordinates) <= MAX_TABLE_COORDINATES:
            return await _request_table(client, coordinates)

        # Each rectangular request includes both its source and destination
        # coordinates. Assemble all directed blocks, including the diagonal.
        block_size = MAX_TABLE_COORDINATES // 2
        node_count = len(coordinates)
        distances = [[0] * node_count for _ in coordinates]
        travel_times = [[0] * node_count for _ in coordinates]
        semaphore = asyncio.Semaphore(2)

        async def fill_block(row_start: int, column_start: int) -> None:
            """Fetch one directed block and write it into the shared matrices.

            Args:
                row_start: First origin's index in the full coordinate sequence.
                column_start: First destination's index in that sequence.
            """
            origins = coordinates[row_start:row_start + block_size]
            destinations = coordinates[column_start:column_start + block_size]
            if row_start == column_start:
                block_coordinates = origins
                source_indices = destination_indices = None
            else:
                block_coordinates = [*origins, *destinations]
                source_indices = list(range(len(origins)))
                destination_indices = list(range(len(origins), len(block_coordinates)))
            async with semaphore:
                block_distances, block_times = await _request_table(
                    client, block_coordinates, source_indices, destination_indices,
                )
            for offset, (distance_row, time_row) in enumerate(zip(block_distances, block_times, strict=True)):
                end = column_start + len(destinations)
                distances[row_start + offset][column_start:end] = distance_row
                travel_times[row_start + offset][column_start:end] = time_row

        await asyncio.gather(*(
            fill_block(row, column)
            for row in range(0, node_count, block_size)
            for column in range(0, node_count, block_size)
        ))
        return distances, travel_times


async def _request_table(
    client: httpx.AsyncClient,
    coordinates: Sequence[tuple[float, float]],
    sources: list[int] | None = None,
    destinations: list[int] | None = None,
) -> tuple[Matrix[int], Matrix[int]]:
    """Request and validate one square or rectangular OSRM driving table.

    Args:
        client: HTTP client used for the request.
        coordinates: (Latitude, longitude) pairs included in the URL.
        sources: Coordinate indices defining row order, or None for all points.
        destinations: Indices defining column order, or None for all points.

    Returns:
        Distance and duration matrices rounded to integer metres and seconds.

    Raises:
        RoutingServiceError: The request fails, OSRM rejects it, a matrix is
            incomplete, or dimensions differ from the requested table.
        ValueError: Response JSON or numeric matrix values cannot be decoded.
    """
    coordinate_path = ";".join(
        f"{longitude:.7f},{latitude:.7f}"
        for latitude, longitude in coordinates
    )
    base_url = os.getenv("OSRM_BASE_URL", DEFAULT_OSRM_BASE_URL).rstrip("/")
    url = f"{base_url}/table/v1/driving/{coordinate_path}"
    params = {"annotations": "distance,duration"}
    if sources is not None:
        params["sources"] = ";".join(map(str, sources))
    if destinations is not None:
        params["destinations"] = ";".join(map(str, destinations))

    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RoutingServiceError(
            f"OSRM request failed: {error}"
        ) from error

    payload = response.json()
    if payload.get("code") != "Ok":
        message = payload.get("message", "Unknown OSRM error")
        raise RoutingServiceError(f"OSRM rejected the request: {message}")

    matrices = (
        _integer_matrix(payload.get("distances"), "distance"),
        _integer_matrix(payload.get("durations"), "duration"),
    )
    row_count = len(coordinates) if sources is None else len(sources)
    column_count = len(coordinates) if destinations is None else len(destinations)
    for matrix in matrices:
        if len(matrix) != row_count or any(len(row) != column_count for row in matrix):
            raise RoutingServiceError("OSRM returned an unexpected matrix shape")
    return matrices


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
