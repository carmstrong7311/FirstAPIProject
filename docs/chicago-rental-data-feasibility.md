# Chicago rental map: is there enough data? (feasibility report)

**Date:** 2026-11-08
**Scope:** desk research plus attempted sampling, for a **personal / friends** map of every Chicago rental (apartments, condos, single-family homes). Each listing would show a link, price, beds/baths, photos, amenities, year built, building type and location. Nothing has been built.

> **Limits of this research.** This cloud session's network allowlist blocked every live fetch: Apartments.com, Zillow, Zumper, RentHop, Domu, Craigslist, RentCast, both Chicago and Cook County open-data portals, and the Census API. So **I pulled no live sample rows**. Listing counts come from search-engine snapshots of each site's Chicago page (dates unknown, roughly ±10%). Field lists come from vendor documentation, scraper output schemas and, for Cook County, the Assessor's own published source code on GitHub. To verify live, allow these hosts in the environment's network settings and re-run the sample URLs in the appendix.

---

## 1. Bottom line

**Yes, the data reaches critical mass, but it is not available through clean channels.**

| Question | Answer |
|---|---|
| How many Chicago units are on the market at any moment? | **~15,000–30,000** (estimate; see section 2). Lowest in winter, highest from April to August. |
| Does the listing data exist online? | **Yes.** Apartments.com alone shows ~18k Chicago rentals. The Zillow network (Zillow/Trulia/HotPads) shows ~10–11k city listings and ~22k with nearby suburbs. Together, these two networks probably cover **most** of the market. |
| Can an individual get it through an official API? | **No.** No major portal offers an outbound listings API to individuals. The legitimate routes are partial: RentCast's API, which is MLS-derived and has no photos or links, and an MRED MLS feed, which requires a sponsoring agent. |
| Can you get the extra fields (year built, building type, coordinates)? | **Yes, for free.** Cook County Assessor and City of Chicago open data provide year built, unit counts, building class and parcel lat/long. You can join them to any listing by address. |
| Main risk | **Terms of service and copyright** if you scrape. Apartments.com (CoStar) and Craigslist are the most litigious. For personal use, the practical risks are being blocked and getting cease-and-desist letters, not prosecution. **Link to photos rather than copying them.** |

**Recommended source mix for a personal app (coverage vs. effort):**
1. **Zillow network** (via a third-party scraper or dataset): large buildings plus many condos and houses. It also covers what Realtor.com, Redfin and Rent.com show for big buildings.
2. **Apartments.com**: the largest single inventory, and CoStar keeps it off Zillow. It is also the hardest to scrape (Akamai bot protection).
3. **Domu**: Chicago-specific listings from small landlords and 2–4 flats. Worth simply emailing them to ask for a feed.
4. **Craigslist**: owner-posted units the portals miss. Highest legal risk, many duplicates and scams.
5. **Free enrichment layer**: Cook County Assessor + City of Chicago open data.
6. Optional legitimate backbone: **RentCast API** (free for 50 requests/month).

Facebook Marketplace and groups are **not recommended**. Scraping them needs a login, which is outside the Meta v. Bright Data ruling, and they carry the highest scam rate (~50% of FTC rental-scam complaints).

---

## 2. Market size: what "complete" means

