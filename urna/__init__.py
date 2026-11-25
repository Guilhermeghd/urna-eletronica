"""Urna do Grêmio - backend Flask + Postgres (Neon).

Fluxo:
  0. O dono do sistema cadastra as contas de mesário em /admin.
  1. O mesário entra (usuário + senha), cria a eleição e cadastra as chapas.
  2. O mesário "libera a urna" naquele aparelho (cookie de sessão).
  3. Os eleitores votam; cada voto é gravado no banco via POST /api/voto.
  4. O mesário entra de novo para ver/imprimir o resultado (só da própria eleição).

Sigilo: a tabela de votos NÃO guarda quem votou nem a hora do voto.
"""
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv é opcional
    pass

from flask import Flask  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


def create_app():
    from .config import Config
    from .extensions import db
    from .models import migrar
    from .routes import dono, mesario, urna

    # Estáticos em public/: na Vercel o CDN serve essa pasta; localmente o Flask serve.
    app = Flask(__name__, static_folder=str(RAIZ / "public"), static_url_path="",
                template_folder=str(RAIZ / "templates"))
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # atrás de proxy (Render etc.)
    app.config.from_object(Config)
    if app.config["SECRET_KEY"] == "dev-chave-insegura-troque":
        print("AVISO: defina SECRET_KEY no ambiente antes de usar em produção.")
    if not app.config["ADMIN_PASSWORD"]:
        print("AVISO: defina ADMIN_PASSWORD para habilitar o painel /admin.")

    db.init_app(app)
    for bp in (urna.bp, mesario.bp, dono.bp):
        app.register_blueprint(bp)

    with app.app_context():
        migrar()
        db.create_all()
    return app
