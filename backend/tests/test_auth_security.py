from datetime import datetime, timezone, timedelta
from app.auth.models import DBManager
from app.auth.utils import create_access_token

def test_login_and_refresh_token_rotation(client):
    # 1. Register and verify and login
    reg_res = client.post("/auth/register", json={
        "email": "security1@test.com",
        "password": "Password123!",
        "full_name": "Security User 1"
    })
    user = DBManager.get_user_by_email("security1@test.com")
    DBManager.verify_email(user["id"])
    
    login_res = client.post("/auth/login", json={
        "email": "security1@test.com",
        "password": "Password123!"
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert "access_token" in data
    
    # Verify cookies set
    cookies = login_res.cookies
    assert "refresh_token" in cookies
    assert "csrf_token" in cookies
    initial_refresh_token = cookies["refresh_token"]

    # 2. Refresh token
    refresh_res = client.post("/auth/refresh", cookies={"refresh_token": initial_refresh_token})
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data
    
    new_refresh_token = refresh_res.cookies["refresh_token"]
    assert new_refresh_token != initial_refresh_token

    # 3. Test Replay Attack (using initial_refresh_token which was rotated/revoked)
    client.cookies.clear()
    replay_res = client.post("/auth/refresh", cookies={"refresh_token": initial_refresh_token})
    assert replay_res.status_code == 401
    assert "Refresh token reuse detected" in replay_res.json()["detail"]


def test_logout_revokes_token(client):
    client.post("/auth/register", json={
        "email": "security2@test.com",
        "password": "Password123!",
        "full_name": "Security User 2"
    })
    user = DBManager.get_user_by_email("security2@test.com")
    DBManager.verify_email(user["id"])

    login_res = client.post("/auth/login", json={
        "email": "security2@test.com",
        "password": "Password123!"
    })
    refresh_token = login_res.cookies["refresh_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    
    # Logout with CSRF header
    logout_res = client.post(
        "/auth/logout",
        cookies={"refresh_token": refresh_token, "csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token}
    )
    assert logout_res.status_code == 200
    
    # Attempt refresh using logged out token
    ref_res = client.post("/auth/refresh", cookies={"refresh_token": refresh_token})
    assert ref_res.status_code == 401


def test_session_management(client):
    reg_res = client.post("/auth/register", json={
        "email": "security3@test.com",
        "password": "Password123!",
        "full_name": "Security User 3"
    })
    user = DBManager.get_user_by_email("security3@test.com")
    DBManager.verify_email(user["id"])

    login_res = client.post("/auth/login", json={
        "email": "security3@test.com",
        "password": "Password123!"
    })
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf_token}

    # List sessions
    sessions_res = client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 1
    session_id = sessions[0]["id"]

    # Revoke session
    del_res = client.delete(
        f"/auth/sessions/{session_id}",
        cookies={"csrf_token": csrf_token},
        headers=headers
    )
    assert del_res.status_code == 200

    # List sessions again
    sessions_res2 = client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert sessions_res2.status_code == 200
    assert len(sessions_res2.json()) == len(sessions) - 1


def test_csrf_middleware(client):
    # Register & Login to get CSRF cookie
    reg_res = client.post("/auth/register", json={
        "email": "csrf@test.com",
        "password": "Password123!",
        "full_name": "CSRF User"
    })
    user = DBManager.get_user_by_email("csrf@test.com")
    DBManager.verify_email(user["id"])

    login_res = client.post("/auth/login", json={
        "email": "csrf@test.com",
        "password": "Password123!"
    })
    csrf_token = login_res.cookies.get("csrf_token")
    access_token = login_res.json()["access_token"]
    
    # State-changing request with CSRF cookie BUT missing header -> should fail with 403
    fail_res = client.post(
        "/auth/logout",
        cookies={"csrf_token": csrf_token},
        headers={"Authorization": f"Bearer {access_token}"}
    )
    assert fail_res.status_code == 403
    assert "CSRF token validation failed" in fail_res.json()["detail"]

    # State-changing request with CSRF cookie AND matching header -> should succeed
    success_res = client.post(
        "/auth/logout",
        cookies={"csrf_token": csrf_token},
        headers={"X-CSRF-Token": csrf_token, "Authorization": f"Bearer {access_token}"}
    )
    assert success_res.status_code == 200


def test_security_headers(client):
    res = client.get("/health")
    headers = res.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "content-security-policy" in headers
