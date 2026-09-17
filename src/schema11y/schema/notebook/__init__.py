from ...types import Schema
from pathlib import Path
from ...html import Options, html_root, content_mapping
HERE = Path(__file__).parent

schema = Schema.from_id( HERE / "core.yaml").expand()

def html_patch_cell(schema: Schema, options: Options = None, **attrs):
    value = schema.value()
    if value["cell_type"] == "markdown":
        value["outputs"] = [dict(data={"text/markdown": value["source"]})]

    return schema

def html_notebook(schema: Schema, options: Options = None, **attrs):
    patch = options.patch | {
        "#/properties/cells/items": html_patch_cell
    }
    print("notebook")
    with options.enter(patch=patch, input=True) as options:
        document = list(html_root(schema, options, **attrs))
    yield from patch_attachments(document, schema, options)

def patch_attachments(document, schema, options):
    import collections
    for doc in document:
        attachments = collections.ChainMap(*filter(bool, (x.get("attachments", None) for x in doc.value().get("cells"))))

        for img in doc.select("""img[src^="attachment"]"""):
            filename = img["src"].removeprefix("attachment:")
            *_, ext = filename.rpartition(".")
            img["src"] = F"data:{ext};base64,{attachments.get(filename)}"
        yield doc

content_mapping["application/x-ipynb+json"] = html_notebook