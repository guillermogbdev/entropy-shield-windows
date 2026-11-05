# Fonts

The **Pixel** theme was designed around **Pixeled** by OmegaPC777
(`Copyright OmegaPC777 2016`), distributed under the **FontStruct
Non-Commercial License** (<https://fontstruct.com/>).

That license is **not compatible** with an MIT-licensed public repository, so
`Pixeled.ttf` is intentionally **excluded** from version control (see
`.gitignore`). Do not commit it and do not include it in a public release
archive unless you have verified that your use complies with the FontStruct
terms.

## Behaviour without the font

`main.py` registers `Fonts/Pixeled.ttf` only when the file exists:

```python
_font_path = os.path.join(os.path.dirname(__file__), "Fonts", "Pixeled.ttf")
if os.path.exists(_font_path):
    QFontDatabase.addApplicationFont(_font_path)
```

If the file is absent, the application starts normally and the Pixel theme
falls back to `Courier New`; every other theme is unaffected.

## Local use

If you own a licensed copy and want the original look on your own machine, place
it at:

```text
Fonts/Pixeled.ttf
```

Git will ignore it, so it stays local.
