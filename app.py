# Sistema Cavere - Gestão e Controle de Cautelas - Ambipar Response
import os
import sys
import sqlite3
import html
import re
import secrets
import hmac
from functools import wraps
from contextlib import contextmanager
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash, abort, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

@contextmanager
def suprimir_warnings_glib():
    """
    Suprime avisos e warnings de baixo nível (C/GLib/GIO) no Windows ao inicializar
    ou executar WeasyPrint/GTK (como verificações de manifesto de apps UWP).
    """
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
    except Exception:
        yield

# Importa WeasyPrint de forma silenciosa para evitar ruído de GLib/GIO no console do Windows
with suprimir_warnings_glib():
    from weasyprint import HTML

# Carrega variáveis de ambiente do arquivo .env caso exista (sem dependência externa)
def _carregar_env():
    caminho_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(caminho_env):
        try:
            with open(caminho_env, 'r', encoding='utf-8') as f:
                for linha in f:
                    linha = linha.strip()
                    if linha and not linha.startswith('#') and '=' in linha:
                        k, v = linha.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_carregar_env()

app = Flask(__name__)

# Configuração de SECRET_KEY persistente e segura (Session Hijacking & Forgery Prevention)
def carregar_ou_gerar_secret_key():
    """
    Obtém SECRET_KEY de variáveis de ambiente ou de um arquivo local protegido (.secret_key).
    Se inexistente, gera uma chave aleatória criptograficamente forte para impedir
    que sessões sejam forjadas por chaves padrão conhecidas no repositório.
    """
    env_key = os.environ.get('SECRET_KEY')
    if env_key:
        return env_key
    chave_arquivo = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.secret_key')
    if os.path.exists(chave_arquivo):
        try:
            with open(chave_arquivo, 'r', encoding='utf-8') as f:
                conteudo = f.read().strip()
                if len(conteudo) >= 32:
                    return conteudo
        except Exception:
            pass
    nova_chave = secrets.token_hex(32)
    try:
        with open(chave_arquivo, 'w', encoding='utf-8') as f:
            f.write(nova_chave)
    except Exception:
        pass
    return nova_chave

def is_safe_redirect_url(target):
    """
    Valida estritamente se o destino de redirecionamento é uma URL relativa interna,
    evitando vulnerabilidades de Open Redirect (ex: //evil.com, /\\evil.com, javascript:).
    """
    if not target or not isinstance(target, str):
        return False
    target = target.strip()
    if target.startswith('\\') or target.startswith('//') or target.startswith('/\\'):
        return False
    parsed = urlsplit(target)
    return parsed.scheme == '' and parsed.netloc == '' and target.startswith('/')

