import datetime
from os import path

import pytest
from pint.registry import Quantity

from gopro_overlay import fit
from gopro_overlay.units import units
from test_gpx import file_path_of_test_asset


def test_converting_fit_without_power_to_timeseries():
    ts = fit.load_timeseries(file_path_of_test_asset("fit-file-no-power.fit", in_dir="fit"), units)

    # 3 are filtered out due to no la/lon
    assert len(ts) == 8597

    item = ts.items()[26]

    assert item.point.lat == pytest.approx(51.3397, abs=0.0001)
    assert item.point.lon == pytest.approx(-2.572136, abs=0.0001)
    assert item.alt.units == units.m
    assert item.alt.magnitude == pytest.approx(96.6, abs=0.1)
    assert item.hr == units.Quantity(72, units.bpm)
    assert item.atemp == units.Quantity(16, units.celsius)
    assert item.odo == units.Quantity(53.77, units.m)
    assert item.gpsfix == 3


def test_converting_fit_with_power_to_timeseries():
    ts = fit.load_timeseries(file_path_of_test_asset("fit-file-with-power.fit", in_dir="fit"), units)

    assert len(ts) == 2945

    item = ts.items()[26]

    assert item.power == units.Quantity(80, units.watt)
    assert item.odo == units.Quantity(114.96, units.m)
    assert item.gpsfix == 3


def test_converting_fit_with_gear_changes_and_power_data_bugfix():
    p = file_path_of_test_asset("issue-272.fit", in_dir="fit", allow_missing=True)
    if p is None:
        pytest.skip("Private test asset not present")

    fit.load_timeseries(p,units)


def test_converting_fit_with_gear_changes_and_respiration():
    p = file_path_of_test_asset("2025-07-24-17-55-12.fit", in_dir="fit", allow_missing=True)
    if p is None:
        pytest.skip("Private test asset not present")

    ts = fit.load_timeseries(p,units)

    entry_with_event_following = ts.get(datetime.datetime(2025, 7, 24, 15, 56, 33,tzinfo=datetime.timezone.utc))
    assert(entry_with_event_following.items['gear_front']) == Quantity(2)
    assert(entry_with_event_following.items['gear_rear']) == Quantity(6)

    entry_picking_up_previous_data = ts.get(datetime.datetime(2025, 7, 24, 16, 56, 38,tzinfo=datetime.timezone.utc))
    assert(entry_picking_up_previous_data.items['gear_front']) == Quantity(2)
    assert(entry_picking_up_previous_data.items['gear_rear']) == Quantity(5)

    entry_with_event_following = ts.get(datetime.datetime(2025, 7, 24, 16, 56, 39,tzinfo=datetime.timezone.utc))
    assert(entry_with_event_following.items['gear_front']) == Quantity(2)
    assert(entry_with_event_following.items['gear_rear']) == Quantity(6)

    entry_with_respiration = ts.get(datetime.datetime(2025, 7, 24, 15, 55, 25,tzinfo=datetime.timezone.utc))
    assert(entry_with_respiration.items['respiration']) == Quantity(21.47, units.brpm)
