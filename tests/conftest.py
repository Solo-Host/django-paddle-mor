import pytest

from django_paddle_mor.settings import clear_django_paddle_mor_settings_cache


@pytest.fixture(autouse=True)
def clear_settings_cache():
    clear_django_paddle_mor_settings_cache()
    yield
    clear_django_paddle_mor_settings_cache()
