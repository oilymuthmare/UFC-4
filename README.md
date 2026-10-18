# UFC 4 — native PS4 port for Linux and Windows (bring-up)

**EA SPORTS UFC 4** (PlayStation 4, `CUSA14209` Europe / `CUSA14204` America, update **28.00**)
as a **native x86-64** program on Linux and Windows. This is not a CPU emulator: the game's
original code runs directly on the PC's processor, a dedicated runtime replaces the PS4 system
libraries, and a renderer derived from [shadPS4](https://github.com/shadps4-emu/shadPS4)
translates the PS4's GPU work to Vulkan.

It is the [UFC 3 native port](https://github.com/T3CHNOLOG1C/SacredFire) retargeted at UFC 4,
which itself comes from SacredFire (Crash Team Racing: Nitro-Fueled) and
[bbport](https://github.com/deadinside28/bloodborne_pc) (Bloodborne). All code is GPL-2.0-or-later.

> **No game files are included.** You need your own dump of UFC 4 and its 28.00 update. This
> project is not affiliated with or endorsed by Electronic Arts, Sony Interactive Entertainment or
> the UFC. *EA SPORTS UFC*, *PlayStation* and related marks belong to their owners and are named
> only to identify the game.

---

## Status

**Not yet playable. Nothing has been run against a UFC 4 dump.** This tree is the UFC 3 port's
runtime, renderer, launchers, packaging and tests with a UFC 4 game profile wired in, and a plan for
bringing the game up: [`docs/ufc4/BRINGUP.md`](docs/ufc4/BRINGUP.md). Every per-game finding the
UFC 3 port made (executable addresses, shader hashes, barred write sites, online protocol tables) is
still UFC 3's and is treated as a hypothesis here until measured on UFC 4.

What carries over unchanged, because it does not depend on which game is loaded:

- **Native execution.** `eboot.bin` is converted offline (`scripts/prepare.py`, `link_libc.py`,
  `link_modules.py`) into a flat memory image with the game's own PS4 libc and `libSceFios2`
  linked in as native code. TLS accesses (`fs:`) are rewritten (`gs:` on Linux, the TEB TLS slot
  on Windows).
- **Runtime** (`src/runtime_*.c`): memory, threads, mutexes/semaphores/event flags, files, audio
  (ATRAC9, and MP3 for AJM), controller (SDL), saves, user services and network stubs. Imports are
  resolved by name (`NID#library`); what UFC 4 calls that UFC 3 did not will show up as
  unresolved imports on the first boot and be implemented from there.
- **GPU** (`gpu/`): the adapted shadPS4 renderer. PM4 commands are decoded on one thread and
  draws are recorded into Vulkan on another; GPU-written memory is page-protected so CPU reads and
  writes keep it coherent. The write-window and readback machinery finds its sites by fault
  address at run time, not from a per-game table.
- **Launchers** (Windows `UFC4.exe`, Linux GTK `launcher/ufc4_launcher.py` and `ufc4.sh`),
  packaging and the test suite.

What is UFC 3's and will need redoing for UFC 4 (details in the bring-up plan):

- The pinned executable image hash (`scripts/game_check.py` `SUPPORTED`, empty until recorded).
- Guest addresses in the diagnostics (`gpu/shim/bbport_guest_hooks.cpp`, heap sites, the UFC 3
  present-interval setter at `0x1182a0`, the discard lock). They verify the code bytes before
  patching and are gated on `BB_GAME_VARIANT`, so on UFC 4 they stay off rather than misfire.
- Shader patches (`patches/shaders/`, keyed by translated-shader hash) and the resolution
  experiments under `patches/experiments/` (keyed to UFC 3's title id; skipped on UFC 4).
- The private online server (`tools/ufc4_server.py`, `ufc4_auth.py`, `ufc4_games.py`): the
  Blaze/EASO schema in it was captured from UFC 3. UFC 4 will differ at least in its game version
  string and probably in its TDF schema; **Offline is the only mode to expect to work** until that
  is re-captured.

## Requirements

- x86-64 CPU with AVX (the game code, built for the PS4's Jaguar, uses AVX).
- GPU with Vulkan 1.3. ≥ 6 GB of VRAM recommended.
- A dump of the game: the base folder and the 28.00 update, already decrypted (plaintext SELF or
  ELF; `scripts/prepare.py` rejects encrypted segments). For example:

  ```
  PS4/CUSA14209          (base game, eboot.bin)
  PS4/CUSA14209-patch    (28.00 update; -PATCH, -update, _patch… also work)
  ```

  `scripts/merge_update.py` merges them into `CUSA14209-merged` using hard links (no extra disk
  space; on drives without hard links the files are copied). The America release `CUSA14204`
  works the same way.

## Linux

```bash
# dependencies: C/C++ compiler, CMake, Vulkan, SDL3, glslang and Python 3 (see shell.nix / build.sh)
git clone <this repo> ufc4 && cd ufc4
git submodule update --init --recursive
bash build.sh                                       # builds the runtime + renderer
python3 scripts/merge_update.py /path/PS4/CUSA14209 # base + 28.00 -> /path/PS4/CUSA14209-merged
BB_GAME_DIR=/path/PS4/CUSA14209-merged bash run.sh  # defaults to orig/CUSA14209
```

`run.sh` detects the `ufc4` profile and applies the starting defaults from the UFC 3 port (precise
readbacks, write windows, pre-upload, unlocked frame rate). Any variable can be overridden on the
command line (`BB_WRITE_WINDOW=0 bash run.sh`). The first run prints the executable's image hash;
record it in `scripts/game_check.py` once the build you develop against is chosen.

The GTK 4 launcher: `python3 launcher/ufc4_launcher.py` from the repo, or `./ufc4.sh` in the
Linux package. Logs go to `~/.local/share/UFC4Native/logs/`.

## Windows

The launcher (`UFC4.exe`) and game are cross-compiled from Linux with llvm-mingw:

```bash
bash scripts/build-windows.sh                 # llvm-mingw cross-compile, LTO on
BB_ALLOW_DIRTY=1 bash scripts/package-windows.sh
# -> dist/UFC4Native-windows-x86_64.zip  (UFC4.exe, bin/, embedded Python, scripts/)
```

Open `UFC4.exe`, pick the `CUSA14209` (or `CUSA14204`) folder with the update beside it, press
**Play**. Preparation happens once in `%LOCALAPPDATA%\UFC4Native`; each session's log goes to
`%LOCALAPPDATA%\UFC4Native\logs\`.

## Key environment variables

The variables and their UFC 3 defaults are documented in the parent project's README
([`docs/ufc3/`](docs/ufc3) holds its write-ups). The ones the UFC 4 profile sets in `run.sh`:

| Variable | Starting default | Why |
|---|---|---|
| `BB_READBACKS` / `BB_READBACK_LINEAR` | 2 / 1 | Precise reads of GPU-written memory. The black fight scene without them was first reported for UFC 4 in shadPS4 (#4375). |
| `BB_GPU_WRITE_TWINS` | 0 | Deadlocks against precise readbacks. |
| `BB_WRITE_STEP` / `BB_WRITE_WINDOW` / `BB_PREUPLOAD` | 1 / 1 / 1 | The UFC 3 fight-FPS path. Set `BB_WRITE_WINDOW=0` first if a fight corrupts memory. |
| `BB_FLIP_RATE` / `BB_VBLANK_HZ` / `BB_FPS_LIMIT` | 0 / 480 / 120 | Unlocked frame rate as on UFC 3. If UFC 4's simulation is tied to its present interval, fall back to `1 / 60`. |
| `BB_Z16S8_AS_D16` | 1 | UFC 3's shadow depth fix; unverified on UFC 4. |
| `BB_SKIP_MOVIES` | 1 | Intro videos replaced by a short black clip. |

`BB_GAME_VARIANT` is `unmapped` for every UFC 4 executable until its image hash is recorded, which
keeps the UFC 3 address-keyed diagnostics (`BB_HEAP_HOOKS`, `BB_HEAP_SITES`, `BB_FREE_CHECK`) off.

## How it works

See the parent project's write-ups in [`docs/ufc3/`](docs/ufc3) and [`docs/bbport/`](docs/bbport)
for the design: native execution of the PS4's x86-64 code, a per-game runtime in place of the PS4
OS, and the PS4 GPU command stream translated to Vulkan. The file-by-file map of what to change for
UFC 4, in order, is [`docs/ufc4/BRINGUP.md`](docs/ufc4/BRINGUP.md).

Comments in `src/` and `gpu/` tagged `ufc3:` or `UFC-NN` describe the finding on UFC 3 that
motivated the code. They are kept as written: they are the evidence for why the code is there.

## Credits

- The [UFC 3 native port](https://github.com/T3CHNOLOG1C/SacredFire) and its contributors, whose
  runtime, renderer, launchers and investigations this tree is built from.
- [SacredFire](https://github.com/T3CHNOLOG1C/SacredFire) and [bbport](https://github.com/deadinside28/bloodborne_pc),
  the native port model.
- [shadPS4](https://github.com/shadps4-emu/shadPS4), renderer and shader recompiler; and the
  [shadPS4 UFC 4 branch](https://github.com/mancelli/shadPS4/releases/tag/ufc4-intel-arc-2026-10-14)
  by mancelli, whose hair, skin, depth-bias and NaN fixes were already backported into this
  renderer for UFC 3.
- [LibAtrac9](https://github.com/Thealexbarney/LibAtrac9), [minimp3](https://github.com/lieff/minimp3),
  [FSR](https://github.com/GPUOpen-Effects/FidelityFX-FSR), Dear ImGui.

## License

GPL-2.0-or-later, like the UFC 3 port, SacredFire, bbport and shadPS4 (see [`LICENSE`](LICENSE)).
