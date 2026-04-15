#
# GeoTiler - library to create maps using tiles from a map provider
#
# Copyright (C) 2014 - 2023 by Artur Wroblewski <wrobell@riseup.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
# This file incorporates work covered by the following copyright and
# permission notice (restored, based on setup.py file from
# https://github.com/stamen/modestmaps-py):
#
#   Copyright (C) 2007-2013 by Michal Migurski and other contributors
#   License: BSD
#

"""
Tests for rendering map image using map tile data.
"""

import asyncio
import io
import PIL.Image  # type: ignore

from gopro_overlay.vendor.geotiler.map import Tile
import gopro_overlay.vendor.geotiler.tile.img as tile_img

from unittest import mock


def _run_render_image(map, tiles):
    """
    Run coroutine rendering map image using the map tiles.

    :param map: Map object.
    :param tiles: Asynchronous generator of tiles.
    """
    loop = asyncio.get_event_loop()
    task = tile_img.render_image(map, tiles)
    image = loop.run_until_complete(task)
    return image

async def _tile_generator(offsets, data):
    """
    Create asynchronous generator of map tiles.
    """
    for o, i in zip(offsets, data):
        yield Tile(None, o, i, None)

def test_render_error_tile():
    """
    Test rendering of error tile.
    """
    tile_img._error_image.cache_clear()
    img = tile_img._error_image(10, 10)
    assert (10, 10) == img.size

def test_tile_image_png():
    """
    Test converting PNG data into PIL image object.
    """
    tile = PIL.Image.new('RGBA', (10, 11))
    f = io.BytesIO()
    tile.save(f, format='png')

    img = tile_img._tile_image(f.getbuffer())
    assert (10, 11) == img.size

def test_tile_image_jpg():
    """
    Test converting JPEG data into PIL image object.
    """
    tile = PIL.Image.new('RGB', (12, 10))
    f = io.BytesIO()
    tile.save(f, format='jpeg')

    img = tile_img._tile_image(f.getbuffer())
    assert (12, 10) == img.size

# removed some mock tests.