# Fonts

The **Pixel** theme uses a pixel-art display face for headings and buttons.
Two fonts are relevant:

## Press Start 2P (included, SIL OFL 1.1)

- File: `PressStart2P-Regular.ttf`
- Author: CodeMan38 / The Press Start 2P Project Authors
- License: **SIL Open Font License, Version 1.1**
- License text: `PressStart2P-OFL.txt`
- Source: <https://github.com/google/fonts/tree/main/ofl/pressstart2p>

The OFL permits redistribution and embedding, so this font is tracked in Git
and included in public builds. It is the fallback for the Pixel theme.

## Pixeled (NOT included, non-commercial)

- Author: OmegaPC777 (2016)
- License: **FontStruct Non-Commercial Software EULA 1.0**
- License page: <https://fontstruct.com/fontstructions/license/1298421/pixeled-5>

The EULA grants personal use only and, in section 2.3, explicitly forbids
selling, distributing, redistributing or making the font available as part of
any product. It is therefore **excluded** from this repository and from public
release archives (see `.gitignore`).

If you own a licensed copy and want the original look on your own machine,
place it at `Fonts/Pixeled.ttf`. Git will ignore it, so it stays local.

## How the fallback works

`main.py` registers every `.ttf`/`.otf` file found in this directory. The
Pixel theme's CSS asks for:

```text
'Pixeled','Press Start 2P','Courier New',monospace
```

- On a developer machine with a local `Pixeled.ttf`, Qt resolves **Pixeled**.
- In a clean clone or public build, Qt resolves **Press Start 2P**.
- If both are missing, it falls back to **Courier New**.

No code change is needed when adding or removing a font: drop the file in this
folder (and commit it only if its license allows redistribution).
