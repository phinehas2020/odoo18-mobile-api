from . import hooks
from . import models


def post_init_hook(cr, registry):
    hooks.post_init_hook(cr, registry)
