#!/usr/bin/env bash
# Build mod/TerraBot into runs/terrabot-build/tml/Mods/TerraBot.tmod (Omarchy). Only TerraBot runs install it; the
# deployed observer build, fixtures and enabled-mods lists of other runs are untouched.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
B=$ROOT/runs/terrabot-build
rm -rf "$B" && mkdir -p "$B/ModSources" "$B/tml"
cp -r "$ROOT/mod/TerraBot" "$B/ModSources/"
cd "$HOME/.local/share/Steam/steamapps/common/tModLoader"
bash LaunchUtils/ScriptCaller.sh -build "$B/ModSources/TerraBot" -tmlsavedirectory "$B/tml" > "$B/build.log" 2>&1 || true
grep -h "error CS" "$B/build.log" | sort -u | head -30 || true
test -f "$B/tml/Mods/TerraBot.tmod" && echo "built $B/tml/Mods/TerraBot.tmod"
