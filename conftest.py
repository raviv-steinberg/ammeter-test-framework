"""
Root pytest configuration: switches on the plugins the whole project uses.

pytester runs pytest inside a test, it is used to test the report plugin itself.
"""

pytest_plugins = ['pytester', 'src.reporting.pytest_report']
