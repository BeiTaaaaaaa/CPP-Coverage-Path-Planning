# CPP field-boundary datasets — consolidated report

**Prepared for:** coverage-path-planning (CPP) research benchmark
**Workspace:** `C:\Users\666\Desktop\CPP` · **Data root:** `C:\Users\666\Desktop\CPP\data`
**Download / inspection date:** 2026-02-11
**Total downloaded & retained:** **203.3 MB** across **808 files** (well under the "few hundred MB" budget)

Every dataset folder has a sibling `SOURCE.md` with full provenance. This file is the overview,
the cross-dataset comparison, and the honest list of what could *not* be obtained.

---

## 1. Headline result

**The highest-value target — Fields2Benchmark's 350 real-world fields — was found and downloaded in
full, and independently verified.** ✅

It is **not** on GitHub (confirming the prior search: GitHub repository search for
`Fields2Benchmark` returns `total_count: 0`). The data is on **Zenodo**, DOI
**`10.5281/zenodo.14524734`** (version record `10.5281/zenodo.14524735`), and that exact DOI is
confirmed by the paper's own Data-availability statement in the open-access PDF.

A useful bonus: the **parent** dataset of Fields2Benchmark is **EuroCrops**, so the benchmark can be
scaled beyond 350 fields from the same lineage — and one EuroCrops national layer was obtained here.

---

## 2. Status summary

| # | Dataset | Status | Geometry | CRS | Polygons | Licence |
|---|---|---|---|---|---|---|
| 1 | **Fields2Benchmark** (Mier et al. 2025) | ✅ **Downloaded & verified** | WKT text, 1 file/field | EPSG:4326 | **350** | CC BY 4.0 (deposit); mixed upstream ⚠️ |
| 2 | **Nilsson & Zhou (2020)** 54 fields | ❌ **Not obtainable** | — | — | 0 | paywalled; no deposit |
| 3a | **PDOK / BRP** Dutch parcels | ✅ **Subset downloaded & verified** | GeoJSON | EPSG:28992 (metres) | **6,093** (1,535 cropland) | **CC0 1.0** |
| 3b | **EuroCrops PT 2021** | ✅ **Downloaded & verified** | ESRI Shapefile | EPSG:4326 | **100,000** | CC BY-SA 4.0 ⚠️ |
| 3c | **Pour Arab et al. 2024** (30 FR fields) | ✅ **Polygons extracted & verified** | XML vertices | *local cm, none* | **31** (30 usable) | CC BY 4.0 |
| 3d | **AI4Boundaries** (JRC) | 🔗 **Link only — not downloaded** | raster + vector labels | EPSG:3035 | 2.5 M parcels | see §7 |
| 3e | **EuroCrops** other countries | 🔗 **Link + sizes only** | Shapefile | varies | — | CC BY-SA 4.0 |
| 3f | **Fields2Benchmark `imgs.zip`** | 🔗 **Link only (138.6 MB)** | raster PNG | — | — | CC BY 4.0 |

Legend: ✅ downloaded and inspected by me · 🔗 found a link but did not fetch it · ❌ could not obtain

---

## 3. `data/` layout

