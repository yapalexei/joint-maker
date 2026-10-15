#!/usr/bin/env bash
# Runs every regression test in a background Blender and checks its output.
#
#   tests/run_all.sh [folder containing joint_maker/]      (default: the repository root)
#
# Set BLENDER to your Blender executable if it isn't the macOS default.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${1:-$(dirname "$HERE")}"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
fails=0

run() {   # run <test file> -> captured output in $OUT
    OUT="$("$BLENDER" --background --factory-startup --python "$HERE/$1" -- "$ROOT" 2>&1)"
    if echo "$OUT" | grep -q "Traceback"; then
        echo "FAIL  $1: Python error"; echo "$OUT" | grep -A8 "Traceback" | head -12; fails=$((fails + 1)); return 1
    fi
}

check() { # check <test> <description> <expected count> <grep pattern>
    local got
    got=$(echo "$OUT" | grep -c -E "$4")
    if [ "$got" -eq "$3" ]; then echo "ok    $1: $2 ($got/$3)"
    else echo "FAIL  $1: $2 ($got/$3)"; fails=$((fails + 1)); fi
}

run test_smoke.py       && check smoke       "every joint type builds and unloads"            7  "SMOKE \('(HINGE|BALL)', .*, 2, 0, |SMOKE \('DOUBLE', .*, 3, 0, |SMOKE unregistered OK"
run test_scale.py       && check scale       "joint sizes: parts, watertight, no collisions"  28 "^RES .*nm 0 collisions none"
run test_place.py       && check place       "slide/turn handles and placement maths"         2  "PT centre matches slide: True|PT parts 2 nonmanifold 0"
run test_offset.py      && check offset      "centre on shape and offsets"                    2  "OT offsets after centring: Y -15.000 mm \(expected -15.000\)|OT shells 3 \(expect 3\)"
run test_fit.py         && check fit         "fit cutter keeps a neighbour intact"            14 "^FT .*(, fit|fit 1mm).*vol 4080.0 \(intact 4080.0\)"
run test_limit.py       && check limit       "limit outer reach: parts still split"           12 "^LT [^ ].*parts [23] "
run test_limit_motion.py && check limit_motion "limit + bevel keep the bend range"             16 "^LM .*parts 2 "
run test_curve.py       && check curve       "joints along a curved, tapering part"           8  "^CV [0-9].*parts 4 \(expect 4\)"
run test_shape.py       && check shape       "shape cutter presets and custom shapes"         12 "^SH .*parts [23] "
run test_section.py     && check section     "cross-section preview and panel draw"           19 "open edges 0|draw OK|gone: True"
run test_shortlink.py   && check shortlink   "short links: parts and honest bend range"       30 "^SL .*parts 3 .*free at range-2: True"

echo
if [ "$fails" -eq 0 ]; then echo "ALL TESTS PASSED"; else echo "$fails CHECK(S) FAILED"; exit 1; fi
