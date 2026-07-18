
def magic_string(line, cell=None):
    if cell is None:
        return magic_file(line)
    from .schemas import Schema
    schema = Schema.from_string(cell)
    object = schema.default()
    return object.render_html()

def magic_file(line):
    from .schemas import Schema
    schema = Schema.from_file(line)
    object = schema.default()
    return object.render_html()

def load_ipython_extension(shell):
    shell.register_magic_function(magic_string, "line_cell", "jsonschema")
    shell.register_magic_function(magic_string, "line_cell", "schema")

def unload_ipython_extension(shell):
    pass