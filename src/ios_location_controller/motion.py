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


class _LateralNoise:
    def __init__(self, seed):
        self.rng = random.Random(f"lateral:{seed}")
        self.start = 0.0
        self.end = self.rng.uniform(0.35, 0.9)
        self.left, self.right = 0.0, self.rng.uniform(-1, 1)

    def sample(self, time):
        while time >= self.end:
            self.start = self.end
            self.end += self.rng.uniform(0.35, 0.9)
            self.left, self.right = self.right, self.rng.uniform(-1, 1)
        fraction = (time - self.start) / (self.end - self.start)
        # Smoothstep joins random targets without a sharp change in slope.
        blend = fraction * fraction * (3 - 2 * fraction)
        return self.left + (self.right - self.left) * blend


class Motion:
    def __init__(self, points, settings):
        self.points = points
        self.lengths = [distance_meters(a, b) for a, b in zip(points, points[1:])]
        self.total = sum(self.lengths)
        self.distance = 0.0
        self.elapsed = 0.0
        self.laps = 0
        self.phase = random.Random(settings.random_seed).random() * math.tau
        self.lateral = _LateralNoise(settings.random_seed)
        self.lateral_time = 0.0

    def advance(self, dt, settings):
        self.elapsed += dt
        self.lateral_time += dt / settings.variation_period
        wave = math.sin(self.elapsed * math.tau / settings.variation_period + self.phase)
        speed = settings.speed_kmh * (1 + settings.speed_variation_pct / 100 * wave)
        self.distance += speed / 3.6 * dt
        done = self.distance >= self.total and not settings.loop
        if settings.loop:
            self.laps += int(self.distance / self.total)
            self.distance %= self.total
        else:
            self.distance = min(self.distance, self.total)
        remaining = self.distance
        for index, length in enumerate(self.lengths):
            if remaining <= length and length > 0:
                fraction = remaining / length
                a, b = self.points[index:index + 2]
                point = interpolate(a, b, fraction)
                # Taper at nodes so corners and endpoints remain on the route.
                if settings.lateral_variation_m and 0 < fraction < 1:
                    sway = settings.lateral_variation_m * self.lateral.sample(self.lateral_time) * math.sin(math.pi * fraction)
                    bearing = bearing_radians(a, b)
                    point = offset_point(point, -math.sin(bearing) * sway, math.cos(bearing) * sway)
                return point, speed, done
            remaining -= length
        return self.points[-1], speed, done
