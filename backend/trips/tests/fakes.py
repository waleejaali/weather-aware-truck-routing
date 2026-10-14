from routing.providers.base import RoutingProvider
from routing.tests.factories import make_route, route_via


class FakeRoutingProvider(RoutingProvider):
    name = "fake-routing"
    profile = "driving-hgv"
    alternatives_max_distance_m = 100_000.0

    def __init__(self, error=None):
        self.error = error
        self.calls = []

    @property
    def request_count(self):
        return len(self.calls)

    def alternative_routes(self, origin, destination, target_count):
        raise AssertionError("long test trips must not request provider alternatives")

    def directions(self, waypoints, *, preference="recommended"):
        self.calls.append((list(waypoints), preference))
        if self.error:
            raise self.error
        origin, destination = waypoints[0], waypoints[-1]
        if len(waypoints) == 3:
            return route_via(origin, waypoints[1], destination)
        return make_route(origin, destination, 0.001 if preference == "shortest" else 0.0)
