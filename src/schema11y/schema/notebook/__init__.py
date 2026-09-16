from ...types import Schema
from pathlib import Path
HERE = Path(__file__).parent

schema = Schema.from_id( HERE / "core.yaml").expand()