app.config['SECRET_KEY'] = carregar_ou_gerar_secret_key()
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Impede que scripts maliciosos acessem os cookies de sessão (mitiga XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Proteção contra ataques CSRF
if os.environ.get('SESSION_COOKIE_SECURE', '0') == '1':
    app.config['SESSION_COOKIE_SECURE'] = True  # Envia cookies apenas sob conexão HTTPS criptografada
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limite estrito de 16MB para payload de requisições contra DoS

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "warning"


# --- CAMADA CENTRALIZADA DE BANCO DE DADOS (SQLite Hardening) ---

def get_db_connection():
    """
    Retorna uma conexão SQLite com modo WAL, chaves estrangeiras ativadas
    e timeout estendido para alta concorrência e integridade referencial.
    """
    conn = sqlite3.connect('Cavere.db', timeout=15.0)
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.execute('PRAGMA journal_mode = WAL;')
    conn.execute('PRAGMA synchronous = NORMAL;')
    return conn


# Modelo de Usuário para autenticação
class Usuario(UserMixin):
    def __init__(self, id, username, senha_hash, role, trocar_senha=0):
        self.id = id
        self.username = username
        self.senha_hash = senha_hash
        self.role = role
        self.trocar_senha = trocar_senha

    @property
    def is_admin(self):
        return self.role == 'admin'


@login_manager.user_loader
def load_user(user_id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, username, senha_hash, role, trocar_senha FROM usuarios WHERE id = ?', (user_id,))
    dados = cursor.fetchone()
    conexao.close()
    if dados:
        trocar = dados[4] if len(dados) > 4 and dados[4] is not None else 0
        return Usuario(id=dados[0], username=dados[1], senha_hash=dados[2], role=dados[3], trocar_senha=trocar)
    return None


def inicializar_banco():
    """
    Cria as tabelas 'usuarios', 'equipamentos', 'coordenadores', 'cautelas' e 'solicitacoes'
    no SQLite caso não existam, garantindo as colunas necessárias e integridade.
    """
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'coordenador')),
            trocar_senha INTEGER DEFAULT 0
        )
    ''')

    # Garante a coluna trocar_senha na tabela usuarios
    cursor.execute("PRAGMA table_info(usuarios)")
    colunas_usuarios = [col[1] for col in cursor.fetchall()]
    if 'trocar_senha' not in colunas_usuarios:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN trocar_senha INTEGER DEFAULT 0")

    # Tabela para equipamentos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS equipamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo TEXT NOT NULL,
            modelo TEXT,
            patrimonio_sn TEXT UNIQUE,
            imei_1 TEXT,
            imei_2 TEXT,
            status TEXT DEFAULT 'Disponível'
        )
    ''')

    # Tabela para coordenadores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coordenadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_completo TEXT NOT NULL,
            cpf_matricula TEXT UNIQUE NOT NULL
        )
    ''')

    # Tabela para cautelas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cautelas (
            id_cautela INTEGER PRIMARY KEY AUTOINCREMENT,
            id_equipamento INTEGER,
            id_coordenador INTEGER,
            rdo_vinculado TEXT,
            data_hora_saida DATETIME DEFAULT CURRENT_TIMESTAMP,
            data_hora_devolucao DATETIME,
            observacoes TEXT,
            id_solicitacao INTEGER,
            FOREIGN KEY(id_equipamento) REFERENCES equipamentos(id),
            FOREIGN KEY(id_coordenador) REFERENCES coordenadores(id)
        )
    ''')

    # Tabela para chamados de solicitação de equipamentos (multissetorial)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS solicitacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_coordenador INTEGER NOT NULL,
            tipo_equipamento TEXT NOT NULL,
            quantidade INTEGER NOT NULL DEFAULT 1,
            destinatario TEXT NOT NULL,
            plataforma TEXT NOT NULL,
            rdo_projeto TEXT,
            data_necessidade TEXT,
            prioridade TEXT DEFAULT 'Normal',
            justificativa TEXT,
            status TEXT NOT NULL DEFAULT 'Pendente',
            tipo_uso TEXT DEFAULT 'Operação',
            setor TEXT DEFAULT 'Operações',
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(id_coordenador) REFERENCES coordenadores(id)
        )
    ''')
    
    # Migrações seguras de colunas caso o banco já exista
    cursor.execute("PRAGMA table_info(cautelas)")
    colunas_cautelas = [col[1] for col in cursor.fetchall()]
    if colunas_cautelas and 'id_solicitacao' not in colunas_cautelas:
        cursor.execute("ALTER TABLE cautelas ADD COLUMN id_solicitacao INTEGER")

    cursor.execute("PRAGMA table_info(solicitacoes)")
    colunas_solicitacoes = [col[1] for col in cursor.fetchall()]
    if colunas_solicitacoes:
        if 'tipo_uso' not in colunas_solicitacoes:
            cursor.execute("ALTER TABLE solicitacoes ADD COLUMN tipo_uso TEXT DEFAULT 'Operação'")
        if 'setor' not in colunas_solicitacoes:
            cursor.execute("ALTER TABLE solicitacoes ADD COLUMN setor TEXT DEFAULT 'Operações'")

    cursor.execute("PRAGMA table_info(coordenadores)")
    colunas_coord = [col[1] for col in cursor.fetchall()]
    if colunas_coord and 'setor' not in colunas_coord:
        cursor.execute("ALTER TABLE coordenadores ADD COLUMN setor TEXT DEFAULT 'Operações'")

    conexao.commit()
    conexao.close()

# Inicializa as tabelas necessárias no banco
inicializar_banco()


# --- SISTEMA DE DEFESA ANTI-CSRF ---

def gerar_csrf_token():
    """Gera e armazena token criptográfico CSRF na sessão do usuário."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

@app.context_processor
def inject_csrf_token():
    """Disponibiliza {{ csrf_token() }} para renderização em todos os templates."""
    return dict(csrf_token=gerar_csrf_token)


# --- SISTEMA DE DEFESA CONTRA FORÇA BRUTA & RATE LIMITING NO LOGIN ---

TENTATIVAS_FALHAS = {}
MAX_TENTATIVAS_FALHAS = 5
TEMPO_BLOQUEIO_SEGUNDOS = 900  # 15 minutos

def obter_ip_cliente():
    """Obtém o endereço IP real da requisição para auditoria e controle."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'

def verificar_bloqueio_login(ip, username):
    """Verifica se o IP ou conta está sob bloqueio temporário por tentativas excessivas."""
    agora = datetime.now()
    chave = (ip, (username or '').strip().lower())
    registro = TENTATIVAS_FALHAS.get(chave)
    if registro and registro.get('bloqueado_ate'):
        if agora < registro['bloqueado_ate']:
            tempo_restante = int((registro['bloqueado_ate'] - agora).total_seconds())
            minutos = max(1, (tempo_restante + 59) // 60)
            return False, f"Muitas tentativas incorretas. Conta bloqueada temporariamente por segurança. Tente novamente em {minutos} minuto(s)."
        else:
            del TENTATIVAS_FALHAS[chave]
    return True, ''

def registrar_falha_login(ip, username):
    """Registra uma falha de autenticação e aciona o bloqueio ao atingir o limite."""
    agora = datetime.now()
    chave = (ip, (username or '').strip().lower())
    if chave not in TENTATIVAS_FALHAS:
        TENTATIVAS_FALHAS[chave] = {'tentativas': 1, 'bloqueado_ate': None, 'ultimo_erro': agora}
    else:
        TENTATIVAS_FALHAS[chave]['tentativas'] += 1
        TENTATIVAS_FALHAS[chave]['ultimo_erro'] = agora

    if TENTATIVAS_FALHAS[chave]['tentativas'] >= MAX_TENTATIVAS_FALHAS:
        TENTATIVAS_FALHAS[chave]['bloqueado_ate'] = agora + timedelta(seconds=TEMPO_BLOQUEIO_SEGUNDOS)

def limpar_falhas_login(ip, username):
    """Limpa o histórico de falhas após login bem-sucedido."""
    chave = (ip, (username or '').strip().lower())
    TENTATIVAS_FALHAS.pop(chave, None)


# --- CONTROLE DE ACESSO BASEADO EM FUNÇÃO (RBAC) ---

def admin_required(f):
    """Decorador estrito: garante que apenas administradores autenticados acessem a rota."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if current_user.role != 'admin':
            flash("Acesso não autorizado: Esta operação exige privilégios de Administrador.", "danger")
            return redirect(url_for('meus_chamados'))
        return f(*args, **kwargs)
    return decorated_function


# --- CONTROLE GLOBAL DE ACESSO, SEGURANÇA E CABEÇALHOS ---

@app.before_request
def auditoria_e_seguranca_global():
    # 1. Bloqueio estrito de acesso direto a arquivos sensíveis (banco de dados, env, git, fontes)
    path_lower = request.path.lower()
    extensoes_proibidas = ('.db', '.sqlite', '.sqlite3', '.env', '.git', '.py', '.pyc', '.bak')
    if any(path_lower.endswith(ext) or ext + '/' in path_lower for ext in extensoes_proibidas):
        return abort(403)

    # 2. Validação Anti-CSRF para requisições com alteração de estado (POST)
    if request.method == 'POST':
        if not app.config.get('TESTING'):
            token_recebido = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            token_esperado = session.get('_csrf_token')
            if not token_esperado or not token_recebido or not hmac.compare_digest(str(token_recebido), str(token_esperado)):
                flash("Falha de validação de segurança (Token CSRF inválido ou expirado). Atualize a página e tente novamente.", "danger")
                return abort(400)

    # 3. Permite requisições sem endpoint (ex: 404), arquivos estáticos ou rota de login
    if request.endpoint is None or request.endpoint in ('login', 'static'):
        return None

    # 4. Exige autenticação em todas as outras rotas do sistema
    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    # 5. Regra: troca de senha obrigatória no 1º acesso (administradores e coordenadores)
    if getattr(current_user, 'trocar_senha', 0) == 1:
        rotas_permitidas_troca = ('trocar_senha', 'logout', 'static')
        if request.endpoint not in rotas_permitidas_troca:
            flash("Primeiro Acesso: por segurança corporativa, você deve alterar sua senha padrão para continuar.", "warning")
            return redirect(url_for('trocar_senha'))

    # 6. Regra de perfil (RBAC):
    # O coordenador tem acesso estritamente restrito às suas funcionalidades
    if current_user.role == 'coordenador':
        rotas_permitidas_coordenador = ('meus_chamados', 'solicitar_equipamento', 'logout', 'static', 'download_cautela', 'trocar_senha')
        if request.endpoint not in rotas_permitidas_coordenador:
            flash("Acesso restrito: seu perfil de Coordenador permite acessar apenas Meus Chamados e Solicitação de Equipamento.", "warning")
            return redirect(url_for('meus_chamados'))


@app.after_request
def aplicar_cabecalhos_seguranca(response):
    """Aplica cabeçalhos HTTP defensivos (OWASP Top 10 Security Headers)."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    )
    if current_user.is_authenticated:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response


# --- TRATAMENTO DE ERROS PADRONIZADO E SEGURO ---

@app.errorhandler(400)
def erro_bad_request(e):
    return """<!DOCTYPE html><html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><title>400 • Requisição Inválida</title>
    <style>body{background:#050505;color:#f0f2f5;font-family:sans-serif;text-align:center;padding:80px 20px;}h1{color:#CEDC00;}</style>
    </head><body><h1>400 • Requisição Inválida</h1><p>A solicitação foi recusada por validação de segurança ou token CSRF ausente/inválido.</p>
    <p><a href="/" style="color:#CEDC00;font-weight:700;">Voltar ao Sistema</a></p></body></html>""", 400

@app.errorhandler(403)
def erro_proibido(e):
    return """<!DOCTYPE html><html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><title>403 • Acesso Negado</title>
    <style>body{background:#050505;color:#f0f2f5;font-family:sans-serif;text-align:center;padding:80px 20px;}h1{color:#ef4444;}</style>
    </head><body><h1>403 • Acesso Negado</h1><p>Você não possui privilégios para acessar este recurso ou arquivo restrito.</p>
    <p><a href="/" style="color:#CEDC00;font-weight:700;">Voltar ao Sistema</a></p></body></html>""", 403

@app.errorhandler(404)
def erro_nao_encontrado(e):
    return """<!DOCTYPE html><html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><title>404 • Não Encontrado</title>
    <style>body{background:#050505;color:#f0f2f5;font-family:sans-serif;text-align:center;padding:80px 20px;}h1{color:#CEDC00;}</style>
    </head><body><h1>404 • Recurso Não Encontrado</h1><p>A página ou registro solicitado não existe no sistema Cavere.</p>
    <p><a href="/" style="color:#CEDC00;font-weight:700;">Voltar ao Sistema</a></p></body></html>""", 404

@app.errorhandler(500)
def erro_servidor(e):
    return """<!DOCTYPE html><html lang="pt-BR" class="dark"><head><meta charset="UTF-8"><title>500 • Erro Interno</title>
    <style>body{background:#050505;color:#f0f2f5;font-family:sans-serif;text-align:center;padding:80px 20px;}h1{color:#ef4444;}</style>
    </head><body><h1>500 • Erro Interno do Sistema</h1><p>Ocorreu uma falha interna segura. Os dados foram preservados.</p>
    <p><a href="/" style="color:#CEDC00;font-weight:700;">Voltar ao Sistema</a></p></body></html>""", 500


# --- REGRAS DE CADASTRO DE USUÁRIOS E SENHAS ---

def salvar_novo_usuario(username, senha_pura, role='coordenador', id_personalizado=None, nome_completo=None, cpf_matricula=None, setor='Operações', trocar_senha=1):
    """
    Cadastra um novo usuário no banco com senha criptografada via scrypt.
    Se o papel for 'coordenador', cadastra atomicamente em 'usuarios' e 'coordenadores' com o MESMO ID.
    Valida formatos, proíbe letras na Matrícula Geral e restringe tamanho para evitar DoS.
    """
    if role not in ('admin', 'coordenador'):
        return False, "O papel (role) deve ser 'admin' ou 'coordenador'."

    username = username.strip()
    if len(username) < 3 or len(username) > 64:
        return False, "O nome de usuário deve ter entre 3 e 64 caracteres."

    if len(senha_pura) < 4 or len(senha_pura) > 128:
        return False, "A senha deve ter entre 4 e 128 caracteres."

    if role == 'coordenador':
        if not nome_completo or not cpf_matricula:
            return False, "Para cadastro de perfil Coordenador / Setor, o Nome Completo e Matrícula Geral/CPF são obrigatórios."
        nome_completo = nome_completo.strip()[:100]
        cpf_matricula = cpf_matricula.strip()[:30]
        setor = (setor or 'Operações').strip()[:50]

        # Regra Estrita: A Matrícula Geral corporativa não começa nem contém letras, é apenas números
        if re.search(r'[a-zA-Z]', cpf_matricula):
            return False, "A Matrícula Geral / CPF não pode conter letras. Informe exclusivamente dígitos numéricos."

    senha_hash = generate_password_hash(senha_pura)
    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        if id_personalizado:
            try:
                id_personalizado = int(id_personalizado)
                if id_personalizado <= 0 or id_personalizado > 1000000:
                    return False, "ID personalizado fora do intervalo permitido (1 a 1.000.000)."
            except ValueError:
                return False, "O ID personalizado deve ser um número inteiro válido."

            cursor.execute('SELECT id FROM usuarios WHERE id = ?', (id_personalizado,))
            if cursor.fetchone():
                return False, f"O ID #{id_personalizado} já está em uso na tabela de usuários."

            if role == 'coordenador':
                cursor.execute('SELECT id FROM coordenadores WHERE id = ?', (id_personalizado,))
                if cursor.fetchone():
                    return False, f"O ID #{id_personalizado} já está em uso na tabela de coordenadores."

            cursor.execute('''
                INSERT INTO usuarios (id, username, senha_hash, role, trocar_senha)
                VALUES (?, ?, ?, ?, ?)
            ''', (id_personalizado, username, senha_hash, role, trocar_senha))
            user_id = id_personalizado
        else:
            cursor.execute('''
                INSERT INTO usuarios (username, senha_hash, role, trocar_senha)
                VALUES (?, ?, ?, ?)
            ''', (username, senha_hash, role, trocar_senha))
            user_id = cursor.lastrowid

        if role == 'coordenador':
            cursor.execute('SELECT id FROM coordenadores WHERE id = ?', (user_id,))
            existe_coord = cursor.fetchone()
            if existe_coord:
                cursor.execute('''
                    UPDATE coordenadores 
                    SET nome_completo = ?, cpf_matricula = ?, setor = ?
                    WHERE id = ?
                ''', (nome_completo, cpf_matricula, setor, user_id))
            else:
                cursor.execute('''
                    INSERT INTO coordenadores (id, nome_completo, cpf_matricula, setor)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, nome_completo, cpf_matricula, setor))

        conexao.commit()
        papel_str = "Coordenador" if role == 'coordenador' else "Administrador"
        return True, f"{papel_str} '{username}' (ID #{user_id}) cadastrado com sucesso!"
    except sqlite3.IntegrityError as e:
        erro_msg = str(e)
        if 'username' in erro_msg:
            return False, f"O login '{username}' já está em uso no sistema."
        if 'cpf_matricula' in erro_msg:
            return False, f"O CPF/Matrícula '{cpf_matricula}' já está cadastrado para outro coordenador."
        return False, f"Conflito de integridade no banco: {erro_msg}"
    except Exception as e:
        return False, f"Erro ao cadastrar usuário: {e}"
    finally:
        conexao.close()


