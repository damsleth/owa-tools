"""Normalisation for /me/people, /users, /me/contacts.

Each upstream shape is a little different. We project them into a
single flat dict so callers can treat them uniformly:
    {
      'id': str,
      'displayName': str,
      'email': str | '',          # primary SMTP / userPrincipalName
      'jobTitle': str | '',
      'department': str | '',
      'companyName': str | '',
      'officeLocation': str | '',
      'mobilePhone': str | '',
      'businessPhones': [str],
      'source': 'people' | 'directory' | 'contacts',
    }
"""


def _first_email(entry):
    """Best-effort extract a primary SMTP address from any of the
    upstream shapes."""
    # /me/people: scoredEmailAddresses: [{address, relevanceScore}]
    addrs = entry.get('scoredEmailAddresses') or []
    if isinstance(addrs, list) and addrs:
        a = addrs[0]
        if isinstance(a, dict) and a.get('address'):
            return a['address']
    # /me/contacts: emailAddresses: [{name, address}]
    addrs = entry.get('emailAddresses') or []
    if isinstance(addrs, list) and addrs:
        a = addrs[0]
        if isinstance(a, dict) and a.get('address'):
            return a['address']
    # /users: mail or userPrincipalName
    return entry.get('mail') or entry.get('userPrincipalName') or ''


def normalize_person(entry, source):
    return {
        'id': entry.get('id') or '',
        'displayName': entry.get('displayName') or '',
        'email': _first_email(entry),
        'jobTitle': entry.get('jobTitle') or '',
        'department': entry.get('department') or '',
        'companyName': entry.get('companyName') or '',
        'officeLocation': entry.get('officeLocation') or '',
        'mobilePhone': entry.get('mobilePhone') or '',
        'businessPhones': entry.get('businessPhones') or [],
        'source': source,
    }


def normalize_group(entry):
    """Flatten a directoryObject from /memberOf.

    /memberOf returns a mixed bag of group, directoryRole and
    administrativeUnit objects; we keep the common fields and surface
    the @odata.type so callers can tell them apart.
    """
    kind = (entry.get('@odata.type') or '').lstrip('#').removeprefix('microsoft.graph.')
    return {
        'id': entry.get('id') or '',
        'displayName': entry.get('displayName') or '',
        'mail': entry.get('mail') or '',
        'description': entry.get('description') or '',
        'type': kind,
    }
