"""Entry point of the built program (PyInstaller): the package's own main."""
import sys

from oyplayer.__main__ import main

sys.exit(main(sys.argv))
