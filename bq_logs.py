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


def classify(filename: str) -> str:
    if "-req.gz" in filename:
        return "req"
    if "-res.gz" in filename:
        return "res"
    return "other"


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
    files = []
    for c in https_calls:
        if c.get("req"):
            files.append(c["req"])
        if c.get("res"):
            files.append(c["res"])
    files = list(dict.fromkeys(files))  # deduplicate, preserve order

    print(f"  Itinerary : {itinerary}")
    print(f"  Trip      : {trip_id or '(none)'}")
    print(f"  Date      : {date}")
    print(f"  HTTPS calls : {len(https_calls)}  →  {len(files)} files")
    print()

    out = Path(__file__).parent / f"logs_{itinerary}"
    for sub in ("req", "res"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    errors = []
    done = 0
    total = len(files)

    def worker(filename):
        cat = classify(filename)
        dest = out / cat
        dest.mkdir(parents=True, exist_ok=True)
        try:
            download_file(filename, itinerary, date, trip_id, dest)
            return filename, cat, None
        except Exception as e:
            return filename, cat, str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, f): f for f in files}
        for future in as_completed(futures):
            filename, cat, err = future.result()
            done += 1
            label = "OK " if err is None else "ERR"
            short = filename[:65]
            print(f"  [{done:3d}/{total}] [{label}] [{cat:5s}] {short}")
            if err:
                errors.append((filename, err))

    req_count = sum(1 for _ in (out / "req").iterdir())
    res_count = sum(1 for _ in (out / "res").iterdir())

    print(f"\nSaved to: {out.resolve()}")
    print(f"  req/ — {req_count} files")
    print(f"  res/ — {res_count} files")

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
