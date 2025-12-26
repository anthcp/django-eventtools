#!/usr/bin/env python
# coding: utf-8

import os
from setuptools import setup, find_packages

# Choose README type dynamically
readme_path = 'README.rst' if os.path.exists('README.rst') else 'README.md'
content_type = (
    'text/x-rst' if readme_path.endswith('.rst') else 'text/markdown'
)

# Load version without importing package
exec(open('eventtools/_version.py').read())

setup(
    name='django-eventtools',
    version=__version__,
    description='Recurring event tools for Django',
    long_description=open(readme_path).read(),
    long_description_content_type=content_type,
    author='Anthony Percy',
    author_email='anthony.percy@systemscom.info',
    url='https://github.com/anthcp/django-eventtools',
    packages=find_packages(exclude=('tests',)),
    license='BSD License',
    zip_safe=False,

    # 🚀 Modern Python versions only
    python_requires='>=3.9',

    install_requires=[
        'Django>=3.2,<5.2',
        'python-dateutil>=2.8.2',
    ],

    include_package_data=True,
    package_data={},

    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',

        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',

        'Framework :: Django',
        'Framework :: Django :: 3.2',
        'Framework :: Django :: 4.0',
        'Framework :: Django :: 4.1',
        'Framework :: Django :: 4.2',
        'Framework :: Django :: 5.0',
        'Framework :: Django :: 5.1',

        'License :: OSI Approved :: BSD License',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
