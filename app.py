"""Urna do Grêmio - backend Flask + Postgres (Neon).

Fluxo:
  0. O dono do sistema cadastra as contas de mesário em /admin.
  1. O mesário entra (usuário + senha), cria a eleição e cadastra as chapas.
  2. O mesário "libera a urna" naquele aparelho (cookie de sessão).
  3. Os eleitores votam; cada voto é gravado no banco via POST /api/voto.
  4. O mesário entra de novo para ver/imprimir o resultado (só da própria eleição).

Sigilo: a tabela de votos NÃO guarda quem votou nem a hora do voto.
"""
import csv
import hmac
import io
import os
import re
import time
from datetime import datetime, timedelta
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv é opcional
    pass

from flask import Flask, Response, jsonify, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "sqlite:///urna_local.db")
    # O Neon entrega "postgresql://"; o SQLAlchemy precisa saber o driver (psycopg 3).
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)  # atrás de proxy (Render etc.)
app.config.update(
    SQLALCHEMY_DATABASE_URI=_database_url(),
    # O Neon "dorme" quando ocioso: pre_ping/recycle evitam conexões mortas.
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "pool_recycle": 300},
    SECRET_KEY=os.environ.get("SECRET_KEY") or "dev-chave-insegura-troque",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
if app.config["SECRET_KEY"] == "dev-chave-insegura-troque":
    print("AVISO: defina SECRET_KEY no ambiente antes de usar em produção.")

db = SQLAlchemy(app)


# ----------------------------------------------------------------- modelos
class Mesario(db.Model):
    """Conta de mesário (escola). Só o dono do sistema cria contas, pelo /admin."""
    __tablename__ = "mesarios"
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(30), nullable=False, unique=True)
    nome = db.Column(db.String(80), nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)


class Eleicao(db.Model):
    __tablename__ = "eleicoes"
    id = db.Column(db.Integer, primary_key=True)
    mesario_id = db.Column(db.Integer, db.ForeignKey("mesarios.id"), nullable=False, index=True)
    titulo = db.Column(db.String(120), nullable=False)
    ativa = db.Column(db.Boolean, nullable=False, default=True, index=True)
    criada_em = db.Column(db.DateTime, default=datetime.utcnow)
    encerrada_em = db.Column(db.DateTime)


class Chapa(db.Model):
    __tablename__ = "chapas"
    id = db.Column(db.Integer, primary_key=True)
    eleicao_id = db.Column(db.Integer, db.ForeignKey("eleicoes.id"), nullable=False, index=True)
    numero = db.Column(db.String(4), nullable=False)
    nome = db.Column(db.String(60), nullable=False)
    img = db.Column(db.Text, default="")  # foto em data URL (base64), já reduzida no navegador
    __table_args__ = (db.UniqueConstraint("eleicao_id", "numero", name="uq_chapa_numero"),)

    def to_dict(self):
        return {"n": self.numero, "name": self.nome, "img": self.img or ""}


class Voto(db.Model):
    """Sem nenhum dado do eleitor e sem horário: só o voto."""
    __tablename__ = "votos"
    id = db.Column(db.Integer, primary_key=True)
    eleicao_id = db.Column(db.Integer, db.ForeignKey("eleicoes.id"), nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)  # 'chapa' | 'branco' | 'nulo'
    numero = db.Column(db.String(4))                  # só quando tipo == 'chapa'


def _migrar():
    """Bancos criados antes das contas de mesário (eleição com PIN) são recriados."""
    insp = inspect(db.engine)
    if insp.has_table("eleicoes") and "mesario_id" not in {c["name"] for c in insp.get_columns("eleicoes")}:
        if insp.has_table("votos") and db.session.query(func.count(Voto.id)).scalar():
            raise RuntimeError("O banco tem votos do formato antigo (com PIN). Exporte o resultado "
                               "e apague as tabelas eleicoes/chapas/votos antes de atualizar.")
        db.session.rollback()
        db.metadata.drop_all(db.engine, tables=[Voto.__table__, Chapa.__table__, Eleicao.__table__])


with app.app_context():
    _migrar()
    db.create_all()


# ----------------------------------------------------------------- helpers
def erro(msg, status=400):
    return jsonify(erro=msg), status


def eleicao_do(m):
    """Eleição ativa do mesário m (cada mesário só tem a sua)."""
    if not m:
        return None
    return Eleicao.query.filter_by(ativa=True, mesario_id=m.id).order_by(Eleicao.id.desc()).first()


