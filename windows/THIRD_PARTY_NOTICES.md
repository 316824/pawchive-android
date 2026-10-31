# Third-party notices

Pawchive Downloader's original application code is distributed under the MIT
license in the repository root. The Windows executable also contains third-party
software; those components retain their own copyrights and license terms.
Their license texts are provided in `third_party_licenses/` in the portable ZIP
and in this source directory.

| Component | Project and source |
| --- | --- |
| Python runtime and standard library | https://www.python.org/ and https://github.com/python/cpython |
| PySide6 / Shiboken6 / Qt | https://doc.qt.io/qtforpython-6/licenses.html and https://code.qt.io/pyside/pyside-setup.git/ |
| Qt libraries and plugins | https://code.qt.io/qt/qtbase.git/ and https://www.qt.io/licensing/open-source-lgpl-obligations |
| Requests | https://github.com/psf/requests |
| Beautiful Soup | https://www.crummy.com/software/BeautifulSoup/ |
| urllib3 | https://github.com/urllib3/urllib3 |
| certifi | https://github.com/certifi/python-certifi |
| charset-normalizer | https://github.com/jawah/charset_normalizer |
| idna | https://github.com/kjd/idna |
| Soup Sieve | https://github.com/facelessuser/soupsieve |
| typing_extensions | https://github.com/python/typing_extensions |
| cryptography / OpenSSL / CFFI | https://github.com/pyca/cryptography and https://www.openssl.org/ and https://cffi.readthedocs.io/ |
| PyInstaller bootloader and packaging support | https://pyinstaller.org/en/stable/license.html and https://github.com/pyinstaller/pyinstaller |

The PySide6 and Qt components offer different license options. Consult the
included texts and the upstream documentation for the terms applicable to each
component. This application does not modify the upstream libraries. The source
and Windows build instructions in `README.md` allow rebuilding the application
with replacement or updated dependencies; any such build must retain the
applicable third-party notices.

The packaged EXE was supplied from the existing Windows build. Publishing the
application's MIT source does not relicense third-party libraries. License files
copied from installed distributions retain the original upstream wording.
