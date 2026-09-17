
from pathlib import Path
from ...types import Schema

HERE = Path(__file__).parent

schema = Schema.from_id( HERE / "core.yaml")