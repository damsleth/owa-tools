"""Tests for distribution artifact inspection."""
import io
import tarfile
import zipfile

from scripts import check_artifacts


def test_inspect_zip_rejects_forbidden_paths(tmp_path):
    artifact = tmp_path / 'package.whl'
    with zipfile.ZipFile(artifact, 'w') as zf:
        zf.writestr('owa_core/__pycache__/x.pyc', b'bytecode')
        zf.writestr('owa_core/http.py', 'print("ok")\n')

    failures = check_artifacts.inspect_artifact(artifact)
    assert ('owa_core/__pycache__/x.pyc', 'forbidden path component') in failures


def test_inspect_tar_rejects_secret_shapes(tmp_path):
    artifact = tmp_path / 'package.tar.gz'
    token = '.'.join([
        'eyJhbGciOiJIUzI1NiIs',
        'eyJhdWQiOiJvd2EtdG9vbHMi',
        'c2lnbmF0dXJlZm9ydGVzdHM',
    ])
    data = f'token = "{token}"\n'.encode()

    with tarfile.open(artifact, 'w:gz') as tf:
        info = tarfile.TarInfo('package/owa_core/leak.py')
        info.size = len(data)
        tf.addfile(info, fileobj=io.BytesIO(data))

    failures = check_artifacts.inspect_artifact(artifact)
    assert ('package/owa_core/leak.py:1', 'secret-shaped access_token') in failures


def test_main_passes_clean_artifact(tmp_path, capsys):
    artifact = tmp_path / 'package.whl'
    with zipfile.ZipFile(artifact, 'w') as zf:
        zf.writestr('owa_core/http.py', 'print("ok")\n')

    assert check_artifacts.main([str(artifact)]) == 0
    assert 'artifact check: OK' in capsys.readouterr().out
