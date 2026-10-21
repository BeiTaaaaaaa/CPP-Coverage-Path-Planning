#!/usr/bin/env bash
# =============================================================================
# setup_fields2cover.sh - Fields2Cover reference baseline for the CPP project
# =============================================================================
# Installs Fields2Cover (with its Python bindings) into a Linux container and
# verifies it by running a real coverage-path-planning example.
#
# WHAT THIS SCRIPT DOES (idempotent - safe to re-run):
#   1. locates the Docker CLI (Docker Desktop on Windows, usable from WSL)
#   2. makes sure tools/ros.key (official ROS signing key) is present
#   3. builds the image `fields2cover:2.1.1` from tools/Dockerfile.fields2cover
#      (skipped when the image already exists; use FORCE_BUILD=1 to rebuild)
#   4. runs tools/f2c_example.py inside that image and writes the figure to
#      tools/out/
#
# WHY DOCKER + A ROS 2 DEB INSTEAD OF `pip install fields2cover`:
#   * PyPI only ships an sdist for fields2cover 2.1.0; building it needs a
#     toolchain plus GitHub access (CMake fetches dependencies) - github.com is
#     not reachable from this machine.
#   * Fields2Cover is also released as a prebuilt ROS 2 Jazzy (Ubuntu 24.04)
#     Debian package that already contains the Python module AND the C++
#     OR-Tools dependency (ros-jazzy-ortools-vendor). Nothing is compiled.
#   * packages.ros.org is unreachable here, so the official ROS 2 apt repo is
#     used through the TUNA (Tsinghua University) mirror.
#   * No WSL sudo is required at all; Docker Desktop is already running.
#
# USAGE
#   From WSL:        wsl -d Ubuntu -- bash /mnt/c/Users/666/Desktop/CPP/tools/setup_fields2cover.sh
#   From Git Bash:   bash /c/Users/666/Desktop/CPP/tools/setup_fields2cover.sh
#   Interactive shell afterwards:
#                    docker run --rm -it -v "C:\Users\666\Desktop\CPP\tools:/work" fields2cover:2.1.1 bash
# =============================================================================

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # ...\CPP\tools
WORKSPACE="$(cd "$HERE/.." && pwd)"                    # ...\CPP
IMAGE="${F2C_IMAGE:-fields2cover:2.1.1}"
OUT_DIR="$HERE/out"

# ---------------------------------------------------------------------------
# 1. Find a Docker CLI that can actually reach the Docker Desktop daemon.
#    IMPORTANT: inside WSL, the extension-less `docker` on PATH is only a
#    Docker Desktop stub that prints
#       "The command 'docker' could not be found in this WSL 2 distro.
#        We recommend to activate the WSL integration in Docker Desktop"
#    (WSL integration is not enabled for this distro), while `docker.exe` -
#    the real Windows client, reachable through WSL interop - works fine.
#    So every candidate is probed against the live daemon and the first one
#    that answers wins.
# ---------------------------------------------------------------------------
DOCKER=""
for cand in docker.exe docker \
            "/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe" \
            "C:/Program Files/Docker/Docker/resources/bin/docker.exe"; do
  command -v "$cand" >/dev/null 2>&1 || continue
  if "$cand" version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    DOCKER="$cand"; break
  fi
done
if [ -z "$DOCKER" ]; then
  echo "ERROR: no docker CLI could reach the Docker Desktop daemon." >&2
  echo "       Start Docker Desktop and/or enable its WSL integration." >&2
  exit 1
fi
echo "== docker CLI : $DOCKER  (server $("$DOCKER" version --format '{{.Server.Version}}'))"

# ---------------------------------------------------------------------------
# 2. Translate Linux paths to the Windows form the Windows docker.exe expects.
#    (`wslpath` on WSL, `cygpath` on Git Bash; no-op on native Linux.)
# ---------------------------------------------------------------------------
to_docker_path() {
  if command -v wslpath >/dev/null 2>&1; then wslpath -w "$1"
  elif command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"
  else printf '%s' "$1"; fi
}
CTX="$(to_docker_path "$HERE")"
echo "== build context: $CTX"

# ---------------------------------------------------------------------------
# 3. The official ROS apt signing key. Shipped in tools/; re-downloaded only
#    if missing. (ghproxy mirrors raw.githubusercontent.com, which is blocked
#    from this network.)
# ---------------------------------------------------------------------------
if [ ! -s "$HERE/ros.key" ]; then
  echo "== downloading ROS apt key"
  for url in \
    "https://ghproxy.net/https://raw.githubusercontent.com/ros/rosdistro/master/ros.key" \
    "https://mirrors.tuna.tsinghua.edu.cn/ros2/ubuntu/ros.key" ; do
    if curl -fsSL --max-time 60 "$url" -o "$HERE/ros.key"; then break; fi
  done
  [ -s "$HERE/ros.key" ] || { echo "ERROR: could not fetch ros.key" >&2; exit 1; }
fi

# ---------------------------------------------------------------------------
# 4. Build the image (skipped when it already exists).
# ---------------------------------------------------------------------------
if [ "${FORCE_BUILD:-0}" = "1" ] || ! "$DOCKER" image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "== building image $IMAGE (first run downloads ~600 MB, takes minutes)"
  "$DOCKER" build \
      --progress=plain \
      -f "$CTX\\Dockerfile.fields2cover" \
      -t "$IMAGE" \
      "$CTX"
else
  echo "== image $IMAGE already present (FORCE_BUILD=1 to rebuild)"
fi

# ---------------------------------------------------------------------------
# 5. Prove it works: run the coverage-planning example inside the image.
#    The tools/ directory is mounted read-write at /work so the figure and the
#    script stay on the Windows side.
# ---------------------------------------------------------------------------
mkdir -p "$OUT_DIR"
echo "== running coverage-planning example"
"$DOCKER" run --rm \
    -v "$(to_docker_path "$HERE"):/work" \
    -w /work \
    "$IMAGE" \
    python3 /work/f2c_example.py /work/out

echo
echo "== done. Figure: $(to_docker_path "$OUT_DIR")\\f2c_example.png"
echo
echo "== run your OWN script with Fields2Cover (whole workspace mounted):"
echo "   $DOCKER run --rm -v \"$(to_docker_path "$WORKSPACE"):/work\" -w /work $IMAGE \\"
echo "       python3 src/your_script.py"
echo "== interactive shell:"
echo "   $DOCKER run --rm -it -v \"$CTX:/work\" -w /work $IMAGE bash"
