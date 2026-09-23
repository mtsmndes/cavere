# -*- coding: utf-8 -*-
"""Notificações de andamento das solicitações do Cavere via SMTP."""

import html
import logging
import os
import re
import smtplib
import ssl
import threading
from email.message import EmailMessage


logger = logging.getLogger(__name__)


def _env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in ('1', 'true', 'sim', 'yes', 'on')


def email_valido(endereco):
    """Valida o formato básico e impede injeção nos cabeçalhos SMTP."""
    if not endereco or '\n' in endereco or '\r' in endereco:
        return False
    return re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", endereco.strip()) is not None


def montar_email_solicitacao(dados, status_anterior=None, detalhe=''):
    """Cria assunto e corpos texto/HTML a partir dos dados da solicitação."""
    id_solicitacao = int(dados['id'])
    status_atual = str(dados['status'] or 'Pendente')
    nome = str(dados['nome'] or 'Solicitante')
    tipo = str(dados['tipo_equipamento'] or 'Equipamento')
    quantidade = int(dados['quantidade'] or 1)
    destino = str(dados['plataforma'] or dados['destinatario'] or '-')
    base_url = os.environ.get('APP_BASE_URL', '').strip().rstrip('/')
    link = f"{base_url}/meus-chamados" if base_url else ''

    assunto = f"Cavere | Solicitação #SOL-{id_solicitacao}: {status_atual}"
    mudanca = f"{status_anterior} → {status_atual}" if status_anterior else status_atual
    linhas = [
        f"Olá, {nome}.", '',
        f"A solicitação #SOL-{id_solicitacao} está com o status: {mudanca}.",
        f"Item: {quantidade}x {tipo}", f"Destino: {destino}",
    ]
    if detalhe:
        linhas.extend(['', detalhe])
    if link:
        linhas.extend(['', f"Acompanhe seus chamados: {link}"])
    linhas.extend(['', 'Esta é uma mensagem automática do sistema Cavere.'])

    esc = html.escape
    link_html = (
        f'<p style="margin:24px 0"><a href="{esc(link, quote=True)}" '
        'style="background:#0b5ed7;color:#fff;padding:12px 18px;text-decoration:none;border-radius:6px">'
        'Acompanhar solicitação</a></p>' if link else ''
    )
    detalhe_html = f'<p><strong>Atualização:</strong> {esc(detalhe)}</p>' if detalhe else ''
    corpo_html = f'''<!doctype html>
<html lang="pt-BR"><body style="margin:0;background:#f3f5f7;font-family:Arial,sans-serif;color:#263238">
  <div style="max-width:620px;margin:24px auto;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #dde3e8">
    <div style="background:#12344d;color:#fff;padding:20px 28px"><strong style="font-size:22px">Cavere</strong></div>
    <div style="padding:28px">
      <p>Olá, {esc(nome)}.</p>
      <p>O andamento da solicitação <strong>#SOL-{id_solicitacao}</strong> foi atualizado.</p>
      <div style="background:#eef5ff;border-left:4px solid #0b5ed7;padding:14px 16px;margin:20px 0">
        <strong>Status: {esc(mudanca)}</strong>
      </div>
      <p><strong>Item:</strong> {quantidade}x {esc(tipo)}<br><strong>Destino:</strong> {esc(destino)}</p>
      {detalhe_html}{link_html}
      <p style="margin-top:28px;color:#68757f;font-size:13px">Esta é uma mensagem automática do sistema Cavere.</p>
    </div>
  </div>
</body></html>'''
    return assunto, '\n'.join(linhas), corpo_html


