


from dataclasses import dataclass, field

from nbref.schemas import Schema
from nbref.objects import Null
from nbref import html, schema

from .utils import el, parse_html

@dataclass
class Options:
    readonly: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)
    is_valid: list = field(default_factory=list)

def aria_role(schema, options=None, object=None):
    role = schema.get("role")
    if role:
        return role
    enum = schema.get("enum")
    if enum:
        return "select"
        return "radiogroup"
    format = schema.get("format")
    if format:
        return "input"
    content = schema.get("contentMediaType")
    if content:
        return "code"
    # if object is None:
    #     t = schema.type()
    # else:
    #     t = object.type()
    if "type" in schema:
        t = Schema.type(schema)
        # this damn mistake again cost me a lot of time. its best to assume you don't have a schema object, 
        # but the object may structured accordingly.
        match t:
            case "array":
                return "list"
            case "object":
                return "associationlist"
            case "string":
                return "textbox"
            case "number" | "integer":
                return "spinbutton"
            case "boolean":
                return "checkbox"
    if "default" in schema:
        return aria_role(Schema.infer(schema["default"]), options)
    
        
Schema.role = aria_role