import asyncio

from ios_location_controller.cli import build_parser
from ios_location_controller.device import LocationDevice
from ios_location_controller.gpx import Point, distance_meters


def test_cli_player_five_closed_laps_without_a_phone(monkeypatch):
    points = [Point(31.23, 121.47), Point(31.231, 121.47),
              Point(31.231, 121.471), Point(31.23, 121.47)]

    class Finished(Exception):
        pass

    class Recorder(LocationDevice):
        async def set_point(self, point):
            self.sent.append(point)
            if len(self.sent) == 20:
                raise Finished

    async def no_wait(_):
        pass

    monkeypatch.setattr('ios_location_controller.device.asyncio.sleep', no_wait)

    async def record():
        recorder = Recorder()
        recorder.sent = []
        try:
            await recorder.play(points, 1, loop=True, random_seed=42, point_variation_m=3)
        except Finished:
            pass
        return recorder.sent

    sent = asyncio.run(record())
    assert sent == asyncio.run(record())
    for index, original in enumerate(points):
        occurrences = sent[index::len(points)]
        assert len(set(occurrences)) == 5
        assert all(distance_meters(p, original) <= 3.001 for p in occurrences)
    for boundary in (4, 8, 12, 16):
        assert sent[boundary - 1] == sent[boundary]


def test_cli_accepts_point_radius():
    args = build_parser().parse_args(['play', 'route.gpx', '--point-variation-m', '2.5'])
    assert args.point_variation_m == 2.5
