# Compound Heat & Air Pollution Exposure Planner

Choose a place to see how many zones combine high surface heat, pollution, limited greenery and residential exposure. Follow the numbered map to five separated hotspots with shade, roof or shelter actions, or compare two places over the same summer window.

## Run from a fresh clone

Prerequisites on macOS or Linux are Git, Make, uv and Python 3.12. The first installation downloads the pinned packages from PyPI. Both bundled presets run offline after installation.

1. Clone the project. Replace `<repository-url-or-local-path>` with your Git remote or the path to a local copy of this repository.

   ```sh
   git clone --branch simplify "<repository-url-or-local-path>" heat-exposure-planner
   cd heat-exposure-planner
   ```

2. Create the environment and install the hash-locked dependencies.

   ```sh
   mkdir -p .local/tmp
   UV_CACHE_DIR="$PWD/.local/uv" uv venv --python 3.12
   make install
   ```

3. Start Streamlit from the repository root.

   ```sh
   .venv/bin/streamlit run app.py
   ```

Open the **Local URL** printed by Streamlit. The central Delhi (28.62° N, 77.23° E) and central Bengaluru (12.97° N, 77.59° E) presets contain 353 and 355 zones respectively, using a 5 km radius and 500 m grid. Both use summer readings from 2019–2021. [Snapshot sources](data/demo/SOURCES.md)

## Live Earth Engine analysis

