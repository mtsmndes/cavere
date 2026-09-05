import sqlite3

def realizar_cautela(id_equipamento, id_coordenador, rdo):
    # 1. Conecta ao nosso banco de dados Cavere
    conexao = sqlite3.connect('cavere.db')
    cursor = conexao.cursor()
    
    try:
        # 2. Registra a saída na tabela de cautelas (Check-out)
        cursor.execute('''
            INSERT INTO cautelas (id_equipamento, id_coordenador, rdo_vinculado)
            VALUES (?, ?, ?)
        ''', (id_equipamento, id_coordenador, rdo))
        
        # 3. Atualiza o status do equipamento para "Em Operação"
        cursor.execute('''
            UPDATE equipamentos 
            SET status = 'Em Operação' 
            WHERE id = ?
        ''', (id_equipamento,))
        
        # Salva as alterações
        conexao.commit()
        print(f"✅ SUCESSO: Cautela registrada para o RDO {rdo}!")
        
        # 4. Busca os dados atualizados para confirmar
        cursor.execute('SELECT modelo, patrimonio_sn, status FROM equipamentos WHERE id = ?', (id_equipamento,))
        equip = cursor.fetchone()
        
        print("-" * 40)
        print("RESUMO DO EQUIPAMENTO APÓS A CAUTELA:")
        print(f"Modelo: {equip[0]}")
        print(f"Patrimônio/SN: {equip[1]}")
        print(f"Status Atual: {equip[2]} 🔴") # Deve mostrar 'Em Operação'
        print("-" * 40)

    except Exception as e:
        print(f"Erro ao registrar cautela: {e}")
        
    finally:
        conexao.close()

# --- TESTANDO O SISTEMA CAVERE ---

# Simulando a operação:
# O Coordenador de ID 1 (João) pediu o Equipamento de ID 1 (Samsung XCover) para o RDO-2026-0905
print("Iniciando o Check-out no Cavere...\n")
realizar_cautela(id_equipamento=1, id_coordenador=1, rdo='RDO-2026-0905')