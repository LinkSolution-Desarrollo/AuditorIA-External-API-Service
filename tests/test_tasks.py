from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import Task, GlobalApiKey
import uuid
import pytest

def test_list_tasks_empty(client: TestClient, db_session: Session):
    response = client.get("/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0

def test_list_tasks_with_data(client: TestClient, db_session: Session):
    # Get the mock API key created in conftest
    api_key = db_session.query(GlobalApiKey).first()
    
    # Create a task linked to this API key
    task_uuid = str(uuid.uuid4())
    task_params = {"api_key_id": api_key.id, "some_param": "test"}
    
    task = Task(
        uuid=task_uuid,
        status="completed",
        task_type="transcription",
        file_name="test_audio.mp3",
        language="es",
        audio_duration=120.5,
        task_params=task_params
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.get("/tasks/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["identifier"] == task_uuid
    assert data[0]["status"] == "completed"

def test_get_task_detail(client: TestClient, db_session: Session):
    api_key = db_session.query(GlobalApiKey).first()
    task_uuid = str(uuid.uuid4())
    task_params = {"api_key_id": api_key.id}
    
    task = Task(
        uuid=task_uuid,
        status="processing",
        task_type="transcription",
        file_name="detail_test.mp3",
        url="s3_path/detail_test.mp3",
        task_params=task_params
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.get(f"/tasks/{task_uuid}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert data["metadata"]["file_name"] == "detail_test.mp3"
    assert data["metadata"]["url"] == "s3_path/detail_test.mp3"

def test_get_task_not_found(client: TestClient):
    response = client.get("/tasks/non-existent-uuid")
    assert response.status_code == 404

def test_delete_task(client: TestClient, db_session: Session):
    api_key = db_session.query(GlobalApiKey).first()
    task_uuid = str(uuid.uuid4())
    task_params = {"api_key_id": api_key.id}
    
    task = Task(
        uuid=task_uuid,
        status="pending",
        task_params=task_params
    )
    db_session.add(task)
    db_session.commit()
    
    # Delete
    response = client.delete(f"/tasks/{task_uuid}")
    assert response.status_code == 204
    
    # Verify deletion
    deleted_task = db_session.query(Task).filter(Task.uuid == task_uuid).first()
    assert deleted_task is None

def test_get_task_audio(client: TestClient, db_session: Session, mock_s3):
    api_key = db_session.query(GlobalApiKey).first()
    task_uuid = str(uuid.uuid4())
    task_params = {"api_key_id": api_key.id}
    
    task = Task(
        uuid=task_uuid,
        status="completed",
        file_name="audio.mp3",
        url="users/audio.mp3",
        task_params=task_params
    )
    db_session.add(task)
    db_session.commit()
    
    response = client.get(f"/tasks/{task_uuid}/audio")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert "attachment; filename=audio.mp3" in response.headers["content-disposition"]
