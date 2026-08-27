from backend.object_storage import R2Settings, TaskVideoObjectStorage


class FakeS3:
    def __init__(self):
        self.calls = []

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append((operation, Params, ExpiresIn))
        return f"https://storage.test/{operation}/{Params['Key']}"

    def head_object(self, **kwargs):
        return {"ContentLength": 1234, **kwargs}

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs, None))


def test_object_keys_do_not_expose_user_identifier():
    storage = TaskVideoObjectStorage(R2Settings("account", "key", "secret", "bucket", "https://r2.test"))
    key = storage.object_key("patient@example.com", "initial", "L6", "video-1", "mp4")

    assert "patient@example.com" not in key
    assert key.endswith("/initial/L6/video-1.mp4")


def test_presigned_put_and_get_are_short_lived_and_content_typed():
    storage = TaskVideoObjectStorage(R2Settings("account", "key", "secret", "bucket", "https://r2.test"))
    fake = FakeS3()
    storage._client = fake

    put_url = storage.presign_put("patients/hash/video.mp4", "video/mp4", 600)
    get_url = storage.presign_get("patients/hash/video.mp4", 300)

    assert put_url.startswith("https://storage.test/put_object/")
    assert get_url.startswith("https://storage.test/get_object/")
    assert fake.calls[0][1]["ContentType"] == "video/mp4"
    assert fake.calls[0][2] == 600
    assert fake.calls[1][2] == 300
