"""Tests for owa_mail.attachments pure helpers."""

import base64

import pytest

from owa_mail import attachments as att


def test_normalize_attachment_flattens_and_omits_bytes():
    raw = {
        "@odata.type": "#Microsoft.OutlookServices.FileAttachment",
        "Id": "a1",
        "Name": "report.pdf",
        "ContentType": "application/pdf",
        "Size": 2048,
        "IsInline": False,
        "ContentBytes": base64.b64encode(b"secret-blob").decode(),
    }
    flat = att.normalize_attachment(raw)
    assert flat == {
        "id": "a1",
        "name": "report.pdf",
        "content_type": "application/pdf",
        "size": 2048,
        "kind": "fileAttachment",
        "is_inline": False,
    }
    # Never surface the base64 blob in a listing.
    assert "ContentBytes" not in flat
    assert "content_bytes" not in flat


def test_normalize_attachments_and_kinds():
    raw = {
        "value": [
            {"@odata.type": "#microsoft.graph.itemAttachment", "Name": "msg"},
            {"@odata.type": "#Microsoft.OutlookServices.ReferenceAttachment", "Name": "link"},
        ]
    }
    flat = att.normalize_attachments(raw)
    assert [a["kind"] for a in flat] == ["itemAttachment", "referenceAttachment"]
    assert att.normalize_attachments("nope") == []
    assert att.normalize_attachment(42) == {}


def test_decode_content_bytes():
    raw = {"ContentBytes": base64.b64encode(b"hello").decode()}
    assert att.decode_content_bytes(raw) == b"hello"
    # camelCase variant.
    raw2 = {"contentBytes": base64.b64encode(b"hi").decode()}
    assert att.decode_content_bytes(raw2) == b"hi"
    # No bytes (item/reference attachment).
    assert att.decode_content_bytes({"Name": "x"}) is None
    assert att.decode_content_bytes(None) is None


def test_read_file_attachment(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_bytes(b"contents")
    name, content = att.read_file_attachment(str(f))
    assert name == "doc.txt"
    assert content == b"contents"
    with pytest.raises(ValueError, match="attachment not found"):
        att.read_file_attachment(str(tmp_path / "missing.txt"))


def test_read_file_attachment_unreadable(monkeypatch, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_bytes(b"x")

    def boom(*a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr("builtins.open", boom)
    with pytest.raises(ValueError, match="cannot read attachment"):
        att.read_file_attachment(str(f))


def test_build_inline_attachment_round_trips():
    obj = att.build_inline_attachment("a.bin", b"\x00\x01\x02", content_type="application/octet-stream")
    assert obj["@odata.type"] == att.FILE_ATTACHMENT_TYPE
    assert obj["Name"] == "a.bin"
    assert obj["ContentType"] == "application/octet-stream"
    assert base64.b64decode(obj["ContentBytes"]) == b"\x00\x01\x02"
    # Without content type the key is omitted.
    assert "ContentType" not in att.build_inline_attachment("b", b"x")


def test_build_upload_session_body():
    assert att.build_upload_session_body("big.zip", 99) == {
        "AttachmentItem": {"attachmentType": "file", "name": "big.zip", "size": 99}
    }


def test_partition_by_size():
    small = ("a", b"x" * 10)
    big = ("b", b"x" * (att.INLINE_LIMIT_BYTES + 1))
    s, l = att.partition_by_size([small, big])
    assert s == [small]
    assert l == [big]
    # Exactly at the limit stays inline.
    edge = ("c", b"x" * att.INLINE_LIMIT_BYTES)
    s2, l2 = att.partition_by_size([edge])
    assert s2 == [edge] and l2 == []


def test_path_helpers():
    assert att.attachment_path("m 1") == "me/messages/m%201/attachments"
    assert att.attachment_path("m1", "a1") == "me/messages/m1/attachments/a1"
    assert att.value_path("m1", "a1") == "me/messages/m1/attachments/a1/$value"
    assert att.createuploadsession_path("m1") == "me/messages/m1/attachments/createUploadSession"
