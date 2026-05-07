"""Curated resource shortcut groups (``owa-graph mail list ...``).

Each module exposes a ``COMMANDS`` dict mapping shortcut name to a
``(handler, help_text)`` tuple. Handlers receive ``(args, ctx)`` where
``args`` is the trailing argv list and ``ctx`` is a
:class:`owa_graph.ctx.RequestContext`. They return an exit code.

This package is imported lazily from ``cli.main`` only when the user
actually invokes a group; the verb-first path stays free of any
resource-table imports so cold-start cost is unaffected.
"""

# Group registry: maps the user-facing group name to the lazy loader.
# Loaders are zero-arg functions returning the module; we don't import
# at package import time because ``owa-graph --help`` should never pay
# for resource code it doesn't run.

_GROUP_LOADERS = {
    'me': lambda: __import__('owa_graph.resources.me', fromlist=['_']),
    'mail': lambda: __import__('owa_graph.resources.mail', fromlist=['_']),
    'calendar': lambda: __import__('owa_graph.resources.calendar', fromlist=['_']),
    'files': lambda: __import__('owa_graph.resources.files', fromlist=['_']),
    'users': lambda: __import__('owa_graph.resources.users', fromlist=['_']),
    'teams': lambda: __import__('owa_graph.resources.teams', fromlist=['_']),
    'chats': lambda: __import__('owa_graph.resources.chats', fromlist=['_']),
    'presence': lambda: __import__('owa_graph.resources.presence', fromlist=['_']),
    'contacts': lambda: __import__('owa_graph.resources.contacts', fromlist=['_']),
    'groups': lambda: __import__('owa_graph.resources.groups', fromlist=['_']),
    'planner': lambda: __import__('owa_graph.resources.planner', fromlist=['_']),
    'todo': lambda: __import__('owa_graph.resources.todo', fromlist=['_']),
    'sites': lambda: __import__('owa_graph.resources.sites', fromlist=['_']),
    'directory': lambda: __import__('owa_graph.resources.directory', fromlist=['_']),
}


# Short descriptions used by top-level ``--help``. Kept here (not in the
# group modules) so help generation is import-free.
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
    return _GROUP_LOADERS.keys()


def load_group(name):
    """Import and return the resource module for ``name``.

    Raises :class:`KeyError` for unknown groups; callers should check
    against :func:`known_groups` first.
    """
    return _GROUP_LOADERS[name]()
