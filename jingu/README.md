# dev branch

`windows` from Supermedo/bloodborne_pc with my open pull requests merged, plus what is not meant for upstream. This is the
build I play and the fork's default branch. When a pull request lands, upstream gets merged in here and that difference is gone.

My pull requests: [#151 to #158](https://github.com/Supermedo/bloodborne_pc/pulls?q=is%3Apr+author%3Akanggu12).

Build it like the port itself, see `packaging/windows/README.md`:

    git clone --recursive https://github.com/kanggu12/bloodborne_pc.git
    cd bloodborne_pc
    bash build.sh
    bash packaging/windows/package.sh

Every push to this branch runs `.github/workflows/dev-ci.yml`: the launcher check, the build, the C++ tests that came with the
pull requests and the package, which stays in the run's artifacts for 14 days. It has what a clone can build, see below for
the rest. `gh workflow run dev-ci.yml -f ref=<branch>` runs the same on a contribution branch.

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

The game, third-party mods, the FSR 4 assets (`bash tools/fetch_fsr4_assets.sh` gets them) and NVIDIA's DLSS files
(`nvngx_*.dll`; `bbport_dlss.dll` needs the SDK and MSVC, see `packaging/windows/README.md`). The official release's ZIP has
these too.