```
data/
├── DATASETS.md                      ← this report
├── fields2benchmark/                ← ★ TARGET 1 — 350 fields
│   ├── SOURCE.md
│   ├── wkt.zip                      (211,710 B, MD5-verified)
│   ├── wkt_extracted/wkt/           350 × *.wkt  ← ORIGINAL, as shipped
│   ├── wkt_rescaled_1ha/            350 × *.wkt  ← DERIVED: every field scaled to 1.00 ha
│   ├── geometry_summary.json        per-field bbox / area / holes / vertices
│   ├── README.md, LICENSE           originals from Zenodo
│   ├── zenodo_record_curl.json      Zenodo API metadata
│   ├── Fields2Benchmark_OA_edepot_698168.pdf
│   └── f2b_paper_text.txt           extracted paper text (proves the data URL)
├── nilsson/
│   └── SOURCE.md                    ← negative result, fully documented
└── other/
    ├── pdok_brp/                                    ← Dutch parcels, CC0
    │   ├── SOURCE.md
    │   ├── pdok_brp_flevoland_28992.geojson          6,093 features
    │   └── pdok_brp_flevoland_cropland_ge1ha.geojson 1,535 features (DERIVED)
    ├── eurocrops_PT_2021/                           ← Portuguese parcels, CC BY-SA
    │   ├── SOURCE.md
    │   ├── PT_2021.zip (MD5-verified) + extracted/PT_2021/*.{shp,shx,dbf,prj,cpg}
    │   └── geometry_summary.json
    ├── pour_arab_french_fields/                     ← 30 French fields, CC BY
    │   ├── SOURCE.md
    │   ├── polygons_2D/ (31), dividing_lines/ (22), access_segments/ (31)
    │   └── geometry_summary.json
    ├── pour_arab_french_fields_zipindex.json        448-entry index of the 854 MB ZIP
    └── pour_arab_french_fields_DESCRIPTION.txt
```

---

## 4. ★ Target 1 — Fields2Benchmark, 350 real-world fields

**Fully downloaded and verified. This is the benchmark's backbone.**

| | |
|---|---|
| Paper | "Fields2Benchmark: An open-source benchmark for coverage path planning methods in agriculture" |
| Authors | Gonzalo Mier, Ana María Casado Faulí, João Valente, Sytze de Bruin |
| Journal | *Smart Agricultural Technology* 12, art. 101156, Dec 2025 |
| Paper DOI | `10.1016/j.atech.2025.101156` |
| OA PDF | https://edepot.wur.nl/698168 |
| **Dataset DOI** | **`10.5281/zenodo.14524734`** (concept) / `10.5281/zenodo.14524735` (version) |
| Landing page | https://research.wur.nl/en/datasets/fields2benchmark-dataset/ |
| Downloaded from | `https://zenodo.org/api/records/14524735/files/{wkt.zip,README.md,LICENSE}/content` |
| Licence | **CC BY 4.0** on the deposit — but see the ⚠️ caveat below |

### Geometry, precisely

- **Format: WKT, plain text, one `POLYGON ((lon lat, …))` per file.** *Not* GeoJSON, *not* Shapefile,
  *not* GeoPackage, *not* `.npy`. No `.prj`, no sidecar metadata, **and no declared CRS anywhere**.
- **CRS: EPSG:4326 (WGS 84), lon/lat, decimal degrees** — *inferred from the coordinate ranges*
  (lon 3.80–27.32, lat 51.36–59.54, which land on NL/EE/LT as the README promises). Consistent, but
  it is an inference, not a document statement.
- **350 polygons** obtained, exactly as claimed. ✅
- **49 of 350 carry genuine interior rings (holes)** — proven by point-in-polygon testing each inner
  ring against its outer ring. These are real in-field obstacles. **This is the single most valuable
  property of this dataset for CPP**: it is the only collection here with obstacles, and the
  Fields2Benchmark paper's own selling point over Nilsson/Pour is precisely "including obstacles and
  non-convex shapes".
- All 350 outer rings explicitly closed; all wound **clockwise**.
- Country split: **`nl_` 140, `lt_` 113, `ee_` 97**.
- Vertices: 18,834 total; per outer ring min 5, **median 33**, max 360.

### Areas and bounding boxes (spot-check numbers)

**Net area, geodesic (WGS 84 sphere), holes subtracted — hectares, n = 350:**

| min | p05 | p25 | **median** | p75 | p95 | max | sum | mean |
|---|---|---|---|---|---|---|---|---|
| 0.4989 | 0.6338 | 1.2691 | **2.1452** | 3.9205 | 8.782 | 25.802 | 1,147.78 ha | 3.2794 ha |

**Overall extent:** lon `3.79653 … 27.32176`, lat `51.35811 … 59.53843`