Use a Cloud project registered for Earth Engine, with the Earth Engine API enabled and permissions for the account doing the computation. Copy the settings template, then set `EE_PROJECT` in the local `.env` to your project ID. [Earth Engine setup](https://developers.google.com/earth-engine/guides/access) · [IAM roles](https://developers.google.com/earth-engine/guides/access_control)

```sh
cp -n .env.example .env
```

The SDK reuses an existing Earth Engine login. For a first login, run `.venv/bin/earthengine authenticate` interactively. Restart the app after changing the project or credentials. Open **Custom coordinates**, enable it and enter a latitude and longitude. The story accepts a 1–15 km radius; Compare fixes both radii at 5 km. Click **Analyze area**. [Authentication guide](https://developers.google.com/earth-engine/guides/auth)

## How to read the results

The answer card sums estimated residents in the highest tenth of zones by equal-weight overall risk. Story colours run from blue (bottom 40%) through pale yellow (next 30%) and orange (next 20%) to dark red (highest 10%). Tree cover reverses direction so less greenery means greater concern. Grey marks missing readings. Dark numbered markers select the highest-risk zones greedily, at least 1 km apart, after excluding available airfield or restricted flags. The flags are incomplete. Tiles require internet access; the observations, shapes and charts are bundled.

Each zone’s dominant Dynamic World class determines its group in the land-type chart. Bars show the group’s area-weighted surface temperature minus the local average, with at least five measured zones per bar. Monthly lines keep missing months as gaps and shade 2020 for context. Area-wide NO₂ is too coarse to guide individual street interventions.

Compare uses June, July and August 2019–2021 for both presets, with the same Landsat quality mask, Sentinel-2 cloud filtering and Sentinel-5P cloud threshold. Both maps use the same 30–50 °C colour scale. The hottest-tenth gap measures local heat contrast. The share above 40 °C uses residents in zones with valid temperature and population.

The central Delhi Landsat summer average was 40.5 °C versus 33.0 °C across six available MODIS summer months (7.5 °C apart). Bengaluru averaged 33.7 °C versus 32.4 °C across three available months. Missing observations, spatial resolution and overpass timing affect the comparison.

### Data and scoring

- **Heat and air.** Clear-sky Landsat 8/9 thermal observations supply median LST in °C. Landsat senses the surface, with roughly 100 m native thermal resolution. Sentinel-5P supplies the mean tropospheric NO₂ column in mol/m² after masking pixels with cloud fraction ≥0.3. Its footprint spans multiple cells. Ground-level air temperature and breathing-level NO₂ require different measurements.
- **Land and population.** Sentinel-2 optical indices use Cloud Score+ clear-pixel screening. Dynamic World supplies probabilistic land-cover classes. SRTM supplies elevation and slope. WorldPop residential counts use a fixed 2020 baseline and are summed on their native grid. The specified WorldPop collection is deprecated. [WorldPop catalog](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop)
- **Index.** Within each area and period, rank LST anomalies relative to the area-weighted mean, NO₂ and NDVI using tied mid-percentiles. Green deficit is one minus the NDVI rank. Hazard is the weighted mean of the three factors. Exposure is hazard multiplied by population rank, with zero weight for zero estimated residents. The story gives the three factors equal weight. Scores compare locations within the current analysis; their numerical values depend on its boundary and period.
- **Time and coverage.** Time-varying exposure layers share the same years and months. Summer uses June–August in the northern hemisphere and December–February in the southern hemisphere, within the selected calendar years. Clouds and gaps can bias composites. Joint coverage measures the area with valid heat, NO₂, vegetation and population inputs. Cells with missing inputs appear grey on the map.

### Models and interpretation

The random forest predicts LST from land cover, spectral indices and terrain. Site estimates require 150 complete cells and at least three occupied 2 km blocks.

The planner screens cells of at least 1 ha with at least 25% combined bare, shrub or grass cover, zero classified water and less than 50% built cover. A 25% conversion moves one quarter of **existing bare cover** into trees. The model holds other predictors fixed. ΔLST is scenario minus baseline, in °C. The percentile interval comes from 100 paired spatial-block bootstrap refits. These are indicative associations. Field assessment is needed to establish access, planting feasibility and actual cooling.

### Earlier analytical methods

The expert dashboard also doubled each factor in turn and flagged zones that reached the top fifth under all four weighting schemes. Its spatial validation held out whole 2 km blocks and reported pooled R² and RMSE. Tree SHAP attributed fitted temperatures to predictors and averaged absolute contributions across up to 2,000 zones. Correlated features can share credit.

The earlier monthly view used MODIS surface temperature and Sentinel-5P NO₂. Robust STL estimated the annual seasonal cycle with at least 24 observed months, 80% coverage and gaps of at most two months. Short gaps were filled for STL only. Mann–Kendall tested the adjusted series and Sen’s slope used calendar spacing. Serial correlation affects p-values. The chart flagged 2020 as lockdown context.

## Architecture and operating limits

Streamlit routes between the place story and Compare. Both use the same bundled observations or validated live extraction. Place story ranks zones, and About offers the planting model with held-out spatial validation.

Live runs are capped at 2,500 cells and use batches of at most 500. A smaller radius or larger cell size can bring an oversized request within budget. Results are cached for 24 hours, with up to 50 entries per live data cache. Compute actions share a 10-second session cooldown. Earth Engine API sockets have a 90-second inactivity timeout and allow two SDK retries with backoff. Backend load can push extraction beyond the one-minute target. Monitor project quota when serving concurrent users. [Security and quota notes](SECURITY.md)

## Streamlit Community Cloud

1. Make the reviewed code and both Parquet presets available in a GitHub repository that Community Cloud can access. Keep `.env`, real secrets TOML and key files out of Git.
2. In Community Cloud, choose **Create app**, select the repository, select `simplify` (or your release branch containing these files), and enter `app.py` as the entrypoint. In **Advanced settings**, choose **Python 3.12**. Community Cloud installs the exact, hash-locked packages from the root `requirements.txt`. [Deployment guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Dependency resolution](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
3. The offline presets need no secrets. For live computation, give a dedicated service account **Earth Engine Resource Viewer** and **Service Usage Consumer** on the registered project. In **Secrets**, supply the two root-level settings from the template below. Replace the project ID and the entire example JSON object in the dashboard. Paste the complete service-account JSON as a TOML literal string, preserving the JSON’s escaped newlines. [Secrets template](.streamlit/secrets.toml.example) · [Cloud secrets guide](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)

   ```toml
   EE_PROJECT = "YOUR_EARTH_ENGINE_PROJECT_ID"
   EE_SERVICE_ACCOUNT_JSON = '''{
     "type": "service_account",
     "project_id": "YOUR_SERVICE_ACCOUNT_PROJECT_ID",
     "private_key": "YOUR_PRIVATE_KEY_FROM_THE_JSON",
     "client_email": "YOUR_SERVICE_ACCOUNT_EMAIL",
     "token_uri": "YOUR_TOKEN_URI_FROM_THE_JSON"
   }'''
   ```

4. Choose **Deploy**. Confirm a preset map opens, then try a small custom ROI if live access is configured. On an authorization error, verify project registration, API enablement, roles and secret formatting. After grading, rotate the deployment key, restart with the replacement, verify a live request and revoke the old key. [Key handling](SECURITY.md)

## Verification and development

```sh
make check
.venv/bin/pytest -q -m live
```

`make check` runs offline pytest, Ruff and Bandit. The live suite uses the configured Earth Engine project, consumes quota, and includes a timed Delhi extraction. For development commits, install Gitleaks v8.24.3 on PATH or in `.local/bin`, then run `make hooks`. Update pinned dependencies in `requirements.in`, regenerate hashes with `make lock` and install with `make install`.

For release verification, run the locked dependency audit, Bandit and the full-history secret scan. The commands assume Gitleaks is on PATH.

```sh
.venv/bin/pip-audit --cache-dir .local/audit-cache --require-hashes --disable-pip -r requirements.txt
.venv/bin/bandit -r src app.py -q
gitleaks detect --log-opts=--all --redact
```

[Ten viva questions and answers](docs/VIVA.md) · [Milestone and QA record](PROGRESS.md)
