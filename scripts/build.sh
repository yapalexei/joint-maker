#!/usr/bin/env bash
# Test, build and validate the Joint Maker extension.
#
#   scripts/build.sh            run the tests, then build dist/joint_maker-<version>.zip
#   scripts/build.sh --no-tests build only
#
# Set BLENDER to your Blender executable if it isn't the macOS default.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
cd "$ROOT"

if [ "${1:-}" != "--no-tests" ]; then
    tests/run_all.sh "$ROOT"
fi

find joint_maker -name __pycache__ -type d -prune -exec rm -rf {} +
mkdir -p dist
"$BLENDER" --factory-startup --command extension build --source-dir joint_maker --output-dir dist
version=$(sed -n 's/^version = "\(.*\)"/\1/p' joint_maker/blender_manifest.toml)
"$BLENDER" --factory-startup --command extension validate "dist/joint_maker-$version.zip"
echo "built dist/joint_maker-$version.zip"