| cc | n | lon | lat | ha min / median / max |
|---|---|---|---|---|
| nl | 140 | 3.7965 … 7.1961 | 51.3581 … 53.4423 | 0.564 / 2.446 / 18.20 |
| ee | 97 | 22.2761 … 27.3218 | 57.7607 … 59.5384 | 0.501 / 1.929 / 20.41 |
| lt | 113 | 21.6053 … 26.2805 | 54.2860 … 56.2405 | 0.499 / 2.123 / 25.80 |

**20 fields to sanity-check against directly** (full table reproducible from `geometry_summary.json`):

| file | holes | pts | area (ha) | min_lon | max_lon | min_lat |
|---|---|---|---|---|---|---|
| `ee_field_10.wkt` | 0 | 128 | 0.642 | 26.49900 | 26.50096 | 58.16785 |
| `ee_field_141.wkt` | **1** | 71 | 1.028 | 24.53486 | 24.53675 | 58.86942 |
| `ee_field_173.wkt` | 0 | 54 | 3.682 | 26.79798 | 26.80125 | 58.25047 |
| `ee_field_210.wkt` | 0 | 60 | 5.594 | 24.93079 | 24.93575 | 58.79634 |
| `ee_field_43.wkt` | 0 | 109 | 3.623 | 23.11054 | 23.11546 | 58.49580 |
| `ee_field_77.wkt` | 0 | 16 | 0.750 | 26.16918 | 26.17134 | 58.07730 |
| `lt_field_115.wkt` | **1** | 54 | 3.027 | 24.97839 | 24.98132 | 55.81913 |
| `lt_field_16.wkt` | 0 | 7 | 0.499 | 22.58645 | 22.58768 | 56.09707 |
| `lt_field_182.wkt` | 0 | 17 | 2.238 | 21.60820 | 21.61100 | 56.23723 |
| `lt_field_214.wkt` | 0 | 24 | 0.711 | 25.31758 | 25.31847 | 55.49329 |
| `lt_field_255.wkt` | **1** | 100 | 3.007 | 26.15822 | 26.16214 | 55.78691 |
| `lt_field_35.wkt` | 0 | 20 | 1.598 | 24.41112 | 24.41398 | 55.08612 |
| `lt_field_82.wkt` | 0 | 20 | 1.977 | 24.51809 | 24.52066 | 55.60073 |
| `nl_field_111.wkt` | 0 | 11 | 2.489 | 5.02025 | 5.02384 | 52.22410 |
| `nl_field_143.wkt` | **1** | 33 | 8.480 | 6.19050 | 6.19400 | 53.29038 |
| `nl_field_175965.wkt` | 0 | 19 | 0.960 | 6.19549 | 6.19740 | 52.11598 |
| `nl_field_278678.wkt` | 0 | 75 | 0.829 | 6.52636 | 6.52800 | 52.74178 |
| `nl_field_42.wkt` | 0 | 40 | 6.688 | 6.24648 | 6.25207 | 52.75759 |
| `nl_field_576946.wkt` | 0 | 79 | 2.576 | 6.13700 | 6.14177 | 52.42108 |
| `nl_field_70.wkt` | 0 | 18 | 2.495 | 5.29037 | 5.29507 | 51.76944 |

All coordinate ranges fall inside the correct countries. ✅ (Estonia spans to 59.54 °N — the
northernmost point in the collection. Relevant if you pick a single equal-area projection.)

### ⚠️ Licence caveat — read before publishing

The Zenodo **deposit** is labelled **CC BY 4.0**, and the paper is CC BY. **But** the dataset's own
README documents the *upstream source* licences, and they are not uniform:

| Subset | Upstream source | Upstream licence |
|---|---|---|
| `nl_` (140) | PDOK / Nationaal Georegister | **CC0 1.0** + Public Domain Mark 1.0 |
| `ee_` (97) | INSPIRE Geoportal (Estonia) | **CC BY-SA 3.0 EE** |
| `lt_` (113) | geoportal.lt (NMA-paseliai) | **Non-commercial use only**; copyright |

