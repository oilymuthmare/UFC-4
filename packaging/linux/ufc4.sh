#!/usr/bin/env bash
# UFC 4 native port (Linux release). Usage:
#   ./ufc4.sh                          opens the graphical launcher
#   ./ufc4.sh --play                   plays with the saved launcher settings (no GTK)
#   ./ufc4.sh [--play] /path/to/CUSA14209  legacy CLI; remembers the base game folder
#                                       (the adjacent -patch folder is merged automatically)
# Settings: ~/.local/share/UFC4Native/launcher.json (GUI / --play); ufc4.conf (legacy CLI).
# Controls and overlay: bbport.ini in the same folder. Logs: logs/ there.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
# No arguments opens the GUI; --play and the existing positional folder keep CLI use.
if [[ $# == 0 ]]; then exec python3 "$here/launcher/ufc4_launcher.py"; fi
if [[ ${1:-} == --play ]]; then
    shift
    if [[ $# == 0 ]]; then exec python3 "$here/launcher/ufc4_online.py" --play; fi
fi
data=${BB_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/UFC4Native}
mkdir -p "$data"
command -v python3 >/dev/null || { echo "UFC 4: python3 is needed (install it with your package manager)" >&2; exit 1; }
[[ -f $data/ufc4.conf ]] || cp "$here/ufc4.conf.example" "$data/ufc4.conf"
if [[ $# -gt 0 && -d $1 ]]; then
    game=$(cd -- "$1" && pwd); shift
    printf '%s\n' "$game" > "$data/game-folder"
    python3 - "$here/launcher" "$data" "$game" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ufc4_online import load_settings, save_settings
data = Path(sys.argv[2])
settings = load_settings(data)
settings['game'] = sys.argv[3]
save_settings(data, settings)
PY
elif [[ -f $data/game-folder ]]; then
    game=$(cat "$data/game-folder")
else
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1
fi
[[ -f $game/eboot.bin ]] || { echo "UFC 4: no eboot.bin in $game" >&2; exit 1; }
game=$(python3 "$here/scripts/merge_update.py" "$game" | tail -1)
# ufc4.conf: KEY=value lines; a variable already set in the environment wins.
while IFS= read -r line || [[ -n $line ]]; do
    [[ $line =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]] || continue
    key=${BASH_REMATCH[1]} value=${BASH_REMATCH[2]}
    [[ -n $value && -z ${!key+x} ]] && export "$key=$value"
done < "$data/ufc4.conf"
export BB_PREBUILT=1 BB_DATA_DIR="$data" BB_GAME_DIR="$game" BB_SAVE_LOG=${BB_SAVE_LOG:-1}
export LD_LIBRARY_PATH="$here/bin/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$here/run.sh" "$@"
