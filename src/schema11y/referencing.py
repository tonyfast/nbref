from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Resource:
    contents: dict
    _specification: object
    id: str
@lru_cache(1)
def get_request_session():
    # handle local and remote requests in the same session
    # caching could go here too
    # fortunately schema are very cacheable
    import requests, requests_file, requests_cache
    session = requests.Session()
    session.mount("file://", requests_file.FileAdapter())
    return session

# there is a better way to cache this
def retrieve(uri, key="@vocab", _cache={}):
    from .types import Pointer
    import referencing, yaml, requests_cache
    from pathlib import Path
    if isinstance(uri, Path):
        uri = str(uri.absolute().as_uri())
    if uri in _cache:
        return _cache[uri]
    response = get_request_session().get(uri)
    contents = yaml.safe_load(response.text)
    if key:
        contents[key] = uri
    reference = referencing.Resource(contents, referencing.jsonschema.DRAFT202012)
    if "://" in uri:
        _cache[uri] = reference
    return reference

def default_registry():
    import jsonschema_specifications, referencing
    return referencing.Registry(
        jsonschema_specifications.REGISTRY._resources,
        jsonschema_specifications.REGISTRY._anchors,
        jsonschema_specifications.REGISTRY._uncrawled,
        retrieve
    )