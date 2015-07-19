from setuptools import setup
from sys import argv


def is_register_command(a):
    for item in a:
        if item.startswith('-'):
            continue
        return item == 'register'
    return False

longdesc = None
if is_register_command(argv[1:]):
    import os
    with os.popen('pandoc -f markdown_github -t rst README.md') as f:
        longdesc = f.read()


setup(
    name='sourcemap-tool',
    version='0.1',
    description='Swiss knife for sourcemaps',
    long_description=longdesc,
    url='https://github.com/neumond/sourcemap-tool',
    author='Vitalik Verhovodov',
    author_email='knifeslaughter@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Build Tools',
    ],
    keywords='sourcemap concat combine merge',
    py_modules=['sourcemap_lib'],
    scripts=['sourcemap_tool.py'],
    extras_require={
        'lexer': ['Pygments'],
    }
)
