# Changelog

## 0.1.1 (2026-11-10)

- `restore` accepts texture names in any case (`0149`, `0149.bmp`) and says clearly when a name isn't in the file, instead of failing with no message.
- Each file is packed once instead of twice, so upscaling is a little faster.
- The temporary upscale folder is named after the folder it works on.
- A unit test for a texture that is entirely transparent.

## 0.1.0 (2026-11-08)

First release.

- `upscale`: AI-upscales the textures of whole tracks (`TR0.QFS`, `TRN0.QFS`), skies (`--skies`) or any FSH/QFS file (`--path`), keeping each texture's own format.
- Stays under the 16 MB limit of a QFS file, retrying at 128 px if needed.
- Checks every packed file by unpacking it again.
- Flags textures that come out woven or flat, with a before/after sheet per file. `--restore-flagged` puts them back to their originals.
- Keeps `<file> original` next to each file and a backup per run, and refuses files whose `original` belongs to a different file.
- `check`, `restore` and `undo` commands.

Tested on copies of Hometown, Raceway 3 and Celtic Ruins track textures, a Raceway 3 sky and `WEATHER.FSH` from one install of the NFS4 HD Mod Pack, on Windows 11 with Python 3.12. The output matched an earlier PowerShell version of the same pipeline, whose files were raced in the game. Files made by this version haven't been raced yet.