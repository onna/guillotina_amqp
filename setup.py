from setuptools import find_packages
from setuptools import setup


try:
    README = open("README.rst").read()
except IOError:
    README = None

setup(
    name="guillotina_amqp",
    version="5.0.30",
    description="Integrate amqp into guillotina",
    long_description=README,
    install_requires=[
        "aioamqp",
        "lru-dict",
        "aioredis<2.0.0",
        "backoff",
        "typing_extensions",
    ],
    author="Nathan Van Gheem",
    author_email="vangheem@gmail.com",
    url="https://github.com/guillotinaweb/guillotina_amqp",
    packages=find_packages(exclude=["demo"]),
    include_package_data=True,
    package_data={"": ["*.txt", "*.rst"], "guillotina_amqp": ["py.typed"]},
    tests_require=["pytest"],
    extras_require={
        "test": [
            "pytest>=7,<9",
            "docker>=6,<8",
            "psycopg2-binary",
            "pytest-asyncio>=0.21,<1",
            "pytest-cov>=4",
            "coverage>=7",
            "pytest-docker-fixtures[rabbitmq]>=1.3.11",
            "prometheus-client>=0.8.0",
            "mypy-zope>=0.9",
            "zope.interface>=5,<7",
            "urllib3>=2",
        ]
    },
    license="BSD",
    classifiers=[
        "License :: OSI Approved :: BSD License",
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP",
        "Intended Audience :: Developers",
    ],
    entry_points={},
)
