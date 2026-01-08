from . import hooks
from . import models


def mobile_api_post_init(env):
    hooks.post_init_hook(env)
