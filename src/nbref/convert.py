from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import json
from uuid import uuid4
from toolz.curried import get, compose, concatv, merge
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
html = tpl.render(nb=nb, settings=settings, config=dict(
    readonly=False
))
soup = bs4.BeautifulSoup(html, "html.parser")
nav =  soup.select_one("nav.cells.headings dl")
for nearest_cell in soup.select("ol.cells>li.cell"):
    for h in nearest_cell.select_one("details.outputs").select("h1, h2, h3, h4, h5, h6"):
        if not h.has_attr("id"):
            h["id"] = id = slugify.slugify(h.string)
        cell_index = int(nearest_cell["aria-posinset"])  
        cell_nav = nav.select_one(F"[data-cell='{cell_index}']")
        dd = tag("a", str(h.string), href=F"#{id}")
        cell_nav and cell_nav.insert_after(
            tag("dd", dd, **{"data-level": h.name[1]})
        )
        h.insert_before(
            tag("a", "¶", href=F"#{id}", **{"class": "h"})
        )
        

target.write_text(str(soup))
print(F"wrote {target.absolute().as_uri()}")
