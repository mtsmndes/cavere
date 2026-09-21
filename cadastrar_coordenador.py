"""Cadastra um coordenador e gera sua credencial de acesso ao Cavere."""

import argparse
import getpass
import re
import sys
import unicodedata

from app import inicializar_banco, salvar_novo_usuario


BASES = ("Tank", "TDBR", "Repair", "Escritório Central")


def perguntar(rotulo, valor=None, padrao=None):
    if valor is not None:
        return str(valor).strip()
    sufixo = f" [{padrao}]" if padrao else ""
    resposta = input(f"{rotulo}{sufixo}: ").strip()
    return resposta or (padrao or "")


def sugerir_login(nome):
    normalizado = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    partes = re.findall(r"[a-z0-9]+", normalizado.lower())
    if not partes:
        return ""
    return partes[0] if len(partes) == 1 else f"{partes[0]}.{partes[-1]}"


def cpf_valido(cpf):
    numeros = re.sub(r"\D", "", cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10 % 11) % 10
        if digito != int(numeros[tamanho]):
            return False
    return True


def selecionar_base(valor=None):
    if valor is not None:
        if valor not in BASES:
            raise ValueError(f"Base inválida. Opções: {', '.join(BASES)}.")
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
    parser.add_argument("--nome")
    parser.add_argument("--cpf")
    parser.add_argument("--matricula")
    parser.add_argument("--email")
    parser.add_argument("--celular")
    parser.add_argument("--setor")
    parser.add_argument("--base", choices=BASES)
    parser.add_argument("--usuario")
    parser.add_argument("--senha", help="Omitir para digitar de forma oculta")
    parser.add_argument("--id", type=int, dest="id_personalizado")
    parser.add_argument("--nao-exigir-troca", action="store_true")
    args = parser.parse_args(argv)

    try:
        print("\nCadastro de coordenador — Cavere\n")
        nome = perguntar("Nome completo", args.nome)
        cpf = perguntar("CPF", args.cpf)
        if not cpf_valido(cpf):
            raise ValueError("CPF inválido.")
        matricula = perguntar("Matrícula (somente números)", args.matricula)
        email = perguntar("E-mail corporativo", args.email)
        celular = perguntar("Celular com DDD", args.celular)
        setor = perguntar("Setor", args.setor, "Operações")
        base = selecionar_base(args.base)
        usuario = perguntar("Login", args.usuario, sugerir_login(nome))

        senha = args.senha
        if senha is None:
            senha = getpass.getpass("Senha temporária: ")
            confirmacao = getpass.getpass("Confirme a senha: ")
            if senha != confirmacao:
                raise ValueError("As senhas informadas não coincidem.")

        inicializar_banco()
        sucesso, mensagem = salvar_novo_usuario(
            username=usuario,
            senha_pura=senha,
            role="coordenador",
            id_personalizado=args.id_personalizado,
            nome_completo=nome,
            cpf_matricula=cpf,
            cpf=cpf,
            matricula=matricula,
            email=email,
            celular=celular,
            setor=setor,
            base=base,
            trocar_senha=0 if args.nao_exigir_troca else 1,
        )
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.", file=sys.stderr)
        return 130
    except ValueError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    print(mensagem, file=sys.stdout if sucesso else sys.stderr)
    if sucesso:
        print(f"Login gerado: {usuario}")
        print("A troca de senha será exigida no primeiro acesso." if not args.nao_exigir_troca else "Acesso liberado sem troca obrigatória de senha.")
    return 0 if sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
