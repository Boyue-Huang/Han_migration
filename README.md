# Han Cloud Run Migration

This repository contains the Cloud Run Jobs migration package for HAN advertising data pipelines. It packages existing Python ETL scripts into a Docker image, deploys them as Google Cloud Run Jobs, and schedules recurring execution through Cloud Scheduler.

## What This Project Does

The jobs collect and process advertising data from multiple media platforms, then write the normalized outputs into BigQuery.

Included job scripts:

- `facebook_api_daily_cmb.py`: Facebook Ads daily reporting import.
- `facebook_api_image.py`: Facebook ad image and creative metadata import.
- `line_api_daily_cmb.py`: LINE Ads API daily reporting import.
- `GoogleAds_API_daily.py`: Google Ads daily creative, keyword, and union table processing.
- `GoogleAds_Pmax.py`: Google Ads Performance Max reporting import.
- `Dable_API_daily.py`: Dable campaign reporting import.
- `popin_api_daily_cmb.py`: PopIn campaign reporting import.
- `Union_mediaTables.py`: BigQuery media table union logic.

`run_job.py` is the container entrypoint. It reads the `SCRIPT` environment variable, validates it against an allowlist, writes secret files from environment variables when provided, and executes the selected job script.

## Repository Layout

```text
.
├── Dockerfile
├── deploy.ps1
├── requirements.txt
├── run_job.py
├── *_daily*.py
├── GoogleAds_*.py
├── Dable_*.py
├── meta_token.py              # ignored, supplied through Secret Manager
├── GoogleAds_api_token_Han.py # ignored, supplied through Secret Manager
└── *.json                     # ignored, GCP service account keys
```

## Requirements

- Python 3.11
- Google Cloud SDK
- Docker or Google Cloud Build
- Access to the GCP project `eco-carver-356809`
- Required Google Cloud APIs:
  - Artifact Registry
  - Cloud Build
  - Cloud Run
  - Cloud Scheduler
  - Secret Manager
  - IAM

Python dependencies are pinned in `requirements.txt`.

## Secrets

Credentials and API tokens are intentionally not committed to GitHub.

The deployment script expects these local files so it can upload them to Google Secret Manager:

- `GoogleAds_api_token_Han.py`
- `Dable_Parm_token.py`
- `meta_token.py`
- `eco-carver-356809-38c8914cd90f.json`
- `eco-carver-356809-a5ccbfde00b9.json`

At runtime, Cloud Run Jobs mount these secrets into environment variables:

- `GOOGLEADS_TOKEN_PY`
- `DABLE_TOKEN_PY`
- `META_TOKEN_PY`
- `BQ_MAIN_JSON`
- `BQ_SHEETS_JSON`

`run_job.py` writes those values back to the file names expected by the legacy scripts inside `/app`.

## Local Run

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run one job locally by setting `SCRIPT`:

```powershell
$env:SCRIPT = "GoogleAds_API_daily.py"
python run_job.py
```

For local execution, the ignored credential and token files must exist in the project root because the legacy scripts read those file names directly.

## Docker Run

Build the image:

```powershell
docker build -t han-jobs .
```

Run one job:

```powershell
docker run --rm -e SCRIPT=facebook_api_daily_cmb.py han-jobs
```

When running in Docker outside Cloud Run, provide the required secret environment variables or mount the credential files manually.

## Deployment

`deploy.ps1` automates Google Cloud setup and deployment:

1. Enables required Google Cloud APIs.
2. Creates the Artifact Registry repository if missing.
3. Creates the Cloud Run Jobs service account if missing.
4. Grants required IAM roles.
5. Uploads local token and credential files to Secret Manager.
6. Builds and pushes the Docker image with Cloud Build.
7. Creates or updates Cloud Run Jobs.
8. Creates or updates Cloud Scheduler triggers in the `Asia/Taipei` timezone.

Run deployment:

```powershell
.\deploy.ps1
```

Default deployment settings:

- Project: `eco-carver-356809`
- Region: `asia-east1`
- Artifact Registry repo: `han-cron`
- Image: `asia-east1-docker.pkg.dev/eco-carver-356809/han-cron/han-jobs:latest`
- Service account: `han-cloud-run-jobs@eco-carver-356809.iam.gserviceaccount.com`

## Scheduled Jobs

The deployment script currently schedules:

- `han-facebook-api-daily-cmb`: 06:00 daily
- `han-facebook-api-image`: 06:00 daily
- `han-line-api-daily-cmb`: 06:00 daily
- `han-googleads-api-daily-0730`: 07:30 daily
- `han-googleads-pmax-0830`: 08:30 daily
- `han-dable-api-daily`: 08:50 daily
- `han-popin-api-daily-1100`: 11:00 daily
- `han-googleads-pmax-1305`: 13:05 daily
- `han-popin-api-daily-1400`: 14:00 daily
- `han-googleads-api-daily-1740`: 17:40 daily
- `han-googleads-pmax-1750`: 17:50 daily

All schedules use the `Asia/Taipei` timezone.
