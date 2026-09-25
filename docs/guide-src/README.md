# Guide source

The source of `docs/our-ba-approach.pdf`, the BA guide. Edit here, never the PDF.

| File | What it does |
|---|---|
| `build.py` | All the page content and layout. One `slide(...)` call per page. Writes the pages to `project/`. |
| `to_pdf.py` | Joins the pages into one HTML file and prints it to `../our-ba-approach.pdf` with Chrome. |

## Rebuild the PDF

```
python build.py
python to_pdf.py
```

- It needs Google Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe`. On another path, change
  `chrome` in `to_pdf.py`.
- Adding or removing a page: change `TOTAL` at the top of `build.py` too. The page numbers in the footer use it.
- Close the PDF in any viewer first. Windows will not let the file be replaced while it is open.
- Check the pages you changed before you commit: each page is 1920×1080 and cuts off what does not fit.
  For example, `uv run --with pymupdf python -c "import pymupdf; pymupdf.open('../our-ba-approach.pdf')[10].get_pixmap(dpi=40).save('p11.png')"`
  saves page 11 as a small image.

`project/` and `our-ba-approach.html` are build output and are not committed.