The Lithuanian third is **non-commercial-only** in its original terms. If the benchmark is
non-commercial this is fine; if it may be used commercially, the `lt_` subset is the problem, and the
clean 237-field alternative is the `nl_` + `ee_` fields. **Do not describe the whole 350 as
uniformly CC BY 4.0 in a paper** — state the mixed provenance.

### Conversion notes (assessed, not performed — no heavy geospatial stack installed)

1. `.wkt` files are not a directory-readable vector source. Use `shapely.wkt.loads` per file and
   build a `GeoDataFrame(..., crs="EPSG:4326")`.
2. **Reprojection to metres is mandatory before any CPP computation.** Recommend **EPSG:3035
   (ETRS89-LAEA Europe)** — equal-area, metric, covers NL→Estonia in one CRS. Alternatives:
   EPSG:28992 (NL), EPSG:3301 (EE), EPSG:3346 (LT). Avoid global Mercator: fields are small
   (median 2.15 ha) and reach 59.5 °N, so shape distortion would bias swath counts.
3. **Holes must survive any conversion.** Dropping them silently converts the obstacle-avoidance
   benchmark into an easier one.
4. `wkt_rescaled_1ha/` is a **derived** artefact I produced: every field scaled about its centroid to
   exactly **1.000000 ha** (verified, ±2×10⁻⁵ ha), mirroring the "re-scaled to 1 ha" protocol used on
   Nilsson's fields in the Fields2Cover paper. Cite the original deposit and label this as derived.

### Not downloaded

`imgs.zip` — **145,310,040 B (138.6 MB)** — per-field satellite PNGs (Matlab Mapping Toolbox), same
basenames as the WKT files. Openly available, no login:
`https://zenodo.org/api/records/14524735/files/imgs.zip/content`. Omitted only for volume; download
if you want raster backdrops for figures.

---

## 5. Target 2 — Nilsson & Zhou (2020), 54 standard fields ❌ **NOT OBTAINABLE**

**No data was obtained. Nothing was fabricated or substituted.** Full write-up in
`data/nilsson/SOURCE.md`.

Four independent negative checks:

1. **No dataset DOI.** Crossref metadata for `10.1016/j.biosystemseng.2020.08.007` exposes no
   supplementary-data link and no repository relation.
2. **Paywalled.** Europe PMC: `isOpenAccess: N`, `inEPMC: N`, `pmcid: None`, full-text link marked
   `Subscription required`. No green OA copy. ScienceDirect returns HTTP 403 to automated access.
   The supplementary material — where the 54 fields most likely live — is behind the subscription.
3. **No public deposit.** Searched Zenodo and the Aarhus University Pure portal (authors'
   institution). The Pure record's only "Access to Document" entry is the paywalled DOI, and its
   "Other files and links" holds only a Scopus citation link.
4. **Mendeley is a decoy.** A Mendeley catalogue entry exists, but it is a reference-manager record
   for the *paper*, not a data deposit — and it returns HTTP 403 behind Cloudflare regardless.

**Path forward if it is genuinely needed:** institutional subscription access to the Elsevier
supplementary material, or an email request to the corresponding author
(**René S. Nilsson, Aarhus University**). I did not attempt to circumvent the paywall.

### Important correction to the premise

Even if obtained, these are **not real-world fields**. The Fields2Benchmark paper itself says
(`f2b_paper_text.txt` lines 83–84):

> "Nilsson's dataset [11] offers **54 manually-created geometries without in-field obstacles**."

i.e. **synthetic, hand-drawn, convex polygons with no holes**. The Fields2Cover paper confirms it
used "**38 convex fields of the Nilsson's benchmark**", re-scaled to 1 ha. So Nilsson's 54 fields and
Fields2Benchmark's 350 are **not interchangeable**: one is a clean convex baseline for isolating
swath/route optimisation, the other is real, non-convex, sometimes perforated geometry. If the brief
requires *real* field boundaries, this target is arguably not worth the subscription —
**target 1 already satisfies it.**

