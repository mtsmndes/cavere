# Cavere - Sistema de Gestão e Controle de Cautelas

O **Cavere** é uma plataforma web desenvolvida para gerenciar, automatizar e rastrear o controle de cautelas e inventário de equipamentos operacionais (como celulares, rádios comunicadores, câmeras, notebooks, monitores e periféricos).

O sistema atende dores reais de logística em bases operacionais, substituindo controles manuais e planilhas por um fluxo auditável de saída, devolução, solicitação de equipamentos por equipes de campo e geração instantânea de termos de responsabilidade em PDF prontos para assinatura.

---

## Principais Funcionalidades

### Gestão de Cautelas & Devoluções
- **Emissão Rápida:** Associação de equipamentos a colaboradores com registro de RDO (Registro Diário de Operação), data e hora de saída.
- **Devolução com 1 Clique:** Baixa imediata de equipamentos com atualização de status no banco de dados e carimbo de data/hora de devolução.
- **Status em Tempo Real:** Visualização imediata de ativos disponíveis, em uso e alocados por base.

### Módulo de Solicitações
- **Portal do Coordenador:** Coordenadores de campo podem abrir chamados informando tipo de equipamento, quantidade, destinatário, base/setor e justificativa.
- **Acompanhamento de Status:** Painel *"Meus Chamados"* com status em tempo real (*Pendente*, *Atendido*, etc.).
- **Atendimento pelo Administrador:** Administradores analisam as solicitações pendentes e realizam a entrega/vinculação do equipamento diretamente na plataforma.

### Inventário Completo de Equipamentos
- Cadastro detalhado de ativos com **Patrimônio / Número de Série (S/N)**, modelo, tipo de equipamento e alocação por base (*Tank, TDBR, Repair, Escritório Central*, etc.).
- Suporte a múltiplos identificadores, incluindo **IMEI 1 e IMEI 2** para dispositivos móveis.
- Histórico individual e status de conservação/uso de cada ativo.

### Base de Colaboradores e Coordenadores
- Cadastro de colaboradores com validação rigorosa de **Matrícula Geral numérica**, **CPF**, **E-mail institucional** e setor de atuação.
- Associação automática de login e permissões aos coordenadores cadastrados.

### Geração Automatizada de Termos em PDF
- Renderização dinâmica de termos formais de responsabilidade via **WeasyPrint**.
- Layout padronizado contendo identificação completa do recebedor, dados técnicos do ativo, cláusulas de responsabilidade e campos para assinatura.
- Armazenamento automático no diretório `Cautelas/` para download da 2ª via a qualquer momento.

### Histórico & Auditoria
- Registro cronológico de todas as movimentações (saídas e devoluções).
- Busca e filtros por colaborador, RDO, equipamento ou período.
- Acesso direto ao termo de cautela correspondente em PDF.

### Segurança & Controle de Acesso (RBAC)
- **Dois Níveis de Acesso:**
  - **Administrador:** Acesso total a cautelas, inventário, cadastro de usuários, histórico e atendimento de solicitações.
  - **Coordenador:** Acesso restrito ao painel de solicitações de equipamentos e acompanhamento de chamados.
- Senhas protegidas com hash criptográfico forte (`werkzeug.security`).
- Troca de senha obrigatória no primeiro acesso.
- Sessões protegidas contra falsificação com `SECRET_KEY` persistente e proteção contra *Open Redirect*.

---

## 📂 Estrutura do Projeto

```text
cavere/
├── app.py                      # Aplicação principal Flask, rotas, lógica de negócios e banco
├── criar_admin.py              # Script utilitário para inicializar/redefinir o admin
├── cadastrar_coordenador.py    # Script CLI interativo para cadastrar coordenadores
├── cadastrar_equipamento.py    # Script CLI interativo para cadastrar ativos
├── requirements.txt            # Dependências do projeto Python
├── .env.example                # Modelo de variáveis de ambiente
├── .gitignore                  # Arquivos e pastas ignorados pelo Git
├── Cavere.db                   # Banco de dados SQLite (gerado automaticamente)
├── Cautelas/                   # Diretório de armazenamento dos PDFs de termos gerados
├── static/                     # Arquivos estáticos usados nas cautelas
│   └── pdf/                    # Logotipos e rodapé dos PDFs
└── templates/                  # Templates HTML Jinja2
    ├── base.html               # Layout base e navegação
    ├── index.html              # Dashboard operacional de cautelas
    ├── login.html              # Tela de autenticação moderna
    ├── trocar_senha.html       # Fluxo de primeiro acesso e troca de senha
    ├── solicitar_equipamento.html # Formulário de abertura de chamados
    ├── meus_chamados.html      # Painel de acompanhamento do coordenador
    ├── equipamentos.html       # Lista e gestão do inventário
    ├── cadastrar_equipamento.html # Formulário web de novos ativos
    ├── colaboradores.html      # Lista de colaboradores da base
    ├── cadastrar_coordenador.html # Formulário de novo coordenador
    ├── cadastrar_usuario.html  # Gestão de acessos
    └── historico.html          # Consulta de histórico e download de 2ª via
```

