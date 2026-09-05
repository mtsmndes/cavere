import sqlite3
from werkzeug.security import generate_password_hash

conexao = sqlite3.connect('Cavere.db')
cursor = conexao.cursor()

# Cria o usuário admin com a senha '123' (já criptografada)
senha_segura = generate_password_hash('123')

try:
    cursor.execute('''
        INSERT INTO usuarios (username, senha_hash, role)
        VALUES (?, ?, ?)
    ''', ('administrador', senha_segura, 'admin'))
    conexao.commit()
    print("✅ Usuário 'administrador' criado com sucesso! Senha: 123")
except sqlite3.IntegrityError:
    print("⚠️ O usuário 'administrador' já existe no banco.")
finally:
    conexao.close()