# --- ROTAS DE AUTENTICAÇÃO E USUÁRIOS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'coordenador':
            return redirect(url_for('meus_chamados'))
        return redirect(url_for('home'))

    ip_cliente = obter_ip_cliente()

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        senha = request.form.get('senha') or ''

        # Verificação de bloqueio anti-força bruta
        pode_tentar, msg_bloqueio = verificar_bloqueio_login(ip_cliente, username)
        if not pode_tentar:
            flash(msg_bloqueio, "danger")
            return render_template('login.html'), 429

        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('SELECT id, username, senha_hash, role, trocar_senha FROM usuarios WHERE username = ?', (username,))
        dados = cursor.fetchone()
        conexao.close()

        if dados and check_password_hash(dados[2], senha):
            limpar_falhas_login(ip_cliente, username)
            trocar = dados[4] if len(dados) > 4 and dados[4] is not None else 0
            usuario = Usuario(id=dados[0], username=dados[1], senha_hash=dados[2], role=dados[3], trocar_senha=trocar)
            login_user(usuario)
            flash(f"Bem-vindo ao Cavere, {usuario.username}!", "success")

            if usuario.trocar_senha == 1:
                flash("Primeiro Acesso: por segurança corporativa, você deve alterar sua senha padrão para continuar.", "warning")
                return redirect(url_for('trocar_senha'))

            if usuario.role == 'coordenador':
                return redirect(url_for('meus_chamados'))
            else:
                proxima = request.args.get('next')
                if proxima and is_safe_redirect_url(proxima):
                    return redirect(proxima)
                return redirect(url_for('home'))
        else:
            registrar_falha_login(ip_cliente, username)
            flash("Usuário ou senha inválidos. Tente novamente.", "danger")

    return render_template('login.html')


