from functools import lru_cache

from ...types import Schema
from pathlib import Path
from ...html import Options, html_root, content_mapping, html_validator
HERE = Path(__file__).parent
    
notebook_schema = schema = Schema.from_id( HERE / "core.yaml").expand()

@lru_cache(1)
def full_schema():
    return Schema.from_id(HERE / "full.yaml").expand()

def html_patch_cell(schema: Schema, options: Options = None, **attrs):
    # print("patch", schema.aid())
    value = schema.value()
    schema = schema.append(tags=[value["cell_type"]])
    
    if value["cell_type"] == "markdown":
        value["execution_count"] = -1
        value["outputs"] = [dict(data={"text/markdown": value["source"]})]
    elif value["cell_type"] == "raw":
        content_type = value.get("metadata", {}).get("contentSchema", {}).get("contentMediaType")
        if content_type == "text/uri-list":
            value["outputs"] = [dict(data={"text/uri-list": value["source"]})]

    content_schema = value.get("metadata", {}).get("contentSchema")
    if content_schema:
        schema = schema.append(dict(properties=dict(source=dict(contentSchema=content_schema))))

    schema = html_notebook_cell_metadata(schema, options, **attrs)

    return schema

def html_notebook_metadata(schema: Schema, options: Options = None, **attrs):
    # a lot of this information can be extracted from git
    return schema

def html_notebook_cell_metadata(schema: Schema, options: Options = None, **attrs):
    jupyter = schema.value().get("metadata", {}).get("jupyter", {})
    source_hidden = jupyter.get("source_hidden", False)
    output_hidden = jupyter.get("output_hidden", False)
    collapsed = jupyter.get("collapsed", False)
    scrolled = jupyter.get("scrolled", False)
    cell_tags = []
    if source_hidden:
        cell_tags.append("source_hidden")
    if output_hidden:
        cell_tags.append("output_hidden")
    if collapsed:
        cell_tags.append("collapsed")
    if scrolled:
        cell_tags.append("scrolled")
    if cell_tags:
        schema = schema.append(tags=[cell_tags])
    return schema

def html_notebook(schema: Schema, options: Options = None, **attrs):
    patch = options.patch | {
        "#/properties/cells/items": html_patch_cell,
        # "#/properties/cells/items/properties/execution_count": print,
    }
    if not schema.get("$dynamicAnchor"):
        # ensure the notebook schema is attached to the value
        schema = notebook_schema.linked(schema.value(), schema.aid(), base=schema.abase())
    with options.enter(patch=patch, input=True, output=True) as options:
        document = list(html_validator(schema, options, **attrs)) 
    yield from patch_attachments(document, schema, options)
    yield options.el("style.read", Path(HERE / "style.css").read_text())

#todo
def replace_title(document, title):
    for doc in document:
        if doc.select_one("title"):
            doc.select_one("title").string = title
    return document

# add headings to the site navigation
# replace the title and description

def patch_attachments(document, schema, options):
    import collections
    for doc in document:
        attachments = collections.ChainMap(*filter(bool, (x.get("attachments", None) for x in schema.value().get("cells", []))))

        for img in doc.select("""img[src^="attachment"]"""):
            filename = img["src"].removeprefix("attachment:")
            *_, ext = filename.rpartition(".")
            for type, data in attachments.get(filename, {}).items():
                img["src"] = F"data:{type};base64,{data}"
        yield doc

NOTEBOOK = "application/x-ipynb+json"
content_mapping[NOTEBOOK] = html_notebook