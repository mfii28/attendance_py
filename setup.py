from setuptools import find_packages, setup

setup(
    name="attendance-system",
    version="1.0.0",
    description="Desktop Attendance Management System",
    packages=find_packages(),
    install_requires=[
        "pandas>=2.0.0",
        "matplotlib>=3.7.0",
        "openpyxl>=3.1.0",
        "reportlab>=4.0.0",
        "python-dateutil>=2.8.0",
        "chardet>=5.0.0",
        "Pillow>=10.0.0",
        "numpy>=1.24.0",
    ],
    python_requires=">=3.8",
    entry_points={"console_scripts": ["attendance-system=main:main"]},
)
