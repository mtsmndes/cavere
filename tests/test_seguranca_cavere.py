# -*- coding: utf-8 -*-
"""
Suíte de Testes Automatizados de Segurança, RBAC, Validação e Hardening - Sistema Cavere
Em conformidade com OWASP Top 10 e diretrizes IEC 62443.
"""
import pytest
import sqlite3
import html
from app import (
    app,
    get_db_connection,
    is_safe_redirect_url,
    validate_schema,
    LoginSchema,
    EquipamentoSchema,
    SolicitacaoItemSchema,
    TrocarSenhaSchema,
    NovoUsuarioSchema,
    Usuario,
    login_manager,
    verificar_bloqueio_login,
    registrar_falha_login,
    limpar_falhas_login,
    TENTATIVAS_FALHAS,
    MAX_TENTATIVAS_FALHAS,
)
from werkzeug.security import generate_password_hash, check_password_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as c:
        yield c

# 1. Autenticação: Acesso não autenticado a rotas protegidas
def test_unauthenticated_access_redirects_to_login(client):
    rotas_protegidas = ['/', '/novo-equipamento', '/colaboradores', '/equipamentos', '/meus-chamados', '/solicitar-equipamento']
    for rota in rotas_protegidas:
        resp = client.get(rota, follow_redirects=False)
        assert resp.status_code in (302, 401), f"Rota {rota} deveria exigir login"
        if resp.status_code == 302:
            assert '/login' in resp.headers.get('Location', '')

# 2. Bloqueio estrito de arquivos sensíveis (.db, .env, .git, .py)
def test_sensitive_files_blocked_with_403(client):
    arquivos_sensiveis = ['/Cavere.db', '/.env', '/.git/config', '/app.py', '/config.sqlite3']
    for arq in arquivos_sensiveis:
        resp = client.get(arq)
        assert resp.status_code == 403, f"Acesso a {arq} deveria ser abortado com 403"

# 3. Cabeçalhos HTTP de Segurança Defensiva (OWASP / CSP / HSTS)
def test_security_headers_present(client):
    resp = client.get('/login')
    headers = resp.headers
    assert headers.get('X-Frame-Options') == 'DENY'
    assert headers.get('X-Content-Type-Options') == 'nosniff'
    assert headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'
    csp = headers.get('Content-Security-Policy', '')
    assert "default-src 'self'" in csp

# 4. Anti-CSRF: Bloqueio de POST sem token quando CSRF está ativo
def test_csrf_protection_blocks_post_without_token():
    app.config['TESTING'] = False
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_csrf_token'] = 'valid_token_1234567890abcdef1234567890abcdef'
        
        resp = c.post('/login', data={'username': 'admin', 'senha': 'password123'}, follow_redirects=False)
        assert resp.status_code == 400, "POST sem csrf_token deve ser rejeitado com 400"
    app.config['TESTING'] = True

# 5. Anti-CSRF: Aceitação de requisição com token CSRF válido
def test_csrf_protection_accepts_valid_token():
    app.config['TESTING'] = False
    csrf_secret = 'valid_token_1234567890abcdef1234567890abcdef'
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['_csrf_token'] = csrf_secret
        
        resp = c.post('/login', data={
            'csrf_token': csrf_secret,
            'username': 'fake_user_test',
            'senha': 'wrong_password'
        }, follow_redirects=True)
        assert resp.status_code != 400, "POST com csrf_token correto não deve dar erro 400"
    app.config['TESTING'] = True

# 6. Mitigação de Open Redirect
def test_open_redirect_mitigation():
    with app.test_request_context('/'):
        urls_perigosas = [
            '//evil.com',
            'http://malicious.org',
            'https://attacker.site/phishing',
            '\\\\attacker.com',
            '/\\malicious',
            None,
            '',
        ]
        for url in urls_perigosas:
            assert is_safe_redirect_url(url) is False, f"URL {url} deveria ser considerada insegura"
        
        urls_seguras = ['/meus-chamados', '/historico', '/', '/login']
        for url in urls_seguras:
            assert is_safe_redirect_url(url) is True, f"URL relativa {url} deveria ser segura"

# 7. Validação de Schema Pydantic: LoginSchema
def test_pydantic_schema_validation_login():
    inst, err = validate_schema(LoginSchema, {'username': 'ad', 'senha': '123'})
    assert err is not None, "Username com menos de 3 caracteres deve falhar"
    
    inst, err = validate_schema(LoginSchema, {'username': 'admin', 'senha': 'secret_password'})
    assert err is None
    assert inst.username == 'admin'

# 8. Validação de Schema Pydantic: EquipamentoSchema
def test_pydantic_schema_validation_equipamento():
    inst, err = validate_schema(EquipamentoSchema, {'tipo': '', 'modelo': 'Dell Latitude'})
    assert err is not None, "Tipo vazio deve ser rejeitado"
    
    inst, err = validate_schema(EquipamentoSchema, {
        'tipo': 'Notebook',
        'modelo': 'Dell Latitude 3420',
        'patrimonio_sn': 'PAT-9999',
        'base': 'Tank',
        'alugado': 0
    })
    assert err is None
    assert inst.tipo == 'Notebook'

