#!/usr/bin/env python3
"""The game files this port runs, keyed on the executable's loaded image.

Profile: EA SPORTS UFC 4, PS4 title CUSA14209 (Europe) or CUSA14204 (America), with the 28.00
update merged in (the last one EA shipped, 2024-02). The check compares the loaded executable
image, whose hash is the same whatever tool dumped it (the SELF headers around it differ).
BB_SKIP_GAME_CHECK=1 skips it.

Bring-up state: no UFC 4 image hash has been recorded yet. Until one is, a 28.00 executable of
either title is accepted as `variant='unmapped'`: the runtime and the GPU library run, and the
diagnostics that hook the game by address (BB_HEAP_HOOKS, BB_HEAP_SITES, BB_FREE_CHECK; they know
UFC 3's executable) stay off because BB_GAME_VARIANT is not "5.05". The first run prints the image
hash (`game_check.py GAME_DIR --image-hash`); put it in SUPPORTED to pin the build this port is
developed against, as the UFC 3 port pinned 46c24777...f055b for CUSA06534 1.14.
"""
import hashlib
import os
import sys
from pathlib import Path

# The titles this port knows: TITLE_ID -> profile. `name` is what run.sh and the launchers read
# (BB_GAME_PROFILE); `modules` are the sce_module PRXs link_modules.py links natively; `patches`
# says whether patches.py has a patch file for it. Both regions are the same game; whether their
# executables are byte-identical is unknown until both images are hashed.
TITLES = {
    'CUSA14209': dict(name='ufc4', title='CUSA14209', version='28.00', game='EA SPORTS UFC 4 (Europe)',
                      update='CUSA14209-patch', modules=('libc.prx', 'libSceFios2.prx'), patches=False),
    'CUSA14204': dict(name='ufc4', title='CUSA14204', version='28.00', game='EA SPORTS UFC 4 (America)',
                      update='CUSA14204-patch', modules=('libc.prx', 'libSceFios2.prx'), patches=False),
}
# image sha256 -> TITLE_ID: the 28.00 executables this port was verified against. Empty at
# bring-up; filled from `--image-hash` once a dump has been run.
SUPPORTED = {
}
BY_TITLE = TITLES
# Images that are known NOT to be 28.00 (the base game's 1.00 executable, older updates). With a
# 28.00 param.sfo these mean the update's eboot.bin was not copied in. Empty until recorded.
OLD_IMAGES = {
}
# Other builds of the supported update (none known).
KNOWN_672 = set()
SUPPORTED_TITLE = 'CUSA14209'
SUPPORTED_VERSION = '28.00'
SUPPORTED_IMAGE = None


def image_sha256(game):
    """The SHA-256 of eboot.bin's loaded image (its loadable segments at their addresses)."""
    from prepare import parse_self, span  # same directory
    elf, header, ph, _segments, _missing = parse_self((Path(game) / 'eboot.bin').read_bytes())
    loads = [p for p in ph if p['type'] in (1, 0x61000010)]
    image = bytearray(max(p['vaddr'] + p['memsz'] for p in loads))
    for p in loads:
        image[p['vaddr']:p['vaddr'] + p['filesz']] = span(elf, p['offset'], p['filesz'])
    return hashlib.sha256(image).hexdigest()


def profile(game, image_hash=None):
    """The profile dict for a supported game folder, else None (BB_SKIP_GAME_CHECK=1: a profile
    guessed from param.sfo's TITLE_ID when one exists, so run.sh can still branch).

    variant: 'pinned' for a recorded image, 'unmapped' for a 28.00 executable not recorded yet
    (address-keyed diagnostics off), '?' when the check is skipped."""
    try:
        image_hash = image_hash or image_sha256(game)
    except (OSError, ValueError, IndexError, StopIteration, KeyError):
        image_hash = None
    if image_hash in SUPPORTED:
        return dict(TITLES[SUPPORTED[image_hash]], variant='pinned')
    if image_hash and problem(game, image_hash) is None and os.environ.get('BB_SKIP_GAME_CHECK') != '1':
        info = sfo_info(game)
        return dict(BY_TITLE[info['TITLE_ID']], variant='unmapped', known=image_hash in KNOWN_672)
    if os.environ.get('BB_SKIP_GAME_CHECK') != '1':
        return None
    info = sfo_info(game)
    found = BY_TITLE.get(info.get('TITLE_ID'))
    return dict(found, variant='?') if found else None


