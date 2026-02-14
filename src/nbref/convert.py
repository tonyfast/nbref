from jinja2 import Environment, FileSystemLoader
from pathlib import Path
import json, argparse
from uuid import uuid4
from toolz.curried import get, compose, concatv, merge, map , pipe, complement
import slugify
from toolz.curried.operator import setitem
import bs4

DIR = Path(__file__).parent
from json import dumps
import pygments.util, pygments.lexers, pygments.formatters


HEADINGS = "h1, h2, h3, h4, h5, h6"
class Config:
    navigation_expanded: bool = False
    readonly: bool = False
    orientation: str = "in-out"
        

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

def get_markdown():
    import markdown_it
    return markdown_it.MarkdownIt()

def order_outputs(outputs:dict, display_priority):
    first = list(filter(outputs.__contains__, display_priority))
    return first + list(filter(complement(first.__contains__), outputs))

def get_environment():
    env = Environment(loader=FileSystemLoader(DIR / "templates"), enable_async=True)
    env.globals.update(
        uuid=compose(str, uuid4),
    )
    
    env.filters.update(
        range=range,
        highlight=highlight,
        dumps = json.dumps,
        splitlines=str.splitlines,
        get=get,
        str=str,
        minimum=min,
        maximum=max,
        order_outputs=order_outputs,
        setitem=lambda c, a, b: setitem(a, b, c),
        markdown=get_markdown().render,
        concat=compose(list, concatv),
        merge=merge,
        sloc = lambda x: len(list(filter(bool, map(str.strip, "".join(x).splitlines()))))
    )
    return env
    
def get_settings_document():
    return json.loads((DIR / "templates" / "settings.ipynb").read_text())

async def arender_notebook_file(
    nb: Path=None, template="main.html", target=None, **config
):
    import anyio
    if nb is None:
        nb = DIR.parent.parent / "docs/index.ipynb"
    if target is None:
        target = DIR / "example.html"    
    data = json.loads(await anyio.Path(nb).read_text())
    return await arender_notebook(data, template, target, **config)

async def arender_notebook(
    data, template="main.html", target=None, **config
):
    """creates html from a notebook document, returns a BeautifulSoup object"""
    env = get_environment()
    tpl = env.get_template("main.html")
    prepare_notebook(data)
    html = await env.get_template("main.html").render_async(
        nb=data,
        settings=get_settings_document(),
        config=config
    )
    soup = bs4.BeautifulSoup(html, "html.parser")
    ammend_attachments(data, soup)
    ammend_headings(soup)
    for output in soup.select("section.nb li.cell details.outputs"):
        first_heading = output.select_one(HEADINGS)
        if first_heading:
            title = soup.select_one("title")
            title.clear()
            title.append(str(first_heading.string))
            print(title, first_heading)
            t = soup.select_one("hgroup").select_one(HEADINGS)
            t.clear()
            t.append(str(first_heading.string))
            break
    return soup
    
import re
async def awrite_notebook(
    target, nb: Path=None, template="main.html", **config
):
    import anyio
    soup = await arender_notebook_file(nb, template, target, **config)
    file = anyio.Path(nb)
    html = str(soup)
    
    # html = re.sub(r'>\s*</input>.+', '/>', html)
    # html = html.replace("></input>", " />")
    await anyio.Path(target).write_text(html)
    print(F"wrote {target.absolute()}")
    

def awrite_notebooks(
    files: list[Path], template="main.html", **config
):
    import asyncio, anyio
    coro = []
    dir = config.get("dir")
    for file in map(Path, files):
        target = (
            Path(dir) if dir else file.parent
        ) / file.with_suffix(".html").name #(file.name + ".html")
        coro.append(awrite_notebook(target, file, **{
            "readonly": False,
            "navigation_expanded": False,
            "orientation": "no-source",
        }))
    return asyncio.gather(*coro)

def get_unified_attachments(nb):
    return pipe(
        nb["cells"], map(get("attachments", default={})), merge
    )
    
def ammend_attachments(nb, soup):
    attachments = get_unified_attachments(nb)
    if attachments:
        # soup = bs4.BeautifulSoup(soup, features="html.parser")
        for img in soup.select("img[src^='attachment']"):
            src = img.attrs.get("src", "")
            key = src.removeprefix("attachment:")
            attachment = attachments.get(key)
            if attachment:
                for mime, data in attachment.items():
                    img.attrs.update(
                        id = src,
                        src = F"data:{mime};base64,{data}",
                        **{"class": ["attachment"]}
                    )
                    break
    return soup

def prepare_notebook(nb):
    for cell in nb["cells"]:
        if cell["cell_type"] == "markdown":
            string = "".join(cell.get("source", ""))
            if string.lstrip():
                cell["outputs"] = [dict(
                    output_type="display_data",
                    data={
                        "text/markdown": cell["source"],
                        "text/html": get_markdown().render("".join(cell["source"]))
                    }
                )]
    
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
        readonly=False,
        navigation_expanded=False,
        orientation="no-source",
    ))
    soup = bs4.BeautifulSoup(html, "html.parser")
    ammend_attachments(nb, soup)
    ammend_headings(soup)
    print(soup.select("section.nb li.cell details.outputs"))
    for output in soup.select("section.nb li.cell details.outputs"):
        first_heading = output.select_one("h1, h2, h3, h4, h5, h6")
        if first_heading:
            title = soup.select_one("title")
            title.clear()
            title.append(first_heading.string)
            print(title, first_heading)
            break
    return str(soup)
    
    
def ammend_headings(soup):
    for listing, cell in zip(soup.select("details.nb.nav nav li.cell"), soup.select("ol.cells>li.cell")):
        hs = cell.select_one("details.outputs").select("h1, h2, h3, h4, h5, h6")
        if hs:
            local_headings = tag("ol", **{"class": "headings"})
            listing.append(local_headings)
        for h in hs:
            if not h.has_attr("id"):
                h["id"] = id = slugify.slugify(" ".join(x.string or "" for x in h))
            a = tag("a", str(h.string), href=F"#{id}")
        
            local_headings.append(
                tag("li", a, **{"data-level": h.name[1]})
            )
            if h.parent.name == "hgroup":
                h = h.parent
            
            h.insert_before(
                tag("a", "¶", href=F"#{id}", **{"class": "h"})
            )
    return soup
    
parser = argparse.ArgumentParser()
parser.add_argument("file", nargs="*")
parser.add_argument("-d", "--dir", default=None)
parser.add_argument("--stdout", action="store_true")


def main(argv=None):
    import asyncio, anyio
    ns = parser.parse_args(argv)
    coro = []
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    coro = awrite_notebooks(ns.file, ns, **{
        "readonly": False,
        "navigation_expanded": False,
        "orientation": "no-source",
    })
    loop.run_until_complete(coro)

# create an synchronous and asynchronous version of the function that writes the notebook to a file

# write a function that does teh fibonacci sequence using recursion and memoization
if __name__ == "__main__":
    main()
    
# target.write_text(render(nb))
# print(F"wrote {target.absolute().as_uri()}")
