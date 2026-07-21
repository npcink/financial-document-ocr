# Third-Party Notices

This project is licensed under GPL-3.0-only. Its dependencies remain available
under their respective licenses.

## PDF rendering

The backend uses `pypdfium2` 5.6.0 to render PDF pages before OCR.

- `pypdfium2` code is available under Apache-2.0 OR BSD-3-Clause.
- PDFium is available under a BSD-style license.
- PDFium bundles components under additional open-source licenses.

The installed `pypdfium2` wheel carries the build-specific license files for
PDFium and its bundled dependencies. Binary redistributions, including derived
container images or application bundles, must preserve those license files and
notices. The authoritative, build-specific texts are the files shipped in the
installed wheel; this summary does not replace them.

Upstream licensing information:

- <https://github.com/pypdfium2-team/pypdfium2#licensing>
- <https://pdfium.googlesource.com/pdfium/+/refs/heads/main/LICENSE>
