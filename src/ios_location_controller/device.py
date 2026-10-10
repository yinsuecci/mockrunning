from __future__ import annotations

import logging
from collections.abc import Sequence
import asyncio
import math
import random
import time
import json
import subprocess
import urllib.request
import sys
from contextlib import AsyncExitStack
from collections.abc import Awaitable, Callable

from .gpx import Point, bearing_radians, distance_meters, interpolate, offset_point
from .motion import perturb_route

log = logging.getLogger(__name__)


class LocationDevice:
    """Adapter around pymobiledevice3's DVT location service."""

    def diagnostics(self):
        return {"horizontal_accuracy": False, "sensors": False, "raw_gnss": False,
                "mock": None, "injections": {}}

    async def set_route_point(self, point):
        return await self.set_point(point)

    def __init__(self, udid: str | None = None, rsd_host: str | None = None, rsd_port: int | None = None) -> None:
        self.udid = udid
        self.rsd_host = rsd_host
        self.rsd_port = rsd_port
        self._simulation = None
        self._provider = None
        self._transport = None
        self._tunnel = None
        self._resources = None
        self._wda_process = None
        self.wda_error = None

    async def connect(self) -> None:
        if (self.rsd_host is None) != (self.rsd_port is None):
            raise ValueError("RSD host and port must be provided together")
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        resources = AsyncExitStack()
        try:
            if self.rsd_host is not None:
                from pymobiledevice3.remote.remote_service_discovery import RemoteServiceDiscoveryService
                transport = RemoteServiceDiscoveryService((self.rsd_host, self.rsd_port))
                resources.push_async_callback(transport.close)
                await transport.connect()
                mode = "external RSD"
            else:
                from pymobiledevice3.lockdown import create_using_usbmux
                lockdown = await create_using_usbmux(self.udid)
                if int(lockdown.product_version.split('.')[0]) < 17:
                    transport = lockdown
                    resources.push_async_callback(lockdown.close)
                    mode = "USB lockdown"
                else:
                    await lockdown.close()
                    from pymobiledevice3.remote.rsd_tunnel import PreferredRsdTunnel
                    tunnel = PreferredRsdTunnel(serial=self.udid)
                    resources.push_async_callback(tunnel.aclose)
                    transport = await tunnel.aopen()
                    mode = "userspace RSD"
            provider = await resources.enter_async_context(DvtProvider(transport))
            self._simulation = await resources.enter_async_context(LocationSimulation(provider))
            self._resources = resources
        except BaseException:
            await resources.aclose()
            self._simulation = None
            raise
        log.info("Connected to iPhone (%s)", mode)

        if self.rsd_host is not None:
            self.wda_error = "External RSD: real GPS readback is unavailable"
            return

        # WDA is optional: the DVT simulation path must remain usable when it is absent.
        try:
            self._wda_process = subprocess.Popen(
                [sys.executable, "-m", "pymobiledevice3", "usbmux", "forward", "8100", "8100",
                 "--serial", self.udid or ""],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            await asyncio.sleep(0.25)
            await self.read_location()
        except Exception as exc:
            self.wda_error = str(exc) or type(exc).__name__
            self._stop_wda()

    async def read_location(self) -> dict:
        if self.rsd_host is not None:
            raise RuntimeError("External RSD: real GPS readback is unavailable")
        def request():
            with urllib.request.urlopen("http://127.0.0.1:8100/wda/device/location", timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
            value = data.get("value", data)
            if "latitude" not in value or "longitude" not in value:
                raise RuntimeError(value.get("message", "WDA returned no location"))
            return {"lat": float(value["latitude"]), "lng": float(value["longitude"]),
                    "altitude": float(value.get("altitude", 0))}
        return await asyncio.to_thread(request)

    def _stop_wda(self):
        if self._wda_process and self._wda_process.poll() is None:
            self._wda_process.terminate()
        self._wda_process = None

    async def set_point(self, point: Point) -> None:
        if self._simulation is None:
            raise RuntimeError("Device is not connected")
        await self._simulation.set(point.latitude, point.longitude)

    async def play(
        self,
        points: Sequence[Point],
        interval: float,
        loop: bool = False,
        speed_kmh: float | None = None,
        speed_variation_pct: float = 0.0,
        lateral_variation_m: float = 0.0,
        random_seed: int | None = None,
        on_point: Callable[[Point], Awaitable[None]] | None = None,
        pause_event: asyncio.Event | None = None,
        point_variation_m: float = 0.0,
    ) -> None:
        if not points or interval <= 0:
            raise ValueError("Route must contain points and interval must be positive")
        if speed_kmh is not None and speed_kmh <= 0:
            raise ValueError("Speed must be positive")
        if not 0 <= speed_variation_pct <= 100:
            raise ValueError("Speed variation must be between 0 and 100 percent")
        if lateral_variation_m < 0:
            raise ValueError("Lateral variation must not be negative")
        if not 0 <= point_variation_m <= 50:
            raise ValueError("Point variation must be between 0 and 50 meters")
        # Keep route jitter and speed/lateral variation on separate streams so
        # enabling point variation does not change existing motion sequences.
        rng = random.Random(random_seed)
        route_rng = random.Random(None if random_seed is None else random_seed ^ 0x9E3779B9)
        previous_end = None
        while True:
            if pause_event is not None:
                await pause_event.wait()
            lap_points = perturb_route(points, point_variation_m, route_rng, previous_end)
            await self.set_point(lap_points[0])
            if on_point is not None:
                await on_point(lap_points[0])
            for segment, (start, end) in enumerate(zip(lap_points, lap_points[1:]), 1):
                if speed_kmh is None:
                    if pause_event is not None:
                        await pause_event.wait()
                    sender = self.set_point if segment == len(points) - 1 else self.set_route_point
                    sent = await sender(end)
                    if on_point is not None and sent is not False:
                        await on_point(end)
                    await asyncio.sleep(interval)
                    continue
                segment_distance = distance_meters(start, end)
                variation = speed_variation_pct / 100
                segment_speed = speed_kmh * rng.uniform(max(0.01, 1 - variation), 1 + variation)
                duration = segment_distance / (segment_speed / 3.6)
                steps = max(1, math.ceil(duration / interval))
                started = time.monotonic()
                bearing = bearing_radians(start, end)
                lateral = rng.uniform(-lateral_variation_m, lateral_variation_m)
                for step in range(1, steps + 1):
                    if pause_event is not None:
                        await pause_event.wait()
                    fraction = step / steps
                    point = interpolate(start, end, fraction)
                    sway = lateral * math.sin(math.pi * fraction)
                    point = offset_point(point, -math.sin(bearing) * sway, math.cos(bearing) * sway)
                    sender = self.set_point if segment == len(points) - 1 and step == steps else self.set_route_point
                    sent = await sender(point)
                    if on_point is not None and sent is not False:
                        await on_point(point)
                    target = started + duration * step / steps
                    await asyncio.sleep(max(0.0, target - time.monotonic()))
                log.debug("Segment %.1f m at %.2f km/h completed in %.2f s", segment_distance, segment_speed, duration)
            if not loop:
                return
            previous_end = lap_points[-1]

    async def clear(self) -> None:
        if self._simulation is not None:
            await self._simulation.clear()

    async def close(self) -> None:
        try:
            if self._simulation is not None:
                await self._simulation.clear()
        finally:
            self._simulation = None
            resources, self._resources = self._resources, None
            if resources is not None:
                await resources.aclose()
            self._stop_wda()
