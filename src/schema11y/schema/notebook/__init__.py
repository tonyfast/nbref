from ...types import Schema
from pathlib import Path
from ...html import Options, html_root, content_mapping, html_validator
HERE = Path(__file__).parent

notebook_schema = schema = Schema.from_id( HERE / "core.yaml").expand()

class Options(Options):
    pass

def html_patch_cell(schema: Schema, options: Options = None, **attrs):
    # print("patch", schema.aid())
    value = schema.value()
    if value["cell_type"] == "markdown":
        value["outputs"] = [dict(data={"text/markdown": value["source"]})]

    content_schema = value.get("metadata", {}).get("contentSchema")
    if content_schema:
        schema = schema.append(dict(properties=dict(source=dict(contentSchema=content_schema))))
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

#todo
def replace_title(document, title):
    for doc in document:
        if doc.select_one("title"):
            doc.select_one("title").string = title
    return document

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