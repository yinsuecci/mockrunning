from __future__ import annotations
import argparse
import asyncio
import logging
import math
from pathlib import Path
from .connections import create_device
from .android import discover as discover_android, pair
from .gpx import load_points


def positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def percentage(value: str) -> float:
    number = float(value)
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return number


def nonnegative_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return number

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="iOS / Android location test controller")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--platform", choices=["ios", "android"], default="ios")
    pairing = sub.add_parser("pair", help="Pair Android wireless debugging (code prompted securely)")
    pairing.add_argument("address", help="Pairing IP:port, not the debugging port")
    validate = sub.add_parser("validate")
    validate.add_argument("route", type=Path)
    emulator = sub.add_parser("emulator", help="Explicit Android AVD test inputs (not physical phones)")
    emulator.add_argument("--serial", required=True, help="Running AVD serial, e.g. emulator-5554")
    emu_commands = emulator.add_subparsers(dest="emulator_command", required=True)
    fix = emu_commands.add_parser("fix", help="GPS fix with a satellite-count test parameter, not raw GNSS")
    fix.add_argument("--latitude", type=float, required=True)
    fix.add_argument("--longitude", type=float, required=True)
    fix.add_argument("--altitude", type=float, default=0)
    fix.add_argument("--satellites", type=int, default=8)
    fix.add_argument("--speed-kmh", type=nonnegative_float, default=0)
    sensor = emu_commands.add_parser("sensor", help="Temporary sensor values, restored after duration")
    from .emulator import SENSORS
    sensor.add_argument("name", choices=SENSORS)
    for axis in ("x", "y", "z"):
        sensor.add_argument("--" + axis, type=float, required=True)
    sensor.add_argument("--duration", type=positive_float, default=1)
    play = sub.add_parser("play")
    play.add_argument("route", type=Path)
    play.add_argument("--udid")
    play.add_argument("--interval", type=positive_float, default=1.0, help="GPS update interval in seconds")
    play.add_argument("--speed-kmh", type=positive_float, help="Travel speed along the route in km/h")
    play.add_argument("--speed-variation-pct", type=percentage, default=0.0, help="Random speed variation per segment")
    play.add_argument("--lateral-variation-m", type=nonnegative_float, default=0.0, help="Left/right sway amplitude in meters")
    play.add_argument("--point-variation-m", type=nonnegative_float, default=0.0,
                      help="Per-route-point random variation radius in meters")
    play.add_argument("--random-seed", type=int, help="Optional seed for repeatable movement variation")
    play.add_argument("--loop", action="store_true")
    play.add_argument("--android-provider", choices=["gps", "network", "both"], default="gps")
    play.add_argument("--gps-accuracy", type=positive_float, default=5.0, help="Android test hAcc in meters")
    play.add_argument("--network-accuracy", type=positive_float, default=50.0, help="Android network test hAcc in meters")
    play.add_argument("--network-interval", type=positive_float, default=5.0, help="Android network test update interval")
    play.add_argument("--rsd-host", help="RSD host printed by pymobiledevice3 remote start-tunnel")
    play.add_argument("--rsd-port", type=int, help="RSD port printed by pymobiledevice3 remote start-tunnel")
    clear = sub.add_parser("clear")
    clear.add_argument("--udid")
    clear.add_argument("--rsd-host")
    clear.add_argument("--rsd-port", type=int)
    for command in (play, clear):
        command.add_argument("--platform", choices=["ios", "android"], default="ios")
        command.add_argument("--address", help="Android wireless debugging IP:port")
    web = sub.add_parser("map", help="Start the local OpenStreetMap route editor")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8765)
    return parser

async def run(args: argparse.Namespace) -> None:
    if args.command == "emulator":
        from .emulator import Emulator
        emulator = Emulator(args.serial)
        if args.emulator_command == "fix":
            await emulator.fix(args.latitude, args.longitude, args.altitude, args.satellites, args.speed_kmh)
            print("AVD GPS fix sent (satellite count is a test input, not raw GNSS; mock status is unchanged)")
        else:
            await emulator.sensor(args.name, args.x, args.y, args.z, args.duration)
            print("AVD sensor test completed; original sensor values restored")
        return
    if args.command == "list":
        if args.platform == "android":
            for device in await discover_android():
                print(device)
            return
        from pymobiledevice3.usbmux import list_devices
        for device in await list_devices():
            print(device)
        return
    if args.command == "pair":
        from getpass import getpass
        await pair(args.address, getpass("Android pairing code: "))
        print("Paired successfully")
        return
    if args.command == "validate":
        print(f"valid: {len(load_points(args.route))} points")
        return
    if args.command == "map":
        from .web import serve
        serve(args.host, args.port)
        return
    rsd_host = getattr(args, "rsd_host", None)
    rsd_port = getattr(args, "rsd_port", None)
    if (rsd_host is None) != (rsd_port is None):
        raise ValueError("--rsd-host and --rsd-port must be used together")
    options = None
    if args.platform == "android" and args.command == "play":
        options = {"provider": args.android_provider, "gps_accuracy": args.gps_accuracy,
                   "network_accuracy": args.network_accuracy, "network_interval": args.network_interval}
    device = create_device(args.platform, getattr(args, "udid", None), rsd_host, rsd_port,
                           args.address, android_options=options)
    try:
        await device.connect()
        if args.command == "clear":
            if args.platform == "android":
                await device.clear(existing=True)
            else:
                await device.clear()
        else:
            await device.play(
                load_points(args.route),
                args.interval,
                args.loop,
                args.speed_kmh,
                args.speed_variation_pct,
                args.lateral_variation_m,
                args.random_seed,
                point_variation_m=args.point_variation_m,
            )
    finally:
        await device.close()

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        args = build_parser().parse_args()
        if args.command == "map":
            # serve_forever is synchronous. Running it inside asyncio.run
            # prevents the first Ctrl+C cancellation from being processed.
            from .web import serve
            serve(args.host, args.port)
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nStopped; cleanup was attempted.")

if __name__ == "__main__":
    main()
