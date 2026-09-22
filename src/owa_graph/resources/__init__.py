"""Curated resource shortcut groups (``owa-graph mail list ...``).

Each module exposes a ``COMMANDS`` dict mapping shortcut name to a
``(handler, help_text)`` tuple. Handlers receive ``(args, ctx)`` where
``args`` is the trailing argv list and ``ctx`` is a
:class:`owa_graph.ctx.RequestContext`. They return an exit code.

This package is imported lazily from ``cli.main`` only when the user
actually invokes a group; the verb-first path stays free of any
resource-table imports so cold-start cost is unaffected.
"""
import importlib

# Group registry: user-facing group name -> short description used by
# top-level ``--help``. Kept here (not in the group modules) so help
# generation is import-free; group modules are imported lazily.
GROUP_DESCRIPTIONS = {
    'me': 'Profile, photo, manager, direct reports',
    'mail': 'Read, send, reply, move, flag messages',
    'calendar': 'List/create events, find meeting times, RSVP',
    'files': 'List, upload, download, share OneDrive items',
    'users': 'Find/list users, manager and direct reports',
    'teams': 'Joined teams, channels, channel messages',
    'chats': 'List 1:1 + group chats, send messages',
    'presence': 'Read or set your Teams presence',
    'contacts': 'Personal contacts (list, find, create, delete)',
    'groups': 'Microsoft 365 groups (list, members)',
    'planner': 'Planner tasks, plans, buckets',
    'todo': 'Microsoft To-Do lists and tasks',
    'sites': 'SharePoint sites and lists',
    'directory': 'Directory roles and audit logs (admin scope)',
}


def known_groups():
    """Return the iterable of registered group names."""
    return GROUP_DESCRIPTIONS.keys()


def load_group(name):
    """Import and return the resource module for ``name``.

    Raises :class:`KeyError` for unknown groups; callers should check
    against :func:`known_groups` first.
    """
    if name not in GROUP_DESCRIPTIONS:
        raise KeyError(name)
    return importlib.import_module(f'{__name__}.{name}')
