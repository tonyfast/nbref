import mimetypes
from pathlib import Path
HERE = Path(__file__).parent
MIMETYPES_FILE = HERE / "mime.types"
mimes = mimetypes.MimeTypes()
mimes.read(str(MIMETYPES_FILE))

def guess(filename):
    if filename.startswith("."):
        return mimes.guess_type("dummy" + filename)[0]
    return mimes.guess_type(filename)[0]