# UFC 4 bring-up plan

What to do, in order, to take this tree from "the UFC 3 port with a UFC 4 profile" to a playable
UFC 4. Each step names the files involved and what counts as done. The UFC 3 port's own record of
the same journey is in [`docs/ufc3/HANDOFF.md`](../ufc3/HANDOFF.md),
[`GROK_HANDOFF.md`](../ufc3/GROK_HANDOFF.md) and the `UFC-NN` notes beside them; the import census
method is in [`docs/sacredfire/01-imports.md`](../sacredfire/01-imports.md).

The game is **EA SPORTS UFC 4**, PS4, `CUSA14209` (Europe) or `CUSA14204` (America), update
**28.00** (the last one, 2024-02). Both are EA Vancouver titles on the same engine family as UFC 3,
which is why the UFC 3 defaults are the starting point; none of them is confirmed for UFC 4.

## 0. What already changed in this tree

| Area | Change |
|---|---|
| `scripts/game_check.py` | Profile `ufc4`: both title ids, version 28.00. `SUPPORTED` (image hashes) is empty: a 28.00 executable is accepted as `variant='unmapped'`. New flags `--title`, `--version`, `--image-hash`. |
| `run.sh` | Default folder `orig/CUSA14209`; title and version come from the game check (patch compiler, shader cache folder). The `ufc4` block carries the UFC 3 defaults with each one annotated as a hypothesis. Prints the image hash while unmapped. |
| `packaging/windows/sacredfire_launcher.c` | Same: title and version from the game check, cache folder by title, UFC 4 names and `UFC4Native` data folder. |
| `scripts/patches.py` | Defaults `CUSA14209` / `28.00`; `GAME_PATCH_KEYS` empty (no bundled patch file). |
| Launchers, packaging, tools, tests | `ufc3_*` → `ufc4_*` names, `UFC4.exe`, `UFC4Native`, tag prefix `ufc4-v`. `UFC4.sh` is made at package time (case-insensitive checkouts cannot hold it beside `ufc4.sh`). |
| `tests/` | `test_game_check.py` rewritten for the new table; `test_patches.py` fixtures retargeted. |
| Untouched | `src/`, `gpu/` (the C and C++ never branch on the game), `docs/ufc3/`, `docs/sacredfire/`, `docs/bbport/`. |

## 1. Prepare a dump and record the executable

Done when: `run.sh` passes the game check, prints the image hash, and `scripts/game_check.py`
has it in `SUPPORTED`.

1. Put the decrypted base and update side by side and merge them:
   `python3 scripts/merge_update.py /path/PS4/CUSA14209` → `CUSA14209-merged`.
2. `python3 scripts/game_check.py /path/PS4/CUSA14209-merged` must print `ufc4`. If it says
   `unreadable`, the dump is not plaintext: `scripts/prepare.py` refuses encrypted or compressed
   SELF segments and this project does not decrypt.
3. `python3 scripts/game_check.py /path/... --image-hash` prints the loaded image's SHA-256.
   Add it to `SUPPORTED` as `'<hash>': 'CUSA14209'` (or `CUSA14204`). From then on the variant
   is `pinned`. Record the base game's 1.00 hash in `OLD_IMAGES` too, so a half-merged folder is
   diagnosed as `wrong_eboot`.
4. Whether the two regions share an executable is unknown. Hash both if you have both; if they
   match, one `SUPPORTED` entry serves both titles.

## 2. Convert the executable and take the import census

Done when: `--list-imports` shows no unresolved import on the boot path, and the loader reaches
the game's entry point.

1. `bash build.sh`, then the scripts `run.sh` runs: `prepare.py`, `link_libc.py`,
   `link_modules.py --modules libc.prx libSceFios2.prx`, `tools/gen_import_names.py`. Check
   that UFC 4's `sce_module/` has those two PRXs; if its libc is a different build, `link_libc.py`'s
   slot offsets (the malloc replacement slots in `gpu/shim/bbport_heap_sites.cpp`, `libc+0xba190`
   on UFC 3) are the first thing that moves.
2. `out/sacredfire out/boot-linked.bin --list-imports --import-names out/import_names.txt`
   prints every import and how it bound: runtime, native module, or trap. Sort the traps by
   library. The UFC 3 census (`docs/sacredfire/01-imports.md`) shows the usual shape: a few
   hundred resolved, a long tail of Np*, dialog and font imports never reached.
