import pytest

from app.core.config import jdbc_mysql_url_to_sqlalchemy


def test_jdbc_mysql_url_to_sqlalchemy_keeps_core_connection_parts() -> None:
    url = jdbc_mysql_url_to_sqlalchemy(
        "jdbc:mysql://mysql.example.com:3307/ai_code_review"
        "?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai"
        "&allowPublicKeyRetrieval=true&useSSL=false",
        "ai_user",
        "p@ss word",
    )

    assert url.startswith("mysql+pymysql://ai_user:p%40ss+word@mysql.example.com:3307/ai_code_review?")
    assert "charset=utf8mb4" in url
    assert "serverTimezone" not in url
    assert "useSSL" not in url


def test_jdbc_mysql_url_to_sqlalchemy_adds_default_charset() -> None:
    url = jdbc_mysql_url_to_sqlalchemy(
        "jdbc:mysql://localhost/ai_code_review",
        "root",
        "root",
    )

    assert url == "mysql+pymysql://root:root@localhost/ai_code_review?charset=utf8mb4"


def test_jdbc_mysql_url_to_sqlalchemy_rejects_non_jdbc_mysql() -> None:
    with pytest.raises(ValueError):
        jdbc_mysql_url_to_sqlalchemy("postgresql://localhost/demo", "root", "root")
