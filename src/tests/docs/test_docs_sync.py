from scripts.check_docs_sync import check_docs_sync


def test_docs_sync_check_passes():
    assert check_docs_sync() == []
