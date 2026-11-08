#!/usr/bin/env bash
# Build observer 0.8-poc = mod/TerrariaBenchObserver + tools/v10_transfer/PocBridge.cs into runs/v10-poc-build.
# Only the v10 transfer PoC run installs this .tmod; benchmark fixtures keep observer 0.7.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
B=$ROOT/runs/v10-poc-build
rm -rf "$B" && mkdir -p "$B/ModSources" "$B/tml"
cp -r "$ROOT/mod/TerrariaBenchObserver" "$B/ModSources/"
cp "$ROOT/tools/v10_transfer/PocBridge.cs" "$B/ModSources/TerrariaBenchObserver/"
sed -i 's/^version = .*/version = 0.8/' "$B/ModSources/TerrariaBenchObserver/build.txt"
cd "$HOME/.local/share/Steam/steamapps/common/tModLoader"
bash LaunchUtils/ScriptCaller.sh -build "$B/ModSources/TerrariaBenchObserver" -tmlsavedirectory "$B/tml" > "$B/build.log" 2>&1 || true
grep -h "error CS" tModLoader-Logs/Natives.log 2>/dev/null | tail -5 || true
test -f "$B/tml/Mods/TerrariaBenchObserver.tmod" && grep -q "0 errors" "$B/build.log" && echo "built $B/tml/Mods/TerrariaBenchObserver.tmod"
