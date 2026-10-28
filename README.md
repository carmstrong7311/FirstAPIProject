# Chicagoland Events

A website listing every upcoming event in the Chicago area in date order, soonest first. It covers concerts, sports, comedy, theater, street fests, holiday events, food festivals and expos. You can filter by category, by sport (and other sub-categories), by date range, and to free events only. You can also search by name, venue or neighborhood.

A GitHub Action refreshes the data every morning and publishes the site to GitHub Pages.

## Where the events come from

| Source | Covers | Key needed |
|---|---|---|
| League schedule APIs (MLB, NHL, ESPN) | Home games for the Cubs, White Sox, Bears, Bulls, Blackhawks, Sky, Fire, Stars, Northwestern, DePaul and Loyola | No |
| [Ticketmaster Discovery API](https://developer.ticketmaster.com/) | United Center, Soldier Field, Chicago Theatre, Allstate Arena, the Live Nation clubs and most other ticketed shows within 40 miles | `TICKETMASTER_API_KEY` |
| [SeatGeek API](https://seatgeek.com/account/develop) | AXS venues and gaps in Ticketmaster's listings | `SEATGEEK_CLIENT_ID` |
| Venue websites (`pipeline/sources/venues.py`) | Second City, Zanies, Lyric Opera, CSO, Goodman, Steppenwolf, Metro, Thalia Hall, Ravinia, Navy Pier, the Park District and more, read from the event data each page publishes for search engines | No |
| Curated calendar (`pipeline/data/curated_events.json`) | Street fests, art fairs, parades, holiday lights, marathons and other events no ticket site lists | No |

When the same event appears in more than one source, the pipeline merges the listings into one entry. League schedules supply official game times; Ticketmaster supplies the ticket link. Shows with many performances, such as a Broadway run, become a single entry spanning their dates.

Some festival dates for next year aren't announced yet. Those events carry an "Estimated date" tag explaining the estimate. Update `curated_events.json` when organizers announce the real dates.

## Setup

1. **Get API keys.** Both are free.
   - Ticketmaster: create an app at https://developer.ticketmaster.com/ and copy the Consumer Key.
   - SeatGeek: register an app at https://seatgeek.com/account/develop and copy the Client ID.
2. **Add them as repository secrets.** In the repo, open Settings → Secrets and variables → Actions → New repository secret. Add `TICKETMASTER_API_KEY` and `SEATGEEK_CLIENT_ID`.
3. **Turn on GitHub Pages.** Open Settings → Pages and set Source to **GitHub Actions**.
4. **Run the workflow.** Open the Actions tab → *Update events & deploy site* → Run workflow. After that it runs daily on its own.

The site works without the keys, but then it shows only team schedules, venue websites and the curated calendar.

## Running locally

```bash
export TICKETMASTER_API_KEY=...   # optional
export SEATGEEK_CLIENT_ID=...     # optional
python -m pipeline.build          # writes site/data/events.json
python -m unittest discover tests
cd site && python -m http.server 8000   # open http://localhost:8000
```

This needs Python 3.11 or newer and no other packages.

## Adding sources

- **A venue:** add a line to `VENUES` in `pipeline/sources/venues.py`. The build log shows how many events each venue page produced; 0 means the page doesn't publish event data in a form the scraper can read.
- **A festival or one-off event:** add an entry to `pipeline/data/curated_events.json`.
- **A team:** add it to `ESPN_TEAMS` in `pipeline/sources/sports.py`.

If a source fails on a given day, the build reuses that source's last good result from `pipeline/cache/`, so the site never loses a whole category because one site was down.
