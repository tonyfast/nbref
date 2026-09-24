
from pathlib import Path
from ...types import Schema

HERE = Path(__file__).parent

specification = "http://json-schema.org/draft/2020-12/schema" 
schema = Schema.from_id( HERE / "core.yaml")