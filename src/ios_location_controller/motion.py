"""Validated route settings and deterministic, pause-safe motion sampling."""
from dataclasses import dataclass, asdict
import math
import random
from .gpx import Point, distance_meters, interpolate, offset_point, bearing_radians


def route_points(items):
    if not isinstance(items, list) or not 2 <= len(items) <= 10000:
        raise ValueError("Route must contain 2 to 10000 nodes")
    points = []
    for item in items:
        lat, lon = float(item["lat"]), float(item["lng"])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -85 <= lat <= 85 or not -180 <= lon <= 180:
            raise ValueError("Coordinates out of range (latitude -85..85, longitude -180..180)")
        points.append(Point(lat, lon))
    if sum(distance_meters(a, b) for a, b in zip(points, points[1:])) < 0.1:
        raise ValueError("Route must have a non-zero length")
    return points


@dataclass(frozen=True)
class Settings:
    speed_kmh: float = 5.0
    interval: float = 1.0
    speed_variation_pct: float = 10.0
    lateral_variation_m: float = 1.0
    point_variation_m: float = 0.0
    variation_period: float = 12.0
    loop: bool = False
    random_seed: int = 42

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) - set(asdict(cls())):
            raise ValueError("Unknown settings")
        values = asdict(cls()) | data
        for key, low, high in [("speed_kmh", .1, 300), ("interval", .1, 10),
                               ("speed_variation_pct", 0, 80), ("lateral_variation_m", 0, 20),
                               ("point_variation_m", 0, 50),
                               ("variation_period", 2, 120)]:
            value = float(values[key])
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} must be within {low}..{high}")
            values[key] = value
        if type(values["loop"]) is not bool:
            raise ValueError("loop must be boolean")
        seed = values["random_seed"]
        if type(seed) is not int or not 0 <= seed <= 2147483647:
            raise ValueError("random_seed must be an integer in 0..2147483647")
        return cls(**values)


class Motion:
    def __init__(self, points, settings):
        self.points = points
        self.lengths = [distance_meters(a, b) for a, b in zip(points, points[1:])]
        self.total = sum(self.lengths)
        self.distance = 0.0
        self.elapsed = 0.0
        self.laps = 0
        self.phase = random.Random(settings.random_seed).random() * math.tau
        self._route_rng = random.Random(settings.random_seed ^ 0x9E3779B9)
        self._point_variation_m = settings.point_variation_m
        self._lap_points = None
        self._new_lap()

    @property
    def start_point(self):
        """The perturbed starting coordinate for the current lap."""
        return self._lap_points[0]

    def _new_lap(self):
        previous_end = self._lap_points[-1] if self._lap_points else None
        self._lap_points = perturb_route(self.points, self._point_variation_m,
                                         self._route_rng, previous_end)
        self.lengths = [distance_meters(a, b)
                        for a, b in zip(self._lap_points, self._lap_points[1:])]
        self.total = sum(self.lengths)

    def advance(self, dt, settings):
        self.elapsed += dt
        wave = math.sin(self.elapsed * math.tau / settings.variation_period + self.phase)
        speed = settings.speed_kmh * (1 + settings.speed_variation_pct / 100 * wave)
        self.distance += speed / 3.6 * dt
        done = self.distance >= self.total and not settings.loop
        if settings.loop:
            while self.distance >= self.total:
                self.distance -= self.total
                self.laps += 1
                self._new_lap()
        else:
            self.distance = min(self.distance, self.total)
        remaining = self.distance
        for index, length in enumerate(self.lengths):
            if remaining <= length and length > 0:
                fraction = remaining / length
                a, b = self._lap_points[index:index + 2]
                point = interpolate(a, b, fraction)
                # Taper at the perturbed nodes so adjacent segments meet.
                sway = settings.lateral_variation_m * math.sin(self.elapsed * math.tau / settings.variation_period + self.phase) * math.sin(math.pi * fraction)
                bearing = bearing_radians(a, b)
                point = offset_point(point, -math.sin(bearing) * sway, math.cos(bearing) * sway)
                return point, speed, done
            remaining -= length
        return self._lap_points[-1], speed, done


def perturb_route(points, radius_m, rng=None, previous_end=None):
    """Return route points with independent, uniformly distributed offsets.

    Offsets are sampled inside a circle of ``radius_m`` in local north/east
    metres.  Keeping one perturbed set for a whole lap avoids point-to-point
    teleporting while making repeated laps distinct.
    """
    if radius_m <= 0:
        return list(points)
    rng = rng or random.Random()
    result = []
    for point in points:
        angle = rng.random() * math.tau
        distance = radius_m * math.sqrt(rng.random())
        result.append(offset_point(point, math.cos(angle) * distance,
                                   math.sin(angle) * distance))
    if previous_end is not None and distance_meters(points[0], points[-1]) < 1e-6:
        # The end of this lap becomes the start of the next. It is allowed to
        # differ from this lap's start, otherwise every lap repeats that anchor.
        result[0] = previous_end
    return result
