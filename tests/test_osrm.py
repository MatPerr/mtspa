import unittest
from unittest.mock import patch

import httpx

from app.services.osrm import RoutingServiceError, get_travel_matrices


class RoutingMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def test_batched_tables_preserve_directed_costs_and_node_order(self):
        """Verify uneven OSRM blocks reconstruct asymmetric matrices in order."""
        requests = []

        def respond(request):
            """Record a table request and encode its directed pairs as mock costs.

            Args:
                request: HTTP request containing coordinates and optional subsets.

            Returns:
                Successful OSRM-shaped response with distinguishable directed costs.
            """
            points = request.url.path.split("/driving/")[1].split(";")
            nodes = [round(float(point.split(",")[0])) for point in points]
            sources = request.url.params.get("sources")
            destinations = request.url.params.get("destinations")
            origins = nodes if sources is None else [nodes[int(index)] for index in sources.split(";")]
            targets = nodes if destinations is None else [nodes[int(index)] for index in destinations.split(";")]
            requests.append((nodes, origins, targets))
            return httpx.Response(200, json={
                "code": "Ok",
                "distances": [[100 * source + target for target in targets] for source in origins],
                "durations": [[10 * source + target for target in targets] for source in origins],
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with (
            patch("app.services.osrm.MAX_TABLE_COORDINATES", 4),
            patch("app.services.osrm.httpx.AsyncClient", return_value=client),
        ):
            distances, times = await get_travel_matrices([(0, node) for node in range(5)])

        self.assertEqual(len(requests), 9)
        self.assertTrue(all(len(nodes) <= 4 for nodes, _, _ in requests))
        self.assertEqual(distances, [[100 * a + b for b in range(5)] for a in range(5)])
        self.assertEqual(times, [[10 * a + b for b in range(5)] for a in range(5)])

    async def test_small_tables_use_one_request(self):
        """Verify a small coordinate set uses one complete table request."""
        requests = []

        def respond(request):
            """Record the request and return a fixed two-node driving table.

            Args:
                request: Outgoing request captured by the mock transport.

            Returns:
                Successful OSRM-shaped response with asymmetric costs.
            """
            requests.append(request)
            return httpx.Response(200, json={
                "code": "Ok", "distances": [[0, 20], [30, 0]], "durations": [[0, 2], [3, 0]],
            })

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        with patch("app.services.osrm.httpx.AsyncClient", return_value=client):
            result = await get_travel_matrices([(48.85, 2.35), (48.86, 2.36)])
        self.assertEqual(result, ([[0, 20], [30, 0]], [[0, 2], [3, 0]]))
        self.assertEqual(len(requests), 1)

    async def test_incorrect_matrix_shape_is_rejected(self):
        """Verify a provider matrix with unexpected dimensions is rejected."""
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"code": "Ok", "distances": [[0]], "durations": [[0]]},
        )))
        with patch("app.services.osrm.httpx.AsyncClient", return_value=client):
            with self.assertRaises(RoutingServiceError):
                await get_travel_matrices([(48.85, 2.35), (48.86, 2.36)])


if __name__ == "__main__":
    unittest.main()
