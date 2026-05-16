import os

from fixmyhyd import create_app

app = create_app()


if __name__ == "__main__":
    os.makedirs("temp", exist_ok=True)
    port = int(os.environ.get("PORT", 5001))
    is_dev = os.environ.get("FLASK_ENV") == "development"
    app.run(
        debug=is_dev,
        use_reloader=is_dev,
        threaded=True,
        host="0.0.0.0",
        port=port,
    )
