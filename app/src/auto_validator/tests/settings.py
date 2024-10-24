import os

os.environ["DEBUG_TOOLBAR"] = "False"
os.environ["STORAGE_BACKEND"] = "django.core.files.storage.FileSystemStorage"

from auto_validator.settings import *  # noqa: E402,F403