---

## 6. Target 3 — other openly licensed polygon datasets

### 6a. PDOK / BRP "Gewaspercelen" — Dutch agricultural parcels ✅

| | |
|---|---|
| Landing | https://service.pdok.nl/rvo/gewaspercelen/atom/index.xml |
| WFS | https://service.pdok.nl/rvo/gewaspercelen/wfs/v1_0 · type `brpgewaspercelen:BrpGewas` |
| **Licence** | **CC0 1.0 Universal (public domain)** — the cleanest licence in this collection |
| Vintage | 2025, `status = Definitief` |
| Downloaded | WFS GetFeature, `bbox=168000,497000,180000,507000,EPSG:28992`, paged `count=1000` ×7 |

- **Format GeoJSON · CRS EPSG:28992 (Amersfoort / RD New) — already metric, in metres.
  No reprojection needed: the most immediately usable dataset here.**
- **6,093 features** downloaded (7.37 MB); **1,535** in the derived cropland subset.
- 169 of 6,093 carry interior rings.
- Attributes: `category`, `gewas` (crop, Dutch), `gewascode`, `jaar`, `status`.
- Extent x `167488 … 180789`, y `496305 … 507812`. Polygon: `Polygon` for all features.

**⚠️ Critical caveat:** the raw BRP register includes **non-field landscape elements as parcels**.
The single most common `gewas` is **`Sloot` (ditch) — 1,957 of 6,093** — and median area is only
**0.10 ha**. Feeding the raw file to a CPP planner would benchmark it mostly on ditches. Hence the
derived subset `pdok_brp_flevoland_cropland_ge1ha.geojson`: ≥1 ha, landscape elements removed.

| | n | min | median | max | sum |
|---|---|---|---|---|---|
| raw | 6,093 | 0.0001 | **0.1046** | 33.160 | 10,115.2 ha |
| cropland ≥1 ha (derived) | 1,535 | 1.001 | **5.378** | 33.160 | 9,506.3 ha |

Top crops retained: potatoes (203), winter wheat (184), onions (129), temporary grassland (117),
sugar beet (114), tulips (78), pears (76), winter carrot (69).

Not downloaded: the full national GeoPackage
(`https://service.pdok.nl/rvo/gewaspercelen/atom/downloads/gewaspercelen_concept_2026.gpkg`) — the
whole Netherlands, on the order of 10⁶ parcels. Change the `bbox` to get any other region.

### 6b. EuroCrops — Portugal 2021 ✅

| | |
|---|---|
| **DOI** | **`10.5281/zenodo.14094196`** |
| Paper | *Scientific Data* 10:612 (2023), `10.1038/s41597-023-02517-0` |
| **Licence** | **CC BY-SA 4.0** ⚠️ *share-alike* — the only copyleft-ish licence here |
| Downloaded | `https://zenodo.org/api/records/14094196/files/PT_2021.zip/content` (34,624,844 B) |
| **MD5** | expected `54728fb13a6abf5f6caaf0b1b3578244` = computed ✅ **exact match** |

- **Format ESRI Shapefile (`.shp/.shx/.dbf/.prj/.cpg`), original filenames kept, not converted.**
- **CRS EPSG:4326 (WGS 84)** — read directly from the `.prj`, not assumed. Shape type `5` (Polygon),
  attributes UTF-8 per `.cpg`.
- **100,000 polygons**, 0 malformed, 2,500,868 vertices total, 3,062 multi-part records, 4,802
  interior rings. Extent lon `−9.454 … −6.467`, lat `37.320 … 42.138` = **mainland Portugal** ✅.
- **18 attributes**, including EuroCrops harmonised crop fields `EC_hcat_n` / `EC_hcat_c`.
  Top crops in sample: `not_known_and_other`, `olive_plantations`, `grain_maize_corn_popcorn`,
  `vineyards_wine_vine_rebland_grapes`, `pasture_meadow_grassland_grass`.

