"""Sessões (mesário e dono), decoradores de acesso e limite de tentativas de login."""
import time
from functools import wraps

from flask import session

from .extensions import db
from .models import Mesario, Tentativa
from .services import eleicao_do, erro

SESSAO_TTL = 30 * 60  # o acesso (mesário ou dono) expira após 30 min sem uso


def sessao_viva(chave):
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
    s = sessao_viva("mes")
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
        if not sessao_viva("dono"):
            return erro("Acesso do administrador expirado. Entre novamente.", 401)
        return f(*a, **kw)
    return wrapper


# limite de tentativas de login por IP (guardado no banco)
MAX_FALHAS, JANELA = 5, 300


def bloqueado(chave):
    t = db.session.get(Tentativa, chave)
    if not t:
        return False
    if time.time() - t.t0 > JANELA:
        db.session.delete(t)
        db.session.commit()
        return False
    return t.n >= MAX_FALHAS


def registrar_falha(chave):
    t = db.session.get(Tentativa, chave)
    if t and time.time() - t.t0 <= JANELA:
        t.n += 1
    elif t:
        t.n, t.t0 = 1, time.time()
    else:
        db.session.add(Tentativa(chave=chave, n=1, t0=time.time()))
    db.session.commit()


def limpar_falhas(chave):
    t = db.session.get(Tentativa, chave)
    if t:
        db.session.delete(t)
        db.session.commit()
