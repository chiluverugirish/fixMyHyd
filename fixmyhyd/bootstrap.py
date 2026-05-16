import logging
import os
import secrets

import cloudinary
from dotenv import load_dotenv
from flask import Flask

from .auth import hash_password
from .db import init_database
from .utils import format_date, format_datetime


def _apply_werkzeug_cookie_shim():
    try:
        from werkzeug.wrappers import Response as _WerkzeugResponse

        _orig_set_cookie = _WerkzeugResponse.set_cookie

        def _set_cookie_compat(self, *args, **kwargs):
            kwargs.pop("partitioned", None)
            return _orig_set_cookie(self, *args, **kwargs)

        _WerkzeugResponse.set_cookie = _set_cookie_compat

        if hasattr(_WerkzeugResponse, "delete_cookie"):
            _orig_delete_cookie = _WerkzeugResponse.delete_cookie

            def _delete_cookie_compat(self, *args, **kwargs):
                kwargs.pop("partitioned", None)
                return _orig_delete_cookie(self, *args, **kwargs)

            _WerkzeugResponse.delete_cookie = _delete_cookie_compat
    except Exception:
        pass


def create_app():
    load_dotenv()
    _apply_werkzeug_cookie_shim()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("fixmyhyd")

    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.config["JSON_SORT_KEYS"] = False
    app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    )

    app.template_filter("format_date")(format_date)
    app.template_filter("format_datetime")(format_datetime)

    try:
        init_database(hash_password)
    except Exception as e:
        logger.exception("DB init failed: %s", e)

    from .routes import register_routes

    register_routes(app)
    return app
