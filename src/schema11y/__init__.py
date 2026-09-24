"""schema first tools for generating archival HTML"""
__version__ = "2026.9.11"

from pathlib import Path
HERE = Path(__file__).parent

from .types import *
from .html import *
from .html_content import *
from .mimetypes import *
from .ipython import *
from . import schema


del Path