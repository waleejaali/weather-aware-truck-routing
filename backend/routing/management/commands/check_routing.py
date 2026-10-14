# Hits the live routing provider (needs ORS_API_KEY); not part of the test suite.

from django.core.management.base import BaseCommand, CommandError

from routing.errors import RoutingError
from routing.geometry import overlap_fraction
from routing.providers import get_routing_provider
from routing.services.route_planner import PlannerConfig, RoutePlanner
from routing.types import Coordinate
from routing.validation import ValidationConfig

DEFAULT_ORIGIN = "34.0522,-118.2437"  # Los Angeles
DEFAULT_DESTINATION = "32.7767,-96.7970"  # Dallas
METERS_PER_MILE = 1609.344


def parse_coordinate(text: str) -> Coordinate:
    try:
        lat_text, lon_text = text.split(",")
        coordinate = Coordinate(float(lat_text), float(lon_text))
    except ValueError:
        raise CommandError(f"Invalid coordinate {text!r}; expected 'lat,lon' such as 34.0522,-118.2437")
    if not (-90 <= coordinate.lat <= 90 and -180 <= coordinate.lon <= 180):
        raise CommandError(f"Coordinate {text!r} is out of range")
    return coordinate


class Command(BaseCommand):
    help = "Request real routes from the configured provider and print how they were obtained."

    def add_arguments(self, parser):
        parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="lat,lon (default: Los Angeles)")
        parser.add_argument("--destination", default=DEFAULT_DESTINATION, help="lat,lon (default: Dallas)")
        parser.add_argument("--max-requests", type=int, default=PlannerConfig.max_provider_requests)
        parser.add_argument(
            "--max-detour-ratio", type=float, default=ValidationConfig.max_detour_ratio,
            help="reject routes longer/slower than the baseline by this factor",
        )
        parser.add_argument(
            "--max-overlap", type=float, default=ValidationConfig.max_overlap,
            help="routes sharing this fraction of their length with an accepted route are duplicates",
        )

    def handle(self, *args, **options):
        origin = parse_coordinate(options["origin"])
        destination = parse_coordinate(options["destination"])
        provider = get_routing_provider()
        config = PlannerConfig(
            max_provider_requests=options["max_requests"],
            validation=ValidationConfig(
                max_detour_ratio=options["max_detour_ratio"], max_overlap=options["max_overlap"]
            ),
        )
        planner = RoutePlanner(provider, config)

        self.stdout.write(f"Provider: {provider.name}  profile: {provider.profile}")
        self.stdout.write(f"Trip: {origin} -> {destination}")
        try:
            plan = planner.plan(origin, destination)
        except RoutingError as exc:
            raise CommandError(str(exc))

        self.stdout.write(f"\nStatus: {plan.status} ({len(plan.routes)} of {plan.requested_count} routes)")
        for i, route in enumerate(plan.routes, start=1):
            overlaps = [
                f"{overlap_fraction(route.points, other.points):.0%}"
                for j, other in enumerate(plan.routes, start=1)
                if j != i
            ]
            self.stdout.write(
                f"  Route {i}: {route.distance_m / METERS_PER_MILE:7.1f} mi  "
                f"{route.duration_s / 3600:5.2f} h  {len(route.points):6d} points  "
                f"strategy={route.strategy}  overlap with others: {', '.join(overlaps) or 'n/a'}"
            )
        if plan.notes:
            self.stdout.write("\nNotes:")
            for note in plan.notes:
                self.stdout.write(f"  - {note}")
