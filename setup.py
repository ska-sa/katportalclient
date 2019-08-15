#!/usr/bin/env python
# Copyright 2015 SKA South Africa (http://ska.ac.za/)
# BSD license - see COPYING for details

from setuptools import setup, find_packages

setup(
    name="katportalclient",
    description="A client for katportal.",
    author="MeerKAT CAM Team",
    author_email="cam@ska.ac.za",
    packages=find_packages(),
    include_package_data=True,
    scripts=[],
    url="http://ska.ac.za/",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Astronomy",
    ],
    platforms=["OS Independent"],
    keywords="meerkat kat ska",
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, <4",
    setup_requires=["katversion"],
    use_katversion=True,
    install_requires=[
        "future",
        "futures; python_version<'3'",
        "tornado>=4.0, <7.0; python_version>='3'",
        "tornado>=4.0, <5.0; python_version<'3'",
        "omnijson>=0.1.2",
        "ujson>=1.33, <2.0",
    ],
    # install extras by running pip install .[doc,<another_extra>]
    extras_require={
        "doc": [
            "sphinx>=1.2.3, <2.0",
            "docutils>=0.12, <1.0",
            "sphinx_rtd_theme>=0.1.5, <1.0",
            "numpydoc>=0.5, <1.0",
        ]
    },
    zip_safe=False,
    test_suite="nose.collector",
)
