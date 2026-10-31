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

The v1.0.1 Windows build uses PySide6-Essentials / Shiboken6 6.12.0,
Requests 2.34.2 and Beautiful Soup 4.15.0. The Essentials distribution provides
the required PySide6 modules without installing the complete Qt Addons,
WebEngine or PDF distributions. Only modules and plugins needed by the
application are selected for packaging. The direct runtime and build versions
are recorded in `requirements.txt` and `requirements-build.txt`.

Some license texts and component entries are retained from the v1.0.0 archive;
their presence does not mean every component is included in every version.
The standard library's TLS support uses OpenSSL independently of whether the
optional cryptography / CFFI packages are present.

The PySide6 and Qt components offer different license options. Consult the
included texts and the upstream documentation for the terms applicable to each
component. This application does not modify the upstream libraries. The source
and Windows build instructions in `README.md` allow rebuilding the application
with replacement or updated dependencies; any such build must retain the
applicable third-party notices.

The v1.0.1 build configuration excludes conflicting copies of the Windows system
ICU libraries and relies on the target operating system's implementation. It does
not redistribute ICU DLLs taken from the build computer's Windows directory or
from unrelated installed applications. See Microsoft's description of the
[Windows ICU APIs](https://learn.microsoft.com/en-us/windows/win32/intl/international-components-for-unicode--icu-).

Unlike the reused executable in v1.0.0, v1.0.1 is rebuilt using the repository's
`build_release.py` and `PawchiveDownloader.spec`. Publishing the application's MIT
source does not relicense third-party libraries. License files copied from
installed distributions retain the original upstream wording.
