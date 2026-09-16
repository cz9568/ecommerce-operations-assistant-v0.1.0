import argparse
import getpass

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models.entities import User
from backend.app.security import hash_password, validate_password_strength


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first application administrator")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--display-name", default="系统管理员")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    password = getpass.getpass("管理员密码（至少 12 位）: ")
    confirmation = getpass.getpass("再次输入密码: ")
    if password != confirmation:
        raise SystemExit("两次密码不一致。")
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    with SessionLocal.begin() as session:
        existing = session.scalar(select(User).where(User.username == args.username))
        if existing:
            raise SystemExit(f"用户 {args.username!r} 已存在。")
        session.add(
            User(
                username=args.username,
                display_name=args.display_name,
                password_hash=hash_password(password),
                role="admin",
                status="active",
            )
        )
    print(f"管理员 {args.username!r} 创建成功。")


if __name__ == "__main__":
    main()
