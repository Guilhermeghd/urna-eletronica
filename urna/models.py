from datetime import datetime

from sqlalchemy import func, inspect

from .extensions import db


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


class Tentativa(db.Model):
    """Falhas de login por IP. No banco (e não na memória) porque a Vercel usa várias instâncias."""
    __tablename__ = "tentativas"
    chave = db.Column(db.String(80), primary_key=True)
    n = db.Column(db.Integer, nullable=False, default=0)
    t0 = db.Column(db.Float, nullable=False)


class Voto(db.Model):
    """Sem nenhum dado do eleitor e sem horário: só o voto."""
    __tablename__ = "votos"
    id = db.Column(db.Integer, primary_key=True)
    eleicao_id = db.Column(db.Integer, db.ForeignKey("eleicoes.id"), nullable=False, index=True)
    tipo = db.Column(db.String(10), nullable=False)  # 'chapa' | 'branco' | 'nulo'
    numero = db.Column(db.String(4))                  # só quando tipo == 'chapa'


def migrar():
    """Bancos criados antes das contas de mesário (eleição com PIN) são recriados."""
    insp = inspect(db.engine)
    if insp.has_table("eleicoes") and "mesario_id" not in {c["name"] for c in insp.get_columns("eleicoes")}:
        if insp.has_table("votos") and db.session.query(func.count(Voto.id)).scalar():
            raise RuntimeError("O banco tem votos do formato antigo (com PIN). Exporte o resultado "
                               "e apague as tabelas eleicoes/chapas/votos antes de atualizar.")
        db.session.rollback()
        db.metadata.drop_all(db.engine, tables=[Voto.__table__, Chapa.__table__, Eleicao.__table__])
