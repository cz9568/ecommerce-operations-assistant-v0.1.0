from sqlalchemy import inspect, text

from backend.app.config import get_settings
from backend.app.database import engine


def main() -> None:
    settings = get_settings()
    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT DATABASE()"))
        database_version = connection.scalar(text("SELECT VERSION()"))
    table_names = inspect(engine).get_table_names()

    print(f"application={settings.app_name}")
    print(f"environment={settings.app_env}")
    print(f"database={database_name}")
    print(f"mysql_version={database_version}")
    print(f"table_count={len(table_names)}")
    print(f"llm_model={settings.llm_model}")
    print(f"image_model={settings.image_model}")
    print(f"generation_provider={settings.generation_provider}")
    print("secrets=hidden")


if __name__ == "__main__":
    main()
