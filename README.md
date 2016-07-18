## LGP v0.1 - A Python 3 library for FF7's LGP files

This is currently a work-in-progress, and is not finished.
This can extract any archive except for `magic.lgp`, which is being worked on.
You can drag-and-drop an archive file to extract it directly in the current
directory; `char.lgp` will become `char`, `battle.lgp` will be `battle`, etc.

Only the pure Python version currently works - the C version is buggy and can
randomly segfault or fail with cryptic errors. The plan is to have the Python
version as the frontend for interacting with it, with the C version consisting
of the main logic. Depending on how things turn out, the C version might either
lose functionality (which will get transfered over to the Python version), or
it might gain some more, which the Python version will either duplicate or
extend.
