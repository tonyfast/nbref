HTML = "text/html"
MARKDOWN = "text/markdown"
PNG = "image/png"
JPEG = "image/jpeg"
GIF = "image/gif"
SVG_XML = "image/svg+xml"
URI_LIST = "text/uri-list"

from .types import Schema, Subschema
from .html import html_plain, Options, content_mapping, unified_string

def html_html(schema: Schema, options: Options, *children, **attrs):
    value = unified_string(schema.value())
    yield from options.el(value, *children, raw=True, **attrs)

def html_markdown(schema: Schema, options: Options, *children, **attrs):
    from midgy.tangle import get_markdown_it
    value = unified_string(schema.value())
    len_value = 0
    value = get_markdown_it().render(value)
    while len_value != len(value):
        len_value = len(value)
        value = value.rstrip().removesuffix("< />")
    yield from options.el(value, *children, raw=True, **attrs)

def html_image(schema: Schema, options: Options, *children, **attrs):
    value = unified_string(schema.value())
    mimetype = schema.get("contentMediaType")
    data = F"data:{mimetype};base64,{value}"
    yield options.el("img", *children, src=data, **attrs)

def html_uri_list(schema: Schema, options: Options, *children, **attrs):
    # needs work
    from .html import html_content, html_root
    value = unified_string(schema.value())
    uris = value.splitlines()
    for uri in filter(str.strip, uris):
        if "://" in uri:
            from .mimetypes import guess
            mimetype = guess(uri)
            value = Subschema.resolve(uri)
            subschema = Schema(contentMediaType=mimetype).linked(value, base=uri)
            yield from html_content(subschema, options)
        elif uri.startswith(("data:",)):
            bulk, sep, data = uri.removeprefix("data:").partition(",")
            mimetype, sep, encoding = bulk.rpartition(";")[0] if bulk else None
            if not mimetype:
                mimetype, encoding = encoding, mimetype
            subschema = Schema(contentMediaType=mimetype).linked(data)
            yield from html_content(subschema, options)


content_mapping.update({
    HTML: html_html,
    MARKDOWN: html_markdown,
    PNG: html_image,
    JPEG: html_image,
    GIF: html_image,
    SVG_XML: html_html,
    URI_LIST: html_uri_list,
})
