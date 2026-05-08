import stat

from owa_core import config


def test_save_config_enforces_private_file_and_directory_modes(tmp_path):
    target = tmp_path / 'owa-test' / 'config'
    target.parent.mkdir(parents=True, mode=0o755)

    config.save_config(target, {'owa_piggy_profile': 'work'})

    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
