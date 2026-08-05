from functools import lru_cache
import uuid

from nbref.htmls import html_applicator
from nbref.schemas import Schema

@lru_cache(maxsize=1)
def get_nb_schema():
    from .schema import parent

    return Schema.from_file(parent / "nb.yaml").expand()

def html_nb(schema, object, options, **attrs):
    nb = Notebook(object)
    yield from html_applicator(nb.schema, nb, options, **attrs)


# this representation of a notebook relies on an alternate framing of the 
# standard notebook schema. in our schema, we consider one cell type represented
# generically. to ensure this, we have to make modifications to cells that ensure
# id and outputs for raw/markdown cells. a way around ambiguity of the raw cell is to define the mimetype in the metadata.
# then let a kernel handle the mime type dispatching necessary.
class Notebook(Schema.Dict):
    @classmethod
    def from_file(cls, path):
        return cls(super().from_file(path))
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ensure_ids()
        self.ensure_raw_output()
        self.ensure_execution()
        self.schema = get_nb_schema()

    def ensure_ids(self):
        for cell in self.get("cells", []):
            if "id" not in cell:
                cell["id"] = str(uuid.uuid4())
    def ensure_execution(self):
        for cell in self.get("cells", []):
            if "execution_count" not in cell:
                cell["execution_count"] = -1
            if cell["execution_count"] is None:
                cell["execution_count"] = -1
    def generate_toc(self, soup):
        from .utils import sluggify
        prefixes = []
        for heading in soup.select("h1,h2,h3,h4,h5,h6"):
            heading.attrs.setdefault("id", sluggify(heading.string))
            prefixes.append(dict(role="link", type="string", default=heading.string, attrs=dict(href="#" + heading.attrs["id"])))
        headings = Schema(prefixItems=prefixes, title="headings", tags=["nav"], parent=dict(
            role="group", title="headings"
        ))
        return headings().set_schema(headings).set_name("nav").render_bs4()

    def ensure_raw_output(self):
        for cell in self.get("cells", []):
            if cell.get("cell_type") == "markdown":
                cell["outputs"] = [{
                        "output_type": "display_data",
                        "data": {
                            "text/markdown": cell.get("source", "")
                        },
                        "metadata": {}
                    }]
            if cell.get("cell_type") == "raw":
                # there are a lot of ways this assumption can fail,
                # we can create new modes of notebook interactions.
                source = "".join(cell.get("source", ""))
                if "://" in source:
                    cell["outputs"] = [{
                            "output_type": "display_data",
                            "data": {
                                cell.get("metadata", {}).get("contentMediaType", "text/uri-list"): "".join(source),
                            },
                            "metadata": {}
                        }]
                    
    def render_bs4(self, options, *children, **attrs):
        if options is None:
            from .htmls import Options
            options = Options()
        object = super().render_bs4(options, *children, **attrs)
        options.el("nav.nb")
        object.insert(1, options.el("nav.top.nb", self.generate_toc(object)))
        object.append(options.el("nav.bottom.nb"))
        return object
    
Schema.Notebook = Notebook