3. Boot. Each unresolved import that is actually called stops the run with its name. Implement
   it in the matching `src/runtime_*.c` (the file layout is by PS4 library), as stubs where the
   console service does not exist on PC (Np, trophies, dialogs), as real code where the game
   needs the result (files, threads, save data, AJM audio). Iterate until the first frame is
   submitted.
4. Expect UFC 4 to use newer SDK entry points than UFC 3 (2018 → 2020): new `sceKernel*`
   variants, `sceNpUniversalDataSystem`, `sceGameLiveStreaming`, more `sceSaveData*`. Stub the
   ones that only report status.

### Result of the first real run (2026-10-19, Windows, GTX 1660 SUPER, CUSA14209 28.00)

Steps 1 and 2 passed on a real dump: `prepare.py` read the plaintext `eboot.bin` (691 imports, 44
required modules), `link_libc.py` and `link_modules.py` linked `libc.prx` and `libSceFios2.prx`
(134 native bindings, 647 imports left to the host runtime, 645 of them named), the game started, mounted its
`.big` archives, created its job and render threads, and opened the pad. It then stopped:

```
Guest fault: read access to 0000000000000018 at guest offset 0x137cde4 (SimThread)
rax=0 rdi=0x6d6e6373 (the ASCII bytes "scnm")   exit code 3
```

A null pointer was read at offset `0x18` right after `NetLib` and `SocketRecv` were created. Which
lookup returned null is not known yet. Use `tools/re/fault_context.py out/eboot.elf <log>` to see the
function and the instructions around `0x137cde4` and each backtrace address, then decide whether the
null comes from a runtime call that returned an error (a stub that should have returned data) or from a
file the game expected. The `open(...) -> not found` lines before the crash (`cps.lreq`,
`tableutil.lreq`, `ctloverride.xml`, `settings.cfg`, `*_versioninfo.ini`) are candidates but are not
shown to be the cause.

## 3. First picture

Done when: the EA logo or the title menu renders and responds to the pad.

1. `BB_SKIP_MOVIES=1` (default) replaces the intro videos. If the game blocks waiting on a video
   player state, the AJM/AvPlayer stubs in `src/runtime_ajm.c` and `runtime_services.c` are the
   place to look.
2. A black window with the log showing submits means shaders or readbacks. Try
   `BB_READBACKS=2 BB_READBACK_LINEAR=1` (already default) and read the GPU log for
   "Unimplemented PM4" or shader translation errors. `BB_SKIP_SHADERS=<hash,...>` and
   `BB_SKIP_FILE=<path>` (a live list, re-read every 0.5 s) isolate a shader without a restart.
3. `BB_CAPTURE_ON_FLIP=1` with `BB_CAPTURE_TRIGGER` / `BB_CAPTURE_DIR` writes one frame's draws
   with their textures and shaders. That is the first artifact to keep for any rendering bug.

## 4. A fight

Done when: a Quick Fight plays from the select screen to the result screen without a crash, at the
console's frame rate (`BB_FLIP_RATE=1 BB_VBLANK_HZ=60`) and then unlocked.

1. Start conservative: `BB_WRITE_WINDOW=0 BB_WRITE_STEP=0 BB_PREUPLOAD=0`. If a fight renders,
   the port is correct and the rest is speed.
2. Turn `BB_WRITE_STEP=1` on, then `BB_WRITE_WINDOW=1`, then `BB_PREUPLOAD=1`, one per run. The
   UFC 3 history of each (why it exists, what broke when it was wrong) is in
   `docs/ufc3/UFC-2-write-window-investigation.md`, `UFC-48-write-window-coherence.md`,
   `UFC-49.md`. `BB_WRITE_WINDOW_DIAG=1` prints every window with the site that opened it;
   `BB_WATCH_GPU_WRITE=<addr>` names the GPU bindings on a page.