| min | p05 | p25 | **median** | p75 | p95 | max | sum |
|---|---|---|---|---|---|---|---|
| 0.0050 | 0.0290 | 0.0911 | **0.2285** | 0.6161 | 3.9358 | 218.8185 | 110,883.7 ha |

**⭐ Strongest validation in this collection:** the `.dbf` carries its own area field `OSA_AREA`
(m²). Recomputing area from raw shapefile coordinates for 4,000 records and comparing gives a ratio
with **median 0.9989, range 0.9902–1.0061** — **~0.1 % agreement**. The declared attribute and the
independent geometric computation corroborate each other.

**Caveats:** parcels are much smaller than elsewhere (median 0.23 ha — Portuguese fragmentation), so
filter to ≥1 ha if you want field-like geometry; **3,062 multi-part records** will break a naive
"one row = one polygon" assumption; the `.shp` header declares a bogus file length (7.79 GB vs the
real 45.6 MB) — the `.shx` index and a byte-level record walk both confirm 100,000, so trust the
`.shx` if a strict validator complains; and the exactly-round 100,000 suggests a capped re-export
rather than the complete national register.

Larger EuroCrops layers **not** downloaded (link + size only, as instructed):
`ES_2023.zip` **9.79 GB** · `FR_2018.zip` 2.64 GB · `IE_2023.zip` 1.09 GB · `AT_2021.zip` 845 MB ·
`RO_ny.zip` 686 MB · `LV_2021.zip` 547 MB · `LT_2021.zip` 545 MB · `SE_2021.zip` 427 MB ·
`FI_2020.zip` 369 MB · `HR_2020.zip` 351 MB · `SK_2021.zip` 325 MB · `DK_2019.zip` 298 MB ·
`EE_2021.zip` 288 MB · `NL_2020.zip` 283 MB · `CZ_2023.zip` 278 MB. All from the same Zenodo record.

### 6c. Pour Arab / Spisser / Essert — 30 French fields ✅ (polygons extracted)

| | |
|---|---|
| Title | Agricultural Fields 2D and 3D Models Dataset |
| Creators | Daniel Pourreau, Spisser Matthias, Caroline Essert |
| **DOI** | **`10.5281/zenodo.10949632`** |
| **Licence** | **CC BY 4.0** |
| Archive | `Agri-Field-Dataset.zip` — **854,038,814 B (854 MB)** — **NOT downloaded in full** |