def eleicao_da_urna():
    """Eleição para a qual este aparelho foi liberado (None se já encerrada)."""
    eid = session.get("urna")
    e = db.session.get(Eleicao, eid) if eid else None
    return e if e and e.ativa else None


def chapas_de(e):
    return Chapa.query.filter_by(eleicao_id=e.id).order_by(Chapa.numero).all()


def total_votos(e):
    return Voto.query.filter_by(eleicao_id=e.id).count()


SESSAO_TTL = 30 * 60  # o acesso (mesário ou dono) expira após 30 min sem uso


def _sessao_viva(chave):
    """Devolve o valor da sessão se ainda não expirou e renova o relógio."""
    s = session.get(chave)
    if not s:
        return None
    if time.time() - s.get("t", 0) > SESSAO_TTL:
        session.pop(chave, None)
        return None
    s["t"] = time.time()
    session[chave] = s
    session.permanent = True
    return s


def mesario_logado():
    s = _sessao_viva("mes")
    m = db.session.get(Mesario, s["m"]) if s else None
    if s and not (m and m.ativo):  # conta desativada: derruba a sessão
        session.pop("mes", None)
        return None
    return m


def entrar_mesario(m):
    session["mes"] = {"m": m.id, "t": time.time()}
    session.permanent = True


def mesario_required(f):
    """Injeta (mesário, eleição ativa dele). Exige login de mesário."""
    @wraps(f)
    def wrapper(*a, **kw):
        m = mesario_logado()
        if not m:
            return erro("Acesso expirado. Entre novamente.", 401)
        e = eleicao_do(m)
        if not e:
            return erro("Nenhuma eleição ativa.", 409)
        return f(e, *a, **kw)
    return wrapper


def dono_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not _sessao_viva("dono"):
            return erro("Acesso do administrador expirado. Entre novamente.", 401)
        return f(*a, **kw)
    return wrapper


# limite simples de tentativas de login por IP (por processo)
_falhas = {}
MAX_FALHAS, JANELA = 5, 300


def _bloqueado(ip):
    n, t0 = _falhas.get(ip, (0, 0))
    if time.time() - t0 > JANELA:
        _falhas.pop(ip, None)
        return False
    return n >= MAX_FALHAS


def _registrar_falha(ip):
    n, t0 = _falhas.get(ip, (0, time.time()))
    _falhas[ip] = (n + 1, t0)


def apuracao(e):
    contagem = dict(
        db.session.query(Voto.numero, func.count(Voto.id))
        .filter(Voto.eleicao_id == e.id, Voto.tipo == "chapa")
        .group_by(Voto.numero).all()
    )
    branco = Voto.query.filter_by(eleicao_id=e.id, tipo="branco").count()
    nulo = Voto.query.filter_by(eleicao_id=e.id, tipo="nulo").count()
    chapas = [{"n": c.numero, "name": c.nome, "v": contagem.get(c.numero, 0)} for c in chapas_de(e)]
    total = sum(c["v"] for c in chapas) + branco + nulo
    return {"titulo": e.titulo, "chapas": chapas, "branco": branco, "nulo": nulo, "total": total}


def validar_chapa(e, numero, nome, img, ignorar_id=None):
    if not re.fullmatch(r"\d{1,4}", numero or ""):
        return "O número da chapa deve ter de 1 a 4 dígitos."
    if not nome or len(nome) > 60:
        return "Informe o nome da chapa (até 60 caracteres)."
    if img and (not img.startswith("data:image/") or len(img) > 400_000):
        return "Foto inválida ou grande demais."
    outras = [c for c in chapas_de(e) if c.id != ignorar_id]
    if any(c.numero == numero for c in outras):
        return f"Já existe uma chapa com o número {numero}."
    if outras and len(numero) != len(outras[0].numero):
        return "Todos os números de chapa devem ter a mesma quantidade de dígitos."
    return None


# ------------------------------------------------------------------ rotas
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/estado")
def estado():
    m = mesario_logado()
    ue = eleicao_da_urna()
    out = {"logado": bool(m), "mesario": m.nome if m else "", "ativa": False, "titulo": "",
           "admin": bool(m), "urna_liberada": bool(ue), "chapas": [], "travado": False}
    if m:
        e = eleicao_do(m)
        if e:
            out.update(ativa=True, titulo=e.titulo, chapas=[c.to_dict() for c in chapas_de(e)],
                       travado=total_votos(e) > 0)
    elif ue:  # urna liberada: recebe só as chapas da própria eleição
        out.update(titulo=ue.titulo, chapas=[c.to_dict() for c in chapas_de(ue)])
    return jsonify(out)


