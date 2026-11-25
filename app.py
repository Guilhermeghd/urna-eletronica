"""Ponto de entrada (gunicorn app:app / Vercel / python app.py). O código está em urna/."""
from urna import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
