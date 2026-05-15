#!/usr/bin/env python3
"""Generate a single layout preview frame and exit."""

import argparse
import os
import pathlib
import random
import sys
from datetime import timedelta
from time import sleep
from xml.etree import ElementTree

# Use local source code instead of installed package
script_dir = pathlib.Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from PIL import Image
from pint import DimensionalityError

from gopro_overlay import fake, geo, timeseries_process
from gopro_overlay.arguments import default_config_location
from gopro_overlay.config import Config
from gopro_overlay.dimensions import dimension_from, Dimension
from gopro_overlay.ffmpeg import FFMPEG
from gopro_overlay.ffmpeg_gopro import FFMPEGGoPro
from gopro_overlay.font import load_font
from gopro_overlay.geo import MapRenderer, api_key_finder, MapStyler
from gopro_overlay.layout import Overlay
from gopro_overlay.layout_xml import layout_from_xml, load_xml_layout
from gopro_overlay.log import log
from gopro_overlay.privacy import NoPrivacyZone
from gopro_overlay.timeunits import timeunits
from gopro_overlay.units import units
from gopro_overlay.widgets.widgets import SimpleFrameSupplier


def main():
    parser = argparse.ArgumentParser(description="Render a single layout preview frame")
    parser.add_argument("file", type=pathlib.Path, help="Input layout file")
    parser.add_argument("--overlay-size", default="1920x1080", help="Size of frame, e.g. 1920x1080")
    parser.add_argument("--output", "-o", type=pathlib.Path, required=True, help="Output PNG file")
    parser.add_argument("--font", default="Coolvetica.otf", help="Font file")
    parser.add_argument("--map-style", choices=geo.available_map_styles(), default="osm")
    parser.add_argument("--cache-dir", type=pathlib.Path, default=default_config_location)

    args = parser.parse_args()

    cache_dir = args.cache_dir
    cache_dir.mkdir(exist_ok=True)

    font = load_font(args.font)
    config_loader = Config(cache_dir)
    key_finder = api_key_finder(config_loader, args)

    dimensions = dimension_from(args.overlay_size)
    rng = random.Random()
    rng.seed(12345)
    timeseries = fake.fake_framemeta(timedelta(minutes=5), step=timedelta(seconds=1), rng=rng, point_step=0.0001)

    with MapRenderer(
        cache_dir=cache_dir,
        styler=MapStyler(api_key_finder=key_finder)
    ).open(args.map_style) as renderer:

        layout_file: pathlib.Path = args.file
        if not layout_file.exists():
            print(f"Layout file not found: {layout_file}")
            sys.exit(1)

        try:
            layout = layout_from_xml(load_xml_layout(args.file), renderer, timeseries, font, NoPrivacyZone())
            overlay = Overlay(
                framemeta=timeseries,
                create_widgets=layout
            )
            supplier = SimpleFrameSupplier(dimensions)
            frame = overlay.draw(timeseries.mid, supplier.drawing_frame())
            frame.save(str(args.output))
            print(f"Saved: {args.output}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
