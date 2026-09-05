O Cavere é um sistema desenvolvido para automatizar e gerenciar o controle de cautelas de equipamentos operacionais (como celulares, câmeras e rádios). 
O projeto resolve dores reais de logística em bases operacionais, controlando o status de ativos no banco de dados (SQLite) e gerando termos de responsabilidade 
de forma rápida e automatizada via scripts em Python.

## 🚀 Como Executar o Projeto

### 1. Pré-requisitos
- Python 3.10 ou superior instalado
- Git instalado (opcional, para clonar)

### 2. Clonar o repositório
```bash
git clone https://github.com/mtsmndes/cavere.git
cd cavere
```

### 3. Instalar as dependências
Crie um ambiente virtual (recomendado) e instale as bibliotecas necessárias listadas no `requirements.txt`:

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# No Windows:
venv\Scripts\activate
# No Linux/macOS:
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

> **Nota para usuários Linux (Ubuntu/Debian):** Caso o WeasyPrint exija bibliotecas gráficas do sistema para renderizar PDFs, instale-as com:
> ```bash
> sudo apt install libpango-1.0-0 libpangoft2-1.0-0
> ```

### 4. Inicializar o Usuário Administrador
Para criar ou redefinir o usuário administrador inicial no banco de dados SQLite:
```bash
python criar_admin.py
```
- **Usuário padrão sugerido:** `administrador`
- **Senha temporária padrão:** `123` (o sistema solicitará a troca obrigatória de senha no primeiro login)

### 5. Iniciar a Aplicação
```bash
python app.py
```
O sistema estará disponível em seu navegador no endereço: **`http://localhost:5000`**.

