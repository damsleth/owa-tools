"""Parse repeated --profile/-p flags out of an argv for multi-profile fan-out.

Pure/stdlib only. This module knows nothing about tools; it just splits the
shared `--profile`/`-p` flag(s) out of an argv so the fan-out machinery in
``modes`` can run a command once per profile.
"""
import sys

_PROFILE_FLAGS = ('--profile', '-p')


def parse_profiles(argv):
    """Extract repeated --profile/-p flags from argv.

    Returns ``(profiles, rest_argv)``:
      * ``profiles``: de-duplicated list of profile values preserving
        first-seen order. Only well-formed ``--profile <value>`` /
        ``-p <value>`` pairs (space-separated) and the ``--profile=<value>``
        equals form contribute.
      * ``rest_argv``: ``argv`` with every well-formed profile flag/value
        removed.

    A duplicate profile value warns once to stderr
    (``warning: duplicate --profile <v> ignored``) and is dropped from
    ``profiles`` (it stays out of ``rest_argv`` either way).

    A trailing bare ``--profile``/``-p`` with NO following value is left in
    ``rest_argv`` untouched and does NOT raise: the caller's N<=1 path passes
    the original argv to the tool dispatcher, which raises its own existing
    usage error.
    """
    profiles = []
    seen = set()
    rest = []
    i = 0
    n = len(argv)
    while i < n:
        arg = argv[i]
        # Equals form: --profile=foo / -p=foo
        if arg.startswith('--profile=') or arg.startswith('-p='):
            value = arg.split('=', 1)[1]
            if value:
                _record(value, profiles, seen)
                i += 1
                continue
            # `--profile=` with empty value: leave untouched.
            rest.append(arg)
            i += 1
            continue
        if arg in _PROFILE_FLAGS:
            if i + 1 >= n:
                # Dangling flag with no value: leave it in rest untouched.
                rest.append(arg)
                i += 1
                continue
            value = argv[i + 1]
            _record(value, profiles, seen)
            i += 2
            continue
        rest.append(arg)
        i += 1
    return profiles, rest


def _record(value, profiles, seen):
    if value in seen:
        sys.stderr.write(f'warning: duplicate --profile {value} ignored\n')
        return
    seen.add(value)
    profiles.append(value)
