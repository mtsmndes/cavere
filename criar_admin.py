import sqlite3
import sys
from werkzeug.security import generate_password_hash

def criar_ou_atualizar_admin():
    print("\n=======================================================")
    print("  CAVERE - CADASTRO DE ADMINISTRADOR (1o ACESSO)")
    print("=======================================================")

    # 1. Escolha do nome de usuário
    try:
        username_input = input("\nNome de usuario para o Administrador [Padrao: administrador]: ").strip()
    except (EOFError, KeyboardInterrupt):
        username_input = ""

    username = username_input if username_input else "administrador"

    # 2. Senha padrão temporária (123)
    try:
        senha_input = input("Senha padrao temporaria [Pressione ENTER para '123']: ").strip()
    except (EOFError, KeyboardInterrupt):
        senha_input = ""

    senha_plana = senha_input if senha_input else "123"

    # 3. Conecta ao banco de dados Cavere
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()

    # Garante que a tabela 'usuarios' e a coluna 'trocar_senha' existam
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

    # Verifica se o usuário já existe
    cursor.execute('SELECT id FROM usuarios WHERE username = ?', (username,))
    existente = cursor.fetchone()

    if existente:
        print(f"\nO usuario '{username}' ja existe no banco de dados.")
        try:
            opcao = input("Deseja redefinir a senha deste admin para a senha temporaria com troca obrigatoria? (S/N): ").strip().upper()
        except (EOFError, KeyboardInterrupt):
            opcao = "S"

        if opcao in ('S', 'SIM', 'Y', ''):
            cursor.execute('''
                UPDATE usuarios 
                SET senha_hash = ?, role = 'admin', trocar_senha = 1 
                WHERE id = ?
            ''', (senha_hash, existente[0]))
            conexao.commit()
            print(f"\n[SUCESSO] Administrador '{username}' atualizado com senha temporaria '{senha_plana}'!")
            print("[INFO] No proximo login, o sistema exigira a troca imediata de senha na nova interface.")
        else:
            print("\nOperacao cancelada. Nenhuma alteracao realizada.")
    else:
        cursor.execute('''
            INSERT INTO usuarios (username, senha_hash, role, trocar_senha)
            VALUES (?, ?, 'admin', 1)
        ''', (username, senha_hash))
        conexao.commit()
        print(f"\n[SUCESSO] Administrador '{username}' criado com sucesso!")
        print(f"[INFO] Senha padrao temporaria: '{senha_plana}'")
        print("[INFO] No primeiro login, o sistema redirecionara automaticamente para a tela de troca de senha.")

    conexao.close()

if __name__ == '__main__':
    criar_ou_atualizar_admin()