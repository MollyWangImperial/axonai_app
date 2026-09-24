import json
import os

os.environ.setdefault('MONGO_URL', 'mongodb://127.0.0.1:27017')
os.environ.setdefault('DB_NAME', 'rehyn_local_video_test')
from fastapi.testclient import TestClient
from backend import deploy_server, local_assessment_recordings as recordings, server


def local_client(host='127.0.0.1', base_url='http://127.0.0.1'):
    async def app(scope, receive, send):
        await deploy_server.app({**scope, 'client': (host, 50000)}, receive, send)
    return TestClient(app, base_url=base_url)


def prepare_recording_test(monkeypatch, tmp_path):
    async def user(*args):
        return {'id': 'local_review_user'}
    monkeypatch.setattr(server, '_task_video_user', user)
    monkeypatch.setattr(recordings, 'RECORDINGS_DIR', tmp_path)


def test_video_is_unique_local_and_owner_scoped_with_evidence(monkeypatch, tmp_path):
    prepare_recording_test(monkeypatch, tmp_path)
    client = local_client()
    payload = b'\x1a\x45\xdf\xa3' + b'local video fixture'
    a = client.post('/api/local-assessment-recordings?task_id=T1&duration_ms=3000', content=payload, headers={'Content-Type':'video/webm'}).json()
    b = client.post('/api/local-assessment-recordings?task_id=T1', content=payload, headers={'Content-Type':'video/webm'}).json()
    assert a['id'] != b['id']
    assert a['status'] == 'video_saved'
    assert (tmp_path / a['filename']).read_bytes() == payload
    assert client.get(f"/api/local-assessment-recordings/{a['id']}/video").content == payload
    video_url=f"/api/local-assessment-recordings/{a['id']}/video"
    middle=client.get(video_url,headers={'Range':'bytes=4-8'})
    assert middle.status_code == 206 and middle.content == payload[4:9]
    assert middle.headers['content-range'] == f'bytes 4-8/{len(payload)}'
    assert client.get(video_url,headers={'Range':'bytes=-5'}).content == payload[-5:]
    assert client.get(video_url,headers={'Range':'bytes=9999-'}).status_code == 416
    assert client.head(video_url).headers['content-length'] == str(len(payload))
    evidence={'task_result':{'task_id':'T1','completed_steps':0,'total_steps':4,'steps':[]},'timeline':[]}
    saved=client.post(f"/api/local-assessment-recordings/{a['id']}/evidence",json=evidence)
    assert saved.status_code == 200 and saved.json()['status'] == 'saved'
    data=json.loads((tmp_path / f"{a['id']}.json").read_text())
    assert data['score_report']['task']['score'] is None
    assert data['evidence'] == evidence
    async def other(*args):return {'id':'other_user'}
    monkeypatch.setattr(server, '_task_video_user', other)
    assert client.get(f"/api/local-assessment-recordings/{a['id']}/video").status_code == 404


def test_recording_rejects_remote_invalid_and_oversized_uploads(monkeypatch,tmp_path):
    prepare_recording_test(monkeypatch,tmp_path)
    client=local_client()
    remote=local_client('198.51.100.1','https://example.org')
    assert remote.post('/api/local-assessment-recordings?task_id=T1').status_code == 404
    assert client.post('/api/local-assessment-recordings?task_id=../../x',content=b'x',headers={'Content-Type':'video/webm'}).status_code == 422
    assert client.post('/api/local-assessment-recordings?task_id=T1',content=b'x',headers={'Content-Type':'video/webm'}).status_code == 415
    monkeypatch.setattr(recordings,'MAX_VIDEO_BYTES',8)
    assert client.post('/api/local-assessment-recordings?task_id=T1',content=b'\x1a\x45\xdf\xa3abcdef',headers={'Content-Type':'video/webm'}).status_code == 413
    assert not list(tmp_path.glob('*.part'))
    async def nobody(*args):return None
    monkeypatch.setattr(server, '_task_video_user', nobody)
    assert client.post('/api/local-assessment-recordings?task_id=T1').status_code == 401
