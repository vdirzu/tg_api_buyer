import importlib.util
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import Settings


def test_locales_load_under_windows_cp1251_default(monkeypatch):
    real_read = Path.read_text

    def windows_read(path, *args, **kwargs):
        # Reproduce CP1251 as the default while respecting explicit UTF-8.
        kwargs.setdefault("encoding", "cp1251")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", windows_read)
    source = Path(__file__).parents[1] / "app" / "locales" / "__init__.py"
    spec = importlib.util.spec_from_file_location("isolated_locales", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.tr("ru", "welcome").startswith("Добро пожаловать")
    assert module.tr("en", "welcome").startswith("Welcome")


def test_utf8_dotenv_with_non_ascii_path(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("CSV_PATH=data/ключи.csv\n", encoding="utf-8")
    settings = Settings(
        _env_file=dotenv,
        key_hmac_secret="synthetic-encoding-test-secret-32-characters",
        payment_encryption_key=Fernet.generate_key().decode(),
    )
    assert settings.csv_path == Path("data/ключи.csv")
