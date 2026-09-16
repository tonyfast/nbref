from functools import lru_cache

@lru_cache(1)
def get_request_session():
    import requests, requests_file
    session = requests.Session()
    session.mount("file://", requests_file.FileAdapter())
    return session

def retrieve(uri, key="@vocab"):
    from .types import Pointer
    import referencing, yaml
    from pathlib import Path
    if isinstance(uri, Path):
        uri = str(uri.absolute().as_uri())
    response = get_request_session().get(uri)
    contents = yaml.safe_load(response.text)
    if key:
        contents[key] = uri
    return referencing.Resource(contents, referencing.jsonschema.DRAFT202012)

def default_registry():
    import jsonschema_specifications, referencing
    return referencing.Registry(
        jsonschema_specifications.REGISTRY._resources,
        jsonschema_specifications.REGISTRY._anchors,
        jsonschema_specifications.REGISTRY._uncrawled,
        retrieve
    )