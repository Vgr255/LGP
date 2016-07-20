from distutils.core import setup, Extension

setup(
    name="LGP",
    version="0.1",
    url="https://github.com/Vgr255/LGP",
    author="Emanuel Barry",
    author_email="vgr255@live.ca",
    py_modules=["lgp"],
    ext_modules=[
        Extension("_lgp", ["src/_lgpmodule.c"], include_dirs=["include"]),
    ],
)
