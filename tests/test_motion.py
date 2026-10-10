import math
import pytest
from ios_location_controller.motion import Settings, Motion, route_points
from ios_location_controller.gpx import distance_meters
from ios_location_controller.web import parse_gpx

ROUTE = [{"lat":31.2304,"lng":121.4737},{"lat":31.2308,"lng":121.4742}]

@pytest.mark.parametrize('data', [{"speed_kmh":0},{"interval":float('nan')},{"lateral_variation_m":-1},{"point_variation_m":51},{"point_variation_m":-1},{"point_variation_m":float('nan')},{"speed_variation_pct":81},{"loop":"false"},{"random_seed":1.2},{"extra":1}])
def test_invalid_settings(data):
    with pytest.raises(ValueError): Settings.parse(data)

@pytest.mark.parametrize('points', [[],ROUTE[:1],[ROUTE[0],ROUTE[0]],[{"lat":float('nan'),"lng":0},ROUTE[1]],[{"lat":91,"lng":0},ROUTE[1]]])
def test_invalid_routes(points):
    with pytest.raises(ValueError): route_points(points)

def test_motion_repeatability_and_bounds():
    settings=Settings(point_variation_m=3)
    points=route_points(ROUTE)
    a,b=Motion(points,settings),Motion(points,settings)
    for _ in range(10):
        result=a.advance(.5,settings)
        assert result==b.advance(.5,settings)
        assert 4.5 <= result[1] <= 5.5
    assert a.elapsed==5

def test_end_and_loop():
    points=route_points(ROUTE)
    settings=Settings(speed_variation_pct=0,lateral_variation_m=0)
    m=Motion(points,settings)
    p,_,done=m.advance(1000,settings)
    assert done and distance_meters(p,points[-1])<.001
    m=Motion(points,settings)
    assert not m.advance(1000,Settings(loop=True))[2]
    assert m.laps>0


def test_point_variation_is_bounded_and_changes_each_loop():
    points = route_points(ROUTE + [{"lat":31.2308,"lng":121.4737}] + ROUTE[:1])
    settings = Settings(speed_kmh=36, speed_variation_pct=0, lateral_variation_m=0,
                        point_variation_m=5, loop=True, random_seed=7)
    motion = Motion(points, settings)
    variants = [motion._lap_points]
    for _ in range(4):
        motion.advance((motion.total - motion.distance + .001) / (settings.speed_kmh / 3.6), settings)
        variants.append(motion._lap_points)

    for variant in variants:
        assert all(distance_meters(actual, original) <= 5.001
                   for actual, original in zip(variant, points))
    assert motion.laps == 4
    for index in range(len(points)):
        # Check at the eight-decimal precision used by the Android transport.
        assert len({(round(v[index].latitude, 8), round(v[index].longitude, 8))
                    for v in variants}) == 5
    for before, after in zip(variants, variants[1:]):
        assert before[-1] == after[0]
    assert points == route_points(ROUTE + [{"lat":31.2308,"lng":121.4737}] + ROUTE[:1])


def test_sampling_hits_perturbed_nodes_and_pause_keeps_current_variant():
    from dataclasses import replace
    points = route_points(ROUTE + [{"lat":31.2308,"lng":121.4737}])
    settings = Settings(speed_kmh=3.6, speed_variation_pct=0, lateral_variation_m=0,
                        point_variation_m=3)
    motion = Motion(points, settings)
    nodes = motion._lap_points[:]
    assert motion.advance(0, settings)[0] == nodes[0]
    first, _, done = motion.advance(motion.lengths[0], settings)
    assert distance_meters(first, nodes[1]) < 1e-6
    assert not done
    # Like pause/resume, sampling at the same elapsed time retains the point.
    changed = replace(settings, point_variation_m=10, random_seed=99)
    assert motion.advance(0, changed)[0] == first
    final, _, done = motion.advance(motion.total, changed)
    assert done and distance_meters(final, nodes[-1]) < 1e-6


def test_closed_lap_transition_has_no_coordinate_jump():
    points = route_points(ROUTE + ROUTE[:1])
    settings = Settings(speed_kmh=3.6, speed_variation_pct=0, lateral_variation_m=0,
                        point_variation_m=3, loop=True)
    motion = Motion(points, settings)
    before, _, _ = motion.advance(motion.total - .001, settings)
    after, _, _ = motion.advance(.002, settings)
    assert motion.laps == 1
    assert distance_meters(before, after) < .003

def test_gpx_validation():
    assert len(parse_gpx('<gpx><rte><rtept lat="1" lon="2"/><rtept lat="1.1" lon="2"/></rte></gpx>'))==2
    for text in ['<gpx/>','<!DOCTYPE x><gpx/>','<gpx><trkpt lat="nan" lon="0"/></gpx>']:
        with pytest.raises(ValueError): parse_gpx(text)
