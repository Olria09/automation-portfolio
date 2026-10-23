# Local Rules-Based Job Search

A local tool that collects job listings from public RSS/Atom feeds, removes duplicates, scores listings with explainable keyword rules, and exports a prioritized CSV. It uses Python’s standard library only. It does not submit applications or send data to an LLM.

## Requirements

- Python 3.9 or newer
- Public RSS/Atom feeds for job listings

No third-party Python packages are required.

## Setup

Copy the example configuration to a local file, then add the public feed URLs you want to monitor:

```bash
cp config.example.json config.json
```

`config.json`, the SQLite database, and generated CSVs are excluded from Git. Adjust the role tracks and keyword filters in your local configuration.

## Run

Validate your configuration:

```bash
python job_search.py --check-config
```

Fetch listings, deduplicate them, score them, and export a CSV:

```bash
python job_search.py run --export
```

Export listings already stored in the local database:

```bash
python job_search.py export
```

The database and CSV are created beside `config.json` by default. The CSV is written to `salida/ofertas.csv`.

## How scoring works

The score uses configurable role-title matches, skill matches, remote-work signals, location signals, and exclusion terms. The script records the reasons for each score so listings can be reviewed. A high score is only a ranking aid: it does not confirm that an employer accepts applications from your country or that the role is current.

## Privacy and limitations

- Listings are fetched from the feed URLs in your local config; no applications are submitted.
- Job descriptions and URLs are stored in your local SQLite database and exported CSV. Keep both private if they contain personal notes.
- Feeds vary in format and availability. A feed error is reported and does not prevent other feeds from being processed.
- Review each listing on the employer’s site before applying.
