"""Request validation for POST /api/v1/routes/assess/. Strict: no silent coercion of types or time zones."""

import math
from datetime import datetime, timezone

from rest_framework import serializers

from routing.geometry import haversine_m
from routing.types import Coordinate
from trips.assessment import ALLOWED_INTERVALS_MILES

MAX_LOAD_LB = 150_000  # well above the 80,000 lb US gross vehicle limit, below absurd values
MIN_TRIP_SEPARATION_M = 100.0


class StrictNumberField(serializers.Field):
    """A JSON number. Rejects strings, booleans, NaN and infinity (DRF's FloatField accepts them)."""

    default_error_messages = {
        "invalid": "A number is required.",
        "not_finite": "Must be a finite number.",
    }

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, (int, float)):
            self.fail("invalid")
        value = float(data)
        if not math.isfinite(value):
            self.fail("not_finite")
        return value

    def to_representation(self, value):
        return value


class AwareDateTimeField(serializers.Field):
    """ISO 8601 date-time WITH a UTC offset (or Z). Naive values are rejected, never assumed to be UTC."""

    default_error_messages = {
        "invalid": "Use an ISO 8601 date-time such as 2026-10-14T08:00:00-05:00.",
        "naive": "Include a UTC offset (for example -05:00 or Z); times without one are ambiguous.",
    }

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        try:
            parsed = datetime.fromisoformat(data)
        except ValueError:
            self.fail("invalid")
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            self.fail("naive")
        return parsed.astimezone(timezone.utc)

    def to_representation(self, value):
        return value.isoformat()


class PointSerializer(serializers.Serializer):
    latitude = StrictNumberField()
    longitude = StrictNumberField()

    def validate_latitude(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value


class AssessRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    departure_datetime = AwareDateTimeField()
    load_lb = StrictNumberField()
    checkpoint_interval_miles = StrictNumberField()

    def validate_load_lb(self, value):
        if value <= 0:
            raise serializers.ValidationError("Load must be greater than 0.")
        if value > MAX_LOAD_LB:
            raise serializers.ValidationError(f"Load must not exceed {MAX_LOAD_LB:,} lb.")
        return value

    def validate_checkpoint_interval_miles(self, value):
        if value not in ALLOWED_INTERVALS_MILES:
            options = ", ".join(str(i) for i in ALLOWED_INTERVALS_MILES)
            raise serializers.ValidationError(f"Must be one of: {options}.")
        return int(value)

    def validate(self, attrs):
        origin, destination = attrs["origin"], attrs["destination"]
        distance = haversine_m(
            Coordinate(origin["latitude"], origin["longitude"]),
            Coordinate(destination["latitude"], destination["longitude"]),
        )
        if distance < MIN_TRIP_SEPARATION_M:
            raise serializers.ValidationError(
                {"destination": ["Destination must be at least 100 m from the origin."]}
            )
        return attrs
