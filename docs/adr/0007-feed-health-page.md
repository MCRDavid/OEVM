# 0007: Feed health page

Date: 2026-10-08. Status: accepted.

Blueprint task 8: a run log and a status page with health figures, kept separate from
the engagement and evidence table. Accept: renders from fixtures with neutral labels.

## Decisions

- **Run logs** (`schema/runlog.py`) now include health figures counted from what was
  received: locations with UK coordinates, EVSEs with a status other than unknown,
  connectors with a tariff that was found, and the median age of the locations' own
  `last_updated` dates (null when an operator gives none). Logs still hold no records or
  keys, and the page refuses any field the model does not list.
- **`pipeline/status.py`** builds `status/index.html` and `data/status.json` from the run
  logs, into a build folder, never the committed `site/`. Each run is merged into the
  previous `status.json` (passed with `--previous`), keeping one entry per day, latest run
  wins, for 30 days. The daily fetch (blueprint task 10) will download the published file
  and pass it in, so the history needs no database.
- **Two pages, one job each**, as the blueprint describes: the feed health page shows
  results, counted automatically; the transparency page keeps sources, rate limits,
  findings and engagement evidence. The transparency page's run section moved to the
  health page, and each links to the other.
- **Neutral labels:** "Fetched", "Fetched, incomplete", "Fetch failed" and "Not fetched
  yet", with dates. The page says the figures describe the data received and do not say
  whether anyone has met their legal duties. A test runs the neutral-wording check over
  the rendered text.
- The blueprint's list also has HTTP status and schema errors with examples. A failed
  run's error text includes the HTTP status, and problems logged (with examples and
  counts) cover schema errors; separate columns can be added if they prove useful.
- The trend is a sentence and a day-by-day table rather than a chart, so the page needs
  no scripts and works with screen readers.