---

## Como Executar o Projeto

### 1. Pré-requisitos
- **Python 3.10** ou superior instalado.
- **Git** instalado.

> **Nota para usuários Linux (Ubuntu/Debian):** Caso o WeasyPrint exija bibliotecas gráficas do sistema para renderizar PDFs, instale-as antes:
> ```bash
> sudo apt update
> sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0
> ```

---

### 2. Clonar o Repositório
```bash
git clone https://github.com/mtsmndes/cavere.git
cd cavere
```

---

### 3. Configurar o Ambiente Virtual e Instalar Dependências

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar o ambiente virtual:
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Windows (CMD):
venv\Scripts\activate.bat
# Linux/macOS:
source venv/bin/activate

# Instalar as dependências
pip install -r requirements.txt
```

---

### 4. Configurar as Variáveis de Ambiente (`.env`)

Copie o arquivo de exemplo para criar a sua configuração local:

```bash
# No Windows (PowerShell):
Copy-Item .env.example .env

# No Linux/macOS:
cp .env.example .env
```

Abra o arquivo `.env` para ajustar conforme necessário:
- `SECRET_KEY`: Chave usada para assinar cookies e sessões (se deixada em branco, o sistema gera uma automaticamente no arquivo `.secret_key`).
- `FLASK_DEBUG`: `1` para desenvolvimento com auto-reload, `0` para ambiente estável/produção.
- `HOST`: Host de bind do servidor (padrão: `127.0.0.1`).
- `PORT`: Porta de execução (padrão: `5000`).
- `SESSION_COOKIE_SECURE`: Ative (`1`) caso o sistema rode sob conexão HTTPS.

### Notificações automáticas por e-mail

O Cavere avisa o coordenador/solicitante no e-mail cadastrado quando o chamado é aberto ou muda de andamento, incluindo atendimento, espera da entrega, finalização e recálculo após devolução.

Configure no `.env`:

```env
EMAIL_NOTIFICATIONS_ENABLED=1
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USERNAME=cavere@empresa.com.br
SMTP_PASSWORD=senha-ou-token-do-provedor
SMTP_FROM=cavere@empresa.com.br
SMTP_USE_TLS=1
SMTP_USE_SSL=0
SMTP_TIMEOUT=10
APP_BASE_URL=https://cavere.empresa.com.br
```

Para SMTP com SSL direto (normalmente porta 465), use `SMTP_USE_SSL=1` e `SMTP_USE_TLS=0`. Uma falha temporária do servidor de e-mail fica registrada no log, mas não desfaz a atualização da solicitação.

---

### 5. Inicializar o Usuário Administrador

Execute o script de inicialização do primeiro usuário com perfil `admin`:

```bash
python criar_admin.py
```

- **Usuário padrão:** `administrador`
- **Senha temporária inicial:** `123`
- *(No primeiro acesso, o sistema exigirá obrigatoriamente a definição de uma nova senha pessoal).*

---

### 6. Iniciar a Aplicação

```bash
python app.py
```

Abra o navegador no endereço: **`http://localhost:5000`** (ou a porta configurada no seu `.env`).

---

## Scripts Auxiliares via Terminal (CLI)

Além dos formulários na interface web, você pode realizar cadastros diretamente pelo terminal a qualquer momento:

| Script | Finalidade |
| :--- | :--- |
| `python criar_admin.py` | Cria ou redefine a senha do usuário Administrador principal. |
| `python cadastrar_coordenador.py` | Cadastra um novo coordenador com validações de CPF, e-mail e matrícula, gerando seu login de acesso. |
| `python cadastrar_equipamento.py` | Cadastra novos equipamentos no inventário com suporte a IMEI e alocação por base. |

---

## Perfis de Acesso

| Recurso / Módulo | Administrador | Coordenador |
| :--- | :---: | :---: |
| Painel Geral & Cautelas Ativas | ✅ Total | ❌ |
| Saída e Devolução de Ativos | ✅ | ❌ |
| Atendimento e Entrega de Solicitações | ✅ | ❌ |
| Gestão de Inventário e Colaboradores | ✅ | ❌ |
| Consulta de Histórico e PDFs de Cautelas | ✅ | ❌ |
| Solicitar Equipamento (Abrir Chamado) | ✅ | ✅ |
| Acompanhamento *"Meus Chamados"* | ✅ | ✅ |
| Troca de Senha Pessoal | ✅ | ✅ |
