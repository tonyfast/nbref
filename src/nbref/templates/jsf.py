"""create html representations of json schema and their datastructure"""

class Pointer(list):
    """a json pointer to the current location in the data structure"""
    def __str__(self):
        return "/" + "/".join(self)
    
class Object:
    pointer: Pointer
    parent: object = None
    schema: object = None

    @classmethod
    def dispatch(cls, object):
        if isinstance(object, dict):
            return Dict(object)
        elif isinstance(object, list):
            return List(object)
        elif isinstance(object, float | int):
            return Number(object)
        return object
    
    def set_schema(self, schema):
        self.schema = schema
        return self
    
class Dict(Object, dict):
    pass

class List(Object, list):
    pass

class Float(Object, float):
    pass

def schema_type(schema, data):
    if "enum" in schema:
        return "enum"
    
    if "type" in schema:
        t = schema["type"]
        if isinstance(t, list):
            return "anyOf"
        return t

    if "if" in schema:
        return "ifThenElse"

    if "oneOf" in schema:
        return "oneOf"
    if "anyOf" in schema:
        return "anyOf"

    
    if (
        "properties" in schema
        or "additionalProperties" in schema
        or "patternProperties" in schema
    ):
        return "object"
    if "items" in schema or "prefixItems" in schema:
        return "array"

    if isinstance(data, str):
        return "string"
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, float | int):
        return "number"
    if data is None:
        return "null"

    if isinstance(data, dict):
        return "object"
    if isinstance(data, list | tuple | set):
        return "array"
    raise "any"
