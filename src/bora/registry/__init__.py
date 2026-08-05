"""Database registry client: digests, archive, PackageRef, verified cache, HTTP client.

Registry is optional. Local path workflows never require it. Config Core still only
reads materialised local trees after resolve.
"""

from bora.registry.archive import MEDIA_TYPE, build_archive, extract_archive
from bora.registry.cache import PackageCache
from bora.registry.client import RegistryClient, RegistryError
from bora.registry.credentials import load_credentials
from bora.registry.digest import compute_package_digest
from bora.registry.ref import PackageRef, parse_package_ref

__all__ = [
    "MEDIA_TYPE",
    "PackageCache",
    "PackageRef",
    "RegistryClient",
    "RegistryError",
    "build_archive",
    "compute_package_digest",
    "extract_archive",
    "load_credentials",
    "parse_package_ref",
]
