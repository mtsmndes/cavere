import sqlite3

def adicionar_equipamento():
    print("\n=======================================================")
    print("  CAVERE - CADASTRAR NOVO EQUIPAMENTO")
    print("=======================================================")
    
    # Coletando os dados do usuário no terminal
    try:
        tipo = input("Qual o Tipo? (ex: Celular, Camera, Radio): ").strip()
    except (EOFError, KeyboardInterrupt):
        tipo = ""

    if not tipo:
        print("Operacao cancelada. Tipo obrigatorio.")
        return

    try:
        modelo = input("Qual o Modelo? (ex: Samsung A54, Nikon D3100): ").strip()
    except (EOFError, KeyboardInterrupt):
        modelo = ""

    try:
        patrimonio = input("Numero de Patrimonio / SN: ").strip()
    except (EOFError, KeyboardInterrupt):
        patrimonio = ""

    if not patrimonio:
        print("Operacao cancelada. Patrimonio/SN obrigatorio.")
        return
    
    # Lógica para pedir IMEI apenas se for celular ou smartphone
    imei1 = ""
    imei2 = ""
    if tipo.lower() in ['celular', 'smartphone']:
        try:
            imei1 = input("Digite o IMEI 1: ").strip()
            imei2 = input("Digite o IMEI 2: ").strip()
        except (EOFError, KeyboardInterrupt):
            pass
    
    # 1. Conecta ao banco de dados Cavere
    conexao = sqlite3.connect('Cavere.db')
    cursor = conexao.cursor()

    # Garante que a tabela 'equipamentos' exista
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
    
    try:
        # 2. Insere os dados na tabela 'equipamentos' com status inicial 'Disponível'
        cursor.execute('''
            INSERT INTO equipamentos (tipo, modelo, patrimonio_sn, imei_1, imei_2, status)
            VALUES (?, ?, ?, ?, ?, 'Disponível')
        ''', (tipo, modelo, patrimonio, imei1, imei2))
        
        # 3. Salva a transação no banco
        conexao.commit()
        print(f"\n[SUCESSO] {tipo} ({modelo}) cadastrado e Disponivel no estoque!")
        
    except sqlite3.IntegrityError:
        print(f"\n[ERRO] Ja existe um equipamento com o Patrimonio/SN '{patrimonio}' no banco!")
    except Exception as e:
        print(f"\n[ERRO INESPERADO] {e}")
    finally:
        conexao.close()

# Rodando o programa
if __name__ == '__main__':
    adicionar_equipamento()