@app.post("/api/eleicao")
def criar_eleicao():
    m = mesario_logado()
    if not m:
        return erro("Entre como mesário para criar uma eleição.", 401)
    d = request.get_json(silent=True) or {}
    titulo = (d.get("titulo") or "Eleição").strip()[:120] or "Eleição"
    atual = eleicao_do(m)
    if atual:  # a eleição anterior fica guardada no banco, só deixa de ser a ativa
        atual.ativa = False
        atual.encerrada_em = datetime.utcnow()
    db.session.add(Eleicao(mesario_id=m.id, titulo=titulo))
    db.session.commit()
    session.pop("urna", None)
    return jsonify(ok=True)


@app.post("/api/login")
def login():
    ip = "m:" + (request.remote_addr or "?")
    if _bloqueado(ip):
        return erro("Muitas tentativas. Aguarde alguns minutos.", 429)
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip().lower()
    m = Mesario.query.filter_by(usuario=usuario).first()
    if not m or not m.ativo or not check_password_hash(m.senha_hash, str(d.get("senha", ""))):
        _registrar_falha(ip)
        return erro("Usuário ou senha incorretos.", 401)
    _falhas.pop(ip, None)
    entrar_mesario(m)
    return jsonify(ok=True)


@app.post("/api/admin/sair")
def admin_sair():
    session.pop("mes", None)
    return jsonify(ok=True)


@app.post("/api/urna/liberar")
@mesario_required
def liberar_urna(e):
    if not chapas_de(e):
        return erro("Cadastre ao menos uma chapa antes de iniciar a votação.", 409)
    session["urna"] = e.id
    session.pop("mes", None)  # por segurança, sai da área do mesário
    session.permanent = True
    return jsonify(ok=True)


@app.post("/api/chapas")
@mesario_required
def criar_chapa(e):
    if total_votos(e) > 0:
        return erro("A votação já começou: as chapas estão travadas.", 409)
    d = request.get_json(silent=True) or {}
    numero, nome, img = str(d.get("numero", "")).strip(), (d.get("nome") or "").strip(), d.get("img") or ""
    msg = validar_chapa(e, numero, nome, img)
    if msg:
        return erro(msg)
    db.session.add(Chapa(eleicao_id=e.id, numero=numero, nome=nome, img=img))
    db.session.commit()
    return jsonify(ok=True)


@app.put("/api/chapas/<numero_atual>")
@mesario_required
def editar_chapa(e, numero_atual):
    if total_votos(e) > 0:
        return erro("A votação já começou: as chapas estão travadas.", 409)
    c = Chapa.query.filter_by(eleicao_id=e.id, numero=numero_atual).first()
    if not c:
        return erro("Chapa não encontrada.", 404)
    d = request.get_json(silent=True) or {}
    numero, nome, img = str(d.get("numero", "")).strip(), (d.get("nome") or "").strip(), d.get("img") or ""
    msg = validar_chapa(e, numero, nome, img, ignorar_id=c.id)
    if msg:
        return erro(msg)
    c.numero, c.nome, c.img = numero, nome, img
    db.session.commit()
    return jsonify(ok=True)


@app.delete("/api/chapas/<numero>")
@mesario_required
def remover_chapa(e, numero):
    if total_votos(e) > 0:
        return erro("A votação já começou: as chapas estão travadas.", 409)
    c = Chapa.query.filter_by(eleicao_id=e.id, numero=numero).first()
    if not c:
        return erro("Chapa não encontrada.", 404)
    db.session.delete(c)
    db.session.commit()
    return jsonify(ok=True)


@app.post("/api/voto")
def votar():
    e = eleicao_da_urna()
    if not e:
        return erro("Esta urna não está liberada. Chame o mesário.", 403)
    chapas = chapas_de(e)
    if not chapas:
        return erro("Nenhuma chapa cadastrada.", 409)
    d = request.get_json(silent=True) or {}
    tipo = d.get("tipo")
    if tipo == "branco":
        voto = Voto(eleicao_id=e.id, tipo="branco")
    elif tipo == "chapa":
        numero = str(d.get("numero", ""))
        if not re.fullmatch(r"\d{1,4}", numero) or len(numero) != len(chapas[0].numero):
            return erro("Número incompleto.")
        existe = any(c.numero == numero for c in chapas)
        # quem decide se é nulo é o servidor, não o navegador
        voto = Voto(eleicao_id=e.id, tipo="chapa" if existe else "nulo", numero=numero if existe else None)
    else:
        return erro("Voto inválido.")
    db.session.add(voto)
    db.session.commit()
    return jsonify(ok=True)


