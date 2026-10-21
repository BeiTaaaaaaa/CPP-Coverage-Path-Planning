# Fields2Cover reference baseline (CPP project)

Status: **working** — Fields2Cover **2.1.1** with its Python bindings runs in a
Linux container on this Windows machine. Verified on 2026-10-12 with real
coverage-path-planning output (see `out/f2c_example.png` and the log below).

## TL;DR — how to run a CPP example

```powershell
# one-time (idempotent) setup: builds the image, runs the example
wsl -d Ubuntu -- bash /mnt/c/Users/666/Desktop/CPP/tools/setup_fields2cover.sh

# afterwards, run any script of the project with Fields2Cover available
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' run --rm `
    -v 'C:\Users\666\Desktop\CPP:/work' -w /work fields2cover:2.1.1 `
    python3 src/your_script.py
```

Interactive shell: `docker.exe run --rm -it -v "C:\Users\666\Desktop\CPP:/work" -w /work fields2cover:2.1.1 bash`

## Files

| file | purpose |
| --- | --- |
| `Dockerfile.fields2cover` | image definition (Ubuntu 24.04 + ROS 2 Jazzy Fields2Cover deb) |
| `setup_fields2cover.sh` | idempotent build + verification driver (runs under WSL / Git Bash) |
| `f2c_example.py` | proof-of-life: field -> headlands -> swaths -> route -> path + PNG |
| `ros.key` | official ROS apt signing key (used with `signed-by=` in apt) |
| `out/f2c_example.png` | figure produced by the verification run |

## Why not `pip install fields2cover`

* PyPI ships fields2cover **2.1.0 as an sdist only** (no wheels, `>=3.9`,
  MacOS/Linux classifiers only) — it must be compiled, and its CMake build
  fetches dependencies from `github.com`, which is **unreachable** from this
  network (verified: `curl https://github.com` times out; raw.githubusercontent
  and api.github.com fail as well; `ghproxy.net` works as a mirror).
* Fields2Cover is also released as a **prebuilt ROS 2 Jazzy (Ubuntu 24.04)
  Debian package** which already contains the Python module *and* the C++
  OR-Tools dependency (`ros-jazzy-ortools-vendor`). Nothing is compiled and no
  WSL `sudo` is needed.
* `packages.ros.org` is unreachable; the official repo is used through the
  Tsinghua (TUNA) mirror `https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu`
  and stays GPG-verified via `ros.key`.

## Exact versions in the image

| component | version |
| --- | --- |
| `ros-jazzy-fields2cover` | `2.1.1-1noble.20260922.035009` (from TUNA ROS 2 mirror) |
| Python | 3.12.3 |
| GDAL | 3.8.4 (`libgdal34t64`) |
| OR-Tools | 9.9 (`ros-jazzy-ortools-vendor`, at `/opt/ros/jazzy/opt/ortools_vendor`) |
| image size | 2.76 GB (`fields2cover:2.1.1`) |

## Gotchas found the hard way (already handled in the image)

1. `import fields2cover` fails with
   `ImportError: libortools.so.9: cannot open shared object file` unless
   `/opt/ros/jazzy/opt/ortools_vendor/lib` is on the loader path — the
   Dockerfile writes `/etc/ld.so.conf.d/fields2cover.conf` + `ldconfig` and
   also sets `LD_LIBRARY_PATH`.
2. `f2c.Visualizer.save()` silently writes **no file** unless `gnuplot-nox` is
   installed (it prints `gnuplot: not found` and returns). The Dockerfile
   installs it.
3. `SG_BruteForce.generateSwaths(angle, width, x)` returns
   `SwathsByCells` when `x` is a `Cells` and plain `Swaths` when `x` is a
   `Cell`; `genSortedSwaths`/`planPath` want the `Cell` form
   (`no_hl.getGeometry(0)`), while `RP_RoutePlannerBase.genRoute` wants the
   `Cells` form.
4. Inside WSL the extension-less `docker` on PATH is a Docker Desktop stub
   ("could not be found in this WSL 2 distro", WSL integration is off for this
   distro) — use **`docker.exe`**, which the setup script probes for
   automatically.
5. In the image, Ubuntu's own archive is switched to the TUNA mirror only
   *after* `ca-certificates` is installed (https mirror before that fails).

## Verified (what was actually run)

1. `python3 tools/f2c_example.py` inside the image — field 3420 m^2 -> 8 swaths
   -> snake order -> Dubins path (1061 states, **339.68 m**) -> OR-Tools route
   over two cells (**373.61 m**) -> PNG written. Exit code 0.
2. **Unmodified upstream tutorials** from the v2.1.0 sources, run against the
   same image:
   `tutorials/python/4_swath_generator.py`, `6_path_planning.py`
   (Dubins, Dubins CC, Reeds-Shepp, Reeds-Shepp HC) and
   `8_complete_flow.py` (GML import -> UTM -> path -> back to GPS).
   All finished successfully and produced 9 figures, kept in
   `env/tutorial_out/`.
3. `setup_fields2cover.sh` itself, invoked exactly as documented from WSL —
   idempotent re-run, exit code 0.

## Cached offline artifacts (`env/`)

* `ros-jazzy-fields2cover_2.1.1-1noble.20260922.035009_amd64.deb` — the exact
  package installed into the image.
* `f2c-repo-v2.1.0.tar.gz` + `Fields2Cover-2.1.0/` — upstream sources, incl.
  `tutorials/python/*` and `data/`.
* `fields2cover-2.1.0.tar.gz` + `sdist/` — the PyPI sdist (not installable
  here: no compiler route to OR-Tools).
* `tutorial_out/` — figures from the upstream tutorials.

## Native WSL route (not used, evaluated)

Ubuntu 26.04 has every build dependency in its archive **except
`libortools-dev`** (not packaged), Python there is 3.14, and the prebuilt
2.1.1 deb cannot be installed (it needs `libgdal34t64` / `ros-jazzy-*`, i.e.
the noble ABI). A native WSL install would therefore mean compiling
Fields2Cover from source with OR-Tools pulled from a GitHub release tarball —
possible only through a GitHub mirror, and much slower than the container.
