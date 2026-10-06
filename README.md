# Urna do Grêmio (Flask + Neon)

Urna eletrônica de escola: chapas com foto, som de confirmação, resultado com impressão
e votos gravados num banco Postgres (Neon), para várias urnas contarem no mesmo lugar.

```
Navegador (urna)  →  Flask (app.py)  →  Neon (Postgres)
```

## 1. Rodar no seu computador (sem configurar nada)

Na pasta do projeto (onde está o `app.py`):

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra http://127.0.0.1:5000. Sem `DATABASE_URL`, o app usa um SQLite local (pasta `instance/`),
bom para testar. Para o Neon, siga o passo 2.

## 2. Conectar no Neon

1. Crie uma conta em https://neon.tech e um projeto (região mais próxima, ex.: São Paulo).
2. No painel, clique em **Connect** e copie a *connection string* (começa com `postgresql://`).
3. Copie `.env.example` para `.env` (`copy .env.example .env` no Windows, `cp` no Linux/macOS)
   e cole a string em `DATABASE_URL`.
4. Gere uma chave e cole em `SECRET_KEY`:
   `python -c "import secrets; print(secrets.token_hex(32))"`
5. Rode `python app.py`. As tabelas (`eleicoes`, `chapas`, `votos`) são criadas sozinhas.

Se o painel mostrar as credenciais separadas (`PGHOST`, `PGUSER`, `PGPASSWORD`...), monte a string assim:
`postgresql://PGUSER:PGPASSWORD@PGHOST/PGDATABASE?sslmode=require`

> O `.env` tem senhas. Ele já está no `.gitignore`: não suba para o GitHub.

## 3. Colocar no ar (Render, plano gratuito)

1. Suba o projeto para um repositório no GitHub (sem o `.env`).
2. No https://render.com: **New > Web Service**, escolha o repositório.
3. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app --workers 2 --threads 4`
4. Em **Environment**, adicione:
   - `DATABASE_URL` = a string do Neon
   - `SECRET_KEY` = a chave gerada
   - `COOKIE_SECURE` = `1`
   - `ADMIN_USER` e `ADMIN_PASSWORD` = login do painel `/admin` (use uma senha forte)
5. Deploy. Você ganha um endereço `https://seu-app.onrender.com` para abrir em qualquer aparelho.

No plano gratuito do Render o site "dorme" depois de um tempo parado e leva ~1 minuto para
acordar. **Abra a urna uns 10 minutos antes da votação.** (PythonAnywhere e Railway também servem.)

## Painel do administrador (só você cadastra mesários)

Defina `ADMIN_USER` e `ADMIN_PASSWORD` no `.env` (no Render, em **Environment**). Depois abra
`/admin`, entre e cadastre cada mesário (escola) com nome, usuário e senha. Dali também dá para
redefinir a senha ou desativar uma conta (o acesso dela cai na hora). Sem `ADMIN_PASSWORD`, o painel
fica desabilitado.

Cada mesário só vê e gerencia as próprias eleições, então várias escolas podem usar o mesmo sistema.
O administrador **não** vê votos nem resultados.

> Bancos criados na versão antiga (eleição com PIN) são recriados na primeira execução. Se já houver
> votos, o app avisa e não apaga nada: exporte o resultado e apague as tabelas `eleicoes`, `chapas`
> e `votos` antes de atualizar.

## Como usar no dia

1. O mesário abre o endereço e entra com o usuário e a senha que o administrador passou.
   Na primeira vez, cria a eleição (nome).
2. Cadastre as chapas (número, nome, foto) na aba **Chapas**.
3. Clique em **Liberar urna e iniciar votação**. Aquele aparelho passa a aceitar votos (por 12 h).
   Nos outros aparelhos, entre com o mesmo login e libere também.
4. Ao terminar: botão **Mesário**, login, aba **Resultado**. Dá para imprimir ou baixar CSV.
5. **Nova eleição** encerra a atual (os votos antigos continuam no banco) e começa outra.

## Segurança e sigilo

- A tabela de votos **não guarda quem votou nem a hora**: só o tipo (chapa/branco/nulo) e o número.
- As senhas dos mesários são guardadas com hash (não em texto) e há limite de 5 tentativas erradas por IP,
  tanto no login do mesário quanto no do administrador.
- O acesso do mesário e do administrador expira após 30 min sem uso.
- Só aparelhos liberados pelo mesário conseguem registrar votos; quem não tem sessão não recebe nem as chapas.
- Quem tem acesso ao painel do Neon pode ver os votos gravados. Proteja a conta.
- Depois do primeiro voto, as chapas ficam travadas.

## Estrutura

```
app.py              API + regras (Flask, SQLAlchemy)
templates/index.html  templates/admin.html
static/app.js       tela da urna e do mesário
static/admin.js     painel do administrador (/admin)
static/style.css
requirements.txt    dependências
Procfile            comando de inicialização (Render/Heroku)
.env.example        modelo das variáveis (copie para .env)
.env                suas variáveis reais (não vai para o GitHub)
instance/           banco SQLite local (só quando não há DATABASE_URL)
```