@app.route('/trocar-senha', methods=['GET', 'POST'])
@login_required
def trocar_senha():
    if request.method == 'POST':
        senha_atual = request.form.get('senha_atual', '')
        nova_senha = request.form.get('nova_senha', '').strip()
        confirmar_senha = request.form.get('confirmar_senha', '').strip()

        if not check_password_hash(current_user.senha_hash, senha_atual):
            flash("A senha atual informada está incorreta.", "danger")
            return render_template('trocar_senha.html')

        if len(nova_senha) < 4 or len(nova_senha) > 128:
            flash("A nova senha deve possuir no mínimo 4 e no máximo 128 caracteres.", "warning")
            return render_template('trocar_senha.html')

        if nova_senha == '123' or nova_senha == senha_atual:
            flash("A nova senha não pode ser a senha padrão '123' nem idêntica à senha atual.", "warning")
            return render_template('trocar_senha.html')

        if nova_senha != confirmar_senha:
            flash("A confirmação da nova senha não confere com a nova senha digitada.", "danger")
            return render_template('trocar_senha.html')

        novo_hash = generate_password_hash(nova_senha)
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('''
            UPDATE usuarios 
            SET senha_hash = ?, trocar_senha = 0 
            WHERE id = ?
        ''', (novo_hash, current_user.id))
        conexao.commit()
        conexao.close()

        current_user.senha_hash = novo_hash
        current_user.trocar_senha = 0

        if current_user.role == 'coordenador':
            flash("Senha alterada com sucesso! Bem-vindo ao painel de Meus Chamados.", "success")
            return redirect(url_for('meus_chamados'))
        else:
            flash("Senha alterada com sucesso! Seu acesso administrativo ao Cavere foi liberado.", "success")
            return redirect(url_for('home'))

    return render_template('trocar_senha.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Sessão finalizada com sucesso.", "info")
    return redirect(url_for('login'))


# --- GERAÇÃO SEGURA DE TERMOS DE CAUTELA EM PDF (Anti-XSS & Anti-SSRF) ---

def seguro_url_fetcher(url):
    """
    Bloqueia qualquer requisição externa de rede ou acesso a arquivos locais
    durante a compilação do PDF (defesa estrita contra SSRF e LFI).
    """
    raise ValueError(f"Acesso a recursos externos bloqueado por segurança: {url}")


def gerar_pdf_termo(rdo, sn, tipo, modelo, imei1, imei2, nome_coord, cpf_coord, data_str=None):
    """
    Gera e salva o PDF do Termo de Cautela na pasta Cautelas/
    Aplica escapamento HTML estrito (html.escape) em todas as variáveis para impedir XSS/SSRF
    e desativa resolução de URLs externas no WeasyPrint.
    """
    if not data_str:
        data_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    s_rdo = html.escape(str(rdo or 'N/A'))
    s_sn = html.escape(str(sn or 'N/A'))
    s_tipo = html.escape(str(tipo or 'Equipamento'))
    s_modelo = html.escape(str(modelo or 'N/A'))
    s_imei1 = html.escape(str(imei1 or 'N/A'))
    s_imei2 = html.escape(str(imei2 or 'N/A'))
    s_nome = html.escape(str(nome_coord or 'Responsável'))
    s_cpf = html.escape(str(cpf_coord or 'N/A'))
    s_data = html.escape(str(data_str or ''))

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #111; }}
            .header {{ text-align: center; border-bottom: 2px solid #005A32; padding-bottom: 10px; }}
            .header h1 {{ color: #005A32; font-size: 18pt; text-transform: uppercase; margin: 0; }}
            .section-title {{ background-color: #eef5f1; padding: 8px; font-weight: bold; margin-top: 25px; border-left: 4px solid #005A32; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #fafafa; width: 30%; }}
            .signature {{ margin-top: 60px; text-align: center; }}
            .line {{ width: 60%; border-top: 1px solid #000; margin: 0 auto 10px auto; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Termo de Cautela - Sistema Cavere</h1>
            <p>Ambipar Response - Base Niterói</p>
        </div>
        
        <p>Declaro que recebi da AMBIPAR RESPONSE, a título de cautela, o equipamento abaixo, comprometendo-me a zelar pela sua guarda e devolução após a operação.</p>
        
        <div class="section-title">Dados do Responsável</div>
        <table>
            <tr><th>Nome</th><td>{s_nome}</td></tr>
            <tr><th>CPF/Matrícula</th><td>{s_cpf}</td></tr>
            <tr><th>RDO Vinculado</th><td>{s_rdo}</td></tr>
        </table>

        <div class="section-title">Dados do Equipamento</div>
        <table>
            <tr><th>Tipo</th><td>{s_tipo}</td></tr>
            <tr><th>Modelo</th><td>{s_modelo}</td></tr>
            <tr><th>Patrimônio / SN</th><td>{s_sn}</td></tr>
            <tr><th>IMEI 1</th><td>{s_imei1}</td></tr>
            <tr><th>IMEI 2</th><td>{s_imei2}</td></tr>
        </table>
        
        <div class="signature">
            <div class="line"></div>
            <p><strong>{s_nome}</strong><br>Assinatura do Responsável<br>Data: {s_data}</p>
        </div>
    </body>
    </html>
    """
    os.makedirs('Cautelas', exist_ok=True)
    rdo_safe = re.sub(r'[^A-Za-z0-9_-]', '', str(rdo))
    sn_safe = re.sub(r'[^A-Za-z0-9_-]', '', str(sn))
    nome_arquivo = f"Cautela_{rdo_safe}_{sn_safe}.pdf"
    caminho_arquivo = os.path.join('Cautelas', nome_arquivo)
    with suprimir_warnings_glib():
        HTML(string=html_content, url_fetcher=seguro_url_fetcher).write_pdf(caminho_arquivo)
    return nome_arquivo


@app.route('/cadastrar-usuario', methods=['GET', 'POST'])
@login_required
@admin_required
def cadastrar_usuario():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        senha = request.form.get('senha', '').strip()
        role = request.form.get('role', 'coordenador')
        id_custom = request.form.get('id_custom', '').strip()
        nome_completo = request.form.get('nome_completo', '').strip()
        cpf = request.form.get('cpf', '').strip()
        setor = request.form.get('setor', 'Operações').strip()
        trocar_senha = 1 if request.form.get('trocar_senha') == '1' else 0

        if not username or not senha:
            flash("Preencha todos os campos obrigatórios (Login e Senha).", "warning")
            return render_template('cadastrar_usuario.html')

        id_param = int(id_custom) if id_custom and id_custom.isdigit() else None
        sucesso, mensagem = salvar_novo_usuario(
            username=username,
            senha_pura=senha,
            role=role,
            id_personalizado=id_param,
            nome_completo=nome_completo if role == 'coordenador' else None,
            cpf_matricula=cpf if role == 'coordenador' else None,
            setor=setor if role == 'coordenador' else 'Operações',
            trocar_senha=trocar_senha
        )
        if sucesso:
            flash(mensagem, "success")
            return redirect(url_for('home'))
        else:
            flash(mensagem, "danger")

    return render_template('cadastrar_usuario.html')


def obter_categoria_equipamento(texto):
    """Identifica a categoria padronizada do equipamento a partir do nome ou descrição."""
    if not texto:
        return 'outro'
    t = texto.lower()
    if any(k in t for k in ['celular', 'smartphone', 'telefone', 'ptt', 'iphone']):
        return 'celular'
    if any(k in t for k in ['camera', 'câmera', 'kodak', 'pixpro', 'fotogr', 'filmagem', 'gopro']):
        return 'camera'
    if any(k in t for k in ['notebook', 'laptop', 'computador', 'pc', 'macbook']):
        return 'notebook'
    if any(k in t for k in ['teclado', 'keyboard']):
        return 'teclado'
    if any(k in t for k in ['mouse']):
        return 'mouse'
    if any(k in t for k in ['monitor', 'tela', 'display']):
        return 'monitor'
    if any(k in t for k in ['headset', 'fone', 'headphone', 'auricular']):
        return 'headset'
    if any(k in t for k in ['radio', 'rádio', 'comunicador', 'vhf', 'uhf', 'ht', 'transceptor']):
        return 'radio'
    if any(k in t for k in ['tablet', 'ipad', 'rugged']):
        return 'tablet'
    if any(k in t for k in ['detector', 'multigás', 'multigas', 'gás', 'gas']):
        return 'detector'
    return 'outro'


def tipos_sao_compativeis(tipo_equip, tipo_solicitado):
    """Verifica se o tipo de equipamento físico corresponde ao solicitado no chamado."""
    if not tipo_equip or not tipo_solicitado:
        return True
    cat1 = obter_categoria_equipamento(tipo_equip)
    cat2 = obter_categoria_equipamento(tipo_solicitado)
    if cat1 != 'outro' and cat2 != 'outro':
        return cat1 == cat2
    t1 = tipo_equip.lower().strip()
    t2 = tipo_solicitado.lower().strip()
    return t1 in t2 or t2 in t1 or cat1 == cat2


# --- ROTAS PRINCIPAIS DO SISTEMA (Acesso Restrito ao Administrador) ---

@app.route('/')
@login_required
@admin_required
def home():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    
    cursor.execute('SELECT id, tipo, modelo, patrimonio_sn, imei_1, imei_2, status FROM equipamentos ORDER BY id DESC')
    equipamentos_raw = cursor.fetchall()
    equipamentos = []
    for eq in equipamentos_raw:
        equipamentos.append({
            'id': eq[0],
            'tipo': eq[1],
            'modelo': eq[2],
            'patrimonio_sn': eq[3],
            'imei_1': eq[4],
            'imei_2': eq[5],
            'status': eq[6],
            'categoria': obter_categoria_equipamento(eq[1])
        })
    
    cursor.execute('SELECT id, nome_completo, cpf_matricula FROM coordenadores ORDER BY id DESC')
    coordenadores_raw = cursor.fetchall()
    coordenadores = [{
        'id': co[0],
        'nome_completo': co[1],
        'cpf_matricula': co[2]
    } for co in coordenadores_raw]

    cursor.execute('''
        SELECT s.id, 
               COALESCE(co.nome_completo, u.username, 'Coordenador #' || s.id_coordenador) AS nome_coord,
               s.tipo_equipamento, s.quantidade, s.destinatario, 
               s.plataforma, s.rdo_projeto, s.prioridade, s.status, s.data_criacao, s.id_coordenador,
               COALESCE(s.tipo_uso, 'Operação') AS tipo_uso,
               COALESCE(s.setor, 'Operações') AS setor
        FROM solicitacoes s
        LEFT JOIN coordenadores co ON s.id_coordenador = co.id
        LEFT JOIN usuarios u ON s.id_coordenador = u.id
        ORDER BY s.id DESC
    ''')
    solicitacoes_raw = cursor.fetchall()

    solicitacoes = []
    for s in solicitacoes_raw:
        id_sol = s[0]
        qtd_total = s[3]
        
        cursor.execute('''
            SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn, c.data_hora_saida, c.data_hora_devolucao
            FROM cautelas c
            JOIN equipamentos e ON c.id_equipamento = e.id
            WHERE c.id_solicitacao = ?
            ORDER BY c.id_cautela ASC
        ''', (id_sol,))
        itens_raw = cursor.fetchall()
        
        itens_emitidos = []
        for it in itens_raw:
            itens_emitidos.append({
                'id_cautela': it[0],
                'tipo': it[1],
                'modelo': it[2],
                'patrimonio_sn': it[3],
                'data_saida': it[4],
                'devolvido': bool(it[5]),
                'data_devolucao': it[5]
            })
        
        status_atual = s[8]
        is_finalizada = status_atual in ('Finalizada', 'Concluído', 'Concluido', 'Finalizado', 'Devolvido')
        
        itens_ativos = [it for it in itens_emitidos if not it['devolvido']]
        itens_devolvidos = [it for it in itens_emitidos if it['devolvido']]

        if is_finalizada:
            qtd_emitida = len(itens_emitidos)
            qtd_restante = 0
        else:
            qtd_emitida = len(itens_ativos)
            qtd_restante = max(0, qtd_total - qtd_emitida)
            if qtd_emitida >= qtd_total and qtd_total > 0:
                status_atual = 'Esperando Entrega'
            elif qtd_emitida > 0:
                status_atual = 'Em Atendimento'
            else:
                status_atual = 'Pendente'

        solicitacoes.append({
            'id': id_sol,
            'nome_coord': s[1],
            'tipo_equipamento': s[2],
            'categoria': obter_categoria_equipamento(s[2]),
            'quantidade_total': qtd_total,
            'destinatario': s[4],
            'plataforma': s[5],
            'rdo': s[6] or '-',
            'prioridade': s[7],
            'status': status_atual,
            'data_criacao': s[9],
            'id_coordenador': s[10],
            'tipo_uso': s[11] if len(s) > 11 else 'Operação',
            'setor': s[12] if len(s) > 12 else 'Operações',
            'itens_emitidos': itens_ativos if not is_finalizada else itens_emitidos,
            'itens_devolvidos': itens_devolvidos,
            'qtd_emitida': qtd_emitida,
            'qtd_restante': qtd_restante,
            'concluida': is_finalizada or (qtd_emitida >= qtd_total and qtd_total > 0)
        })

    cursor.execute('''
        SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn,
               COALESCE(co.nome_completo, u.username, 'Coordenador #' || c.id_coordenador) AS nome_coord,
               c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao,
               e.id AS id_equipamento, c.id_solicitacao
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        LEFT JOIN usuarios u ON c.id_coordenador = u.id
        ORDER BY c.id_cautela DESC
    ''')
    cautelas_raw = cursor.fetchall()
    cautelas = []
    for cr in cautelas_raw:
        cautelas.append({
            'id': cr[0],
            'tipo': cr[1] or 'Equipamento',
            'modelo': cr[2] or '',
            'patrimonio_sn': cr[3] or '',
            'coordenador': cr[4] or 'N/A',
            'rdo': cr[5] or 'N/A',
            'data_saida': cr[6] or '',
            'data_devolucao': cr[7],
            'id_equipamento': cr[8],
            'id_solicitacao': cr[9],
            'status': 'Devolvido' if cr[7] else 'Em Campo',
            'pdf_nome': f"Cautela_{cr[5]}_{cr[3]}.pdf" if cr[5] and cr[3] else None
        })
    
    conexao.close()
    return render_template('index.html', 
                           equipamentos=equipamentos, 
                           coordenadores=coordenadores, 
                           solicitacoes=solicitacoes,
                           cautelas=cautelas)


@app.route('/gerar', methods=['POST'])
@login_required
@admin_required
def gerar():
    id_equipamento = request.form.get('id_equipamento')
    id_coordenador = request.form.get('id_coordenador')
    rdo = request.form.get('rdo', '').strip()
    id_solicitacao = request.form.get('id_solicitacao', '').strip()

    if not id_equipamento or not id_coordenador or not rdo:
        flash("Por favor, selecione o Equipamento, o Coordenador e informe o RDO.", "warning")
        return redirect(url_for('home'))

    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute('SELECT tipo, modelo, patrimonio_sn, imei_1, imei_2, status FROM equipamentos WHERE id = ?', (id_equipamento,))
        equip = cursor.fetchone()
        
        cursor.execute('SELECT id, nome_completo, cpf_matricula FROM coordenadores WHERE id = ?', (id_coordenador,))
        coord = cursor.fetchone()

        if not coord:
            cursor.execute('SELECT id, username FROM usuarios WHERE id = ?', (id_coordenador,))
            user_row = cursor.fetchone()
            if user_row:
                cursor.execute('SELECT id, nome_completo, cpf_matricula FROM coordenadores WHERE LOWER(nome_completo) = LOWER(?)', (user_row[1],))
                coord = cursor.fetchone()
                if not coord:
                    nome_padrao = user_row[1].replace('.', ' ').title()
                    cursor.execute('INSERT INTO coordenadores (id, nome_completo, cpf_matricula) VALUES (?, ?, ?)',
                                   (user_row[0], nome_padrao, f"MAT-{user_row[0]}"))
                    conexao.commit()
                    coord = (user_row[0], nome_padrao, f"MAT-{user_row[0]}")
                    id_coordenador = user_row[0]
                else:
                    id_coordenador = coord[0]

        if not equip:
            flash("Erro: Equipamento selecionado não foi encontrado.", "danger")
            return redirect(url_for('home'))

        if not coord:
            flash("Erro: Coordenador selecionado não foi encontrado no sistema.", "danger")
            return redirect(url_for('home'))

        tipo, modelo, sn, imei1, imei2, status_equip = equip
        coord_id, nome_coord, cpf_coord = coord
        id_sol_int = int(id_solicitacao) if id_solicitacao and id_solicitacao.isdigit() else None

        if id_sol_int:
            cursor.execute('SELECT tipo_equipamento, quantidade FROM solicitacoes WHERE id = ?', (id_sol_int,))
            sol_row = cursor.fetchone()
            if sol_row:
                tipo_pedido, qtd_pedida = sol_row
                if not tipos_sao_compativeis(tipo, tipo_pedido):
                    flash(f"Equipamento recusado! A solicitação #SOL-{id_sol_int} exige '{tipo_pedido}', mas você selecionou '{tipo} ({modelo})'.", "danger")
                    return redirect(url_for('home'))

        cursor.execute('''
            INSERT INTO cautelas (id_equipamento, id_coordenador, rdo_vinculado, id_solicitacao) 
            VALUES (?, ?, ?, ?)
        ''', (id_equipamento, id_coordenador, rdo, id_sol_int))
        
        cursor.execute("UPDATE equipamentos SET status = 'Em Operação' WHERE id = ?", (id_equipamento,))

        msg_progresso = ""
        if id_sol_int:
            cursor.execute('SELECT COUNT(*) FROM cautelas WHERE id_solicitacao = ? AND data_hora_devolucao IS NULL', (id_sol_int,))
            total_emitidos = cursor.fetchone()[0]
            cursor.execute('SELECT quantidade FROM solicitacoes WHERE id = ?', (id_sol_int,))
            row_q = cursor.fetchone()
            qtd_solicitada = row_q[0] if row_q else 1

            if total_emitidos >= qtd_solicitada:
                cursor.execute("UPDATE solicitacoes SET status = 'Esperando Entrega' WHERE id = ?", (id_sol_int,))
                msg_progresso = f"Todos os {qtd_solicitada} itens solicitados foram emitidos! O chamado agora está 'Esperando Entrega'."
            else:
                cursor.execute("UPDATE solicitacoes SET status = 'Em Atendimento' WHERE id = ?", (id_sol_int,))
                faltam = qtd_solicitada - total_emitidos
                msg_progresso = f"Item {total_emitidos} de {qtd_solicitada} emitido com sucesso! Faltam {faltam} item(ns)."
        else:
            msg_progresso = "Cautela gerada com sucesso."

        conexao.commit()
        gerar_pdf_termo(rdo, sn, tipo, modelo, imei1, imei2, nome_coord, cpf_coord)
        flash(f"Termo gerado com sucesso para {nome_coord} ({tipo} {modelo} - SN: {sn})! {msg_progresso}", "success")
        
    except Exception as e:
        flash(f"Erro ao gerar cautela: {e}", "danger")
    finally:
        conexao.close()

    return redirect(url_for('home'))


@app.route('/solicitacao/entregar/<int:id_solicitacao>', methods=['POST'])
@login_required
@admin_required
def entregar_solicitacao(id_solicitacao):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute("UPDATE solicitacoes SET status = 'Finalizada' WHERE id = ?", (id_solicitacao,))
        conexao.commit()
        flash(f"Equipamento da solicitação #SOL-{id_solicitacao} marcado como entregue! Chamado finalizado.", "success")
    except Exception as e:
        flash(f"Erro ao finalizar solicitação: {e}", "danger")
    finally:
        conexao.close()
    return redirect(url_for('home'))


@app.route('/novo-equipamento')
@login_required
@admin_required
def novo_equipamento():
    return render_template('cadastrar_equipamento.html')


@app.route('/salvar-equipamento', methods=['POST'])
@login_required
@admin_required
def salvar_equipamento():
    tipo = (request.form.get('tipo') or '').strip()[:60]
    modelo = (request.form.get('modelo') or '').strip()[:80]
    patrimonio = (request.form.get('patrimonio') or '').strip()[:60]
    imei1 = (request.form.get('imei1') or '').strip()[:30]
    imei2 = (request.form.get('imei2') or '').strip()[:30]
    
    if not tipo or not modelo or not patrimonio:
        flash("Preencha todos os campos obrigatórios do equipamento.", "warning")
        return redirect(url_for('novo_equipamento'))

    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute('''
            INSERT INTO equipamentos (tipo, modelo, patrimonio_sn, imei_1, imei_2, status)
            VALUES (?, ?, ?, ?, ?, 'Disponível')
        ''', (tipo, modelo, patrimonio, imei1, imei2))
        conexao.commit()
        flash(f"Equipamento '{tipo} - {modelo}' cadastrado com sucesso!", "success")
    except sqlite3.IntegrityError:
        flash(f"Erro: O número de patrimônio/SN '{patrimonio}' já está cadastrado no sistema.", "danger")
    except Exception as e:
        flash(f"Erro ao cadastrar equipamento: {e}", "danger")
    finally:
        conexao.close()
        
    return redirect(url_for('home'))


@app.route('/novo-coordenador')
@login_required
@admin_required
def novo_coordenador():
    flash("O cadastro de coordenadores foi unificado à criação de login. Cadastre o coordenador abaixo.", "info")
    return redirect(url_for('cadastrar_usuario'))


@app.route('/salvar-coordenador', methods=['POST'])
@login_required
@admin_required
def salvar_coordenador():
    return redirect(url_for('cadastrar_usuario'))


@app.route('/devolver/<int:id_equipamento>', methods=['POST'])
@login_required
@admin_required
def devolver(id_equipamento):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute('''
            SELECT id_cautela, id_solicitacao 
            FROM cautelas 
            WHERE id_equipamento = ? AND data_hora_devolucao IS NULL
        ''', (id_equipamento,))
        cautela_info = cursor.fetchone()

        cursor.execute("UPDATE equipamentos SET status = 'Disponível' WHERE id = ?", (id_equipamento,))
        
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            UPDATE cautelas 
            SET data_hora_devolucao = ? 
            WHERE id_equipamento = ? AND data_hora_devolucao IS NULL
        ''', (agora, id_equipamento))
        
        msg_solicitacao = ""
        if cautela_info and cautela_info[1]:
            id_sol = cautela_info[1]
            cursor.execute('SELECT status, quantidade FROM solicitacoes WHERE id = ?', (id_sol,))
            sol_row = cursor.fetchone()
            if sol_row:
                status_sol, qtd_pedida = sol_row
                if status_sol not in ('Finalizada', 'Concluído', 'Finalizado', 'Devolvido'):
                    cursor.execute('''
                        SELECT COUNT(*) FROM cautelas 
                        WHERE id_solicitacao = ? AND data_hora_devolucao IS NULL
                    ''', (id_sol,))
                    ativas_restantes = cursor.fetchone()[0]

                    if ativas_restantes == 0:
                        novo_status = 'Pendente'
                    elif ativas_restantes < qtd_pedida:
                        novo_status = 'Em Atendimento'
                    else:
                        novo_status = 'Esperando Entrega'

                    cursor.execute('UPDATE solicitacoes SET status = ? WHERE id = ?', (novo_status, id_sol))
                    faltam_agora = max(0, qtd_pedida - ativas_restantes)
                    msg_solicitacao = f" Solicitação #SOL-{id_sol} recalculada: {ativas_restantes}/{qtd_pedida} ativos (status '{novo_status}')."

        conexao.commit()
        flash(f"Equipamento devolvido com sucesso! Status atualizado para Disponível.{msg_solicitacao}", "success")
    except Exception as e:
        flash(f"Erro ao devolver equipamento: {e}", "danger")
    finally:
        conexao.close()
    return redirect(url_for('home'))


@app.route('/historico')
@login_required
@admin_required
def historico():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn,
               COALESCE(co.nome_completo, u.username, 'Coordenador #' || c.id_coordenador) AS nome_coord,
               c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao,
               e.id AS id_equipamento, c.id_solicitacao
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        LEFT JOIN usuarios u ON c.id_coordenador = u.id
        ORDER BY c.id_cautela DESC
    ''')
    cautelas_raw = cursor.fetchall()
    conexao.close()

    cautelas = []
    contadores = {'Total': 0, 'Em Campo': 0, 'Devolvido': 0}
    for cr in cautelas_raw:
        st = 'Devolvido' if cr[7] else 'Em Campo'
        contadores['Total'] += 1
        contadores[st] += 1
        cautelas.append({
            'id': cr[0],
            'tipo': cr[1] or 'Equipamento',
            'modelo': cr[2] or '',
            'patrimonio_sn': cr[3] or '',
            'coordenador': cr[4] or 'N/A',
            'rdo': cr[5] or 'N/A',
            'data_saida': cr[6] or '',
            'data_devolucao': cr[7],
            'id_equipamento': cr[8],
            'id_solicitacao': cr[9],
            'status': st,
            'pdf_nome': f"Cautela_{cr[5]}_{cr[3]}.pdf" if cr[5] and cr[3] else None
        })
    
    return render_template('historico.html', cautelas=cautelas, contadores=contadores)


# --- ROTA DE DOWNLOAD SEGURO DE CAUTELAS (Anti-Path-Traversal & Anti-IDOR) ---

PADRAO_NOME_CAUTELA = re.compile(r'^Cautela_[A-Za-z0-9_\-.]+\.pdf$')

@app.route('/cautelas/<path:filename>')
@login_required
def download_cautela(filename):
    # 1. Prevenção estrita de Path Traversal
    nome_seguro = secure_filename(os.path.basename(filename))
    if not PADRAO_NOME_CAUTELA.match(nome_seguro) or '..' in filename or '/' in filename or '\\' in filename:
        return abort(403)

    # 2. Prevenção estrita de IDOR: Coordenador só pode baixar termos pertencentes ao seu usuário
    if current_user.role == 'coordenador':
        partes = nome_seguro.replace("Cautela_", "").replace(".pdf", "").rsplit("_", 1)
        if len(partes) == 2:
            rdo_busca, sn_busca = partes[0], partes[1]
            conexao = get_db_connection()
            cursor = conexao.cursor()
            cursor.execute('''
                SELECT c.id_coordenador 
                FROM cautelas c
                LEFT JOIN equipamentos e ON c.id_equipamento = e.id
                WHERE (c.rdo_vinculado = ? OR e.patrimonio_sn = ?)
            ''', (rdo_busca, sn_busca))
            rows = cursor.fetchall()
            conexao.close()
            
            if not rows:
                flash("Acesso não autorizado: Termo de cautela não encontrado ou não pertence a você.", "danger")
                return abort(403)

            ids_permitidos = [r[0] for r in rows]
            if current_user.id not in ids_permitidos:
                flash("Acesso negado: Você não tem autorização para baixar termos emitidos para outros coordenadores.", "danger")
                return abort(403)
        else:
            return abort(403)

    caminho_dir = os.path.abspath('Cautelas')
    caminho_completo = os.path.join(caminho_dir, nome_seguro)

    # Auto-regeneração segura caso o PDF ainda não exista em disco
    if not os.path.exists(caminho_completo):
        try:
            partes = nome_seguro.replace("Cautela_", "").replace(".pdf", "").rsplit("_", 1)
            if len(partes) == 2:
                rdo_busca, sn_busca = partes[0], partes[1]
                conexao = get_db_connection()
                cursor = conexao.cursor()
                cursor.execute('''
                    SELECT e.tipo, e.modelo, e.patrimonio_sn, e.imei_1, e.imei_2,
                           COALESCE(co.nome_completo, u.username, 'Responsável') AS nome_coord,
                           COALESCE(co.cpf_matricula, 'N/A') AS cpf_coord,
                           c.rdo_vinculado, c.data_hora_saida
                    FROM cautelas c
                    LEFT JOIN equipamentos e ON c.id_equipamento = e.id
                    LEFT JOIN coordenadores co ON c.id_coordenador = co.id
                    LEFT JOIN usuarios u ON c.id_coordenador = u.id
                    WHERE (c.rdo_vinculado = ? OR e.patrimonio_sn = ?)
                    ORDER BY c.id_cautela DESC LIMIT 1
                ''', (rdo_busca, sn_busca))
                row = cursor.fetchone()
                conexao.close()
                if row:
                    tipo, modelo, sn, imei1, imei2, nome_coord, cpf_coord, rdo, dt_saida = row
                    gerar_pdf_termo(rdo or rdo_busca, sn or sn_busca, tipo or 'Equipamento', modelo or '', imei1, imei2, nome_coord, cpf_coord, dt_saida)
        except Exception as e:
            print(f"Aviso seguro: Falha ao auto-regenerar PDF {nome_seguro}: {e}")

    if os.path.exists(caminho_completo):
        return send_from_directory(caminho_dir, nome_seguro)

    flash(f"O termo em PDF '{nome_seguro}' não foi encontrado.", "warning")
    return redirect(url_for('meus_chamados') if current_user.role == 'coordenador' else url_for('home'))


# --- ROTAS DO COORDENADOR ---

@app.route('/meus-chamados')
@login_required
def meus_chamados():
    conexao = get_db_connection()
    cursor = conexao.cursor()

    id_coordenador = current_user.id
    cursor.execute('''
        SELECT id, nome_completo FROM coordenadores 
        WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
    ''', (current_user.id, current_user.username, current_user.username))
    coord_row = cursor.fetchone()
    nome_exibicao = current_user.username
    if coord_row:
        id_coordenador = coord_row[0]
        nome_exibicao = coord_row[1]

    cursor.execute('''
        SELECT id, tipo_equipamento, quantidade, destinatario, plataforma,
               rdo_projeto, data_necessidade, prioridade, justificativa, status, data_criacao,
               COALESCE(tipo_uso, 'Operação') AS tipo_uso,
               COALESCE(setor, 'Operações') AS setor
        FROM solicitacoes
        WHERE id_coordenador = ? OR id_coordenador = ?
        ORDER BY id DESC
    ''', (id_coordenador, current_user.id))
    solicitacoes_rows = cursor.fetchall()

    cursor.execute('''
        SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn, co.nome_completo,
                c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao, e.status, c.observacoes
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        WHERE c.id_coordenador = ? OR c.id_coordenador = ?
        ORDER BY c.id_cautela DESC
    ''', (id_coordenador, current_user.id))
    registros_cautelas = cursor.fetchall()

    contadores = {'Pendente': 0, 'Esperando Entrega': 0, 'Em Operação': 0, 'Finalizada': 0, 'Devolvido': 0, 'Total': 0}

    solicitacoes = []
    for s in solicitacoes_rows:
        id_sol, tipo_eq, qtd, dest, plat, rdo_proj, dt_nec, prio, just, st, dt_cria, tipo_uso, setor = s

        cursor.execute('''
            SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn, c.data_hora_saida, c.data_hora_devolucao
            FROM cautelas c
            JOIN equipamentos e ON c.id_equipamento = e.id
            WHERE c.id_solicitacao = ?
            ORDER BY c.id_cautela ASC
        ''', (id_sol,))
        itens_raw = cursor.fetchall()
        itens_emitidos = [{
            'id_cautela': it[0],
            'tipo': it[1],
            'modelo': it[2],
            'patrimonio_sn': it[3],
            'data_saida': it[4],
            'devolvido': bool(it[5]),
            'data_devolucao': it[5]
        } for it in itens_raw]

        is_finalizada = st in ('Devolvido', 'Concluído', 'Finalizado', 'Finalizada')
        itens_ativos = [it for it in itens_emitidos if not it['devolvido']]
        itens_devolvidos = [it for it in itens_emitidos if it['devolvido']]

        if is_finalizada:
            qtd_emitida = len(itens_emitidos)
            qtd_restante = 0
            st_label = 'Finalizada'
            badge_class = 'bg-success'
            timeline_step = 3
        else:
            qtd_emitida = len(itens_ativos)
            qtd_restante = max(0, qtd - qtd_emitida)

            if qtd_emitida >= qtd and qtd > 0:
                st_label = 'Esperando Entrega'
                badge_class = 'bg-warning text-dark'
                timeline_step = 2
            elif qtd_emitida > 0:
                st_label = 'Em Operação'
                badge_class = 'bg-primary'
                timeline_step = 2
            else:
                st_label = 'Pendente'
                badge_class = 'bg-secondary'
                timeline_step = 1

        if st_label not in contadores:
            contadores[st_label] = 0
        contadores[st_label] += 1
        contadores['Total'] += 1

        solicitacoes.append({
            'id': id_sol,
            'tipo': tipo_eq,
            'quantidade': qtd,
            'destinatario': dest,
            'plataforma': plat,
            'rdo': rdo_proj or 'N/A',
            'data_necessidade': dt_nec or 'Imediato',
            'prioridade': prio or 'Normal',
            'justificativa': just or '',
            'status': st_label,
            'badge_class': badge_class,
            'timeline_step': timeline_step,
            'data_criacao': dt_cria,
            'tipo_uso': tipo_uso,
            'setor': setor,
            'itens_emitidos': itens_ativos if not is_finalizada else itens_emitidos,
            'itens_devolvidos': itens_devolvidos,
            'qtd_emitida': qtd_emitida,
            'qtd_restante': qtd_restante
        })

    conexao.close()

    chamados = []
    for reg in registros_cautelas:
        id_cautela, tipo, modelo, patrimonio_sn, nome_coord, rdo, data_saida, data_devolucao, status_equip, obs = reg

        if data_devolucao:
            status = 'Devolvido'
            badge_class = 'bg-success'
            timeline_step = 3
        elif status_equip == 'Pendente' or not data_saida:
            status = 'Pendente'
            badge_class = 'bg-warning text-dark'
            timeline_step = 1
        else:
            status = 'Em Operação'
            badge_class = 'bg-primary'
            timeline_step = 2

        if status not in contadores:
            contadores[status] = 0
        contadores[status] += 1
        contadores['Total'] += 1

        chamados.append({
            'id': id_cautela,
            'tipo': tipo or 'Equipamento',
            'modelo': modelo or 'N/A',
            'patrimonio_sn': patrimonio_sn or 'N/A',
            'coordenador': nome_coord or nome_exibicao,
            'rdo': rdo or 'N/A',
            'data_saida': data_saida or 'Aguardando liberação',
            'data_devolucao': data_devolucao,
            'status': status,
            'badge_class': badge_class,
            'timeline_step': timeline_step,
            'pdf_nome': f"Cautela_{rdo}_{patrimonio_sn}.pdf" if rdo and patrimonio_sn else None
        })

    return render_template(
        'meus_chamados.html',
        chamados=chamados,
        solicitacoes=solicitacoes,
        id_coordenador=id_coordenador,
        nome_coordenador=nome_exibicao,
        contadores=contadores
    )


@app.route('/solicitar-equipamento', methods=['GET', 'POST'])
@login_required
def solicitar_equipamento():
    conexao = get_db_connection()
    cursor = conexao.cursor()

    id_coordenador = current_user.id
    cursor.execute('''
        SELECT id, nome_completo, COALESCE(setor, 'Operações') FROM coordenadores 
        WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
    ''', (current_user.id, current_user.username, current_user.username))
    coord_row = cursor.fetchone()
    nome_coordenador = current_user.username
    setor_padrao = 'Operações'
    if coord_row:
        id_coordenador = coord_row[0]
        nome_coordenador = coord_row[1]
        setor_padrao = coord_row[2] if len(coord_row) > 2 and coord_row[2] else 'Operações'
    else:
        # Se for um usuário sem registro na tabela de coordenadores (ex: admin), cadastra para respeitar FK
        cursor.execute('SELECT id FROM coordenadores WHERE id = ?', (current_user.id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO coordenadores (id, nome_completo, cpf_matricula, setor)
                VALUES (?, ?, ?, 'TI (Tecnologia da Informação)')
            ''', (current_user.id, current_user.username, f"ADM{current_user.id:06d}"))
            conexao.commit()
        id_coordenador = current_user.id
        nome_coordenador = current_user.username
        setor_padrao = 'TI (Tecnologia da Informação)'

    if request.method == 'POST':
        tipos = request.form.getlist('tipo_equipamento') or request.form.getlist('tipo_equipamento[]')
        quantidades = request.form.getlist('quantidade') or request.form.getlist('quantidade[]')
        destinatario = (request.form.get('destinatario') or '').strip()[:100]
        tipo_uso = (request.form.get('tipo_uso') or 'Operação').strip()[:30]
        setor = (request.form.get('setor') or setor_padrao).strip()[:50]
        plataforma = (request.form.get('plataforma') or '').strip()[:100]
        
        # Quando marcada a opção de ficar na base, não há RDO/Projeto associado
        if tipo_uso == 'Base':
            rdo = ''
        else:
            rdo = (request.form.get('rdo_projeto') or '').strip()[:60]

        data_necessidade = (request.form.get('data_necessidade') or '').strip()[:30]
        prioridade = (request.form.get('prioridade') or 'Normal').strip()[:20]
        justificativa = (request.form.get('justificativa') or '').strip()[:500]

        itens_solicitados = []
        for t, q in zip(tipos, quantidades):
            t_clean = (t or '').strip()[:100]
            try:
                q_int = int(q)
            except (ValueError, TypeError):
                q_int = 1
            if t_clean and q_int > 0:
                if q_int > 100:
                    q_int = 100
                itens_solicitados.append((t_clean, q_int))

        if not itens_solicitados or not destinatario or not plataforma:
            destino_txt = "unidade operacional" if tipo_uso == 'Operação' else "local/base"
            flash(f"Por favor, adicione ao menos um tipo de equipamento válido, informe o destinatário e o destino ({destino_txt}).", "warning")
            conexao.close()
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao)

        try:
            ids_criados = []
            resumo_itens = []
            for tipo_item, qtd_item in itens_solicitados:
                cursor.execute('''
                    INSERT INTO solicitacoes (id_coordenador, tipo_equipamento, quantidade, destinatario, plataforma, rdo_projeto, data_necessidade, prioridade, justificativa, status, tipo_uso, setor)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', ?, ?)
                ''', (id_coordenador, tipo_item, qtd_item, destinatario, plataforma, rdo, data_necessidade, prioridade, justificativa, tipo_uso, setor))
                ids_criados.append(cursor.lastrowid)
                resumo_itens.append(f"{qtd_item}x {tipo_item}")

            conexao.commit()

            if len(ids_criados) == 1:
                flash(f"Chamado #{ids_criados[0]} criado com sucesso! Solicitação de {resumo_itens[0]} ({tipo_uso} - {setor}) registrada.", "success")
            else:
                ids_str = ", ".join([f"#{i}" for i in ids_criados])
                itens_str = ", ".join(resumo_itens)
                flash(f"{len(ids_criados)} chamados criados com sucesso ({ids_str})! Itens solicitados: {itens_str} ({tipo_uso} - {setor}).", "success")

            conexao.close()
            return redirect(url_for('meus_chamados'))
        except Exception as e:
            flash(f"Erro ao registrar chamado(s): {e}", "danger")
            conexao.close()
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao)

    conexao.close()
    return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao)


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    porta = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    app.run(debug=debug_mode, host=host, port=porta)