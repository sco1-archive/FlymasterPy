import datetime as dt
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import List, NamedTuple, Union, Tuple

import click
import pandas as pd


class TrackEntry(NamedTuple):
    """Represent a track record log entry."""

    timestamp: dt.datetime
    latitude: str
    longitude: str
    fix_validity: str
    pressure_altitude: int
    gps_altitude: int


class FlymasterLog:
    """Represent a Flymaster flight log."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.log_date, self._log_date_str = self.date_from_filename(self.filepath)
        self.headers, self.track = self.parse_log()

    def parse_log(self) -> Tuple[List[str], List[TrackEntry]]:
        """
        Parse the Flymaster log & separate headers & track logs into discrete lists.

        Headers are returned as-is, track logs are converted to TrackEntry named tuples.
        """
        headers = []
        track = []
        uncategorized = []
        with self.filepath.open("r") as f:
            for line in f:
                if line.startswith(("A", "H", "L")):
                    # Manufacturer ID (A), File Header (H), Logbook/commends (L)
                    headers.append(line.strip())
                elif line.startswith("B"):
                    # Track log
                    track.append(self.parse_track_entry(line))
                else:
                    uncategorized.append(line.strip())

        return headers, track

    def parse_track_entry(self, log_entry: str) -> TrackEntry:
        """
        Parse the relevant parameters out of the log entry and create a TrackEntry named tuple.

        Log entry is assumed to be formatted according to IGC specification:
            e.g. B1320450030251N00020296WA0058200583
            B HHMMSS DDMMmmmN/S DDDMMmmmE/W  A/V PPPPP GGGGG
                HHMMSS is the UTC time
                DDMMmmm N/S, DDDMMmmm E/W is GPS decimal degrees
                A/V is the fix validity, A for 3D, V for 2D
                PPPPP is pressure altitude (1013.25 HPa Sea Level)
                GGGG is GPS altitude (WGS84 ellipsoid)

        Per IGC spec, log date comes from the name of the file, which we've parsed in another method
        """
        # Generate regex to match the IPC specification w/named groups
        exp = (
            r"B(?P<time>\d{6})"
            r"(?P<lat_deg>\d{2})(?P<lat_min>\d{2})(?P<lat_dec_min>\d{3})(?P<lat_dir>\w)"
            r"(?P<lon_deg>\d{3})(?P<lon_min>\d{2})(?P<lon_dec_min>\d{3})(?P<lon_dir>\w)"
            r"(?P<fix>\w)(?P<press_alt>\d{5})(?P<gps_alt>\d{5})"
        )
        log_groups = re.findall(exp, log_entry)[0]

        time_exp = "%y%m%d%H%M%S"
        full_timestamp = f"{self._log_date_str}{log_groups[0]}"
        log_dt = dt.datetime.strptime(full_timestamp, time_exp)

        latitude = f"{log_groups[1]} {log_groups[2]}.{log_groups[3]} {log_groups[4]}"
        longitude = f"{log_groups[5]} {log_groups[6]}.{log_groups[7]} {log_groups[8]}"

        fix_validity = log_groups[9]
        press_alt = int(log_groups[10])
        gps_alt = int(log_groups[11])

        return TrackEntry(log_dt, latitude, longitude, fix_validity, press_alt, gps_alt)

    def to_excel(self):
        """Export track log to *.xlsx."""
        start_time = self.track[0].timestamp
        track_df = pd.DataFrame(self.track)
        track_df["time"] = track_df["timestamp"].apply(self._normalize_timestamp, args=[start_time])
        track_df.set_index("time", inplace=True)

        out_filepath = self.filepath.with_suffix(".xlsx")
        track_df.to_excel(out_filepath)

    @staticmethod
    def date_from_filename(filepath: Path) -> Tuple[dt.date, str]:
        """
        Parse the date from the Flymaster log's filename.

        Log file name is assumed to be named according to IGC Specification:
            YYMMDD??????.igc

        Optionaly return the raw log date string
        """
        date_segment = filepath.stem[:6]
        log_date = dt.date.fromisoformat(
            f"20{date_segment[:2]}-{date_segment[2:4]}-{date_segment[4:6]}"
        )

        return log_date, date_segment

    @staticmethod
    def _normalize_timestamp(timestamp: dt.datetime, start_time: dt.datetime) -> float:
        """Normalize timestamp to time since the log begain."""
        delta = timestamp - start_time
        return delta.total_seconds()


def processing_pipeline(data_dir: Path):
    """
    Recursively iterate over all *.igc files in the top-level directory and export to *.xlsx.

    Note: *.igc files with an exactly named *.xlsx partner in the same directory are ignored.
    """
    for log_file in data_dir.rglob("*.igc"):
        # Check for existing conversion
        file_as_xlsx = log_file.with_suffix(".xlsx")
        if file_as_xlsx.exists():
            continue
        else:
            FlymasterLog(log_file).to_excel()


@click.command()
@click.option("-d", "--datadir", default=None, help="Top level data directory")
def cli(datadir: Union[str, None]):
    """
    CLI Userflow.

    If no `datadir` is explicitly specified, the user is prompted to select the top-level data
    directory.
    """
    if not datadir:
        # Generate a Tk file selection dialog to select the top level data dir if none is provided
        # to the CLI
        root = tk.Tk()
        root.withdraw()
        datadir = Path(filedialog.askdirectory(title="Select Data Directory"))
    else:
        datadir = Path(datadir)

    processing_pipeline(datadir)


if __name__ == "__main__":
    cli()
