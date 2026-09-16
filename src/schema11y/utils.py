import typing

def infer_schema(*object):
    from genson import SchemaBuilder
    builder = SchemaBuilder()
    for object in object:
        builder.add_object(object)
    schema = builder.to_schema()
    schema.pop("$schema", None)
    return schema

def parse_yaml(string):
    import yaml
    return yaml.safe_load(string)

def el_from_tag(tag, *children, **attrs):
    import bs4
    if isinstance(tag, str):
        tag = bs4.Tag(name=tag)
    for child in children:
        if isinstance(child, typing.Generator):
            child = list(child)
        if isinstance(child, list):
            for subchild in child:
                tag.append(subchild)
        else:
            tag.append(child)
    style = attrs.get("style")
    if style:
        styles = ""
        for key, value in style.items():
            styles += f"{key}: {value}; "
        attrs["style"] = styles
        

    tag.attrs.update(attrs)
    return tag

def el_from_selector(selection, *children, first=True, **attrs):
    import cssselect, bs4
    if isinstance(selection, bs4.Tag):
        return el_from_tag(selection, *children, **attrs)
    if isinstance(selection, str):
        selection = cssselect.parse(selection)

    if isinstance(selection, list):
        elements = []
        for element in selection:
            element = el_from_selector(element, *children, **attrs)
            if first:
                return element
            elements.append(element)
        return elements
        

    elif isinstance(selection, cssselect.Selector):
        return el_from_selector(selection.parsed_tree, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Element):
        return el_from_tag(selection.element, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Hash):
        attrs.update(id=selection.id)
        return el_from_selector(selection.selector, *children, **attrs)
    elif isinstance(selection, cssselect.parser.Class):
        attrs.setdefault("class", []).append(selection.class_name)
        return el_from_selector(selection.selector, *children, **attrs)
    elif isinstance(selection, cssselect.parser.CombinedSelector):
        return el_from_selector(selection.selector, el_from_selector(selection.subselector), *children, **attrs)
    raise ValueError(f"Unsupported selection type: {selection}")
element = el_from_selector