"""reference implementations of aria first notebooks"""
__version__ = "0.1.0"

from .schemas import Schema

from . import schema

import referencing
core = referencing.Resource(
    Schema.from_file(schema.parent / "meta.yaml").builtin(), 
    referencing.jsonschema.DRAFT202012
)
Schema.Ref.REGISTRY = Schema.Ref.REGISTRY.with_resource(core.id(), core).crawl()

from .metaschema import meta

import sys
if "IPython" in sys.modules:
    from .ipython import load_ipython_extension, unload_ipython_extension
    from IPython import get_ipython
    load_ipython_extension(get_ipython())
del sys