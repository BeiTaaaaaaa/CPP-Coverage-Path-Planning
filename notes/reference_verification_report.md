# Bibliographic verification report — CPP for agricultural mowers (computational-geometry clipping + coverage path planning)

Scope: 10 claimed references from the Chinese-language research notes.
Method: publisher metadata (Crossref REST, DOAJ API, OpenAlex, Europe PMC, Zenodo API), official repos (GitHub API), package indexes (PyPI JSON). Sources are cited per item.
Verification date: 2026-10-12.

Legend: **VERIFIED** = claim matches official metadata · **PARTIALLY WRONG** = exists but a field/method/number is wrong · **NOT FOUND** = no evidence found.

---

## 1. Jayalakshmi et al., IEEE Access 2025 CPP-in-dynamic-environments survey

**Status: VERIFIED** (identity/metadata/topic) — **section structure NOT CONFIRMED**

Every bibliographic field in the claim is correct:

| Field | Value (Crossref, DOI 10.1109/ACCESS.2025.3556446) |
|---|---|
| Title | A Comprehensive Survey on Coverage Path Planning for Mobile Robots in Dynamic Environments |
| Authors | K. P. Jayalakshmi (ORCID 0000-0002-4093-7442, Manipal Inst. of Technology), Vishnu G. Nair (ORCID 0000-0003-0599-748X, same), Dayakshini Sathish (ORCID 0000-0002-0952-9176, St. Joseph Engineering College, Mangaluru) |
| Venue | IEEE Access, vol. 13, ISSN 2169-3536 |
| Pages | 60158–60185 (confirmed by both Crossref and DOAJ start/end page fields) |
| Date | DOI deposited/created 31 March 2025 (matches the claimed 31 Mar 2025); DOAJ record created 9 April 2025 |
| DOI | 10.1109/ACCESS.2025.3556446 |
| Other | CC-BY; 237 references; type = TOPICAL REVIEW |

- Does it cover dynamic environments? **Yes.** DOAJ abstract: "This survey reviews recent advancements in CPP, focusing on algorithms and methodologies tailored for dynamic environments. It highlights the challenges posed by environmental variability, obstacle dynamics, and real-time computational demands." DOAJ keywords: *Coverage path planning, path planning, dynamic environment, obstacle avoidance, autonomous systems*.
- Sections on replanning in dynamic environments / multi-robot cooperation / algorithm classification + performance evaluation: **could not be confirmed.** IEEE Xplore serves a bot challenge to non-browser fetches, my tooling cannot read PDFs, and the shell has no outbound network, so I could not read the full text. Indirect evidence only: (a) the paper is a 237-reference "topical review" whose stated scope is dynamic environments, so replanning-type content is very likely present; (b) a table row indexed from the paper's own PDF reads `Competitive Strategies | Online | Dynamic Environments | Robots compete for tasks/resources; requires interaction m…`, i.e. there is a strategy-classification table with an "Online / Dynamic Environments" axis and a multi-robot "competitive strategies" category. **Treat the three named sections as unverified.** If these must be cited, get the PDF.
- Note for the project: this is a *general mobile-robot* CPP survey (cleaning, mowing, demining, AUV, inspection), not an agricultural-machinery survey.

Sources: <https://doi.org/10.1109/ACCESS.2025.3556446> · <https://api.crossref.org/works/10.1109/ACCESS.2025.3556446> · <https://doaj.org/api/search/articles/doi%3A10.1109%2FACCESS.2025.3556446> · <https://ieeexplore.ieee.org/document/10946186>

---

## 2. "3D Path Planning for Autonomous Agricultural Machinery" (2026, ScienceDirect)

**Status: PARTIALLY WRONG** (title truncated; venue/year correct)

Real record:
- **Title:** *From Flat Fields to Rugged Terrain: A Systematic Review of 3D Path Planning for Autonomous Agricultural Machinery*
- **Authors:** Jingjing Xu; ruhui wang; yi xiong; yixiao xie; bin zeng; Fuyu Yang (ORCID 0000-0003-1857-2851) — as deposited in Crossref, several given names are lower-cased
- **Venue:** Smart Agricultural Technology (Elsevier), article 102593
- **Date:** September 2026 issue
- **DOI:** 10.1016/j.atech.2026.102593

The claimed short title is a plausible abbreviation of the real title, and "2026, ScienceDirect" is right (Elsevier/ScienceDirect), but the citation as written is not usable as-is.

