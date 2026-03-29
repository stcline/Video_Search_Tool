from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import re
import shutil

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".m4v", ".mpg", ".mpeg"}
TIMESTAMP_PATTERN = re.compile(r"_(\d{8})_(\d{6})(?=\.[^.]+$)")
DATETIME_INPUT_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y%m%d %H%M%S",
    "%Y%m%d %H%M",
    "%Y%m%d_%H%M%S",
    "%Y%m%d_%H%M",
    "%Y%m%d%H%M%S",
    "%Y%m%d%H%M",
]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Search video files by filename timestamp, export CSV, and copy matches "
            "to a destination folder."
        )
    )
    parser.add_argument("-f", "--folder", help="Folder to search recursively for video files.")
    parser.add_argument("-d", "--destination", help="Folder to copy matched files into.")
    parser.add_argument(
        "-s",
        "--start",
        help=(
            "Start date/time (inclusive). Examples: '2026-03-28 15:00:00' or "
            "'20260328_150000'."
        ),
    )
    parser.add_argument(
        "-e",
        "--end",
        help=(
            "End date/time (inclusive). Examples: '2026-03-28 18:30:00' or "
            "'20260328_183000'."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default="video_matches.csv",
        help="Output CSV path (default: video_matches.csv).",
    )
    return parser


def parse_user_datetime(raw_value: str) -> datetime | None:
    for fmt in DATETIME_INPUT_FORMATS:
        try:
            return datetime.strptime(raw_value, fmt)
        except ValueError:
            continue
    return None


def parse_datetime_or_raise(raw_value: str, label: str) -> datetime:
    parsed = parse_user_datetime(raw_value)
    if parsed is None:
        raise ValueError(
            f"Invalid {label} date/time '{raw_value}'. Use formats like "
            "'2026-03-28 15:00:00' or '20260328_150000'."
        )
    return parsed


def prompt_directory(prompt_text: str, create_if_missing: bool = False) -> Path:
    while True:
        raw_value = input(prompt_text).strip().strip('"')
        folder = Path(raw_value).expanduser()

        if folder.exists() and folder.is_dir():
            return folder

        if create_if_missing and raw_value:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                return folder
            except OSError as exc:
                print(f"Could not create folder: {exc}")
                continue

        print("Folder not found. Please enter a valid directory path.")


def prompt_datetime(label: str) -> datetime:
    prompt = (
        f"Enter {label} date/time "
        "(examples: 2026-03-28 15:00:00 or 20260328_150000): "
    )
    while True:
        raw_value = input(prompt).strip()
        parsed = parse_user_datetime(raw_value)
        if parsed is not None:
            return parsed
        print("Invalid date/time format. Please try again.")


def extract_timestamp_from_filename(filename: str) -> datetime | None:
    match = TIMESTAMP_PATTERN.search(filename)
    if not match:
        return None

    date_part, time_part = match.groups()
    try:
        return datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
    except ValueError:
        return None


def find_matching_videos(folder: Path, start_dt: datetime, end_dt: datetime) -> list[tuple[Path, datetime]]:
    matches: list[tuple[Path, datetime]] = []

    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        timestamp = extract_timestamp_from_filename(path.name)
        if timestamp is None:
            continue

        if start_dt <= timestamp <= end_dt:
            matches.append((path.resolve(), timestamp))

    matches.sort(key=lambda item: item[1])
    return matches


def write_csv(output_path: Path, matches: list[tuple[Path, datetime]]) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["filepath", "filename", "timestamp"])
        for path, timestamp in matches:
            writer.writerow([str(path), path.name, timestamp.strftime("%Y-%m-%d %H:%M:%S")])


def next_available_path(target: Path) -> Path:
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    counter = 1

    while True:
        candidate = target.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def copy_matches(matches: list[tuple[Path, datetime]], destination: Path) -> list[Path]:
    copied_paths: list[Path] = []

    for source_path, _ in matches:
        target_path = next_available_path(destination / source_path.name)
        shutil.copy2(source_path, target_path)
        copied_paths.append(target_path)

    return copied_paths


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    print("Video Copy Tool")
    print("This scans filenames for timestamps (YYYYMMDD_HHMMSS), exports CSV, and copies matches.")

    if args.folder:
        search_folder = Path(args.folder).expanduser()
        if not search_folder.is_dir():
            parser.error(f"Folder not found: {search_folder}")
    else:
        search_folder = prompt_directory("Enter the folder to search: ")

    if args.destination:
        destination_folder = Path(args.destination).expanduser()
        try:
            destination_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            parser.error(f"Could not create destination folder '{destination_folder}': {exc}")
    else:
        destination_folder = prompt_directory(
            "Enter the destination folder to copy matches into: ",
            create_if_missing=True,
        )

    if args.start:
        try:
            start_dt = parse_datetime_or_raise(args.start, "START")
        except ValueError as exc:
            parser.error(str(exc))
    else:
        start_dt = prompt_datetime("START")

    if args.end:
        try:
            end_dt = parse_datetime_or_raise(args.end, "END")
        except ValueError as exc:
            parser.error(str(exc))
    else:
        end_dt = prompt_datetime("END")

    if end_dt < start_dt:
        parser.error("END date/time must be greater than or equal to START.")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    matches = find_matching_videos(search_folder, start_dt, end_dt)
    write_csv(output_path, matches)

    copied_paths = copy_matches(matches, destination_folder)

    print(f"Search complete. {len(matches)} matching file(s) written to:")
    print(output_path)
    print(f"Copied {len(copied_paths)} file(s) to:")
    print(destination_folder)


if __name__ == "__main__":
    main()