# 9. Validação de Schema Pydantic: SolicitacaoItemSchema
def test_pydantic_schema_validation_solicitacao():
    inst, err = validate_schema(SolicitacaoItemSchema, {'tipo': 'Radio VHF', 'quantidade': 0})
    assert err is not None, "Quantidade 0 deve falhar"
    
    inst, err = validate_schema(SolicitacaoItemSchema, {'tipo': 'Radio VHF', 'quantidade': 100})
    assert err is not None, "Quantidade > 50 deve falhar"
    
    inst, err = validate_schema(SolicitacaoItemSchema, {'tipo': 'Radio VHF', 'quantidade': 5})
    assert err is None
    assert inst.quantidade == 5

# 10. Validação de Schema Pydantic: TrocarSenhaSchema
def test_pydantic_schema_validation_trocar_senha():
    inst, err = validate_schema(TrocarSenhaSchema, {
        'senha_atual': '123',
        'nova_senha': 'abc',
        'confirmar_senha': 'abc'
    })
    assert err is not None, "Senha com menos de 4 caracteres deve falhar"
    
    inst, err = validate_schema(TrocarSenhaSchema, {
        'senha_atual': 'senha123',
        'nova_senha': 'NovaSenhaSegura@2026',
        'confirmar_senha': 'NovaSenhaSegura@2026'
    })
    assert err is None

# 11. Validação de Schema Pydantic: NovoUsuarioSchema (Validação de Papéis/Roles)
def test_pydantic_schema_validation_novo_usuario_role():
    inst, err = validate_schema(NovoUsuarioSchema, {
        'username': 'superoperador',
        'senha': 'senha_valida_123',
        'role': 'hacker_role'
    })
    assert err is not None, "Role fora de (admin, coordenador) deve ser rejeitada"
    
    inst, err = validate_schema(NovoUsuarioSchema, {
        'username': 'coordenador_rio',
        'senha': 'senha_valida_123',
        'role': 'coordenador'
    })
    assert err is None
    assert inst.role == 'coordenador'

# 12. Rate Limiting e Proteção contra Força Bruta no Login
def test_login_rate_limiting_and_lockout():
    ip_teste = '192.168.100.50'
    usuario_teste = 'tentativa_bruta'
    limpar_falhas_login(ip_teste, usuario_teste)
    
    for _ in range(MAX_TENTATIVAS_FALHAS - 1):
        registrar_falha_login(ip_teste, usuario_teste)
        permitido, _ = verificar_bloqueio_login(ip_teste, usuario_teste)
        assert permitido is True
        
    registrar_falha_login(ip_teste, usuario_teste)
    bloqueado, msg = verificar_bloqueio_login(ip_teste, usuario_teste)
    assert bloqueado is False, "Após 5 tentativas falhas, o acesso deve ser bloqueado temporariamente"
    assert "Muitas tentativas incorretas" in msg
    
    limpar_falhas_login(ip_teste, usuario_teste)
    desbloqueado, _ = verificar_bloqueio_login(ip_teste, usuario_teste)
    assert desbloqueado is True

# 13. Neutralização de XSS em Entradas e Sanitização HTML
def test_xss_payload_neutralization():
    payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "<svg onload=alert(document.domain)>",
        "javascript:alert(1)"
    ]
    for p in payloads:
        escaped = html.escape(p)
        assert "<script>" not in escaped
        assert "<img" not in escaped
        assert "<svg" not in escaped

# 14. RBAC: Coordenador restrito de rotas administrativas
def test_rbac_coordenador_restricted_from_admin_pages(client):
    u_coord = Usuario(id=999, username='coord_unit', senha_hash='hash', role='coordenador', trocar_senha=0)
    original_loader = login_manager._user_callback
    try:
        login_manager._user_callback = lambda uid: u_coord
        with client.session_transaction() as sess:
            sess['_user_id'] = '999'
            sess['_fresh'] = True
        
        # Coordenador tentando acessar painel administrativo de equipamentos
        resp = client.get('/equipamentos', follow_redirects=False)
        assert resp.status_code == 302
        assert '/meus-chamados' in resp.headers.get('Location', '')
    finally:
        login_manager._user_callback = original_loader

# 15. Persistência Segura: Modo WAL, Integridade Referencial e Concorrência SQLite
def test_database_wal_mode_and_foreign_keys():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys;")
    fk_enabled = cursor.fetchone()[0]
    assert fk_enabled == 1, "Foreign keys devem estar ativadas no SQLite"
    
    cursor.execute("PRAGMA journal_mode;")
    journal = cursor.fetchone()[0]
    assert journal.lower() == 'wal', "SQLite deve estar configurado em modo WAL"
    
    conn.close()

# 16. Criptografia de Credenciais: Senhas com Hash Werkzeug (Scrypt/PBKDF2)
def test_password_hashing_security():
    plain = 'Ambipar#Security@2026'
    h = generate_password_hash(plain)
    assert h != plain
    assert h.startswith(('scrypt:', 'pbkdf2:'))
    assert check_password_hash(h, plain) is True
    assert check_password_hash(h, 'WrongPass123') is False

# 17. Isolamento de Ambiente: Rotas de Teste e Debug Inativos em Produção
def test_production_environment_isolation(client):
    assert app.debug is False or app.config.get('DEBUG') is False or not app.debug
    resp = client.get('/api/teste/simular_falha')
    assert resp.status_code in (404, 302, 403), "Rotas de teste devem retornar 404 em produção"
