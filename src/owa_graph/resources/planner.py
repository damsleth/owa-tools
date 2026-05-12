"""``owa-graph planner`` - Planner tasks, plans, buckets."""
from __future__ import annotations

from owa_core.errors import InternalError, UsageError

from . import _argv


def cmd_tasks(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/planner/tasks')


def cmd_plans(args, ctx):
    _argv.parse(args)
    return ctx.get('/me/planner/plans')


def cmd_buckets(args, ctx):
    parsed, pos = _argv.parse(args, flags=('--plan',))
    plan = parsed.get('--plan') or (pos[0] if pos else None)
    if not plan:
        raise UsageError('buckets requires --plan <plan-id>')
    return ctx.get(f'/planner/plans/{plan}/buckets')


def cmd_complete(args, ctx):
    """Mark a task complete (PATCH percentComplete=100).

    Planner requires a strong ETag on PATCH; we GET the task first to
    learn its etag, then PATCH with ``If-Match``. Two round-trips, but
    saves callers from chasing the etag manually.
    """
    parsed, pos = _argv.parse(args, flags=('--id',))
    task_id = parsed.get('--id') or (pos[0] if pos else None)
    if not task_id:
        raise UsageError('complete requires --id')
    from .. import api as api_mod
    url = api_mod.build_url(ctx.api_base, f'/planner/tasks/{task_id}')
    current = api_mod.api_request(
        'GET', '', url, ctx.access_token,
        debug=ctx.debug, retry=ctx.retry,
    )
    if not isinstance(current, dict):
        return 1
    etag = current.get('@odata.etag')
    if not etag:
        raise InternalError('planner task has no etag; cannot PATCH')
    return ctx.patch(f'/planner/tasks/{task_id}',
                     {'percentComplete': 100},
                     headers={'If-Match': etag})


COMMANDS = {
    'tasks': (cmd_tasks, 'List my planner tasks'),
    'plans': (cmd_plans, 'List my planner plans'),
    'buckets': (cmd_buckets, 'List buckets in --plan'),
    'complete': (cmd_complete, 'Mark --id task complete'),
}
