"""Lado do eleitor: páginas, estado da urna e voto."""
import re

from flask import Blueprint, jsonify, render_template, request, session

from ..auth import mesario_logado, mesario_required
from ..extensions import db
from ..models import Voto
from ..services import chapas_de, eleicao_da_urna, eleicao_do, erro, total_votos

bp = Blueprint("urna", __name__)


@bp.get("/")
def index():
    return render_template("index.html")


@bp.get("/health")
def health():
    return {"ok": True}


@bp.get("/api/estado")
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


@bp.post("/api/urna/liberar")
@mesario_required
def liberar_urna(e):
    if not chapas_de(e):
        return erro("Cadastre ao menos uma chapa antes de iniciar a votação.", 409)
    session["urna"] = e.id
    session.pop("mes", None)  # por segurança, sai da área do mesário
    session.permanent = True
    return jsonify(ok=True)


@bp.post("/api/voto")
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
