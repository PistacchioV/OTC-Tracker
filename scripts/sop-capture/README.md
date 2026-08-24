# SOP · Captura de telas (dados fictícios)

Ferramentas para (re)gerar as telas do **SOP de Processamento OTC** a partir do
sistema real, com **dados 100% fictícios** injetados via mock. Use isto quando um
módulo novo ficar pronto e você precisar atualizar o SOP.

> ⚠️ **Privacidade / segurança.** As telas devem sempre exibir dados fictícios —
> nenhum dado real de cliente, conta, servidor ou credencial. O launcher local
> (`devrun.py`) contém um bypass de login **que nunca pode ser versionado nem
> copiado para dentro de `apps/`** (HANDOFF, pitfall #11). Por isso ele é um
> template `.example` e o `devrun.py` real está no `.gitignore`.

## Conteúdo

| Arquivo | Papel |
|---|---|
| `mockgen.py` | Gera linhas/valores fictícios reaproveitando as **colunas reais** de cada endpoint. |
| `capture_screens.py` | Percorre o sidebar, renderiza cada rota no Chromium headless, intercepta `/api/**` e salva os PNGs em `docs/sop-screenshots/`. |
| `devrun.example.py` | **Template** do launcher local (stub de `awmpy` + rota `/dev-login`). Copie para `devrun.py` (gitignored). |
| `.gitignore` | Impede o commit de `devrun.py`, caches e artefatos. |

## Passo a passo

```bash
# 1) dependências (uma vez)
pip install playwright python-docx
#   Chromium: em ambientes com Playwright já instalado (PLAYWRIGHT_BROWSERS_PATH),
#   o capturador detecta o binário sozinho. Caso contrário: playwright install chromium

# 2) launcher local — NÃO versionado (contém o bypass /dev-login)
cp scripts/sop-capture/devrun.example.py devrun.py
python devrun.py            # sobe o app em http://127.0.0.1:8050

# 3) em outro terminal: capturar as telas
python scripts/sop-capture/capture_screens.py
#   -> salva os PNGs em docs/sop-screenshots/ (só as rotas desenvolvidas / 200)

# 4) regerar o Word a partir do Markdown
python scripts/build_sop_docx.py
#   Pillow é OPCIONAL e vale a pena: com ele a cópia embutida de cada captura
#   é reduzida a 1400 px (a largura no Word é 6,6", então acima disso o arquivo
#   cresce sem ninguém ver diferença) — o Guia cai de 44 MB para 20 MB. Sem
#   Pillow o original é embutido e o .docx sai gordo, mas sai.
#   Largura configurável por SOP_IMG_MAX_PX.
```

## Como funciona o mock

`capture_screens.py` primeiro faz login via `/dev-login` e, para cada endpoint em
`DATA_EPS`, busca a resposta **real** (que traz as colunas corretas, porém vazia)
e passa por `mockgen.transform()`:

- **Tabelas** (`{columns, rows, widgets}`): mantém as colunas reais e gera ~12
  linhas fictícias tipadas pelo nome da coluna (datas, CNPJs, contas, valores,
  moedas, strike, classe do ativo, etc.).
- **Cards / widgets** (NDF Summary, Other Products): preenche as contagens.
- **Dashboard** (`/api/dashboard-stats`): monta KPIs, distribuições, Top 5 e
  negócios recentes fictícios.

Durante a captura, um interceptor do Playwright responde essas rotas com o payload
fictício; as demais chamadas seguem normalmente (retornando vazio/real).

## Incluir um módulo novo no SOP

1. Desenvolva a rota e confirme que ela responde **200**.
2. Rode a captura (passos 2–3). O PNG sai como
   `docs/sop-screenshots/<rota-com-underscores>.png`.
3. No `SOP_PROCESSAMENTO_OTC.md`, copie o **bloco-modelo** (seção 8) para a
   subseção correta da seção 5 e aponte a imagem.
4. Rode `python scripts/build_sop_docx.py` para regerar o `.docx`.

## Notas

- O capturador ignora automaticamente rotas **não desenvolvidas** (que retornam
  404 no catch-all de template).
- Se precisar de mais/menos linhas fictícias ou de outra contraparte/valor,
  ajuste os pools no topo do `mockgen.py`.
- Variáveis de ambiente opcionais: `SOP_BASE_URL`, `SOP_LOGIN_PATH`, `SOP_CHROME`,
  `SOP_OUT_DIR` — este último grava os PNGs num diretório à parte, para conferir a
  rodada antes de sobrescrever as telas do guia (uma captura ruim não pode apagar
  a boa).
