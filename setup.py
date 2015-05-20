from setuptools import setup


setup(
    name='sourcemap-tool',
    version='0.1',
    description='Swiss knife for sourcemaps',
    url='https://github.com/neumond/sourcemap-tool',
    author='Vitaly Verhovodov',
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
    extras_require = {
        'lexer': ['Pygments'],
    }
)