3. `BB_FRAME_STATS=1` prints the readback site table every few seconds. On UFC 3 the top sites
   were the engine's dynamic-buffer discard lock (`0x64b50` → `0xf4120`) and two store sites
   (`+0x431c4f`, `+0x4219b8`). UFC 4's will be at other addresses but the same shape: find the
   top three, open them in a disassembler, and write down what the engine does there. That note
   is the UFC 4 equivalent of `docs/ufc3/WINDOWS-EXACT-WRITE-WINDOWS.md`.
4. Frame rate. The flip-rate override is generic (`sceVideoOutSetFlipRate` in
   `gpu/shadps4/core/libraries/videoout/video_out.cpp`, `BB_FLIP_RATE`), so it applies without
   finding any UFC 4 address. What is unknown is whether UFC 4's simulation follows real frame
   time as UFC 3's did. Test at `BB_FLIP_RATE=0 BB_VBLANK_HZ=480` with `BB_FPS_LIMIT=60`, then
   `120`: if the fighters speed up, the game ties its step to the present interval and needs a
   patch rather than an override.

## 5. What is UFC 3-specific and how it is kept from misfiring

| Item | Where | Guard | What to do for UFC 4 |
|---|---|---|---|
| Guest code hooks: GPU range allocator return, discard-lock store, heap allocator returns, collector entry, release check, loader `memcpy` call sites | `gpu/shim/bbport_guest_hooks.cpp` | Each `Patch()` compares the code bytes at the address before writing an `int3`; a mismatch skips that hook | Leave off until the UFC 4 sites are found (step 4.3). Then add them under a `ufc4` table and select by `BB_GAME_PROFILE`. |
| Address-keyed diagnostics (`BB_HEAP_HOOKS`, `BB_HEAP_SITES`, `BB_FREE_CHECK`) | `gpu/shim/bbport_toggles.h` `ReferenceBuild()` | On only when `BB_GAME_VARIANT == "5.05"`; UFC 4 reports `pinned` or `unmapped` | Same as above. When UFC 4's addresses are known, extend `ReferenceBuild()` to accept the UFC 4 pinned variant with its own table. |
| libc malloc slots `libc+0xba190…` | `gpu/shim/bbport_heap_sites.cpp` | Only reached through the diagnostics above | Re-derive from UFC 4's `libc.prx` if the heap diagnostics are wanted. |
| Barred write sites learned at run time | `gpu/shadps4/video_core/write_window_sites.h` | Runtime table, empty at start | Nothing: it learns UFC 4's own. |
| Shader patches | `patches/shaders/*.comp` (gitignored, none shipped) | Keyed by translated-shader hash | UFC 3's never load. Write UFC 4's when a shader needs one. |
| Resolution experiments (2K / 4K) | `patches/experiments/ufc45-4k`, `ufc46-1440p` | XML `TitleID` is `CUSA06534`, filtered out by `patches.py` | The launcher's 2K/4K choices therefore change only the window on UFC 4. Re-make the patches against UFC 4's executable, or hide the options. |
| Online server | `tools/ufc4_server.py`, `ufc4_auth.py`, `ufc4_games.py`, `blaze_tdf.py`; client side `src/runtime_net.c` | Only active with `BB_ONLINE_SERVER` | The Blaze/EASO replies, the `GVER '1.14'` game version and the TDF schema were captured from UFC 3. Capture UFC 4's login with `tools/ufc4-login-probe.sh` and `tools/ufc4_tdf_schema.py`, then update the tables. Offline is the only supported mode until then. |
| Save-data details (`CAREERSAVE0` mount flow, 32 KiB blocks, 1 GiB) | `src/runtime_savedata.c` | Generic code paths; the comments record UFC 3's observed behaviour | Verify the career save mounts and that the slot icon loads; UFC 4's save names may differ. |
| Content profile (`--sku full`) | `scripts/content_profile.py` | Reads the dump | Check the DLC / entitlement list UFC 4 asks for. |

## 6. Housekeeping once it runs

- Pin the executable (step 1.3) and set `BB_GAME_VARIANT` handling for the UFC 4 address tables.
- Replace the launcher banner text and the `docs/ufc4/releases/` notes as releases are cut
  (`scripts/release.sh <version>` tags `ufc4-v<version>`).
- Keep the rule the parent projects kept: no game data, generated code, shader dumps or logs
  with the player's paths in git. `.gitignore` already covers `orig/`, `out/`, `user/`,
  `patches/shaders/`, `captures/`.
