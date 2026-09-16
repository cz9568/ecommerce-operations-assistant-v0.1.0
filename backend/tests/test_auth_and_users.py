import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.entities import AuditLog, User
from backend.app.security import hash_password

ADMIN_PASSWORD = "Strong-Admin-Password-123"
VIEWER_PASSWORD = "Strong-Viewer-Password-123"


def create_test_user(
    session: Session,
    *,
    username: str,
    password: str,
    role: str,
    status: str = "active",
) -> User:
    user = User(
        username=username,
        display_name=username.title(),
        password_hash=hash_password(password),
        role=role,
        status=status,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_login_me_logout_and_revocation(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    me_response = await api_client.get("/api/v1/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"
    assert me_response.headers["X-Request-ID"]

    logout_response = await api_client.post("/api/v1/auth/logout", headers=headers)
    assert logout_response.status_code == 200

    revoked_response = await api_client.get("/api/v1/auth/me", headers=headers)
    assert revoked_response.status_code == 401
    assert revoked_response.json()["code"] == "AUTHENTICATION_REQUIRED"


async def test_invalid_credentials_have_stable_error(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"
    assert response.json()["request_id"]


async def test_missing_bearer_token_uses_standard_error(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_viewer_cannot_manage_users(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="viewer",
        password=VIEWER_PASSWORD,
        role="viewer",
    )
    token = await login(api_client, "viewer", VIEWER_PASSWORD)

    response = await api_client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


async def test_admin_can_create_list_and_update_users(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    admin = create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await api_client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "operator01",
            "display_name": "运营一号",
            "password": "Strong-Operator-Password-123",
            "role": "operator",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    operator_id = create_response.json()["id"]
    assert "password" not in create_response.json()

    list_response = await api_client.get("/api/v1/users?page=1&page_size=10", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 2

    update_response = await api_client.patch(
        f"/api/v1/users/{operator_id}",
        headers=headers,
        json={"role": "viewer", "display_name": "只读用户"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["role"] == "viewer"

    last_admin_response = await api_client.patch(
        f"/api/v1/users/{admin.id}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert last_admin_response.status_code == 409
    assert last_admin_response.json()["code"] == "LAST_ADMIN_REQUIRED"

    db_session.expire_all()
    audit_count = db_session.scalar(select(func.count(AuditLog.id)))
    assert (audit_count or 0) >= 3


async def test_user_password_policy_is_enforced(
    api_client: httpx.AsyncClient, db_session: Session
) -> None:
    create_test_user(
        db_session,
        username="admin",
        password=ADMIN_PASSWORD,
        role="admin",
    )
    token = await login(api_client, "admin", ADMIN_PASSWORD)

    response = await api_client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "username": "weak-user",
            "display_name": "弱密码",
            "password": "alllowercase",
            "role": "viewer",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
