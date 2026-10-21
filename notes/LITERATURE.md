# Literature notes — verified reference list

Compiled 2026-10-12. Every entry below was checked against a publisher metadata
API (Crossref, DOAJ, OpenAlex, Europe PMC, Zenodo, GitHub, PyPI) rather than
against the original notes file. Items are marked **VERIFIED**, **CORRECTED** or
**NOT OBTAINABLE**.

The starting point was `CPP.txt` in the repository root. Nine of its eleven
factual claims survived verification; three did not. The corrections are
collected in [Corrections to the original notes](#corrections-to-the-original-notes)
and they matter, because two of them would have produced wrong numbers in a
benchmark section.

---

## 1. Core surveys

### 1.1 Coverage path planning in dynamic environments — VERIFIED

> Jayalakshmi, K. P., Nair, V. G., & Sathish, D. (2025). *A Comprehensive Survey
> on Coverage Path Planning for Mobile Robots in Dynamic Environments.*
> **IEEE Access**, 13, 60158–60185.
> [10.1109/ACCESS.2025.3556446](https://doi.org/10.1109/ACCESS.2025.3556446)

Every bibliographic field checks out independently in Crossref *and* DOAJ,
including the page range. Open access (CC-BY), 237 references, labelled a
topical review. The abstract confirms the dynamic-environment framing —
"environmental variability, obstacle dynamics, and real-time computational
demands" — and the keyword list includes *dynamic environment* and *obstacle
avoidance*.

**Caveat that matters for this project.** This is a *general mobile-robot* CPP
survey (cleaning, mowing, demining, AUV, inspection), **not** an agricultural
machinery survey. It is the right source for the dynamic-replanning framing and
the wrong source for headlands, refill trips or soil compaction.

**Unverified detail.** IEEE Xplore serves a bot challenge and the PDF could not
be read, so the claim in `CPP.txt` that the paper contains specific sections on
"replanning in dynamic environments" and "algorithm classification and
performance evaluation" could not be confirmed at section level. Indirect
evidence — a table row indexed from the paper's own PDF reading
`Competitive Strategies | Online | Dynamic Environments | ...` — shows a
strategy-classification table with an online/dynamic axis and a multi-robot
"competitive strategies" category does exist. Treat the section names as
unconfirmed until the PDF is read.

### 1.2 3D path planning for agricultural machinery — CORRECTED (title truncated)

The real title is longer than the notes claimed:

> Xu, J., Wang, R., Xiong, Y., Xie, Y., Zeng, B., & Yang, F. (2026).
> *From Flat Fields to Rugged Terrain: A Systematic Review of 3D Path Planning
> for Autonomous Agricultural Machinery.* **Smart Agricultural Technology**,
> article 102593.
> [10.1016/j.atech.2026.102593](https://doi.org/10.1016/j.atech.2026.102593)

### 1.3 Agricultural machinery navigation technology — CORRECTED (venue and year)

`CPP.txt` lists this as "2023, Cell". It is Cell **Press**, but the journal is
*iScience*, and the issue of record is February 2024:

> Yao, Z., Zhao, C., & Zhang, T. (2024). *Agricultural machinery automatic
> navigation technology.* **iScience**, 27(2), 108714.
> [10.1016/j.isci.2023.108714](https://doi.org/10.1016/j.isci.2023.108714)
> PMID 38292432

Online 14 December 2023; issue February 2024. Reviews GNSS / machine-vision /
lidar navigation and four path-planning algorithm families (graph search,
sampling, optimisation, learning), proposing 22 algorithms.

---

## 2. Benchmark and datasets

### 2.1 Fields2Benchmark — VERIFIED with one unconfirmed number

> Mier, G., Casado Faulí, A. M., Valente, J., & de Bruin, S. (2025).
> *Fields2Benchmark: An open-source benchmark for coverage path planning methods
> in agriculture.* **Smart Agricultural Technology**, 12, article 101156.
> [10.1016/j.atech.2025.101156](https://doi.org/10.1016/j.atech.2025.101156)

Confirmed verbatim from the abstract: **350 real-world fields** with non-convex
shapes and in-field obstacles; the problem decomposed into **five units** (field
decomposition, headland generation, swath generation, route planning, path
planning); it **extends Fields2Cover** by adding a field-splitting module, route
shortening, refill handling, and tools to compare algorithms in isolation.

**Not confirmed:** the note "16 algorithms, 8 objective functions" appears
nowhere accessible. The abstract says only "interchangeable algorithms and
objective functions", and the predecessor Fields2Cover paper reported *8 methods
and 7 objective functions*, so 16/8 is plausible but **must not be cited**. The
full text is behind ScienceDirect's bot wall; a green open-access PDF exists at
<https://edepot.wur.nl/698168>.

**The data is real and downloadable** — but not from GitHub (a repository search
returns zero hits, and the Fields2Cover organisation has no benchmark repo). It
is on Zenodo:

> **DOI [10.5281/zenodo.14524734](https://doi.org/10.5281/zenodo.14524734)**
> (version 10.5281/zenodo.14524735). Landing page:
> <https://research.wur.nl/en/datasets/fields2benchmark-dataset/>

350 plain-text WKT files, one `POLYGON` per file, in **EPSG:4326** (the CRS is
declared nowhere in the files or the README and had to be inferred from the
coordinate ranges, 3.80–27.32 °E, 51.36–59.54 °N). 140 Dutch, 113 Lithuanian, 97
Estonian. **49 of the 350 have genuine interior rings** — verified by
point-in-polygon testing, so they are real in-field obstacles rather than
multipart islands. Net area: min 0.499 ha, median 2.145 ha, max 25.802 ha.

**Licence caveat.** The Zenodo deposit is CC BY 4.0, but the dataset's own
README documents mixed upstream terms: the Dutch fields are PDOK CC0 1.0 /
Public Domain Mark, the Estonian fields are CC BY-SA 3.0 EE, and **the 113
Lithuanian fields are "non-commercial use only"**. Do not describe all 350 as
uniformly CC BY 4.0 in a commercial context; the clean subset is `nl_` + `ee_`
(237 fields).

### 2.2 Nilsson's benchmark — CORRECTED, and not obtained

The notes said "38 convex fields". The benchmark itself has **54 fields**:

> Nilsson, R. S., & Zhou, K. (2020). *Method and bench-marking framework for
> coverage path planning in arable farming.* **Biosystems Engineering**, 198,
> 248–265.
> [10.1016/j.biosystemseng.2020.08.007](https://doi.org/10.1016/j.biosystemseng.2020.08.007)

The **38** is a Fields2Cover subset: its contribution list says "a quantitative
comparison using 38 convex fields", and its results say "the second experiment
was conducted using 38 convex fields of the Nilsson's benchmark, re-scaled to an
area of 1 ha". Fields2Cover v1 supported only convex fields, hence the subset.
"Initial experiments" is also imprecise — the first experiment used three named
fields (REC_A, CIR_B, SAL_B) at 100 m².

Any sentence of the form "38 fields (Nilsson's benchmark)" must be reworded to
"38 convex fields selected from the 54-field Nilsson benchmark".

**The data could not be obtained.** Four independent negative checks: Crossref
exposes no data DOI; Europe PMC reports `isOpenAccess=N`, no PMCID,
"Subscription required"; there is no Zenodo deposit and none on the authors' own
Aarhus Pure record; the Mendeley hit is a reference-manager record, not data. It
was not pursued further, and nothing was substituted for it.

**More importantly, these are not real fields.** The Fields2Benchmark paper
states that "Nilsson's dataset offers 54 manually-created geometries without
in-field obstacles" — synthetic, hand-drawn, convex, no holes. It is a convex
baseline and is *not* interchangeable with real field geometry. Since
Fields2Benchmark already supplies real, non-convex fields with obstacles, the
practical loss is small.

### 2.3 Hexagonal Maritime CPP Dataset — VERIFIED

> Sepúlveda, C. S. (2026). *Hexagonal Maritime Coverage Path Planning Dataset.*
> Zenodo. [10.5281/zenodo.19477858](https://doi.org/10.5281/zenodo.19477858)

Published 2026-04-09, CC-BY-4.0. Contains `DATASET_SCHEMA.md` and
`poly_mix_28_46_with_hex_holes_10k.pt` (490 MB) — the `10k` matches the claim.
The "10,000 Hamiltonian-feasible instances" phrasing comes from the companion
paper, not the dataset record:

> Sepúlveda, C. S., & Ruz, G. A. (2026). *Benchmarking Classical Coverage Path
> Planning Heuristics on Irregular Hexagonal Grids for Maritime Coverage
> Scenarios.* [arXiv:2604.15202](https://arxiv.org/abs/2604.15202)

Exact depth-first search confirms every released instance is Hamiltonian-feasible.
Caveat for experimental design: the instances are synthetic (maritime-motivated,
with internal holes) and single-vehicle, and the 17 heuristics belong to the
paper rather than the dataset.

---

## 3. Algorithms

### 3.1 Concave-region convex decomposition — CORRECTED attribution

> Wu, W., Wang, Z., Lin, L., Chang, X., & Tian, L. (2025). *An efficient
> coverage path planning method for UAV in complex concave regions.*
> **Scientific Reports**, 15, article 37227.
> [10.1038/s41598-025-20978-8](https://doi.org/10.1038/s41598-025-20978-8)

The citation is exact, and the article does discuss rotating calipers
("The Rotating Calipers method is an algorithmic technique used to solve
geometric problems…"). But the abstract presents the decomposition as
**PSO-based** — "employs Particle Swarm Optimization (PSO) to decompose the
target area into convex subregions" — followed by an improved ant-colony
optimiser. So rotating calipers is in the toolkit, not demonstrably *the*
convex-decomposition mechanism. The notes' attribution should be softened until
the method section is read.

### 3.2 Nonlinear-weight decomposition — VERIFIED existence, objective unconfirmed

> Wang, Z., Zhang, M., & Cen, M. (2026). *Nonlinear Weight Decomposition Based
> Coverage Path Planning Method for Irregular Polygonal Areas.* **2026 38th
> Chinese Control and Decision Conference (CCDC)**, Nanjing, 15–18 May 2026,
> pp. 7404–7410.
> [10.1109/CCDC69976.2026.11560112](https://doi.org/10.1109/CCDC69976.2026.11560112)

It is an **IEEE conference paper, not a journal article** as the notes implied.
The abstract is unretrievable (IEEE blocks automated access), so the claim that
it partitions concave polygons "into as few convex subregions as possible" is
unverified; only the method name in the title is confirmed.

---

## 4. Tools and code

### 4.1 Fields2Cover — VERIFIED, with practical caveats

> Mier, G., Valente, J., & de Bruin, S. (2023). *Fields2Cover: An Open-Source
> Coverage Path Planning Library for Unmanned Agricultural Vehicles.*
> **IEEE Robotics and Automation Letters**, 8(4), 2166–2172.
> [10.1109/LRA.2023.3248439](https://doi.org/10.1109/LRA.2023.3248439)

Repository <https://github.com/Fields2Cover/Fields2Cover>, **BSD-3-Clause**,
actively maintained (last push 2026-09-22; 909 stars, 206 forks). Latest release
**v2.1.0**, 2026-09-03.

**"Most mature" needs qualification.** Defensible as "the most widely used /
most feature-complete open-source *agricultural* CPP library", but there are
competitors: `nobleo/full_coverage_path_planner` (674★, grid-based),
`ethz-asl/polygon_coverage_planning` (668★, GPL-3.0, last push 2023),
`ipa320/ipa_coverage_planning`, `RicheyHuang/CoveragePlanner` (353★), and
`open-navigation/opennav_coverage` (318★, built on Fields2Cover).

**The PyPI route does not work on Windows.** The `fields2cover` package on PyPI
is **sdist-only** (a single version, 2.1.0), so pip compiles from source and
needs GDAL, GEOS, Eigen, Boost, TBB, tinyxml2, nlohmann-json and C++ OR-Tools.
Its classifiers list MacOS and POSIX::Linux only — **no Windows**. On this
project's Windows host, `pip install fields2cover` fails. It was made to work
through a Docker container instead; see `tools/README_fields2cover.md`. (Note
this also contradicts the original notes' advice to
`pip install fields2cover` in weeks 1–2.)

Also relevant: the ROS 1 wrapper `Fields2Cover/fields2cover_ros` is **archived**;
the maintained ROS 2 path is `opennav_coverage`. Fields2Benchmark reports that
Fields2Cover v1 "fails on non-convex fields and operations that require reload
trips" — which is exactly the gap Fields2Benchmark exists to close.

### 4.2 Clipper2 — VERIFIED, but unusable on Python 3.14

> Johnson, A. *Clipper2.* <https://github.com/AngusJohnson/Clipper2>

The library is real, well maintained, and exactly what the notes describe
(boolean ops and polygon offsetting for simple and complex polygons). Its Python
binding, `clipper2-py`, however, declares `Requires-Python <3.13` on every
release (1.6.2 through 1.11.3), so **it cannot be installed on this project's
Python 3.14** and has no wheel for it. This project therefore uses
Shapely 2.2.0 / GEOS 3.14.1 as the geometry engine, which is the notes'
own first-choice prototype path anyway. Clipper2 remains the right choice if
the C++ port is done, and its performance advantage over GEOS on large unions
and buffers is a genuine argument for that port.

### 4.3 Other repositories — all four VERIFIED

| Resource | Facts |
|---|---|
| `devanys/Coverage-Path-Planning-The-Boustrophedon-Cellular-Decomposition` | Exists; Python BCD simulation with obstacle avoidance; 18★; created and last pushed 2025-10-23; **no licence**; immature |
| `RicheyHuang/BoustrophedonCellularDecompositionPathPlanning` | Exists; C++; GPL-3.0; 162★, 61 forks; last push **2020-12-07**, unmaintained |
| `open-navigation/opennav_coverage` | Exists and active; Nav2 complete-coverage task server; Apache-2.0; 318★; last push 2026-08-03 |
| PyPI `field-coverage` | Exists; 0.1.1 (2026-04-24); Python ≥3.11; damage-aware CPP with a GTSP formulation over sweep patterns, parallel ACO, simulated annealing; evaluated on 200 real UK Sentinel-2 field geometries, 4.2 % average revisit rate. Caveats: v0.x, no licence declared on PyPI, Docker tested ARM64 only |

---

## Corrections to the original notes

| # | `CPP.txt` said | Verified |
|---|---|---|
| 1 | "Hybrid A" (line 21, 88) and a stray `*` | **Hybrid A\*** — the asterisks were lost in plain-text conversion |
| 2 | "有理半径 `r` `r` 的偏移" (lines 31–33) | LaTeX rendering artefact; the variable is duplicated |
| 3 | "Agricultural machinery automatic navigation technology (2023, Cell)" | **iScience** 27(2):108714, issue of record **February 2024** (online Dec 2023) |
| 4 | "3D Path Planning for Autonomous Agricultural Machinery (2026)" | Real title is *From Flat Fields to Rugged Terrain: A Systematic Review of 3D Path Planning for Autonomous Agricultural Machinery* |
| 5 | "16 algorithms, 8 objective functions" | **Unverified.** Only 350 fields, the five units and the Fields2Cover extension are confirmed |
| 6 | "Nilsson's benchmark: 38 convex fields" | The benchmark has **54** fields; **38** is the convex subset Fields2Cover used in its *second* experiment |
| 7 | "Nilsson's benchmark, used for Fields2Cover's initial experiments" | The first experiment used three named fields; the 38-field comparison was the second |
| 8 | "used rotating calipers for convex decomposition" | The paper's decomposition is **PSO-based**; rotating calipers appears in the toolkit, not as the decomposition mechanism |
| 9 | "Fields2Benchmark (2025, Smart Agricultural Technology Vol. 12)" | Correct — but the data is on **Zenodo**, not GitHub, and there is no public "Fields2Benchmark" repository |
| 10 | "`pip install fields2cover`" as week-1 setup | **Fails on Windows** (sdist-only, Linux/macOS classifiers). Needs Docker/WSL |
| 11 | "CGAL provides exact inward offset contours via `offset_polygon_2`" | Function name not verified; CGAL's straight-skeleton offset is the documented route. Left as a claim to check against the CGAL manual before citing |

## Reading priorities

The three claims that most affect this project's experimental design, in order:

1. **Read the Fields2Benchmark full text** to recover the real algorithm and
   objective-function counts, and to check how its five units map onto the
   pipeline here. Its five-unit decomposition is a natural comparison frame.
2. **Read the IEEE Access survey's PDF** to confirm the dynamic-replanning and
   multi-robot sections before citing them as motivation.
3. **Read the Scientific Reports method section** before attributing convex
   decomposition to rotating calipers.

Items that looked like blockers but are not: the Clipper2 Python binding (use
Shapely), the Nilsson dataset (synthetic, and Fields2Benchmark is better), and
the Fields2Cover install path (Docker works).
