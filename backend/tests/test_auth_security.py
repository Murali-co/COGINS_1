import pyotp
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

    # 4. Verify that all sessions for that user were revoked (new_refresh_token should now be invalid/revoked as well)
    second_replay_res = client.post("/auth/refresh", cookies={"refresh_token": new_refresh_token})
    assert second_replay_res.status_code == 401


def test_missing_csrf_cookie_rejected(client):
    # State-changing POST with NO csrf_token cookie and NO X-CSRF-Token header -> 403 Forbidden
    res = client.post("/auth/logout")
    assert res.status_code == 403
    assert "CSRF token validation failed" in res.json()["detail"]


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

    # Create a dummy second refresh token session for this user
    second_session_id = DBManager.create_refresh_token(
        user_id=user["id"],
        token_hash="dummy_hash_for_second_device_12345",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
        ip_address="192.168.1.50"
    )

    # List sessions
    sessions_res = client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 2

    # Attempting to revoke current session must return 400 Bad Request
    current_session = next(s for s in sessions if s["is_current"])
    del_current_res = client.delete(
        f"/auth/sessions/{current_session['id']}",
        cookies={"csrf_token": csrf_token},
        headers=headers
    )
    assert del_current_res.status_code == 400

    # Revoking second session must succeed (200 OK)
    del_res = client.delete(
        f"/auth/sessions/{second_session_id}",
        cookies={"csrf_token": csrf_token},
        headers=headers
    )
    assert del_res.status_code == 200

    # List sessions again to verify count decreased by 1
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


def test_account_lockout_after_failed_logins(client):
    email = "lockout@test.com"
    client.post("/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Lockout User"
    })
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])

    # Perform 8 failed login attempts
    for _ in range(8):
        res = client.post("/auth/login", json={"email": email, "password": "WrongPassword!"})
        assert res.status_code == 401

    # 9th attempt must be blocked by 429 Account Locked
    locked_res = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    assert locked_res.status_code == 429
    assert "Account temporarily locked" in locked_res.json()["detail"]


def test_sessions_is_current_and_revoke_guard(client):
    email = "sessions_guard@test.com"
    client.post("/auth/register", json={
        "email": email,
        "password": "Password123!",
        "full_name": "Sessions User"
    })
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])

    login_res = client.post("/auth/login", json={"email": email, "password": "Password123!"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    csrf_token = login_res.cookies.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf_token}

    sessions_res = client.get("/auth/sessions", headers=headers)
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) == 1
    current_session = sessions[0]
    assert current_session["is_current"] is True

    # Attempting to DELETE current session must return 400 Bad Request
    del_res = client.delete(f"/auth/sessions/{current_session['id']}", headers=headers)
    assert del_res.status_code == 400
    assert "Cannot revoke your current session" in del_res.json()["detail"]

    # Call revoke-others (should revoke 0 since there are no other sessions)
    revoke_others_res = client.post("/auth/sessions/revoke-others", headers=headers)
    assert revoke_others_res.status_code == 200
    assert revoke_others_res.json()["revoked_count"] == 0


def test_single_use_password_reset_token(client):
    email = "reset_single_use@test.com"
    client.post("/auth/register", json={
        "email": email,
        "password": "OldPassword123!",
        "full_name": "Reset User"
    })
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])

    # Request password reset
    forgot_res = client.post("/auth/forgot-password", json={"email": email})
    assert forgot_res.status_code == 200

    # Fetch token stored in DB
    updated_user = DBManager.get_user_by_id(user["id"])
    reset_token = updated_user["reset_password_token"]
    assert reset_token is not None

    # First reset attempt (must succeed)
    reset_res1 = client.post("/auth/reset-password", json={"token": reset_token, "password": "NewPassword123!"})
    assert reset_res1.status_code == 200
    assert reset_res1.json()["success"] is True

    # Second reset attempt with same token (must fail due to single-use enforcement)
    reset_res2 = client.post("/auth/reset-password", json={"token": reset_token, "password": "AnotherPassword123!"})
    assert reset_res2.status_code == 400
    assert "already been used or is invalid" in reset_res2.json()["detail"]