@app.get("/api/resultado")
@mesario_required
def resultado(e):
    return jsonify(apuracao(e))


@app.get("/api/resultado.csv")
@mesario_required
def resultado_csv(e):
    r = apuracao(e)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([r["titulo"]])
    w.writerow(["Chapa", "Nome", "Votos"])
    for c in r["chapas"]:
        w.writerow([c["n"], c["name"], c["v"]])
    w.writerow(["", "Brancos", r["branco"]])
    w.writerow(["", "Nulos", r["nulo"]])
    w.writerow(["", "Total", r["total"]])
    return Response(
        "\ufeff" + buf.getvalue(),  # BOM: o Excel abre os acentos certinho
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=resultado.csv"},
    )


# ------------------------------------------------- painel do dono (/admin)
# Só quem tem ADMIN_USER/ADMIN_PASSWORD (variáveis de ambiente) cria contas de mesário.
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    print("AVISO: defina ADMIN_PASSWORD para habilitar o painel /admin.")


def _igual(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())


def mesario_dict(m):
    return {"id": m.id, "usuario": m.usuario, "nome": m.nome, "ativo": m.ativo,
            "eleicoes": Eleicao.query.filter_by(mesario_id=m.id).count()}


@app.get("/admin")
def painel_dono():
    return render_template("admin.html")


@app.get("/api/dono/estado")
def dono_estado():
    return jsonify(logado=bool(_sessao_viva("dono")), habilitado=bool(ADMIN_PASSWORD))


@app.post("/api/dono/login")
def dono_login():
    if not ADMIN_PASSWORD:
        return erro("Painel desabilitado: defina ADMIN_PASSWORD no servidor.", 503)
    ip = "d:" + (request.remote_addr or "?")
    if _bloqueado(ip):
        return erro("Muitas tentativas. Aguarde alguns minutos.", 429)
    d = request.get_json(silent=True) or {}
    ok_u, ok_s = _igual(d.get("usuario", ""), ADMIN_USER), _igual(d.get("senha", ""), ADMIN_PASSWORD)
    if not (ok_u and ok_s):
        _registrar_falha(ip)
        return erro("Usuário ou senha incorretos.", 401)
    _falhas.pop(ip, None)
    session["dono"] = {"t": time.time()}
    session.permanent = True
    return jsonify(ok=True)


@app.post("/api/dono/sair")
def dono_sair():
    session.pop("dono", None)
    return jsonify(ok=True)


@app.get("/api/dono/mesarios")
@dono_required
def dono_listar():
    return jsonify(mesarios=[mesario_dict(m) for m in Mesario.query.order_by(Mesario.nome).all()])


@app.post("/api/dono/mesarios")
@dono_required
def dono_criar():
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip().lower()
    nome = str(d.get("nome", "")).strip()
    senha = str(d.get("senha", ""))
    if not re.fullmatch(r"[a-z0-9._-]{3,30}", usuario):
        return erro("Usuário: 3 a 30 caracteres (letras minúsculas, números, ponto, hífen ou sublinhado).")
    if not nome or len(nome) > 80:
        return erro("Informe o nome da escola/mesário (até 80 caracteres).")
    if len(senha) < 6:
        return erro("A senha precisa ter ao menos 6 caracteres.")
    if Mesario.query.filter_by(usuario=usuario).first():
        return erro("Já existe um mesário com esse usuário.", 409)
    db.session.add(Mesario(usuario=usuario, nome=nome, senha_hash=generate_password_hash(senha)))
    db.session.commit()
    return jsonify(ok=True)


@app.patch("/api/dono/mesarios/<int:mid>")
@dono_required
def dono_editar(mid):
    m = db.session.get(Mesario, mid)
    if not m:
        return erro("Mesário não encontrado.", 404)
    d = request.get_json(silent=True) or {}
    if "ativo" in d:
        m.ativo = bool(d["ativo"])
    if "senha" in d:
        if len(str(d["senha"])) < 6:
            return erro("A senha precisa ter ao menos 6 caracteres.")
        m.senha_hash = generate_password_hash(str(d["senha"]))
    db.session.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
