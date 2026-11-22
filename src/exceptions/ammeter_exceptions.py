"""
Custom exceptions raised when communicating with the ammeter emulators.
"""


class AmmeterError(Exception):
    """
    Base class for all ammeter related errors.
    """


class AmmeterConnectionError(AmmeterError):
    """
    Raised when the client cannot connect to the ammeter or the ammeter does not answer in time.
    """


class AmmeterResponseError(AmmeterError):
    """
    Raised when the ammeter closes the connection without sending any data.
    """


class AmmeterInvalidReplyError(AmmeterError):
    """
    Raised when the ammeter sends data that cannot be converted to a number.
    """