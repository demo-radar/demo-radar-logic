"""DemoLogic single-event inference API.

app and lifecycle assemble the service; api handles HTTP; inference coordinates
attempts; persistence owns SQLite; providers owns external and offline adapters.
Configuration, public schemas and safe error messages are shared at this level.
"""
