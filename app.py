# Sistema Cavere - Gestão e Controle de Cautelas - Ambipar Response
import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from weasyprint import HTML

app = Flask(__name__)

# Configuração de SECRET_KEY forte para proteção contra sequestro de sessão (Session Hijacking)
SECRET_KEY_PADRAO = "cavere_sec_2026_8f3c7e2b904d16e5f82c49b1a7d6e3c0f5928a74e1d3b6c5a8f2e9d0c1b4a7e"
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', SECRET_KEY_PADRAO)
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Impede que scripts maliciosos acessem os cookies de sessão (mitiga XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Proteção contra ataques CSRF

# Configuração do Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "warning"


# Modelo de Usuário para autenticação
class Usuario(UserMixin):
    def __init__(self, id, username, senha_hash, role):
        self.id = id
        self.username = username
        self.senha_hash = senha_hash
        self.role = role

    @property
    def is_admin(self):
        return self.role == 'admin'


@login_manager.user_loader
def load_user(user_id):
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    cursor.execute('SELECT id, username, senha_hash, role FROM usuarios WHERE id = ?', (user_id,))
    dados = cursor.fetchone()
    conexao.close()
    if dados:
        return Usuario(id=dados[0], username=dados[1], senha_hash=dados[2], role=dados[3])
    return None


def inicializar_banco():
    """
    Cria as tabelas 'usuarios' e 'solicitacoes' no SQLite caso não existam,
    garante a coluna 'id_solicitacao' na tabela 'cautelas' e inicializa um usuário admin padrão.
    """
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'coordenador'))
        )
    ''')

    # Tabela para chamados de solicitação de equipamentos (estilo Service Desk/TI)
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
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(id_coordenador) REFERENCES coordenadores(id)
        )
    ''')
    
    # Garante a coluna id_solicitacao na tabela cautelas
    cursor.execute("PRAGMA table_info(cautelas)")
    colunas_cautelas = [col[1] for col in cursor.fetchall()]
    if 'id_solicitacao' not in colunas_cautelas:
        cursor.execute("ALTER TABLE cautelas ADD COLUMN id_solicitacao INTEGER")

    # Se não houver nenhum usuário, cria o admin padrão com senha criptografada
    cursor.execute('SELECT COUNT(*) FROM usuarios')
    if cursor.fetchone()[0] == 0:
        senha_criptografada = generate_password_hash('admin123')
        cursor.execute('''
            INSERT INTO usuarios (username, senha_hash, role)
            VALUES (?, ?, ?)
        ''', ('admin', senha_criptografada, 'admin'))
        
    conexao.commit()
    conexao.close()

# Inicializa as tabelas necessárias no banco
inicializar_banco()


def salvar_novo_usuario(username, senha_pura, role='coordenador', id_personalizado=None, nome_completo=None, cpf_matricula=None):
    """
    Cadastra um novo usuário no banco com senha criptografada.
    Se o papel for 'coordenador', cadastra atomicamente em 'usuarios' e 'coordenadores' com o MESMO ID.
    Permite escolher um ID personalizado (se disponível) ou gerar automaticamente.
    """
    if role not in ('admin', 'coordenador'):
        return False, "O papel (role) deve ser 'admin' ou 'coordenador'."

    if role == 'coordenador':
        if not nome_completo or not cpf_matricula:
            return False, "Para cadastro de Coordenador, o Nome Completo e CPF/Matrícula são obrigatórios."

    senha_hash = generate_password_hash(senha_pura)
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    try:
        # Se um ID personalizado foi informado, valida disponibilidade
        if id_personalizado:
            try:
                id_personalizado = int(id_personalizado)
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
                INSERT INTO usuarios (id, username, senha_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (id_personalizado, username, senha_hash, role))
            user_id = id_personalizado
        else:
            cursor.execute('''
                INSERT INTO usuarios (username, senha_hash, role)
                VALUES (?, ?, ?)
            ''', (username, senha_hash, role))
            user_id = cursor.lastrowid

        # Se for coordenador, cadastra na tabela coordenadores com o MESMO ID
        if role == 'coordenador':
            cursor.execute('SELECT id FROM coordenadores WHERE id = ?', (user_id,))
            existe_coord = cursor.fetchone()
            if existe_coord:
                cursor.execute('''
                    UPDATE coordenadores 
                    SET nome_completo = ?, cpf_matricula = ?
                    WHERE id = ?
                ''', (nome_completo, cpf_matricula, user_id))
            else:
                cursor.execute('''
                    INSERT INTO coordenadores (id, nome_completo, cpf_matricula)
                    VALUES (?, ?, ?)
                ''', (user_id, nome_completo, cpf_matricula))

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


