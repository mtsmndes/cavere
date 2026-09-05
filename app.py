import sqlite3
from datetime import datetime
from weasyprint import HTML

def realizar_cautela_com_pdf(id_equipamento, id_coordenador, rdo):
    conexao = sqlite3.connect('cavere.db')
    cursor = conexao.cursor()
    
    try:
        # 1. Busca os dados do Equipamento e do Coordenador no banco
        cursor.execute('SELECT tipo, modelo, patrimonio_sn, imei_1, imei_2 FROM equipamentos WHERE id = ?', (id_equipamento,))
        equip = cursor.fetchone()
        
        cursor.execute('SELECT nome_completo, cpf_matricula FROM coordenadores WHERE id = ?', (id_coordenador,))
        coord = cursor.fetchone()
        
        if not equip or not coord:
            print("❌ Erro: Equipamento ou Coordenador não encontrados no banco.")
            return

        tipo, modelo, sn, imei1, imei2 = equip
        nome_coord, cpf_coord = coord
        
        # 2. Registra no banco de dados (A saída)
        cursor.execute('INSERT INTO cautelas (id_equipamento, id_coordenador, rdo_vinculado) VALUES (?, ?, ?)', 
                       (id_equipamento, id_coordenador, rdo))
        cursor.execute("UPDATE equipamentos SET status = 'Em Operação' WHERE id = ?", (id_equipamento,))
        conexao.commit()
        
        # 3. Prepara os dados para o PDF
        data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
        imei1_texto = imei1 if imei1 else "N/A" # Se for câmera, não tem IMEI
        imei2_texto = imei2 if imei2 else "N/A"
        
        # 4. Desenha o documento usando HTML (f-strings do Python para injetar as variáveis)
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
                <p><strong>{nome_coord}</strong><br>Assinatura do Responsável<br>Data: {data_atual}</p>
            </div>
        </body>
        </html>
        """
        
        # 5. Gera e salva o PDF
        nome_arquivo = f"Cautela_{rdo}_{sn}.pdf"
        HTML(string=html_content).write_pdf(nome_arquivo)
        
        print(f"✅ SUCESSO: Equipamento travado no banco!")
        print(f"📄 PDF gerado e salvo como: {nome_arquivo}")
        
    except Exception as e:
        print(f"❌ Erro no sistema Cavere: {e}")
        
    finally:
        conexao.close()

# --- TESTANDO O CAVERE ---
print("Iniciando a emissão de cautela...")
# Simulando a entrega do equipamento ID 1 para o coordenador ID 1, RDO 9999
realizar_cautela_com_pdf(id_equipamento=1, id_coordenador=1, rdo='RDO-9999')