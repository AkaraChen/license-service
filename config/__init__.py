"""django-user-sessions 2.0 imports pkg_resources only for __version__."""

import sys
import types

if "pkg_resources" not in sys.modules:
    pkg_resources = types.ModuleType("pkg_resources")

    class DistributionNotFound(Exception):
        pass

    def get_distribution(_name):
        raise DistributionNotFound

    pkg_resources.DistributionNotFound = DistributionNotFound
    pkg_resources.get_distribution = get_distribution
    sys.modules["pkg_resources"] = pkg_resources