def enviar_email_smtp(destinatario, assunto, corpo_texto, corpo_html):
    """Envia pelo SMTP configurado; retorna False sem propagar falhas ao chamado."""
    host = os.environ.get('SMTP_HOST', '').strip()
    remetente = os.environ.get('SMTP_FROM', '').strip()
    if not _env_bool('EMAIL_NOTIFICATIONS_ENABLED') or not host or not remetente:
        return False
    if not email_valido(destinatario) or not email_valido(remetente):
        logger.warning('Notificação não enviada: endereço de e-mail inválido.')
        return False
    try:
        porta = int(os.environ.get('SMTP_PORT', '587'))
        timeout = float(os.environ.get('SMTP_TIMEOUT', '10'))
    except ValueError:
        logger.error('Notificação não enviada: SMTP_PORT ou SMTP_TIMEOUT inválido.')
        return False

    mensagem = EmailMessage()
    mensagem['Subject'], mensagem['From'], mensagem['To'] = assunto, remetente, destinatario.strip()
    mensagem.set_content(corpo_texto)
    mensagem.add_alternative(corpo_html, subtype='html')
    usuario = os.environ.get('SMTP_USERNAME', '').strip()
    senha = os.environ.get('SMTP_PASSWORD', '')
    usar_ssl = _env_bool('SMTP_USE_SSL', porta == 465)
    usar_tls = _env_bool('SMTP_USE_TLS', not usar_ssl)
    contexto_tls = ssl.create_default_context()

    try:
        cliente_cls = smtplib.SMTP_SSL if usar_ssl else smtplib.SMTP
        kwargs = {'host': host, 'port': porta, 'timeout': timeout}
        if usar_ssl:
            kwargs['context'] = contexto_tls
        with cliente_cls(**kwargs) as smtp:
            if not usar_ssl and usar_tls:
                smtp.ehlo()
                smtp.starttls(context=contexto_tls)
                smtp.ehlo()
            if usuario:
                smtp.login(usuario, senha)
            smtp.send_message(mensagem)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception('Falha ao enviar notificação de solicitação: %s', exc)
        return False


def agendar_notificacao_solicitacao(db_factory, id_solicitacao, status_anterior=None, detalhe=''):
    # CAUSA: o SMTP era executado dentro da requisição HTTP e mantinha a tela aguardando conexão, TLS e autenticação.
    # FIX: o envio passa a ocorrer em uma thread daemon isolada depois que a alteração do chamado já foi confirmada.
    # ATENÇÃO: falhas continuam registradas no log e nunca revertem a cautela nem bloqueiam o redirecionamento.
    # ASSUMI: o volume de atualizações é baixo, compatível com uma thread curta por notificação.
    if not _env_bool('EMAIL_NOTIFICATIONS_ENABLED'):
        return False

    tarefa = threading.Thread(
        target=notificar_andamento_solicitacao,
        args=(db_factory, id_solicitacao, status_anterior, detalhe),
        name=f'cavere-email-sol-{id_solicitacao}',
        daemon=True,
    )
    tarefa.start()
    return True


def notificar_andamento_solicitacao(db_factory, id_solicitacao, status_anterior=None, detalhe=''):
    """Busca o e-mail cadastrado do solicitante e envia o status vigente."""
    if not _env_bool('EMAIL_NOTIFICATIONS_ENABLED'):
        return False
    conexao = None
    try:
        conexao = db_factory()
        cursor = conexao.cursor()
        cursor.execute('''
            SELECT s.id, s.status, s.tipo_equipamento, s.quantidade,
                   s.destinatario, s.plataforma,
                   COALESCE(c.nome_completo, u.username, 'Solicitante'),
                   COALESCE(c.email, '')
            FROM solicitacoes s
            LEFT JOIN coordenadores c ON c.id = s.id_coordenador
            LEFT JOIN usuarios u ON u.id = s.id_coordenador
            WHERE s.id = ?
        ''', (id_solicitacao,))
        row = cursor.fetchone()
    except Exception as exc:
        logger.exception('Falha ao consultar destinatário da solicitação #%s: %s', id_solicitacao, exc)
        return False
    finally:
        if conexao is not None:
            conexao.close()

    if not row or not email_valido(row[7]):
        logger.info('Solicitação #%s sem e-mail válido para notificação.', id_solicitacao)
        return False
    try:
        dados = {'id': row[0], 'status': row[1], 'tipo_equipamento': row[2],
                 'quantidade': row[3], 'destinatario': row[4], 'plataforma': row[5], 'nome': row[6]}
        assunto, texto, corpo_html = montar_email_solicitacao(dados, status_anterior, detalhe)
        return enviar_email_smtp(row[7], assunto, texto, corpo_html)
    except Exception as exc:
        logger.exception('Falha ao preparar notificação da solicitação #%s: %s', id_solicitacao, exc)
        return False
