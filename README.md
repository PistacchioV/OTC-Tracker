# OTC Tracker Flask - Guia de Instalação e Estrutura

## Índice
1. [Pré-requisitos](#pré-requisitos)
2. [Estrutura do Projeto](#estrutura-do-projeto)
3. [Instalação](#instalação)
4. [Configuração](#configuração)
5. [Executando o Projeto](#executando-o-projeto)
6. [Desenvolvimento](#desenvolvimento)

## Pré-requisitos
- Python 3.8+
- pip (gerenciador de pacotes Python)
- virtualenv ou venv
- Node.js e npm (para assets)

## Estrutura do Projeto
```
OTC Tracker/
├── apps/                     # Pasta principal onde fica todo o código do sistema
│   ├── config.py            # Arquivo que guarda todas as configurações do sistema (banco de dados, senhas, etc.)
│   ├── pages/               # Pasta que contém os arquivos que controlam as páginas do site (como elas funcionam e o que mostram)
│   ├── static/              # Pasta que guarda todos os arquivos visuais (imagens, estilos CSS, códigos JavaScript)
│   ├── templates/           # Pasta com os arquivos que definem como as páginas vão aparecer no navegador
│   └── __init__.py         # Arquivo que inicia o sistema e suas configurações básicas
├── .env                     # Arquivo secreto com senhas e configurações privadas
├── build.sh                 # Script que ajuda a preparar o sistema para funcionar
├── gulpfile.js             # Arquivo que automatiza tarefas como compilar CSS e JavaScript
├── gunicorn-cfg.py         # Configurações do servidor web para quando o site estiver no ar
├── requirements.txt         # Lista de todos os programas Python necessários para o sistema funcionar
└── run.py                  # Arquivo principal que inicia todo o sistema
```

### Explicação Detalhada de Cada Parte

1. **Pasta `apps/`**: 
   - É como se fosse a "casa" do sistema, onde todo o código importante fica guardado
   - Aqui encontramos todos os arquivos que fazem o site funcionar

2. **`config.py`**: 
   - É como um painel de controle
   - Guarda informações importantes como:
     - Dados para conectar ao banco de dados
     - Senhas e chaves secretas
     - Configurações gerais do sistema

3. **Pasta `pages/`**: 
   - É onde ficam os "controladores" das páginas
   - Cada arquivo aqui define:
     - O que acontece quando você clica em um botão
     - Quais informações aparecem em cada página
     - Como os dados são processados

4. **Pasta `static/`**: 
   - É a "parte visual" do sistema
   - Contém:
     - Imagens (logos, ícones, fotos)
     - Arquivos CSS (definem cores, fontes, layout)
     - JavaScript (fazem as páginas serem interativas)

5. **Pasta `templates/`**: 
   - São os "moldes" das páginas
   - Como um blueprint de arquiteto, define:
     - Como cada página vai ser organizada
     - Onde cada elemento vai aparecer
     - Como os dados serão mostrados

6. **Arquivo `.env`**: 
   - É como um cofre de senhas
   - Guarda informações sensíveis que não devem ser públicas
   - Por exemplo: senhas de banco de dados, chaves de API

7. **Arquivo `requirements.txt`**: 
   - É como uma lista de compras
   - Mostra todos os programas Python que precisam ser instalados
   - Garante que todas as funcionalidades vão funcionar corretamente

8. **Arquivo `run.py`**: 
   - É o "botão de ligar" do sistema
   - Quando executado:
     - Inicia o servidor web
     - Carrega todas as configurações
     - Faz o site ficar disponível para acesso

## Instalação

### 1. Preparar o Ambiente Virtual
```bash
# Criar ambiente virtual
python -m venv env

# Ativar ambiente virtual

# No Windows CMD
env\Scripts\activate.bat

# No Windows PowerShell
.\env\Scripts\Activate.ps1

# No Linux/Mac/Git Bash
source env/bin/activate

# Para DESATIVAR o ambiente virtual (em qualquer shell)
deactivate
```

### 2. Instalar Dependências Python
```bash
# Instalar requisitos
pip install -r requirements.txt
```

### 3. Instalar Dependências Node.js
```bash
# Instalar pacotes npm
npm install
```

## Configuração

### 1. Configurar Variáveis de Ambiente
Copie o arquivo `env.sample` para `.env` e configure as seguintes variáveis:

```ini
# Flask
FLASK_APP=run.py
FLASK_ENV=development

# Database
DB_ENGINE=
DB_USERNAME=
DB_PASS=
DB_HOST=
DB_PORT=
DB_NAME=

# Assets
ASSETS_ROOT=/static
```

> **Fora do Windows, `OTC_SHARED_DRIVE_ROOT` é obrigatória.** Todo destino no
> share pende dela e o padrão é `I:\`, que em macOS/Linux é um caminho
> **relativo** — o app **recusa subir** nesse caso, em vez de criar em silêncio
> uma árvore `I:\Confirmation\...` dentro do diretório de trabalho.
>
> ```ini
> OTC_SHARED_DRIVE_ROOT=/Users/voce/otc-share
> ```
>
> O `env.sample` traz o conjunto completo, comentado uma a uma: `DATABASE_PATH`
> (mover o DuckDB de usuários para fora do pacote), `OTC_TRACKER_URL` (endereço
> absoluto que os botões dos e-mails usam), `IMPORT_POLL_WINDOW` (a janela
> 08:00–20:00 BRT dos schedulers de importação), `QUOTES_PROXY` (a saída para o
> BCB e o Yahoo) e as chaves VAPID do Web Push.

### 2. Configuração do Banco de Dados

O SQLAlchemy vem configurado do template (SQLite por padrão, PostgreSQL/MySQL
pelas variáveis `DB_*` do `.env`), mas **a lógica da aplicação não o usa**. Os
dados de verdade estão em três lugares:

- **DuckDB** — usuários/2FA (`Users_OTCTracker.db`), notificações
  (`Notifications_OTCTracker.db`) e os bancos de Pending Confirmation, esteira
  de confirmação e Onboarding. Todos sob `Config.DATABASE_DIR`.
- **JSON** — os arquivo-dia (cache), os 43 cadastros do `/mapping`, RefData,
  calendários e templates, sob `Config.DATA_DIR`. **É aqui que a aplicação
  escreve**, e é o que se reverte num rollback.
- **DuckDB espelhado** — cada JSON gravado é reconvertido na hora
  (`apps/pages/duck_mirror.py`) para um banco em `db/`, e a leitura usa o banco
  quando ele comprovadamente reflete o JSON atual.

Mover tudo de lugar é uma variável só: `OTC_DATABASE_DIR` (bancos) e
`OTC_DATA_DIR` (JSONs). Ver **CLAUDE.md §4**.

#### Materializar os bancos DuckDB numa instância nova

O espelho cuida do dia a dia; a carga inicial (ou a reconciliação depois de um
período com o app parado) é feita por script. Ela é **idempotente e
incremental**, e converte só os arquivo-dia dos **últimos 12 meses** por padrão:

```bash
python scripts/convert/00_completo.py            # tudo num comando
python scripts/convert/00_completo.py --meses 0  # depois, o histórico inteiro
```

A carga no share leva horas, então ela também vem **repartida em 39 fatias**
(uma por pasta de cadastro e uma por bloco de `cache/`, com New Deals e B3 Files
quebrados até o produto, o Daily Settlement e o B3 Files por arquivo e uma fatia
por reconciliação) que várias pessoas rodam ao mesmo tempo —
`scripts/convert/README.md` explica.
Para uma máquina **sem o código do app**, o `scripts/standalone/` tem o mesmo
corte com os caminhos do share fixos e só o `duckdb` como dependência.

## Executando o Projeto

### 1. Desenvolvimento
```bash
# Executar em modo desenvolvimento
# Porta padrão (5000)
flask run

# Especificar uma porta diferente
flask run --port=8051

# Permitir acesso externo (de outras máquinas) com porta específica
flask run --host=0.0.0.0 --port=8051
```

### 2. Produção
```bash
# Usando Gunicorn (Linux/Mac)
gunicorn --config gunicorn-cfg.py run:app

# Usando Waitress (Windows)
waitress-serve --port=8000 run:app
```

## Desenvolvimento

### 1. Estrutura e Personalização de Templates
Os templates estão organizados em:
```
apps/templates/
├── layouts/          # Layouts base (estruturas principais)
│   ├── base.html    # Template base com estrutura HTML comum
│   ├── default.html # Layout padrão herdado do base
│   └── auth.html    # Layout para páginas de autenticação
├── pages/           # Templates específicos de cada página
│   ├── dashboard/   # Templates do painel principal
│   ├── auth/        # Templates de login/registro
│   └── errors/      # Templates de páginas de erro
└── partials/        # Componentes reutilizáveis
    ├── sidebar.html # Menu lateral
    ├── header.html  # Cabeçalho da página
    └── footer.html  # Rodapé da página
```

#### Como Personalizar Layouts
1. Layouts Base (`apps/templates/layouts/`)
   - Edite `base.html` para modificar a estrutura HTML comum
   - Modifique `default.html` para ajustar o layout padrão das páginas
   - Altere `auth.html` para customizar o layout de autenticação

2. Componentes (`apps/templates/partials/`)
   - `sidebar.html`: Personalize o menu lateral e navegação
   - `header.html`: Modifique o cabeçalho, logo e menu superior
   - `footer.html`: Ajuste o rodapé e informações de copyright

### 2. Assets e Recursos Estáticos
Os assets estão organizados em:
```
apps/static/
├── css/             # Arquivos CSS compilados
├── scss/            # Arquivos SCSS fonte
├── js/              # Scripts JavaScript
├── images/          # Imagens do sistema
│   ├── logo/        # Logos e marcas
│   ├── users/       # Avatares e fotos de usuário
│   └── backgrounds/ # Imagens de fundo
├── plugins/         # Plugins e bibliotecas terceiras
└── data/           # Arquivos JSON para dados estáticos
```

#### Gerenciamento de Imagens
1. Localização das Imagens:
   - Logo principal: `apps/static/images/logo/logo.png`
   - Favicon: `apps/static/images/favicon.ico`
   - Avatares: `apps/static/images/users/`
   - Backgrounds: `apps/static/images/backgrounds/`

2. Como Alterar Imagens:
   - Substitua os arquivos mantendo os mesmos nomes
   - Ou atualize os caminhos em:
     - Templates: Use `{{ url_for('static', filename='images/...') }}`
     - CSS: Atualize em `apps/static/scss/custom/structure/_general.scss`

#### Personalização de Estilos
1. SCSS (`apps/static/scss/`)
   - `_variables.scss`: Cores, fontes e variáveis globais
   - `custom/`: Arquivos para personalização específica
   - `theme/`: Estilos do tema principal

2. JavaScript (`apps/static/js/`)
   - `pages/`: Scripts específicos de cada página
   - `app.js`: Configurações globais da aplicação

#### Compilação de Assets
```bash
# Desenvolvimento (com watch)
gulp watch

# Compilação para produção
gulp build --prod
```

### 3. Backend e Integração com Frontend

#### Estrutura do Backend
```
apps/
├── pages/                    # Blueprints e rotas
│   ├── routes.py            # Rotas principais
│   └── api.py               # Endpoints da API
├── models/                   # Modelos de dados
│   ├── user.py              # Modelo de usuário
│   └── content.py           # Outros modelos
└── utils/                   # Funções utilitárias
```

#### Como Adicionar Novas Funcionalidades
1. Criar Rota:
```python
# apps/pages/routes.py
@blueprint.route('/nova-pagina')
def nova_pagina():
    # Lógica do backend
    dados = obter_dados()
    return render_template('pages/nova-pagina.html', dados=dados)
```

2. Criar Template:
```html
<!-- apps/templates/pages/nova-pagina.html -->
{% extends "layouts/default.html" %}
{% block content %}
    <!-- Seu conteúdo aqui -->
    {% for item in dados %}
        {{ item.nome }}
    {% endfor %}
{% endblock %}
```

3. Adicionar Assets:
   - CSS: Criar arquivo em `apps/static/scss/custom/pages/`
   - JS: Adicionar script em `apps/static/js/pages/`

#### Integração com Dados Dinâmicos
1. Em Templates:
```html
<!-- Uso de variáveis do backend -->
{{ dados.titulo }}

<!-- Loops e condicionais -->
{% for item in lista %}
    {% if item.ativo %}
        {{ item.nome }}
    {% endif %}
{% endfor %}

<!-- Inclusão de imagens dinâmicas -->
<img src="{{ url_for('static', filename='images/' + usuario.avatar) }}">
```

2. No Backend:
```python
# Envio de dados para templates
@blueprint.route('/dashboard')
def dashboard():
    context = {
        'usuario': obter_usuario_atual(),
        'dados': obter_dados_dashboard(),
        'graficos': gerar_graficos()
    }
    return render_template('pages/dashboard.html', **context)
```

### 3. Principais Dependências
- Flask 3.1.1: Framework web
- Flask-SQLAlchemy 3.0.5: ORM para banco de dados
- Flask-Login 0.6.3: Gerenciamento de autenticação
- Flask-WTF 1.2.1: Formulários e validação
- Flask-Migrate 4.0.4: Migrações de banco de dados
- Flask-Minify 0.42: Minificação de assets
- Gunicorn 20.1.0: Servidor WSGI para produção

### 4. Desenvolvimento de Novas Páginas
1. Criar route em `apps/pages/routes.py`
2. Criar template em `apps/templates/pages/`
3. Adicionar assets específicos em `apps/static/src/`

### 5. Boas Práticas
- Use blueprints para organizar rotas
- Mantenha a lógica de negócios em módulos separados
- Siga o padrão MVC
- Use variáveis de ambiente para configurações
- Documente novas funcionalidades
- Mantenha o código limpo e bem documentado

## Suporte

Para questões e suporte, consulte:
- Documentação em `/Docs`
- Issues no repositório
- Equipe de desenvolvimento

<br />

### Set Up for `Unix`, `MacOS` 

> Install modules via `VENV`  

```bash
$ virtualenv env
$ source env/bin/activate
$ pip install -r requirements.txt
```

<br />

> Set Up Flask Environment

```bash
$ export FLASK_APP=run.py
$ export FLASK_ENV=development
```

<br />

> Start the app

```bash
$ flask run
// OR
$ flask run --cert=adhoc # For HTTPS server
```

At this point, the app runs at `http://127.0.0.1:5000/`. 

<br />

### Set Up for `Windows` 

> Install modules via `VENV` (windows) 

```
$ virtualenv env
$ .\env\Scripts\activate
$ pip install -r requirements.txt
```

<br />

> Set Up Flask Environment

```bash
$ # CMD 
$ set FLASK_APP=run.py
$ set FLASK_ENV=development
$
$ # Powershell
$ $env:FLASK_APP = ".\run.py"
$ $env:FLASK_ENV = "development"
```

<br />

> Start the app

```bash
$ flask run
// OR
$ flask run --cert=adhoc # For HTTPS server
```

At this point, the app runs at `http://127.0.0.1:5000/`. 

<br />

### Create Users

By default, the app redirects guest users to authenticate. In order to access the private pages, follow this set up: 

- Start the app via `flask run`
- Access the `registration` page and create a new user:
  - `http://127.0.0.1:5000/register`
- Access the `sign in` page and authenticate
  - `http://127.0.0.1:5000/login`

<br />