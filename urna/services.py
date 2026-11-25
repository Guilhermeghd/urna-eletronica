"""Regras de negócio e consultas compartilhadas pelas rotas."""
import re

from flask import jsonify, session
from sqlalchemy import func

from .extensions import db
from .models import Chapa, Eleicao, Voto


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


def apuracao(e):
    contagem = dict(
        db.session.query(Voto.numero, func.count(Voto.id))
        .filter(Voto.eleicao_id == e.id, Voto.tipo == "chapa")
        .group_by(Voto.numero).all()
    )
    branco = Voto.query.filter_by(eleicao_id=e.id, tipo="branco").count()
    nulo = Voto.query.filter_by(eleicao_id=e.id, tipo="nulo").count()
    chapas = [{"n": c.numero, "name": c.nome, "img": c.img or "", "v": contagem.get(c.numero, 0)} for c in chapas_de(e)]
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
