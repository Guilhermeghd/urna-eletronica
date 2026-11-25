"""Painel do dono do sistema (/admin): cadastro de contas de mesário."""
import hmac
import re
import time

from flask import Blueprint, current_app, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

from ..auth import bloqueado, dono_required, limpar_falhas, registrar_falha, sessao_viva
from ..extensions import db
from ..models import Eleicao, Mesario
from ..services import erro

bp = Blueprint("dono", __name__)


def _igual(a, b):
    return hmac.compare_digest(str(a).encode(), str(b).encode())


def mesario_dict(m):
    return {"id": m.id, "usuario": m.usuario, "nome": m.nome, "ativo": m.ativo,
            "eleicoes": Eleicao.query.filter_by(mesario_id=m.id).count()}


@bp.get("/admin")
def painel():
    return render_template("admin.html")


@bp.get("/api/dono/estado")
def estado():
    return jsonify(logado=bool(sessao_viva("dono")), habilitado=bool(current_app.config["ADMIN_PASSWORD"]))


@bp.post("/api/dono/login")
def login():
    senha_admin = current_app.config["ADMIN_PASSWORD"]
    if not senha_admin:
        return erro("Painel desabilitado: defina ADMIN_PASSWORD no servidor.", 503)
    ip = "d:" + (request.remote_addr or "?")
    if bloqueado(ip):
        return erro("Muitas tentativas. Aguarde alguns minutos.", 429)
    d = request.get_json(silent=True) or {}
    ok_u = _igual(d.get("usuario", ""), current_app.config["ADMIN_USER"])
    ok_s = _igual(d.get("senha", ""), senha_admin)
    if not (ok_u and ok_s):
        registrar_falha(ip)
        return erro("Usuário ou senha incorretos.", 401)
    limpar_falhas(ip)
    session["dono"] = {"t": time.time()}
    session.permanent = True
    return jsonify(ok=True)


@bp.post("/api/dono/sair")
def sair():
    session.pop("dono", None)
    return jsonify(ok=True)


@bp.get("/api/dono/mesarios")
@dono_required
def listar():
    return jsonify(mesarios=[mesario_dict(m) for m in Mesario.query.order_by(Mesario.nome).all()])


@bp.post("/api/dono/mesarios")
@dono_required
def criar():
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


@bp.patch("/api/dono/mesarios/<int:mid>")
@dono_required
def editar(mid):
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