def test_admin_audit_log_endpoint(client):
    # Non-admin user
    non_admin_email = "regular_user@test.com"
    client.post("/auth/register", json={"email": non_admin_email, "password": "Password123!", "full_name": "Regular User"})
    reg_user = DBManager.get_user_by_email(non_admin_email)
    DBManager.verify_email(reg_user["id"])

    reg_login = client.post("/auth/login", json={"email": non_admin_email, "password": "Password123!"})
    reg_token = reg_login.json()["access_token"]

    # Non-admin request to admin endpoint must return 403 Forbidden
    forbidden_res = client.get("/auth/admin/audit-log", headers={"Authorization": f"Bearer {reg_token}"})
    assert forbidden_res.status_code == 403

    # Admin user
    admin_email = "admin_audit@test.com"
    client.post("/auth/register", json={"email": admin_email, "password": "Password123!", "full_name": "Admin Audit User"})
    admin_user = DBManager.get_user_by_email(admin_email)
    DBManager.verify_email(admin_user["id"])
    DBManager.promote_user_to_admin(admin_email)

    admin_login = client.post("/auth/login", json={"email": admin_email, "password": "Password123!"})
    admin_token = admin_login.json()["access_token"]

    # Admin request to audit log endpoint must succeed (200 OK)
    audit_res = client.get("/auth/admin/audit-log?event_type=login_success&page=1&per_page=10", headers={"Authorization": f"Bearer {admin_token}"})
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert "logs" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["per_page"] == 10


def test_2fa_full_flow_and_backup_codes(client):
    email = "2fa_test_user@test.com"
    password = "Password123!"
    client.post("/auth/register", json={"email": email, "password": password, "full_name": "2FA User"})
    user = DBManager.get_user_by_email(email)
    DBManager.verify_email(user["id"])

    login_res1 = client.post("/auth/login", json={"email": email, "password": password})
    token1 = login_res1.json()["access_token"]
    csrf_token1 = login_res1.cookies.get("csrf_token")
    headers1 = {"Authorization": f"Bearer {token1}", "X-CSRF-Token": csrf_token1}

    # 1. Setup 2FA
    setup_res = client.post("/auth/2fa/setup", headers=headers1)
    assert setup_res.status_code == 200
    secret = setup_res.json()["secret"]
    otpauth_url = setup_res.json()["otpauth_url"]
    assert secret is not None
    assert "otpauth://" in otpauth_url

    # 2. Confirm 2FA with valid TOTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()
    confirm_res = client.post("/auth/2fa/confirm", json={"secret": secret, "code": valid_code}, headers=headers1)
    assert confirm_res.status_code == 200
    backup_codes = confirm_res.json()["backup_codes"]
    assert len(backup_codes) == 10

    # 3. Login now requires 2FA
    login_2fa_challenge = client.post("/auth/login", json={"email": email, "password": password})
    assert login_2fa_challenge.status_code == 200
    challenge_data = login_2fa_challenge.json()
    assert challenge_data["requires_2fa"] is True
    pending_token = challenge_data["pending_token"]
    assert pending_token is not None

    # Using pending_token on protected endpoint must fail with 401
    protected_res = client.get("/auth/me", headers={"Authorization": f"Bearer {pending_token}"})
    assert protected_res.status_code == 401
    assert "Full authentication required" in protected_res.json()["detail"]

    # 4. Verify 2FA with backup code
    used_backup_code = backup_codes[0]
    verify_res1 = client.post("/auth/2fa/verify", json={"pending_token": pending_token, "code": used_backup_code})
    assert verify_res1.status_code == 200
    assert "access_token" in verify_res1.json()

    # Attempting to re-use the consumed backup code must fail
    login_2fa_challenge2 = client.post("/auth/login", json={"email": email, "password": password})
    pending_token2 = login_2fa_challenge2.json()["pending_token"]
    verify_res_reuse = client.post("/auth/2fa/verify", json={"pending_token": pending_token2, "code": used_backup_code})
    assert verify_res_reuse.status_code == 400

    # 5. Verify 2FA with current TOTP code
    verify_res2 = client.post("/auth/2fa/verify", json={"pending_token": pending_token2, "code": totp.now()})
    assert verify_res2.status_code == 200
    final_token = verify_res2.json()["access_token"]
    final_csrf = verify_res2.cookies.get("csrf_token")
    final_headers = {"Authorization": f"Bearer {final_token}", "X-CSRF-Token": final_csrf}

    # 6. Disable 2FA with password
    disable_res = client.post("/auth/2fa/disable", json={"password": password}, headers=final_headers)
    assert disable_res.status_code == 200

    # Login after disabling 2FA should issue token directly
    login_after_disable = client.post("/auth/login", json={"email": email, "password": password})
    assert login_after_disable.status_code == 200
    assert login_after_disable.json().get("requires_2fa") in (False, None)
    assert login_after_disable.json()["access_token"] != ""
