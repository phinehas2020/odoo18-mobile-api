from . import hooks
from . import models


def post_init_hook(env):
    hooks.post_init_hook(env.cr, env.registry)
