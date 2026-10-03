"""Where Firefox is, for the checks that open the report in a browser."""
import os
import shutil


def firefox():
    """
    The path of Firefox, or None. On PATH if it is there (Linux); on Windows
    the installer does not put it there, so its usual folders are looked in
    too.
    """
    found = shutil.which("firefox")
    if found or os.name != "nt":
        return found
    for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(var)
        if root:
            path = os.path.join(root, "Mozilla Firefox", "firefox.exe")
            if os.path.isfile(path):
                return path
    return None
