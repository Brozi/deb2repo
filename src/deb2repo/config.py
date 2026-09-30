from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str | None = None
    gpg_key_id: str
    repo_origin: str = "My Custom Repo"
    base_repo_path: str = "/app/repo"

    #fmt: off

    my_model_config  = SettingsConfigDict(  # pyright: ignore[reportUnannotatedClassAttribute]
        env_file=".env", env_file_encoding="utf-8"
    )
    #fmt: on


settings = Settings()  # pyright: ignore[reportCallIssue]
