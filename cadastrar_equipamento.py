"""Cadastra um novo equipamento no inventário do Cavere."""

import argparse
import re
import sqlite3
import sys

from app import EquipamentoSchema, get_db_connection, inicializar_banco, validate_schema


BASES = ("Tank", "TDBR", "Repair", "Escritório Central")


def perguntar(rotulo, valor=None, padrao=None):
    if valor is not None:
        return str(valor).strip()
    sufixo = f" [{padrao}]" if padrao else ""
    resposta = input(f"{rotulo}{sufixo}: ").strip()
    return resposta or (padrao or "")


def resposta_sim(valor):
    return str(valor).strip().lower() in {"s", "sim", "1", "true", "y", "yes"}


def validar_imei(imei, rotulo):
    if not imei:
        return ""
    numeros = re.sub(r"[\s-]", "", imei)
    if not numeros.isdigit() or len(numeros) != 15:
        raise ValueError(f"{rotulo} deve conter exatamente 15 dígitos.")
    return numeros


def selecionar_base(valor=None):
    if valor is not None:
        return valor
    print("Bases: " + " | ".join(f"{i + 1}. {base}" for i, base in enumerate(BASES)))
    escolha = perguntar("Base", padrao="1")
    if escolha.isdigit() and 1 <= int(escolha) <= len(BASES):
        return BASES[int(escolha) - 1]
    if escolha in BASES:
        return escolha
    raise ValueError("Base inválida.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tipo")
    parser.add_argument("--modelo")
    parser.add_argument("--patrimonio", help="Patrimônio ou número de série")
    parser.add_argument("--imei-1")
    parser.add_argument("--imei-2")
    parser.add_argument("--base", choices=BASES)
    parser.add_argument("--alugado", action="store_true")
    parser.add_argument("--locadora")
    parser.add_argument("--processador")
    parser.add_argument("--memoria")
    parser.add_argument("--armazenamento")
    parser.add_argument("--sistema")
    parser.add_argument("--especificacoes")
    args = parser.parse_args(argv)

    try:
        print("\nCadastro de equipamento — Cavere\n")
        tipo = perguntar("Tipo", args.tipo)
        modelo = perguntar("Modelo", args.modelo)
        patrimonio = perguntar("Patrimônio / Nº de série (opcional)", args.patrimonio) or None
        imei_1 = validar_imei(perguntar("IMEI 1 (opcional)", args.imei_1), "IMEI 1")
        imei_2 = validar_imei(perguntar("IMEI 2 (opcional)", args.imei_2), "IMEI 2")
        base = selecionar_base(args.base)

        alugado = args.alugado
        if not args.alugado and args.locadora is None:
            alugado = resposta_sim(perguntar("Equipamento alugado? (s/N)", padrao="n"))
        locadora = perguntar("Empresa locadora", args.locadora) if alugado else ""
        if alugado and not locadora:
            raise ValueError("A empresa locadora é obrigatória para equipamentos alugados.")

        processador = perguntar("Processador (opcional)", args.processador)
        memoria = perguntar("Memória RAM (opcional)", args.memoria)
        armazenamento = perguntar("Armazenamento (opcional)", args.armazenamento)
        sistema = perguntar("Sistema operacional (opcional)", args.sistema)
        especificacoes = perguntar("Outras especificações (opcional)", args.especificacoes)

        dados, erro = validate_schema(EquipamentoSchema, {
            "tipo": tipo,
            "modelo": modelo,
            "patrimonio_sn": patrimonio or "",
            "imei_1": imei_1,
            "imei_2": imei_2,
            "base": base,
            "alugado": int(alugado),
            "empresa_locadora": locadora,
        })
        if erro:
            raise ValueError(erro)

        inicializar_banco()
        conexao = get_db_connection()
        try:
            conexao.execute(
                """
                INSERT INTO equipamentos
                    (tipo, modelo, patrimonio_sn, imei_1, imei_2, status, base,
                     alugado, empresa_locadora, processador, memoria_ram,
                     armazenamento, sistema_operacional, especificacoes)
                VALUES (?, ?, ?, ?, ?, 'Disponível', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dados.tipo, dados.modelo, patrimonio, dados.imei_1, dados.imei_2,
                    dados.base, dados.alugado, dados.empresa_locadora,
                    processador[:80], memoria[:40], armazenamento[:60],
                    sistema[:60], especificacoes[:255],
                ),
            )
            conexao.commit()
        except sqlite3.IntegrityError:
            conexao.rollback()
            raise ValueError(f"O patrimônio/SN '{patrimonio}' já está cadastrado.")
        finally:
            conexao.close()
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.", file=sys.stderr)
        return 130
    except (ValueError, sqlite3.Error) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    print(f"Equipamento '{tipo} - {modelo}' cadastrado com sucesso na base {base}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