Sources: <https://doi.org/10.1016/j.atech.2026.102593> · <https://www.sciencedirect.com/science/article/pii/S277237552600818X>

---

## 3. "Agricultural machinery automatic navigation technology" (2023, Cell)

**Status: PARTIALLY WRONG** — real paper, wrong venue and wrong year of record

Real record:
- **Title:** *Agricultural machinery automatic navigation technology* (claim's title is exact)
- **Authors:** Zhixin Yao, Chunjiang Zhao, Taihong Zhang — College of Computer and Information Engineering, Xinjiang Agricultural University; National Engineering Research Center for Information Technology in Agriculture
- **Venue:** **iScience** (Cell Press / Elsevier), vol. 27, issue 2, article 108714 — **not** *Cell*
- **Dates:** first published online **14 December 2023**; issue of record **February 2024**
- **DOI:** 10.1016/j.isci.2023.108714 · PMID 38292432 · PMC10827555 · CC BY
- **Type:** review article. Abstract: reviews GNSS / machine-vision / lidar navigation for agricultural machinery and four families of path-planning algorithms (graph search, sampling, optimization, learning), proposing 22 algorithms by application scenario.

Corrections: "Cell" → **iScience**; "2023" is defensible only as the online-first year (14 Dec 2023), the issue of record is **2024**. It is also not an agricultural-engineering journal such as *Computers and Electronics in Agriculture* — it is a broad multidisciplinary Cell Press journal, so follow the "Cell Press ≠ Cell" caution, but note the paper is genuinely a Cell Press publication.

Sources: <https://doi.org/10.1016/j.isci.2023.108714> · <https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:%2210.1016/j.isci.2023.108714%22&resultType=core&format=json> · <https://europepmc.org/articles/PMC10827555>

---

## 4. Fields2Benchmark

**Status: VERIFIED for existence, name, venue, volume, 350 fields, the five-unit decomposition and the Fields2Cover extension — NOT CONFIRMED for "16 algorithms / 8 objective functions"**

Real citation (name "Fields2Benchmark" is correct):
- Mier, G.; Casado Faulí, A. M.; Valente, J.; de Bruin, S. **"Fields2Benchmark: An open-source benchmark for coverage path planning methods in agriculture."** *Smart Agricultural Technology*, **vol. 12**, article **101156**, **December 2025**. DOI **10.1016/j.atech.2025.101156**. Open access, CC BY. NWO-funded (ENPPS.LIFT.019.019). Online 15 July 2025.

Confirmed against the abstract (OpenAlex, DOAJ, WUR Research Portal — all agree):
- "a dataset with **350 real-world fields**, featuring non-convex fields and in-field obstacles" ✔ (350 confirmed)
- "decomposes the problem into **five units**, i.e., **field decomposition, headland generation, swath generation, route planning, and path planning**" ✔ (exact match to the claim's list)
- "**extends the existing Fields2Cover library** by allowing task-specific choices, adding a module that splits a field into simpler parts, introducing new algorithms to shorten routes and handle refill needs, and adding tools to compare algorithms in isolation" ✔
- Validated on three use cases (field arrangement; route and path planning with and without capacity constraints).

Not confirmed:
- **"16 algorithms"** and **"8 objective functions"**: no accessible source states these numbers. The abstract only says "interchangeable algorithms and objective functions". The predecessor Fields2Cover paper (2023) reported "8 state-of-the-art methods and 7 objective functions", so 16/8 is plausible but unproven. I could not read the full text (PDF content-type blocked for my fetch tool; ScienceDirect returns HTTP 403; shell has no network). **Do not cite 16/8 as verified.**
- **Code location:** I could not find a public repository named Fields2Benchmark — GitHub repository search for the name returns 0 results, and the Fields2Cover org has no repo with "benchmark" in its name. The paper states datasets and code are publicly available, but the URL lives in the full text I could not read. The paper itself is green-OA at <https://edepot.wur.nl/698168>.

Sources: <https://doi.org/10.1016/j.atech.2025.101156> · <https://api.openalex.org/works/doi:10.1016/j.atech.2025.101156> · <https://doaj.org/api/search/articles/doi%3A10.1016%2Fj.atech.2025.101156> · <https://research.wur.nl/en/publications/fields2benchmark-an-open-source-benchmark-for-coverage-path-plann/>

---

## 5. Hexagonal Maritime CPP Dataset, Zenodo 2026

**Status: VERIFIED** (exact title differs slightly)

- **Dataset title:** *Hexagonal Maritime Coverage Path Planning Dataset* (the notes' "Hexagonal Maritime CPP Dataset" is an abbreviation)
- **DOI:** 10.5281/zenodo.19477858 (version v1.0.0; concept DOI 10.5281/zenodo.19477857)
- **Creator:** Carlos S. Sepúlveda (ORCID 0000-0003-2426-7634), Directorate of Programs, Research and Development, Chilean Navy
- **Publication date:** 9 April 2026 · license CC-BY-4.0 · type: Dataset
- **Files:** `DATASET_SCHEMA.md` (1,508 B) and `poly_mix_28_46_with_hex_holes_10k.pt` (490,531,467 B ≈ 490 MB) — the `10k` in the filename matches the claimed instance count
- **Code:** <https://github.com/carsepmo/cpp_benchmarks/>

The claim "10,000 Hamiltonian-feasible instances on a hexagonal grid" is confirmed by the companion paper (the dataset record itself does not use the phrase "Hamiltonian-feasible"):
- Sepúlveda, C. S.; Ruz, G. A. **"Benchmarking Classical Coverage Path Planning Heuristics on Irregular Hexagonal Grids for Maritime Coverage Scenarios."** arXiv:2604.15202 (16 Apr 2026), cs.RO. Abstract: "The benchmark contains **10,000 Hamiltonian-feasible instances** spanning compact, elongated, and irregular morphologies, **17 heuristics from seven families**… **Exact Depth-First Search confirms that every released instance is Hamiltonian-feasible.**"

Caveats for experimental design: instances derive from *synthetic, maritime-motivated* areas of interest (irregular shapes plus internal holes), not real maritime survey data; the benchmark is single-vehicle; and the 17 heuristics belong to the arXiv paper, not to the Zenodo dataset.

Sources: <https://doi.org/10.5281/zenodo.19477858> · <https://zenodo.org/records/19477858> · <https://arxiv.org/abs/2604.15202>

---

## 6. Nilsson's benchmark — the "38 convex fields" claim

**Status: PARTIALLY WRONG** — 38 is a Fields2Cover subset, not the size of Nilsson's benchmark

- **Real size of Nilsson's benchmark: 54 standard fields** (plus three operation configurations). Nilsson & Zhou's own abstract (Aarhus University research portal, publisher-deposited): "a benchmark dataset comprising **54 standard fields** and three operation configurations."
- **Where 38 comes from:** the Fields2Cover paper. Its contribution list reads "A quantitative comparison using **38 convex fields** between eight state-of-the-art CPP approaches/methods and seven objective functions", and the results section reads "The second experiment was conducted using **38 convex fields of the Nilsson's benchmark**, re-scalated to an area of 1 ha…" Fields2Cover v1 supported only convex fields, which is why only the convex subset was used.
- **"initial experiments" is imprecise:** 38 convex fields were used in the *second* simulation experiment of the 2023 RA-L paper (the first used three named fields — REC_A, CIR_B, SAL_B — rescaled to 100 m²).

True citation:
> Nilsson, R. S., & Zhou, K. (2020). *Method and bench-marking framework for coverage path planning in arable farming.* **Biosystems Engineering, 198, 248–265.** DOI 10.1016/j.biosystemseng.2020.08.007

(Same paper is cited as ref. [27] by Fields2Cover and as ref. 0110 by Fields2Benchmark.)

Sources: <https://doi.org/10.1016/j.biosystemseng.2020.08.007> · <https://pure.au.dk/portal/en/publications/method-and-bench-marking-framework-for-coverage-path-planning-in-/> · <https://ar5iv.labs.arxiv.org/html/2210.07838> · <https://doi.org/10.1109/LRA.2023.3248439>

---

## 7. 2025 Scientific Reports paper using rotating calipers for convex decomposition of concave polygons

**Status: VERIFIED (citation) — method attribution PARTIALLY supported**

- Wu, W.; Wang, Z.; Lin, L.; Chang, X.; Tian, L. **"An efficient coverage path planning method for UAV in complex concave regions."** *Scientific Reports* **15**, article **37227** (2025). DOI **10.1038/s41598-025-20978-8**. Published online **24 October 2025**. PMID 41136448 · PMC12552447 · CC BY-NC-ND.

Why it is the right paper: publisher text from this article reads "The Rotating Calipers method is an algorithmic technique used to solve geometric problems, primarily for calculating specific pr…", i.e. the paper does use/discuss rotating calipers.

Caveat — read the method before citing it for "rotating calipers for convex decomposition": the abstract describes the decomposition as **PSO-based** ("employs Particle Swarm Optimization (PSO) to decompose the target area into convex subregions, simplifying intricate concave areas into manageable convex components, thus reformulating the issue as a TSP"), followed by an improved ACO (FA3ACO) for the resulting TSP. Rotating calipers appears as part of the geometric toolkit rather than as the headline decomposition algorithm, so a citation saying "uses rotating calipers for convex decomposition" needs the method section checked. (Full text: <https://europepmc.org/articles/PMC12552447>.)

Also found, in case the notes meant a different 2025 Scientific Reports concave-decomposition CPP paper: *Multi-UAV forest area inspection path planning based on concave polygon region decomposition*, Sci Rep (2025), DOI 10.1038/s41598-025-26060-7 — I did not verify its use of rotating calipers.

Sources: <https://doi.org/10.1038/s41598-025-20978-8> · <https://api.crossref.org/works/10.1038/s41598-025-20978-8> · <https://www.nature.com/articles/s41598-025-20978-8>

---

## 8. 2026 paper on "nonlinear weight decomposition" for convex partitioning

**Status: VERIFIED that the paper exists with that exact method name — the "as few convex subregions as possible" objective is NOT CONFIRMED**

- Wang, Zhongjie; Zhang, Minyu; Cen, Ming (Chongqing University of Posts and Telecommunications). **"Nonlinear Weight Decomposition Based Coverage Path Planning Method for Irregular Polygonal Areas."** In *2026 38th Chinese Control and Decision Conference (CCDC)*, Nanjing, China, 15–18 May 2026, **pp. 7404–7410**. DOI **10.1109/CCDC69976.2026.11560112**. Publisher: IEEE; 27 references; 0 citations (Crossref, indexed 24 June 2026).

Important qualifier: this is an **IEEE conference paper (CCDC 2026)**, not a journal article — if the notes describe it as a journal paper, that is wrong. I could not retrieve the abstract (IEEE Xplore blocks automated fetches; PDFs are unfetchable with my tools), so **the claim that it "partitions concave polygon regions into as few convex subregions as possible" is unverified**; only the title's method name is confirmed.

Sources: <https://doi.org/10.1109/CCDC69976.2026.11560112> · <https://api.crossref.org/works?query.bibliographic=Nonlinear+Weight+Decomposition+Based+Coverage+Path+Planning+Method+for+Irregular+Polygonal+Areas&rows=2> · <https://ieeexplore.ieee.org/document/11560112>

---

## 9. Fields2Cover: repo, license, maintenance, PyPI, maturity

**Status: VERIFIED (with important practical caveats)**

- **Repo URL:** <https://github.com/Fields2Cover/Fields2Cover> (org *Fields2Cover*, repo id 501080115, created 2022-06-08; docs at <https://fields2cover.github.io>)
- **License:** **BSD-3-Clause** (GitHub API `license.spdx_id = BSD-3-Clause`; README badge BSD-3; PyPI classifier "License :: OSI Approved :: BSD License")
- **Still maintained? Yes.** Last push 2026-09-22; repo updated 2026-10-08; **909 stars / 206 forks / 30 open issues**; Discussions enabled. Latest release **v2.1.0, published 2026-09-03** (new headland generators `ReqHL` and `CorridorHL`, scikit-build-core packaging, PyPI sdist publishing, several geometry bug fixes). GitHub's releases list contains v2.1.0, v1.2.1 and v1.2.0 (the docs additionally reference a v2.0 and a v1→v2 migration guide). NWO-funded.
- **Is it on PyPI and does `pip install fields2cover` work?** The package exists: <https://pypi.org/project/fields2cover/>, owner *Fields2Cover*, version **2.1.0** (uploaded 2026-09-03), `requires_python >=3.9`. **But only an sdist is published** (`fields2cover-2.1.0.tar.gz`, 110,389 B) — **no wheels**, and 2.1.0 is the *only* version on PyPI. So pip must compile from source, which requires GDAL, GEOS, Eigen, Boost, TBB, tinyxml2, nlohmann-json and (for C++) OR-tools to be pre-installed. PyPI classifiers list **Operating System :: MacOS and POSIX :: Linux only — there is no Windows classifier**, so on this Windows working copy `pip install fields2cover` will most likely fail; use WSL2/Linux or the project's dev container. I could not execute `pip install` to prove it either way (no outbound network from the shell) — the packaging facts above are from the PyPI JSON API.
- **"Most mature" agricultural CPP library?** **Defensible but should be qualified.** Supporting: it is the most-starred repo in GitHub's "coverage path planning" search (909★), its own RA-L comparison table rates it the only package combining documentation + no grid + non-holonomic turns + headlands + customizable objective + terrestrial agricultural vehicles, it has ROS 2 integration (via opennav_coverage) and it is the base of the 2025 Fields2Benchmark. Notable competitors/caveats: **nobleo/full_coverage_path_planner** (674★, Apache-2.0, ROS, last push 2025-05-27, grid-based); **ethz-asl/polygon_coverage_planning** (668★, GPL-3.0, last push 2023-11-13, polygons with holes, UAV-oriented); **ipa320/ipa_coverage_planning** (Fraunhofer IPA, ROS); **RicheyHuang/CoveragePlanner** (353★); **open-navigation/opennav_coverage** (318★, Nav2-based, itself built on Fields2Cover). Also note the Fields2Benchmark paper's own criticism that Fields2Cover "fails on non-convex fields and operations that require reload trips" (true of v1; v2 added trapezoidal/boustrophedon decomposition). Suggested phrasing: "the most widely used and most feature-complete *open-source agricultural* CPP library", with competitors named.
- ROS note: the ROS 1 wrapper `Fields2Cover/fields2cover_ros` is **archived**; the maintained ROS 2 route is `opennav_coverage`.

Sources: <https://api.github.com/repos/Fields2Cover/Fields2Cover> · <https://api.github.com/repos/Fields2Cover/Fields2Cover/releases> · <https://pypi.org/pypi/fields2cover/json> · <https://fields2cover.github.io/>

---

## 10. GitHub / PyPI resources

### 10a. github.com/devanys/Coverage-Path-Planning-The-Boustrophedon-Cellular-Decomposition
**Status: VERIFIED it exists — but treat as immature**
- Description: "Implements a Coverage Path Planning (CPP) simulation using the Boustrophedon Cellular Decomposition (BCD) algorithm. It allows a mobile robot to efficiently cover an entire workspace while avoiding obstacles."
- Language Python · 18★ · 4 forks · created 2025-10-23 · last push **2025-10-23** (single burst of activity) · **no license** · 0 open issues · default branch `main`.

### 10b. github.com/RicheyHuang/BoustrophedonCellularDecompositionPathPlanning
**Status: VERIFIED — but unmaintained since 2020**
- Description: "Complete Coverage Path Planning Using Boustrophedon Cellular Decomposition Algorithm"
- Language **C++** · **GPL-3.0** · **162★** · 61 forks · created 2019-08-23 · last push **2020-12-07** · 3 open issues · default branch `master`. (Same author also maintains the more popular `RicheyHuang/CoveragePlanner`, 353★.)

### 10c. github.com/open-navigation/opennav_coverage
**Status: VERIFIED and actively maintained**
- Description: "Nav2 Compatible Complete Cover Task Server, Navigator, & BT Utils"
- Language C++ · **Apache-2.0** · **318★** · 78 forks · created 2023-09-14 · last push **2026-08-03** · 9 open issues · org *open-navigation*. This is the Nav2 complete-coverage server documented by Nav2, and the Fields2Cover README names it as the ROS 2 integration built on Fields2Cover.

### 10d. PyPI package `field-coverage`
**Status: VERIFIED** (matches "damage-aware CPP with GTSP modeling")
- PyPI page: <https://pypi.org/project/field-coverage/> · owner **Louis_Cutteridge** · latest **0.1.1**, released **2026-04-24** (0.1.0 on 2026-04-15) · `requires_python >=3.11` · wheel + sdist published · dependencies include `ortools`, `networkx`, `shapely`, `pandas`, `pyarrow`.
- Description confirms the claim: "Damage-Aware Coverage Path Planning … Produces coverage paths that jointly minimise tile revisits and turns — both of which contribute to soil compaction in agricultural applications… reference implementation for the paper *Damage-Aware Coverage Path Planning as a Generalised Travelling Salesperson* (Cutteridge, Frenkel, and Mansouri)". Pipeline: (1) rectilinear decomposition via **Fields2Cover** + up to eight boustrophedon sweep patterns per region; (2) parallel **Ant Colony Optimisation** over sweep patterns formulated as a **GTSP**; (3) simulated-annealing refinement with an "absorption" operator. Evaluated on **200 real UK field geometries** from Sentinel-2: **4.2% average revisit rate, 33 turns per 100 tiles**.
- Caveats: version 0.x; the 0.1.0 PyPI page titles it "Louis Cutteridge FYP…" (final-year project); no license field and no classifiers declared on PyPI; Docker image documented as tested on ARM64 only; the README notes the web interface used for one figure is not public.

Sources: <https://api.github.com/repos/devanys/Coverage-Path-Planning-The-Boustrophedon-Cellular-Decomposition> · <https://api.github.com/repos/RicheyHuang/BoustrophedonCellularDecompositionPathPlanning> · <https://api.github.com/repos/open-navigation/opennav_coverage> · <https://pypi.org/pypi/field-coverage/json>

---

## Summary table

| # | Item | Verdict | Key correction |
|---|---|---|---|
| 1 | Jayalakshmi et al., IEEE Access 13:60158–60185, 2025 | VERIFIED (identity/topic); sections unconfirmed | None on metadata; get PDF to confirm replanning/multi-robot/evaluation sections |
| 2 | "3D Path Planning for Autonomous Agricultural Machinery" | PARTIALLY WRONG | Real title: "From Flat Fields to Rugged Terrain…", Smart Agric. Technol., art. 102593, 2026-09, 10.1016/j.atech.2026.102593 |
| 3 | "Agricultural machinery automatic navigation technology" | PARTIALLY WRONG | iScience 27(2):108714, **not Cell**; online 14 Dec 2023, issue Feb **2024** |
| 4 | Fields2Benchmark, 2025, Smart Agric. Technol. 12, 350 fields | VERIFIED (350 fields, 5 units, extends Fields2Cover) | "16 algorithms / 8 objective functions" unverified; no public repo found under that name |
| 5 | Hexagonal Maritime CPP Dataset, Zenodo 2026, 10k instances | VERIFIED | Exact title "Hexagonal Maritime Coverage Path Planning Dataset", DOI 10.5281/zenodo.19477858 |
| 6 | Nilsson benchmark = 38 convex fields | PARTIALLY WRONG | Benchmark = **54 fields**; 38 = convex subset used by Fields2Cover's *second* experiment |
| 7 | 2025 Sci Rep rotating-calipers convex decomposition | VERIFIED (citation); method partly supported | Sci Rep 15:37227, 10.1038/s41598-025-20978-8; headline decomposition is PSO-based |
| 8 | 2026 "nonlinear weight decomposition" paper | VERIFIED existence; objective unconfirmed | CCDC 2026 conference paper, pp. 7404–7410, 10.1109/CCDC69976.2026.11560112 |
| 9 | Fields2Cover repo/license/maintenance/PyPI | VERIFIED | BSD-3-Clause, v2.1.0 (2026-09-03), actively maintained; **sdist-only, Linux/macOS only** → pip install compiles from source |
| 10 | 3 GitHub repos + PyPI `field-coverage` | ALL VERIFIED | devanys repo has no license & one day of commits (Oct 2025); RicheyHuang repo unmaintained since Dec 2020 |

### Items needing the parent's action
1. **Item 6** — fix the notes: Nilsson's benchmark has 54 fields; 38 is Fields2Cover's convex subset. Any experimental-design sentence that says "38 fields (Nilsson)" must be reworded.
2. **Item 3** — change venue to iScience (Cell Press) and year to 2024 (or 2023 online-first, stated explicitly).
3. **Item 4** — delete or re-source "16 algorithms, 8 objective functions"; only 350 fields / 5 units are verified.
4. **Items 1, 7, 8** — three claims need the PDFs read before citing at section/method level (survey sections; rotating-calipers role; nonlinear-weight-decomposition objective).
5. **Item 9** — if the project must run Fields2Cover on this Windows workspace, plan for WSL2/Linux or a container; `pip install fields2cover` is an sdist build requiring GDAL/GEOS/OR-tools.