# --- CONTROLE GLOBAL DE ACESSO E AUTENTICAÇÃO ---

@app.before_request
def exigir_autenticacao():
    # Permite requisições sem endpoint (ex: erro 404) ou arquivos estáticos e rota de login
    if request.endpoint is None or request.endpoint in ('login', 'static'):
        return None

    # Exige autenticação em todas as outras rotas do sistema
    if not current_user.is_authenticated:
        return login_manager.unauthorized()

    # Regra de perfil (RBAC):
    # O coordenador tem acesso a: meus chamados, solicitação de equipamento, logout, download de termos e estáticos
    if current_user.role == 'coordenador':
        rotas_permitidas_coordenador = ('meus_chamados', 'solicitar_equipamento', 'logout', 'static', 'download_cautela')
        if request.endpoint not in rotas_permitidas_coordenador:
            flash("Acesso restrito: seu perfil de Coordenador permite acessar apenas a página de Meus Chamados e Solicitação de Equipamento.", "warning")
            return redirect(url_for('meus_chamados'))


# --- ROTAS DE AUTENTICAÇÃO E USUÁRIOS ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'coordenador':
            return redirect(url_for('meus_chamados'))
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form.get('username')
        senha = request.form.get('senha')

        conexao = sqlite3.connect('Cavere.db')
        cursor = conexao.cursor()
        cursor.execute('SELECT id, username, senha_hash, role FROM usuarios WHERE username = ?', (username,))
        dados = cursor.fetchone()
        conexao.close()

        if dados and check_password_hash(dados[2], senha):
            usuario = Usuario(id=dados[0], username=dados[1], senha_hash=dados[2], role=dados[3])
            login_user(usuario)
            flash(f"Bem-vindo, {usuario.username}!", "success")

            # Regra: se o usuário tiver a role 'admin', vai para o painel principal.
            # Se for 'coordenador', só pode acessar a rota /meus-chamados.
            if usuario.role == 'coordenador':
                return redirect(url_for('meus_chamados'))
            else:
                proxima = request.args.get('next')
                if proxima and proxima.startswith('/'):
                    return redirect(proxima)
                return redirect(url_for('home'))
        else:
            flash("Usuário ou senha inválidos. Tente novamente.", "danger")

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Sessão finalizada com sucesso.", "info")
    return redirect(url_for('login'))


