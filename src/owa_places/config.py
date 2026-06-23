"""Non-secret configuration for owa-places."""

from owa_core.config import load_config_file

CONFIG_FILE = 'owa-places.json'


def load_config():
    return load_config_file(CONFIG_FILE)
