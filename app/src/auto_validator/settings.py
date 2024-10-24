"""
Django settings for auto_validator project.
"""

import inspect
import logging
import os
import pathlib
from datetime import timedelta
from functools import wraps

import environ
import structlog

# from celery.schedules import crontab
root = environ.Path(__file__) - 2

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env()

# .env file contents are not passed to docker image during build stage;
# this results in errors if you require some env var to be set, as if in "env('MYVAR')" -
# obviously it's not set during build stage, but you don't care and want to ignore that.
# To mitigate this, we set ENV_FILL_MISSING_VALUES=1 during build phase, and it activates
# monkey-patching of "environ" module, so that all unset variables get some default value
# and the library does not complain anymore
if env.bool("ENV_FILL_MISSING_VALUES", default=False):

    def patch(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if kwargs.get("default") is env.NOTSET:
                kwargs["default"] = {
                    bool: False,
                    int: 0,
                    float: 0.0,
                }.get(kwargs.get("cast"), None)

            return fn(*args, **kwargs)

        return wrapped

    for name, method in inspect.getmembers(env, predicate=inspect.ismethod):
        setattr(env, name, patch(method))

# read from the .env file if hasn't been sourced already
if env("ENV", default=None) is None:
    env.read_env(root("../../.env"))

ENV = env("ENV")
TESTING = env("TESTING", default=False)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = ["*"]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_extensions",
    "django_probes",
    "django_structlog",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "constance",
    "fingerprint",
    "storages",
    "auto_validator.core",
    "bootstrap5",
    "auto_validator.discord_bot",
    "auto_validator.validator_manager",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_structlog.middlewares.RequestMiddleware",
]


if DEBUG_TOOLBAR := env.bool("DEBUG_TOOLBAR", default=False):
    INTERNAL_IPS = [
        "127.0.0.1",
    ]

    DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda _request: True}
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

if CORS_ENABLED := env.bool("CORS_ENABLED", default=True):
    INSTALLED_APPS.append("corsheaders")
    MIDDLEWARE = ["corsheaders.middleware.CorsMiddleware"] + MIDDLEWARE
    CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
    CORS_ALLOWED_ORIGIN_REGEXES = env.list("CORS_ALLOWED_ORIGIN_REGEXES", default=[])
    CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Content Security Policy
if CSP_ENABLED := env.bool("CSP_ENABLED"):
    MIDDLEWARE.append("csp.middleware.CSPMiddleware")

    CSP_REPORT_ONLY = env.bool("CSP_REPORT_ONLY", default=True)
    CSP_REPORT_URL = env("CSP_REPORT_URL", default=None) or None

    CSP_DEFAULT_SRC = env.tuple("CSP_DEFAULT_SRC")
    CSP_SCRIPT_SRC = env.tuple("CSP_SCRIPT_SRC")
    CSP_STYLE_SRC = env.tuple("CSP_STYLE_SRC")
    CSP_FONT_SRC = env.tuple("CSP_FONT_SRC")
    CSP_IMG_SRC = env.tuple("CSP_IMG_SRC")
    CSP_MEDIA_SRC = env.tuple("CSP_MEDIA_SRC")
    CSP_OBJECT_SRC = env.tuple("CSP_OBJECT_SRC")
    CSP_FRAME_SRC = env.tuple("CSP_FRAME_SRC")
    CSP_CONNECT_SRC = env.tuple("CSP_CONNECT_SRC")
    CSP_CHILD_SRC = env.tuple("CSP_CHILD_SRC")
    CSP_MANIFEST_SRC = env.tuple("CSP_MANIFEST_SRC")
    CSP_WORKER_SRC = env.tuple("CSP_WORKER_SRC")

    CSP_BLOCK_ALL_MIXED_CONTENT = env.bool("CSP_BLOCK_ALL_MIXED_CONTENT", default=False)
    CSP_EXCLUDE_URL_PREFIXES = env.tuple("CSP_EXCLUDE_URL_PREFIXES", default=tuple())


ROOT_URLCONF = "auto_validator.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [root("auto_validator/templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "auto_validator.wsgi.application"

DATABASES = {}
if env("DATABASE_POOL_URL"):  # DB transaction-based connection pool, such as one provided PgBouncer
    DATABASES["default"] = {
        **env.db_url("DATABASE_POOL_URL"),
        "DISABLE_SERVER_SIDE_CURSORS": True,  # prevents random cursor errors with transaction-based connection pool
    }