def gerar_pdf_termo(rdo, sn, tipo, modelo, imei1, imei2, nome_coord, cpf_coord, data_str=None):
    """
    Gera e salva o PDF do Termo de Cautela na pasta Cautelas/
    Retorna o nome do arquivo gerado.
    """
    if not data_str:
        data_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    imei1_texto = imei1 if imei1 else "N/A"
    imei2_texto = imei2 if imei2 else "N/A"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
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
            <tr><th>Nome</th><td>{nome_coord}</td></tr>
            <tr><th>CPF/Matrícula</th><td>{cpf_coord}</td></tr>
            <tr><th>RDO Vinculado</th><td>{rdo}</td></tr>
        </table>

        <div class="section-title">Dados do Equipamento</div>
        <table>
            <tr><th>Tipo</th><td>{tipo}</td></tr>
            <tr><th>Modelo</th><td>{modelo}</td></tr>
            <tr><th>Patrimônio / SN</th><td>{sn}</td></tr>
            <tr><th>IMEI 1</th><td>{imei1_texto}</td></tr>
            <tr><th>IMEI 2</th><td>{imei2_texto}</td></tr>
        </table>
        
        <div class="signature">
            <div class="line"></div>
            <p><strong>{nome_coord}</strong><br>Assinatura do Responsável<br>Data: {data_str}</p>
        </div>
    </body>
    </html>
    """
    os.makedirs('Cautelas', exist_ok=True)
    nome_arquivo = f"Cautela_{rdo}_{sn}.pdf"
    caminho_arquivo = os.path.join('Cautelas', nome_arquivo)
    HTML(string=html_content).write_pdf(caminho_arquivo)
    return nome_arquivo


@app.route('/cadastrar-usuario', methods=['GET', 'POST'])
def cadastrar_usuario():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        senha = request.form.get('senha', '').strip()
        role = request.form.get('role', 'coordenador')
        id_custom = request.form.get('id_custom', '').strip()
        nome_completo = request.form.get('nome_completo', '').strip()
        cpf = request.form.get('cpf', '').strip()

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
            cpf_matricula=cpf if role == 'coordenador' else None
        )
        if sucesso:
            flash(mensagem, "success")
            return redirect(url_for('home'))
        else:
            flash(mensagem, "danger")

    return render_template('cadastrar_usuario.html')


# --- ROTAS PRINCIPAIS DO SISTEMA ---

# Rota Principal (Painel de Controle do Administrador)
@app.route('/')
def home():
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    
    # Busca equipamentos para a listagem
    cursor.execute('SELECT id, tipo, modelo, patrimonio_sn, imei_1, imei_2, status FROM equipamentos ORDER BY id DESC')
    equipamentos = cursor.fetchall()
    
    # Busca coordenadores para a listagem
    cursor.execute('SELECT id, nome_completo, cpf_matricula FROM coordenadores ORDER BY id DESC')
    coordenadores = cursor.fetchall()

    # Busca solicitações recentes de equipamentos (chamados abertos por coordenadores)
    cursor.execute('''
        SELECT s.id, 
               COALESCE(co.nome_completo, u.username, 'Coordenador #' || s.id_coordenador) AS nome_coord,
               s.tipo_equipamento, s.quantidade, s.destinatario, 
               s.plataforma, s.rdo_projeto, s.prioridade, s.status, s.data_criacao, s.id_coordenador
        FROM solicitacoes s
        LEFT JOIN coordenadores co ON s.id_coordenador = co.id
        LEFT JOIN usuarios u ON s.id_coordenador = u.id
        ORDER BY s.id DESC
    ''')
    solicitacoes = cursor.fetchall()

    # Busca cautelas geradas com detalhes e link de PDF para o dashboard do administrador
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


# Rota para Gerar Termo de Cautela e PDF
@app.route('/gerar', methods=['POST'])
def gerar():
    id_equipamento = request.form.get('id_equipamento')
    id_coordenador = request.form.get('id_coordenador')
    rdo = request.form.get('rdo', '').strip()
    id_solicitacao = request.form.get('id_solicitacao', '').strip()

    if not id_equipamento or not id_coordenador or not rdo:
        flash("Por favor, selecione o Equipamento, o Coordenador e informe o RDO.", "warning")
        return redirect(url_for('home'))

    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    try:
        # 1. Busca os dados do Equipamento no banco
        cursor.execute('SELECT tipo, modelo, patrimonio_sn, imei_1, imei_2, status FROM equipamentos WHERE id = ?', (id_equipamento,))
        equip = cursor.fetchone()
        
        # 2. Busca os dados do Coordenador
        cursor.execute('SELECT id, nome_completo, cpf_matricula FROM coordenadores WHERE id = ?', (id_coordenador,))
        coord = cursor.fetchone()

        # Fallback inteligente: se não encontrou por ID em coordenadores, procura em usuarios
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
        
        # 3. Registra na tabela cautelas
        id_sol_int = int(id_solicitacao) if id_solicitacao and id_solicitacao.isdigit() else None
        cursor.execute('''
            INSERT INTO cautelas (id_equipamento, id_coordenador, rdo_vinculado, id_solicitacao) 
            VALUES (?, ?, ?, ?)
        ''', (id_equipamento, id_coordenador, rdo, id_sol_int))
        
        # Atualiza status do equipamento para 'Em Operação'
        cursor.execute("UPDATE equipamentos SET status = 'Em Operação' WHERE id = ?", (id_equipamento,))

        # 4. Atualiza o status da solicitação vinculada para 'Esperando Entrega'
        if id_sol_int:
            cursor.execute("UPDATE solicitacoes SET status = 'Esperando Entrega' WHERE id = ?", (id_sol_int,))
        else:
            # Tenta vincular e atualizar solicitação pendente do mesmo coordenador e RDO
            cursor.execute('''
                UPDATE solicitacoes 
                SET status = 'Esperando Entrega' 
                WHERE (id_coordenador = ? OR id_coordenador = ?) 
                  AND (rdo_projeto = ? OR rdo_projeto IS NULL OR rdo_projeto = '')
                  AND status = 'Pendente'
            ''', (id_coordenador, coord_id, rdo))

        conexao.commit()
        
        # 5. Gera e salva o PDF na pasta Cautelas
        nome_arquivo = gerar_pdf_termo(rdo, sn, tipo, modelo, imei1, imei2, nome_coord, cpf_coord)
        
        flash(f"✅ Termo de Cautela gerado com sucesso para {nome_coord}! Status da solicitação alterado para 'Esperando Entrega'. Arquivo: {nome_arquivo}", "success")
        
    except Exception as e:
        flash(f"❌ Erro ao gerar cautela: {e}", "danger")
        print(f"Erro no sistema Cavere: {e}")
    finally:
        conexao.close()

    return redirect(url_for('home'))


# Rota para marcar Solicitação como Equipamento Entregue / Finalizada
@app.route('/solicitacao/entregar/<int:id_solicitacao>', methods=['GET', 'POST'])
def entregar_solicitacao(id_solicitacao):
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    try:
        cursor.execute("UPDATE solicitacoes SET status = 'Finalizada' WHERE id = ?", (id_solicitacao,))
        conexao.commit()
        flash(f"✅ Equipamento da solicitação #SOL-{id_solicitacao} marcado como entregue! Chamado finalizado com sucesso.", "success")
    except Exception as e:
        flash(f"Erro ao finalizar solicitação: {e}", "danger")
    finally:
        conexao.close()
    return redirect(url_for('home'))


# Rota para Formulário de Novo Equipamento
@app.route('/novo-equipamento')
def novo_equipamento():
    return render_template('cadastrar_equipamento.html')


# Rota para Salvar Novo Equipamento
@app.route('/salvar-equipamento', methods=['POST'])
def salvar_equipamento():
    tipo = request.form.get('tipo')
    modelo = request.form.get('modelo')
    patrimonio = request.form.get('patrimonio')
    imei1 = request.form.get('imei1', '')
    imei2 = request.form.get('imei2', '')
    
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    try:
        cursor.execute('''
            INSERT INTO equipamentos (tipo, modelo, patrimonio_sn, imei_1, imei_2, status)
            VALUES (?, ?, ?, ?, ?, 'Disponível')
        ''', (tipo, modelo, patrimonio, imei1, imei2))
        conexao.commit()
        flash(f"Equipamento '{tipo} - {modelo}' cadastrado com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao cadastrar equipamento: {e}")
    finally:
        conexao.close()
        
    return redirect(url_for('home'))


# Redirecionamento da antiga rota de coordenador para a criação unificada de login
@app.route('/novo-coordenador')
def novo_coordenador():
    flash("O cadastro de coordenadores foi unificado à criação de login. Cadastre o coordenador abaixo.", "info")
    return redirect(url_for('cadastrar_usuario'))


@app.route('/salvar-coordenador', methods=['POST'])
def salvar_coordenador():
    return redirect(url_for('cadastrar_usuario'))


# Rota para Devolver Equipamento
@app.route('/devolver/<int:id_equipamento>')
def devolver(id_equipamento):
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()
    try:
        # 1. Muda o status do equipamento para Disponível
        cursor.execute("UPDATE equipamentos SET status = 'Disponível' WHERE id = ?", (id_equipamento,))
        # 2. Carimba a data de devolução na tabela de cautelas (na última saída sem devolução)
        cursor.execute('''
            UPDATE cautelas 
            SET data_hora_devolucao = ? 
            WHERE id_equipamento = ? AND data_hora_devolucao IS NULL
        ''', (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_equipamento))
        
        conexao.commit()
        flash("Equipamento devolvido com sucesso! Status atualizado para Disponível.", "success")
    except Exception as e:
        flash(f"Erro ao devolver equipamento: {e}", "danger")
    finally:
        conexao.close()
    return redirect(url_for('home'))


# Rota para a Página de Histórico Completo
@app.route('/historico')
def historico():
    conexao = sqlite3.connect('Cavere.db')
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


# Rota para Acessar/Baixar os PDFs de Cautela (com regeneração sob demanda se o arquivo não estiver em disco)
@app.route('/cautelas/<path:filename>')
def download_cautela(filename):
    caminho = os.path.join('Cautelas', filename)
    if not os.path.exists(caminho):
        try:
            partes = filename.replace("Cautela_", "").replace(".pdf", "").rsplit("_", 1)
            if len(partes) == 2:
                rdo_busca, sn_busca = partes[0], partes[1]
                conexao = sqlite3.connect('Cavere.db')
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
            print(f"Aviso: Não foi possível auto-regenerar PDF {filename}: {e}")

    if os.path.exists(caminho):
        return send_from_directory('Cautelas', filename)
    flash(f"O termo em PDF '{filename}' não foi encontrado.", "warning")
    return redirect(url_for('home'))


# Rota exclusiva para Coordenadores: visualização de Meus Chamados
@app.route('/meus-chamados')
def meus_chamados():
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()

    # 1. Identifica o ID do coordenador logado
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

    # 2. Busca solicitações de equipamentos (chamados de TI/Operações) feitas pelo coordenador
    cursor.execute('''
        SELECT id, tipo_equipamento, quantidade, destinatario, plataforma,
               rdo_projeto, data_necessidade, prioridade, justificativa, status, data_criacao
        FROM solicitacoes
        WHERE id_coordenador = ? OR id_coordenador = ?
        ORDER BY id DESC
    ''', (id_coordenador, current_user.id))
    solicitacoes_rows = cursor.fetchall()

    # 3. Busca no SQLite (tabela cautelas) os registros emitidos pertencentes ao coordenador logado
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
    conexao.close()

    contadores = {'Pendente': 0, 'Esperando Entrega': 0, 'Em Operação': 0, 'Finalizada': 0, 'Total': 0}

    # Formata solicitações (chamados de equipamentos)
    solicitacoes = []
    for s in solicitacoes_rows:
        id_sol, tipo_eq, qtd, dest, plat, rdo_proj, dt_nec, prio, just, st, dt_cria = s

        if st in ('Devolvido', 'Concluído', 'Finalizado', 'Finalizada'):
            st_label = 'Finalizada'
            badge_class = 'bg-success'
            timeline_step = 3
        elif st == 'Esperando Entrega':
            st_label = 'Esperando Entrega'
            badge_class = 'bg-warning text-dark'
            timeline_step = 2
        elif st in ('Em Operação', 'Em Atendimento', 'Aprovado'):
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
            'data_criacao': dt_cria
        })

    # Formata cautelas de equipamentos já emitidas
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


# Rota para Solicitação de Equipamento (Chamado de TI/Operações para Coordenadores)
@app.route('/solicitar-equipamento', methods=['GET', 'POST'])
def solicitar_equipamento():
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()

    # Identifica o coordenador logado
    id_coordenador = current_user.id
    cursor.execute('''
        SELECT id, nome_completo FROM coordenadores 
        WHERE id = ? OR LOWER(nome_completo) = LOWER(?) OR LOWER(cpf_matricula) = LOWER(?)
    ''', (current_user.id, current_user.username, current_user.username))
    coord_row = cursor.fetchone()
    nome_coordenador = current_user.username
    if coord_row:
        id_coordenador = coord_row[0]
        nome_coordenador = coord_row[1]

    if request.method == 'POST':
        tipo = request.form.get('tipo_equipamento')
        quantidade = request.form.get('quantidade', 1, type=int)
        destinatario = request.form.get('destinatario', '').strip()
        plataforma = request.form.get('plataforma', '').strip()
        rdo = request.form.get('rdo_projeto', '').strip()
        data_necessidade = request.form.get('data_necessidade', '')
        prioridade = request.form.get('prioridade', 'Normal')
        justificativa = request.form.get('justificativa', '').strip()

        if not tipo or not destinatario or not plataforma:
            flash("Por favor, preencha o tipo de equipamento, o destinatário e a plataforma de destino.", "warning")
            conexao.close()
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador)

        try:
            cursor.execute('''
                INSERT INTO solicitacoes (id_coordenador, tipo_equipamento, quantidade, destinatario, plataforma, rdo_projeto, data_necessidade, prioridade, justificativa, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pendente')
            ''', (id_coordenador, tipo, quantidade, destinatario, plataforma, rdo, data_necessidade, prioridade, justificativa))
            conexao.commit()
            id_chamado = cursor.lastrowid
            flash(f"✅ Chamado #{id_chamado} criado com sucesso! Solicitação de {quantidade}x {tipo} para '{destinatario}' ({plataforma}) registrada.", "success")
            conexao.close()
            return redirect(url_for('meus_chamados'))
        except Exception as e:
            flash(f"Erro ao registrar chamado: {e}", "danger")
            conexao.close()
            return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador)

    conexao.close()
    return render_template('solicitar_equipamento.html', nome_coordenador=nome_coordenador, id_coordenador=id_coordenador)


if __name__ == '__main__':
    app.run(debug=True)