from pathlib import Path
import re
HERE = Path(__file__).parent

from .objects import Object, String
from functools import lru_cache

def get_mimetypes():
    from mimetypes import MimeTypes
    mimes = MimeTypes()
    mimes.read(HERE / "mime.types")
    return mimes

def retrieve(uri):
    """retrieve a resource from a uri, returning a referencing.Resource"""
    import requests_cache, referencing
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return retrieve_file(uri[len("file://"):])
    requests_cache.install_cache("nbref_cache")
    return requests_cache.requests.get(uri)
    return referencing.Resource(
        Object.from_string(response.text), referencing.jsonschema.DRAFT202012)

def retrieve_file(path):
    """retrieve a resource from a uri, returning a referencing.Resource"""
    import referencing
    print(path)
    response = Path(path).expanduser().read_text()
    return type("tmp", (), dict(text=response))

def retrieve_schema(uri):
    """retrieve a resource from a uri, returning a referencing.Resource"""
    response = retrieve(uri)    
    import referencing
    subschema = Object.from_string(response.text)
    if "$id" not in subschema:
        subschema["$id"] = uri
    return referencing.Resource(
        subschema, referencing.jsonschema.DRAFT202012)


@lru_cache(maxsize=1)
def get_nbref_schema():
    import referencing
    from .schemas import Schema
    schema = Object.from_file(
        Path(__file__).parent / "schema" / "meta.yaml"
    )
    return {schema["$id"]: referencing.Resource(
        schema, referencing.jsonschema.DRAFT202012
    )}

@lru_cache(maxsize=1)
def get_registry():
    import jsonschema_specifications, referencing
    registry = jsonschema_specifications.REGISTRY
    return referencing.Registry(
        {
            k: referencing.Resource(Object.dispatch(v.contents), v._specification)
            for k, v in registry.items()
        } | get_nbref_schema(), registry._anchors, registry._uncrawled, retrieve_schema
    ).crawl()

class Ref(String):
    REGISTRY = get_registry()
    default_specification = __import__("referencing").jsonschema.DRAFT202012

    def __init__(self, value, *args, **kwargs):
        super().__init__(value, *args, **kwargs)
        self.root = None

    # the ref resolver may not return a schema.
    def resolve(self, root=None, specification=None):
        import referencing
        registered = Ref.REGISTRY.get(self)
        if registered is not None:
            return registered.contents
        if root is None:
            root = self.root
            # if root is self:
            #     root = {}
        if root is None:
            return retrieve_schema(self)
        if specification is None:
            specification = Ref.default_specification
        # print(self.path, self)
        # print(self.path, root)
        # if "$id" in root:
        #     id = root["$id"]
        #     subschema = Ref.REGISTRY.resolver(
        #         id
        #     ).lookup(self).contents
        # else:
        subschema = Ref.REGISTRY.resolver_with_root(
            referencing.Resource(root, specification),
        ).lookup(self).contents
        
        return subschema
    def mimetype(self):
        return get_mimetypes().guess_type(str(self))[0]

class DynamicRef(Ref):
    dynamic_root = "https://deathbeds.github.io/nbref/schema/meta.yaml"

    # the dynamic resolver will always return a schema
    def resolve(self, root=None, specification=None):
        if root is None:
            root = DynamicRef.dynamic_root
        if isinstance(root, str):
            root = Ref.REGISTRY[root].contents
        return Ref.resolve(
            self,
            root=root,
            specification=specification
        )