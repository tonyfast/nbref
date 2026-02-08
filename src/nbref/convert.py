from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import json
from uuid import uuid4
from toolz.curried import get, compose, concatv, merge, map , pipe
import slugify
from toolz.curried.operator import setitem
import bs4
import markdown_it
DIR = Path(__file__).parent
from json import dumps
env = Environment(loader=FileSystemLoader(DIR / "templates"), enable_async=True)
import pygments.util, pygments.lexers, pygments.formatters

def tag(name, *contents, **attrs):
    element = bs4.BeautifulSoup("", "html.parser").new_tag(name, attrs=attrs)
    if contents:
        element.extend(contents)
    return element

def highlight(code, lang):
    try:
        lexer = pygments.lexers.get_lexer_by_name(lang)
    except pygments.util.ClassNotFound:
        lexer = pygments.lexers.TextLexer()
    formatter = pygments.formatters.HtmlFormatter(nowrap=True)
    return pygments.highlight(code, lexer, formatter)

env.globals.update(
    uuid=compose(str, uuid4),
)
env.filters.update(
    highlight=highlight,
    dumps = json.dumps,
    splitlines=str.splitlines,
    get=get,
    str=str,
    setitem=lambda c, a, b: setitem(a, b, c),
    markdown=markdown_it.MarkdownIt().render,
    concat=compose(list, concatv),
    merge=merge,
    sloc = lambda x: len(list(filter(bool, map(str.strip, "".join(x).splitlines()))))
)
tpl = env.get_template("main.html")
nb = json.loads((DIR.parent.parent / "docs/index.ipynb").read_text())
settings = json.loads((DIR / "templates" / "settings.ipynb").read_text())
target = DIR / "example.html"

def get_unified_attachments(nb):
    return pipe(
        nb["cells"], map(get("attachments", default={})), merge
    )
    
def ammend_attachments(nb, soup):
    attachments = get_unified_attachments(nb)
    if attachments:
        soup = bs4.BeautifulSoup(html, features="html.parser")
        for img in soup.select("img[src^='attachment']"):
            src = img.attrs.get("src", "")
            key = src.removeprefix("attachment:")
            attachment = attachments.get(key)
            if attachment:
                for mime, data in attachment.items():
                    img.attrs.update(
                        id = src,
                        src = F"data:{mime};base64,{data}"
                    )
                    break
    return soup

def render(nb):
    for cell in nb["cells"]:
        if cell["cell_type"] == "markdown":
            string = "".join(cell.get("source", ""))
            if string.lstrip():
                cell["outputs"] = [dict(
                    output_type="display_data",
                    data={
                        "text/markdown": cell["source"]
                    }
                )]
    html = tpl.render(nb=nb, settings=settings, config=dict(
        readonly=False
    ))
    soup = bs4.BeautifulSoup(html, "html.parser")
    ammend_attachments(nb, soup)
    ammend_headings(soup)
    
    return str(soup)
    
def ammend_headings(soup):
    for listing, cell in zip(soup.select("nav.cells.headings li.cell"), soup.select("ol.cells>li.cell")):
        hs = cell.select_one("details.outputs").select("h1, h2, h3, h4, h5, h6")
        if hs:
            local_headings = tag("ol")
            
            listing.append(local_headings)
        for h in hs:
            if not h.has_attr("id"):
                h["id"] = id = slugify.slugify(h.string)
            a = tag("a", str(h.string), href=F"#{id}")
            local_headings.append(
                tag("li", a, **{"data-level": h.name[1]})
            )
            h.insert_before(
                tag("a", "¶", href=F"#{id}", **{"class": "h"})
            )
    return soup
        

target.write_text(render(nb))
print(F"wrote {target.absolute().as_uri()}")
