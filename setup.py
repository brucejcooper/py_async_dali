import setuptools
from pathlib import Path


this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()


setuptools.setup(
    name="async_dali",
    version="0.1.3",
    author="Bruce Cooper",
    description="A module to discover devices and send commands to DALI enabled lights",
    long_description=long_description,
    long_description_content_type='text/markdown',
    url="https://github.com/brucejcooper/py_async_dali",
    packages=["async_dali"],
    license="MIT",
    install_requires=["hid", "dom_query", "dateparser"]
)
