# house.mi.gov's server sends its leaf cert but not the intermediate it
# chains through (DigiCert Global G3 TLS ECC SHA384 2020 CA1) - a server
# misconfiguration, not an untrusted cert (confirmed via openssl s_client:
# the leaf's issuer matches this intermediate, which chains to DigiCert's
# trusted root). Rather than disabling verification, supply the missing
# intermediate ourselves alongside the normal trusted-root bundle.
import os
import tempfile

import certifi

_INTERMEDIATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "house_mi_gov_intermediate.pem"
)
_cached_path = None


def house_mi_gov_ca_bundle() -> str:
    """Path to a CA bundle (certifi's trusted roots + the intermediate
    house.mi.gov fails to send) that verifies house.mi.gov properly instead
    of skipping verification entirely."""
    global _cached_path
    if _cached_path is None:
        with open(certifi.where(), encoding="utf-8") as f:
            roots = f.read()
        with open(_INTERMEDIATE_PATH, encoding="utf-8") as f:
            intermediate = f.read()
        fd, path = tempfile.mkstemp(suffix=".pem", prefix="house_mi_gov_ca_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(roots)
            f.write(intermediate)
        _cached_path = path
    return _cached_path
