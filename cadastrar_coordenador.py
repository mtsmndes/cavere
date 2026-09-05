import sqlite3

def adicionar_coordenador():
    print("\n--- 👤 CADASTRAR NOVO COORDENADOR NO CAVERE ---")
    
    # Coletando os dados do coordenador
    nome = input("Nome completo do Coordenador: ")
    cpf_matricula = input("CPF ou Matrícula (ex: 123.456.789-00 ou M12345): ")
    
    # 1. Conecta ao banco de dados Cavere
    conexao = sqlite3.connect('cavere.db')
    cursor = conexao.cursor()
    
    try:
        # 2. Insere os dados na tabela 'coordenadores'
        cursor.execute('''
            INSERT INTO coordenadores (nome_completo, cpf_matricula)
            VALUES (?, ?)
        ''', (nome, cpf_matricula))
        
        # 3. Salva as alterações
        conexao.commit()
        print(f"\n✅ SUCESSO: Coordenador(a) '{nome}' cadastrado(a) com ID e pronto para solicitar cautelas!")
        
    except sqlite3.IntegrityError:
        # Se tentar cadastrar a mesma matrícula/CPF duas vezes, o banco barra
        print(f"\n❌ ERRO: Já existe um coordenador cadastrado com o CPF/Matrícula '{cpf_matricula}'!")
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO: {e}")
    finally:
        conexao.close()

# Rodando o programa
adicionar_coordenador()