| Input | Value | Source |
|---|---|---|
| Renter-occupied units, Chicago | **624,368** (54.5% of households) | ACS 2019–23 via [CMAP Chicago Housing Profile](https://cmap.illinois.gov/wp-content/uploads/Chicago-Housing-Profile.pdf) |
| Rental vacancy | ~4.6–5.4% | [Northmarq Q2 2026](https://www.northmarq.com/sites/default/files/docs/NMMarketInsights-Q22026-Chicago.pdf), [Cushman & Wakefield](https://www.cushmanwakefield.com/en/united-states/insights/us-marketbeats/chicago-marketbeats/multifamily), [RentCafe](https://www.rentcafe.com/blog/rental-market/market-snapshots/us-hottest-rental-markets-start-of-2026/) |
| Renter mobility | ~16–22% move per year | [Harvard JCHS](https://www.jchs.harvard.edu/blog/household-mobility-fell-record-low-2024), [Zillow](https://www.zillow.com/research/renters-housing-trends-report-2025-35647) |
| Zillow "available rentals", Chicago, 2026-06-18 | 11,022 | [Zillow Rental Manager market trends](https://d3blkd4k0wk9oj.cloudfront.net/rental-manager/market-trends/chicago-il/) |

**Estimates:**
- **Vacant-unit stock** = 624k × v/(1−v). At 4.5–5.5% vacancy that is ≈ 29k–36k, which includes unmarketed units.
- **Flow method** = annual moves × days a unit is marketed ÷ 365. That gives ≈ 9k–26k.
- **Working estimate: 15k–30k units actively marketed at once**, and ~110k–155k leases signed per year.

**What this means:** any single site covers roughly 40–70% of the market. **Two or three combined sources, de-duplicated, should get close to complete coverage.** The remaining gap is mostly small landlords who post only on Craigslist, Facebook or a window sign.

---

## 3. Listing sources compared

Counts are snapshots of what each site's Chicago page displayed. A site may count listings, buildings or units, and some include suburbs.

| Source | Approx. Chicago count | Fields available | Official access for an individual | Scraping difficulty | Legal / ToS risk |
|---|---|---|---|---|---|
| **Apartments.com** (CoStar; ForRent, ApartmentFinder etc. are copies) | **~17.6k–18.1k "rentals"** | Address, **coordinates**, unit-level floor-plan pricing, beds/baths/sq ft, **full amenity list**, pet/parking/fees, photos. Year built is in its feed spec; I did not confirm it on public pages. | None. Feeds are inbound-only, from property managers. | **High.** Akamai Bot Manager; residential proxies required. | **High.** CoStar won $10k per listing/photo against Apartment Hunters and is suing Zillow over ~53k photos. |
| **Zillow / Trulia / HotPads** | Trulia ~9.9k–11k (city); HotPads ~22k–23k (incl. suburbs); Zillow 11,022 (June 2026) | ~44 fields incl. **yearBuilt, homeType** (apartment/condo/SFH/townhouse), **lat/long**, photos, price, beds/baths, building-level unit pricing | None. Public API retired in 2021; the Bridge API is invite-only and gated by each MLS. | Medium. Cheap scrapers exist. | Medium-high. ToS bans scraping; Zillow has sent cease-and-desist letters. |
| **Realtor.com, Redfin, Rent.com, ApartmentGuide** | Realtor.com ~1.7k (via HomeFinder); others not found | MLS-style fields | None | Medium | Medium. **Mostly duplicates of Zillow:** Zillow supplies their 25+ unit buildings (2024–25 deals, FTC settlement through 2030). Only their MLS condos and houses add anything. |
| **Zumper / PadMapper** | ~14k (one snapshot) | Price, beds, pets, photos, neighborhood, lat/long (via scrapers) | None ("does not offer API integration") | Medium | Medium |
| **Apartment List** | ~2.7k–2.9k (buildings) | Building plus per-unit availability | None | Medium | Medium |
| **RentHop** | Not found | — | None (inbound feeds only) | — | Medium |
| **Domu** (Chicago-only) | ~4k–6k (dated company projection) | Price, beds/baths, photos, amenities, pets, map. Year built rare. | None, but small and local, so **ask them for a feed**. | Unknown (fetch blocked) | Medium |
| **Craigslist /apa** | Several thousand (unverified) | Price, beds, sometimes sq ft, free-text attributes, photos. **Lat/long only if a map pin was placed.** No year built. | None. RSS is unreliable after the move to JavaScript rendering. | Medium | **High.** ToS bans scraping; won ~$1M plus an injunction vs. 3Taps, $60.5M vs. RadPad, $31M vs. Instamotor. |
| **Facebook Marketplace / groups** | Unknown, likely large | Approximate area only, no year built | None (partner feeds ended in 2021) | **Very high.** Login wall; Meta bans accounts. | High. Logged-in scraping falls outside the Meta v. Bright Data ruling. Highest scam rate. |
| **MRED MLS** (Chicago's MLS) | ~43k active listings of all types; Chicago rentals est. low thousands (mostly condos, 2–4 flats, SFH) | **Best quality:** RESO fields incl. YearBuilt, PropertySubType, lat/long, photos, features | Only via a **sponsoring broker** (IDX/VOW through SimplyRETS, Spark, Bridge etc.), ~$5–$100/month | N/A (licensed) | Low if licensed. IDX display and redistribution rules apply. |
| **RentCast API** | Derived from MLS and other sources | Address, lat/long, propertyType, beds/baths, sq ft, yearBuilt, price, days on market. **Likely no photos or listing URL** (unverified). | **Self-serve:** free for 50 requests/month; paid from ~$74/month | N/A | Low |
| ILHousingSearch, CHA, university boards, Furnished Finder | Hundreds each | Varies | Web only; university boards often login-gated | Varies | Medium |

### Duplication between sites
Property-management software (AppFolio, Entrata, Yardi, RentEngine…) pushes the same unit to CoStar, Zillow, Zumper, RentHop and Apartment List at once. Expect **≥50% overlap** for professionally managed buildings (estimate). Duplicates are matched on **normalized address + unit number + lat/long proximity**. Within each network, scrape only the main site: Apartments.com, Zillow and Zumper.

### Third-party scrapers and datasets (if you go that route)
| Vendor | Target | Rough price |
|---|---|---|
| Apify actors | Zillow rentals | ~$1–$6 per 1k results. Many cap at ~1k per search, so split the city by neighborhood. |
| Apify actors | Apartments.com | ~$2–$10 per 1k plus residential-proxy costs. Several actors report Akamai blocks. |
| Apify actors | Craigslist, Facebook Marketplace, Zumper, Trulia, Apartment List, Realtor.com | ~$0.50–$4 per 1k |
| Bright Data | Zillow dataset | ~$250 per 100k records |

A full Chicago refresh from the Zillow network plus Apartments.com would cost roughly **$20–$150 per run**. These are vendor-listed prices and change often. Paying a vendor does not transfer the ToS risk away from you.

---

## 4. Enrichment layer (free public data)

This covers the fields listings often lack: **year built, building type, unit count, exact coordinates**, plus useful map layers.

**Cook County Assessor** (datacatalog.cookcountyil.gov; IDs verified from the Assessor's [published source code](https://github.com/ccao-data/data-architecture)):

| Dataset | ID | Key fields |
|---|---|---|
| Single & Multi-Family Improvement Characteristics | `x54s-btds` | `char_yrblt` (year built), `char_apts`, `char_beds`, `char_bldg_sf`, `char_type_resd`, `class`. **Only buildings with fewer than 7 units.** |
| Residential Condominium Unit Characteristics | `3r7i-mrz4` | `char_yrblt`, `char_unit_sf`, `char_bedrooms`, `char_building_pins` (units in building) |
| Parcel Addresses | `3723-97qp` | `prop_address_full`, so an address can be matched to a PIN (parcel ID) |
| Parcel Universe (current year) | `pabr-t5kh` | `lat`, `lon`, community area, ward, census tract, flood zone, schools |
| Commercial Valuation Data | (on data.gov) | 7+ unit apartment buildings: units, rents |

**City of Chicago** (data.cityofchicago.org):

| Layer | ID |
|---|---|
| Building Footprints (year built, stories, units; fills the 7+ unit gap) | `hz9b-7nh8` (possibly `syp8-uezg`; verify) |
| Building Violations | `22u3-xenr` |
| Building Permits | `ydr8-5enu` |
| Affordable Rental Housing Developments | `s6ha-ppgi` |
| CTA 'L' Stops / Bus Stops | `8pix-ypme` / `qs84-j7wh` |
| Crimes 2001–present | `ijzp-q8t2` |
| Zoning Districts | `dj47-wfun` |
| Cook County Address Points (geocoding) | `78yw-iddh` (county portal) |

**No rental registry exists.** The proposed Protecting Renters Ordinance would create one, but it was still being debated as of September 2026 ([Axios](https://www.axios.com/local/chicago/2026/09/23/chicago-rental-rules-pro-fair-ordinance-landlords-tenants)). If it passes, a registry would make a useful master list of rental buildings.

**Join path:** listing address → Parcel Addresses → PIN → characteristics (year built, type, units) + Parcel Universe lat/lon.

**Geocoding and maps (free options):**
- [Census Geocoder](https://geocoding.geo.census.gov/): free, batches of up to 10k addresses.
- Local matching against Cook County Address Points: parcel-level precision.
- MapLibre GL JS + [OpenFreeMap](https://openfreemap.org) or self-hosted [Protomaps](https://protomaps.com) tiles: free, no API key.
- Avoid bulk use of OSM's own tile servers and public Nominatim, which their policies forbid.

**Licensing:** City data is "as is" with a disclaimer required. Cook County terms allow personal use; ask before redistributing. Census data is public domain.

---

## 5. Field coverage: can every desired attribute be filled?

| Desired field | Primary source | Backup / enrichment |
|---|---|---|
| Listing link | Each portal (always) | — |
| Photos | Portal (link to them; don't copy) | — |
| Price, beds/baths | All listing sources | — |
| Amenities | Apartments.com (best), Zillow, Domu | Craigslist free text |
| Year built | Zillow, MLS, RentCast | **Cook County Assessor / City footprints (free, near-universal)** |
| Building type | Zillow homeType, MLS PropertySubType | Assessor class + unit count |
| Location (lat/long) | Apartments.com, Zillow, MLS | Assessor parcel lat/lon, Census Geocoder |

**Every attribute you asked for can be filled for most listings** by combining a portal source with the public enrichment layer.

---

## 6. Risks and open questions
- **Legal:** For personal, logged-out scraping, the federal anti-hacking law (CFAA) is unlikely to apply (*hiQ v. LinkedIn*, *Meta v. Bright Data*). ToS (contract) and **copyright** claims remain. Storing facts and linking out is far safer than storing photos or descriptions. If the app ever goes public or commercial, this changes significantly.
- **Chicago MLS turmoil:** Zillow is suing MRED and Compass (filed May 2026). MRED briefly cut Zillow's Chicago feed before a court restored it. Zillow's coverage of MLS condos and houses could change.
- **Scams:** Craigslist and Facebook carry heavy scam volume. An app should flag listings with no address, prices well below market, or text reused across addresses.
- **Unverified (blocked fetches):** live counts for Zillow, Redfin, RentHop, Domu and Craigslist; RentCast's exact fields; the City footprint dataset ID and columns; the 2025 ACS 1-year "for rent" count (released 2026-10-29).

## 7. Suggested next steps (before building)
1. Allow the hosts in the appendix in this environment's network settings, then run the sample queries to confirm counts and fields.
2. Sign up for RentCast's free tier and pull one Chicago page to see actual fields and coverage.
3. Email Domu to ask whether they offer a data feed or partnership.
4. Optionally ask a Chicago agent you know about IDX access to MRED.
5. Run one paid Zillow-rentals scraper job for one neighborhood (~$1) to measure real field completeness and duplication.

---

## Appendix: hosts to allow, and sample queries
Hosts: `datacatalog.cookcountyil.gov`, `data.cityofchicago.org`, `api.census.gov`, `geocoding.geo.census.gov`, `api.rentcast.io`, `www.domu.com`, `chicago.craigslist.org`, `www.apartments.com`, `www.zillow.com`, `www.zumper.com`.

```
https://datacatalog.cookcountyil.gov/resource/x54s-btds.json?$limit=2
https://datacatalog.cookcountyil.gov/resource/pabr-t5kh.json?$limit=2
https://datacatalog.cookcountyil.gov/resource/3723-97qp.json?$limit=2
https://data.cityofchicago.org/resource/hz9b-7nh8.json?$limit=2
https://data.cityofchicago.org/resource/s6ha-ppgi.json?$limit=2
https://api.census.gov/data/2024/acs/acs1?get=NAME,B25003_003E,B25004_002E&for=place:14000&in=state:17
```

### Key sources
- Apartments.com Chicago page: https://www.apartments.com/chicago-il/
- HotPads / Trulia: https://hotpads.com/chicago-il/apartments-for-rent, https://www.trulia.com/for_rent/chicago,IL/
- Zillow API retirement and Bridge: https://www.zillowgroup.com/developers/api/mls-broker-data/mls-listings
- Zillow–Redfin multifamily deal: https://investors.zillowgroup.com/news-and-events/news/news-details/2025/Zillow-and-Redfin-partner-to-make-apartment-hunting-easier-and-give-listings-more-exposure/default.aspx
- CoStar v. Zillow: https://www.geekwire.com/2025/costar-sues-zillow-over-photos-claims-systematic-infringement/
- CoStar v. Apartment Hunters: https://www.bisnow.com/news/national/commercial-real-estate/judge-rules-in-costars-favor-fines-apartment-hunters-for-publishing-stolen-content-72788
- Craigslist v. RadPad: https://newmedialaw.proskauer.com/2017/04/17/craigslist-garners-60-million-judgment-against-radpad-in-scraping-dispute/
- Craigslist terms: https://www.craigslist.org/about/terms.of.use/en
- Meta v. Bright Data: https://www.fbm.com/alex-reese/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/
- Zillow v. MRED: https://housingwire.com/articles/judge-restores-zillow-mred-feeds/
- Zumper feeds policy: https://help.zumper.com/hc/en-us/sections/43549953493147-Feeds
- RentCast API: https://developers.rentcast.io
- SimplyRETS (IDX): https://simplyrets.com/
- Apify Zillow rentals: https://apify.com/themineworks/zillow-rental-listings
- Bright Data Zillow dataset: https://brightdata.com/products/datasets/zillow
- FTC rental-scam share by platform: https://bankerandtradesman.com/?p=244339
- CCAO data architecture: https://github.com/ccao-data/data-architecture
- Geocoding/tiles: https://operations.osmfoundation.org/policies/nominatim/, https://openfreemap.org, https://protomaps.com/faq