def sfo_info(game):
    from prepare import sfo
    try:
        return sfo((Path(game) / 'sce_sys/param.sfo').read_bytes())
    except (OSError, ValueError, IndexError):
        return {}


def problem(game, image_hash=None):
    """None for a supported game, else (kind, title, version): kind is 'missing_update' (base
    game or an older update), 'wrong_eboot' (param.sfo names the supported update, eboot.bin is
    another version), 'other_title' (another edition, region or game) or 'unreadable'."""
    if os.environ.get('BB_SKIP_GAME_CHECK') == '1':
        return None
    from prepare import sfo
    try:
        info = sfo((Path(game) / 'sce_sys/param.sfo').read_bytes())
    except (OSError, ValueError, IndexError):
        info = {}
    title, version = info.get('TITLE_ID', '?'), info.get('APP_VER', '?')
    try:
        image_hash = image_hash or image_sha256(game)
    except (OSError, ValueError, IndexError, StopIteration, KeyError):
        return 'unreadable', title, version
    if image_hash in SUPPORTED:
        return None
    if title not in BY_TITLE:
        return 'other_title', title, version
    if version != BY_TITLE[title]['version']:
        return 'missing_update', title, version
    if image_hash in OLD_IMAGES:
        return 'wrong_eboot', title, version
    return None  # a 28.00 build not recorded yet (unmapped): accepted, see the module docstring


def explain(kind, title, version):
    """What is wrong and what to do, for the log (English)."""
    found = f'Found {title} version {version} (sce_sys/param.sfo).'
    p = BY_TITLE.get(title, BY_TITLE[SUPPORTED_TITLE])
    supported = ', '.join(f"{q['game']} {q['title']} {q['version']}" for q in TITLES.values())
    return {
        'missing_update': f"{found} The port needs the {p['version']} update merged into the game folder: copy "
                          f"everything from the dumped {p['version']} update (e.g. {p['update']}) into the "
                          'game folder, replacing files (eboot.bin and sce_sys too).',
        'wrong_eboot': f"{found} param.sfo is from {p['version']} but eboot.bin is not: copy eboot.bin from "
                       f"the dumped {p['version']} update into the game folder, replacing the old one.",
        'other_title': f'{found} Supported: {supported}; other editions and regions have a different executable.',
        'unreadable': f'{found} eboot.bin could not be read as a decrypted PS4 executable: dump '
                      'the game and its update again.',
    }[kind]


if __name__ == '__main__':
    # game_check.py GAME_DIR: prints the profile name (run.sh branches on it), or fails with the
    # reason. --variant: the executable's standing instead ("pinned", "unmapped" or "?"), for
    # BB_GAME_VARIANT. --title / --version: the profile's title id and update version, for the
    # patch compiler and the cache folder. --image-hash: the loaded image's SHA-256, to record
    # in SUPPORTED.
    flags = {'--variant', '--title', '--version', '--image-hash'}
    args = [a for a in sys.argv[1:] if a not in flags]
    game = Path(args[0]) if args else Path('.')
    if '--image-hash' in sys.argv:
        print(image_sha256(game))
        sys.exit(0)
    found = problem(game)
    if found:
        sys.exit('Unsupported game files: ' + explain(*found))
    p = profile(game)
    if '--variant' in sys.argv:
        print(p.get('variant', '?') if p else '?')
    elif '--title' in sys.argv:
        print(p['title'] if p else SUPPORTED_TITLE)
    elif '--version' in sys.argv:
        print(p['version'] if p else SUPPORTED_VERSION)
    else:
        print(p['name'] if p else 'unknown')
