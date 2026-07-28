import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-dev-only-change-in-production",
)

DEBUG = os.environ.get("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_host:
    ALLOWED_HOSTS.append(render_host)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "mailing.apps.MailingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
]

if not DEBUG:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")

MIDDLEWARE.extend([
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
])

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

_database_url = os.environ.get("DATABASE_URL", "")
_ssl_env = os.environ.get("DATABASE_SSL_REQUIRE", "").lower()
if _ssl_env in ("true", "1", "yes"):
    _database_ssl_require = True
elif _ssl_env in ("false", "0", "no"):
    _database_ssl_require = False
else:
    _database_ssl_require = bool(os.environ.get("RENDER")) or "sslmode=require" in _database_url

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=_database_ssl_require,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

if DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

RENDER_ORIGINS = (
    "https://enriquecimento-nio.onrender.com",
    "https://mailing-enderecos.onrender.com",
)

render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if render_host:
    RENDER_ORIGINS = (*RENDER_ORIGINS, f"https://{render_host}")

for origin in RENDER_ORIGINS:
    if origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(origin)

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

GOOGLE_MAPS_URL = os.environ.get(
    "GOOGLE_MAPS_URL",
    "https://www.google.com/maps/d/viewer?mid=1NfQvsWBh_AmyvVABRRd7_lJ4W4mg8q4&ll=-23.281103667749008%2C-51.28276285&z=17",
)
GOOGLE_MAPS_LEGEND_XPATH = os.environ.get(
    "GOOGLE_MAPS_LEGEND_XPATH",
    '//*[@id="legendPanel"]/div/div/div[1]/div[4]/div/span/span/span',
)
PLAYWRIGHT_LEGEND_TIMEOUT_MS = int(os.environ.get("PLAYWRIGHT_LEGEND_TIMEOUT_MS", "60000"))
PLAYWRIGHT_HEADLESS = os.environ.get("PLAYWRIGHT_HEADLESS", "True").lower() == "true"
PLAYWRIGHT_SEARCH_DELAY_MS = int(os.environ.get("PLAYWRIGHT_SEARCH_DELAY_MS", "2500"))
_default_browser_channel = "" if render_host else "chrome"
PLAYWRIGHT_BROWSER_CHANNEL = os.environ.get(
    "PLAYWRIGHT_BROWSER_CHANNEL", _default_browser_channel
)
PLAYWRIGHT_USER_DATA_DIR = os.environ.get(
    "PLAYWRIGHT_USER_DATA_DIR",
    str(BASE_DIR / "playwright" / "chrome-profile"),
)
PLAYWRIGHT_ENABLED = os.environ.get(
    "PLAYWRIGHT_ENABLED",
    "False" if render_host else "True",
).lower() == "true"
PLAYWRIGHT_REQUIRE_AUTH = os.environ.get(
    "PLAYWRIGHT_REQUIRE_AUTH",
    "True" if render_host else "False",
).lower() == "true"
_default_storage_state = BASE_DIR / "playwright" / "google-auth.json"
PLAYWRIGHT_STORAGE_STATE = os.environ.get(
    "PLAYWRIGHT_STORAGE_STATE",
    str(_default_storage_state),
)
