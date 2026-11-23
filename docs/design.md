# Inhale: design

## 1. Goal and approach

A PC port of *Kirby and the Forgotten Land, Nintendo Switch 2 Edition + Star-Crossed World* by static recompilation,
following Longshot (GPL-3.0-or-later): Python tools lift AArch64 to C, clang compiles it, a native Horizon OS and
NVN2 runtime in C hosts it, and a Vulkan back end replays the NVN2 call stream. No CPU or GPU emulation.

The user supplies their own `.nup` package or extracted `exefs/` and `romfs/`. The repository holds no game files,
keys, or anything made from them, and its documents do not explain how to obtain or dump a game.

Decisions:

- One import of Longshot's tree at commit `31f8d8be`, with identical paths (`PROVENANCE.md`).
- Linux first. Longshot's Windows paths stay in the tree, unverified.
- The project's name through the tree is changed by a script, `scripts/rename_full.py` (S6; until then only the
  player-facing names and the dump variables were changed). It is one rule, so `scripts/sync_upstream.py` puts
  Longshot's files through it before merging them, and Longshot's later changes keep applying.
- This game's code goes in files of its own (`host/kirby_*.c`, `nx2/kirby_*.py`). The other game's code (`oot_*`)
  is gated on that game's build id, not deleted: deleting the host files breaks the link.
- First goal: the first rendered frame (stage S3).

## 2. What the package is

Measured by reading the package in place.

