"""Dataset registry client: digests, archive, PackageRef, verified cache, HTTP client.

Registry is optional. Local path workflows never require it. Config Core still only
reads materialised local trees after resolve.
"""

from ageval.registry.archive import MEDIA_TYPE, build_archive, extract_archive
from ageval.registry.cache import PackageCache
from ageval.registry.client import RegistryClient, RegistryError
from ageval.registry.credentials import (
    DEFAULT_REGISTRY_URL,
    REGISTRY_URL_ENV,
    load_credentials,
)
from ageval.registry.digest import compute_package_digest
from ageval.registry.ref import PackageRef, parse_package_ref

__all__ = [
    "MEDIA_TYPE",
    "PackageCache",
    "PackageRef",
    "RegistryClient",
    "RegistryError",
    "build_archive",
    "compute_package_digest",
    "extract_archive",
    "DEFAULT_REGISTRY_URL",
    "REGISTRY_URL_ENV",
    "load_credentials",
    "parse_package_ref",
]
