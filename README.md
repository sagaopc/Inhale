# Inhale

<a href="https://recomplauncher.com"><picture><source media="(prefers-color-scheme: dark)" srcset="https://recomplauncher.com/assets/press/launcher/badge-light.svg"><img alt="Get it on RecompLauncher" src="https://recomplauncher.com/assets/press/launcher/badge-dark.svg" height="48"></picture></a>

**Kirby and the Forgotten Land running natively on Windows and Linux, without emulation.**

[Download](https://github.com/mario-ttide/Inhale/releases/latest) | [Status](#project-status) |
[Install and play](#install-and-play) | [What you need](#what-you-need) | [Build from source](#build-from-source) |
[How it works](#how-it-works) | [Licence](#licence)

Inhale turns your own copy of *Kirby and the Forgotten Land, Nintendo Switch 2 Edition + Star-Crossed World* into a
Windows or Linux program. The game's code is translated and compiled **on your PC, from your own copy of the game**;
the graphics are redrawn with Vulkan. It is a work in progress.

> [!IMPORTANT]
> This repository **does not contain the game, keys or a ready-made program**, and it does not explain how to get
> them. You need your own copy. Everything the build makes (the game folder, its program and caches, your saves)
> comes from your game and stays on your PC. Never share those files, and don't ask for them in the issues.

## Project status

Early. One player has played it by hand on Linux; the Windows installer has been tested on one PC.

v0.4.0 drew the scene black in play, on every graphics card (issues #18 and #19), and was withdrawn: use v0.4.1.

| What | Status |
|---|---|
| Opening, title screen, the first world's stages and its boss, several special stages | ✅ Played through, at 60 fps |
| Later worlds | ❓ Not played yet |
| Build `a6ce40dc` of the game | ❓ Taken by the builder, not yet played (see [What you need](#what-you-need)) |
| Star-Crossed World stages (the Switch 2 Edition's) | ⚠️ The first one played. Up to v0.2.0 its crystal covering vanished for single frames in a jump or a camera turn. Fixed in v0.3.0 |
| Sound, music, movies, keyboard and saves | ✅ Work |
| Controllers | ❓ Few reports yet. Rumble is played since v0.2.0, not yet felt on a pad in play. Local co-op with one controller per player: new in v0.4.1, not yet tried with two controllers |
| Frame generation | ⚠️ **Auto** works. A fixed **2x** and up can freeze the game for a few seconds now and then (seen on Linux with an AMD card) |
| Linux | ✅ The AppImage, tested on CachyOS with an AMD Radeon RX 7900 XTX (Mesa). It also starts in clean Ubuntu 22.04 and Fedora |
| Windows | ✅ The installer, tested on Windows 11 with an NVIDIA RTX 2080 SUPER, built from the extracted folders. The `.nup` route there is still to be tried. Up to v0.3.0 play hitched now and then there (frames of 40 ms and more, on that card and the 780M); fixed in v0.3.1 |
| AMD cards on Windows | ⚠️ One tried, a Radeon 780M (integrated): v0.2.0 draws coloured discs over the picture there. Fixed in v0.3.0, checked on that card in the first stage only |
| Intel cards | ⚠️ Iris Xe on Linux (Mesa) tried. Up to v0.3.1, Kirby and the enemies were drawn as clear shapes there. Fixed in v0.4.1 |
| Cards without mesh shaders (such as NVIDIA GTX 10 and AMD RX 5000) | ⚠️ Should run through a slower compute path (upstream's). Not tried with this game |

## Install and play

### [Download for Windows](https://github.com/mario-ttide/Inhale/releases/latest/download/Inhale-Setup-x64.exe)

### [Download for Linux (AppImage)](https://github.com/mario-ttide/Inhale/releases/latest/download/Inhale-x86_64.AppImage)

Older versions and the `nightly` build of the newest code are on the [Releases](https://github.com/mario-ttide/Inhale/releases) page.
Each download brings its own compiler and every other tool it needs, works without an internet connection, and holds
nothing of the game. `Inhale-Windows-x64.zip` on the same page is the installer's folder unpacked, without an
installer: unzip it anywhere and start `Inhale.exe`.

### With RecompLauncher

Both packages carry a `recomplauncher.json`, so [RecompLauncher](https://recomplauncher.com) can ask for your `.nup`
or folder, build the game into its own install folder and start it, with a few of the menu's settings on its page.
Each update builds the game again from your copy (from v0.3.1: the update to v0.3.0 kept the v0.2.0
game; run the launcher's setup again to rebuild it). Inhale is not in RecompLauncher's catalog yet.

### On Windows

1. Run `Inhale-Setup-x64.exe`. It installs for you only (no administrator rights) and adds **Inhale Builder** to the
   Start menu and the desktop. The files are not signed yet, so SmartScreen says "Windows protected your PC": choose
   **More info**, then **Run anyway**. To check the file first, compare `Get-FileHash Inhale-Setup-x64.exe` (in
   PowerShell) with the release's `SHA256SUMS`.
2. Start **Inhale Builder** and build the game (below).

### On Linux

1. Let the AppImage run as a program: in your file manager, open its **Properties** and turn on "Allow executing
   file as program" (the wording differs between desktops), or run `chmod +x Inhale-x86_64.AppImage`.
2. Double-click it. If nothing happens, your system may lack FUSE 2 (`libfuse2`): start it from a terminal as
   `./Inhale-x86_64.AppImage --appimage-extract-and-run`.

**Faster GPU memory on AMD and Intel (`/dev/udmabuf`).** The game is fastest with access to the kernel's `udmabuf`
device; without it, it warns at start and can be much slower on AMD. Check with `ls -l /dev/udmabuf` (if it is
missing: `sudo modprobe udmabuf`). On a desktop, give it to the logged-in user with a file
`/etc/udev/rules.d/70-inhale-udmabuf.rules` that holds `SUBSYSTEM=="misc", KERNEL=="udmabuf", TAG+="uaccess"`, then
run `sudo udevadm control --reload-rules` and `sudo udevadm trigger --action=add /sys/class/misc/udmabuf`. Never run
the game as root. On NVIDIA's own driver the warning can be ignored.

### Build the game

In Inhale Builder:

1. **Your game:** choose your `.nup` file, or a folder that holds the extracted `exefs/` and `aoc/` folders. It is
   checked to be the right game and version.
2. **Where:** the game folder (`~/Games/Inhale` or `%USERPROFILE%\Games\Inhale` by default), about 12 GB.
3. **Build:** the whole game is compiled on your PC, which takes a few minutes on a desktop with 12 to 16 cores and
   longer on a smaller one; the window shows the time left. You can stop it: what was compiled is kept for next time.
4. **Play.** **Create shortcut** adds the game to the applications menu (Linux) or the desktop (Windows).

**The first start takes longer.** Before the title screen it prepares the game's shaders and pipelines (about half a
minute on a 12-core PC), so play does not stutter while they compile. Later starts reuse them. A new version of Inhale
can prepare them again once, and so can a start after the shaders kept were lost (a laptop's other GPU, a start closed
while it prepared).

The **Insert** key opens Inhale's own menu in the game (graphics, frame generation, controls). **Graphics, Detail,
Depth of field** turns the game's depth of field off or on at once. **Graphics, Detail, Shadow resolution** sets the
size of the game's shadow map, after a restart: **Game's** is the console's 1400 pixels a side (about 12 MB of video
memory), **High** 2800 (about 47 MB), **Highest** 4096 (about 101 MB). **Auto**, the default, picks it from the
graphics card's memory: the game's size on 4 and 6 GB, High on 8 GB, Highest on 12 GB or more. The game softens its
shadows' edges, so the gain is small: edges a little tighter. On an RX 7900 XTX at 3840 x 2160, Highest costs about
0.5 ms of GPU time a frame over the game's size. The handheld profile keeps the game's own size.

**Local co-op.** Every controller plays as the first player unless **Controls, One controller per player** is on. With
it on, each controller is a player of its own, in the order the controllers were connected, and the game's Play Co-op
counts them: the first controller is the first player, with the keyboard and mouse, the second controller the second
player, and so on. A controller unplugged moves the players after it up one. Vibration goes to each player's own
controller, on every kind of controller (HD rumble, a DualSense's haptics, an Xbox controller's triggers). The haptics
play on one DualSense on a cable and one over Bluetooth: a second DualSense on the same link rumbles with its motors.
Motion controls follow the controller used last. Xbox controllers read through XInput, when SDL is missing, all stay the first player's.

**Resolution.** The 3D scene is drawn at your screen's size up to 3840 x 2160 (a 16:9 screen wider than 2560 x 1440),
and at 2560 x 1440 on any other screen. The game's dynamic resolution is off, so the size stays fixed; set the
environment variable `HOS_DYNAMIC_RES=1` to let the game lower it under load. The handheld profile keeps the game's
own smaller sizes and its steps, for a slower PC. After you update
Inhale Builder, choose **Update an existing game folder** to build your folder again with the new version.

**If the picture goes wrong where an older version drew it right**, try the environment variable
`HOS_KIRBY_QUEUE_ORDER=0` and report what you see. It hands the game's graphics work to your PC in the order of v0.2.0
and before, in which the crystal covering of the Star-Crossed World stages vanishes for single frames.

**Sound on 5.1.** When the game mixes for 5.1, the centre channel also goes to the front pair at -3 dB, so a headset's
virtual surround or a driver that drops the centre still plays what is on it. Set the environment variable
`HOS_AUDIO_CENTRE=0` to keep the centre on its own channel only.

## What you need

**Your copy of the game:** *Kirby and the Forgotten Land, Nintendo Switch 2 Edition + Star-Crossed World*, as one
`.nup` file, or as the extracted folders: `exefs/` (program `04004d300c5ae001`, v65536) and `aoc/<title id>/romfs/`
(the data, `01004d300c5af001`). The builder checks the version: it is made for build `395fc326` (the
build id of `main`). Build `a6ce40dc`, another release of the same program, is taken too but has not been played yet:
the far-scenery fix and the shader list are made for `395fc326` and are left out for it, so far objects can move at 30
or 15 fps and a first visit can stutter. Other versions are not supported.

| Component | What you need |
|---|---|
| **Operating system** | 64-bit Windows 10 or 11 (tested on 11), or 64-bit Linux with glibc 2.35 or newer (Ubuntu 22.04 and later, Fedora, Arch, SteamOS) |
| **Graphics card** | Vulkan 1.3 with an up-to-date driver (on Linux: Mesa or NVIDIA's own). Mesh shaders are not needed |
| **Storage** | About 12 GB for the game folder, plus room for the build's own files |
| **Internet** | Not needed: the download brings everything |

No minimum processor or memory has been measured yet. Tested on a 12-core Ryzen 9 7900X with 64 GB, and on a 16-core
Windows PC with 26 GB.

## Build from source

For development, or to build without the packages. `Inhale-x86_64.AppImage --cli <arguments>` runs
`nx2/make_game.py` with the AppImage's own tools, for the command line, over SSH or from a script.

### What you need to build

- Linux, x86-64. (Windows: use the installer; building from a checkout there is Longshot's route, less tried.)
- clang and lld, pkg-config, Python 3.12 or newer, git.
- FFmpeg's development files (libavcodec, libavutil, libswscale, libswresample) and dav1d's.
- The Vulkan, SPIR-V and Vulkan Memory Allocator headers. Distributions ship the first two; VMA is often not packaged:
  put `include/vk_mem_alloc.h` of [VMA](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator) (3.1 or
  newer) in `/usr/local/include`, or point `INHALE_VMA_HEADERS` at its folder. When a distribution's Vulkan or SPIR-V
  headers are too old, set `INHALE_VULKAN_HEADERS` and `INHALE_SPIRV_HEADERS` to newer ones (the commits the checks
  use are in `.github/workflows/ci.yml`).
- To play: a GPU and driver with Vulkan 1.3 (mesh shaders not needed), the Vulkan loader, and SDL 3 (or SDL 2),
  which the game loads at run time.
- For the checks: spirv-tools (`spirv-val`) and glslang 16.6.0.
- About 12 GB of disk for the extracted game data, plus the build's own files under `work/`.

On Arch Linux (as tested):

```
pacman -S --needed clang lld pkgconf python git ffmpeg dav1d vulkan-headers spirv-headers vulkan-icd-loader sdl3 \
    spirv-tools glslang
```

### Set up

```
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PY=".venv/bin/python -I"
```

Tell the tools where your package is, either with the `INHALE_NUP` environment variable or by writing its path as
the only line of `work/nup.txt` (`work/` is ignored by git):

```
mkdir -p work && printf '%s\n' "/path/to/your/package.nup" > work/nup.txt
NUP="$(cat work/nup.txt)"
```

### One command: a game folder

```
$PY nx2/make_game.py --nup "$NUP" --out ~/Games/Inhale
~/Games/Inhale/inhale
```

It unpacks the package into the folder, translates and compiles the code, and puts the program beside the data.
From extracted folders: `--game <folder with exefs/ and aoc/>`, or `--exefs <dir> --aoc <dir>`. `--update <folder>`
builds a folder again with newer tools from the files it keeps. Saves go to `$XDG_DATA_HOME/inhale`. The Insert key
opens the port's own menu.

The rest of this page is the same work step by step, for development.

### Check the tools and the package

```
$PY -B tests/run_all.py                    # the game-free checks
$PY scripts/check_third_party.py           # third_party/ is unmodified
$PY nx2/nup.py "$NUP"                      # list the package: a code title and a data title
$PY nx2/nup.py "$NUP" --extract work/dump  # code to work/dump/exefs, data to work/dump/aoc/<title id>/romfs
$PY nx2/dump.py --dump work/dump --set     # what the code is: platform, modules, build id
```

### Translate, build, run

```
$PY nx2/lift.py                            # translate everything and report coverage
$PY nx2/test_insn.py --per 6 --states 12   # each instruction form against Unicorn
$PY nx2/test_leaf.py --count 3000 --states 4
$PY nx2/lift.py --standalone --write       # write the C of the standalone program
$PY nx2/build.py --standalone --jobs 16    # compile and link it
work/sa/build/inhale work/sa/image/image.bin --romfs work/dump/romfs --aoc work/dump/aoc --user work/user
```

`docs/design.md` says how far each of these gets today and which switches help when one stops.

### Following Longshot

`scripts/sync_upstream.py` applies Longshot's changes since the commit recorded in `PROVENANCE.md`. It puts both
sides of Longshot's diff through the rule of `scripts/rename_full.py` first, so the changes arrive under this fork's
names; run `scripts/rename_full.py` after a sync to see that nothing is left to rename.

`scripts/sync_nightly.py` does a sync with nobody at the keyboard, for a timer to run each night: it fetches
Longshot, has Claude Code do the sync in a clone under `work/sync/`, and moves `main` and pushes it only when the
checks pass and, where the game's files are at hand, the game still starts. Its docstring has the order and what a
stopped night leaves.

## How it works

Python tools translate the game's AArch64 code to C, clang compiles that C, a native runtime written in C stands in
for the console's system and its NVN2 graphics API, and a Vulkan back end replays the graphics calls. There is no CPU
or GPU emulation. The stages of the work and what each has reached are in [docs/design.md](docs/design.md).

Inhale is a fork of [Longshot](https://git.magicbean.dev/MagicBeanDev/Longshot), which does the same for another game
(`PROVENANCE.md`, `CREDITS.md`). Most of the code is still Longshot's; its name was changed through the tree by a
script (`scripts/rename_full.py`).

## Licence

GPL-3.0-or-later (`LICENSE`). Copyright lines, the notice of modification and the people whose work this is:
`CREDITS.md`.

Inhale is an unofficial fan project, not affiliated with or endorsed by Nintendo or HAL Laboratory.
