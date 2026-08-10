"""macOS LibreSSL: urllib3 NotOpenSSLWarning must not reach the user."""

from __future__ import annotations

import warnings


def test_libressl_warning_message_is_filtered():
    """The ignore filter used by emby_cli must catch urllib3's LibreSSL notice."""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        # Same rule as __init__.py / client.py / cli.py (after simplefilter).
        warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
        warnings.warn(
            "urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' "
            "module is compiled with 'LibreSSL 2.8.3'. See: "
            "https://github.com/urllib3/urllib3/issues/3020",
            UserWarning,
            stacklevel=2,
        )

    assert recorded == []