elif env("DATABASE_URL"):
    DATABASES["default"] = env.db_url("DATABASE_URL")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_L10N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = env("STATIC_URL", default="/static/")
STATIC_ROOT = env("STATIC_ROOT", default=root("static"))
MEDIA_URL = env("MEDIA_URL", default="/media/")
MEDIA_ROOT = env("MEDIA_ROOT", default=root("media"))

# Security
# redirect HTTP to HTTPS
if env.bool("HTTPS_REDIRECT", default=False) and not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = []  # type: ignore
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_CONFIG = {
    "API_UPLOAD_MAX_SIZE": (100 * 1024 * 1024, "API upload max size in bytes", int),
    "ENABLE_VALIDATOR_AUTO_SYNC": (False, "Enable or disable validator auto sync", bool),
}


CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
CELERY_RESULT_BACKEND = env("CELERY_BROKER_URL", default="")  # store results in Redis
CELERY_RESULT_EXPIRES = int(timedelta(days=1).total_seconds())  # time until task result deletion
CELERY_COMPRESSION = "gzip"  # task compression
CELERY_MESSAGE_COMPRESSION = "gzip"  # result compression
CELERY_SEND_EVENTS = True  # needed for worker monitoring
CELERY_BEAT_SCHEDULE = {  # type: ignore
    # 'task_name': {
    #     'task': "auto_validator.core.tasks.demo_task",
    #     'args': [2, 2],
    #     'kwargs': {},
    #     'schedule': timedelta(seconds=30),
    #     'options': {"time_limit": 10000},
    # },
    "update-validator-status": {
        "task": "auto_validator.core.tasks.schedule_update_validator_status",
        "schedule": timedelta(seconds=60),
    },
    "sync_validators_task_core": {
        "task": "auto_validator.core.tasks.sync_validators_task_core",
        "schedule": timedelta(seconds=60),
    },
    "sync_validators_task_validator_manager": {
        "task": "auto_validator.validator_manager.tasks.sync_validators_task_validator_manager",
        "schedule": timedelta(seconds=60),
    },
}
CELERY_TASK_ROUTES = ["auto_validator.celery.route_task"]
CELERY_TASK_TIME_LIMIT = int(timedelta(minutes=5).total_seconds())
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int("CELERY_WORKER_PREFETCH_MULTIPLIER", default=10)
CELERY_BROKER_POOL_LIMIT = env.int("CELERY_BROKER_POOL_LIMIT", default=50)

