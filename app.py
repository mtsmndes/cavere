# Sistema Cavere - Gestão e Controle de Cautelas - Ambipar Industrial
import os
import sys
import sqlite3
import html
import re
import base64
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
from pydantic import BaseModel, Field, ValidationError
from notificacoes_email import agendar_notificacao_solicitacao

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
    from weasyprint.urls import URLFetcherResponse

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
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

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
    Valida estritamente se o destino de redirecionamento é uma URL relativa interna
    ou pertence ao mesmo host da aplicação, evitando vulnerabilidades de Open Redirect.
    """
    if not target or not isinstance(target, str):
        return False
    target = target.strip()
    if target.startswith('\\') or target.startswith('//') or target.startswith('/\\'):
        return False
    parsed = urlsplit(target)
    if parsed.scheme == '' and parsed.netloc == '' and target.startswith('/'):
        return True
    if hasattr(request, 'host') and parsed.netloc == request.host and parsed.scheme in ('http', 'https'):
        return True
    return False

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


# --- ESQUEMAS DE VALIDAÇÃO DE DADOS (Pydantic / Schema Hardening - OWASP A03 / IEC 62443) ---

class LoginSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    senha: str = Field(..., min_length=1, max_length=128)

class TrocarSenhaSchema(BaseModel):
    senha_atual: str = Field(..., min_length=1, max_length=128)
    nova_senha: str = Field(..., min_length=4, max_length=128)
    confirmar_senha: str = Field(..., min_length=4, max_length=128)

class EquipamentoSchema(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=60)
    modelo: str = Field(..., min_length=1, max_length=100)
    patrimonio_sn: str = Field(default='', max_length=100)
    imei_1: str = Field(default='', max_length=30)
    imei_2: str = Field(default='', max_length=30)
    base: str = Field(default='Tank', max_length=50)
    alugado: int = Field(default=0, ge=0, le=1)
    empresa_locadora: str = Field(default='', max_length=100)

class SolicitacaoItemSchema(BaseModel):
    tipo: str = Field(..., min_length=1, max_length=80)
    quantidade: int = Field(..., ge=1, le=50)

class NovoUsuarioSchema(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    senha: str = Field(..., min_length=4, max_length=128)
    role: str = Field(default='coordenador', pattern=r'^(admin|coordenador)$')
    nome_completo: str = Field(default='', max_length=100)
    base: str = Field(default='Tank', max_length=50)
    setor: str = Field(default='Operações', max_length=50)

def validate_schema(model_cls, data):
    """Valida dados de entrada contra um modelo Pydantic e retorna (objeto, None) ou (None, erro_str)."""
    try:
        instance = model_cls(**data)
        return instance, None
    except ValidationError as e:
        primeiro_erro = e.errors()[0]
        campo = primeiro_erro.get('loc', [''])[0]
        msg = f"Campo '{campo}': {primeiro_erro.get('msg', 'inválido')}"
        return None, msg


# --- CAMADA CENTRALIZADA DE BANCO DE DADOS (SQLite Hardening) ---

def get_db_connection():
    """
    Retorna uma conexão SQLite com modo WAL, chaves estrangeiras ativadas
    e timeout estendido para alta concorrência e integridade referencial.
    """
    conn = sqlite3.connect('Cavere.db', timeout=15.0)
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.execute('PRAGMA busy_timeout = 15000;')
    conn.execute('PRAGMA synchronous = NORMAL;')
    return conn


# Modelo de Usuário para autenticação
class Usuario(UserMixin):
    def __init__(self, id, username, senha_hash, role, trocar_senha=0, base=None, setor='', nome_completo=''):
        self.id = id
        self.username = username
        self.senha_hash = senha_hash
        self.role = role
        self.trocar_senha = trocar_senha
        self.base = base or 'Tank'
        self.setor = setor or ''
        self.nome_completo = nome_completo or username

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def base_nome(self):
        b = getattr(self, 'base', None)
        if not b:
            return 'Tank (Niterói)'
        b_clean = str(b).strip()
        b_lower = b_clean.lower()
        if b_lower in ('tank', 'niterói', 'niteroi'):
            return 'Tank (Niterói)'
        return b_clean


@login_manager.user_loader
def load_user(user_id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        SELECT u.id, u.username, u.senha_hash, u.role, u.trocar_senha, c.base, c.setor, c.nome_completo
        FROM usuarios u
        LEFT JOIN coordenadores c ON c.id = u.id
        WHERE u.id = ?
    ''', (user_id,))
    dados = cursor.fetchone()
    if not dados:
        conexao.close()
        return None

    trocar = dados[4] if len(dados) > 4 and dados[4] is not None else 0
    base_user = dados[5]
    setor_user = dados[6] or ''
    nome_user = dados[7] or dados[1]

    # Fallback caso a base não esteja ligada diretamente pelo ID
    if not base_user:
        cursor.execute('''
            SELECT base, setor, nome_completo 
            FROM coordenadores 
            WHERE LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
            LIMIT 1
        ''', (dados[1], dados[1]))
        fb = cursor.fetchone()
        if fb:
            base_user = fb[0]
            if fb[1]: setor_user = fb[1]
            if fb[2]: nome_user = fb[2]

    conexao.close()
    return Usuario(
        id=dados[0],
        username=dados[1],
        senha_hash=dados[2],
        role=dados[3],
        trocar_senha=trocar,
        base=base_user or 'Tank',
        setor=setor_user,
        nome_completo=nome_user
    )


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
            status TEXT DEFAULT 'Disponível',
            base TEXT DEFAULT 'Tank',
            alugado INTEGER DEFAULT 0,
            empresa_locadora TEXT DEFAULT '',
            processador TEXT DEFAULT '',
            memoria_ram TEXT DEFAULT '',
            armazenamento TEXT DEFAULT '',
            sistema_operacional TEXT DEFAULT '',
            especificacoes TEXT DEFAULT ''
        )
    ''')

    # Tabela para coordenadores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coordenadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_completo TEXT NOT NULL,
            cpf_matricula TEXT UNIQUE NOT NULL,
            setor TEXT DEFAULT 'Operações',
            cpf TEXT DEFAULT '',
            matricula TEXT DEFAULT '',
            email TEXT DEFAULT '',
            celular TEXT DEFAULT '',
            base TEXT DEFAULT 'Tank'
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
            base TEXT DEFAULT '',
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(id_coordenador) REFERENCES coordenadores(id)
        )
    ''')
    
    # Migrações seguras de colunas caso o banco já exista
    cursor.execute("PRAGMA table_info(equipamentos)")
    colunas_equip = [col[1] for col in cursor.fetchall()]
    if colunas_equip:
        if 'base' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN base TEXT DEFAULT 'Tank'")
        if 'alugado' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN alugado INTEGER DEFAULT 0")
        if 'empresa_locadora' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN empresa_locadora TEXT DEFAULT ''")
        if 'processador' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN processador TEXT DEFAULT ''")
        if 'memoria_ram' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN memoria_ram TEXT DEFAULT ''")
        if 'armazenamento' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN armazenamento TEXT DEFAULT ''")
        if 'sistema_operacional' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN sistema_operacional TEXT DEFAULT ''")
        if 'especificacoes' not in colunas_equip:
            cursor.execute("ALTER TABLE equipamentos ADD COLUMN especificacoes TEXT DEFAULT ''")

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
        if 'base' not in colunas_solicitacoes:
            cursor.execute("ALTER TABLE solicitacoes ADD COLUMN base TEXT DEFAULT ''")

    cursor.execute("PRAGMA table_info(coordenadores)")
    colunas_coord = [col[1] for col in cursor.fetchall()]
    if colunas_coord:
        if 'base' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN base TEXT DEFAULT 'Tank'")
        if 'setor' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN setor TEXT DEFAULT 'Operações'")
        if 'cpf' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN cpf TEXT DEFAULT ''")
        if 'matricula' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN matricula TEXT DEFAULT ''")
        if 'email' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN email TEXT DEFAULT ''")
        if 'celular' not in colunas_coord:
            cursor.execute("ALTER TABLE coordenadores ADD COLUMN celular TEXT DEFAULT ''")

        # Backfill retrocompatível se houver registros antigos
        cursor.execute("SELECT id, cpf_matricula, cpf, matricula FROM coordenadores")
        for c_id, cm, cp, mt in cursor.fetchall():
            if (not cp or not mt) and cm:
                cm_str = str(cm).strip()
                if not mt and (cm_str.isdigit() and len(cm_str) < 9 or 'ADM' in cm_str):
                    cursor.execute("UPDATE coordenadores SET matricula = ? WHERE id = ? AND (matricula IS NULL OR matricula = '')", (cm_str, c_id))
                if not cp and cm_str.isdigit() and len(cm_str) == 11:
                    cursor.execute("UPDATE coordenadores SET cpf = ? WHERE id = ? AND (cpf IS NULL OR cpf = '')", (cm_str, c_id))

    conexao.commit()
    conexao.close()

# Inicializa as tabelas necessárias no banco
inicializar_banco()

def inferir_base_operacional(plataforma, tipo_uso, base_informada=''):
    """
    Identifica a base operacional (Tank, TDBR, Repair, Escritório Central ou Operação)
    com base no parâmetro informado ou no texto de destino.
    """
    if base_informada and base_informada.strip():
        b = base_informada.strip()
        if b in ('Tank', 'TDBR', 'Repair', 'Escritório Central', 'Operação'):
            return b
    if tipo_uso == 'Operação':
        return 'Operação'
    p = (plataforma or '').strip()
    p_lower = p.lower()
    if p_lower.startswith('tank') or 'tank' in p_lower or 'niterói' in p_lower:
        return 'Tank'
    if p_lower.startswith('tdbr') or 'tdbr' in p_lower:
        return 'TDBR'
    if p_lower.startswith('repair') or 'repair' in p_lower:
        return 'Repair'
    if 'central' in p_lower or 'recepção' in p_lower:
        return 'Escritório Central'
    return 'Base'


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
        rotas_permitidas_coordenador = ('meus_chamados', 'solicitar_equipamento', 'historico', 'logout', 'static', 'download_cautela', 'redirecionar_cautelas', 'trocar_senha')
        if request.endpoint not in rotas_permitidas_coordenador:
            flash("Acesso restrito: seu perfil de Coordenador permite acessar apenas Meus Chamados, Solicitação de Equipamento e Histórico.", "warning")
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

def salvar_novo_usuario(username, senha_pura, role='coordenador', id_personalizado=None, nome_completo=None, cpf_matricula=None, setor='Operações', trocar_senha=1, cpf=None, matricula=None, email=None, celular=None, base='Tank'):
    """
    Cadastra um novo usuário no banco com senha criptografada via scrypt.
    Se o papel for 'coordenador', cadastra atomicamente em 'usuarios' e 'coordenadores' com o MESMO ID.
    Valida documentação obrigatória: Nome Completo, Matrícula, CPF, E-mail, Celular, Setor e Base.
    """
    if role not in ('admin', 'coordenador'):
        return False, "O papel (role) deve ser 'admin' ou 'coordenador'."

    username = username.strip()
    if len(username) < 3 or len(username) > 64:
        return False, "O nome de usuário deve ter entre 3 e 64 caracteres."

    if len(senha_pura) < 4 or len(senha_pura) > 128:
        return False, "A senha deve ter entre 4 e 128 caracteres."

    cpf_formatado = ''
    matricula_formatada = ''
    email_formatado = ''
    celular_formatado = ''
    cpf_matricula_valor = ''

    if role == 'coordenador':
        if not nome_completo or not nome_completo.strip():
            return False, "O Nome Completo do coordenador / solicitante é obrigatório."
        nome_completo = nome_completo.strip()[:100]
        setor = (setor or 'Operações').strip()[:50]
        base = (base or 'Tank').strip()[:50]

        # Tratamento e validação de CPF (11 dígitos)
        cpf_raw = (cpf or cpf_matricula or '').strip()
        cpf_digitos = re.sub(r'\D', '', cpf_raw)
        if not cpf_digitos or len(cpf_digitos) != 11:
            return False, "CPF obrigatório e inválido. Informe os 11 dígitos numéricos do CPF."
        cpf_formatado = f"{cpf_digitos[:3]}.{cpf_digitos[3:6]}.{cpf_digitos[6:9]}-{cpf_digitos[9:]}"

        # Tratamento e validação de Matrícula Geral (apenas dígitos numéricos)
        mat_raw = (matricula or '').strip()
        if not mat_raw:
            return False, "A Matrícula Geral corporativa é obrigatória."
        if not mat_raw.isdigit():
            return False, "A Matrícula Geral não pode conter letras. Informe exclusivamente dígitos numéricos."
        matricula_formatada = mat_raw[:30]

        # Tratamento e validação de E-mail
        email_raw = (email or '').strip()[:100]
        if not email_raw:
            return False, "O E-mail institucional do colaborador é obrigatório."
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email_raw):
            return False, "Formato de e-mail inválido. Informe um endereço corporativo válido (ex: nome@empresa.com)."
        email_formatado = email_raw.lower()

        # Tratamento e validação de Celular / WhatsApp
        cel_raw = (celular or '').strip()
        cel_digitos = re.sub(r'\D', '', cel_raw)
        if not cel_digitos or len(cel_digitos) < 10 or len(cel_digitos) > 11:
            return False, "Número de celular obrigatório e inválido. Informe DDD + número (10 ou 11 dígitos)."
        if len(cel_digitos) == 11:
            celular_formatado = f"({cel_digitos[:2]}) {cel_digitos[2:7]}-{cel_digitos[7:]}"
        else:
            celular_formatado = f"({cel_digitos[:2]}) {cel_digitos[2:6]}-{cel_digitos[6:]}"

        # Campo composto para retrocompatibilidade
        cpf_matricula_valor = f"{cpf_formatado} | Matrícula: {matricula_formatada}"

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
                    SET nome_completo = ?, cpf_matricula = ?, setor = ?,
                        cpf = ?, matricula = ?, email = ?, celular = ?, base = ?
                    WHERE id = ?
                ''', (nome_completo, cpf_matricula_valor, setor, cpf_formatado, matricula_formatada, email_formatado, celular_formatado, base, user_id))
            else:
                cursor.execute('''
                    INSERT INTO coordenadores (id, nome_completo, cpf_matricula, setor, cpf, matricula, email, celular, base)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, nome_completo, cpf_matricula_valor, setor, cpf_formatado, matricula_formatada, email_formatado, celular_formatado, base))

        conexao.commit()
        papel_str = "Coordenador" if role == 'coordenador' else "Administrador"
        return True, f"{papel_str} '{username}' (ID #{user_id}) cadastrado com sucesso!"
    except sqlite3.IntegrityError as e:
        erro_msg = str(e)
        if 'username' in erro_msg:
            return False, f"O login '{username}' já está em uso no sistema."
        if 'cpf_matricula' in erro_msg or 'cpf' in erro_msg:
            return False, f"O CPF ou Matrícula informado já está cadastrado para outro coordenador."
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
            usuario = load_user(dados[0])
            if not usuario:
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
    # Imagens incorporadas pelo próprio servidor não abrem acesso a rede ou ao sistema de arquivos.
    if url.startswith('data:image/png;base64,'):
        conteudo = url.split(',', 1)[1]
        return URLFetcherResponse(
            url,
            base64.b64decode(conteudo, validate=True),
            {'Content-Type': 'image/png'},
        )
    raise ValueError(f"Acesso a recursos externos bloqueado por segurança: {url}")


def imagem_pdf_data_uri(nome_arquivo):
    """Carrega somente os elementos gráficos internos permitidos no termo."""
    nomes_permitidos = {
        'ambipar-logo.png',
        'ambipar-footer.png',
    }
    if nome_arquivo not in nomes_permitidos:
        raise ValueError('Elemento gráfico de PDF não permitido.')
    caminho = os.path.join(app.root_path, 'static', 'pdf', nome_arquivo)
    with open(caminho, 'rb') as arquivo:
        conteudo = base64.b64encode(arquivo.read()).decode('ascii')
    return f'data:image/png;base64,{conteudo}'


def formatar_nome_pdf_cautela(rdo, sn):
    """
    Retorna o nome de arquivo padronizado, seguro e canônico para o Termo de Cautela em PDF.
    Remove espaços e caracteres especiais para compatibilidade com o sistema de arquivos e URLs.
    """
    rdo_safe = re.sub(r'[^A-Za-z0-9_-]', '', str(rdo or 'SEM_RDO'))
    sn_safe = re.sub(r'[^A-Za-z0-9_-]', '', str(sn or 'SEM_SN'))
    return f"Cautela_{rdo_safe}_{sn_safe}.pdf"


def gerar_pdf_termo(rdo, sn, tipo, modelo, imei1, imei2, nome_coord, cpf_coord, data_str=None,
                    processador='', memoria_ram='', armazenamento='', sistema_operacional='', especificacoes=''):
    """
    Gera o termo corporativo de responsabilidade em uma página A4.
    A identificação técnica é adaptada à categoria do equipamento sem alterar as cláusulas jurídicas.
    """
    if not data_str:
        data_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    s_sn = html.escape(str(sn)) if sn else 'Sem Serial / Apagado'
    s_tipo = html.escape(str(tipo or 'Equipamento'))
    s_modelo = html.escape(str(modelo or 'N/A'))
    s_imei1 = html.escape(str(imei1 or 'N/A'))
    s_imei2 = html.escape(str(imei2 or 'N/A'))
    s_nome = html.escape(str(nome_coord or 'Responsável'))
    s_cpf = html.escape(str(cpf_coord or 'N/A'))
    logo_pdf = imagem_pdf_data_uri('ambipar-logo.png')
    rodape_pdf = imagem_pdf_data_uri('ambipar-footer.png')
    data_documento = str(data_str or '').strip()
    for formato_data in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y %H:%M'):
        try:
            data_documento = datetime.strptime(data_documento, formato_data).strftime('%d/%m/%Y')
            break
        except ValueError:
            continue
    s_data = html.escape(data_documento.split(' ')[0])

    # CAUSA: o PDF anterior usava a mesma tabela genérica para celular, notebook e demais ativos.
    # FIX: celulares priorizam IMEI; computadores recebem configuração técnica; os demais usam identificação patrimonial.
    tipo_chave = str(tipo or '').lower()
    tipo_chave = (tipo_chave.replace('á', 'a').replace('â', 'a').replace('ã', 'a')
                  .replace('é', 'e').replace('ê', 'e').replace('í', 'i')
                  .replace('ó', 'o').replace('ô', 'o').replace('õ', 'o')
                  .replace('ú', 'u').replace('ç', 'c'))
    eh_celular = any(chave in tipo_chave for chave in ('celular', 'smartphone', 'telefone'))
    eh_computador = any(chave in tipo_chave for chave in ('notebook', 'laptop', 'computador', 'desktop'))

    campos_principais = [('TIPO DE EQUIPAMENTO', s_tipo), ('MODELO', s_modelo),
                         ('Nº DE SÉRIE OU PATRIMÔNIO', s_sn)]
    if eh_celular:
        campos_principais.append(('IMEI 1', s_imei1))
        if imei2:
            campos_principais.append(('IMEI 2', s_imei2))

    cabecalhos = ''.join(f'<th>{rotulo}</th>' for rotulo, _ in campos_principais)
    valores = ''.join(f'<td>{valor}</td>' for _, valor in campos_principais)
    tabela_identificacao = f'<table class="equipment-table"><thead><tr>{cabecalhos}</tr></thead><tbody><tr>{valores}</tr></tbody></table>'

    campos_tecnicos = []
    if eh_computador:
        campos_tecnicos = [
            ('SISTEMA OPERACIONAL', sistema_operacional), ('PROCESSADOR (CPU)', processador),
            ('MEMÓRIA RAM', memoria_ram), ('ARMAZENAMENTO', armazenamento),
            ('ESPECIFICAÇÕES TÉCNICAS', especificacoes)
        ]
    elif not eh_celular and especificacoes:
        campos_tecnicos = [('ESPECIFICAÇÕES TÉCNICAS', especificacoes)]

    linhas_tecnicas = ''
    for rotulo, valor in campos_tecnicos:
        if valor:
            linhas_tecnicas += f'<tr><th>{rotulo}</th><td>{html.escape(str(valor))}</td></tr>'
    tabela_tecnica = f'<table class="technical-table">{linhas_tecnicas}</table>' if linhas_tecnicas else ''

    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: A4; margin: 14mm 15mm 25mm; }}
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; color: #111; font-family: Arial, sans-serif; font-size: 8.7pt; line-height: 1.22; }}
            .brand {{ height: 17mm; text-align: center; }}
            .brand img {{ display: inline-block; width: 48mm; height: auto; }}
            h1 {{ margin: 2mm 0 8mm; text-align: center; font-size: 12pt; text-transform: uppercase; }}
            .opening {{ margin: 0 0 7mm; text-align: justify; font-size: 9.4pt; line-height: 1.34; }}
            .equipment-table {{ width: 92%; margin: 0 auto 6mm; border-collapse: collapse; table-layout: fixed; }}
            .equipment-table th {{ padding: 2mm 1mm; background: #c6e0b4; border: 1px solid #888; font-size: 7pt; text-align: center; }}
            .equipment-table td {{ height: 9mm; padding: 2.4mm 1mm; border: 1px solid #888; font-size: 8.5pt; text-align: center; word-break: break-word; }}
            .technical-table {{ width: 92%; margin: -4mm auto 6mm; border-collapse: collapse; }}
            .technical-table th {{ width: 29%; padding: 1.4mm; background: #edf4e8; border: 1px solid #999; font-size: 7pt; text-align: left; }}
            .technical-table td {{ padding: 1.4mm; border: 1px solid #999; font-size: 7.8pt; }}
            h2 {{ margin: 0 0 3mm; font-size: 10pt; text-transform: uppercase; }}
            ol {{ margin: 0; padding-left: 5mm; }}
            li {{ margin: 0 0 2mm; padding-left: 1mm; text-align: justify; font-size: 8.3pt; line-height: 1.24; }}
            .place-date {{ margin-top: 6mm; font-size: 9pt; }}
            .signatures {{ display: table; width: 100%; margin-top: 18mm; table-layout: fixed; }}
            .signature {{ display: table-cell; width: 50%; padding: 0 8mm; text-align: center; vertical-align: top; }}
            .signature-space {{ height: 13mm; position: relative; }}
            .signature-line {{ border-top: 1px solid #111; padding-top: 1.5mm; font-size: 7.8pt; }}
            .signature-data {{ margin-top: 2mm; text-align: left; font-size: 7.2pt; line-height: 1.35; }}
            /* Mantém a proporção original do rodapé para não deformar o QR Code e a marca. */
            .footer {{ position: fixed; right: -15mm; bottom: -25mm; left: -15mm; height: 30.7mm; overflow: hidden; }}
            .footer-art {{ position: absolute; right: 0; bottom: 0; left: 0; width: 210mm; height: auto; }}
            .footer-info {{ position: absolute; left: 28mm; bottom: 7mm; font-size: 6.5pt; font-weight: 700; line-height: 1.3; }}
        </style>
    </head>
    <body>
        <div class="brand"><img src="{logo_pdf}" alt="Ambipar"></div>
        <h1>Termo de Responsabilidade e Cautela de Equipamento</h1>

        <p class="opening"><strong>AMBIPAR RESPONSE TANK CLEANING S/A</strong>, localizada na Rua Manoel Pacheco de Carvalho, nº 102 – Galpão, Centro, Niterói/RJ, inscrita no CNPJ sob o nº 18.591.097/0001-10, <strong>ENTREGA</strong>, neste ato, ao(à) colaborador(a) <strong>{s_nome}</strong>, portador(a) do CPF nº <strong>{s_cpf}</strong>, doravante denominado(a) simplesmente <strong>“USUÁRIO(A)”</strong>, o equipamento abaixo descrito, destinado ao uso exclusivo em suas atividades profissionais, sob as seguintes condições:</p>

        {tabela_identificacao}
        {tabela_tecnica}

        <h2>Condições</h2>
        <ol>
            <li>O equipamento deverá ser utilizado única e exclusivamente a serviço da <strong>EMPRESA</strong>, em razão da atividade exercida pelo(a) <strong>USUÁRIO(A)</strong>;</li>
            <li>O(A) <strong>USUÁRIO(A)</strong> ficará responsável pela guarda, uso e conservação do equipamento, cabendo-lhe zelar por sua integridade e bom funcionamento;</li>
            <li>O(A) <strong>USUÁRIO(A)</strong> detém apenas a detenção do equipamento, para fins de uso exclusivo na prestação de serviços, e não a sua propriedade, sendo terminantemente vedados o empréstimo, a locação, a cessão ou o repasse a terceiros, sem autorização prévia e expressa da <strong>EMPRESA</strong>;</li>
            <li>O(A) <strong>USUÁRIO(A)</strong> deverá comunicar imediatamente ao setor responsável qualquer anormalidade, avaria, mau funcionamento, perda, furto ou roubo do equipamento;</li>
            <li>A <strong>EMPRESA</strong> garante suporte técnico, manutenção e, quando necessário, substituição do equipamento sem qualquer ônus ao(à) <strong>USUÁRIO(A)</strong>, exceto quando o dano decorrer comprovadamente de mau uso, negligência, imprudência ou descumprimento das condições aqui previstas;</li>
            <li>Não será atribuída responsabilidade ao(à) <strong>USUÁRIO(A)</strong> por desgaste natural decorrente do uso regular, defeito de fabricação, caso fortuito ou força maior;</li>
            <li>Ao término da prestação de serviço, do contrato individual de trabalho, ou mediante solicitação da <strong>EMPRESA</strong>, o(a) <strong>USUÁRIO(A)</strong> compromete-se a devolver o equipamento em perfeito estado no mesmo dia em que for comunicado ou comunique seu desligamento, resguardado o desgaste natural decorrente do uso normal.</li>
        </ol>

        <div class="place-date">Niterói/RJ, {s_data}.</div>

        <div class="signatures">
            <div class="signature">
                <div class="signature-space"></div>
                <div class="signature-line">Assinatura do(a) Colaborador(a) / USUÁRIO(A)</div>
                <div class="signature-data">Nome: {s_nome}<br>CPF: {s_cpf}</div>
            </div>
            <div class="signature">
                <div class="signature-space"></div>
                <div class="signature-line">Assinatura do Responsável pela Entrega</div>
                <div class="signature-data">Representante da EMPRESA</div>
            </div>
        </div>

        <div class="footer">
            <img class="footer-art" src="{rodape_pdf}" alt="Ambipar">
            <div class="footer-info">AMBIPAR RESPONSE TANK CLEANING S/A<br>Rua Manoel Pacheco de Carvalho, nº 102 – Galpão, Centro, Niterói/RJ</div>
        </div>
    </body>
    </html>
    """
    os.makedirs('Cautelas', exist_ok=True)
    nome_arquivo = formatar_nome_pdf_cautela(rdo, sn)
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
        matricula = request.form.get('matricula', '').strip()
        email = request.form.get('email', '').strip()
        celular = request.form.get('celular', '').strip()
        setor = request.form.get('setor', 'Operações').strip()
        base = request.form.get('base', 'Tank').strip()
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
            base=base if role == 'coordenador' else 'Tank',
            trocar_senha=trocar_senha,
            cpf=cpf if role == 'coordenador' else None,
            matricula=matricula if role == 'coordenador' else None,
            email=email if role == 'coordenador' else None,
            celular=celular if role == 'coordenador' else None
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
    
    cursor.execute('''
        SELECT id, tipo, modelo, patrimonio_sn, imei_1, imei_2, status, 
               COALESCE(base, 'Tank') AS base,
               COALESCE(alugado, 0) AS alugado,
               COALESCE(empresa_locadora, '') AS empresa_locadora,
               COALESCE(processador, '') AS processador,
               COALESCE(memoria_ram, '') AS memoria_ram,
               COALESCE(armazenamento, '') AS armazenamento,
               COALESCE(sistema_operacional, '') AS sistema_operacional,
               COALESCE(especificacoes, '') AS especificacoes
        FROM equipamentos ORDER BY id DESC
    ''')
    equipamentos_raw = cursor.fetchall()
    equipamentos = []
    for eq in equipamentos_raw:
        tipo_str = eq[1] or ''
        is_notebook = (tipo_str.strip().lower() == 'notebook') or ('notebook' in tipo_str.lower()) or ('laptop' in tipo_str.lower())
        equipamentos.append({
            'id': eq[0],
            'tipo': eq[1],
            'modelo': eq[2],
            'patrimonio_sn': eq[3] or '',
            'imei_1': eq[4],
            'imei_2': eq[5],
            'status': eq[6],
            'categoria': obter_categoria_equipamento(eq[1]),
            'base': eq[7] or 'Tank',
            'alugado': bool(eq[8]) if len(eq) > 8 else False,
            'empresa_locadora': eq[9] if len(eq) > 9 else '',
            'is_notebook': is_notebook,
            'processador': eq[10] if len(eq) > 10 else '',
            'memoria_ram': eq[11] if len(eq) > 11 else '',
            'armazenamento': eq[12] if len(eq) > 12 else '',
            'sistema_operacional': eq[13] if len(eq) > 13 else '',
            'especificacoes': eq[14] if len(eq) > 14 else ''
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
               COALESCE(s.setor, 'Operações') AS setor,
               COALESCE(s.base, '') AS base
        FROM solicitacoes s
        LEFT JOIN coordenadores co ON s.id_coordenador = co.id
        LEFT JOIN usuarios u ON s.id_coordenador = u.id
        ORDER BY s.id DESC
    ''')
    solicitacoes_raw = cursor.fetchall()

    # CAUSA: o painel executava uma nova consulta para cada solicitação (N+1 queries).
    # FIX: carrega todos os itens vinculados uma vez e os agrupa em memória.
    cursor.execute('''
        SELECT c.id_solicitacao, c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn,
               c.data_hora_saida, c.data_hora_devolucao
        FROM cautelas c
        JOIN equipamentos e ON c.id_equipamento = e.id
        WHERE c.id_solicitacao IS NOT NULL
        ORDER BY c.id_solicitacao, c.id_cautela
    ''')
    itens_por_solicitacao = {}
    for item in cursor.fetchall():
        itens_por_solicitacao.setdefault(item[0], []).append({
            'id_cautela': item[1],
            'tipo': item[2],
            'modelo': item[3],
            'patrimonio_sn': item[4],
            'data_saida': item[5],
            'devolvido': bool(item[6]),
            'data_devolucao': item[6],
        })

    solicitacoes = []
    for s in solicitacoes_raw:
        id_sol = s[0]
        qtd_total = s[3]
        itens_emitidos = itens_por_solicitacao.get(id_sol, [])
        
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

        base_sol = s[13] if len(s) > 13 and s[13] else inferir_base_operacional(s[5], s[11] if len(s) > 11 else 'Operação')

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
            'base': base_sol,
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
               e.id AS id_equipamento, c.id_solicitacao,
               COALESCE(s.base, '') AS base_solicitacao,
               COALESCE(s.plataforma, '') AS plataforma_solicitacao,
               COALESCE(s.tipo_uso, 'Operação') AS tipo_uso_solicitacao,
               COALESCE(e.base, 'Tank') AS base_equipamento
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        LEFT JOIN usuarios u ON c.id_coordenador = u.id
        LEFT JOIN solicitacoes s ON c.id_solicitacao = s.id
        ORDER BY c.id_cautela DESC
    ''')
    cautelas_raw = cursor.fetchall()
    cautelas = []
    for cr in cautelas_raw:
        base_sol = cr[10] if len(cr) > 10 and cr[10] else ''
        plat_sol = cr[11] if len(cr) > 11 and cr[11] else ''
        tipo_uso_sol = cr[12] if len(cr) > 12 and cr[12] else 'Operação'
        base_eq = cr[13] if len(cr) > 13 and cr[13] else 'Tank'

        if cr[9]:  # id_solicitacao
            base_cautela = base_sol if base_sol else inferir_base_operacional(plat_sol, tipo_uso_sol)
        else:
            base_cautela = base_eq or 'Tank'

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
            'base': base_cautela,
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

    origem = request.form.get('origem', '').strip()
    id_sol_int = int(id_solicitacao) if id_solicitacao and id_solicitacao.isdigit() else None
    destino_sucesso = url_for('historico') if (origem == 'historico' or (not id_sol_int and origem != 'home')) else url_for('home')

    if not id_equipamento or not id_coordenador or not rdo:
        flash("Por favor, selecione o Equipamento, o Coordenador e informe o RDO.", "warning")
        return redirect(destino_sucesso)

    notificacao = None
    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        # Serializa a retirada do equipamento: dois cliques concorrentes não podem criar duas cautelas.
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('''
            SELECT tipo, modelo, patrimonio_sn, imei_1, imei_2, status,
                   COALESCE(processador, ''), COALESCE(memoria_ram, ''),
                   COALESCE(armazenamento, ''), COALESCE(sistema_operacional, ''),
                   COALESCE(especificacoes, '')
            FROM equipamentos WHERE id = ?
        ''', (id_equipamento,))
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
                    coord = (user_row[0], nome_padrao, f"MAT-{user_row[0]}")
                    id_coordenador = user_row[0]
                else:
                    id_coordenador = coord[0]

        if not equip:
            flash("Erro: Equipamento selecionado não foi encontrado.", "danger")
            return redirect(destino_sucesso)

        if not coord:
            flash("Erro: Coordenador selecionado não foi encontrado no sistema.", "danger")
            return redirect(destino_sucesso)

        tipo, modelo, sn, imei1, imei2, status_equip, proc, ram, arm, so, esp = equip
        coord_id, nome_coord, cpf_coord = coord

        cursor.execute('''
            SELECT id_cautela FROM cautelas
            WHERE id_equipamento = ? AND data_hora_devolucao IS NULL
            LIMIT 1
        ''', (id_equipamento,))
        cautela_ativa = cursor.fetchone()
        status_disponivel = str(status_equip or '').strip().lower() in ('disponível', 'disponivel')
        if cautela_ativa or not status_disponivel:
            conexao.rollback()
            flash("Este equipamento já possui uma cautela ativa ou não está mais disponível. Nenhum registro duplicado foi criado.", "warning")
            return redirect(destino_sucesso)

        if id_sol_int:
            cursor.execute('SELECT tipo_equipamento, quantidade FROM solicitacoes WHERE id = ?', (id_sol_int,))
            sol_row = cursor.fetchone()
            if sol_row:
                tipo_pedido, qtd_pedida = sol_row
                if not tipos_sao_compativeis(tipo, tipo_pedido):
                    flash(f"Equipamento recusado! A solicitação #SOL-{id_sol_int} exige '{tipo_pedido}', mas você selecionou '{tipo} ({modelo})'.", "danger")
                    return redirect(destino_sucesso)

        cursor.execute('''
            INSERT INTO cautelas (id_equipamento, id_coordenador, rdo_vinculado, id_solicitacao) 
            VALUES (?, ?, ?, ?)
        ''', (id_equipamento, id_coordenador, rdo, id_sol_int))
        
        cursor.execute("UPDATE equipamentos SET status = 'Em Operação' WHERE id = ?", (id_equipamento,))

        msg_progresso = ""
        if id_sol_int:
            cursor.execute('SELECT COUNT(*) FROM cautelas WHERE id_solicitacao = ? AND data_hora_devolucao IS NULL', (id_sol_int,))
            total_emitidos = cursor.fetchone()[0]
            cursor.execute('SELECT quantidade, status FROM solicitacoes WHERE id = ?', (id_sol_int,))
            row_q = cursor.fetchone()
            qtd_solicitada = row_q[0] if row_q else 1
            status_anterior = row_q[1] if row_q else None

            if total_emitidos >= qtd_solicitada:
                novo_status = 'Esperando Entrega'
                cursor.execute("UPDATE solicitacoes SET status = 'Esperando Entrega' WHERE id = ?", (id_sol_int,))
                msg_progresso = f"Todos os {qtd_solicitada} itens solicitados foram emitidos! O chamado agora está 'Esperando Entrega'."
            else:
                novo_status = 'Em Atendimento'
                cursor.execute("UPDATE solicitacoes SET status = 'Em Atendimento' WHERE id = ?", (id_sol_int,))
                faltam = qtd_solicitada - total_emitidos
                msg_progresso = f"Item {total_emitidos} de {qtd_solicitada} emitido com sucesso! Faltam {faltam} item(ns)."
            notificacao = (id_sol_int, status_anterior, msg_progresso)
        else:
            msg_progresso = "Cautela gerada com sucesso."

        conexao.commit()
        sn_display = f"SN: {sn}" if sn else "Sem Serial"
        flash(f"Cautela registrada para {nome_coord} ({tipo} {modelo} - {sn_display})! O PDF será gerado ao abrir ou baixar. {msg_progresso}", "success")
        
    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao gerar cautela: {e}", "danger")
    finally:
        conexao.close()

    if notificacao:
        agendar_notificacao_solicitacao(get_db_connection, *notificacao)

    return redirect(destino_sucesso)


@app.route('/solicitacao/entregar/<int:id_solicitacao>', methods=['POST'])
@login_required
@admin_required
def entregar_solicitacao(id_solicitacao):
    notificacao = None
    conexao = get_db_connection()
    cursor = conexao.cursor()
    # O modo WAL persiste no arquivo; configurá-lo uma vez evita renegociação em toda requisição.
    cursor.execute('PRAGMA journal_mode = WAL;')
    try:
        cursor.execute('SELECT status FROM solicitacoes WHERE id = ?', (id_solicitacao,))
        row = cursor.fetchone()
        if not row:
            flash('Solicitação não encontrada.', 'warning')
            return redirect(url_for('home'))
        status_anterior = row[0]
        cursor.execute("UPDATE solicitacoes SET status = 'Finalizada' WHERE id = ?", (id_solicitacao,))
        conexao.commit()
        if status_anterior != 'Finalizada':
            notificacao = (id_solicitacao, status_anterior, 'A entrega foi confirmada e o chamado foi finalizado.')
        flash(f"Equipamento da solicitação #SOL-{id_solicitacao} marcado como entregue! Chamado finalizado.", "success")
    except Exception as e:
        flash(f"Erro ao finalizar solicitação: {e}", "danger")
    finally:
        conexao.close()
    if notificacao:
        agendar_notificacao_solicitacao(get_db_connection, *notificacao)
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
    patrimonio = patrimonio if patrimonio else None

    imei1 = (request.form.get('imei1') or '').strip()[:30]
    imei2 = (request.form.get('imei2') or '').strip()[:30]
    base = (request.form.get('base') or 'Tank').strip()[:40]
    if base not in ('Tank', 'TDBR', 'Repair', 'Escritório Central'):
        base = 'Tank'
    
    alugado_val = request.form.get('alugado')
    alugado = 1 if alugado_val in ('1', 'on', 'true', 'sim') else 0
    empresa_locadora = (request.form.get('empresa_locadora') or '').strip()[:100] if alugado else ''

    # Campos específicos de hardware e OS
    processador = (request.form.get('processador') or '').strip()[:80]
    memoria_ram = (request.form.get('memoria_ram') or '').strip()[:40]
    armazenamento = (request.form.get('armazenamento') or '').strip()[:60]
    sistema_operacional = (request.form.get('sistema_operacional') or '').strip()[:60]

    # Especificações extras (monitor, rádio, detector de gás, observações)
    extras = []
    mon_tam = (request.form.get('monitor_polegadas') or '').strip()
    mon_conn = (request.form.get('monitor_conexoes') or '').strip()
    if mon_tam:
        extras.append(f"Tela: {mon_tam}")
    if mon_conn:
        extras.append(f"Entradas: {mon_conn}")

    rad_faixa = (request.form.get('radio_faixa') or '').strip()
    rad_canais = (request.form.get('radio_canais') or '').strip()
    if rad_faixa:
        extras.append(f"Faixa: {rad_faixa}")
    if rad_canais:
        extras.append(f"Canais: {rad_canais}")

    gas_sens = (request.form.get('gas_sensores') or '').strip()
    gas_calib = (request.form.get('gas_calibracao') or '').strip()
    if gas_sens:
        extras.append(f"Gases: {gas_sens}")
    if gas_calib:
        extras.append(f"Calibração: {gas_calib}")

    obs_livre = (request.form.get('especificacoes') or '').strip()
    if obs_livre:
        extras.append(obs_livre)

    especificacoes_final = " • ".join(extras)[:255]

    if not tipo or not modelo:
        flash("Preencha o tipo e o modelo do equipamento.", "warning")
        return redirect(url_for('novo_equipamento'))

    if alugado and not empresa_locadora:
        flash("Para equipamentos alugados, informe obrigatoriamente a empresa responsável pelo aluguel.", "warning")
        return redirect(url_for('novo_equipamento'))

    conexao = get_db_connection()
    cursor = conexao.cursor()
    try:
        cursor.execute('''
            INSERT INTO equipamentos (tipo, modelo, patrimonio_sn, imei_1, imei_2, status, base, alugado, empresa_locadora,
                                     processador, memoria_ram, armazenamento, sistema_operacional, especificacoes)
            VALUES (?, ?, ?, ?, ?, 'Disponível', ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (tipo, modelo, patrimonio, imei1, imei2, base, alugado, empresa_locadora,
              processador, memoria_ram, armazenamento, sistema_operacional, especificacoes_final))
        conexao.commit()
        detalhe_loc = f" [Alugado: {empresa_locadora}]" if alugado else " [Próprio]"
        sn_info = f" (SN: {patrimonio})" if patrimonio else " (Sem Serial)"
        flash(f"Equipamento '{tipo} - {modelo}'{sn_info} cadastrado com sucesso na base {base}{detalhe_loc}!", "success")
    except sqlite3.IntegrityError:
        flash(f"Erro: O número de patrimônio/SN '{patrimonio}' já está cadastrado no sistema.", "danger")
    except Exception as e:
        flash(f"Erro ao cadastrar equipamento: {e}", "danger")
    finally:
        conexao.close()
        
    return redirect(url_for('lista_equipamentos'))


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


@app.route('/equipamentos')
@login_required
@admin_required
def lista_equipamentos():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        SELECT id, tipo, modelo, patrimonio_sn, imei_1, imei_2, status, 
               COALESCE(base, 'Tank') AS base,
               COALESCE(alugado, 0) AS alugado,
               COALESCE(empresa_locadora, '') AS empresa_locadora,
               COALESCE(processador, '') AS processador,
               COALESCE(memoria_ram, '') AS memoria_ram,
               COALESCE(armazenamento, '') AS armazenamento,
               COALESCE(sistema_operacional, '') AS sistema_operacional,
               COALESCE(especificacoes, '') AS especificacoes
        FROM equipamentos 
        ORDER BY id DESC
    ''')
    rows = cursor.fetchall()
    conexao.close()
    
    equipamentos = []
    total_notebooks = 0
    total_alugados = 0
    total_proprios = 0
    total_disponiveis = 0
    total_em_operacao = 0
    
    for r in rows:
        tipo = r[1] or ''
        is_notebook = (tipo.strip().lower() == 'notebook') or ('notebook' in tipo.lower()) or ('laptop' in tipo.lower())
        if is_notebook:
            total_notebooks += 1
            
        alugado = bool(r[8])
        if alugado:
            total_alugados += 1
        else:
            total_proprios += 1
            
        status = r[6] or 'Disponível'
        if status in ('Disponível', 'Disponivel'):
            total_disponiveis += 1
        elif status in ('Em Operação', 'Em Operacao'):
            total_em_operacao += 1
            
        equipamentos.append({
            'id': r[0],
            'tipo': r[1],
            'modelo': r[2] or '',
            'patrimonio_sn': r[3] or '',
            'imei_1': r[4] or '',
            'imei_2': r[5] or '',
            'status': status,
            'base': r[7] or 'Tank',
            'alugado': alugado,
            'empresa_locadora': r[9] or '',
            'processador': r[10] or '',
            'memoria_ram': r[11] or '',
            'armazenamento': r[12] or '',
            'sistema_operacional': r[13] or '',
            'especificacoes': r[14] or '',
            'is_notebook': is_notebook,
            'categoria': obter_categoria_equipamento(r[1])
        })
        
    metricas = {
        'total': len(equipamentos),
        'notebooks': total_notebooks,
        'alugados': total_alugados,
        'proprios': total_proprios,
        'disponiveis': total_disponiveis,
        'em_operacao': total_em_operacao
    }
    
    return render_template('equipamentos.html', equipamentos=equipamentos, metricas=metricas)


@app.route('/colaboradores')
@login_required
@admin_required
def colaboradores():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        SELECT c.id, c.nome_completo, 
               COALESCE(c.matricula, '') AS matricula,
               COALESCE(c.cpf, '') AS cpf,
               COALESCE(c.email, '') AS email,
               COALESCE(c.celular, '') AS celular,
               COALESCE(c.setor, 'Operações') AS setor,
               COALESCE(u.username, '') AS username,
               COALESCE(c.cpf_matricula, '') AS cpf_matricula,
               (SELECT COUNT(*) FROM solicitacoes s WHERE s.id_coordenador = c.id) AS total_solicitacoes,
               COALESCE(c.base, 'Tank') AS base,
               COALESCE(u.role, 'coordenador') AS role,
               (SELECT COUNT(*) FROM solicitacoes s WHERE s.id_coordenador = c.id AND s.status = 'Pendente') AS solicitacoes_pendentes
        FROM coordenadores c
        LEFT JOIN usuarios u ON c.id = u.id
        ORDER BY c.id DESC
    ''')
    rows = cursor.fetchall()
    conexao.close()
    
    lista_colaboradores = []
    setores_ativos = set()
    bases_ativas = set()
    total_chamados = 0
    for r in rows:
        matricula_val = r[2]
        cpf_val = r[3]
        if not matricula_val and not cpf_val and r[8]:
            leg = str(r[8]).strip()
            if '|' in leg:
                partes = leg.split('|')
                cpf_val = partes[0].strip()
                matricula_val = re.sub(r'\D', '', partes[1])
            elif len(leg) == 11 and leg.isdigit():
                cpf_val = f"{leg[:3]}.{leg[3:6]}.{leg[6:9]}-{leg[9:]}"
            else:
                matricula_val = leg

        setor_val = r[6] or 'Operações'
        setores_ativos.add(setor_val)
        base_val = r[10] or 'Tank'
        bases_ativas.add(base_val)
        qtd_sol = r[9] or 0
        total_chamados += qtd_sol
        
        lista_colaboradores.append({
            'id': r[0],
            'nome_completo': r[1],
            'matricula': matricula_val or 'Não informada',
            'cpf': cpf_val or 'Não informado',
            'email': r[4] or 'Não informado',
            'celular': r[5] or 'Não informado',
            'setor': setor_val,
            'base': base_val,
            'username': r[7] or f"coord_{r[0]}",
            'total_solicitacoes': qtd_sol,
            'role': r[11] if len(r) > 11 else 'coordenador',
            'solicitacoes_pendentes': r[12] if len(r) > 12 else 0
        })
        
    metricas = {
        'total': len(lista_colaboradores),
        'setores': len(setores_ativos),
        'bases': len(bases_ativas),
        'total_chamados': total_chamados
    }
    
    return render_template('colaboradores.html', colaboradores=lista_colaboradores, metricas=metricas)


@app.route('/devolver/<int:id_equipamento>', methods=['POST'])
@login_required
@admin_required
def devolver(id_equipamento):
    notificacao = None
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
                    notificacao = (id_sol, status_sol, 'O andamento foi recalculado após a devolução de um equipamento.')
                    faltam_agora = max(0, qtd_pedida - ativas_restantes)
                    msg_solicitacao = f" Solicitação #SOL-{id_sol} recalculada: {ativas_restantes}/{qtd_pedida} ativos (status '{novo_status}')."

        conexao.commit()
        flash(f"Equipamento devolvido com sucesso! Status atualizado para Disponível.{msg_solicitacao}", "success")
    except Exception as e:
        flash(f"Erro ao devolver equipamento: {e}", "danger")
    finally:
        conexao.close()
    if notificacao:
        agendar_notificacao_solicitacao(get_db_connection, *notificacao)
    origem = request.referrer
    if origem and is_safe_redirect_url(origem):
        return redirect(origem)
    return redirect(url_for('historico'))


@app.route('/historico')
@login_required
def historico():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    
    base_usuario = 'Tank'
    setor_usuario = 'Operações'
    id_coordenador = current_user.id

    if current_user.role == 'coordenador':
        cursor.execute('''
            SELECT id, base, setor FROM coordenadores 
            WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
        ''', (current_user.id, current_user.username, current_user.username))
        coord_row = cursor.fetchone()
        if coord_row:
            id_coordenador = coord_row[0]
            base_usuario = coord_row[1] or 'Tank'
            setor_usuario = coord_row[2] or 'Operações'

        cursor.execute('''
            SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn,
                   COALESCE(co.nome_completo, u.username, 'Coordenador #' || c.id_coordenador) AS nome_coord,
                   c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao,
                   e.id AS id_equipamento, c.id_solicitacao,
                   COALESCE(s.base, '') AS base_solicitacao,
                   COALESCE(s.plataforma, '') AS plataforma_solicitacao,
                   COALESCE(s.tipo_uso, 'Operação') AS tipo_uso_solicitacao,
                   COALESCE(e.base, 'Tank') AS base_equipamento
            FROM cautelas c
            LEFT JOIN equipamentos e ON c.id_equipamento = e.id
            LEFT JOIN coordenadores co ON c.id_coordenador = co.id
            LEFT JOIN usuarios u ON c.id_coordenador = u.id
            LEFT JOIN solicitacoes s ON c.id_solicitacao = s.id
            WHERE c.id_coordenador = ? OR c.id_coordenador = ?
            ORDER BY c.id_cautela DESC
        ''', (id_coordenador, current_user.id))
    else:
        cursor.execute('''
            SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn,
                   COALESCE(co.nome_completo, u.username, 'Coordenador #' || c.id_coordenador) AS nome_coord,
                   c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao,
                   e.id AS id_equipamento, c.id_solicitacao,
                   COALESCE(s.base, '') AS base_solicitacao,
                   COALESCE(s.plataforma, '') AS plataforma_solicitacao,
                   COALESCE(s.tipo_uso, 'Operação') AS tipo_uso_solicitacao,
                   COALESCE(e.base, 'Tank') AS base_equipamento
            FROM cautelas c
            LEFT JOIN equipamentos e ON c.id_equipamento = e.id
            LEFT JOIN coordenadores co ON c.id_coordenador = co.id
            LEFT JOIN usuarios u ON c.id_coordenador = u.id
            LEFT JOIN solicitacoes s ON c.id_solicitacao = s.id
            ORDER BY c.id_cautela DESC
        ''')
    cautelas_raw = cursor.fetchall()
    conexao.close()

    cautelas = []
    contadores = {'Total': 0, 'Em Campo': 0, 'Devolvido': 0}
    for cr in cautelas_raw:
        st = 'Devolvido' if cr[7] else 'Em Campo'
        
        base_sol = cr[10] if len(cr) > 10 and cr[10] else ''
        plat_sol = cr[11] if len(cr) > 11 and cr[11] else ''
        tipo_uso_sol = cr[12] if len(cr) > 12 and cr[12] else 'Operação'
        base_eq = cr[13] if len(cr) > 13 and cr[13] else 'Tank'

        if cr[9]:  # id_solicitacao
            base_cautela = base_sol if base_sol else inferir_base_operacional(plat_sol, tipo_uso_sol)
        else:
            base_cautela = base_eq or 'Tank'

        # Se for coordenador (não-admin), restringe os registros exibidos estritamente à sua base cadastrada
        if current_user.role == 'coordenador':
            base_u_norm = (base_usuario or '').strip().lower()
            base_c_norm = (base_cautela or '').strip().lower()
            if base_u_norm and base_c_norm:
                if base_u_norm not in base_c_norm and base_c_norm not in base_u_norm:
                    continue

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
            'base': base_cautela,
            'status': st,
            'pdf_nome': formatar_nome_pdf_cautela(cr[5], cr[3]) if cr[5] else None
        })
    
    return render_template('historico.html', 
                           cautelas=cautelas, 
                           contadores=contadores,
                           base_usuario=base_usuario,
                           setor_usuario=setor_usuario)


# --- ROTA DE DOWNLOAD SEGURO DE CAUTELAS (Anti-Path-Traversal & Anti-IDOR) ---

PADRAO_NOME_CAUTELA = re.compile(r'^Cautela_[A-Za-z0-9_\-.]+\.pdf$')

@app.route('/cautelas/<path:filename>')
@login_required
def download_cautela(filename):
    caminho_dir = os.path.abspath('Cautelas')
    os.makedirs(caminho_dir, exist_ok=True)

    # 1. Prevenção estrita de Path Traversal
    nome_puro = os.path.basename(filename)
    if '..' in filename or '/' in filename or '\\' in filename:
        return abort(403)

    nome_seguro = secure_filename(nome_puro)
    nome_canonico = re.sub(r'[^A-Za-z0-9_.]', '', nome_puro)

    # 2. Localiza o registro correspondente no banco de dados para checagem de permissão e regeneração
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('''
        SELECT c.id_cautela, c.id_coordenador, c.rdo_vinculado, e.patrimonio_sn,
               e.tipo, e.modelo, e.imei_1, e.imei_2,
               COALESCE(co.nome_completo, u.username, 'Responsável') AS nome_coord,
               COALESCE(co.cpf_matricula, 'N/A') AS cpf_coord,
               c.data_hora_saida,
               COALESCE(e.processador, ''), COALESCE(e.memoria_ram, ''),
               COALESCE(e.armazenamento, ''), COALESCE(e.sistema_operacional, ''),
               COALESCE(e.especificacoes, '')
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        LEFT JOIN usuarios u ON c.id_coordenador = u.id
        ORDER BY c.id_cautela DESC
    ''')
    todas_cautelas = cursor.fetchall()

    cautela_info = None
    arquivo_esperado = None
    for row in todas_cautelas:
        c_id, id_coord, rdo_v, sn_v = row[0], row[1], row[2], row[3]
        nome_esp = formatar_nome_pdf_cautela(rdo_v, sn_v)
        if nome_esp in (nome_seguro, nome_canonico, nome_puro):
            cautela_info = row
            arquivo_esperado = nome_esp
            break
        # Fallback para nomes com espaços substituídos por underscore
        if nome_seguro and (nome_seguro == secure_filename(f"Cautela_{rdo_v}_{sn_v}.pdf")):
            cautela_info = row
            arquivo_esperado = nome_esp
            break

    # 3. Prevenção estrita de IDOR: Coordenador só pode baixar termos pertencentes ao seu usuário
    if current_user.role == 'coordenador':
        cursor.execute('''
            SELECT id FROM coordenadores 
            WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
        ''', (current_user.id, current_user.username, current_user.username))
        ids_coord = [r[0] for r in cursor.fetchall()]
        ids_coord.append(current_user.id)

        if cautela_info:
            id_dono_cautela = cautela_info[1]
            if id_dono_cautela not in ids_coord:
                conexao.close()
                flash("Acesso negado: Você não tem autorização para baixar termos emitidos para outros colaboradores.", "danger")
                return abort(403)
        else:
            conexao.close()
            flash("Acesso não autorizado: Termo de cautela não encontrado ou não pertence a você.", "danger")
            destino = request.referrer if (request.referrer and is_safe_redirect_url(request.referrer)) else url_for('historico')
            return redirect(destino)

    # 4. Regenera sempre a partir do banco para nunca entregar uma versão antiga em cache no disco.
    arquivo_alvo = None
    if cautela_info:
        try:
            c_id, id_coord, rdo_v, sn_v, tipo, modelo, imei1, imei2, nome_c, cpf_c, dt_saida, proc, ram, arm, so, esp = cautela_info
            nome_gerado = gerar_pdf_termo(rdo_v, sn_v, tipo or 'Equipamento', modelo or '', imei1, imei2, nome_c, cpf_c, dt_saida,
                                          processador=proc, memoria_ram=ram, armazenamento=arm, sistema_operacional=so, especificacoes=esp)
            if os.path.exists(os.path.join(caminho_dir, nome_gerado)):
                arquivo_alvo = nome_gerado
        except Exception as e:
            print(f"Aviso seguro: Falha ao regenerar PDF: {e}")

    conexao.close()

    # 5. Se o arquivo existe em disco, envia o PDF diretamente
    if arquivo_alvo and os.path.exists(os.path.join(caminho_dir, arquivo_alvo)):
        resposta = send_from_directory(caminho_dir, arquivo_alvo, conditional=False, max_age=0)
        resposta.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resposta.headers['Pragma'] = 'no-cache'
        return resposta

    # 6. Caso não exista de forma alguma, redireciona adequadamente
    flash(f"O termo em PDF solicitado não foi encontrado.", "warning")
    destino = request.referrer if (request.referrer and is_safe_redirect_url(request.referrer)) else (url_for('historico') if current_user.role == 'admin' else url_for('meus_chamados'))
    return redirect(destino)


@app.route('/cautela')
@app.route('/cautelas')
@login_required
def redirecionar_cautelas():
    """Redireciona amigavelmente rotas diretas de cautela para o Histórico de Cautelas."""
    return redirect(url_for('historico'))


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
               COALESCE(setor, 'Operações') AS setor,
               COALESCE(base, '') AS base
        FROM solicitacoes
        WHERE id_coordenador = ? OR id_coordenador = ?
        ORDER BY id DESC
    ''', (id_coordenador, current_user.id))
    solicitacoes_rows = cursor.fetchall()

    cursor.execute('''
        SELECT c.id_cautela, e.tipo, e.modelo, e.patrimonio_sn, co.nome_completo,
               c.rdo_vinculado, c.data_hora_saida, c.data_hora_devolucao, e.status, c.observacoes,
               COALESCE(s.base, '') AS base_solicitacao,
               COALESCE(s.plataforma, '') AS plataforma_solicitacao,
               COALESCE(s.tipo_uso, 'Operação') AS tipo_uso_solicitacao,
               COALESCE(e.base, 'Tank') AS base_equipamento
        FROM cautelas c
        LEFT JOIN equipamentos e ON c.id_equipamento = e.id
        LEFT JOIN coordenadores co ON c.id_coordenador = co.id
        LEFT JOIN solicitacoes s ON c.id_solicitacao = s.id
        WHERE c.id_coordenador = ? OR c.id_coordenador = ?
        ORDER BY c.id_cautela DESC
    ''', (id_coordenador, current_user.id))
    registros_cautelas = cursor.fetchall()

    contadores = {'Pendente': 0, 'Esperando Entrega': 0, 'Em Operação': 0, 'Finalizada': 0, 'Devolvido': 0, 'Total': 0}

    solicitacoes = []
    for s in solicitacoes_rows:
        id_sol, tipo_eq, qtd, dest, plat, rdo_proj, dt_nec, prio, just, st, dt_cria, tipo_uso, setor, base_val = s
        base_sol = base_val if base_val else inferir_base_operacional(plat, tipo_uso)

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
            'base': base_sol,
            'itens_emitidos': itens_ativos if not is_finalizada else itens_emitidos,
            'itens_devolvidos': itens_devolvidos,
            'qtd_emitida': qtd_emitida,
            'qtd_restante': qtd_restante
        })

    conexao.close()

    chamados = []
    for reg in registros_cautelas:
        id_cautela, tipo, modelo, patrimonio_sn, nome_coord, rdo, data_saida, data_devolucao, status_equip, obs = reg[:10]
        base_sol = reg[10] if len(reg) > 10 and reg[10] else ''
        plat_sol = reg[11] if len(reg) > 11 and reg[11] else ''
        tipo_uso_sol = reg[12] if len(reg) > 12 and reg[12] else 'Operação'
        base_eq = reg[13] if len(reg) > 13 and reg[13] else 'Tank'

        base_cautela = base_sol if base_sol else (inferir_base_operacional(plat_sol, tipo_uso_sol) if plat_sol else (base_eq or 'Tank'))

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
            'base': base_cautela,
            'status': status,
            'badge_class': badge_class,
            'timeline_step': timeline_step,
            'pdf_nome': formatar_nome_pdf_cautela(rdo, patrimonio_sn) if rdo else None
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
        SELECT id, nome_completo, COALESCE(setor, 'Operações'), COALESCE(base, 'Tank') FROM coordenadores 
        WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
    ''', (current_user.id, current_user.username, current_user.username))
    coord_row = cursor.fetchone()
    nome_coordenador = current_user.username
    setor_padrao = 'Operações'
    base_padrao = 'Tank'
    if coord_row:
        id_coordenador = coord_row[0]
        nome_coordenador = coord_row[1]
        setor_padrao = coord_row[2] if len(coord_row) > 2 and coord_row[2] else 'Operações'
        base_padrao = coord_row[3] if len(coord_row) > 3 and coord_row[3] else 'Tank'
    else:
        # Se for um usuário sem registro na tabela de coordenadores (ex: admin), cadastra para respeitar FK
        cursor.execute('SELECT id FROM coordenadores WHERE id = ?', (current_user.id,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO coordenadores (id, nome_completo, cpf_matricula, setor, base)
                VALUES (?, ?, ?, 'TI (Tecnologia da Informação)', 'Tank')
            ''', (current_user.id, current_user.username, f"ADM{current_user.id:06d}"))
            conexao.commit()
        id_coordenador = current_user.id
        nome_coordenador = current_user.username
        setor_padrao = 'TI (Tecnologia da Informação)'
        base_padrao = 'Tank'

    setor_lower = (setor_padrao or '').lower()
    is_ti = ('ti' in setor_lower or 'tecnologia' in setor_lower) or (current_user.role == 'admin')
    is_operacoes = ('opera' in setor_lower) and not is_ti

    if request.method == 'POST':
        tipos = request.form.getlist('tipo_equipamento') or request.form.getlist('tipo_equipamento[]')
        quantidades = request.form.getlist('quantidade') or request.form.getlist('quantidade[]')
        destinatario = (request.form.get('destinatario') or '').strip()[:100]
        tipo_uso = (request.form.get('tipo_uso') or 'Operação').strip()[:30]
        
        # Regras de Setor conforme permissão corporativa
        if is_ti:
            setor = (request.form.get('setor') or setor_padrao).strip()[:50]
        elif is_operacoes:
            setor_req = (request.form.get('setor') or '').strip()
            if setor_req in ('Operações', 'Pátio / Operacional'):
                setor = setor_req
            else:
                setor = 'Operações'
        else:
            # Colaborador padrão (Compras, Financeiro, QSMS, Planejamento, Almoxarifado): setor automático e fixo
            setor = setor_padrao

        plataforma = (request.form.get('plataforma') or '').strip()[:100]
        
        # Regras de Base conforme permissão corporativa
        if is_ti:
            base_informada = (request.form.get('base_operacional') or '').strip()[:50]
            base = inferir_base_operacional(plataforma, tipo_uso, base_informada) or base_padrao
        else:
            # Demais colaboradores: base automática e fixa vinculada ao seu cadastro
            base = base_padrao

        # Ajuste de destino na base quando não for TI
        if tipo_uso == 'Base':
            if not is_ti and not is_operacoes:
                plataforma = f"{base_padrao} - {setor_padrao}"
            elif is_operacoes:
                if not plataforma:
                    plataforma = f"{base_padrao} - {setor}"

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
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao, base_padrao=base_padrao, is_ti=is_ti, is_operacoes=is_operacoes)

        try:
            ids_criados = []
            resumo_itens = []
            for tipo_item, qtd_item in itens_solicitados:
                cursor.execute('''
                    INSERT INTO solicitacoes (id_coordenador, tipo_equipamento, quantidade, destinatario, plataforma, rdo_projeto, data_necessidade, prioridade, justificativa, status, tipo_uso, setor, base)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendente', ?, ?, ?)
                ''', (id_coordenador, tipo_item, qtd_item, destinatario, plataforma, rdo, data_necessidade, prioridade, justificativa, tipo_uso, setor, base))
                ids_criados.append(cursor.lastrowid)
                resumo_itens.append(f"{qtd_item}x {tipo_item}")

            conexao.commit()

            conexao.close()
            for id_criado in ids_criados:
                agendar_notificacao_solicitacao(
                    get_db_connection, id_criado, None,
                    'Sua solicitação foi registrada e aguarda o início do atendimento.'
                )

            if len(ids_criados) == 1:
                flash(f"Chamado #{ids_criados[0]} criado com sucesso! Solicitação de {resumo_itens[0]} ({tipo_uso} - {base} - {setor}) registrada.", "success")
            else:
                ids_str = ", ".join([f"#{i}" for i in ids_criados])
                itens_str = ", ".join(resumo_itens)
                flash(f"{len(ids_criados)} chamados criados com sucesso ({ids_str})! Itens solicitados: {itens_str} ({tipo_uso} - {base} - {setor}).", "success")

            return redirect(url_for('meus_chamados'))
        except Exception as e:
            flash(f"Erro ao registrar chamado(s): {e}", "danger")
            conexao.close()
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao, base_padrao=base_padrao, is_ti=is_ti, is_operacoes=is_operacoes)

    conexao.close()
    return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador, setor_padrao=setor_padrao, base_padrao=base_padrao, is_ti=is_ti, is_operacoes=is_operacoes)


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    porta = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    app.run(debug=debug_mode, host=host, port=porta)
