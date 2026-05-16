import os

from fixmyhyd import create_app

app = create_app()


if __name__ == "__main__":
    os.makedirs("temp", exist_ok=True)

    port = int(os.environ.get("PORT", 5001))
    is_dev = os.environ.get("FLASK_ENV", "production") == "development"

    print("===================================")
    print("FixMyHyd Flask Server Starting...")
    print(f"Running on Port: {port}")
    print(f"Development Mode: {is_dev}")
    print("===================================")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=is_dev,
        threaded=True,
        use_reloader=False
    )
