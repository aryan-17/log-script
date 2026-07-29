#!/usr/bin/env python3
"""
BQ Logs Downloader — fetch req/res logs for a booking itinerary.

Usage:
    python bq_logs.py <itinerary-id> [--zip] [--workers N]

Examples:
    python bq_logs.py NIX6de81811-697d-48a5-ab8d-260729143024
    python bq_logs.py NIX6de81811-697d-48a5-ab8d-260729143024 --zip
    python bq_logs.py NIX6de81811-697d-48a5-ab8d-260729143024 --zip --workers 20
"""
import sys
import gzip
import json
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://bqapi.cleartripcorp.me/bqAPI"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-GB,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://statsui.cleartripcorp.me",
    "referer": "https://statsui.cleartripcorp.me/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "token": "DummyToken",
    "user": "DummyEmail",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_booking(iid: str) -> dict:
    url = f"{BASE}/air/book?iId={urllib.parse.quote(iid)}&isSRE=true"
    return json.loads(http_get(url))


def download_file(filename: str, itinerary: str, date: str, trip_id: str, dest: Path) -> None:
    params = urllib.parse.urlencode({
        "name": filename,
        "iId": itinerary,
        "date": date,
        "tripId": trip_id,
    })
    data = http_get(f"{BASE}/file?{params}")
    try:
        data = gzip.decompress(data)
    except Exception:
        pass  # not gzip, save as-is
    txt_name = filename.replace(".gz", "") + ".txt"
    (dest / txt_name).write_bytes(data)



def parse_args(argv):
    args = argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        sys.exit(1)
    iid = args[0]
    do_zip = "--zip" in args
    workers = 10
    if "--workers" in args:
        idx = args.index("--workers")
        workers = int(args[idx + 1])
    return iid, do_zip, workers


def main():
    iid, do_zip, workers = parse_args(sys.argv)

    print(f"Fetching booking: {iid}")
    try:
        resp = fetch_booking(iid)
    except Exception as e:
        print(f"Failed to fetch booking data: {e}")
        sys.exit(1)

    if resp.get("status") != 1:
        print("API returned error status:")
        print(json.dumps(resp, indent=2))
        sys.exit(1)

    payload = resp["data"]
    header = payload["header_data"][0]
    itinerary = header["itinerary"][0]
    trip_id = (header.get("trip") or [""])[0]
    date = payload["air_api_call"][0]["time"].split(" ")[0]

    # only entries whose url is https
    all_calls = payload["air_api_call"]
    https_calls = [c for c in all_calls if c.get("url", "").startswith("https")]

    # build task list: (filename, api_name)
    tasks = []
    seen = set()
    for c in https_calls:
        api_name = c.get("api") or c.get("api_type") or "UNKNOWN"
        # sanitize folder name
        api_name = api_name.replace("/", "_").replace(" ", "_")
        for key in ("req", "res"):
            fname = c.get(key)
            if fname and fname not in seen:
                seen.add(fname)
                tasks.append((fname, api_name))

    print(f"  Itinerary   : {itinerary}")
    print(f"  Trip        : {trip_id or '(none)'}")
    print(f"  Date        : {date}")
    print(f"  HTTPS calls : {len(https_calls)}  →  {len(tasks)} files")
    print()

    out = Path(__file__).parent / f"logs_{itinerary}"
    out.mkdir(parents=True, exist_ok=True)

    errors = []
    done = 0
    total = len(tasks)

    def worker(task):
        filename, api_name = task
        dest = out / api_name
        dest.mkdir(parents=True, exist_ok=True)
        try:
            download_file(filename, itinerary, date, trip_id, dest)
            return filename, api_name, None
        except Exception as e:
            return filename, api_name, str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, t): t for t in tasks}
        for future in as_completed(futures):
            filename, api_name, err = future.result()
            done += 1
            label = "OK " if err is None else "ERR"
            print(f"  [{done:3d}/{total}] [{label}] [{api_name}] {filename[:55]}")
            if err:
                errors.append((filename, err))

    api_folders = [d for d in out.iterdir() if d.is_dir()]
    print(f"\nSaved to: {out.resolve()}")
    for folder in sorted(api_folders):
        count = sum(1 for _ in folder.iterdir())
        print(f"  {folder.name}/ — {count} files")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for f, e in errors:
            print(f"  {f}\n    → {e}")

    if do_zip:
        zip_name = str(out)
        zip_path = shutil.make_archive(zip_name, "zip", out.parent, out.name)
        print(f"\nZipped: {zip_path}")
    else:
        print(f"\nTo zip: zip -r {out}.zip {out}/")


if __name__ == "__main__":
    main()