Cited by the Fields2Benchmark paper as prior art ("Pour [12] introduced a dataset of 30 French
fields"), making it a directly relevant comparator.

**How it was obtained without the 854 MB:** I parsed the ZIP's *central directory* over HTTP range
requests to build a complete 448-entry index, then extracted only the small XML members by byte
range and inflated them in memory. **Total transferred ≈ 120 KB instead of 854 MB.** The bulk is PLY
meshes and rasters (e.g. `surfaces_3D/field15.ply` = 30.7 MB alone).

- **Format: XML** — `<field_polygon>` with `<vertex><x>/<y>` elements. *Not* GeoJSON/Shapefile/WKT.
- **CRS: NONE — no coordinate reference system at all.** These are **local, field-centred, projected
  coordinates in CENTIMETRES**, origin at field centre. Not georeferenced; cannot be placed on a map.
- Obtained: **`polygons_2D/` 31 files** (30 usable), **`dividing_lines/` 22**, **`access_segments/` 31**.
- 4–17 vertices per field; **no holes, no multipart**.

**How the centimetre unit was established** (the naive reading is wrong by 10⁴):
1. Reading the coordinates as **metres** gives 154–132,048 ha per field — absurd, and contradicted by
   the dataset's own stated range. Ruled out.
2. Reading as **centimetres** gives 0.015–13.205 ha. The dataset states **"from 1.83 to 13.21
   hectares"**, and the largest field computes to **13.205 ha** — matching the stated maximum almost
   exactly. **30 of 31 fields land in 1.5–14 ha.** ✅
3. Cross-check from the mesh: `surfaces_2D/field1.ply` has 546,212 vertices and is documented as a
   0.25 m grid. Under centimetres `field1` is ~260 × 180 m → ~750,000 grid points, the right order.
   Under metres it would be 4.6 million × too many. ✅
4. `field1.xml` (12477.5, 5226.81) matches `field1.ply` (12455.4, 5186.4) to ~1.5 % — same system. ✅

**One outlier:** `field31.xml` = **0.015 ha** (~17 × 14 m), far outside the stated range — exclude
it, leaving **30 usable fields**, which matches the "30 French fields" count in the Fields2Benchmark
paper. ✅

**Conversion notes:** divide coordinates by **100** to get metres — *not* 1000. Because there is no
CRS there is nothing to reproject; the data is planar and metric once divided, so swath spacing and
turn radii are directly usable. Do **not** invent an EPSG code for these.

### 6d. AI4Boundaries (JRC) — 🔗 located, **not downloaded**

| | |
|---|---|
| Title | "AI4Boundaries: an open AI-ready dataset to map field boundaries with Sentinel-2 and aerial photography" |
| Authors | d'Andrimont, Claverie, Kempeneers, Muraro, Yordanov, Peressutti, Batič, Waldner (EC Joint Research Centre) |
| Paper | *Earth System Science Data* 15, 317–329 (2023) · `10.5194/essd-15-317-2023` · **open access, CC BY 4.0** |
| **Data DOI** | **`http://data.europa.eu/89h/0e79ce5d-e4c8-4721-8773-59a4acf2c9c9`** (JRC Open Data Catalogue) |
| Content | 7,831 samples; **2.5 M vector ground-truth parcels covering 47,105 km²** + raster chips |
| Regions | Austria, Catalonia, France, Luxembourg, Netherlands, Slovenia, Sweden (2019 GSAA) |
| CRS | **EPSG:3035** (ETRS89-LAEA, metres) for the vector labels |

**Why not downloaded:** it is primarily a **raster/computer-vision** benchmark (256×256 Sentinel-2
and 512×512 orthophoto chips) built for field-*boundary detection* models, not for CPP. The vector
labels are genuine GSAA parcel polygons and are the interesting part for this project, but they are
bundled with the imagery in a large archive. **Reported as a link rather than downloaded.**

**Caveats for CPP use:** parcel coverage is limited to 4 × 4 km sampled chips (2560 × 2560 m or
512 × 512 m extents), so the polygons are clipped to small tiles rather than whole fields; and the
source GSAA layers for France and Sweden require registration/password, which affects provenance of
those subsets.

### 6e. Considered and not pursued

- **Sen4CAP** — the project's own summary document is licensed CC BY-SA 4.0, but Sen4CAP is a
  processing system/software suite, not a redistributable field-boundary polygon product. No single
  open parcel GeoPackage to download. No dataset obtained.
- **EU JRC / MARS field polygons** — MARS is an agro-meteorological *statistical* service; its
  outputs are regional aggregates and rasterised crop masks, not parcel polygons. No polygon product
  to download. (AI4Boundaries, above, is the JRC's actual open parcel-polygon release and is the
  right thing to use if a JRC source is wanted.)

---

## 7. Cross-dataset comparison (for choosing a benchmark set)

| Dataset | Polygons | Holes? | Non-convex? | Real? | CRS / units | Median area | Licence |
|---|---|---|---|---|---|---|---|
| Fields2Benchmark | 350 | **Yes (49)** | Yes | **Yes** | EPSG:4326 (deg) | 2.15 ha | CC BY 4.0 + mixed ⚠️ |
| PDOK BRP (cropland) | 1,535 | Yes (169) | Yes | **Yes** | EPSG:28992 (**m**) | 5.38 ha | **CC0 1.0** |
| EuroCrops PT | 100,000 | Yes | Yes | **Yes** | EPSG:4326 (deg) | 0.23 ha | CC BY-SA 4.0 ⚠️ |
| Pour Arab (FR) | 30 | No | Some | **Yes** | *local cm* | 4.15 ha | CC BY 4.0 |
| Nilsson & Zhou | (54) | **No** | **No — convex** | **No — synthetic** | — | — | not obtainable |

**Reading of this table:** Fields2Benchmark is the only set that is simultaneously real,
obstacle-bearing and published as a *benchmark* — which is exactly why it was the right top priority.
PDOK BRP is the best licence (CC0) and the only one already in metres. EuroCrops PT gives volume but
tiny parcels and a share-alike licence. Pour Arab gives real French geometry but is un-georeferenced.

---

## 8. Verification ledger — what "verified" means here

**Downloaded and inspected by me** (files on disk, checksums and contents checked):

- [x] Fields2Benchmark `wkt.zip` — **MD5 identical to Zenodo**; unzips to exactly **350** non-empty
      `.wkt` files; all 350 re-parsed with an independent bracket-matching WKT parser; all rings
      closed; inner rings proven to be true holes by point-in-polygon; coordinate ranges land in
      NL/EE/LT; areas physically plausible.
- [x] Fields2Benchmark `README.md` and `LICENSE` — **MD5 identical to Zenodo**.
- [x] The dataset URL **independently confirmed inside the OA paper's own Data-availability
      statement**, extracted from the PDF text (`f2b_paper_text.txt` line 845).
- [x] PDOK BRP GeoJSON — 6,093 valid features re-parsed; CRS member read; geometry types enumerated;
      areas recomputed; attribute values read; bbox axis order verified *before* bulk download.
- [x] EuroCrops `PT_2021.zip` — **MD5 identical to Zenodo**; complete 5-file shapefile set; `.prj`
      read directly; all 100,000 records walked at byte level, 0 malformed; extent = mainland
      Portugal; **areas cross-validated against the file's own `OSA_AREA` to ~0.1 %**.
- [x] Pour Arab XMLs — ZIP central directory parsed over range requests (448 real entries); XML
      members inflated from byte ranges; coordinate unit determined empirically and cross-checked
      two independent ways; areas recomputed; outlier identified and disclosed.

**Found a link but did NOT fetch:** AI4Boundaries (JRC catalogue), EuroCrops non-PT country layers,
Fields2Benchmark `imgs.zip`.

**Could NOT obtain:** Nilsson & Zhou's 54 fields (paywall + no deposit). Reason recorded in
`data/nilsson/SOURCE.md`.

**Not done:** no heavy geospatial stack was installed; **no dataset was converted or reprojected** —
all conversion needs are reported above as notes instead, as instructed. No synthetic data was
generated and passed off as real; the only derived artefacts are explicitly labelled as such
(`wkt_rescaled_1ha/`, `pdok_brp_flevoland_cropland_ge1ha.geojson`).

---

## 9. Recommended next steps for the parent agent

1. **Use `data/fields2benchmark/wkt_extracted/wkt/` as the primary benchmark set** — 350 real fields,
   49 with obstacles. Reproject to **EPSG:3035** and preserve holes.
2. **Use `wkt_rescaled_1ha/` for the constant-area comparison** that would otherwise have required
   Nilsson's fields — it fills the gap left by target 2 without pretending to be that dataset.
3. **Add `pdok_brp_flevoland_cropland_ge1ha.geojson` as the metric-control set** — CC0, already in
   metres, no reprojection risk, 1,535 fields to scale up sample sizes.
4. **Treat EuroCrops PT as optional scale-up** — it works, but tiny parcels and CC BY-SA complicate
   both the experiment and the licence story.
5. **Say "not obtained" about Nilsson**, with the reason, and note it is synthetic anyway.
6. **State the mixed upstream licence of the Fields2Benchmark `lt_` subset** if the work is or may
   become commercial.
7. If raster backdrops are wanted for figures, download `imgs.zip` (138.6 MB) separately — link in §4.
