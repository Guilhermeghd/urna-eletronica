"""Área do mesário: login, eleição, chapas e resultado."""
import csv
import io
from datetime import datetime

from flask import Blueprint, Response, jsonify, request, session
from werkzeug.security import check_password_hash

from ..auth import (bloqueado, entrar_mesario, limpar_falhas, mesario_logado,
                    mesario_required, registrar_falha)
from ..extensions import db
from ..models import Chapa, Eleicao, Mesario
from ..services import apuracao, eleicao_do, erro, total_votos, validar_chapa

bp = Blueprint("mesario", __name__)


@bp.post("/api/login")
def login():
    ip = "m:" + (request.remote_addr or "?")
    if bloqueado(ip):
        return erro("Muitas tentativas. Aguarde alguns minutos.", 429)
    d = request.get_json(silent=True) or {}
    usuario = str(d.get("usuario", "")).strip().lower()
    m = Mesario.query.filter_by(usuario=usuario).first()
    if not m or not m.ativo or not check_password_hash(m.senha_hash, str(d.get("senha", ""))):
        registrar_falha(ip)
        return erro("Usuário ou senha incorretos.", 401)
    limpar_falhas(ip)
    entrar_mesario(m)
    return jsonify(ok=True)


@bp.post("/api/admin/sair")
def sair():
    session.pop("mes", None)
    return jsonify(ok=True)


@bp.post("/api/eleicao")
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


@bp.post("/api/chapas")
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


@bp.put("/api/chapas/<numero_atual>")
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


@bp.delete("/api/chapas/<numero>")
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


@bp.get("/api/resultado")
@mesario_required
def resultado(e):
    return jsonify(apuracao(e))


@bp.get("/api/resultado.csv")
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
        "﻿" + buf.getvalue(),  # BOM: o Excel abre os acentos certinho
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=resultado.csv"},
    )
