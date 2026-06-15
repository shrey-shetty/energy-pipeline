# energy-pipeline

A data pipeline project for energy market datasets.

## What this repo contains

- `index.js` - Google Cloud Functions trigger that starts a Dataproc batch job.
- `scripts/` - Python ETL and cleaning scripts for SMARD and ENTSOE data.
- `package.json` - Node.js dependencies and startup script.
- `requirements.txt` - Python library requirements.
- `Procfile` - Heroku-style start command for web deployment.

## Setup

1. Install Node.js dependencies:
   ```bash
   npm install
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Update `index.js` with your Google Cloud project and bucket settings.

4. Configure your local environment and credentials for Google Cloud.

## Notes

- Large raw CSV and Parquet dataset files are excluded from the GitHub repository to keep the repo size manageable.
- Keep your local data in `data/` or store it in a cloud storage bucket.

## Deploy to GitHub

This repo is ready to be published to GitHub. After creating the remote repository, push with:

```bash
git remote add origin https://github.com/<your-user>/energy-pipeline.git
git branch -M main
git push -u origin main
```
