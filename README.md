# NFS High Stakes texture upscaler

Safely AI-upscales the textures of *Need for Speed: High Stakes* (NFS4, 1999), whole tracks at a time, and catches the textures that come out worse.

The game's textures are small, often 64 or 128 pixels wide, so they look blocky on a modern screen. Upscaling them by hand means unpacking each file with FSHTool, editing every image and packing it again, one track at a time. This tool does all of that in one command and takes care of the traps:

- **The 16 MB limit.** A texture file stores its unpacked size in 3 bytes, so it must stay under 16 MB. If a file would go over, the tool tries again at a smaller size.
- **The game's own formats.** Track textures stay 8-bit with a 256-colour palette, and see-through edges stay crisp. Skies and effects keep their soft transparency.
- **Bad results.** AI upscalers sometimes invent a woven pattern on smooth asphalt, or wipe the grain off grass and dirt. The tool measures every texture, flags the suspects, and draws a before/after sheet so you can judge them. It can put flagged textures back to their originals for you.
- **Safety.** Every file is checked after packing, the old file is kept next to the new one as `<file> original` (the HD Mod Pack's convention), and a backup copy goes to the output folder.
- **Leftover originals.** If a track was replaced by a remake, an old `original` from the previous track may still be lying next to it. The tool spots this and refuses to touch the file, because undoing it later would bring back the wrong track's textures.

No game files are included. You need your own copy of the game.

## What you need

- Windows, and a graphics card that supports Vulkan.
- Python 3.10 or newer, with Pillow and NumPy (`pip install pillow numpy`).
- **FSHTool** 1.22 by Denis Auroux, from http://auroux.free.fr/nfs/. By default the tool looks for it in `<game>\FSHTool\fshtool.exe`.
- **Real-ESRGAN ncnn-vulkan** from https://github.com/xinntao/Real-ESRGAN/releases, unzipped into `realesrgan\` next to this README, or pointed to with `--esrgan`.

**Work on a copy of the game folder.** The tool keeps originals and backups, but a copy costs nothing.

## Use

From this folder:

```
python -m nfshs_upscaler upscale --game "D:\Games\NFS4 copy"
```

That upscales the day and night textures (`TR0.QFS`, `TRN0.QFS`) of every track. Useful options:

| Option | What it does |
|---|---|
| `--tracks UK,HILLS` | Only these track folders. Folder names don't always match track names: `UK` is Durham Road, `HILLS` is Celtic Ruins, `GERMANY` is Landstrasse, `GT1` to `GT3` are the raceways |
| `--skies` | The skies (`SKY.QFS`) instead of the track textures |
| `--restore-flagged` | Put textures that come out woven or flat back to their originals before installing |
| `--max-size 128` | A smaller target size, for tracks that are close to the 16 MB limit |
| `--path <file> --format 7D --bleed-below 64 --exclude mous` | Any other texture file, such as `Data\GAMEART\SFX.FSH` (smoke, spray). Use `--format 78` for `WEATHER.FSH`. `mous` is the mouse cursor |

Results go to `output\<date-time>\`: `report.csv`, a before/after sheet for every file with flagged textures, and backups.

**Look at the sheets.** The woven and flat checks are measurements, not judgement. In testing on 93 flagged textures from one install, about one in ten flagged textures was actually fine, and a few bad ones were missed.

Don't use it on menu or speedometer files (`Data\FEART\`, `HUD*.QFS`). Those pieces are drawn at their pixel size, so bigger images simply appear bigger.

### Other commands

```
python -m nfshs_upscaler check   --game <folder>                        # flag woven or flat textures in already upscaled files
python -m nfshs_upscaler restore --game <folder> --tracks GT3 --files TR0.QFS --textures 0149,0153
python -m nfshs_upscaler undo    --game <folder> --tracks HILLS          # put whole files back to their originals
```

`check` works on files upscaled by any tool, as long as the `original` is next to them. `restore` puts single textures back to their original versions; the graphics card smooths the smaller original when drawing, so nothing is invented. `undo` moves `<file> original` back into place.

## How it works

For each file: unpack with FSHTool, pick the textures between 32 and 255 pixels, fill see-through pixels with their neighbours' colours (so the AI doesn't draw dark fringes), upscale them all in one Real-ESRGAN run (`realesrgan-x4plus`), resize to the target, turn them back into a 256-colour palette (median cut in 15-bit colour, the palette's own precision), repack, unpack again to check every entry, then compare each texture with its original.

The quality check measures how much the brightness changes between neighbouring pixels. Smooth asphalt scores about 1 and real grain 3 to 6. An upscale that jumps above 5 and to more than three times the original is called woven. One that drops below 1 from above 2.5, and is low in contrast overall, is called flat.

## Credits and licence

- FSHTool by Denis Auroux (GPL). This tool runs it as a separate program and doesn't include it.
- Real-ESRGAN by Xintao Wang and others (BSD-3-Clause), not included.
- Written with Claude Code, an AI coding agent, for a 2026 NFS4 project: https://coseac.swiss/blog/a-weekend-with-need-for-speed-4/

MIT licence, see `LICENSE`. Use at your own risk, on a copy of the game.
