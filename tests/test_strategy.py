"""Module for the testing the internals of the strategy module."""
"""
class Sync:
    local = None
    remote = None

class Remote:
    exists = False

    def create(): pass
    def delete(): pass

class Local:
    exists = False

    def create(): pass
    def delete(): pass

"""


def test_full_sync_plan():
    # TODO: make input which has sync-couples for:
    # {create,move,update,delete} {local,remote} + move resolve
    pass
