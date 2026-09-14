
from .types import Schema
from argparse import ArgumentParser
import sys
parser = ArgumentParser()

def json_schema_magic(line, cell=None):
    line = parser.parse_args(line.split())

    if cell is not None:
        return Schema.from_string(cell).html()
    raise NotImplementedError("Should load from a file or url or something.")

def load_ipython_extension(shell):
    shell.register_magic_function(json_schema_magic, "cell", "jsonschema")
    shell.register_magic_function(json_schema_magic, "cell", "schema")

def unload_ipython_extension(shell):
    pass

if "IPython" in sys.modules:
    from IPython import get_ipython
    ipython = get_ipython()
    if ipython is not None:
        load_ipython_extension(ipython)