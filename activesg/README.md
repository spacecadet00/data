# ActiveSG Crowd Finder

Independent, non-commercial project. Not affiliated with or endorsed by ActiveSG or Sport Singapore.

## Scope and lifetime

- **28 October–26 November 2026 (30 calendar days)**: public occupancy readings.
- **07:07–21:52 SGT**, every 15 minutes while GitHub Actions is available.
- **27 November 2026**: the next scheduled run disables its own workflow. Extension requires renewed permission.
- Gym operation hours determine the global schedule, identically on weekdays and weekends. Any swimming pool occupancy supplied incidentally by the public page may also be kept.
- Only outlets with public occupancy readings are recorded. An absent or closed value is not converted to zero.

## Dashboard

Map-first [ActiveSG crowd explorer](https://spacecadet00.github.io/data/) (only after GitHub Pages is enabled and deployment succeeds).

Features:
- Live reading and freshness check (live data older than 45 minutes is shown as stale)
- Gym/pool filter, user's local browser geolocation, map markers with occupancy
- Weekday/time explorer with hourly historical patterns
- Ranking by available occupancy; no machine-level availability inference
- Per-outlet weekday-by-hour heatmap
- Week-by-week occupancy medians, dispersion and evidence quality

For first-time publishing, go to **repository Settings → Pages → Build and deployment → Source: GitHub Actions**. The scheduled workflow will publish the site; if it does not, inspect the [Actions tab](https://github.com/spacecadet00/data/actions/workflows/activesg.yml).

## Data model

| Path | Purpose |
| --- | --- |
| `data/raw/YYYY-MM-DD.csv` | Compact snapshots: `ts,id,pct,status` |
| `data/outlets.json` | Name/type and available geocoded map coordinates |
| `data/live.json` | Last successfully observed crowd readings |
| `data/patterns.json` | Reproducible week-weighted historical statistics |
| `src/collector.py` | Reads public page / public page responses using Chromium |
| `src/build_stats.py` | Computes independent weekly statistics |
| `site/index.html` | Pure static dashboard hosted on GitHub Pages |

Rows have explicit timestamps in Asia/Singapore; missing is distinct from 0%. An ISO week contributes one median per outlet/weekday/hour, regardless of how many successful 15-minute polls it contains. For 3+ independent weeks, a range across weekly medians of ≤15 percentage points is labeled **consistent**, 15–30 **moderate**, and >30 **variable**. Fewer than three weeks is **insufficient**.

The automated collector has no `push` trigger, so its own data commits cannot initiate duplicate polling runs. The raw CSV remains source of truth, with patterns regenerated once per day to avoid high dashboard data transfer. An outlet is mapped only if validated latitude/longitude are found. Unmapped facilities remain in the ranking list. Geocoding queries are limited to one per polling run and cached.

## Collection safety

The source is ActiveSG's public [gym and pool crowd page](https://activesg.gov.sg/gym-pool-crowd). There is no official machine-readable data contract established for this implementation; the public page is rendered dynamically and may change. The collector exits with an error and **does not fabricate or write observations** if it cannot extract at least four credible records. See Actions logs for fetch/parser errors.

Collection uses GitHub-hosted runners and attempts a limited number of requests. It does not bypass authentication, CAPTCHA or access controls. GitHub's scheduled tasks may be late or skipped, so compare sample counts before interpreting statistics.

After the 30-day cutoff, the workflow's first subsequent run disables future scheduled runs using GitHub Actions API. The dashboard stays published with the last available snapshot, which will become stale.

## Troubleshooting

1. Enable GitHub Pages (Settings → Pages → Source: **GitHub Actions**).
2. Check the [ActiveSG collection workflow](https://github.com/spacecadet00/data/actions/workflows/activesg.yml).
3. A red run at **Collect publicly available occupancy data** means the public page was inaccessible or the extractor could not validate its format. Inspect errors; do not substitute historical estimates as live readings.
4. If data collection works but publication fails, inspect the **Configure GitHub Pages** step; repository permissions and Pages enablement may need attention.
5. If no markers appear, geocoding may not yet have resolved locations; the outlet list still works and never invents coordinates.
6. To continue after the end date, explicitly change the cutoff in config and re-enable the workflow after the user's approval. Do not do this silently.
