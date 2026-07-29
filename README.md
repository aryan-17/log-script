# BQ Logs Downloader

CLI to download req/res logs for a flight booking itinerary from bqAPI.

Filters only HTTPS-layer calls (Amadeus supplier calls) and saves them locally.

## Requirements

- Python 3.6+
- No external dependencies

## Setup

Clone the repo:

```bash
git clone git@github.com:aryan-17/log-script.git
cd log-script
```

Add a global alias so you can run it from anywhere:

```bash
echo 'alias bq_logs="python3 /path/to/log-script/bq_logs.py"' >> ~/.zshrc
source ~/.zshrc
```

## Usage

```bash
bq_logs <itinerary-id>
```

### Options

| Flag | Description |
|------|-------------|
| `--zip` | Auto-zip the output folder after download |
| `--workers N` | Number of parallel download threads (default: 10) |

### Examples

```bash
# basic download
bq_logs NIX6de81811-697d-48a5-ab8d-260729143024

# download and zip
bq_logs NIX6de81811-697d-48a5-ab8d-260729143024 --zip

# faster with more workers
bq_logs NIX6de81811-697d-48a5-ab8d-260729143024 --zip --workers 20
```

## Output

Logs are saved next to the script:

```
log-script/
  logs_<itinerary-id>/
    req/   ← request payloads  (.gz)
    res/   ← response payloads (.gz)
```

Only files from API calls with HTTPS URLs are downloaded (supplier-level calls like Amadeus).

## Notes

- `token` and `user` headers in the script use dummy values — update them in `bq_logs.py` if the API requires real credentials.
- To manually zip after download: `zip -r logs_<id>.zip logs_<id>/`
