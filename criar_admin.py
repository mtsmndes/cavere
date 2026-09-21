"""Cria o administrador principal do Cavere ou redefine sua senha."""

import argparse
import getpass
import sqlite3
import sys

from werkzeug.security import generate_password_hash

from app import get_db_connection, inicializar_banco


def ler_senha(valor=None):
    if valor is not None:
        senha = valor
    else:
        senha = getpass.getpass("Senha temporária [123]: ") or "123"
        if senha != "123":
            confirmacao = getpass.getpass("Confirme a senha: ")
            if senha != confirmacao:
                raise ValueError("As senhas informadas não coincidem.")
    if not 3 <= len(senha) <= 128:
        raise ValueError("A senha deve ter entre 3 e 128 caracteres.")
    return senha


def criar_ou_redefinir_admin(usuario, senha, exigir_troca=True):
    usuario = usuario.strip()
    if not 3 <= len(usuario) <= 64:
        return False, "O usuário deve ter entre 3 e 64 caracteres."

    conexao = get_db_connection()
    try:
        cursor = conexao.cursor()
        cursor.execute("SELECT id, role FROM usuarios WHERE username = ?", (usuario,))
        existente = cursor.fetchone()
        senha_hash = generate_password_hash(senha)
        trocar_senha = 1 if exigir_troca else 0

        if existente:
            if existente[1] != "admin":
                return False, f"O login '{usuario}' já pertence a um coordenador."
            cursor.execute(
                "UPDATE usuarios SET senha_hash = ?, trocar_senha = ? WHERE id = ?",
                (senha_hash, trocar_senha, existente[0]),
            )
            acao = "Senha do administrador redefinida"
        else:
            cursor.execute(
                "INSERT INTO usuarios (username, senha_hash, role, trocar_senha) VALUES (?, ?, 'admin', ?)",
                (usuario, senha_hash, trocar_senha),
            )
            acao = "Administrador criado"

        conexao.commit()
        return True, f"{acao} com sucesso para o login '{usuario}'."
    except sqlite3.Error as erro:
        conexao.rollback()
        return False, f"Erro no banco de dados: {erro}"
    finally:
        conexao.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usuario", default="administrador", help="Login do administrador")
    parser.add_argument("--senha", help="Senha temporária (omitir para digitar de forma oculta)")
    parser.add_argument(
        "--nao-exigir-troca",
        action="store_true",
        help="Não solicitar uma nova senha no primeiro acesso",
    )
    args = parser.parse_args(argv)

    try:
        inicializar_banco()
        senha = ler_senha(args.senha)
        sucesso, mensagem = criar_ou_redefinir_admin(
            args.usuario, senha, exigir_troca=not args.nao_exigir_troca
        )
    except (EOFError, KeyboardInterrupt):
        print("\nOperação cancelada.", file=sys.stderr)
        return 130
    except ValueError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1

    print(mensagem, file=sys.stdout if sucesso else sys.stderr)
    return 0 if sucesso else 1


if __name__ == "__main__":
    raise SystemExit(main())
