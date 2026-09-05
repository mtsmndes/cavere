import sqlite3

def adicionar_equipamento():
    print("\n--- 📦 CADASTRAR NOVO EQUIPAMENTO NO CAVERE ---")
    
    # Coletando os dados do usuário no terminal
    tipo = input("Qual o Tipo? (ex: Celular, Câmera): ")
    modelo = input("Qual o Modelo? (ex: Samsung A54, Nikon D3100): ")
    patrimonio = input("Número de Patrimônio / SN: ")
    
    # Lógica para pedir IMEI apenas se for celular
    imei1 = ""
    imei2 = ""
    if tipo.lower() == 'celular' or tipo.lower() == 'smartphone':
        imei1 = input("Digite o IMEI 1: ")
        imei2 = input("Digite o IMEI 2: ")
    
    # 1. Conecta ao banco de dados
    conexao = sqlite3.connect('cavere.db')
    cursor = conexao.cursor()
    
    try:
        # 2. Insere os dados na tabela 'equipamentos'
        cursor.execute('''
            INSERT INTO equipamentos (tipo, modelo, patrimonio_sn, imei_1, imei_2, status)
            VALUES (?, ?, ?, ?, ?, 'Disponível')
        ''', (tipo, modelo, patrimonio, imei1, imei2))
        
        # 3. Salva a transação
        conexao.commit()
        print(f"\n✅ SUCESSO: {tipo} ({modelo}) cadastrado e Disponível no estoque!")
        
    except sqlite3.IntegrityError:
        # Se você tentar cadastrar o mesmo SN duas vezes, o banco bloqueia!
        print(f"\n❌ ERRO: Já existe um equipamento com o SN '{patrimonio}' no banco!")
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
    finally:
        conexao.close()

# Rodando o programa
adicionar_equipamento()