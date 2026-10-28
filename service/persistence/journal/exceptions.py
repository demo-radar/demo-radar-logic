"""Structured admission failures shared by journal components and API callers."""


class AdmissionError(Exception):
    """Safe, structured rejection that contains no title, token or server body."""

    def __init__(self, code, status=409, retry_after=None):
        self.code, self.status, self.retry_after = code, status, retry_after
