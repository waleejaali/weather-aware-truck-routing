"""Live end-to-end check: real routes (ORS) + real weather (Open-Meteo) + risk ranking.

Needs ORS_API_KEY in .env. Not part of the automated test suite.

    python manage.py check_weather --departure 2026-10-13T08:00:00-05:00 --load-lb 42000
    python manage.py check_weather --interval-miles 50 --checkpoints
"""

from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from risk.levels import RiskLevel
from routing.checkpoints import METERS_PER_MILE
from routing.errors import RoutingError
from routing.management.commands.check_routing import DEFAULT_DESTINATION, DEFAULT_ORIGIN, parse_coordinate
from routing.providers import get_routing_provider
from routing.services.route_planner import RoutePlanner
from trips.assessment import ALLOWED_INTERVALS_MILES, WIND_METRICS, assess_routes
from weather.errors import WeatherProviderError
from weather.providers import get_weather_provider


def _fmt(value, spec=".1f"):
    return "  n/a" if value is None else format(value, spec)


class Command(BaseCommand):
    help = "Plan routes, fetch weather at each checkpoint's ETA, and print risk and the recommendation."

    def add_arguments(self, parser):
        parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="lat,lon (default: Los Angeles)")
        parser.add_argument("--destination", default=DEFAULT_DESTINATION, help="lat,lon (default: Dallas)")
        parser.add_argument(
            "--departure",
            help="ISO 8601 with offset, e.g. 2026-10-13T08:00:00-05:00. Naive values are read as UTC. Default: next full hour.",
        )
        parser.add_argument("--load-lb", type=float, default=35_000.0)
        parser.add_argument("--interval-miles", type=int, choices=ALLOWED_INTERVALS_MILES, default=25)
        parser.add_argument("--wind-metric", choices=WIND_METRICS, default=settings.WEATHER_WIND_METRIC)
        parser.add_argument("--checkpoints", action="store_true", help="print every checkpoint")

    def handle(self, *args, **options):
        origin = parse_coordinate(options["origin"])
        destination = parse_coordinate(options["destination"])
        now = datetime.now(timezone.utc)
        departure = self._departure(options["departure"], now)

        routing_provider = get_routing_provider()
        weather_provider = get_weather_provider()
        self.stdout.write(f"Routing: {routing_provider.name} ({routing_provider.profile})  Weather: {weather_provider.name}")
        self.stdout.write(
            f"Departure {departure:%Y-%m-%d %H:%M} UTC, load {options['load_lb']:,.0f} lb, "
            f"checkpoints every {options['interval_miles']} mi, wind metric: {options['wind_metric']}"
        )
        try:
            plan = RoutePlanner(routing_provider).plan(origin, destination)
            trip = assess_routes(
                plan.routes,
                departure=departure,
                load_lb=options["load_lb"],
                interval_miles=options["interval_miles"],
                provider=weather_provider,
                now=now,
                wind_metric=options["wind_metric"],
            )
        except (RoutingError, WeatherProviderError) as exc:
            raise CommandError(f"{type(exc).__name__}: {exc}")

        self.stdout.write(f"\nRoutes: {plan.status} ({len(plan.routes)} of {plan.requested_count})")
        self.stdout.write(f"Recommendation status: {trip.status}")
        for r in trip.routes:
            s = r.summary
            flag = "RECOMMENDED" if r.recommended else ("NO TRAVEL" if not r.eligible else "")
            self.stdout.write(
                f"\n#{r.rank} route {r.plan_index + 1} [{r.route.strategy}] {flag}\n"
                f"  {r.route.distance_m / METERS_PER_MILE:.0f} mi, {r.route.duration_s / 3600:.1f} h, "
                f"arrives {r.arrival:%Y-%m-%d %H:%M} UTC, {len(r.checkpoints)} checkpoints\n"
                "  miles: "
                + ", ".join(f"{level.label} {s.miles(level):.0f}" for level in RiskLevel)
                + f", unknown {s.unknown_miles:.0f}\n"
                f"  average score (0-4): {_fmt(s.average_score, '.2f')}, weather known for {r.weather_coverage:.0%} of miles, "
                f"complete: {s.data_complete}"
                + (f"\n  NOT RECOMMENDABLE: {r.ineligible_reason}" if r.ineligible_reason else "")
            )
            for cp in r.no_travel_checkpoints:
                self.stdout.write(
                    f"  NO TRAVEL at mile {cp.checkpoint.distance_miles:.0f} ({cp.eta:%m-%d %H:%M} UTC): "
                    + "; ".join(cp.risk.reasons)
                )
            if options["checkpoints"]:
                self.stdout.write(
                    f"   mile  eta(UTC)     wind  gust  rain  snow  wind used ({trip.wind_metric})  risk       note"
                )
                for cp in r.checkpoints:
                    c = cp.conditions
                    self.stdout.write(
                        f"  {cp.checkpoint.distance_miles:5.0f}  {cp.eta:%m-%d %H:%M}  "
                        f"{_fmt(c and c.wind_mph)} {_fmt(c and c.gust_mph)} {_fmt(c and c.rain_in_hr, '.2f')} "
                        f"{_fmt(c and c.snow_in_hr, '.2f')}  {_fmt(cp.wind_mph_used):>20}  "
                        f"{(cp.level.label if cp.level is not None else 'unknown'):<10} {cp.unavailable_reason or ''}"
                    )
        for note in (*plan.notes, *trip.notes):
            self.stdout.write(f"Note: {note}")
        self.stdout.write("\nMethod limits:")
        for assumption in trip.assumptions:
            self.stdout.write(f"  - {assumption}")
        self.stdout.write(f"\n{trip.attribution.text} ({trip.attribution.url}), licensed {trip.attribution.license}.")

    def _departure(self, text, now):
        if not text:
            return (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise CommandError(f"Invalid --departure {text!r}; use ISO 8601 such as 2026-10-13T08:00:00-05:00")
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