DJANGO_STRUCTLOG_CELERY_ENABLED = True

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env.int("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "main": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.dev.ConsoleRenderer(),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "main",
        },
        "bot": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": root("logs/bot.log"),
            "formatter": "main",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
        "django_structlog.*": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "celery.task": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "celery.redirected": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "psycopg.pq": {
            # only logs unavailable libs during psycopg initialization
            "propagate": False,
        },
        "bot": {
            "handlers": ["console", "bot"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


def configure_structlog():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


configure_structlog()

# Sentry
if SENTRY_DSN := env("SENTRY_DSN", default=""):
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(  # type: ignore
        dsn=SENTRY_DSN,
        environment=ENV,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
            LoggingIntegration(
                level=logging.INFO,  # Capture info and above as breadcrumbs
                event_level=logging.ERROR,  # Send error events from log messages
            ),
        ],
    )
    ignore_logger("django.security.DisallowedHost")


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

PROJECT_TITLE = "Auto Validator Initiative"
PROJECT_DESCRIPTION = "Bittensor Auto Validator Initiative"

SPECTACULAR_SETTINGS = {
    "TITLE": f"{PROJECT_TITLE} API",
    "DESCRIPTION": PROJECT_DESCRIPTION,
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}


_STORAGE_BACKEND = env("STORAGE_BACKEND")


if _STORAGE_BACKEND == "storages.backends.s3.S3Storage":
    # Instructions for setting up S3 storage using Backblaze B2:
    # 1. create bucket
    #   STORAGE_S3_BUCKET_NAME=auto-validator-bucket-name
    #   b2 bucket create "$STORAGE_S3_BUCKET_NAME" allPrivate
    # 2. create key
    # returns STORAGE_S3_ACCESS_KEY and STORAGE_S3_SECRET_KEY :
    #   b2 key create --bucket "$STORAGE_S3_BUCKET_NAME" "${STORAGE_S3_BUCKET_NAME}-key" readFiles,writeFiles,listBuckets,listFiles
    # 3.
    #   echo STORAGE_S3_ENDPOINT_URL=`b2 account get | jq -r '.s3endpoint'`
    # 4.
    #   echo STORAGE_S3_REGION_NAME=`b2 account get | jq '.s3endpoint | split(".")[1]'`
    _STORAGE_BACKEND_OPTIONS = {
        "access_key": env("STORAGE_S3_ACCESS_KEY"),
        "secret_key": env("STORAGE_S3_SECRET_KEY"),
        "bucket_name": env("STORAGE_S3_BUCKET_NAME"),
        "region_name": env("STORAGE_S3_REGION_NAME"),
        "endpoint_url": env("STORAGE_S3_ENDPOINT_URL") or None,
    }
elif _STORAGE_BACKEND == "django.core.files.storage.FileSystemStorage":
    _STORAGE_BACKEND_OPTIONS = {}
else:
    raise RuntimeError(f"unsupported STORAGE_BACKEND: {_STORAGE_BACKEND}")

STORAGES = {
    "default": {
        "BACKEND": _STORAGE_BACKEND,
        "OPTIONS": _STORAGE_BACKEND_OPTIONS,
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

BT_NETWORK_NAME = env("BT_NETWORK_NAME", default="finney")

SUBNETS_INFO_GITHUB_URL = env(
    "SUBNETS_INFO_GITHUB_URL",
    default="https://raw.githubusercontent.com/bactensor/bt-validator-scripts/master/subnets.yaml",
)

VALIDATORS_INFO_GITHUB_URL = env("VALIDATORS_INFO_GITHUB_URL", default="")

LINODE_API_KEY = env("LINODE_API_KEY", default="")
PAPERSPACE_API_KEY = env("PAPERSPACE_API_KEY", default="")

SIGNATURE_EXPIRE_DURATION = env("SIGNATURE_EXPIRE_DURATION", default="300")

DISCORD_BOT_TOKEN = env("DISCORD_BOT_TOKEN", default="")
GUILD_ID = env("GUILD_ID", default="")
BOT_NAME = env("BOT_NAME", default="")
CATEGORY_NAME = env("CATEGORY_NAME", default="")

BITTENSOR_WALLET_PATH = pathlib.Path(env("BITTENSOR_WALLET_PATH", default="/root/.bittensor/wallets"))
BITTENSOR_WALLET_NAME = env("BITTENSOR_WALLET_NAME", default="validator")
BITTENSOR_HOTKEY_NAME = env("BITTENSOR_HOTKEY_NAME", default="validator-hotkey")

LOCAL_SUBNETS_CONFIG_PATH = pathlib.Path(
    os.path.expanduser(env("LOCAL_SUBNETS_CONFIG_PATH", default="~/.config/auto-validator/subnets.yaml"))
)

LOCAL_SUBNETS_SCRIPTS_PATH = pathlib.Path(
    os.path.expanduser(env("LOCAL_SUBNETS_SCRIPTS_PATH", default="~/.config/auto-validator/subnet-scripts"))
)

LOCAL_VALIDATORS_CONFIG_PATH = pathlib.Path(
    os.path.expanduser(env("LOCAL_VALIDATORS_CONFIG_PATH", default="~/.config/auto-validator/validators.yaml"))
)

GITHUB_SUBNETS_SCRIPTS_PATH = env(
    "GITHUB_SUBNETS_SCRIPTS_PATH", default="https://github.com/bactensor/bt-validator-scripts.git"
)

GITHUB_SUBNETS_CONFIG_PATH = env(
    "GITHUB_SUBNETS_CONFIG_PATH",
    default="https://raw.githubusercontent.com/bactensor/bt-subnet-config/main/subnets.yaml",
)

GITHUB_VALIDATORS_CONFIG_PATH = env(
    "GITHUB_VALIDATORS_CONFIG_PATH",
    default="https://raw.githubusercontent.com/bactensor/bt-validator-config/main/validators.yaml",
)

VALIDATOR_SECRET_VALUE_TYPES = {
    "RANDOM": "random",
    "HOTKEY_SS58_ADDRESS": "hotkey_ss58_address",
    "IP_ADDRESS": "ip_address",
}

MAINNET_CHAIN_ENDPOINT = env(
    "MAINNET_CHAIN_ENDPOINT",
    default="wss://entrypoint-finney.opentensor.ai:443",
)

TESTNET_CHAIN_ENDPOINT = env(
    "TESTNET_CHAIN_ENDPOINT",
    default="wss://test.finney.opentensor.ai:443",
)
