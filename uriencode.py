#! /usr/bin/env pixi run python
import sys
from pathlib import Path
print(Path(sys.argv[1]).absolute().as_uri())