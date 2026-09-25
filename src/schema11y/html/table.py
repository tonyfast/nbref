
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import partial, wraps
from toolz import pipe, compose_left as compose
from ..types import Schema, Subschema
from .core import role_mapping, Options

def html_table(schema: Schema, options: Options, *children, **attrs):
    table = options.el("table>thead", **attrs)

    yield table

def html_tbody(schema: Schema, options: Options, *children, **attrs):
    value = schema.value()      
    if isinstance(value, list):
        yield from html_tbody_list(schema, options, *children, **attrs)
    elif isinstance(value, dict):
        yield from html_tbody_dict(schema, options, *children, **attrs)

def html_tbody_list(schema: Schema, options: Options, *children, **attrs):
    # Implementation for handling list values in tbody
    for group in [schema.value()]:
        tbody =options.el("tbody")
        for item in schema.value():
            yield from html_row(schema, options, *children, **attrs)
        yield tbody

def html_row(schema: Schema, options: Options, *children, **attrs):
    value = schema.value() 
    row = options.el("tr", *children, **attrs)
    if isinstance(value, list):
        for item in value:
            options.el(row, options.el("td", *children, **attrs))
    elif isinstance(value, dict):
        for item in value.values():
            options.el(row, options.el("td", item))

    yield row

def html_tbody_dict(schema: Schema, options: Options, *children, **attrs):
    # Implementation for handling dict values in tbody
    for key, value in schema.value().items():
        yield options.el("tr", *children, **attrs)

    

role_mapping.update(
    table=html_table,
    # grid=html_grid,
    # treegrid=html_treegrid,
)