| Item | Value |
|---|---|
| Package | one `.nup`, 15424373958 bytes, 2 titles. Its file name has a non-ASCII character: never hardcode the path |
| Title 0 (code) | `04004d300c5ae001` v65536: `main` 22.9 MB, `sdk`, `subsdk0`, `rtld`, `main.npdm`; its romfs is empty |
| Title 1 (data) | `01004d300c5af001` v0: no exefs, romfs with 11326 files, 11.60 GB (the add-on's levels included) |
| Platform | Native Switch 2: program id prefix 04, no Switch 1 ACID, no `nvdrv` or `vi:u`, DT_RELR in all modules, PAC, LSE and LDAPR in the code, NVN names with DLSS |
| Modules | plain `NSO0` (LZ4), not ZBIC. The build id of `main` starts `395fc326` |
| Size | about 4.9 M instructions in total (Longshot's game: 17.7 M) |
| SDK | 19.3.7 (Longshot's game: 22.2.8). Middleware: G3d, Ui2d, Vfx2, Atk2, movie, NEX 4.6.10, PhysX 5.2.0; `subsdk0` is NVIDIA CUDA |
| Data formats | `.cmp` (a u32 and an LZ4 frame), `.webm` with VP9, `.opus`, `.bfstm`, `.bfsar`, 36 small `.bfsha` |

The package path comes from the `INHALE_NUP` environment variable or from the git-ignored `work/nup.txt`.

## 3. Stages

Each stage has an exit check. Its command output is kept under the git-ignored `work/runs/`.

**S0: the tools accept this package.** The game-free tests have 0 failures; the third-party hashes pass; the package
listing shows both titles; the code signals all say Switch 2; the build id of `main` starts `395fc326`.

**S1: lift everything and prove it.** 100% of the discovered instructions are translated; no indirect branch without
a jump table; every instruction form is bit-exact against Unicorn; every comparable function is identical. From the
import list: the use of `nn::aoc` and `MountAddOnContent`, what `main` imports from `subsdk0`, the VP9 and `nfp`
names, and the symbols no module provides.

**S2: the standalone program boots to graphics start-up.** The lift prints both thread hooks non-zero; the log shows
`boot:` lines for the libc inits, `nnosInitialize`, `nninitStartup`, every `DT_INIT` including `subsdk0`, and
`nnMain`; the game reaches `nvnBootstrapLoader`.

**S3: first frame.** A PNG shows the first logo or loading screen, and the list of NVN procs with no host
implementation that the game called is recorded here.

**S4: title and menus** (outline). Scripted input (`HOS_INPUT_SCRIPT`), one VP9 movie plays, a save round trip.

**S5: gameplay** (outline). The first level without flashes (`RX_VK_FLASH=1`), one add-on map loads, a profile with
`HOS_SAMPLE` and `scripts/prof.py`.

**S6: PC features and packaging.** `nx2/make_game.py` builds a game folder from the package, and the folder's
program starts with no arguments; a hot list and a profile for this game, with their effect measured; the in-game
menu shows no row or text of the other game; one scripted full rename, after which the tests pass and a second run
of the script changes nothing.

## 4. The lessons from MKW, as rules here

Carried over from Longshot's design notes, where each of them cost days in the project before it. They are the checks
that keep the renderer right for another game; `tests/test_doc_anchors.py` keeps the functions that enforce them
pointing here.

1. **Cross-queue `nvnCommandBufferWaitEvent` is honoured.** A game's queues pass stages back and forth with events;
   replaying them in arrival order on one Vulkan queue flashes. `gpu/vk/vk_replay.cpp` `submit_job` replays each
   submission as far as its waits allow, with per-queue state (`RX_VK_EVENT_WAITS=0` turns it off, for A/B only).
   A game whose queues share no event can still count on their order: this game's short compute queue is done on the
   console before its long queue's draws read what it wrote, and arrival order gets that wrong. `host/kirby_queue.c`
   keeps this game's order (section 9, "issue #6, the crystal overlay drops out for a frame").
   *Check early:* log the game's queues and event waits on the first boot.
2. **Nothing the replay reads comes from live guest memory.** Games write per-frame data ahead of the GPU: every
   read is from submit-time captures, and pools are captured from their creation, not their first GPU use
   (`gpu/vk/vk_memory.cpp`, `RX_VK_CAPTURE_POOL_MB`). *Check:* the mirror sync log's live-sync count stays near 0.
3. **Texture and sampler registrations are queued in order with the submits**, never applied out of band.
4. **GPU timestamps drive dynamic resolution.** A game with a resolution controller is fed by timestamp reports: the
   GPU time the replay reports (`gpu/vk/vk_replay.cpp` `NOP_REPORT_COUNTER`, scaled by `RX_VK_TS_SCALE`) must be
   scaled so the controller settles where the PC is, not at its floor. *Check:* the render size it picks over time.
5. **Clears after draws, and draws that sample a target their pass already wrote (or write one an earlier draw of the
   pass sampled), get passes of their own** (`gpu/vk/vk_draw.cpp` `clear_after_draws`, `draw_hazards`). A draw that
   samples a target it writes itself stays in the pass; where a driver answers that read wrongly (AMD's Windows
   driver), the draw is drawn into a copy of the colour target (`gpu/vk/vk_feedback.h`, section 9, "coloured discs on
   a Radeon 780M").
6. **2D views of 3D textures need `VK_EXT_image_2d_view_of_3d`.**
7. **The CPU saturates first.** The game's threads, the replay, captures and pipeline compiles share the cores, and
   extra helper threads have lowered the frame rate before. Thread counts are measured, never raised by default
   (`HOS_VCORES`, `RX_VK_CAPTURE_THREADS`, `HOS_THREAD_TIMES=<seconds>`, the `HOS_SAMPLE` profiler with
   `scripts/prof.py`).

Also inherited: hooks at fixed guest addresses belong to one game and are gated on that game's build id
(`hos_game_is_mkw`, `hos_game_is_oot`). This game's `main` overlaps the other games' address ranges, so an ungated
address compare can fire by coincidence.

## 13. Frame generation's presents, as rules

Carried over from Longshot's design notes as they are at `9af4808f`, under Longshot's number: the renderer's code
points here by it (`// doc: docs/design.md#13-frame-generations-presents-as-rules`, which `tests/test_doc_anchors.py`
checks), and that code is Longshot's. Longshot checked them on 2026-11-16 (Windows 11, RTX 5090, NVIDIA 621.24,
5120x2160 at 165 Hz with G-Sync, DLSS Frame Gen at 3x and 4x, PresentMon 2.3.0); none of it has been measured with
this game. Each fault these rules keep away looked like frame generation turned off: the FPS counter and the display
thread's own counts said the frames were made and on time, and the screen showed the game's frame rate.
`tests/test_framegen_fixed_pace.py` runs the timing functions through a model of the display loop. Longshot's notes
also name its method for rule 1 (its measure skill), which is not carried here.

1. **Frame pacing is measured on the screen, not in the log.** The display thread's `frame interpolation: ... shown on time`
   and `shown apart` counts are its present calls. After the call a present can still wait for the GPU: on 2026-11-16 the
   log had no late frame while PresentMon showed 32% (3x) and 45% (4x) of the frames on the screen under 2 ms. Read
   PresentMon's `DisplayedTime` (the share under 2 ms, its p10 to p90) and, for where a frame waited, `DisplayLatency` against
   `CPUBusy` (the call) and `GPULatency` + `GPUTime` (its GPU work).
2. **A fixed multiplier's set is shown on the game's timeline, in every present mode** (`gpu/vk/vk_framegen.cpp`
   `fixed_on_timeline`, `fixed_dues`, `pace_lead`), whatever Frame pacing says. An immediate (V-Sync Off) swapchain shows
   each present at once: a set presented as it came (its made frames and the game's within a millisecond) showed the
   game's frame and hardly the made ones. Evenly apart (the smoothed frame time over the set) the motion stutters as much
   as the game's frame times vary; on the game's timeline each frame moves as far as its time. Under FIFO (V-Sync On) a VRR
   display shows each present when it comes, one a refresh at most: as they came, a set's frames were a refresh apart and
   its last one waited for the next set (3x at 60 fps on 240 Hz: 4.2, 4.2 and 8.3 ms), so there a frame goes at its time
   but no sooner than a refresh after the one before was given (`fifo_slot`). `RX_VK_FG_TIMELINE=0` gives the old way
   back, for an A/B.
3. **The GPU's delay is fed back only from sets taken as they came** (`pace_delay`, `display_main`'s `as_came`). A set's
   frames are done with the game frame's GPU work, so its times wait for that (`fg.late_ns`). A set whose copies went to the
   GPU late for another reason (no swapchain image free, the display thread busy with the set before) would raise the delay
   by its own lateness, which sends the next set's copies later still: at 4x it ran to a whole game frame.
4. **A set presented ahead needs a frame slot per frame of both sets in flight, and two sets' spare swapchain images**
   (`gpu/vk/vk_replay.cpp` `present_slots_for`, `gpu/vk/vk_main.cpp` `create_swapchain`, `present_ahead_wanted`). Each present
   waits for the copy last made in its slot: with fewer slots than a set's frames, its 4th copy waited for its own first
   copy, and with a slot per frame of one set the next set's copy k waited for the shown set's copy k, each so for all the
   game's work queued before it, while frames of the shown set were due. The slot count is the swapchain's
   (`dev.swap_slots`), set when it is made for its sets, in every present mode; `RX_VK_FG_TIMELINE=0` keeps 3. An app may hold at most
   imageCount - minImageCount acquired images (an NVIDIA surface: 8 images, 6 spare): the next set's copies go as images
   come free (`copy_up_to`), never all or none. The slots are also how many copies may still be on the GPU: what a copy
   reads lives through `kPresentSlotsMax` presents after it (the overlays' staging buffers and old textures,
   `gpu/vk/vk_imgui.cpp` `kFramesLater`; Dear ImGui's vertex buffers, `ImageCount`). At 4, frame generation at 3x and up
   let them go while copies could still read them (a test-only log showed it on an RTX 5090; a likely cause of a
   tester's lost device on an RTX 5080, not reproduced).
5. **A present waits on the queue it is made on.** On the replay's graphics queue it waits behind the game's next frame (3 to
   12 ms at 5120x2160), and a second queue of the graphics family takes turns with it on the GPU. A compute family's queue
   runs beside it (`RX_VK_PRESENT_QUEUE`, `vk_main.cpp` `create_device`): 0.1% of the frames under 2 ms, on the screen 4.9
   to 6.9 ms apart at 3x (p10 to p90), each present's call to the screen 1.3 ms instead of 6.6. It is on by default
   with NVIDIA's driver 621.24 and newer on Windows, where it was measured; Hookshot issue 1161, before the fork (an
   RTX 4090 on NVIDIA's 621.14 had a black screen with it on), was never placed, so older drivers, other drivers and
   Linux keep the replay's queue until they are measured, and `=0` is the way back.
6. **Under FIFO the made frames do not queue** (`gpu/vk/vk_framegen.cpp` `fifo_catch_up`, `fifo_pick`,
   `gpu/vk/vk_reflex.cpp` `fifo_min_interval_us`). FIFO shows one frame a refresh: when the game's frame rate times the
   multiplier passes the refresh, the frames queue in the sets taken ahead and their refresh slots, the game is held
   back, and each game frame reaches the screen later and later (RTX 5090, 165 Hz: 3x, 40 to 51 ms after its hand-over
   before the timeline under FIFO and 65 to 82 ms with it; at 2x under the refresh, 15 and 22 ms; 6x, the game held to
   27.5 game frames a second (45.7 with V-Sync Off) and each game frame presented 138 ms after its hand-over). FIFO's catch-up (`display_main`'s `take`): a set
   whose game frame, its last, would be shown over a refresh after its own time keeps the most frames that bring it
   within one, the ones left out spread over the set so the picture moves in even steps (6x with 3 shown: the 2nd, 4th
   and 6th), and their copies are not made, so no image is held for them. Past the refresh the screen then shows 160 to
   165 frames a second at 165 Hz, each game frame within a refresh of its time, the game at its own rate (the model in
   `tests/test_framegen_fixed_pace.py`: 3x, 4x and 6x at 33 to 60 game frames a second; in the game, 6x: the game at
   52 to 55 frames a second and each game frame on screen 46 to 52 ms after its hand-over). At most all but one made frame is left out:
   at 2x the one made frame stays, as a set of one frame is not presented ahead. The GPU's delay is fed back against
   the set's first frame whichever frames are shown: a copy takes as long for any of them, and against the first one
   shown 6x ran the delay down to 0, so its frames came due before their copies and a frame more a set was left out.
   For a G-SYNC or
   FreeSync display, `RX_VK_FG_FIFO_CAP=1` has NVIDIA Reflex's sleep, while frames are made, hold the game to the
   multiplier's share of refresh - refresh²/3600 frames a second (157 at 165 Hz: 52.5 game frames at 3x), as NVIDIA's
   own Reflex keeps a G-SYNC display under the refresh with V-Sync (with the first catch-up, 3x on 165 Hz: 29 ms on
   screen with a 60 cap against main's 45 to 51 before the timeline under FIFO, and 39 uncapped against 33 to 40). It is off by default: a
   display of a fixed refresh then has refreshes without a new frame (7 a second at 165 Hz), and the game cannot tell
   the two apart.

## 5. Risks, ranked, with the stage that settles each

1. The data lives in a second, romfs-only title: certain to need work. S1 (imports), S2 (the first `fs:` lines).
2. SDK 19.3.7 against a runtime fitted to SDK 21 and 22: thread layout, hooked names that moved, NVN version. S1 to S3.
3. `subsdk0` is NVIDIA CUDA: its init runs at boot, and it may hold instruction forms the lifter lacks. S1, S2.
   Fallback: make its init fail so that PhysX stays on the CPU (untested).
4. DLSS and acceleration-structure NVN procs have no host implementation; harmless unless called. S3, settled by S5.
5. Shader lowering for this engine's programs. S3.
6. The VP9 movie function names may differ in SDK 19; `HOS_NO_MOVIES=1` goes around them until S4.
7. Engine script or dispatch code that makes indirect branches without tables. S1.
8. NEX and the network services answered by stubs that return 0. S4.
9. `mii`, `nfc`, `ngc`, `nim`, `notif`, `ectx` have neither hooks nor stubs. S4 or S5.

## 6. Reused unchanged from Longshot

`nx2/nso2.py`, `image.py`, `insn.py`, `lift_fixes.py`, `poll.py`, `rtgen.py`, `standalone.py`, `build.py`,
`census.py`, `imports.py`, `test_insn.py`, `test_leaf.py`; `third_party/a64-kit`; `tests/run_all.py`;
`scripts/check_third_party.py`, `scripts/inhale_ctl.py`, `scripts/prof.py`; all of `gpu/vk`; `host/nn_video.c`,
`nn_codec.c`, `nn_audio.c`, `nn_fs.c`, `hos_svc.c`, `control.c`.

## 7. Not verified yet

- The 3D frame at the output size (section 9, "issue #1, dynamic resolution") on a 4K screen, in a window or full
  screen, and at an output between 2560 x 1440 and 3840 x 2160. NVIDIA and Windows were checked headless only, with the
  size in the ini as the menu saves it ("The menu's 4K" in that section).
- The game's dynamic resolution off by default (the same section, "Off by default"): the fixed 2560 x 1440 scene on a
  weak GPU at a small output (a 1080p monitor), and the handheld profile as that PC's way out, chosen in the menu. Why
  handheld drew at a docked level's size in one run.
- What `subsdk0` (CUDA) does after its init: its `DT_INIT` runs, but no `cu*` call has been seen yet.
- The NVN API version this game's `sdk` expects, and the SDK 19 thread layout beyond a clean start of the game's threads.
- The first start's shader preparation (section 9, "issue #1"), on another GPU than the RX 7900 XTX: NVIDIA, Windows,
  and the issue's RTX 5080 at 4K. How many of a player's pipelines the shipped lists hold at other settings than the two
  lists' (the blend state and vertex strides differ, not the shaders).
- The depth mode fix (section 9, "the picture that stays wrong until `cache/` is deleted") in a window, on NVIDIA and on
  Windows, and why deleting `cache/` cured the picture for the reporter.
- Why the presents sometimes drop to 7 a second while the movie player starts (S4, section 9): seen twice, not explained.
- One of three runs sampled with `HOS_SAMPLE_ALL` (`work/runs/s5x/c4.txt`) fell below 6 presents a second at the first zone
  change and stayed there; no unsampled run did. The sampler unwinds inside a signal handler: suspected, not proven.
- The Star-Crossed World stages (`DlcLevelN`) but the first, which a player's save reached on 2026-11-20 (section 9,
  "issue #6").
- Issue #6's fix as committed, played: the runs that showed it were of a test build that also kept the virtual core
  during a hand-over (section 9, "issue #6", the open point).
- The fix of the 10 s stall at the start (section 9, "issue #6", "The stall at the start, fixed"): headless only, not
  played; and the lower waiter's case it does not cover (same place).
- The Windows build, on Windows 11 with Visual Studio Build Tools 2022, LLVM's clang and FFmpeg from vcpkg
  (`x64-windows-static-md`, in a CPM-style folder named by `RX_CPM`): `tests/run_all.py` passes (3 checks that build the
  lifter fail only with MinGW's clang first on `PATH`; they pass with the Visual Studio environment), `nx2/build.py
  --standalone` links `inhale.exe` and `inhale_vk.dll`, and the game runs through the boot and the first scene on an
  RTX 2080 SUPER at 60 presents a second, with nothing in the log but the usual unimplemented imports. Not yet looked at
  on screen: which scene that is, input, audio, the movie. The llvm-mingw route (`LONGSHOT_MINGW`) builds and runs too
  (section 9, "the release packages").
  Slow in a window over Remote Desktop (21 to 25 presents a second, the main thread blocked 3.7 s of every 5 s in GPU sync
  waits while the GPU was busy 4 ms a frame): the same build run headless over ssh gives 60.0 with 0.1 s blocked. The
  remote display adapter paces FIFO presents (V-Sync On); the registry value `DWMFRAMEINTERVAL` = 15 (the RDP frame
  interval, as the user set it) fixed it: 60 in the window afterwards (the player's report). Not a defect of the host or the renderer.
- Rumble in the game with a pad in hand (section 9, "issue #2"): the SDK's file readers run and read the game's
  files, but no run here made the game play one. Why the game's script switches a player's rumble off 2.3 s after the
  last scripted press.
- `make_game.py`'s `--romfs-from` and its folder input (`--game <folder>`, `--exefs` with `--aoc`) on a real dump:
  covered by tests with made-up files only. The package path and `--update` were run for real (section 9, S6).
- Whether the profiles add anything to the hot list: the three measured runs differ more among themselves than from
  the hot list's (section 9, S6).
- AMD's Windows driver and an integrated GPU (section 9, "coloured discs on a Radeon 780M"): checked on a Radeon 780M
  for the title screen and the first stage's walk from the beach into the jungle, headless over ssh, and no further.
  Not checked: the fix in a window in the player's hands, other stages, AMD's older Windows driver branch (RX 5000
  and RX 6000) and AMDVLK, what the two copies cost at other scene sizes, and the two programs that sample the depth
  target they write (`cb8d129794535ac7`, `e169c16f0c368e7b`), which stay as they are.
- The Shadow resolution row for this game (section 9, "issue #7, shadow resolution"): checked in the first stage's
  walk on an RX 7900 XTX, docked, and handheld for the size only. Not checked: NVIDIA, Windows, later worlds and
  their stages (whether one sets a size of its own), shimmer as the camera moves, the menu row in a player's hands,
  and its restart in play: the "After restart" tag and the question on closing the menu (game-free test only).
- Issue #14's fix on screen (section 9, "issue #14"): the Star-Crossed World stage bubble with the face's icon, and the
  arena entry, the hero panel and the ball minigame. Checked only that the game reads the four archives other than the
  DLC marker's from the faces' files.
- The menu rows kept for this game that were not tried in play: Mouse camera, Button prompts, Walk mode, and Output
  resolution on a screen that is not 16:9. The microphone rows are hidden for this game instead: it imports the SDK's
  input-stream API but no game code calls it (section 9, "the microphone rows").

## 8. Status

| Stage | State | Notes |
|---|---|---|
| Import | done 2026-11-16 | Longshot `31f8d8be`; two commits |
| S0 | done 2026-11-16 | tests 575 passed, 0 failed (522 without the system's Vulkan and SPIR-V headers); six signals say Switch 2 |
| S1 | done 2026-11-16 | 4801605 instructions, 100% translated; instruction and function tests pass; one unbounded jump table, in `rtld` |
| S2 | done 2026-11-17 | every `boot:` line, `nnMain`, NVN device, pools, 3840x2160 window textures; the game then loads from `aoc1:` |
| S3 | done 2026-11-17 | 60 presents a second; the online and difficulty screens draw; no NVN proc without a host implementation was called |
| S4 | done 2026-11-17 | scripted input; the opening movie plays (2296 pictures, with its sound); the game's sound plays; a save is read back at the title screen |
| S5 | done 2026-11-17 | the first stage at 60 presents a second, the beach into the jungle with 0 flashes (`RX_VK_PIPE_SKIP=0` by default); the hint movies play; all data loads from `aoc1:`; a profile; tests 575 passed |
| S6 | done 2026-11-17 | `make_game.py` from the package to a folder that starts with no arguments (60 presents a second); a hot list (CPU time down 10%) and profiles; the menu without the other game's rows; the name changed by `scripts/rename_full.py`; tests 575 passed |

Work after the two import commits is in five commits: the rename alone (what `scripts/rename_full.py --write` does
to the tree before it, with the script, and nothing else); the fork's documents and the files changed at import
(`PROVENANCE.md`); the stages S0 to S6; the sync script; the notes for coding agents.

## 10. The release packages

Three downloads, made by `.github/workflows/release.yml` on Linux runners (a `v*` tag: a release; a push to `main` or
Run workflow: the rolling `nightly` prerelease, with `SHA256SUMS`, unsigned):

- `Inhale-x86_64.AppImage` (`packaging/linux/`, built in an Ubuntu 22.04 container by `packaging/linux/docker.sh`).
  The container's image is built once per `packaging/linux/Dockerfile` by `.github/workflows/pkg-image.yml` and pushed
  to `ghcr.io/<owner>/inhale-pkg-build:<first 16 hex digits of the Dockerfile's SHA-256>`; the release jobs pull that
  tag, so a release does not reach Launchpad (the toolchain PPA, which failed three release runs in a row) or the
  Ubuntu mirrors. A Dockerfile with no image pushed yet is built by the release run itself.
  Its AppDir: `usr/python` (CPython 3.12 with tkinter and `requirements.txt`), `usr/lib/inhale/{llvm,sysroot,ffmpeg,
  sdl2,cpm}` (clang and lld, the glibc 2.35 sysroot, static FFmpeg with dav1d, `libSDL2-2.0.so.0`, the Vulkan, SPIR-V
  and VMA headers), `usr/share/inhale` (the tracked sources, `VERSION`, `liba64emit.so`, zbic, the prebuilt
  third-party objects, `packaging/gui`, `licenses/`). `AppRun` starts the window, `--cli` runs `make_game.py` and
  `--play` the game, with the tools' variables (`EMSDK`, `INHALE_SYSROOT`, `INHALE_FFMPEG`, `INHALE_SDL2`, `RX_CPM`)
  set as `packaging/gui/tools_env.py` sets them for the window's build.
- `Inhale-Setup-x64.exe` (`packaging/windows/`, cross-built on Linux: `packaging/linux/docker.sh windows`). NSIS,
  per user, into `%LOCALAPPDATA%\Programs\Inhale`: the sources beside `llvm-mingw\` (its Windows release, which
  `make_game.py` `bundled_mingw()` finds), `python\` (with tkinter), `cpm\` (the headers, and FFmpeg and dav1d built
  with llvm-mingw: FFmpeg's libraries named `<name>.lib`, as `nx2/build.py` links them), `third_party\sdl2\SDL2.dll`
  (sdl2-compat) and `SDL3.dll`, `a64emit.dll` and the third-party objects prebuilt with `RX_TARGET=windows`, `gui\`.
  The uninstaller removes only those names, so a folder chosen by hand keeps its other files; the game folders and
  saves stay, and it asks about the work folder.
- `Inhale-Windows-x64.zip`: the installer's folder, zipped with its contents at the top (no installer, nothing written
  outside the folder), for RecompLauncher. `Inhale.exe` at its top (`packaging/windows/inhale_launch.c`) is the Windows
  `AppRun`: no argument starts the window as the installer's shortcut does, `--cli` runs `make_game.py` with the
  variables `tools_env.build_env` sets (`LONGSHOT_MINGW`, `RX_CPM`, `PYTHONUTF8`, `PYTHONUNBUFFERED`), `--play <dir>`
  starts `<dir>\inhale.exe` in `<dir>`; both wait and return the child's exit code. The installer carries it too.

**RecompLauncher.** `packaging/recomplauncher.json` (format 1) sits at the AppImage's top and the zip's. `prepare` runs
`--cli --prepare --game {game} --out {install}/Inhale` (`make_game.py --prepare`: its `progress` and `error` lines) and
`start` runs `--play {install}/Inhale`, so the game, its `inhale_options.ini` (the `config`) and Windows' `user/` saves
are in the launcher's install folder (upstream's RecompLauncher issue 215: a build into `~/Games` missed the drive the
player chose); Linux's saves are `{local}/inhale`. The check is `nup_build_id` 395fc326, `make_game.py`'s `BUILD_ID`.
The packages write it with `packaging/stamp_manifest.py`, which sets `prepare.version` to the release (`$VERSION`):
the launcher runs `prepare` again for a player already set up only when that field changes, not for a new release, so
with a fixed `"1"` the v0.3.0 update kept playing the v0.2.0 build. Its ten settings are rows this game's menu shows (none of `is_oot_row`'s); Frame generation offers Off and Auto only
(the fixed multipliers' freezes, section 9, "played by hand past the first boss"). No `prepare.options`: DLSS, FSR 4
and XeSS reach this game only through the Upscaler row and Frame generation by, both hidden for it. No `dumps`: Redump
and No-Intro list no `.nup`. `tests/test_recomplauncher_inhale.py` checks all of this against the sources.

Everything downloaded is in `packaging/pins.txt` (name, version, system, URL, SHA-256), fetched and checked by
`packaging/fetch.py` into `work/pkg/dl`; the versions are upstream's at `9af4808f` (LLVM 23.1.5, llvm-mingw 20261104,
Python 3.12.16, FFmpeg 9.0.2, dav1d 1.5.4, SDL 2.32.10 / 3.4.20 / sdl2-compat 2.32.74, Vulkan-Headers v1.4.345,
SPIRV-Headers vulkan-sdk-1.4.341.0, VMA v3.3.0). The window (`packaging/gui/inhale_builder.py`) runs
`python -I nx2/make_game.py` and reads its `@@` lines (`packaging/gui/protocol.py`); nothing in `nx2/` changed for it.

The shipped pipeline state lists (`assets/pipeline_states/`, section 9, "issue #1") are in both packages' sources
(`assets` in the `git ls-files` line of `packaging/linux/appimage.sh` and `packaging/windows/build.sh`; the
uninstaller removes `$INSTDIR\assets`), where `make_game.py` `ship_state_list` reads them; `tests/test_packaging_scripts.py`
checks both scripts.

The hot list (section 9, S6: CPU time 10% less) is tracked as `packaging/profiles/hot_funcs.txt`, 301 function names,
and both packages put it in their `work/`, where `make_game.py` takes it; CI's packages have it too. The profiles
(`work/inhale_pieces.prof`, `work/inhale_vk.profdata`) and `work/image/chunks.txt` stay untracked, since their gain over
the hot list is not shown (section 7): a package built on a PC that has them carries them, one built by CI does not.

## 9. Findings

### 2026-11-16, S0

- `nx2/nup.py` listed a title without an exefs by indexing dir `0xffffffff`. `walk` now yields nothing for a tree a
  title does not have; the code title is the newest title with an exefs; a title with a romfs and no exefs is a data
  title and unpacks to `<dump>/aoc/<title id>/romfs` (`nx2/kit.py` `data_romfs` finds it).
- The package's metadata has no name record: `nx2/game_title.py` names the title by id.
- `nx2/kit.py` reads `INHALE_WORK`, `INHALE_DUMP`, `INHALE_EXEFS`, `INHALE_ROMFS` first, then the `OOT_` names.
  Each name is written out where it is read, because `tests/test_lift_cache.py` finds the lift's variables that way.

### 2026-11-16, S1

    $PY nx2/lift.py                      85548 functions, 4801605 instructions, 100.0000% translated, 13 s
    $PY nx2/census.py --nx2              untranslated words are udf and padding only, in every module
    $PY nx2/test_insn.py --per 6 --states 12      583 forms, 34536 cases, 0 failures
    $PY nx2/test_leaf.py --count 3000 --states 4  1363 functions, 3229 cases, 0 differences
    $PY nx2/test_leaf.py --calls                  1695 call trees, 4748 cases, 0 differences

- One indirect branch without a table: `rtld+0x220`, the tag switch of rtld's dynamic-section parser. The standalone
  program does not run rtld (the image is relocated at lift time), so it is not reached.
- `subsdk0` has no instruction form the lifter lacks.
- Both test harnesses were written for Windows (`VirtualAlloc`, structured exceptions). `nx2/test_leaf.py` now also
  builds on Linux (`mmap`, signals); `nx2/test_insn.py` replaces the vendored harness's two Windows lines at run time.
- The other game's lift hooks (`oot_wide`, `oot_fov`, `oot_shadow`, `oot_jitter`) are installed only for its build id
  (`nx2/lift.py`). `nx2/oot_patches.py` is the empty stand-in, so `nx2/chunks.py` needed no gate.
- Imports: `main` takes 899 symbols from `sdk` and 49 from `subsdk0`, all of them CUDA driver calls (`cuInit`,
  `cuCtxCreate_v2`, `cuMemAlloc_v2`, `cuLaunchKernel`, ...): PhysX's GPU path. `subsdk0` takes `NvRmGpu*`, `NvOs*`
  from `sdk`. No module provides eight `glslc*` names (weak, the online shader compiler).
- Add-on content: `nn::aoc::CountAddOnContent`, `ListAddOnContent`, `nn::fs::MountAddOnContent`,
  `QueryMountAddOnContentCacheSize`, beside `MountRom`.
- Movies: `nn::codec` `Vp9Decoder` names of SDK 19 (`InitializeVp9Decoder` with and without a work buffer,
  `RegisterVp9DecoderBuffer`, `SubmitVp9DecoderInputBuffer`, `AcquireVp9DecoderOutputBuffer`, ...). `host/nn_video.c`
  has SDK 22's names (`...ByRemoteMemory`, `...ByTransferMemory`): 21 of its functions match no symbol here. S4.
- `nn::nfp`: 11 names, all answered by stubs.

### 2026-11-17, S2

Run: `work/sa/build/inhale work/sa/image/image.bin --romfs <code title's romfs, may be empty> --aoc work/dump/aoc
--user work/user`, with `HOS_HEADLESS=1 HOS_AUDIO=0 HOS_NO_MOVIES=1`. The whole build takes about 75 s (20 jobs).

What stopped the boot, in order, and the fix:

1. `nn::mem::StandardAllocator::Initialize(NULL, 20 GB)` aborted in `nninitStartup`: the SDK's
   `VammManager::IsVirtualAddressMemoryEnabled` asks `svcGetInfo(16)` (system resource size) and takes 0 as "off".
   `main.npdm` says 0x1000000. `gen/hos_image.c` now carries it (`hos_system_resource_size`) and `host/hos_svc.c`
   answers it.
2. A static initializer of `main` uses `std::random_device`, which ends in
   `nn::crypto::GenerateCryptographicallyRandomBytes` and the `csrng` service. HLE in `host/kirby_hle.c`.
3. `nn::audio::IsValidAudioRendererParameter` was a stub answering 0: abort. HLE answers 1.
4. The game waits until `nn::audio::GetMemoryPoolState` says Attached (1). `host/nn_audio.c` now tracks attach and
   detach requests and answers it.
5. `nn::hid::GetTouchScreenState<16>` (the singular form) aborted in the lifted SDK. HLE forwards to the plural one.

Settled:

- The data title is add-on content index 1. The game mounts the code title's (empty) RomFS as `content:` and the data
  as `aoc1:`, and reads everything from `aoc1:`. `host/nn_aoc.c` lists the titles under `--aoc` (or `HOS_AOC`) and
  mounts them.
- Both thread hooks are found (`0x84e0ac38`, `0x84e0ac40`) and the game's threads start with them.
- The other game's return-address compares in `host/hos_thread.c` and `host/nvn_native.c` are behind
  `hos_game_is_oot()`. `host/hos_main.c` still holds that game's debug and cheat code with fixed addresses; it runs
  only from its menu and the control bridge, and is to be gated before S4.

Open, seen in the last boot (40 s, no abort, no frame):

- 184 imports are answered by stubs. Called so far: `nn::hid::GetNpadState` (five state types),
  `GetSupportedNpadStyleSet`, `GetNpadJoyHoldType`, `GetSixAxisSensorState`, `EnableVibrationNxCompatibleMode`;
  `nn::oe::GetDefaultDisplayResolution` and its change event; `nn::audio::SetDownMixParameterEnabled`;
  `nn::codec::GetOpusDecoderWorkBufferSize`; `nn::nfp::Initialize`, `AttachAvailabilityChangeEvent`, `ListDevices`;
  `nn::nifm`, `nn::bcat`, `nn::prepo`, `nn::socket` `Initialize`; `nn::pl::GetBuiltInFontDataSet`;
  `nn::ro::ProtectRelro`. Not yet called but needed for sound: the `AudioOut` family, `GetVoicePlayState`,
  `ExecuteAudioRendererRendering`, the delay effect, the resampler, the Opus and AAC decoders.
- After NVN start-up (device, three memory pools, sampler and texture pools, two syncs, two 3840x2160 window
  textures, window, queue) the main thread issues no submit and no present. Settled in S3.
- The process ignores SIGTERM while running; runs are ended with SIGKILL.

### 2026-11-17, S3

Evidence: `work/runs/s3/first_frame.png` (present 300 of a headless run, `RX_VK_SHOTS=<dir> RX_VK_SHOT_EVERY=100`): the
"connect online" dialog. `work/runs/s3/first_frames_sheet.png` is from before fixes 3 and 4 (presents 15 to 360). Log
with `--trace`: `work/runs/s3/origin1.txt`.

What stopped the first frame, and the fix:

1. The main thread slept in a loop in `main+0x65b460`: it asks `nn::pl::GetBuiltInFontDataSet` for the console's six
   built-in fonts every 100 ms until the answer is true, and the stub answered 0. Found with a backtrace of every
   thread (`work/gdbbt.sh <name> [seconds]`: the run under gdb, interrupted; `HOS_SAMPLE` is Windows only). The HLE in
   `host/kirby_hle.c` answers with the bundled Libertinus Sans for every type; `nx2/build.py` compiles
   `nx2/ui_fonts.py`'s file into the program too. The entry layout (0x18 bytes: type, flag, address at 8, size at 16)
   is read from the lifted `sdk+0x4fc650`.
2. `nn::fs::CommitSaveData("save")`, SDK 19's name of `nn::fs::Commit`, aborted in the lifted SDK after the game wrote
   its first `save:/system`, `file0` to `file2`. HLE answers 0.

3. Every text was upside down, pane by pane. The game draws each text into a small texture of its own and then draws
   that texture. It never calls `nvnDeviceSetWindowOriginMode`, so its origin is NVN's default, the lower left, where
   +y of clip space is the higher row; the back end flipped every viewport, as the upper-left origin of the two games
   before needs. Found with a frame dump (`RX_VK_DUMP=<present>`). The host now tells the back end the mode
   (`MkwVkHost.origin_lower_left`, API version 26): with a lower-left origin `gpu/vk/vk_draw.cpp` leaves the viewport
   as it is and swaps the front face, and `gpu/vk/vk_replay.cpp` `blit_crop_to_rect` presents bottom row first.
   Not covered: the presents that do not go through that blit (frame generation, the temporal upscalers), and the
   frame dump's pictures, which show row 0 on top.
4. `nn::hid::GetNpadState` (five styles) and `GetSixAxisSensorState`, the singular forms, were stubs that left the
   game's state unwritten: the game answered its first dialogs by itself. HLEs forward to the plural forms.

Settled:

- NVN procs with no host implementation that the game called: none (no `is not implemented` line in 60 s).
- Shader lowering: the 2D screens draw with no renderer complaint in the log. 3D scenes are not reached yet.
- Queues: the game submits to two queues, three submits a frame; presents hold 60.0 a second headless.
- The live-sync count of the mirror log stays 0 (rule 2 of section 4).

Open, for S4:

- `nn::hid::GetSupportedNpadStyleSet` and `GetNpadJoyHoldType` are still stubs.
- Seen before fix 4, when the dialogs answered themselves: after the difficulty screen the game loads the first stage
  (`gfx/Step`, `lyt/Pause/StageTitle/Lv1`) and the frames are black, 3 draws and 1 dispatch each. Stubs called on
  the way: `nn::web::ShowOfflineHtmlPage` (once, right after the first screen), `nn::movie::Initialize`,
  `nn::audio::GetVoiceNodeId`, `GetVoicePlayState`, the delay effect's setters,
  `nn::vi::QueryDisplayBufferMaxResolution`. The opening movie is the first suspect (`HOS_NO_MOVIES=1` was set, and
  `nn::movie` has no host implementation).

### 2026-11-17, S4

Run: `HOS_INPUT_FRAME_CLOCK=1 HOS_NO_MOVIES=0 HOS_INPUT_SCRIPT="10:LEFT,12:A,16:A,20:A,24:A" HOS_VIDEO_LOG=1
RX_VK_SHOTS=<dir> RX_VK_SHOT_EVERY=240 RUNDIR=s4 work/boot.sh <name> 90` (`work/boot.sh` keeps `HOS_NO_MOVIES=1` unless
it is given; the pictures' folder must exist). With `HOS_INPUT_FRAME_CLOCK=1` the script's seconds are 60 presents:
the start takes 3 to 15 s of wall clock from run to run, and a wall-clock script then presses `LEFT` before the first
dialog takes input (the game stays on "connect online" and calls `nn::web::ShowOfflineHtmlPage`). The same variables
work with `work/gdbbt.sh` (`RUNDIR`, `HOS_NO_MOVIES`). Last log: `work/runs/s4/mov9.txt`.

Done:

- Scripted input works: "Do Not Use", the notice after it, the difficulty screen. The game then starts its movie
  player (threads `MoviePlayerMain`, `MovieEventHandler`, `MediaExtractorWorker`, `VideoDecoderThread`,
  `AudioDecoderThread`) on `aoc1:/mov/EventMovie/Opening.webm`. With `HOS_NO_MOVIES=1` the file is "not found" and
  the frames stay black: that was the black after the difficulty screen.
- The lifted `nn::movie::MediaExtractor` demuxes the WebM by itself (class members stay lifted; only the free
  functions `nn::movie::Initialize`, `IsInitialized`, `Finalize` are stubs, and the game goes on with them).
- The VP9 decoder's SDK 19 names are on `host/nn_video.c`'s functions (`host/kirby_hle.c`): `MakeDecodeImagePreference`
  and `InitializeDecoderImagePool` with a `CodecMode`, `CalculateVp9DecoderWorkBuffer`, `InitializeVp9Decoder` with a
  work buffer, `GetVp9DecoderSubmissionReadyEvent` with an out pointer, `GetVp9DecoderOutputBufferProperties` with a
  colour space (its index is on the stack). Before, the first `AcquireVp9DecoderOutputBuffer` answered an error and
  the game aborted. Now: `video: VP9 decoder ready on vp9`. `work/plt.py <addr>` names the import behind a PLT stub
  of `main`.
- `tests/test_audio_output_devices.py`, `tests/test_microphone_test_gain.py` and `tests/present_source_crop_test.cpp`
  follow API version 26 and the new host callback.
- The movie player is the game's own code in `main` (0x8088d000 to 0x80895000, decoders' wrappers at 0x80450000 to
  0x80459000), not the SDK's player. Four things stopped it, in the order found:
  1. `nn::os::TimedReceiveMessageQueue` had no host function: the lifted SDK body ran on a queue the host had made and
     slept forever in `InternalCriticalSection::Enter` (`MovieVideoInputReadThread`, `MovieAudioInputReadThread`).
     Now in `host/nn_os_sync.c`. An audit of the SDK's `nn::os` exports against the host's functions (577 exports,
     140 with a host function; `main` imports 116) found one more of this kind that `main` imports,
     `BroadcastConditionVariable`: added too (wakes every waiter), not seen called in these runs.
  2. The `nn::audio::AudioOut` family (15 imports) was stubs: channel count, rate and sample size read 0, the first
     `AppendAudioOutBuffer` answered false and the player went on without sound. Now in `host/nn_audio.c`: one
     output, 48 kHz, 16 bit, 2 or 6 channels; the renderer thread plays the queue (240 frames each 5 ms, with the
     device off too) and signals the game's event for each buffer played. The game queues four buffers of 10 ms and
     refills one for each signal, on `MovieEventHandler`. It never asks for a played sample count.
  3. `host/nn_video.c` opened libavcodec's VP9 decoder with frame threads, which give a picture back only once three
     more are in; this player submits one picture and waits for it. VP9 now decodes with tile threads: the first
     picture comes back (`video: acquire 3: 1920x1080 pts 0`).
  4. The decoder's submission-ready event was signalled once, when made, and again only after the decoder had been
     full. This player clears the event each time it wakes and submits one picture: it never submitted a second.
     `input_room` now signals at every call with room.
- The opening movie plays to its end (`work/runs/s4/mov12.txt`, 240 s): 2296 pictures of 1920x1080 in 76.5 s, 1.9 ms
  to decode each, none skipped, 0.07 s from the movie's clock at the end, then `Stop`; 60.0 presents a second all
  through. Pictures: `work/runs/s4/movie_sheet.png` (colours and orientation right). Sound: `HOS_AUDIO_DUMP=<wav>`
  works with `HOS_AUDIO=0`; the dump has the movie's sound for those 76 s (peaks about 15000 of 32767).
- After the movie the game writes `save:/system` and `save:/file0` and starts the first stage: a 3D scene, drawn at
  60 presents a second (`work/runs/s4/after_movie_sheet.png`).
- The present stall of the first S4 runs (7 presents a second, the main thread's `nvnSyncWait` 70 to 140 ms each,
  each wait satisfied, GPU time 0.2 ms a frame) is not explained. Runs with the movie started and no picture decoded:
  it came in `mov2` and `mov7`, not in `mov4`, `mov5` or under gdb (`stall1`). With the first picture decoded (`mov9`)
  the rate dipped twice for a few seconds and came back to 60. The wait is in `gpu/vk/vk_replay.cpp` `wait`.

- The game's own sound was silent (0 in the dump, before and after the movie) though its voices were made:
  `nn::audio::GetVoicePlayState` was a stub that answered 0, "started", and the sound engine starts only the voices
  it reads as stopped, so it never called `AppendWaveBuffer` or `SetVoicePlayState` (0 calls with `HOS_HLE_STATS=1`).
  The host function answers the state the game set last. Now `HOS_AUDIO_STATS=1` shows 2 to 6 voices playing and
  the dump has sound on the title screen and in the stage (`work/runs/s4/snd2.txt`, `snd2.wav`). Not listened to.
- Save round trip: after the movie the game wrote `save:/system` and `save:/file0`; the next boot shows the title
  screen with "File 1, Continue, Select File", and `A` there enters the stage with its HUD
  (`work/runs/s4/second_boot_sheet.png`). A first boot (no save) has no title screen: its three dialogs, the movie,
  the stage. With a save the script is `HOS_INPUT_SCRIPT="10:A"`; for a first boot again, move `work/user/save` away.
- Tests after these changes: 575 passed, 0 failed (`work/runs/s4/tests3.txt`).

Left for later stages:

- The first stage is drawn under a cyan wash, the lower half plain cyan (`work/runs/s4/after_movie_sheet.png`,
  `second_boot_sheet.png`): S5's first item.
- The presents' drop to 7 a second while the movie player starts (above): not explained, not seen since the movie
  plays.
- Not adapted, not called so far: `InitializeVp9Decoder` without a work buffer,
  `GetDecoderImagePoolNativeImageHandle`, `nn::codec::sdk::MakeDecodeImagePreferenceForCompat`.
- Stubs called and unanswered: `nn::web::ShowOfflineHtmlPage` (when "Use" is chosen on the first screen),
  `nn::movie::Initialize`, `IsInitialized`, `Finalize`, `nn::audio::SetDownMixParameterEnabled`, `AddDelay` and the
  delay's setters (the effect is not heard), `GetVoiceNodeId`, `nn::codec::GetOpusDecoderWorkBufferSize`,
  `nn::vi::QueryDisplayBufferMaxResolution`, `nn::hid::GetSupportedNpadStyleSet`, `GetNpadJoyHoldType`,
  `EnableVibrationNxCompatibleMode`, `nn::nfp` (three), `nn::oe::GetDefaultDisplayResolution` and its event.
- The other game's debug and cheat code in `host/hos_main.c`, `host/nn_hid.c` and `host/oot_*.c` is reached only
  through that game's lift hooks or through menu options that are off by default; gating it on the build id is S6's.
- The `nnos*` C wrappers of the SDK (about 140, 20 imported by `main`) have no host functions of their own: safe
  where a wrapper branches to the hooked C++ function, not checked one by one.

### 2026-11-17, S5

Run, with the save of S4 in `work/user/save`: `HOS_INPUT_FRAME_CLOCK=1 HOS_INPUT_SCRIPT="10:A" RUNDIR=s5 work/boot.sh
<name> 45` (title screen, Continue, the first stage by present 900). One frame pass by pass: add `RX_VK_DUMP=1500
RX_VK_DUMP_DIR=<existing dir> RX_VK_DUMP_W=480`; the pictures go to `<dir>/dump_1500` (row 0 on top: upside down for
this game), and the log's `vk: dump` lines give each pass's result (`dump NNN ...: mean, min, max`), its state
(`dump-st`) and its textures (`dump-in`, where `none(0x<handle>)` is a texture the back end has no view of).

Done:

- The cyan wash is gone (`work/runs/s5/d2.txt`, `work/runs/s5/d2/vk_001500.png`: the beach, right colours, 60.0
  presents a second, GPU time 2.7 ms a frame). Cause: the scene's depth buffer is NVN `DEPTH24_STENCIL8`, Vulkan
  `D24_UNORM_S8_UINT` (129), and RADV on AMD has no 24-bit depth format at all (`vulkaninfo`: the format is not
  listed). Its features read 0, so the image was made without sampled usage (and was not a valid image), the passes
  that read the scene's depth got the dummy, and the lighting pass fogged the picture. `image_format_of`
  (`gpu/vk/vk_texture.cpp`) now answers the 32-bit float twin (`D32_SFLOAT_S8_UINT`, `D32_SFLOAT`) where the device
  cannot attach the 24-bit one: the image, its views and the pipeline list's attachment format follow from that one
  rule. The format table (`vk_format`) stays a plain table: two tests read it as text.
- The frame gate (`gpu/vk/vk_replay.cpp` `gate_need_value`) dropped a fence request made while a present was queued.
  This game submits once more after its present and waits for that submit's fence (hand-over order: submit, submit,
  present, submit; 10 s timeout). Where the present is replayed at once (a shot of that present: `RX_VK_SHOT_EVERY=1`
  or 2), the last submit then stood alone at the gate for `RX_VK_FRAME_GATE_MS` (1000): 1.0 present a second
  (`work/runs/s5/f4.txt`; `RX_VK_FRAME_GATE=0`: 57). The request is now honoured with a present queued too: 60.0 with
  a shot of every present (`work/runs/s5/f8.txt`). Whether this is also the S4 stall (7 presents a second while the
  movie player starts) is not checked.
- Slots with no view, looked at: `0x2cb`, `0x48b`, `0x521` are 16x16x16 3D textures (NVN format 0x38) a 2D sample
  instruction reads. `make_view` makes such a view only with `sampler2DViewOf3D`, which RADV does not have
  (`image2DViewOf3D` only): they are sampled as the dummy. None of them is in the dumped frame of the stage; which
  passes read them is not known. `0x55a` / `0x397` (512x512 BC4, 2D) is bound where the lighting pass's program
  declares a 3D sampler (`t19` of dump 022), and handle `0xffffffff` is an unset binding (dumps 015 and 062): both
  get the dummy, and the picture is right with it.

- The two one-frame flashes are gone: 0 flashes in 5040 presents, the beach into the jungle, with a shot of every
  present (`work/runs/s5/g5.txt`). Run: `HOS_INPUT_FRAME_CLOCK=1 HOS_INPUT_SCRIPT="10:A,20:LUP/9000,23:A,26:A,
  30:LRIGHT/2000,33:LUP/10000,36:B,40:A/800,45:LLEFT/2000,48:LUP/8000,52:B/1500,58:LUP/10000" RUNDIR=s5 RX_VK_FLASH=1
  RX_VK_FLASH_DUMPS=0 RX_VK_SHOTS=<dir> RX_VK_SHOT_EVERY=1 work/boot.sh <name> 85` (before: `work/runs/s5/f9.txt`, two
  flashes, `work/runs/s5/f9/flash_sheet.png`: the title screen's blue background black for a frame at present 461 to
  477, and at present 1406, where the beach ends, a frame without the new zone's objects). Cause: the renderer, not the
  game. Its default leaves a draw out of the frame while its pipeline is built, where the targets hold an earlier
  frame's picture (`gpu/vk/vk_draw.cpp`, the `may_skip` branch; the build is a job even when the pipeline cache has
  it, so a warm cache flashes too). The log said so all along: `draws left out (not ready)` read 4.7 a frame in the
  120 presents around the place, 0.0 elsewhere. `host/hos_main.c` now sets `RX_VK_PIPE_SKIP=0` (every pipeline is
  waited for) where the player has not set the switch; `RX_VK_PIPE_SKIP=1` is the renderer's default again. Cost,
  measured with `work/cold.sh` (a fresh folder: no pipeline or program cache, `MESA_SHADER_CACHE_DISABLE=true`):
  cold and left out, 3 flashes (`work/runs/s5/c1.txt`); cold and waited for, 0 flashes, the slowest 120 presents at
  52.9 a second against 59.1 (`work/runs/s5/c2.txt`); warm, no wait measured (0.0 ms a frame).
  The earlier reading here (the game keeps frame data in two copies and one takes the new zone a frame late) was
  wrong. What ruled it out: a log of each recording's age at the submit (temporary, removed; `work/runs/s5/g3.txt`,
  read with `work/agelog.py`). The main thread records one 730 KB buffer a present, the thread `Thread_8091ce68`
  records the 16 buffers it calls and submits; every one of them is recorded in the present that submits it, and the
  lists change once at the zone change (present 1405) and never go back. The game does keep its cached per-object
  lists in two sets used in turn (17 new lists twice at the zone change), and both sets held the new zone.
  The renderer's quick pipelines (`RX_VK_QUICK_MS`, off by default) are the other way to draw such a frame without
  the wait; not tried, as its budget can still leave a draw out.

- The black box at the "Jump" hint is the hint's movie, left out by `HOS_NO_MOVIES=1`, which the helpers set
  (`host/nn_fs.c` OpenFile answers "path not found" for every `.webm` then; log: `fs: OpenFile(aoc1:/mov/GuideMovie/
  Jump.webm): movies are left out (HOS_NO_MOVIES)`). With `HOS_NO_MOVIES=0` the box shows the movie (Kirby jumping on
  a checkered floor), then the check mark, then fades by present 2550; the script needs no change
  (`work/runs/s5x/a2.txt`, `work/runs/s5x/a2_hint.png` against `work/runs/s5x/a3_hint.png`). 480x270 VP9, it loops,
  `video: Stop after 168 submits and 157 acquires`; presents stay 59.5 to 60.3 a second while the player starts, so
  the S4 stall did not show here. Not checked: the other 35 files of `mov/GuideMovie`, colours against a console.
- "One add-on map loads", read literally, is met: `work/dump/romfs` is empty and the add-on title is the whole game's
  data. In `work/runs/s5x/a2.txt`: `aoc: index 1: work/dump/aoc/01004d300c5af001/romfs`, `fs: mounted aoc1:`, 11062
  OpenFile calls on `aoc1:` (3203 found), 14 on `content:` (all not found), and the first stage's maps from it
  (`aoc1:/ubin/Step/Map/Level0/Stage1/Step01/Attr_Attr.bin.cmp` and the rest of `Step01`, `Step02`, the models under
  `aoc1:/gfx/Step/Decor/Map/Level0/Stage1/`). The Switch 2 Edition's extra stages are the `Dlc` names of the same
  romfs (1223 files, 1.53 GB; maps `ubin/Step/Map/DlcLevel0/Stage1` to `DlcLevel8/Stage1`, 13 stages, and
  `DlcArena`). None of those maps has been opened: a Starry stage is entered from the world map, and the game's texts
  say one appears when a world's boss is beaten, so it needs a save past the first world or a long scripted
  play-through. Left for after S6 unless such a save turns up. (2026-11-20: a player's save reached the first one,
  "issue #6" below.)
- A profile in the stage (script `"10:A,20:LUP/9000"`, 60.0 presents a second; `work/runs/s5x/c5.txt`, `c6_all.txt`,
  `c7_main.stacks`; helpers `work/runs/s5x/prof_cpu.py`, `prof_all.py`). The whole process uses 101 to 126% of a
  core over ten threads, none above a fifth: `mkw_vk recorder` 17 to 19, `mkw_vk replay` 16 to 18, `MainThread` 14 to
  15, seven `Thread_8091ce68` workers from 13 down to 2. The render thread's jobs take 2.48 ms of a 16.65 ms frame.
  Of the game threads' CPU samples 77% are lifted game code, 12% the host runtime, 6% libc or the driver, 5% the
  renderer; `f_807eff00` (a bytecode interpreter by its disassembly: 32-bit words, a jump table at 0x809c76a8) holds
  65% inclusive. No hot stub and no costly spin. Small host-side items: the recorder spins idle 0.76 s in 10 s
  against 0.44 s of work; `spin_until_set` (`host/nn_os_sync.c`) 3.4%; futex wakes under `WakeAllConditionVariable`
  3.4% (the virtual cores change hands about 24000 times a second); with `--trace` every NVN call goes through
  `a64_call_miss` (10 to 21% of the workers' samples), so profiles are taken with `TRACE=`.
  Tool notes: `HOS_SAMPLE` is wall-clock (most leaves in libc are waits; `scripts/prof.py` does not split them);
  it cannot reach the workers, which share one name: `HOS_SAMPLE_ALL=<file>` samples every thread while `<file>.go`
  exists; `RX_MAPS=<folder>` tells `scripts/prof.py` where the build's maps are.

- The 3D textures a 2D sample instruction reads, looked at: no change made, the dummy is harmless here. The texture
  is the colour grading's 16x16x16 table (the grading pass `5be22000a0782116` samples it as 3D, rightly). The 2D
  readers are layout programs that name it in an unused third sampler slot: `517266ea5da77cfe` in the stage intro
  (present 726 to 730, one HUD draw) and six programs on the title screen in one run of three. In `517266ea...` the
  sample sits in a block that runs only when the float at c3+4 is not 0, and it was 0 in every such draw of a 62 s
  run (`work/wt2/w/runs/a7.txt`, IR in `work/wt2/w/runs/b4ir/`): the shader never executes the sample. A fix exists
  and is not applied: `work/wt2/item2.diff` (a 2D image holding slice 0, made in `texture_view`, copied again after
  each upload; the copy was pixel-identical to slice 0, the pictures unchanged, 60.0 presents a second). Applied to
  the main tree it failed two tests that compile `vk_texture.cpp`'s functions against their own `Texture`
  (`tests/test_image_view_retry.py`, `tests/test_readback_timeout_source.py`; `work/runs/s5/tests3.txt`), and its
  re-upload and destroy paths were never run: not worth carrying for a sample that is not executed. Apply it, with
  the two fixtures extended, if a dump ever shows a 16x16x16 `none(0x...)` in a draw whose picture is wrong.
- Tests at the end of S5: 575 passed, 0 failed (`work/runs/s5/tests4.txt`).

S5's exit checks: the first level without flashes (met), one add-on map loads (met as written; no Star-Crossed
World stage yet, section 7), a profile (met).

### 2026-11-17, S6

Order: the rename first, so that everything after it was written and tested under the final names. Logs:
`work/runs/s6/`. The work tree as it was before S6 is kept in `work/runs/s6/pre/` (the diff of the tracked files and
the two untracked sources).

**The rename** (`scripts/rename_full.py`; without `--write` it only counts).

- One rule, case by case (`longshot`, `Longshot`, `LONGSHOT`), over the tracked and the untracked files: 2228 places
  in 428 files, 4 files renamed (`gpu/vk/compat/inhale_env.h`, `scripts/inhale_ctl.py` and its two tests). A second
  run finds 0 places.
- Kept, and why: the marks `(longshot)`, `(longshot: ...)`, `(longshot-amd)` on upstream's changes to code it took
  from others (1575); `LONGSHOT_MINGW` and `LONGSHOT_LIGHT_PASSES`, which the vendored a64-kit reads by name (its tree
  hash is checked); upstream's repository and tracker addresses and one launcher issue number; whole files: the
  provenance and credit documents, the readme, this file, the sync script, `third_party/`, the renderer's shader
  sources with their compiled headers (a header names the hash of its source: `tests/test_hdr_encode.py` failed
  until they were left alone), and the other game's item table, where the name is an item of that game.
- One span has an answer of its own: the window's application id was under upstream's domain, and is now the plain
  `inhale`.
- A name of another length breaks lengths written by hand. Thirteen places copied or compared a string holding the
  name with its length as a number (`memcpy(path + n, "longshot_env.txt", 17)`, `strncmp(text, "Longshot crash
  record 1\n", 24)`, `strstr(line, "] longshot ") ... at + 11`): three tests found the first of them
  (`test_crash_record`, `test_env_file`, `test_log_open_failure`, under gcc's `-Werror`), a scan of every string
  holding the name found the rest. The script now moves such a number with its string (`LENGTH`: the first number
  that ends an argument or a sum after the string, where it equals the string's length with or without the end's
  zero); run over the files as they were before the rename it changes exactly those thirteen.
- Where this fork's own text meant upstream by the name (six comments), it now says "upstream": the rule cannot tell
  the two meanings apart, so the text that must keep the name is in the kept files.
- `scripts/sync_upstream.py` builds both sides of Longshot's diff as trees put through the same rule (file names and
  text, blobs written into this repository so that `git apply -3` finds its bases) and applies the diff between
  them. Tried on two throwaway clones: a change to `longshot_env.h` and to `longshot_ctl.py` and a new file arrived
  under the new names with the new text, and a line changed on both sides was left as a conflict.
- Consequences: the environment variables are `INHALE_*` (`INHALE_VULKAN_HEADERS`, `INHALE_SPIRV_HEADERS`,
  `INHALE_JOBS` and the rest), the program is `work/sa/build/inhale`, the saves' default folder is
  `$XDG_DATA_HOME/inhale`, the builder's default work folder `~/.cache/inhale-builder` (no longer shared with a
  Longshot install), and every cache keyed on the old names was built again once. The prefix lists that pass or drop
  `INHALE_` variables now also match the dump variables (`INHALE_WORK`, `INHALE_DUMP`): harmless, the game reads none.

**`nx2/make_game.py`.**

- The game folder: `inhale`, `inhale_vk.so`, `image.bin`, an empty `romfs/`, and `aoc/<title id>/romfs` with the
  data. `host/hos_main.c` takes `aoc` from beside the executable, as it takes `romfs` and `user`, unless `--aoc` or
  `HOS_AOC` names one.
- Changed in the builder: the data check (`ROMFS_NEEDED`: `ubin/Step/Map`, `gfx/Common`, `fdg/Archive.dat`, tested
  on the romfs that holds the data); the package path moves `aoc` into the folder and always makes `romfs`; reuse
  by stamp and `--update` do not unpack again; `--aoc <dir>` and `--game <folder with exefs and aoc>`;
  `--romfs-from` carries `aoc`; the lift and the build get `INHALE_*`; the game's name for folder input comes from
  `main.npdm`'s program id; the texts and button prompts steps, which read the other game's archives, are gone from
  the build; the language list is this game's 13 (the folders of `msg/Kirby15`), in `make_game.py`,
  `host/nn_applet.c` and `gpu/vk/vk_menu_i18n.cpp`.
- Run for real: `make_game.py --nup <package> --out work/game --work work/mg` ends `@@done`, 132 s after the unpack
  (83 s of compiling), 12 GB (`work/runs/s6/make_game1.txt`). `work/game/inhale` with no arguments mounts `aoc1:`
  from the folder and presents 60.0 a second (`game_folder1.txt`; `XDG_DATA_HOME` set to a folder under `work/`, so
  the first-boot script was used). `--update work/game` after later source changes: 10 s, 99 of 455 files compiled,
  no unpack, 60.0 again (`make_game2.txt`, `game_folder2.txt`).
- Left as they are, harmless here: the shader list step (it ends "the shader list was not made: the game will
  compile its shaders as it plays", which is true), the damaged texture check (nothing to find: no `.zs` files),
  sizes in a few messages that are the other game's.

**The hot list and the profiles.** None is in the repository (upstream kept its own out too): they are
`work/hot_funcs.txt`, `work/inhale_pieces.prof` and `work/inhale_vk.profdata`, which `make_game.py` copies into its
work folder and uses when they exist. `work/boot.sh` sets the matching variables, since `nx2/lift.py` and
`nx2/build.py` take them from the environment alone: a lift without `A64_HOT_FUNCS` takes the hot chunk away, and a
build without `RX_PGO` / `RX_VK_PGO` compiles without the profiles again.

- Sampling: `HOS_SAMPLE_ALL=<file> HOS_PROFILE=5`, no call tracing, the S5 walk script; `<file>.go` must be made
  after the stage has started (second 20): made before the start, only `MainThread` is ever sampled (41983 lines of
  one thread; the sampler takes its thread list when it first sees the file).
- `scripts/hotlist.py work/runs/s6/hot2/all.txt <out> 0.95` (since v3.1.1 `scripts/perf.py hotlist <samples> <out> --share 0.95`): 10414 samples of game threads in 725 lifted functions;
  301 functions cover 95% (79 cover 85%). First: `f_807eff00`, the bytecode interpreter of S5's profile. Two faults
  of the tool fixed on the way: on Linux it took the module from the empty entry the linker map gives the `.exe`
  name (0 samples counted), and it appended the other game's decoder functions to every list (now only where the
  build's `gen/hos_image.c` carries that game's build id).
- Lift with the list: `hot functions (A64_HOT_FUNCS): 301 of 301 listed found, in code_hot.c`; `nx2/split_hot.py`
  makes 8 pieces.
- Profiles: `RX_PGO=gen RX_VK_PGO=gen` build, `work/pgo_run.sh` (the walk script; at present 4200 both modules
  write their counters, on the `.dump` files; the instrumented build presents about 25 a second, and the script
  counts presents, so the play is the same), `llvm-profdata merge`: 1310 functions of the hot pieces, 4369 of the
  renderer. The build says `the Vulkan back end: built with the profile ...`; the game side says nothing.
- Measured (`work/cpu.sh <folder with the two binaries> <name>`: the process's CPU seconds by thread between
  presents 1800 and 3000 of a fixed walk, from `/proc`; all runs at 60.0 presents a second; three runs each on a
  quiet machine, `work/runs/s6/cpu_*{7,8,9}.cpu`): before 18.29, 18.30, 18.43; with the hot list 16.87, 16.42,
  16.24 (10% less; the workers `Thread_8091ce68` 10.66 to 8.61); with the hot list and both profiles 16.13, 15.60,
  17.45. The profiles' gain over the hot list is not shown by these numbers (section 7).

**The in-game menu.** The host tells the menu once, before the renderer starts, whether the game is the one the
game-specific rows were made for (`HOS_OPT_OOT_GAME`, 72, through the existing option call: `host/rx_backend.c`,
`gpu/vk/vk_menu.cpp` `row_shown`, `is_oot_row`). Never told (a menu built alone, as the tests build it), every row
shows; no row or string was deleted.

- Hidden for this game, each for a consumer that is only the other game's code: Field of view, Shadow resolution,
  Aspect ratio, Ultrawide menus, HUD layout, Text speed, Text size, Camera speed, Skip title screen, Skip opening,
  the Debug tab's tools, the ocarina notes of the Controls page, the microphone rows (Audio's Microphone, Microphone
  gain and Test microphone: the ocarina's input streams in host/nn_audio_in.c, which no game code calls); and, read to
  be sure, Render resolution (its values are read by no host code), Upscaler and DLSS model (the chain replaces only the
  other game's programs), Frame generation by (DLSS frame generation needs that upscaler's picture), Game frame rate cap
  and Game speed (the limiter and the time step need the other game's graphics module; measured: a cap of 120 still gives
  60, a cap of 30 gives 30 presents with the same game state each, so half speed), Disable camera centering.
- A hidden row's saved value is held at its default while the row is hidden (`oot_rows_hold`, for the run only: the
  file keeps its value). Checked with a saved cap of 30: 60.0 presents a second.
- Any game but the other one stays 16:9 (`host/hos_main.c`): told another shape, the renderer stretched the 16:9
  picture.
- Words: "Link" is "the character" in the Walk rows; the Microphone help no longer speaks of the ocarina; the
  Quality preset's and the weak laptop row's help are chosen by the flag, without the hidden rows' names; the
  graphics card message no longer names the other game; the three texts that sent the player to upstream's tracker
  name `tracker.inhale.invalid` (this fork has no tracker). Carried through the 13 language tables where the text
  had entries.
- Kept, generic or half so: Mouse camera (falls back to "as the stick"), Button prompts (names the pad's inputs;
  the game's own icons are the other game's files), Walk mode and speed.
- Seen: `work/runs/s6/menu/*.png` (one picture a tab, in the stage) and `options.txt` (the control bridge's list,
  65 settings). Left: texts that speak of a launcher or a builder application, which this fork does not have
  (`host/hos_crash_dialog.h`, two in `gpu/vk/vk_menu.cpp`); the Controls help names the Button prompts row.

**At the end of S6:** the walk from the beach into the jungle, 0 flashes in 5040 presents with a shot of every
present, on the build with the hot list and the profiles (`work/runs/s6/flash1.txt`); tests 575 passed, 0 failed
(`work/runs/s6/tests2.txt`); `scripts/check_third_party.py`: 13 parts as their notes say.

S6's exit checks: the builder and the folder's program (met), the hot list and a profile measured (met; the hot
list's effect is shown, the profiles' is not), the menu (met for the rows and texts listed; the launcher texts are
left), the rename (met).

### 2026-11-17, after S6: played by hand

The first stage was played in a window, with sound, from `work/game/inhale`.

- Keyboard defaults are this game's (Type A): Space or Enter A, E or the left mouse button B, F X, Q Y, Shift or the
  right mouse button L, Tab Plus (`host/nn_hid.c` `key_default`). The keys were not pressed in a scripted run.
- A hint movie that plays to its end and starts again aborted the game (`nn::diag::detail::AbortImpl`, lr 0x80450168:
  the decoder wrapper in `main` gives back a picture it no longer has). S5 saw a hint movie only until the walk
  finished the hint, before its 5 s were over. Three causes in `host/nn_video.c`, all at a movie's end:
  1. Every acquire after the last submission marked its buffer "last": three "last" pictures, where the player takes
     one and flushes. Now one; later buffers go out not last, their sync not reached.
  2. `RequestSyncPointEvent` for a sync not reached left the event signalled from the buffer's last picture. The
     wrapper's decoder thread then queued such a buffer for the player as a picture; the loop's flush took it back
     (the wrapper's flush at 0x8044f860 releases everything it handed out) and the player's next release aborted.
     The event is now cleared when the request is put off.
  3. A flush kept the buffers' times. The first buffers of the next pass told 4.9 s, the player took its clock from
     them and ran through the 150 pictures in 0.45 s. The times are zeroed at a flush.
  Checked: `work/runs/c1/h.txt`, 120 s with the "Jump" hint up (Kirby walks against a ledge), 17 passes, each 150 pictures 33.3 ms apart,
  none skipped, no abort; the opening movie still ends with `Stop` and the stage starts (`work/runs/c1/first.txt`);
  tests 575 passed. The player's crash came after copying an ability, so at a later hint: the same abort and
  backtrace, that hint itself not replayed. Helpers: `work/runs/c1/run.sh <name> <seconds> <input script>` (the game folder on a copy of the
  player's save, `HOS_VIDEO_LOG=1`), `work/runs/c1/script_b.txt` (the walk that reaches the hint and stays).
  `HOS_VIDEO_LOG=1` now also logs each buffer's release and each sync event request.
- Not looked at: each pass of a looping movie starts with the two buffers as they were (the last pass's final
  pictures) for a frame or two.
- Background music missing in stages and in the scenes drawn by the engine: the software `nn::codec::OpusDecoder`
  family was all stubs. It is now in `host/nn_codec.c`, on the hardware decoder's bodies (not committed; in
  `work/game/inhale` since 14:03). The player heard the music in play afterwards; the check below forced a track.
  - The game's music is 160 Opus streams (`snd/Kirby15/stream/*.opus`, Nintendo header `0x80000001`) and 66
    `.bfstm`. The title's `K15_TitleAndTownNewWorld1` is a `.bfstm`, which is why it always played. The sound engine
    decodes Opus with the software decoder: `GetOpusDecoderWorkBufferSize` twice at start (lr 0x805823ec,
    0x805822d0), then `InitializeOpusDecoder` (48000 Hz, 2 channels, lr 0x80582b0c) and `DecodeOpusInterleaved`
    (lr 0x80582ed8) on the stream thread `Thread_8059dc48`. The hardware family is not called.
  - The first stage's beach has no music by the game's data, so a run that stops there says nothing about the fix
    (the mistake of the first look: "the change alone brings no music"). `yaml/Scn/Step/Map/MapData.bin` names
    `_NO_SOUND` for `Level0/Stage1/Step01` and `Step02`; its `GimmickData` row for both is
    `["_NO_SOUND", "K15_Grassland1"]`, so the music there starts from something in the map, further in than any
    scripted walk has reached. The game's scripts ask for a step's music through `f_8090d740(manager, archive,
    label, ...)` (bindings at 0x8070f074 and after; `f_8090da40` is its sibling); the manager's per-frame update
    `f_8090dd40` starts it with `f_8057f364(startable, handle, label, archive, info)`, and `f_8057b2ec` looks a
    label up. With the save on the beach the only requests are the title's and `_NO_SOUND`.
  - Check: under gdb the stage's `_NO_SOUND` request was rewritten in place to `K15_Cave1` (an Opus stream, same
    length). The decoder is created and decodes (`codec: decode 803 bytes (of 4096) -> 960 samples`), and the audio
    dump is music for the 45 s after: RMS 2500 to 3400 by 4 s windows against about 400 for the beach's waves alone
    (`work/runs/bgm/force1.wav`, `work/runs/c1/bgm1.wav`). With `GetOpusDecoderWorkBufferSize` made to answer 0
    again the stream still starts and decodes: the missing bodies were the cause, not the size. Tests 575 passed.
  - Not checked by a scripted run: a loop point of a `.marker.opus` stream, and the natural start of
    `K15_Grassland1` in the first stage (holding the stick up and jumping stalls in the first clearing,
    `work/runs/bgm/wj1_sheet.png`). The player's report covers the music in play, not these two by name.
  - Method, helpers in `work/runs/bgm/`: `gdb.sh <name> <seconds> <input script> <python file>` runs the game
    folder under gdb on the copy of the player's save; the Python file sets breakpoints on lifted `f_<addr>`
    symbols and writes `<name>.out.txt`. In a breakpoint the guest registers are `((unsigned long*)$rdi)[n]` (lr is
    30) and guest memory is at `0x100000000000 + (addr & 0x7fffffffff)`: the guest space is 39 bits here, and a
    32-bit mask (as in the first look's label script) reads the wrong place for anything on the heap. A host
    function's `hle_<symbol>` body is inlined into `imp_<symbol>` unless `HOS_HLE_STATS=1`: break on `imp_*`.
    gdb does not count a hit when a Python `stop` answers False: log from `stop`. Scripts: `start2.py` (labels of
    every start and lookup; `FUNCS=` picks the functions), `watch.py` (write watch on the manager's label buffer),
    `force.py` (`LABEL=`), `codec.py` (the Opus host functions' first calls; `ZERO=1`), `xyaml.py <file.bin>`
    (HAL's `XBIN` YAML version 6 to JSON: every offset is relative to its own field; node types 1 int, 2 float,
    3 bool, 5 string, 6 map, 7 list).

### 2026-11-17, after S6: far objects at 30 and 15 updates a second

- Report: far animated objects (the Maxim tomato sign across the first stage's village) move at 30 while the game presents
  at 60. Measured first (`work/runs/c1/mask.py`, `reg.py`, `farnear.py`; a shot of each present from the player's save,
  `RX_VK_SHOT_FROM=1500 RX_VK_SHOT_TO=1559`): the tomato and the Waddle Dees beside it change once every fourth present
  (29 of 59 pairs changed, in a burst every fourth), the Waddle Dee near Kirby every present. So the far updates are
  at 15 here, not 30; the cell metric also sees periods of 2 (other objects).
- Cause, in the game's code: each animated object is put in an update level by its squared distance to the camera
  (`main+0x8e2064` on; three cumulative steps in the object's +0x84, +0x88, +0x8c). The dispatch at `main+0x8e2350` does
  level 1 = skip odd frames (`(frame counter [+0x3f4] + object index [+0x38]) & 1`), level 2 = one frame in four
  (`& 3`). Past step 1 an object is level 1 (2 when its sphere is outside the view), past step 2 level 2. With the
  dispatch skipped (an experiment, not kept) the tomato changes in 58 of 59 pairs: this is the whole cause, not the host.
- The Switch 1 60 fps patch (build id D9BA7DB7, three edits): `0x5330d8` and `0x533110` force the main loop's
  per-frame wait count to one vertical sync (frame pacing, already 60 here, not carried over); `0x7f0d1c` turns the step 1
  compare's `b.pl` into a `b`, so objects past step 1 are judged near. The listed addresses are module offsets as they are
  (the `offset_shift 0x100` is not to be added: the words there are `b.eq`, `mul` and `b.pl`, the three sites). The same
  code is in this build (found by the frame-counter dispatch's shape: the counter's offset moved from +0x3e4 to +0x3f4).
- Step 1 alone does not help here: the tomato stayed at one in four (`work/runs/c1/shots_s7c`) because it and its
  neighbours are past step 2. Step 2 skipped as well gives 57 of 59 pairs for the tomato (`shots_s7f`, the built
  game), the near Waddle Dee unchanged. Skipping step 2 goes past what the Switch 1 patch does (a decision of this port, to be confirmed by the
  player's look); the third step (level 3) and the hidden-object level 2 stay the game's.
- Fix: `nx2/kirby_far.py` (gated on main's build id `395fc326...` and on each site's word) writes three branches in the
  lifter's copy of the image before the discovery (`nx2/lift.py`): `main+0x8e21a0` `b.mi` to `nop`, `main+0x8e21f4`
  `b.pl` to `b`, `main+0x8e2180` `b.pl` to `b`. The image the guest reads is the game's. Test: `nx2/test_kirby_far.py`.
  (Not `edit_c`'s text pass: the lifter's other edits are in the instruction stream, and the branch is then gone
  from the lifted C, so no label is left for the skipped path; checked in `work/sa/gen/code_hot_1.c`.)
- Cost, `work/cpu.sh` (20 s of the first stage walking): 18.21 CPU seconds before, 18.43 after; the game's own
  thread 10.24 to 10.56 (that walk is the beach, not the village). In the village run itself (`work/runs/c1/s7b.txt`, `s7f.txt`) both stay at
  60.0 presents a second up to present 1920 and after (the fixed build to 2640).
- Not checked: other stages (their objects have other step values), the game's own scripted cut scenes, whether
  keeping the Switch 1 scope (step 1 only) is wanted somewhere. The player is to look at the tomato spot.

### 2026-11-17, after S6: the microphone rows

- The microphone support is Longshot's Ocarina of Time path (`host/nn_audio_in.c`: the ocarina's input streams), not
  something this game uses. The `sdk` module imports 16 `nn::audio` virtual-input/input-stream functions
  (`ListVirtualInputDevices`, `GetDefaultVirtualInputDevice`, `IsVirtualInputDeviceStreamFormatSupported`, the
  `*InputStream` family and `SetInputStreamGain`); none is referenced anywhere in the lifted image: no call from the
  lifted C and no constant or pointer in the relocated guest image (`work/sa/gen/code_*.c`, `nx2/image.py` `EdenImage.mem`).
  The output thunks do have callers (e.g. `OpenAudioOut`), which is how the difference was checked. `main` imports none
  of the input symbols (only `ListAudioOutputDeviceName` and `SetAudioDeviceOutputVolume`), `GetTrueRawAudioInputDevice`
  is imported by no module, and no run log has an `audio in:` line or an input-stream HLE call under `HOS_HLE_STATS=1`.
- Kept, not deleted, so upstream's (OoT's) fixes to it stay easy to cherry-pick: the menu hides its three rows for this
  game through `is_oot_row` (Microphone, Microphone gain, and the Test microphone action row), so they leave the Audio
  tab, its counts and the control bridge (the two value rows: 65 settings -> 63; the Test row is an action). The saved
  `microphone_device` line is still read and the host still lists devices when the menu opens, but no stream can start:
  the Test row is the only way, and it is hidden.
- Check: `tests/test_mic_rows_hidden.py` (the hiding stays), and the full suite. A menu built alone (the tests) still
  shows the rows, as it shows every row.

### 2026-11-18: the first sync, to Longshot `v3.0.0-rc.7`

- `scripts/sync_upstream.py --to v3.0.0-rc.7` (`544229a2`, 36 commits past the import's base): 204 files changed in
  the imported paths, 191 applied (59 of them new), 13 not applied (12 not tracked here, and the stand-in). Five
  files conflicted, in 8 places, each with one answer: `.gitignore` (both sides), `gpu/vk/vk_api.h` and
  `host/rx_backend.c` (below), and the two checks that assert the interface's version.
- The renderer's interface is version 30 here: Longshot went from 25 to 29 with six new host members, and this
  fork's `origin_lower_left` (26 before the sync) now comes after them, in `MkwVkHost`, in `host/rx_backend.c`'s
  table and in `tests/test_audio_output_devices.py`.
- The rename rule was wrong in two places, found on a trial of this sync and fixed before it:
  `scripts/fsr3_shaders.py` now holds shader text with functions named after Longshot, compiled into headers the rule
  keeps (the file is kept whole), and the mark `(version 26, longshot)` on a member of the interface was renamed (it
  stays). `tests/test_sync_rules.py` has both.
- Longshot now sends things: the crash window's Send posts a crash report, and a launcher's tick sends performance
  statistics, both to Longshot's own services, whose addresses are in `nx2/addresses.ini`. Every key is empty here,
  which turns each use off (`nx2/make_game.py` writes no address into the game folder, `nx2/perf_report.py` has no
  relay). `tests/test_perf_report.py` expects that.
- The stand-in `nx2/oot_patches.py` needed nothing: Longshot's file gained 14 names, and nothing in `nx2/` uses one.
- Checks: `tests/run_all.py` had 19 new failures after the sync. Longshot's own tree at the same revision, checked out
  under `work/` and run on the same machine, fails 16 of them too (45 in all): checks whose source moved on without
  them. Those are left out, with one script and three checks bound to things left out (`PROVENANCE.md` has the
  lists). One was this fork's: `nx2/test_kirby_far.py` named the lift's call, which Longshot reworded; the merge of
  `nx2/lift.py` itself was right. After that: 530 passed, 5 failed, 64 skipped, the five being the ones that fail
  only in the sandbox the checks ran in (a run outside it, `work/runs/s7/tests.txt`, has 0 failed).
- In the game: `work/boot.sh rc7 60 --lift` (the lift with the hot list, the build with the profiles, 0 files
  failed, then 60 s headless without movies or sound): 3599 frames presented, 60.0 a second over the last 5 s, every
  present interval between 15.5 and 17.8 ms (`work/runs/sync-rc7/rc7.txt`). No picture was looked at and nothing was
  played: that is still to do by hand.
- Not looked at: what Longshot's 36 commits change for this game beyond the checks and that run (its new settings
  rows, the fullscreen monitor choice, the crash window).

### 2026-11-18: the nightly sync

- `scripts/sync_nightly.py` does the sync unattended (the sync-upstream skill, section 8): Longshot's clone fetched,
  the agent at work in a clone of this repository (`work/sync/tree`), and `main` moved by fast-forward only when a
  gate the script runs itself passes. A stopped night is kept, never discarded.
- The gate runs the game. `INHALE_WORK` and `INHALE_DUMP` (`nx2/kit.py`) give the lift, the build and the run a work
  folder apart from the one a person builds in, reading the same dump: `work/sync/game`. Measured there on the tree
  at `v3.0.0-rc.7`, with no hot list and no profiles: lift 17 s, build 73 s from an empty object cache (24 jobs),
  then 60 s with `HOS_HEADLESS=1 HOS_AUDIO=0 HOS_NO_MOVIES=1` and a new user folder: 3301 frames presented, 60.0 a
  second over the last 5 s. With the cache filled the three take 81 s together.
- The gate passes the game when it is still running at 60 s and has presented 1800 frames. It does not look at a
  picture and plays nothing: a sync that draws wrong or breaks a level still lands.

### 2026-11-18: the second sync, to Longshot `9af4808f`

- `scripts/sync_upstream.py --to 9af4808f` (66 commits past `v3.0.0-rc.7`), run by the nightly agent in
  `work/sync/tree`: 347 files changed in the imported paths, 315 applied (88 of them new), 32 not applied (31 not
  tracked here, and the stand-in). Five files conflicted, in 7 places, each with one answer: `gpu/vk/vk_api.h`,
  `host/rx_backend.c` and `tests/test_audio_output_devices.py` (the interface, below), `nx2/lift.py` (both sides:
  Longshot's entry hooks, then this fork's `other_game`) and `nx2/make_game.py` (Longshot's new sentence with this
  fork's wording of its end).
- `git apply -3` runs git's rerere when it leaves conflicts. With `rerere.enabled` and `rerere.autoupdate` set (they
  are in this PC's `~/.gitconfig`) and a resolution of the same conflict recorded in the clone's `.git/rr-cache` (a
  trial run to `310e7c9d` the same night had left all five), git writes the recorded resolutions into the files and
  then stops at the index lock it holds itself (`fatal: Unable to create '.git/index.lock': File exists`): the work
  tree is whole, with no conflict marks, and nothing is staged, so `git diff --diff-filter=U` lists nothing and the
  new files are untracked. That night the work tree was compared with a second run in a scratch clone with rerere off
  (the same files, the same bytes but for the five), the five replayed resolutions were read against the rules of the
  sync-upstream skill, and the paths were staged by name. `scripts/sync_upstream.py` does not turn rerere off for its
  `git apply`; it is not changed here.
- The renderer's interface is version 34 here: Longshot went from 29 to 33 (the pose sample's `perf_tracking`, the
  renderer's `nvn_invalidate_quick`, `rumble_test`, seven NFC members), and this fork's `origin_lower_left` comes after
  them in `MkwVkHost` and in `host/rx_backend.c`'s table. Longshot's list of names in
  `tests/test_audio_output_devices.py` now ends at its own `perf_tracking` and is checked as one run from `take_text`,
  so this fork's member is no longer in that list: a line of its own there asserts that it is the last member and the
  last entry of the table.
- Longshot's lift now puts the host's `memcpy`, `memmove`, `memset`, `memcmp`, `strlen` and `strcmp` first in the
  SDK's functions of those names (`nx2/entry_hooks.py`, `host/nn_libc.c`), for any game. In this game's `sdk` it finds
  all six (`entry hooks spliced: 6`), and the game's log says so (`libc: ... are the host's`). `HOS_GUEST_LIBC=1`
  gives the game's own back. It is the one change of this sync known to alter what this game runs.
- Section 13 above is new: Longshot's renderer now points at rules in its own design notes
  (`// doc: docs/design.md#13-frame-generations-presents-as-rules`), which `tests/test_doc_anchors.py` follows, so the
  rules are carried here under Longshot's number, as they are at `9af4808f`. Nothing brings Longshot's later changes
  to them over: `docs/` is not an imported path.
- The stand-in `nx2/oot_patches.py` needed nothing: Longshot's file gained 11 names (the horse's jump, the texture
  heap's compaction), and nothing in `nx2/` uses one. `host/oot_tex_compact.c` is reached only from code those patches
  edit.
- Checks: before the sync `tests/run_all.py` had 0 failed (536 passed, 64 skipped; 590 and 10 with the Vulkan and
  SPIR-V headers given). After it, 12 failed. Five fail in Longshot's own tree at the same revision for the same reason
  (checked out under `work/` and run on the same machine) and are left out, with two more that run only with the
  Vulkan headers and fail in both trees there. Five are bound to things left out (three read Longshot's
  `docs/development.md`, two the text of its `nx2/oot_patches.py`) and are left out with their fixtures, as are eleven
  build outputs of a builder test project that Longshot committed (`tests/builder_workers/obj/`). `PROVENANCE.md` has
  the lists. Two were this fork's to repair: `tests/test_doc_anchors.py` (section 13) and Longshot's new
  `tests/test_share_message_i18n.py`, whose fixture compiles the menu's lookup and needed this fork's rows
  (`menu_i18n_inhale.h`). After that: 556 passed, 0 failed, 79 skipped, and 625 passed, 0 failed, 10 skipped with the
  headers given (`INHALE_VULKAN_HEADERS` and `INHALE_SPIRV_HEADERS`, a folder holding only them; Longshot's own tree
  reads `LONGSHOT_VULKAN_HEADERS`).
- In the game, in the clone's own work folder, no hot list and no profiles: lift 18 s, build 12 s (0 files failed;
  the trial's object cache was there), then 60 s with `HOS_HEADLESS=1 HOS_AUDIO=0 HOS_NO_MOVIES=1`: 3288 frames
  presented, 60.0 a second over the last 5 s, still running at the end. No picture was looked at and nothing was
  played.
- Not looked at: what Longshot's 66 commits change for this game beyond the checks and that run (the Insert menu's
  NFC tab and Rumble row, the log's redaction, long paths, the present queue and frame generation changes).

### 2026-11-18: the release packages

`packaging/` (section 10) built here at `eb25254` plus the packaging changes: `Inhale-x86_64.AppImage` 235 MB,
`Inhale-Setup-x64.exe` 127 MB (its folder 1.1 GB). Each prebuilt its 316 third-party objects with 0 failures.
`tests/run_all.py`: 560 passed, 0 failed, 79 skipped.

- Linux, the AppImage in clean `ubuntu:22.04` and `fedora:latest` containers with no compiler: `--cli --check` on the
  package says "Linux build prerequisites: OK" and accepts it. A whole build in the `ubuntu:22.04` container
  (`--cli --game <.nup>`): `@@times 135 81 -1`, `@@done`. That folder, started on this PC through `--play` with
  `PATH=/usr/bin:/bin` and a clean environment, ran at 60.0 presents a second for 60 s. No picture was looked at.
- Windows, on aubox (Windows 11, RTX 2080 SUPER), as a normal user with no compiler on `PATH`: the silent install
  (`/S`) into `%LOCALAPPDATA%\Programs\Inhale`, with its Start menu shortcut and its "Apps & features" entry. The window's
  own runner (`gui/inhale_builder.Child`) with the installed Python: `--check --game <dump folder>` said "the
  compiler: ...\llvm-mingw (no Visual Studio needed)" and ok. A whole build from the extracted folders (`--game` with
  `exefs/` and `aoc/`) took 306 s, prepared the shaders and ended with `@@done`. This is the first run of both the
  llvm-mingw route and the folder input on a real dump. Started as the window's Play button starts it, in the
  disconnected desktop session, the game ran at 60.0 presents a second. No picture was looked at, because the console
  session is another user's. The silent uninstall left the game folder and removed the install folder, both shortcuts
  and the uninstall key.
- Cancel: the runner's `kill()` during the compile took the build's session from 25 processes to 0 (Linux). The
  Windows path (`taskkill /T`) was not tried.
- Both builds printed a traceback from `nx2/shader_census.py`, which reads `romfs/Pack/ZsDic.pack.zs` (the other game's
  file), then "the shader list was not made". Gone: this game's list is `nx2/kirby_shaders.py`'s now (section 9,
  "issue #1").
- Played by hand (the user): the AppImage's window, a build into the default `~/Games/Inhale`, Play: the game works.
- The release workflow (run 44315474239, from a branch with a commit adding it to the push trigger, dropped after):
  the three jobs passed, and the `nightly` prerelease got `Inhale-x86_64.AppImage` (245 MB), `Inhale-Setup-x64.exe`
  (132 MB) and `SHA256SUMS`. Downloaded, both match the sums; the AppImage carries the hot list and no profiles, and
  its `--cli --check` in a clean `ubuntu:22.04` container accepts the package.
- Not tried: the window clicked through on Windows; Cancel there.

### 2026-11-18: played by hand past the first boss

- The user played the AppImage's build (`~/Games/Inhale`, Linux, RX 7900 XTX, RADV, Mesa 26.2.6) through the first
  world's stages, its boss and several special stages. Nothing else was seen to go wrong.
- With frame generation on, the game hung now and then for a few seconds and then went on. The options file had
  V-Sync on and Frame pacing on (`vsync=1`, `frame_pacing=1`); the multiplier was not noted, and frame generation is
  now off there. No log was kept. Section 13's rules were measured by upstream on NVIDIA under Windows only; this
  is the first report from RADV. Not looked into.

### 2026-11-18: RecompLauncher's manifest and the Windows zip

`packaging/recomplauncher.json`, `Inhale.exe` and `Inhale-Windows-x64.zip` (section 10), checked here at `6d5040d` plus
the changes. `tests/run_all.py`: 561 passed, 0 failed, 79 skipped.

- The manifest validates against RecompLauncher's `schema.json` (`jsonschema`).
- `packaging/linux/docker.sh windows`: `Inhale-Setup-x64.exe` 127 MB and `Inhale-Windows-x64.zip` 270 MB (deflate,
  against the installer's LZMA), with `Inhale.exe` and `recomplauncher.json` at its top. `docker.sh`: the AppImage,
  235 MB, with `recomplauncher.json` at its root.
- Under Wine, from the unpacked zip: `Inhale.exe --cli --help` prints `make_game.py`'s usage; `--cli -c` returns 2,
  `make_game.py`'s own code; `--play <empty folder>` says "no built game" and returns 1. An argument with spaces,
  quotes and a trailing backslash reaches `make_game.py` whole. A non-ASCII argument came through mangled, as it does
  when Wine starts `python.exe` directly too, so that part is not shown either way.
- The AppImage: `--cli --prepare --game <the other game's .nup>` printed `progress` lines, then
  `error This is build e0f3ccfa. Inhale supports build 395fc326.`, and returned 1. It unpacked the whole 26 GB first,
  then removed it. `--play ~/Games/Inhale` started the build there: 59.5 presents a second, the window closed at 25 s.
  With no argument, the window was still up at 15 s.
- The AppImage, as the manifest starts it: `--cli --prepare --game <this game's .nup> --out work/rl/out` returned 0
  in 48 s (the object cache from earlier builds), with 469 `progress` lines on stdout, from `0.000 Reading your game
  files` to `1.000 Done`, and the known `shader_census.py` traceback (section 9, the release packages) on stderr.
  `--play work/rl/out` ran at 60.0 presents a second at 30 s. No picture was looked at.
- Not tried: RecompLauncher itself, and the zip on Windows.

### 2026-11-19: issue #1, the stutter of a first visit

Issue #1 (an RTX 5080 at 4K): "constant microstutters" in the first level, 60 presents a second otherwise. The cause was
the first visit's shader and pipeline compiles. This game sets `RX_VK_PIPE_SKIP=0` (S5: every draw waits for its
pipeline), and a first start had nothing to build ahead of time: no shader list (the census was upstream's and stopped,
section 9, "the release packages") and no shipped pipeline list. A warm folder does not stutter (the user's install: 374
of 412 log windows at 0.00 waits a frame).

Where the game keeps its shaders. The code title's romfs is empty, and the files are in the data title
(`aoc/01004d300c5af001/romfs`). A `.cmp` is a u32 size, then an LZ4 frame. Every stage is a BNSH as upstream's game has
them: the control section (magic `34 12 76 98`, 0xd8 bytes) and the code area it sizes, one program per variation (slot 8
vertex, 40 fragment, 48 compute, 32 an NVN stage 2). `shader_census.py`'s `bnsh_all` reads them unchanged:

- `gfx/**/*.bfres.cmp`: the models, a BNSH for each material shader, 44522 programs;
- `ptcl/**/*.ptcl.cmp`: 8638 programs; `lyt/**/*.arc.cmp` (SARCs, some files in them `.cmp` again): 970;
  `shader/**/*.bfsha` (an FSHA with a BNSH at 0x1000 or 0x2000): 46;
- `ndsr/lower_left.ndsr`: an NDSR in another layout than upstream's (u16 +0x0e the item count, items from +0x10;
  upstream's: u32 +0x0c, from +0x14), with the same item types: 3 graphics programs, 30 compute;
- the executable itself: three BNSHs in `main` (the layouts' common programs, 55 not found elsewhere), read from the
  folder's `image.bin`. No file holds them: the layout archives carry near copies that differ in the control section's
  hash at +0x20 and in the code.

`nx2/kirby_shaders.py` walks these and writes `HKSEED01` (`inhale_shaders.bin`): 54264 programs from 66064 stages,
544 MB, 10-14 s. It runs only for main's build 395fc326. `make_game.py` runs it instead of `shader_census.py` when the
data is a data title's (`data_romfs`), and the "not made again" key covers it and its folders (`CENSUS_READS`).
Coverage: all 636 stages a cold walk dumped (`RX_VK_DUMP_STAGES`), and 5041 of the 5045 stage keys in the user's play
list (past the first boss). `assets/pipeline_states/contrib/` ships two lists: the user's play (9778 pipelines, v0.1.1)
and the walk below (899); 10219 merged.

Measured with `work/cold.sh` (a fresh folder, `MESA_SHADER_CACHE_DISABLE=true`, RX 7900 XTX, RADV, Mesa 26.3.1) on S5's
walk (beach to jungle), `RX_VK_FRAME_TRACE=1`, presents 900 to 4860 (the stage). A development build prepares only with
`RX_VK_PRECOMPILE=1`; a release does it by default.

| run | pipeline waits | wait ms in all | frames over 20 ms (with waits) | slowest 120 presents |
|---|---|---|---|---|
| before (`work/runs/i1/cold0.txt`) | 290 | 832 | 38 (38) | 24.2 ms |
| the list and the user's play list only (`after_play`) | 210 | 101 | 2 (1) | 19.0 ms |
| the list and both shipped lists (`after_both`) | 212 | 3.0 | 21 (0) | 19.1 ms |

- The preparation on the first start: 54264 programs translated in 28.5-30 s on 12 workers, then the shipped list's
  pipelines (9684 and 9732) built into the pipeline cache in 2.9-3.2 s on 16 threads. 262 programs do not translate:
  30 are a network left out on this card, and 232 use an NVN stage 2 (slot 32) that does not lower ("unsupported native
  opcode"). Play never drew one of them (no such key in either list).
- With the user's list only, the zone change still compiled: 145 pipelines in one frame, 100 ms (present 1426). 435 of
  the 875 pipelines the walk used were not in that list. For 419 of them a record of the same stages was there, with
  another blend state (316) or vertex strides (252), so another route or other settings add pipelines that a list does
  not have. The walk's own list is the test route here, so `after_both` measures the release set-up, not how well a
  list carries over.
- `after_both`'s 21 slow frames (20-26 ms, one 49 ms) have no pipeline wait, with the game 2-7 ms and the draws about
  1 ms. They are pacing, not looked into.
- `make_game.py` into `work/i1/game` makes the same list (byte for byte), ships 10219 pipelines, and prints no
  traceback. A second build says "not made again" (0 s). `tests/run_all.py`: 562 passed, 0 failed, 79 skipped (before:
  561, 0, 79).
- Not checked: NVIDIA, Windows, 4K, the issue's GPU (section 7).

### 2026-11-19: the third sync, to Longshot `v3.0.0`

- `scripts/sync_upstream.py --to v3.0.0` (`09cbdd97`, Longshot's first stable release, 68 commits past `9af4808f`),
  run by hand in a worktree: 395 files changed in the imported paths, 365 applied (199 of them new, 90 of those
  `third_party/tracy/`, a new part whose note `scripts/check_third_party.py` accepts), 30 not applied (29 not tracked
  here, and the stand-in). Six files conflicted, in 10 places:
  - `gpu/vk/vk_api.h`, `host/rx_backend.c`: Longshot's `ab_frame` (the A/B's side of a frame, its version 34), then
    this fork's `origin_lower_left`, now version 35. Longshot's new `tests/test_hos_ab.py` asserted that `ab_frame`
    ends `MkwVkHost` and the table; it now finds it one before this fork's member.
  - `nx2/make_game.py`: Longshot's hot list (`hot_list_for`, a committed `assets/profiles/hot_funcs.txt`, which is not
    carried: the build takes a developer's `work/hot_funcs.txt` or none, as before) beside this fork's `npdm_name`
    and prompts, and the environment of nx2/kit.py's names. Longshot's first install now reads the assets while the
    game is translated (`overlap_package_read`); its `read_assets` takes this fork's romfs-or-data-title check and
    moves `aoc/` too. Under that overlap `INHALE_ROMFS` is set before the data title is there (the code title's
    empty `romfs/`); nothing in the lift or the build reads it. `tests/test_make_game_cache.py` has a check of the
    data title arriving beside translation, and Longshot's overlap check expects this fork's message.
  - `tests/test_bound_keys.py`: Longshot's check of the side mouse buttons in the game's menus gives them to X and Y
    here, since this fork's left and right buttons are B's and L's.
  - `nx2/test_leaf.py`: Longshot's timing file beside this fork's `map_rw` and signal handlers.
- The stand-in `nx2/oot_patches.py` gained `touches` (never) and `mentioned_addresses` (none): the lift now asks
  them which functions keep their registers in the context, as Longshot's registers as locals arrive (`A64_LOCAL_REGS`,
  on by default). The 45 other new names are used only by Longshot's checks of its own patches, which are left out.
- Longshot's new marking rule for host writes to guest memory (`hos_guest_copy`, `HOS_WRITTEN`) found this fork's
  built-in font copy in `host/kirby_hle.c`; it uses `hos_guest_copy` now. Its check,
  `tests/test_host_guest_writes.py`, fails in Longshot's own tree at `v3.0.0` (Longshot's `host/nn_nfp.c`,
  `host/hos_main.c`, `host/oot_menu.c`) and is left out.
- `gpu/vk/perf_report.h` had one em dash in a comment (the punctuation rule, `tests/test_hygiene.py`): a colon now.
- Telemetry stays off: the renderer's performance summaries post to `perf_reports=` of the game folder's
  `inhale_version.txt`, which `make_game.py` writes from `nx2/addresses.ini`, whose keys are empty. The Discord
  status has no application id.
- Checks: before the sync `tests/run_all.py` had 561 passed, 0 failed, 79 skipped (no Vulkan or SPIR-V headers given).
  After it, 18 failed; Longshot's own tree at `v3.0.0` on the same machine had 39 failed. Five of the 18 fail there
  too and are left out with the C file one compiles; 13 are bound to things left out (`builder/`, `assets/`,
  `mise.toml`, `.forgejo/`, `scripts/tools.py`, `scripts/check_windows_files.py`, and the text of Longshot's
  `nx2/oot_patches.py`). `PROVENANCE.md` has the lists. After that: 600 passed, 0 failed, 80 skipped;
  `scripts/rename_full.py` 0 places, `scripts/check_third_party.py` 14 parts as their notes say.
- Not run in the game. Changes that alter what this game runs by default, none measured here: registers as locals in
  the lift, lifted stores marking only GPU pages (`RX_MARK_BITMAP`), `nn::os::YieldThread` giving up the virtual core
  only (`HOS_OS_YIELD=1` as before), temporary pipelines for required draws, threaded rendering's Auto by physical
  cores, the correctly rounded FMA on CPUs without FMA3, and the first install's overlapped unpack.

### 2026-11-19: issue #1, dynamic resolution

The question (an RTX 5080 at 4K): "not sure if dynamic resolution is disabled here or not". It was not, and the 4K
output was not a 4K picture. Measured with `RX_VK_PASS_TRACE=1 RX_VK_PASS_TRACE_AT=300` (each pass's size, two frames
every 300 presents) on S5's walk; the scene's size is the colour grading pass's (`5be22000a0782116`).

- At `HOS_OUTPUT_RES=3840x2160` the scene drew at 2560 x 1440 at most, and at 2240 x 1260 and 1862 x 1048 at times
  (1536 x 864 on the title screen). The game's own pass (`272f3b6f806b3a33`, one draw) stretched it to the output
  (`work/runs/i1/dynres4k.txt`). With `RX_VK_TS_SCALE` 0.001, 0.1 or 1 the stage stayed at 2560 x 1440 after the first
  frames of the walk (`dyn_ts0001`, `dyn_ts01`, `dyn_ts1`): the clock the renderer reports does not change the level here.
- Where the sizes come from: data. `basil/ScnCommon.bin` of the data title (an XBIN) holds at 0x97ca0 six docked levels
  as (index, width, height), 2560 x 1440, 2240 x 1260, 1862 x 1048, 1536 x 864, 1280 x 720, 854 x 480, then five sizes
  of another set (1920 x 1080 to 640 x 360) and the load thresholds (1.0, 0.97, 0.88, 0.84, 0.03, 0.95, 0.65). The game
  makes a set of scene targets at each level (`nvnTextureBuilderSetWidth` from `main+0x63e8dc`, 2560 to 1536 wide) and
  steps between them by GPU load. Found by a store probe in the lifted C (each store of 1862 or 854, the function
  logged: `L_8068aa74` copies the list, `main+0x6f9470` and `main+0x899ef4` read it).
- Not the cause, ruled out on the way. (a) The code's own sizes: the graphics system writes 2560 x 1440 into a list of
  six sizes at `main+0x64fbac`, `main+0x65ef80` and `main+0x66e270`, and `main+0x660dc0` clamps to the largest of
  `main+0x9aaa70` (1920 x 1080, 2560 x 1440, 3840 x 2160; mode 3 here). The game takes 3840 x 2160 as its x1
  (`main+0x6611d4` divides by it). Those three constants raised to the output size (`lifter.after`, `work/runs/i1/res_patch/`)
  made the targets 3840 wide, and the passes stayed at 2560 x 1440. With the table scaled they are not needed. (b)
  DLSS: the executable loads every `nvnDlss*` proc (the host answers device integer 0x5A with 0, and `main+0x63e7a0`
  makes a capability bit of it), but no code calls any of them (no use of their GOT slots outside the loader at
  `main+0x63d000`; with 0x5A answered 1 and every DLSS proc logging, none ran). This game has no DLSS route to turn on.
  (c) `HOS_GRAPHICS_SCALE=1.5`: the game does not size its frame by the float.
- The change: `host/kirby_res.c`, called from `nn_fs.c`'s read for each file read (one `(inhale)` block): where the
  bytes read hold the whole table and it is the one known, the six sizes are scaled by the output's width over 2560,
  each side even, when the output is 16:9 and wider than 2560 and at most 3840 (the largest of the game's table). Any
  other output, file or table is left as read. `HOS_DYNAMIC_RES=0` gave all six levels the first one's size: that is
  the default since ("Off by default" below), and `HOS_DYNAMIC_RES=1` the switch. Test: `tests/test_kirby_res.py`.

| run (S5's walk, RX 7900 XTX) | scene sizes seen | presents a second | GPU time a frame |
|---|---|---|---|
| 4K output, before (`dynres4k`) | 2560 x 1440, 2240 x 1260, 1862 x 1048 | 60.0 | 1.8-1.9 ms |
| 4K output, after (`a4k`) | 3840 x 2160, 3360 x 1890 | 60.1 | 2.9 ms (4.2 ms in two windows) |
| 4K, after, `RX_VK_TS_SCALE=1` (`a4k_ts1`) | 3840 x 2160, 3360 x 1890 (the first 1200 presents) | 60.0 | |
| 4K, after, `HOS_DYNAMIC_RES=0` (`a4k_fixed`) | 3840 x 2160 only | 60.0 | 2.9-3.2 ms |
| 2560 x 1440 output, after (`a1440`) | 2560 x 1440, 2240 x 1260 (unchanged) | 60.0 | 1.8-1.9 ms |

- The picture at present 1800 (the jungle) with the table scaled, against the game's 2560 x 1440 stretched: the same
  scene, the fog the game's (`work/runs/i1/ov4k_shots`, `base_shots`). Tried first through `HOS_FS_OVERLAY` with a
  scaled copy of the file (`work/i1/ov`).
- `tests/run_all.py`: 602 passed, 0 failed, 80 skipped (the tree before the change, after the v3.0.0 sync: 601, 0, 80).
  `scripts/rename_full.py` 0 places, `scripts/check_third_party.py` 14 parts.
- Not checked: NVIDIA, Windows, a 4K screen (the runs are headless at 3840 x 2160), an output between 2560 and 3840
  wide, the handheld set of sizes (left as the game's), whether a heavy scene steps down further on a slower GPU, and
  the UI at 4K against 1440p (the layouts are drawn after the scene, at the output's size).

**Off by default (2026-11-19, the same day).** The steps cost sharpness on a PC that has no need of them: in `a4k` the
scene dropped to 3360 x 1890 with the GPU at 2.9 ms of a 16.6 ms frame, and nothing here shows that the level follows
this PC's GPU load (`RX_VK_TS_SCALE` did not move it). So `kirby_read_done` now asks for the fixed size unless
`HOS_DYNAMIC_RES` is set to a number that is not 0, and never in the handheld profile.

- Docked, a 16:9 output wider than 2560 and at most 3840: the scene at the output's size, always.
- Docked, any other output (a 1080p monitor, 21:9): the scene at 2560 x 1440, always. Before, it could step down to
  854 x 480.
- Handheld (the menu's Profile row after a restart, or `HOS_HANDHELD=1`): the file as the game ships it, so the game's
  sizes and steps. This is the choice for a PC too slow for the fixed size.
- `HOS_DYNAMIC_RES=1`: the docked steps back, scaled as above.
- No menu row: the table is read once at the start, the Render resolution row is hidden for this game, and a row would
  offer a help that is not measured. One can be added on `kirby_scn_patch`'s `fixed` argument.

| run (S5's walk, RX 7900 XTX, `work/runs/i1/`) | scene sizes seen | presents a second |
|---|---|---|
| 4K output, default (`d4k`) | 3840 x 2160 only | 60.0 |
| 4K output, `HOS_DYNAMIC_RES=1` (`d4k_steps`) | 3840 x 2160, 3360 x 1890, 2792 x 1572 | 60.0 |
| 2560 x 1440 output, default (`d1440`) | 2560 x 1440 only | 60.0 |
| handheld, default (`hh_after`) | 1920 x 1080, 1600 x 900 | 60.0 |

- Handheld was looked at first, since the patch was taken to reach the six docked levels only. It does not hold. With
  the docked table fixed (`HOS_HANDHELD=1`, 1920 x 1080 output), the scene drew at 1920 x 1080 only in one run
  (`hh_before`, the tree before, `HOS_DYNAMIC_RES=0`), at 1600 x 900 and then 1920 x 1080 in two (`hh2`, `hh3`), and in
  one at 2560 x 1440 for the first 600 presents (the title screen) and 1920 x 1080 after: a docked level's size in
  handheld, larger than its output. That run's log was written over by `hh_after`. With the game's own table
  (`hh_steps`, `hh_steps2`, `hh_after`) handheld showed 1920 x 1080, 1600 x 900 and 1280 x 720, so its set does step
  here, and no docked size in those three runs. Hence the profile is asked (`hos_handheld`, one `(inhale)` line in
  `nn_applet.c`) and the file left as read in handheld, where no `kirby:` line is logged.
- `tests/test_kirby_res.py` failed on the tree before at the unset case, and fails at the handheld case with the
  profile not asked. `tests/run_all.py --strict` with `INHALE_VULKAN_HEADERS` and `INHALE_SPIRV_HEADERS` set: 674
  passed, 0 failed, 10 skipped (Windows, a Vulkan 1.3 device, Unicorn). `scripts/rename_full.py` 0 places,
  `scripts/check_third_party.py` 14 parts.
- Not checked: why handheld drew at a docked size in that one run, and whether it does with the game's own table (a
  level below the first then); a weak GPU, where the fixed 2560 x 1440 at a small output costs most; a window; NVIDIA;
  Windows; the Profile row changed in the menu (the runs set `HOS_HANDHELD`).

**The menu's 4K, on Windows and NVIDIA (2026-11-20).** The player then wrote that 4K chosen in the menu gave the same
picture as 2560 x 1440. The runs above set the output with `HOS_OUTPUT_RES`. These runs set `output_res=` in
`inhale_options.ini`, as the menu saves it, and leave the variable unset. They use S5's walk and the pass trace, as above.

| run (S5's walk) | `output_res=` | scene sizes seen |
|---|---|---|
| Linux, RX 7900 XTX (`work/runs/i1/menu4k`) | 3840x2160 | 3840 x 2160 only |
| Linux, RX 7900 XTX (`menu1440`) | 2560x1440 | 2560 x 1440 only |
| Windows, RTX 2080 SUPER (`work/runs/i1/aubox/menu4k`) | 3840x2160 | 3840 x 2160 only |
| Windows, RTX 2080 SUPER (`aubox/menu1440`) | 2560x1440 | 2560 x 1440 only |

- Each run logged `oe: output resolution` and `kirby: 3D frame` at its size. The Windows runs used v0.2.0's
  `inhale.exe`, which holds `kirby_res.c`, with a test `inhale_vk.dll` built from this tree (the 780M fix, `48eeccd`).
  They were headless, so they had no window.
- So the size reaches the table on both systems and both vendors, from the ini as from the variable. Nothing in the
  code was found to change.
- What is left is on the player's side:
  - The size is read once, at the start (`output_mode` in `nn_applet.c`, `kirby_read_done`). A change closed with
    "Later" applies at the next start only.
  - A window smaller than the screen shows the 4K frame scaled down.
  - The handheld profile keeps the game's sizes.
- The player's log settles it, from a start with 4K chosen. The lines that matter are `oe: output resolution`,
  `kirby: 3D frame`, `vk: swapchain` and `display:`.
- Not checked: a 4K screen, a window or full screen, the menu row changed and Restart now taken (the runs wrote the
  ini before the start).

### 2026-11-19: issue #1, the depth-of-field switch

The ask: "being able to disable depth of field". The game's DoF is `shader/DepthOfField/DepthOfField.bfsha` of the data
title: three programs, one vertex stage of their own (`20c3d9b7a221506d`, in no other `shader/` file) and three fragment
stages, `976a0ce23a971ed0`, `912173d38909e3fd`, `3fe01c0d0629e41f`. Those are the runtime code keys (`vk_shader.cpp`
`code_key`: FNV-1a 64 over the control section's 0xd8 bytes and the code area it sizes), computed from the file with
`kirby_shaders.py`'s walk.

- In play (S5's walk with `RX_VK_SKIP_CODE` set to the three keys, `work/runs/i1/dof_off.txt`) one program has them:
  `0383c5894eee303d` (vertex and `976a0ce23a971ed0`), the composite. It draws once a frame into the scene's HDR target
  (the deferred shading's), reading depth and the half-size blurred targets, after the colour grading's inputs and
  before the bloom. Left out, the target keeps the sharp scene, and every later pass reads the same target: the
  background is sharp, nothing is black or stale (present 1200, the beach's far trees, against a run with it:
  `work/runs/i1/dof_on_shots`, `dof_off_shots`). The two other programs did not run on the walk (cut scenes, not
  tried); leaving them out too is safe, since only DoF reads what they write.
- The row: Graphics, Detail, "Depth of field", On (the game's) or Off; `opts.dof`, saved as `depth_of_field`, out of
  the Quality presets. Hidden only while the other game runs (`kirby_row` in `row_shown`). Off leaves out the draws of
  every program with one of the keys (`gpu/vk/kirby_post.h`, a memo by program as `RX_VK_SKIP_CODE`'s; the call in
  `vk_draw.cpp` right after that block). The row is read at each draw, so it applies at once. The keys are hashes of
  this game's shaders, so another game's programs cannot match them, and they need no build id gate. Texts:
  `menu_i18n_inhale.h`.
- In play with `depth_of_field=0` in the options file (`rowoff`): the far trees sharp, as with `RX_VK_SKIP_CODE`.
  Tests: `tests/test_kirby_post.py` (the keys on made-up code strings, the memo, the call's place, the row's gate).
- Not checked: the row changed in the menu while playing (headless runs), cut scenes, later worlds.

### 2026-11-19: issue #1, what a DLAA-class anti-aliasing would have to work with (research, nothing built)

The ask: "DLAA/DLSS implementation into this game I think would do wonders". The back end's temporal chain
(`vk_temporal.cpp`: DLSS, DLAA, FSR 3.1, FSR 4, XeSS) is fed by the other game only: its upscale pass, its camera in
uniform buffer 3, its jitter (`nx2/oot_jitter.py`). What this game offers, read on a frame of the first stage (present
1500, 2560 x 1440 output; `RX_VK_DUMP=1500`, `work/runs/i1/dump1.txt`; the uniform buffers written whole by a temporary
dump, `work/runs/i1/dump2`, `dump3a`, `dump4`; program keys mapped to `shader/` files through `RX_VK_SKIP_CODE`'s log,
`map1.txt`):

- **No FXAA, no anti-aliasing at all.** `shader/Fxaa/Fxaa.bfsha` (code keys `70a47a2c6cd6f415`, `03a2f72e86791140`) and
  `shader/ToneMapping` never ran on S5's walk, the title to the jungle, 3600 presents (`map2.txt`). The scene is
  supersampled only where the output is smaller than the frame (a 1080p screen). So there is no pass to replace; a
  temporal AA is added, not swapped in.
- **Where it would sit.** The frame's post chain on the scene target (`#358`, R11G11B10 float, the scene's size):
  deferred shading `62830cf22f14b2ae`, the blurs, DoF `0383c5894eee303d`, bloom (`6e78d7ac90a71ceb`,
  `c6179b9128534d74`), then ScreenFilter `5be22000a0782116` (`shader/ScreenFilter`: tone map and the 16x16x16 grading
  table), which writes the tone-mapped picture (0 to 1) back into `#358`. Then Copy `272f3b6f806b3a33` (`shader/Copy`,
  the same program as every blit of the frame) draws `#358` into the window texture (`#1`, RGBA8), and the layouts draw
  after it. So the AA's input is `#358` after ScreenFilter, its output the window texture in place of that one Copy
  draw (told from the others by its target: the presented texture), and the UI stays out of it. The input's size moves
  with the dynamic resolution (section 9, "dynamic resolution"): the history must take a size change, or be reset.
- **Depth.** `#359`, D32S8 (the 24-bit depth's twin, section 9 S5), written by the G-buffer pass and still whole at
  ScreenFilter (the DoF composite reads it just before). Reversed Z: 0 is far, 0.016 the nearest here.
- **The camera.** Uniform buffer c16 (288 bytes), bound in the G-buffer, deferred, DoF, SSAO and ScreenFilter passes:
  +0x00 the projection, row-major, `[1.2063 0 0 0; 0 2.1445 0 0; 0 0 1e-05 0.1; 0 0 -1 0]` (16:9, near 0.1, far
  all but infinite, reversed Z), +0x40 the view as 3 x 4, then the camera's position, the aspect (1.7778), the
  half-angle tangents and the inverses. The CPU writes it each frame (`f_8082e090`, `main+0x80e090`; found by a store
  probe on its address, `0x7f5b5cc000`, which stayed the same over runs) from a camera object, through a 4 x 4 inverse
  (`main+0x84a060`, called from 14 places). Copies of the projection are elsewhere too: c6 +0x20 (written by
  `f_807af840`), c8 +0x40 with the product view x projection at +0x80, and a compute stage's c3 +0x1410. **No
  previous frame's matrix** is in any of them: the host would keep last frame's c16 itself.
- **Motion vectors: none.** The G-buffer is c0 RGBA16F (normals), c1 RGBA8 (albedo), c2 RGBA8, c3 R11G11B10 (light),
  c4 R8_UINT, depth: no velocity target. Camera-only vectors from depth and the two frames' view x projection are what
  FSR 3.1's own-inputs path makes for the other game (`vk_fsr3_inputs.cpp`).
- **Jitter: a site is not settled.** The projection reaches at least three buffers by different writers, so a jitter
  added to c16 alone (C after `main+0x80e0c8` in `f_8082e090`) would jitter the deferred pass's reconstruction and not
  the geometry, which reads c8. The place to add it is where the camera's projection is made, before those copies;
  that function is not found yet (the camera object `f_8082e090` reads is the lead).

What that costs, against the plan's three conditions (depth at the AA's pass, a reachable camera, a place for the
jitter): depth is there; the camera is there, but this frame's only; the jitter has no site yet. And without the game's
own motion vectors, everything that moves on its own (Kirby, enemies, water, particles) gets vectors of the camera's
motion only: with FSR 3.1 AA, XeSS AA or DLAA that shows as ghosting or smearing behind Kirby. A version without jitter
(the AA's history only, no sub-pixel offsets) is possible, and anti-aliases far less.

### 2026-11-19: the picture that stays wrong until `cache/` is deleted

The report: a game folder updated from v0.1.1 to main shows the 3D scene blurred at every start (the HUD sharp),
sometimes with smeared geometry, and deleting `cache/` cures it. The question was which part of the cache has to be
invalidated, how and when. Answer: none by hand. The programs in the cache were translated for the wrong depth mode,
and the fix changes the cache's stamp, so the first start of a fixed build drops them by itself.

Cause. The renderer asks the host for NVN's depth mode when it translates a vertex stage (`vk_shader.cpp`,
`convert_depth_mode = host->depth_minus_w()`), and puts the answer in the program cache's stamp (`translator_stamp`).
The host started with 1, near = -w (`host/nvn_native.c`, `depth_minus_w`: Longshot's game's mode, so that what is
prepared before its device exists comes out right). This game calls `nvnDeviceSetDepthMode` with near = 0. A shader
preparation translates with no game (`--prepare-shaders`, a build's last step) or before the game makes its device (a
start's own preparation), so each of the shader list's 54264 programs got a vertex stage that converts the depth,
z' = (z + w) / 2, and play then drew with them. The log said so at every start: `nvn: the depth mode is not the one the
prepared shaders were made for: their vertex stages draw wrong`. The stamp is read before the game's call, so it
matched and nothing was dropped.

It came with main, not with v0.1.1's cache: v0.1.1 had no shader list (section 9, "issue #1, the stutter of a first
visit"), so nothing was prepared and every program was translated in play, after the game had set its mode.

Runs (RX 7900 XTX, RADV, Mesa 26.3.1; headless; the user's save, which starts in Waddle Dee Town; the folders under
`work/runs/cache1/`, each with the build, the shader list and the shipped pipeline list, `RX_VK_PRECOMPILE=1` as a
release has it; `run.sh <folder> prepare|play <name>`, shots with `RX_VK_SHOTS`):

| folder | cache | programs made | picture |
|---|---|---|---|
| A | v0.1.1's (`work/game/cache`, copied) | `--prepare-shaders`, then play | blurred and dark (`A_p1`) |
| B | empty | `--prepare-shaders`, then play | the same (`B_p1`) |
| E | empty | the start's own preparation | the same (`E_p1`) |
| C | empty, no shader list, nothing prepared | in play | right (`C_p1`) |

- One frame of B and C pass by pass (`RX_VK_DUMP=2000`, `B_d1.txt`, `C_d1.txt`): the depth differs from the first
  depth pass on, and B's is 0.5 + C's / 2 everywhere. The scene's depth has a maximum of 0.5061 in B against 0.0122 in
  C, the shadow map 0.7358 against 0.4717. Every pass that reads depth then goes wrong: the depth of field takes the
  whole scene for far and blurs it all, and the lighting comes out dark. With Depth of field Off the blur goes and the
  rest stays, which is how the row looked like a cause.
- Two suspects that are not it. The player's pipeline state list (`inhale_pipeline_states.bin`, which survives an
  update unstamped): B and E have none and are as wrong as A. The storage buffer pass's pointer answers
  (`IsCbufStorageBufferPointer`, answered from bound buffers, so "no" for everything before the game): with
  `RX_VK_PTR_DIAG=1` the 183 programs C's play translated have the same counts of bound and searched accesses as the
  same keys in a preparation (`C_p1.txt`, `D_prep.txt`).

Fix. `nvn_depth_minus_w` answers the game's own mode until the game sets one: 1 for Longshot's game (by its build id),
0 otherwise. `tests/test_depth_mode_start.py` cuts the three pieces out of `host/nvn_native.c` and checks both games,
the report of a mode that differs, and a call made before anything asked. Before the fix it fails with "the mode before
the game sets one is not the game's".

After it, with the same folders:

- E, whose cache the build before the fix had prepared: `pipeline cache: 4 files made for another translator dropped`,
  `program cache ...: 0 program keys kept`, the preparation again (33.7 s), no depth mode line, and the picture is C's
  (`E_fix1`).
- A from v0.1.1's cache again, state list kept: `--prepare-shaders` (`A_fixprep.txt`: 20345 pipelines, 180 variants by
  their textures), then three starts, with Depth of field On, Off (`depth_of_field=0`) and On again: right each time,
  86404 program keys kept, no depth mode line (`A_fix1`, `A_fix2_dofoff`, `A_fix3_dofon`).
- So an install needs nothing done to it: the stamp holds the mode, and a cache made for mode 1 is another
  translator's to the fixed build. That costs one preparation, and it also drops the right programs a v0.1.1 folder
  made in play, since their file carries the same stamp.
- `tests/run_all.py`: 604 passed, 0 failed, 80 skipped. `scripts/rename_full.py`: nothing to rename.
  `scripts/check_third_party.py`: 14 parts as their notes say.

Not explained: why deleting `cache/` cured it for the reporter. Here a start that prepares by itself (E) was as wrong
as the build's preparation. Programs translated in play are right (C), so a start whose preparation was skipped or
stopped would give the right picture; that was not tried.

Not checked: a window (all runs headless), NVIDIA, Windows, 4K, the Depth of field row changed in the menu while
playing (the option file was edited between starts), the smeared geometry of the second screenshot (not seen in these
runs; a wrong depth in every vertex stage is a likely cause, not a shown one), and the AMD Anti-Lag 2 row (nothing of
it is kept on disk or read by the translator).

For Longshot, which has the same path: the mode the host starts with is one game's, and a game that asks for the other
gets every prepared program wrong with only a log line to show for it. The stamp cannot catch it, because it is read
before the game's call. A game folder could keep the mode the game last set, or the preparation could wait for it.

### 2026-11-19: issue #2, no rumble in the game

The report: the menu's Rumble strength slider shakes the pad, the game never does.

Cause. The game plays its rumble from files (`aoc1:/hidvib/**/*.bnvib`, 340 of them) with a player of its own, not
the SDK's `VibrationPlayer`: a play request (main+0x851240) builds the file's object (main+0x850120), which calls
`nn::hid::ParseVibrationFile`, and plays only when the info's first word (`metaDataSize`) is not 0; each tick
(main+0x84f280, the second "Vibration" thread) reads a sample with `nn::hid::RetrieveVibrationValue` and sends it
with `nn::hid::SendVibrationValue`, which `host/nn_hid.c` has. The lift stubbed the two readers, as it does every
free function of an OS-facing namespace the runtime does not define (`nx2/standalone.py`, `os_facing`): the stub's 0
is a success with the info left zeroed, so no file ever played. Both are plain code in the sdk that reaches no
service.

Fix: the two names are in `LIFTED` (`nx2/standalone.py`), so they run as the SDK has them; the lift then says 135
stubs, not 137. `tests/test_lifted_vibration_file.py` holds it. `make_game.py` lifts again by itself: the file is one
of the translator's, which the lift's key covers.

Checked in the game (headless, `INHALE_DUMP=$PWD/work/dump work/boot.sh rumble_after 90 --lift`: 60 fps, nothing new
in the log), and the two lifted functions called from gdb in that build on two of the game's files:
`ParamatterBlueIcicleLanding.bnvib` gives meta 4, format 3, 200 Hz, 349 samples, no loop, and its first sample (bytes
`01 76 04 9f`) low 0.0039 at 128.8 Hz, high 0.0157 at 313.1 Hz; `RollingLoop.bnvib` gives meta 12, 680 samples, loop
396 to 666. So a byte is amplitude / 255 and frequency 10 x 2^(byte / 32) Hz.

Not shown: a file played in the game. Two scripted walks through the first stage (`work/runs/i2/`) made no play
request at all, before or after the fix, so no run here has the game's own call of the readers or a pad that shook.
Also seen and not explained: a script of the game switches a player's rumble off (the native at main+0x72e8a0, called
every frame) about 2.3 s after the last scripted press, in both walks (presents 4218 and 8122), and on again at the
stage's start. If it follows the pad's activity that is the game's own rule; if it follows something this runtime
reports about the pad, it is a second cause.

### 2026-11-20: issue #4, a crash to desktop in play (not explained), and the record's `guest_trap`

The report: v0.1.1 (`ff044b2a`, the release build) on Windows 10, a Ryzen 3 3200G with its own graphics (4 threads,
the weakest PC this has run on), every setting at its default, closed after 412 s of play. One crash record and the
crash window's report; no log (the game logged to no file).

What the record says. `reason: hos_fatal` on `Thread_8091ce68`, one of the game's seven job workers, with the host
frames `hos_fatal`, `a64_on_trap` (`host/hos_thread.c`), `site_call` (`third_party/a64-kit/rt/a64_rt.c`): a trap of
an indirect branch, to an address with no function. The guest's `lr` 0x80683f38 is in main+0x663ee0 (`f_80683ee0`),
which is the game's `free`:

- it takes the calling thread's current allocator from thread-local storage (`f_8091d0c0`) and calls that one's
  virtual at +80 (slot 10) with the block (`x1` = `x19` = 0x7883eebc00 in the record);
- the allocator here is the game's static default one at 0x82c1fb50: member +352 of the static at 0x82c1f9f0, which
  `f_80681ba0` builds, vtable 0x82bbd520;
- that vtable's slot 10 is `f_8088b848`, a thunk with no frame: the override allocator at +16 if there is one, else
  the base at +8, and a `br` to that one's slot 10.

At the stop `x8` is 0x7ad3071000 and `x2` 0xff000498: a vtable read from heap data, and a target in it that is no
code. So an allocator object that a worker's `free` reached was not an allocator: freed, written over, or not built
yet.

Not known: which object was bad (`x0` is still 0x82c1fb50 at the stop, which the thunk as lifted does not leave so;
the static's vtable may not be the one `f_80681ba0` stores), where in the game it happened, and whether the builds
since v0.1.1 still do it. None of the 12 commits since is aimed at it; the third sync changed `host/nn_os_sync.c`,
`host/hos_thread.c` and the lifter (registers as locals), which can move a race's timing and is no evidence that it
is gone. Not reproduced here, and no fix: the record does not name the cause. Asked of the reporter: the place, how
the game is started (no log file), and a run of the nightly. Worth trying once the place is known: four cores pinned
and a session played by hand.

The stutter of the same report is issue #1's and #3's: v0.1.1 compiles each pipeline when it is first drawn, and the
builds since prepare the shipped lists before the title.

What changed: the crash record now keeps a trap. Its `reason` is a fixed label, never the formatted message
(`host/hos_crash_record.h`), so the trap's text ("indirect jump to an address with no function at 0x...") was in the
log alone, and this report had none. `a64_on_trap` now notes the address and the kind (`host/kirby_trap_note.c`), and
the record has one more line after the guest's backtrace:

    guest_trap: 0xff000498 indirect jump

The kind is one of `trap`, `branch to a non-function`, `indirect call`, `indirect jump`, `svc` and `other`, never the
runtime's text (an svc's has a number formatted into it, and a text this does not know becomes `other`). A fatal that
is no trap has no such line. `tests/test_crash_record.py` holds it with three trapping children. Not checked: the
Windows build's record (the test and the game ran on Linux).

### 2026-11-20: issue #7, shadow resolution

The issue asks for a higher LOD, texture quality and shadow quality. Shadows first, as the Graphics tab's Shadow
resolution row (upstream's, `opts.shadow_res`, option 56, its Auto by the card's memory), which was hidden here as one
of the other game's rows.

**What the game draws.** One square shadow map, a D16 depth target, drawn in three passes a frame (the first clears it:
land, decor, characters, by the names `ParallelShadowMapLand`, `ParallelShadowMapDecorDefault` and
`ParallelShadowMapEffectAndChara` in `basil/ScnCommon.bin`), then blurred twice through two R16 targets of its size
(program `21240c5afa2d2e61`, which the bloom uses too). In the pass trace (`RX_VK_PASS_TRACE=1
RX_VK_PASS_TRACE_AT=300`, S5's walk, `work/runs/i7/base.txt`): 1000 x 1000 in two passes before the stage (presents 300
and 600), 1400 x 1400 at every traced frame of the stage from 900 to 3900. It did not change over the walk: no sign of
`_changeShadowMapSizeAuto` stepping it. Handheld (`HOS_HANDHELD=1`, `hh3.txt`): 980 x 980.

**Where the size comes from.** Data. `basil/ScnCommon.bin` of the data title holds, after the names
`UseCustomShadowMapResolution`, `ShadowMapResolutionConsole` and `ShadowMapResolutionHandheld`, the u32 pair 1400, 980
at 0x173ec40, the only such pair in the dump. Written to 2800 as the file was read (a test build), the stage's map was
2800 x 2800 at every traced frame (`x2800.txt`). The file is read once, whole, at the start, after the renderer has
resolved its Auto (the log's `policy: auto settings` line comes first), so the row's value is known then, and a change
applies after a restart. Not found: the body of `get_CurrentShadowMapResolution` and what
`GetResolutionArrayForShadowMap` holds, so the game's own larger sizes, if it has any, are not known.

**The change.** `host/kirby_shadow.c`, called from `kirby_res.c`'s read hook: the console size becomes 2800 (High,
twice the game's) or 4096 (Highest; the largest side every Vulkan device must allow, so no limit to ask for), never
lower than the file's, and only where the pair is the one known (another version of the file is left, and the log
says so). The handheld size stays the game's. The menu shows the row for this game (`is_oot_row` no longer lists it) and
gives it this game's help and hints when the host says which game runs, as the Quality preset's (`kShadowHelpKirby`,
`hn_shadow_res_kirby`, translated in `gpu/vk/menu_i18n_inhale.h`). Auto keeps upstream's tiers: the game's size on 4 and
6 GB, High on 8 GB, Highest from 12 GB.

**The restart.** The first build of the row said "Applies after a restart" but did not ask for one: the "After
restart" tag and the question on closing the menu come only from rows with `Row::restart` set, given a slot once by
`restart_init`, and upstream's row has it off (the sun's cascades follow it each frame). So, for this game only:

- `menu_option_set`, when the host says which game runs, sets the flag with the help. The host says so in `rx_start`
  before the renderer starts, so the slot is taken.
- The restart compares the size drawn, `menu_shadow_res()` with Auto resolved, not the row's value
  (`inhale_restart_value`, called from upstream's `row_restart_value`; upstream's checks that cut that function stand
  it in with one line). A preset that moves the memory tier under Auto counts; Auto on the game's own size and Game's
  do not differ.
- The start value is the level the game got. `restart_init` runs in `pick_device`, before Auto's tier is known, so its
  value is a guess. `kirby_shadow_read` sends the level it applied (Game's too) through `option_set`
  (`HOS_OPT_SHADOW_RES`), only where the read holds the known pair, and the menu takes it as the slot's start value.
  A file whose pair is not the known one sends nothing, and the start stays the guess.

The other rows were checked the same way, their help against the flag and against what this game reads once:
upstream's table agrees with its help. Output resolution and the Profile (read at the ScnCommon.bin read), GPU
device, Game language and Button prompts take a restart already. Depth of field (each draw), Anisotropic filtering
(the samplers made again) and the controller, mouse and motion rows (polled) apply at once. Shadow resolution was the
only one wrong.

**Measured** (RX 7900 XTX, Mesa, 3840 x 2160 output, S5's walk, `work/runs/i7/l1.txt` to `l3.txt`):

| Level | Map | Video memory (3 targets, 6 bytes a texel) | GPU time a frame | Presents a second |
|---|---|---|---|---|
| Game's | 1400 | about 12 MB | 2.7 ms | 60.0 |
| High | 2800 | about 47 MB | 2.9 ms | 60.0 |
| Highest | 4096 | about 101 MB | 3.2 ms | 60.0 |

Shots at full size (`fshots_l1/`, `fshots_l3/`, present 2400 the same pose in both): no acne and no other new fault on
the ground or the characters; the gain is small, because the game blurs its map, so its edges were soft already: they
are a little tighter. `RX_VK_LOG_CASCADE_BIAS=1` (`bias3.txt`, Highest) logs its first 40 draws only, all the title's
1000 x 1000 map: no depth bias asked (enabled 0, units 0, slope 0); the stage's draws were not reached by it. Whether
the projection snaps to the texel size (shimmer as the camera moves) is not seen in still shots.

**Leads for the rest of the issue, nothing built.** Textures: the game ships one size of each; the Anisotropic
filtering row (up to 16x) already shows for this game. LOD: `LodCullingController`, `UseLodModel`, `IsUseLodCulling`,
`FarDistCullingDist`, `_bf_ViewDistance` and `EffectLodLv` in `basil/ScnCommon.bin`; near `IsUseLodCulling` the same
kind of name-then-value block holds `ActorFadeStartDistance`, `ActorCullingStartDistance`, `DecorFadeStartDistance` and
`DecorCullingStartDistance`, a place to start.

`tests/test_kirby_shadow.py` holds the patch on made-up bytes (each level, the handheld size, another file, a read
that does not hold the pair, bytes not known, a level not known), the call from the read hook, the level told to the
menu only where the known pair was read, the menu's row and texts (their sizes and memory computed from the patch's),
and the row's restart: the flag in this game only, the size drawn compared, the start value taken under `menu_mu`.

### 2026-11-20: coloured discs on a Radeon 780M (AMD's Windows driver)

The report: v0.2.0 on Windows 11, an AMD Radeon 780M (integrated, driver 26.11.2, `0x8001a0`), the first run on AMD's
Windows driver and on an integrated GPU. The first stage's beach is drawn right, with solid red, orange, yellow, green
and white discs over it and a dotted line, all on one straight line through the middle of the picture. The same PC's
RTX 2080 SUPER draws it right, and so do RADV on an RX 7900 XTX and on a Ryzen 9 7900X's integrated graphics.

What it was not, each ruled out by a run:

- The occlusion counts. The game makes no samples-passed report in that frame: its two counter reports are timestamps
  (`nvn: the game reports counter type 0`). `RX_VK_OCC_QUERIES=0` changes nothing.
- The ASTC textures kept as BC3 on an integrated GPU. No draw of the frame samples an ASTC texture; `RX_VK_ASTC_BC_ALL=1`
  on the RX 7900 XTX, the whole integrated policy on RADV (`RX_VK_DEVICE=0`) and "ASTC as RGBA8" on the 780M change
  nothing.
- The player's settings (the 780M's options file on the RX 7900 XTX), NaN tests on bits (`RX_VK_NAN_BITS=1`), native
  fragment shuffles (`RX_VK_FRAG_SHUFFLE_FALLBACK=0`), the driver's optimizer (`RX_VK_NOOPT=1`), every fragment sample
  at level 0 and BC views cut at their 4 x 4 level (two test builds): the discs stay.

What it is. A frame dumped pass by pass on both PCs (`RX_VK_DUMP=1500`) differs first in the scene's target after the
lighting pass: its largest value is 3.4 on Linux and 35,330 on the 780M. At full size the wrong texels are in 8 x 8
blocks every 16 pixels along the picture's diagonal, on one side of it or on both: the blocks that the two triangles
of the pass's full-screen draw share. The lens flare is not at fault: the game's bloom and its flare, made from the
scene, turn each such texel into a disc and a row of ghosts on the line through the centre.

The lighting pass (program `62830cf22f14b2ae`) draws into the scene's target and samples it in the same draw
(`c0:#364`, `t15:#364` in the dump): the G-buffer pass left the light each surface gives off there, and the lit colour
is written over it. The tone map (`5be22000a0782116`) reads and writes the scene the same way. The log had said so on
every PC: `vk: a draw (program 62830cf22f14b2ae) samples targets it writes (mask 0x1, 2560x1440)`. The console's GPU
gives each pixel what was there before the draw; Vulkan leaves such a read undefined, rule 5 of section 4 left the draw
as it was, and AMD's Windows driver is the first seen to answer it wrongly. The 8 x 8 blocks fit a colour target kept
compressed by the GPU, read while one of its blocks is half written; that part is a reading of the picture, not
something measured.

The fix (`gpu/vk/vk_feedback.h`, `gpu/vk/feedback_copy.h`): a draw that samples a colour target it writes is drawn into
a copy of that target. The target is copied into the copy, the draw's pass is begun with the copy's view while the draw
samples the target, which nothing writes then, and the copy is copied back when the draw ends (`feedback::Draw` in
`draw`, on every way out of it). On by default on AMD's Windows driver only; `RX_VK_FEEDBACK_COPY=1` or `0` on any
driver. Upstream has the same undefined read and no fix for it (looked at `08994a9`, 2026-11-20): the rule is in files
of this fork, and `gpu/vk/vk_draw.cpp` has the lines that call it.

Checked, on the 780M, headless over ssh with a test `inhale_vk.dll` built there from the release's sources and this
change (`work/runs/lf/aubox/`):

- before, `base/vk_001500.jpg`: the discs. After, `fix/last.jpg`: none, at present 12,600. The same DLL with
  `RX_VK_FEEDBACK_COPY=0`: the discs again (`fixoff/vk_003000.jpg`).
- the walk from the beach into the jungle (`final/sheet.jpg`, the code as committed): as on Linux, and the log's
  `vk: 2.0 colour targets a frame drawn into a copy` for all of it: the two draws named above and no other.
- the cost, the same view and DLL: GPU time 16.7 ms a frame without the copies, 18.4 with them; 53.7 presents a second
  against 49.6. Four copies of a 2560 x 1440 target a frame. A draw that sampled a copy and wrote the target would need
  two; it needs the sampled view made again on the copy, with its format and swizzle, and the draw's descriptors kept
  from reuse. Not done.

On Linux with `RX_VK_FEEDBACK_COPY=1` (RX 7900 XTX): the same picture, 60 presents a second, 1.9 targets a frame.

`tests/test_feedback_copy.py` runs the rule and the copies' own code against stand-ins for the Vulkan calls (the copy
in, the pass's view, the copy back to the target's level and layer, a copy each for two targets of one draw, what
cannot be copied left alone), and reads the draw for its order. A second reader went through the change cold: two
targets of one draw shared a copy as first written (not this game's case; fixed, and in the test), and a frame dump
reads such a pass's target before the copy back (`gpu/vk/vk_feedback.h` says so). Not modelled by the test: the GPU,
the driver, the parallel replay's threads.

Found on the way: a row added to `gpu/vk/switches.def` does not compile `vk_main.cpp` again here (`nx2/build.py`
`HEADER_EXTS` has no `.def`; upstream's has, a sync brings it), so a build that kept its objects says
`RX_VK_FEEDBACK_COPY is set, and is not a switch of this build` and then obeys it.

### 2026-11-20: issue #6, the crystal overlay drops out for a frame

The report: "texture flickering" in the first Star-Crossed World stage (nightly `5b9dc0c`, an RX 7900 XTX on RADV,
2560 x 1440). In the player's screencast the stage's crystal covering is missing over large parts of the picture for
exactly one presented frame (the floor back to grey paving, the walls back to grey) and right again in the next. The
holes have the shape of 32 pixel tiles. The flash detector's rule run over the screencast finds 5 such frames in 195.
It shows in a jump and, at another place, while the camera turns.

What it was not, each ruled out by a run of the player's at the place (the logs `i6-*.txt` of those runs):

- The render thread, the write-back at a part's end, the mirror, late data, the frame gate: `RX_VK_ASYNC=0`,
  `RX_VK_CHUNK=0`, `RX_VK_MIRROR=0`, `RX_VK_SUBMIT_DELAY_US=3000` and `RX_VK_FRAME_GATE=0` each leave the dropout.
- A draw or a dispatch left out. With the detector and the pass trace on (`RX_VK_FLASH=1 RX_VK_PASS_TRACE=1`,
  `i6-flash2.txt`), a bad frame and its two neighbours have the same passes, draws and dispatches.
- Texel buffers. The tables the covering is drawn from are images, 80 x 45 x 32 and 80 x 45 x 64, written by compute
  dispatches.
- The capture rules (rule 2 of section 4): `RX_VK_MEM_CHECK=1` counts 0 breaks in 28,800 submits.
- Upstream has no fix for it (looked at `89c3d21e`, 2026-11-20).

The frame's order (`work/runs/i6/order1.txt`, `HOS_NVN_SYNC_LOG` and the pass trace). The game has two NVN queues, and
each frame its render thread

1. submits A1 on the first: a chain of tile dispatches, the shadows, the G-buffer, the lighting, the window's blit;
   takes a fence, flushes;
2. submits B on the second: three compute dispatches, of which `6c332c13...` builds the 80 x 45 x 64 grid at
   `0x7f76190000` from lists the CPU wrote, then `2c32cb11...` and `6e448e47...`; takes a fence, flushes;
3. presents, and submits A2 on the first (the exposure passes); takes a fence, flushes.

The main thread then waits for the three fences. No `nvnCommandBufferWaitEvent` passes between the queues, so rule 1
of section 4 had nothing to honour.

The cause. A1's G-buffer draws sample the grid that B writes. The replay runs submissions in arrival order on one
Vulkan queue, so those draws always read the grid of the frame before. On the console the two queues run side by side,
and B's three dispatches are done long before A1 reaches its G-buffer pass. A grid one frame old is wrong against this
frame's lists where the lists change: a jump, a camera turn.

The fix (`host/kirby_queue.c`, and the lines of `host/nvn_native.c` that call it): the first queue's submission is
held, and handed to the replay after the second queue's next one (B, then A1). It also goes before the first queue's
own next submission, and at a present, a queue finish or a sync wait for its own fence. One submitted right after a
present or a finish (A2, which nothing would overtake) is not held. A queue flush hands nothing over: the game flushes the
first queue right after A1. Nothing is held until a second queue has submitted, and the log then names the two
(`kirby: two queues: ...`). A fence taken on the held submission is set to its number at the hand-over, and a wait for
that fence hands over first: a first test build that guessed the number stalled twice for 10 s while loading.
`HOS_KIRBY_QUEUE_ORDER=0` gives arrival order back.

Which waits hand over was settled by two runs. Every wait handing over (the test build, and `work/runs/i6/fix1.txt`)
lets a wait of the main thread for the frame before, falling between A1 and B, send A1 first: arrival order for that
frame. Only the wait for the held one's own fence (`fix2.txt`) stalled five times for 10 s while loading: the main
thread waits for A1's fence first, with A2 still held, and the replay sends a submission's work to the GPU when the
next one follows it (its batched submits), which A2 was until then; `vk: wait for fence 78 (done 77, pushed 79)` is that
wait timing out. A2 handed over at any wait (`fix3.txt`) still stalled at the start in 2 of 6 boots with the render
thread: the main thread handed A2 over just before waiting for it. So A2 is not held at all, and goes at its submit as
before the fix. That still leaves the stall below.

What the fix changes besides the order:

- A held submission is captured when it is handed over, not at its submit (rule 2 of section 4 captures at the
  hand-over): A1 at B's submit, A2 at the main thread's first wait or the next frame's A1. Upstream's `HOS_NVN_HOLD`
  did the same to another game and made it worse; here the runs below show no harm.
- A1's hand-over is made by the render thread at B's submit; the main thread hands over only in a frame without B.
- What the game hands the replay that is no submission (a texture's registration or release, rule 3 of section 4)
  between a held submission's submit and its hand-over gets there before it. The game keeps what a submission names
  until it has waited for its fence, and that wait hands over; nothing wrong was seen. Not looked for beyond that.
- A recording's copy is freed once the replay has passed the submissions made when the game let its memory go
  (`release_copies`, `sweep_overwritten_copies`). A held submission is made and not yet counted by the replay, so
  those two count it (`kirby_queue_pushed`), as they count upstream's held ones.
- The first frame in which the second queue submits is still in arrival order, and a first queue made again at
  another address would no longer be held (the game makes its queues once). The held queue is the one of the first
  submission ever, not one known by name: a start that submitted on the compute queue first would hold the wrong one,
  and the log's line would show it.

Checked:

- A test build that handed B over before A1 behind a switch (`TEMP_I6_BFIRST=1`, not in the tree), played by the
  reporter at every place the dropout had shown, with the detector on: 0 `flash at present` lines in 27,840 presents
  and none seen (`work/runs/i6/user-bfirst.txt`). The same build without the switch: the dropout, seen and detected
  (`user-plain.txt`).
- Headless, the code as committed, S5's walk (`work/runs/i6/fix3.txt`): 60.0 presents a second, 0 polls timed out,
  GPU time 3.2 ms a frame as before, and the pass trace of frame 4200 has B's dispatches (`2c32cb11...`,
  `6e448e47...`) first, where `order1.txt` has them last.
- `tests/test_kirby_queue.py` cuts the six entry points out of `host/nvn_native.c`, compiles them with
  `host/kirby_queue.c` and stand-ins for the replay and the virtual core, and makes the game's calls: the order B, A1,
  the present, A2; a frame without B; two submissions in a row; a wait for the held fence, and for another with A1
  held and with A2 held; a finish;
  every fence its submission's number; the count for the recordings' copies; the switch both ways and
  `HOS_NVN_HOLD=1`. Before the fix it fails with `the replay got "A1 B P A2", wanted "B A1 P A2"`. Not modelled:
  threads (the render thread submits while the main thread waits), timing, the replay, the recordings' copies
  themselves (that their two places use the count is read from the text).
- A second reader went through the change cold and found three things in it as first written. Any sync wait handed
  the held submission over (the paragraph on waits above). The recordings' copies did not count the held submission
  and could be freed under it: counted now. And the third bullet of the list above, which is left as it is. Its
  remarks that stand: a thread can wait for the lock with its virtual core held, for as long as another thread's
  hand-over takes (no deadlock: the core is taken again only after the lock is let go); the held fence is a pointer
  into the game's sync object, written at the hand-over. The rule for A2 was written after that reading and has had
  no second reader.

The stall at the start, fixed: a 10 s stall at the start, with the render thread and batched submits (RADV). Headless boots with
the sync log (`work/runs/i6/v4boot-*.txt`, `v4off-*.txt`), the frame gate on (this tree's default): with the fix 3 of 6
stalled once early (fences 80 to 100, the first frames of the title), without it 1 of 6 (fence 2716, the stage's load).
Each is a wait for the last submission of a frame, `vk: wait for fence N (done N-1, pushed N)`. That submission comes
after the present, so the frame gate holds it until the wait lets it on (`gate_need_value`); the wait then sends the
batched submits to the GPU and waits, and the render thread records the submission after that send. It sends a batch
itself only when the GPU is idle (`batch_gpu_idle`), so the submission stays held until the wait gives up. Before the fix
the work just before the present was B, which is short, and the GPU was mostly idle; now it is A1. Upstream fixed this
(`rec::take_flush_owed` in `ed9495bb`, #1866: "a permanent hang with batched submits on RADV (a held last part with a
waiter)"), inside its recorder's rewrite (#1763, #1866), which a sync brings. With the gate off (`RX_VK_FRAME_GATE=0`)
every boot stalled twice, with the fix and without it (`v4gate0*-*.txt`). Once in the stage, none of the runs stalled.

Removed at the sync to v3.1.1 (2026-11-22), which brings upstream's `rec::take_flush_owed` (#1866), and put back the same
day: upstream's covers only a wait for parts already handed over to the recorder. Every 70 s headless walk then stalled
4-6 times (`vk: wait for fence N (done N-1, pushed N+2): 2`, `1 polls timed out (10334 ms)`: a wait with a 10 s timeout,
counted with the polls as one that timed out), none with `RX_VK_BATCH=0`. A temporary log of the wait's state (once
before its driver wait, then every 0.5 s) showed the order each time: at the wait, f's submit job was still in the
render thread's queue (`pushed` f-1, 2 to 16 jobs queued, nothing held, every part handed over submitted, so
`settle_parts` was met and nothing owed); 0.5 s later the render thread had replayed it and gone idle, 3-6 command
buffers held with `pend.signal` past f, the GPU idle (`batch_tl` at `batch_flushed`), nothing owed. The held part had
come through the recorder's `part_submit`, so putting the stand-in back with its old four lines (the submit's in
`submit_recording` only) did not help (6 stalls). It is back with a fifth line, the same `due` in `part_submit`'s batch
branch, and the owe in `wait_inner` (the wait's body since upstream's `wait` became the timeline line's wrapper):
0 stalls in 3 walks, 60 fps in play. The stand-in's own record follows.

The fix (`gpu/vk/flush_owed_inhale.h`, and the lines of `gpu/vk/vk_replay.cpp` marked `(inhale)` that called it) did
what upstream's does, keyed on fence values instead of its recorder's parts: a wait with a timeout (not a poll, which
comes many times a frame) owes its value before its own send, and the submit that holds that value sends the batch at
once (`FR_WAIT`). A seq_cst fence on each side (the waiter's after it owes, the submitter's after it raises
`pend_held`) makes sure that one of the two sends it. A value already sent is not owed, else every wait for the frame
before's fence would send the next submit alone. As upstream's, only the highest owed value is kept, and a send that
reaches it clears it. The header and its lines go at the sync that brings #1866.

Checked:

- The same headless boots with the fix (`f1boot-*.txt`, `f1off-*.txt`, `f1gate0-*.txt`): no stall in 6 with issue
  #6's fix (was 3), in 6 with `HOS_KIRBY_QUEUE_ORDER=0` (was 1), in 3 with `RX_VK_FRAME_GATE=0` (was two in each). Each
  boot was at fence ~5,960 when its 25 s ran out.
- S5's walk with the render thread on, with the fix and with its lines taken out, twice each, a temporary count of the
  sends by reason in the build (`f1walk-*.txt`, `f1walk-*/frames.csv`). Both walks without them stalled (fences 2708;
  80, 2708, 2736); those with them did not and presented 60.0 a second. Frames 1500 on: p50 16.67 ms, p95 16.96 and
  16.93, p99 17.37 and 17.31, none over 20 ms, as before this fix (`reg-a1-o1`: 16.67, 16.97, 17.21). The batching is unchanged: 2.16 command buffers a
  send against 2.17, about 1.23 sends per fence value either way. The owed sends (29 and 44 in a run, against 6 and 8
  sends for a wait without them) all came before the 6,000th send, in the title and the load: none in play.
- `tests/test_flush_owed.py` compiles a model of the held submits, the two sends and the submit with the header, and
  makes the cases: the stall's order, the other order, a poll, two waiters, a signal past the owed value, a send below
  it, a wait for what is already sent, and a waiter and a submitter racing on two threads 100,000 times. It reads the
  lines' places in `vk_replay.cpp` (since v3.1.1 five: the submit's in `part_submit` too). Before the fix it fails on
  the four places. Each of these breaks it: the
  submitter's fence removed (5 to 6,500 of the 100,000 rounds left the value held), `>=` made `>` or `==`, the owed
  value never cleared, cleared by any send, owed when already sent, owed after the waiter's send, cleared by a send that
  failed. The waiter's fence removed does not break it on x86, where the CAS before it is a full barrier already. Not
  modelled: the wait's later sends, the frame gate, `RX_VK_BATCH_MAX`, the send when the GPU is idle, the recordings'
  timeline, timing.
- A second reader went through the header, the lines and the test cold, and found no fault in the fix. What the test
  lacked (a signal past the owed value, a check that a failed send clears nothing) is in it now. Its remarks that stand:
  a lower waiter is sent only once the highest owed value is held. With the render thread, the higher waiter's
  `gate_need_value` lets that submit on. Where it cannot come (it waits behind a queue stopped at an event wait, with
  `RX_VK_ASYNC=0`; or a wait that gave up leaves a higher value owed), the lower waiter can still wait its 10 s, as
  before the fix. This game makes no event waits between its queues. `vk_timeline_wait` (upstream's) has the same race
  and does not owe: it waits 250 ms at most.

The open point. The test build also kept the virtual core during a hand-over (`hos_vcore_away` was not called), and
`HOS_NVN_HOLD=1`, which has that side effect and the old order, removed the dropout at the jump but not where the
camera turns (`i6-hold.txt`). So the order is proven together with the kept core, not alone. The fix gives the core
up for a hand-over as the imported code does, since keeping it costs frame time where the replay runs on the
submitting thread. Until the code as committed has been played at both places, this is in section 7.

### 2026-11-20: issue #14, the DLC stage bubble shows the Switch's A

The report: "Some controller icons aren't replaced", on the Xbox face. The base game's stage bubble on the world map
(`lyt/Wmap/GateInfo`) shows the face's icon (B, the Xbox button at the Switch A's place; the keyboard face: Space); the
Star-Crossed World stage bubble (`lyt/Wmap/GateInfoDlcStage`) shows the Switch's "A". Both layouts use the
`CmnBtnIcon` part.

The cause, found in the data. `nx2/kirby_prompts.py` redrew the labels only in `lyt/Cmn/BtnIcon/Parts.arc.cmp`, and
`host/prompts.c` served only that path. Four other archives carry a `BtnIconA^t` of their own, 128 x 128 BC5 and
byte-identical to the common one's, and no other label:

- `lyt/Wmap/MarkerDlcStage/Body.arc.cmp`, the DLC stage marker: its copy is the one the DLC bubble draws;
- `lyt/Arena/Entry/Parts.arc.cmp`, `lyt/Cmn/HeroPanel/Parts.arc.cmp`, `lyt/MgameBall/Game/Parts.arc.cmp`.

A layout looks a texture up by name and finds the copy in its own archive first, so those copies were never redrawn.
Found by a scan of every archive of the data romfs (the add-on title's: `lyt`, `font`, `msg`, `ubin` and the rest,
without `gfx`, `snd`, `mov` and `shader`) for a texture named like a label: no other archive holds one. The arena entry,
the hero panel and the ball minigame show the same fault, not seen on screen.

The fix. `kirby_prompts.py` `ARCHIVES` lists the five archives, the common one first; each is written to
`prompts/<face>/<its path>` with its variants beside it (`.var` for `.cmp`), and `redraw` skips a label an archive does
not hold. One the romfs lacks is not written (the common one must be there, as before). `host/prompts.c`
`icon_archives` serves the same five (the key is in lower case: matched without case), and `icons_file` takes the
file's path. The cache file of a set of controls (`cache/prompts/btnicon-<face>-<hash>.cmp`) has the path in its hash,
so two archives on the same controls do not share one; the common archive's cache files of a build before this one
are no longer used.

Checked:

- `nx2/test_kirby_prompts.py`: an archive holding `BtnIconA^t` and a texture that is no label has A's blocks redrawn
  and nothing else (before the fix: `KeyError: 'BtnIconB^t'`); `main` on a romfs of two of the archives writes both
  and their variants (before: `lyt/Wmap/MarkerDlcStage/Body.arc.cmp` not written). It needs the prompts' packages
  (`nx2/prompt_requirements.txt`); without them its cases skip.
- `tests/test_prompt_icon_archives.py` cuts `hos_prompts_romfs` and `icons_file` out of `host/prompts.c`, serves each
  key from a made-up game folder, and checks the face's file at its own path, a cache file for each of two archives
  with variants, and the text font, a mod's own file and another path as before (before the fix:
  `lyt/wmap/markerdlcstage/body.arc.cmp: not served`). With the path left out of the hash it fails on the shared cache
  file.
- The tool on the game's data: each face's five archives written in 16 s; the common archive's files byte-identical to
  the build before the fix; in each of the four others, A's label decodes to the common archive's redrawn one.
- The game, headless, 60 s from the start on the keyboard face with this PC's controls, which are not the defaults
  (`work/runs/i14/boot.txt`, its file opens in `strace.txt`): four of the five archives are read at the start (the
  arena entry, the common one, the hero panel, the ball minigame), each from `prompts/keyboard/<its path>` with its
  variants, and each written to a cache file of its own (four hashes). The DLC marker is read on the world map, which
  the run does not reach. Not seen on screen: the DLC bubble with the face's icon (section 7).

### 2026-11-21: issue #5, microstutter: telling its kinds apart

The reporter of issue #5 says v0.3.0 plays the first level well "aside from some micro stutters". `scripts/frame_hitches.py`
reads a frame trace (`RX_VK_FRAME_TRACE=1`, `logs/inhale_frames.csv`). A frame is slow at 1.25 medians or more. The script
takes each column less its median and gives the frame the cause whose columns grew the most. The causes are pipeline,
translate, upload, memsync and gpu, then the Breakdown's broad parts (game, render, pace, wait_main, wait_render). A frame
is "unexplained" when no cause grew by half its excess. The script also counts a slow frame followed by a short one (the
pacing catching up): the eye sees that as a judder even at a steady 60 fps.

Two warm runs of S5's walk, headless, at 3840x2160 (RX 7900 XTX, RADV), presents 900 to 4860:

| run | p50 / p95 / p99 / max (ms) | slow frames | causes |
|---|---|---|---|
| `work/runs/ms1/warm` | 16.67 / 17.00 / 17.65 / 30.3 | 4 | 4 unexplained, all caught up |
| `work/runs/ms1/warm2` (with `HOS_PRESENT_TRACE`) | 16.67 / 16.90 / 17.26 / 81.1 | 1 | render |

- `warm`: in all four the game's thread kept its time. Its Breakdown sums to about 16 ms and `pace_ms` stays at 12.3. Only
  the render thread's present-to-present time grew (30.3 ms, then 5.2 ms). The render thread's present came late and the
  next one caught up: this is render-thread or present scheduling, not the game's pacer.
- `warm2`: the game's own present 1821 took 80.8 ms (`presents.csv`), 64 ms of it in the renderer's part. The replay's
  buckets were all small (draw 1.2 ms). The log's 600-frame window gave back 48 mirrors (270 MB), which may be the cause,
  but the log has no times to place it. Not explained.
- Neither run repeats the 21 frames of 20-26 ms in issue #1's `after_both`. That run was a cold one with a shot every
  frame (`work/cold.sh`), so its pacing differs.
- `main_cpu_ms`, `main_blocked_ms` and `main_vcore_ms` are 0 throughout this game. The host reads them from the thread
  named `sead::MainThread` (`host/rx_backend.c`), and that name may not be this game's main thread's. Not checked.
- A headless run shows nothing of the display: MAILBOX or IMMEDIATE composition, or a 60 fps game on a display of another
  rate without VRR. PresentMon's `DisplayedTime` (section 13, rule 1) or `shown_ms` (FIFO and `RX_VK_PRESENT_THREAD=1`)
  is needed for that.
- `tests/test_frame_hitches.py` puts a slow frame of each cause into a made-up trace and checks that each is found. It
  fails when the medians are not taken off.

### 2026-11-21: the hitches in play on Windows are pool imports; upstream's import fence

On aubox (Windows 11, RTX 2080 SUPER, driver 621.24), every frame over 40 ms of a 100 s walk after the first level's load
was one or two imports of game memory, on the thread that replays the frame (`vk: pool ... imported in N ms`, then a
`slow submit` of the same time). The log's `vk: import N ms: ... allocate N` lines put all of an import's time in
`vkAllocateMemory`. Each took 20-36 ms whatever its size: 4 MB chunks averaged 28.6 ms, 16 MB 28.7, 64 MB 33.7. The
Radeon 780M on the same PC took 27-36 ms; the RX 7900 XTX on Linux takes under 2 ms. Upstream's #330 explains it: the
driver asks Windows about the pointer, and Windows walks page by page to the end of the run of pages with the same state
and protection, and this game's pools lie in long runs of committed read-write pages. The lazy commit of the game's
regions (`AllocateAddressRegion`, v0.3.0) did not shorten the walk.

Tried and left: `RX_VK_ASYNC_IMPORT=1` moves the import to a thread of its own, but `vkQueueSubmit` then took 22-55 ms
(the driver serialises the two), and frame 2405 stayed at 109 ms. `RX_VK_IMPORT_CHUNK_MB=16` halves the imports and the
hitches but costs about 260 MB of VRAM for the larger mirrors (64 MB: 650 MB).

The fix is upstream's PR #334, which upstream closed unmerged because its own game measured no gain after its lazy heap:
`gpu/vk/import_fence_inhale.h` gives the page after the import's range `PAGE_EXECUTE_READWRITE` for the length of the
call, so the run, and the walk, end with the range; `commit_on_touch` retries a data fault on such a page as on a
read-write one. `RX_VK_IMPORT_FENCE=0` turns it off. Runs of the build with it, the same walk, 1920x1080, frames after 300
(after frame 800 is play, before it the load):

| run | imports of 2 ms or more | their mean | frames > 25 ms | frames > 40 ms | > 40 ms after frame 800 |
|---|---|---|---|---|---|
| 2080, fence off (2 runs) | 112, 114 | 22.0, 23.7 ms | 17, 23 | 14, 16 | 10, 12 |
| 2080, fence on (2 runs) | 4, 2 | 3.4, 4.0 ms | 9, 8 | 6, 6 | 1, 0 |
| 780M, fence off | 62 | 27.5 ms | 541 | 37 | 33 |
| 780M, fence on | 21 | 3.6 ms | 614 | 24 | 19 |

The 780M runs at about 45 fps here, so its count over 25 ms is the frame rate's, not hitches. The frames left on the 2080
are the level's load (frames 690-733, 80-320 ms) and one 109 ms frame of GPU time in one run. Not measured: Intel on
Windows, NVIDIA cards other than the 2080, a long session.

### 2026-11-21: a shader preparation that the program cache lost (HeyListen c795788f, 8a629e6c)

`inhale_prepared.bin` said what the shaders were prepared for (the translator, the seed, the driver's part), not
whether the program cache still held them. The cache is one file per folder, made again whenever its stamp
(`program_cache_stamp`: the translator and what it is told of the GPU, `RX_VK_WARP64`, a laptop's other GPU with
`RX_VK_DEVICE`) is not the file's. A start under another stamp, closed before its preparation ended, left the usual
start an empty cache under a record that said prepared: nothing was prepared and every program the walk met was
translated in play. Reproduced on this PC (RX 7900 XTX, Linux) in `work/runs/pc1` (`run.sh`): a folder prepared, a start
with `RX_VK_WARP64=1` killed after 12 s (the cache rewritten, 0 of the 86163 keys left), then the tier-2 walk, frames
after 800:

| run | prepared at the start | translation in play | translations waited for | frames > 20.8 ms | > 40 ms | max |
|---|---|---|---|---|---|---|
| prepared, no other start (`A_base`) | no (nothing to do) | 13 ms | 2 | 1 | 0 | 24.8 ms |
| after the cut start, before the fix (`A_before`) | no | 255 ms | 5 | 7 | 4 | 60.0 ms |
| after the cut start, with the fix (`B_after2`) | yes, 27.5 s | 12 ms | 0 | 0 | 0 | 18.5 ms |

This game's programs translate in about 13 ms each, not the other game's 200-400 ms: `scripts/frame_hitches.py` gives
`pipeline` for 6 of the 7 slow frames and `translate` for 1. The fix: the record has a seventh word, the program keys
the cache held when it was written (`prepared_write`), and `prepare_check` prepares again (`PrepareWhy::Cache`, "the
program cache holds N program keys of the M the last preparation left") when the cache holds fewer than half of that,
or none under a record of six words; no program cache is never a reason. A six-word record (every folder before this)
and a cache partly refilled in play under it is not caught: the count starts with the next preparation.

The count opened a second hole, which upstream closed in 8a629e6c: the record was only written again at the end, so a
preparation closed part way left the old one standing, and a cache it had filled past half passed for prepared; the
rest was translated in play. `prepare_run` now removes the record once the seed is open, before it translates; the
next start prepares again, only what the cache does not hold. Not in play (an update with `RX_VK_PREPARE_BACKGROUND=1`):
there the old record's other stamp already prepares again, and `prepare_is_update` needs it to stay an update. Same folder, wiped again with a `RX_VK_WARP64=1` start,
then a usual start killed at 22 s into its preparation, then the walk:

| run | cache at the walk's start | prepared at the start | translation in play | waited for |
|---|---|---|---|---|
| before (`B_before2`) | 70777 keys, the old record (82880) | no | 165 ms | 5 |
| after (`B_after3`) | 66429 keys, no record | yes, 18404 new programs | 15 ms | 0 |

The frames hardly differ here (1 over 20.8 ms before, 14 after, all under 23 ms and given to `game`): the cut cache
still had most of what the walk meets.

### 2026-11-22: issue #15, Kirby and the enemies drawn as a clear shape on Intel Iris Xe

The report: Iris Xe (i5-11320H, TGL GT2, Mesa 26.3.1 ANV), and the same on an i7-1365U with v0.3.1. Kirby and the
enemies drew as an "invisible filter", the ground seen through them. The logs named no cause: no draw skipped, no error.
Of the switches tried in turn on the i7-1365U, the first fixed it: `RX_VK_EQ_BIAS=0`.

Cause. On Intel, upstream turns a colour pass that tests depth EQUAL (and does not write it or blend) into
LESS_OR_EQUAL with a depth bias of -64 (device_policy.h `equal_depth_bias`; tests/test_equal_depth_margin.py has why).
That is a margin towards the camera only where a smaller depth is nearer. This game draws reversed depth: a run here with
a temporary log in `dynamic_state` showed its draws that write depth testing GREATER_OR_EQUAL (`dop` 6), the depth range
0 to 1, and 26 programs whose colour pass tests EQUAL. With LESS_OR_EQUAL such a pass passes everything behind the
depth already drawn, and the ground's colour pass, drawn after the characters, painted over them. The bug shows on
any GPU with `RX_VK_EQ_BIAS=64`: in S5's walk (frame 4800) Kirby is cut in half and the enemy is gone.

Fix (`vk_draw.cpp`, `dynamic_state`, marked `(inhale)`): the margin goes the way the draws that write depth order. A
draw that writes depth with LESS or LESS_OR_EQUAL says smaller is nearer, GREATER or GREATER_OR_EQUAL that larger is;
EQUAL, NOT_EQUAL, NEVER and ALWAYS say nothing. Under reversed depth, the EQUAL pass becomes GREATER_OR_EQUAL with a
bias of +64. Until a draw has said, the margin is upstream's. `tests/test_equal_depth_margin_reversed.py` cuts the
margin out and runs draws through it, both ways. The same walk with `RX_VK_EQ_BIAS=64` and the fix draws frame 4800 as
the run without the margin does.
On the i7-1365U (Iris Xe, Mesa ANV), the `nightly` build of 2964a28 draws Kirby and the enemies with no switch set.

### 2026-11-22: issue #16, local co-op with one controller for each player

Every controller drove Npad No.1. Upstream's `host/pad_sdl.c` ORs every SDL pad's buttons into one state and keeps
the strongest stick of all of them; `host/nn_hid.c` `pads_read` ORs XInput's slots in, `npad_states` gives input only
to id 0 (every other id reads as not connected), `GetNpadStyleSet` answers FullKey for No.1 alone and
`ShowControllerSupport` always answers one player. The game reads No.1 to No.4 and Handheld at the title (each id is
logged once, `hid: the game reads npad ...`), and its Play Co-op asks the applet: it said only one controller was
connected.

The Controls tab's **One controller per player** (`opts.pad_per_player`, `HOS_OPT_PAD_PER_PLAYER` 1001,
`gpu/vk/menu/kirby_coop.cpp`) turns each controller into a player. The open pads that give input are the players in
their slots' order (`pad_sdl.c` `hos_sdl_pad_player`: a Steam stand-in's motion-only twin is no player). That is the
order of connection until a pad is unplugged: the players after it move up one, and a pad plugged in then takes the
lowest free slot. No.1 is the
first pad with the keyboard, the mouse, the scripts and every toggle as before; No.2 and later read their own pad
through the same bindings (`host/kirby_npad.c` `kirby_npad_read`), only with the game in front (or the pads let
through behind other windows) and the Insert menu closed. Each Npad has its own sampling number. The applet answers
the players connected, at most the game's maximum, one in single mode, with No.1 selected; there is no dialog, so a
game asking for more players than are connected is told how many there are. Off is the default: a device that reads
as a second pad (a virtual pad, upstream #1673's held axes) would take the player's own pad to No.2.

Vibration: `vibration_send` hands each handle's value, with its npad id, to `kirby_npad_vibration`, and the plain
motors of each player's pad play that player's (`pad_sdl.c` `rumble_of`). With the row on it also hands the value as it
is to that player's HD rumble and RenHDrum (`hos_sdl_rumble_hd_player`, `rh_push_player`); `vibration_send`'s shared
calls stay, and with the row off they are all that plays.

- HD rumble: `pad_sdl.c` keeps each player's values beside the shared ones (`hd_of`), and the poll encodes a `VIB_HD`
  pad's side bytes from its own player's (`hd_sides_of`) just before `hd_poll`, the test aside.
- RenHDrum: the poll tells it whose each pad is (`rh_pad_player`, -1 with the row off or the pad closed). `feed_to`
  takes who sends: -1 the shared stream, 0 to 7 a player, `RH_ALL` the Test vibration row. A target (the cable's and
  Bluetooth's DualSense, the Steam grips, each Xbox and Switch engine) takes a value when it is who's, so with the row
  off every target is -1's and the shared stream reaches all of them, as upstream has it; with it on, only the pads no
  player owns. Each player's sides go quiet on their own (`at_of`, `quiet_of`), so player 2 stopping silences player
  2's pad alone. The DualSense triggers read their own path's copy of what it was fed (`usb_last`/`usb_fed`,
  `bt_last`/`bt_fed`), not one shared copy, since the cable and Bluetooth can play two players.
- The limit stays: RenHDrum drives one DualSense on a cable, one over Bluetooth and one Steam Controller. A second one
  on the same link already plays its motors (`vib_choose`), and those are per player.

`tests/test_rumble_per_player.py` cuts RenHDrum's routing and `pad_sdl.c`'s per-player HD values and runs them with
stand-ins for RenHDrum's calls: player 2's value reaches its engine alone, the shared one every target with the row off,
a quiet player is silenced alone, the test reaches every pad.

Motion stays the pad used last's (`motion_poll`); XInput, read only when SDL has no pad, stays No.1's.

`tests/test_kirby_npad.py` compiles the applet's and the style set's HLE from `nn_hid.c` with `kirby_npad.c` and
stand-in pads. Before the change it failed on No.2 not connected and on the applet's one player. Not checked here: a
played run with two controllers (this PC has none attached); the issue's reporter is asked to try it.

### 2026-11-23: issues #18 and #19, the scene black in play (v0.4.0)

The reports: v0.4.0 on an RTX 3050 Laptop (NVIDIA 610.64, Windows 11) and an RTX 5080. The title, the movies and the
pause menu drew; in play only the HUD, the particles and the dithered transparent draws showed. The renderer logged no
error, but many lines `vk: page table: pool … is outside its windows: a pointer into it that no bound buffer holds
reads 0`.

Not NVIDIA's: S5's walk on this PC's RX 7900 XTX (RADV) drew the same, from frame 600 (the title's blue background is
gone too). `RX_VK_GP_TABLE=0` brought every frame back.

Cause. The v3.1.1 sync brought upstream's default `graphics_table_loads` (`gpu/vk/vk_coopmat.cpp` `table_loads_wanted`,
`RX_VK_GP_TABLE=1`): the vertex, fragment and compute stages read global memory through the guest page table alone,
not by searching the bound storage buffers. The table covers three windows laid out for upstream's game
(`gpu/vk/page_table_census.h` `kPageWindows`: 64-72 GB, 496-512 GB, 1 TB). This game's pools lie elsewhere, near 2 GB
and between 482 and 492 GB (the census lines), so every load through the table read 0: vertex and lighting data among
them. On any GPU with host memory import and buffer device addresses, which is all of the tested ones.

Fix (`host/hos_main.c`, marked `(inhale)`, beside the `RX_VK_PIPE_SKIP` default): `RX_VK_GP_TABLE=0` unless the player
set it, the storage buffer search of v0.3.1. Moving the windows to this game's pools would also do, but the window
bases are written into the shaders (`spirv_emit_context.cpp` `kGuestPagesBase*`) and into upstream's files around them.
`tests/test_kirby_gp_table.py` cuts the defaults after `hos_options_choose` and `table_loads_wanted`, and checks the
switch the renderer takes: before the fix it printed `FAIL: RX_VK_GP_TABLE unset: the renderer takes 1, wanted 0`.
S5's walk with the fix draws every frame on the 7900 XTX and the Ryzen 7900X's iGPU (RADV), as `RX_VK_GP_TABLE=0` does.
On the Windows PC (Windows 11) the same walk was compared with v0.3.1's, shot by shot
(`scripts/kirby_shot_compare.py`): on the RTX 2080 SUPER (NVIDIA 621.24, #19's driver) the fixed build differs by at
most 18 of 255 in a frame and `RX_VK_GP_TABLE=1` by 50 to 130 in every frame, the scene black as in #18; on the
Radeon 780M (AMD 26.11.2) the fixed build differs by at most 9.

Why the headless runs after the sync did not see it: they counted the fence stalls in the log and nobody looked at the
shots. `.claude/skills/verify` now makes the shots of each run part of the check.

### 2026-11-23: build a6ce40dc taken, not yet played

A player's `.nup` of the same program (its file named "Kirby and the Forgotten Land + Star-Crossed Worlds [01004D300...]")
was refused by the check: `This is build a6ce40dc. Inhale supports build 395fc326.` Its full build id and version number are
not known here yet.

- What was tied to the build: the check (`check_supported_build`, `check`'s `@@check` line, `exefs_problem` for a kept
  exefs), the far-objects edit (`nx2/kirby_far.py`) and the shader list (`nx2/kirby_shaders.py`). The two last check main's
  build id and each site's word themselves, and leave another build out with a line in the log. Nothing else in the tree
  reads a guest address of this build: `host/kirby_hle.c` hooks SDK names, and `host/kirby_res.c` and `host/kirby_shadow.c`
  check the data's bytes before they change them. No hot list or play profile of the game ships (`assets/` holds the
  pipeline lists only, keyed by shader hash).
- Change: `OTHER_BUILDS` in `nx2/make_game.py` (`supported_build`) lists `a6ce40dc`. The check says it is taken and not yet
  played, and what is left out. `BUILD_ID` and the manifest's `nup_build_id` stay `395fc326`
  (`tests/test_recomplauncher_inhale.py`): RecompLauncher still takes only that build. Test:
  `tests/test_make_game_other_builds.py`.
- Not checked: a build of `a6ce40dc` and play. The far objects can update at 30 or 15 and a first visit can stutter there
  until the two lists are made for its addresses.
