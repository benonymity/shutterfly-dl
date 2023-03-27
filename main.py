#!/usr/bin/env python3
import argparse
import logging
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple, TypedDict

import chompjs
import requests
from exif import Image
from pathvalidate import sanitize_filename, sanitize_filepath

DMS = Tuple[int, int, int]
Coordinate = Tuple[DMS, DMS]


def decimal_to_dms(decimal: float) -> DMS:
    """Converts a geo coordinate decimal to (degrees, minutes, seconds)"""
    negative = decimal < 0
    decimal = abs(decimal)
    minutes, seconds = divmod(decimal * 3600, 60)
    degrees, minutes = divmod(minutes, 60)
    if negative:
        if degrees > 0:
            degrees = -degrees
        elif minutes > 0:
            minutes = -minutes
        else:
            seconds = -seconds
    return (int(degrees), int(minutes), int(seconds))


def lat_long_decimal_to_dms(coord: str) -> Coordinate:
    """Converts geo lat long coordinates from decimals to degrees, minutes,
    seconds.

    See: https://en.wikipedia.org/wiki/Geographic_coordinate_conversion
    """
    (N, W) = coord.split(",")
    return (decimal_to_dms(float(N)), decimal_to_dms(float(W)))


class Photo(TypedDict):
    id: str
    title: str
    url: str
    capture_date: Optional[datetime]


class Album(TypedDict):
    title: str
    photos: List[Photo]


def download_albums(
    albums: List[Album], download_dir: Path, coordinate: Optional[Coordinate]
) -> bool:
    """Downloads all the given albums to the given directory."""
    if not download_dir.is_dir():
        logging.error(f"Does not exist or is not a directory: {download_dir}")
        return False

    for album in albums:
        logging.info(f"Downloading album: {album['title']}")
        group_path = download_dir / sanitize_filepath(album["title"].replace("/", " "))
        group_path.mkdir(exist_ok=True)
        for photo in album["photos"]:
            # Download file
            filename = group_path / sanitize_filename(photo["title"])
            if filename.exists():
                logging.debug(f"> {filename} exists already, so skipping download")
                continue
            if not "." in str(filename):
                filename = str(filename) + ".jpg"
            if "file.jpg" in str(filename):
                filename = str(filename)[:-8] + str(uuid.uuid4()) + ".jpg"
            logging.info(f"> Downloading image: {filename}")
            req = requests.get(photo["url"], stream=True)
            with open(filename, "wb") as fd:
                for chunk in req.iter_content(chunk_size=65536):
                    fd.write(chunk)

            if coordinate:
                try:
                    with open(filename, "rb") as image_file:
                        image = Image(image_file)
                    image.gps_latitude = coordinate[0]
                    image.gps_latitude_ref = "N"
                    image.gps_longitude = coordinate[1]
                    image.gps_longitude_ref = "W"

                    with open(filename, "wb") as image_file:
                        image_file.write(image.get_file())
                except RuntimeError as err:
                    logging.warning(f"Unable to store EXIF data: {err}")

            # Set file date to capture date
            if photo["capture_date"]:
                dt_str = photo["capture_date"].strftime("%Y%m%d%H%M")
                subprocess.run(["/usr/bin/touch", "-mt", dt_str, filename])

    return True


def _get_albums_data(token: str, site: str) -> Any:
    """Fetches the raw albums data."""
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Gecko/20100101 Firefox/96.0",
        }
    )
    session.cookies.update({"ShrAuth": token})
    body = {
        "startIndex": "0",
        "size": "-1",
        "pageSize": "-1",
        "page": f"{site}/pictures",
        "nodeId": "5",
        "format": "json",
        "layout": "ManagementAlbums",
    }
    resp = session.post(
        f"https://cmd.shutterfly.com/commands/pictures/getitems?site={site}", data=body
    )
    logging.debug(f"Response: {resp.text}")
    return chompjs.parse_js_object(resp.text)


def _parse_albums(albums_data: Any, token: str, site: str) -> List[Album]:
    """Parses the albums and photos data from the Shutterfly JS."""
    # print(albums_data)
    ret: List[Album] = []
    groups = albums_data["result"]["section"]["groups"]
    for group in groups:
        album: Album = {
            "title": group["title"],
            "photos": [],
        }
        session = requests.Session()
        session.headers.update(
            {
                "Accept": "*/*",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:96.0) Gecko/20100101 Firefox/96.0",
            }
        )
        session.cookies.update({"ShrAuth": token})
        body = {
            "startIndex": "0",
            "size": "-1",
            "pageSize": "-1",
            "page": (site + "/pictures"),
            "nodeId": group["nodeId"],
            "format": "json",
            "layout": "ManagementAlbumPictures",
        }
        resp = session.post(
            f"https://cmd.shutterfly.com/commands/pictures/getitems?site={site}",
            data=body,
        )
        items = chompjs.parse_js_object(resp.text)["result"]["section"]["items"]
        for item in items:
            id = item["shutterflyId"]
            capture_date = (
                datetime.fromtimestamp(item["captureDate"])
                if item["captureDate"]
                else None
            )
            photo: Photo = {
                "id": id,
                "title": item["title"],
                "url": f"https://uniim-share.shutterfly.com/v2/procgtaserv/{id}",
                "capture_date": capture_date,
            }
            album["photos"].append(photo)

        ret.append(album)

    return ret


def get_albums(token: str, site: str) -> List[Album]:
    """Gets the albums for all albums for the given site."""
    albums_data = _get_albums_data(token, site)
    return _parse_albums(albums_data, token, site)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--token",
        type=str,
        required=True,
        help="Authentication token (ie ShrAuth cookie contents)",
    )
    parser.add_argument("--site", type=str, required=True, help="Share Sites site name")
    parser.add_argument(
        "--directory", type=str, default=".", help="Directory to download photos to"
    )
    parser.add_argument(
        "--geo",
        type=str,
        help="Adds geo coordinates EXIF data to all the photos (ex: 40.73351445015099, -74.00306282630127)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Turns on verbose logging"
    )

    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    albums = get_albums(args.token, args.site)
    coordinate = None
    if args.geo:
        coordinate = lat_long_decimal_to_dms(args.geo)
    success = download_albums(albums, Path(args.directory), coordinate)
    return 0 if success else 1


if __name__ == "__main__":
    main()
