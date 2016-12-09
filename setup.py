# -*- coding: utf-8 -*-

from setuptools import setup

setup(
    name='clg-table',
    version='0.1.0',
    author='François Ménabé',
    author_email='francois.menabe@gmail.com',
    url = 'https://clg.readthedocs.org/en/latest/',
    download_url = 'http://github.com/fmenabe/python-clg-table',
    license='MIT License',
    description='Manage terminal tables.',
    long_description=open('README.rst').read(),
    keywords=['command-line', 'argparse', 'wrapper', 'clg'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Topic :: Utilities'
    ],
    py_modules=['clg/table'])
