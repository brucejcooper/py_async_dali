from .tridonic import TridonicDali


def scan_for_dali_transcievers():
    drivers = TridonicDali.scan_for_transcievers()
    return drivers
