# dev branch

`windows` from Supermedo/bloodborne_pc with my open pull requests merged, plus what is not meant for upstream. This is the
build I play. When a pull request lands, its commits leave this branch.

Build it like the port itself, see `packaging/windows/README.md`:

    git submodule update --init --recursive
    bash build.sh
    bash packaging/windows/package.sh

## Only here

- The game files check fix (same as #137), the PC Settings entries without a name (#146 changes that menu), the commit from the
  `freeze-fixes` branch, and motion target reuse with DLSS (#144 changes that cache). These go when those land.
- Object motion pipelines kept between runs. Held back: on 1.9.7 the motion buffers' addresses can change between runs.
- Render cache counters and its 512 MiB option, off by default.
- "Use existing account" on the Online page, Korean only so far.
- `jingu/patches/Bloodborne_fixes.xml`: two entries for the external patches folder. One goes with the third-party
  `Bloodborne_exit_game.xml`, which is not in this repository, one with the Performance Patch in `patches/Bloodborne.xml`.
- `jingu/tools`: the Korean text mods (`korean_port_texts.py`, needs your own game and the translation mod, nothing from them is
  stored here; set `BB_INSTALL` and `BB_SETTINGS`, or pass `--install` and `--settings`), and tools to read run logs and the
  pipeline cache, which take their paths as arguments. `jingu/tests` skips what needs a game when `BB_INSTALL` has none.

## Settings I run with

`BB_COPY_GPU_BUFFERS=1` and the two-stage GPU pipeline off are the launcher's defaults on this branch. Screen-space reflections
are off (rainbow floors in one DLC area).

## Not in the repository

The game, third-party mods, and NVIDIA's DLSS files (`nvngx_*.dll`; `bbport_dlss.dll` needs the SDK and MSVC, see
`packaging/windows/README.md`).
