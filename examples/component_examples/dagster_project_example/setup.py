from setuptools import find_packages, setup

setup(
    name="dagster_lambda_example",
    packages=find_packages(exclude=["tests"]),
    install_requires=[
        "dagster>=1.5.0",
        "dagster-cloud>=1.5.0",
        "pydantic>=2.0.0",
    ],
    extras_require={"dev": ["dagster-webserver", "pytest"]},
)
