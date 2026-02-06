def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "running" in response.json()["message"]
