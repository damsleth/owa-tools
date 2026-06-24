"""OData query-string helpers shared across owa-tools API modules."""
import urllib.parse


def build_query(params):
    """Build an OData query string.

    Values are URL-encoded; keys are left as-is (they are $-prefixed OData
    system params such as ``$top``, ``$filter``, ``$select``).
    """
    parts = []
    for k, v in params.items():
        parts.append(f'{k}={urllib.parse.quote(str(v), safe="")}')
    return '&'.join(parts)
