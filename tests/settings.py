from tests.paddle_test_support import MODERN_SANDBOX_API_KEY

SECRET_KEY = "tests-only-secret-key"
USE_TZ = True
TIME_ZONE = "UTC"
ROOT_URLCONF = "tests.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_paddle_mor",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DJANGO_PADDLE_MOR = {
    "API_KEY": MODERN_SANDBOX_API_KEY,
    "WEBHOOK_SECRETS": ["whsec_test"],
    "SANDBOX": True,
    "DEFAULT_SYNC_LIMIT": 25,
}
