from setuptools import setup, find_packages
from katversion import get_version

setup(
    name="katportalclient",
    version=get_version(),
    description="A client for websocket connections to katportal.",
    author="MeerKAT CAM Team",
    author_email="cam@ska.ac.za",
    packages=find_packages(),
    include_package_data=True,
    scripts=[],
    url='http://ska.ac.za/',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Astronomy"
    ],
    platforms=["OS Independent"],
    keywords="meerkat kat ska",
    install_requires=[
        "tornado>=4.0, <5.0",
        "omnijson>=0.1.2",
        "ujson>=1.33, <2.0",
        # "numpydoc>=0.5, <1.0",
        # "sphinx>=1.2.3, <2.0",
        # "docutils>=0.12, <1.0",
        # "sphinx_rtd_theme>=0.1.5, <1.0",
    ],
    tests_require=[
        "unittest2>=0.5.1",
        "nose>=1.3, <2.0",
        "mock>=1.0, <2.0",
    ],
    zip_safe=False,
    # Bitten Test Suite
    test_suite="nose.collector",
)
