import sqlite3
import sys
import re
from werkzeug.security import generate_password_hash

def adicionar_coordenador():
    print("\n=======================================================")
    print("  CAVERE - CADASTRO DE COORDENADOR (1o ACESSO)")
    print("=======================================================")
    
    # Coletando os dados do coordenador
    try:
        nome = input("\nNome completo do Coordenador: ").strip()
    except (EOFError, KeyboardInterrupt):
        nome = ""

    if not nome:
        print("Operacao cancelada. Nome obrigatorio.")
        return

    try:
        cpf_matricula = input("Matricula Geral ou CPF (apenas numeros, ex: 104523 ou 12345678900): ").strip()
    except (EOFError, KeyboardInterrupt):
        cpf_matricula = ""

    if not cpf_matricula:
        print("Operacao cancelada. Matricula/CPF obrigatorio.")
        return

    if re.search(r'[a-zA-Z]', cpf_matricula):
        print("\n[ERRO] A Matricula Geral nao contem letras! Digite exclusivamente digitos numericos.")
        return

    setores_validos = [
        "Operações",
        "TI (Tecnologia da Informação)",
        "QSMS",
        "Planejamento",
        "Compras",
        "Financeiro",
        "Almoxarifado"
    ]
    print("\nSetores disponíveis:")
    for idx, s in enumerate(setores_validos, start=1):
        print(f"  [{idx}] {s}")

    try:
        escolha_setor = input("\nEscolha o número ou digite o nome do Setor [Padrão: 1 - Operações]: ").strip()
    except (EOFError, KeyboardInterrupt):
        escolha_setor = ""

    if escolha_setor.isdigit() and 1 <= int(escolha_setor) <= len(setores_validos):
        setor = setores_validos[int(escolha_setor) - 1]
    elif any(escolha_setor.lower() == s.lower() for s in setores_validos):
        setor = next(s for s in setores_validos if escolha_setor.lower() == s.lower())
    else:
        setor = "Operações"

    # Sugestão de nome de usuário para login
    primeiro_nome = nome.split()[0].lower()
    sugestao_user = re.sub(r'[^a-z0-9]', '', primeiro_nome) + ".coord"
    
    try:
        user_input = input(f"Usuario de login [Padrao: {sugestao_user}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        user_input = ""

    username = user_input if user_input else sugestao_user

    # Senha padrão temporária (123)
    try:
        senha_input = input("Senha padrao temporaria [Pressione ENTER para '123']: ").strip()
    except (EOFError, KeyboardInterrupt):
        senha_input = ""

    senha_plana = senha_input if senha_input else "123"

    # Conecta ao banco de dados Cavere
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()

    # Garante que as tabelas existam
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coordenadores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome_completo TEXT NOT NULL,
            cpf_matricula TEXT UNIQUE NOT NULL,
            setor TEXT DEFAULT 'Operações'
        )
    ''')

    cursor.execute("PRAGMA table_info(coordenadores)")
    cols_coord = [c[1] for c in cursor.fetchall()]
    if 'setor' not in cols_coord:
        cursor.execute("ALTER TABLE coordenadores ADD COLUMN setor TEXT DEFAULT 'Operações'")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            trocar_senha INTEGER DEFAULT 0
        )
    ''')

    cursor.execute("PRAGMA table_info(usuarios)")
    colunas = [c[1] for c in cursor.fetchall()]
    if 'trocar_senha' not in colunas:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN trocar_senha INTEGER DEFAULT 0")

    senha_hash = generate_password_hash(senha_plana)

    try:
        # Insere em usuarios com trocar_senha = 1
        cursor.execute('''
            INSERT INTO usuarios (username, senha_hash, role, trocar_senha)
            VALUES (?, ?, 'coordenador', 1)
        ''', (username, senha_hash))
        novo_id = cursor.lastrowid

        # Insere em coordenadores com o mesmo ID
        cursor.execute('''
            INSERT INTO coordenadores (id, nome_completo, cpf_matricula, setor)
            VALUES (?, ?, ?, ?)
        ''', (novo_id, nome, cpf_matricula, setor))
        
        conexao.commit()
        print(f"\n[SUCESSO] Coordenador(a) / Solicitante '{nome}' ({setor}) cadastrado(a) com sucesso!")
        print(f"[LOGIN] Usuario: '{username}' | Senha temporaria: '{senha_plana}'")
        print("[INFO] No primeiro acesso, o sistema exigira a troca obrigatoria de senha.")
        
    except sqlite3.IntegrityError as e:
        if "coordenadores.cpf_matricula" in str(e):
            print(f"\n[ERRO] Ja existe um coordenador cadastrado com o CPF/Matricula '{cpf_matricula}'!")
        elif "usuarios.username" in str(e):
            print(f"\n[ERRO] O nome de usuario '{username}' ja esta em uso no sistema. Escolha outro.")
        else:
            print(f"\n[ERRO] Violacao de registro unico: {e}")
    except Exception as e:
        print(f"\n[ERRO INESPERADO] {e}")
    finally:
        conexao.close()

if __name__ == '__main__':
    adicionar_coordenador()
