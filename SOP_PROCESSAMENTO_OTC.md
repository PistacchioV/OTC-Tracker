# SOP — Procedimento Operacional Padrão
## Processamento de Operações de Derivativos OTC

---

| Campo | Conteúdo |
|---|---|
| **Empresa** | Meridian Capital Markets S.A. |
| **Sistema** | **DeriskOne** — Plataforma de Back Office de Derivativos OTC |
| **Documento** | SOP-OTC-001 |
| **Versão** | 1.0 |
| **Classificação** | Uso Interno — Operações de Back Office |
| **Data de emissão** | 08/07/2026 |
| **Próxima revisão** | 08/01/2027 |
| **Elaborado por** | Área de Documentação Técnica |
| **Aprovado por** | Gerência de Operações OTC |
| **Público-alvo** | Operador / Analista de Back Office de Derivativos |

> **Aviso de confidencialidade.** Todos os nomes de empresas, contrapartes, contas, datas e valores utilizados nos exemplos deste documento são **fictícios** e servem apenas para fins ilustrativos. Nenhum dado de produção, credencial, servidor ou parâmetro de ambiente real está reproduzido aqui.

---

## 2. Índice

1. [Cabeçalho](#sop--procedimento-operacional-padrão)
2. [Índice](#2-índice)
3. [Visão Geral](#3-visão-geral)
   - 3.1. [O que o sistema faz](#31-o-que-o-sistema-faz)
   - 3.2. [Produtos suportados](#32-produtos-suportados)
   - 3.3. [Conceito central: a Data Base](#33-conceito-central-a-data-base)
   - 3.4. [Campos validados em cada operação](#34-campos-validados-em-cada-operação)
   - 3.5. [Ciclo de vida de uma operação](#35-ciclo-de-vida-de-uma-operação)
4. [Passo a Passo Operacional](#4-passo-a-passo-operacional)
   - 4.1. [Pré-requisitos](#41-pré-requisitos-antes-de-começar)
   - 4.2. [Passo 1 — Autenticar e definir a Data Base](#42-passo-1--autenticar-e-definir-a-data-base)
   - 4.3. [Passo 2 — Importar / salvar os arquivos de posição](#43-passo-2--importar--salvar-os-arquivos-de-posição)
   - 4.4. [Passo 3 — Validar os campos da operação](#44-passo-3--validar-os-campos-da-operação)
   - 4.5. [Passo 4 — Processar / gerar o arquivo de registro](#45-passo-4--processar--gerar-o-arquivo-de-registro)
   - 4.6. [Passo 5 — Conferência (Recon) e encerramento](#46-passo-5--conferência-recon-e-encerramento)
5. [Tratamento de Exceções](#5-tratamento-de-exceções)
6. [Suporte](#6-suporte)

---

## 3. Visão Geral

### 3.1. O que o sistema faz

O **DeriskOne** é a plataforma de Back Office que consolida, valida, registra e concilia operações de **Derivativos de Balcão (OTC)** ao longo do ciclo diário de liquidação. O operador não digita cada contrato manualmente: o sistema **importa arquivos de posição** (planilhas e arquivos posicionais gerados pelos sistemas de front e pelas câmaras de registro), aplica **regras de validação de negócio**, gera os **arquivos de registro/liquidação** no layout exigido pela câmara e permite a **conciliação (recon)** contra os arquivos de retorno.

Toda a lógica de processamento é executada no servidor por rotas de API dedicadas; cada tela do operador dispara uma dessas rotas e exibe o resultado (sucesso, contadores, ou uma mensagem de erro específica). O processamento é sempre **ancorado a uma data de referência** (a *Data Base*), de modo que reprocessar um dia anterior nunca contamina o dia corrente.

### 3.2. Produtos suportados

| Produto OTC | O que o operador faz na plataforma |
|---|---|
| **Swap (MtM diário)** | Importa o arquivo de posição do swap e do COE, aplica os valores de marcação a mercado (MtM), gera o arquivo de registro e envia para conferência. |
| **Swap (Accrual — fim de mês)** | Calcula/importa os fatores de accrual, gera os arquivos de validação de fim de mês (EOM) e concilia contra o retorno da câmara. |
| **NDF (a termo de moeda)** | Consolida a posição viva de NDF, classifica os contratos (Vanilla / Outro Publicador / T+0 / Commodities) e gera o arquivo de registro. |
| **Opções (FXO e Commodities)** | Mantém o cache de novos negócios, gera o arquivo de registro (Conecta) e o mapeamento para a câmara. |
| **Liquidação / Registro em câmara** | Importa, edita, adiciona, remove e **confirma** linhas de liquidação (settlements) e operações. |
| **Intragrupo (Intrag)** | Envia, edita e **aprova** arquivos de operações intragrupo. |

### 3.3. Conceito central: a Data Base

A **Data Base** (rotulada nas telas como *Reference date* / *Data de referência*) é o eixo de todo o processamento. Regras que o operador precisa conhecer:

- Quando o campo de data é deixado **em branco**, o sistema assume automaticamente o **dia útil anterior** segundo o calendário de feriados (calendário da câmara/ANBIMA). O operador não precisa calcular o dia útil manualmente.
- Todos os arquivos importados, gerados e salvos são **organizados em pastas por data** (`AAAA / MM. Mês / DD`), garantindo rastreabilidade.
- As **linhas de dados** de um arquivo gerado usam a Data Base; os **cabeçalhos de controle** usam a data do sistema (hoje). Portanto, gerar um arquivo hoje para uma Data Base retroativa é uma operação suportada e esperada.
- Reprocessar uma Data Base **sobrescreve apenas a porção correspondente** do conjunto salvo daquele dia (ex.: reimportar o arquivo de swap preserva a porção de COE já carregada).

### 3.4. Campos validados em cada operação

O sistema valida, dependendo do produto, os seguintes atributos de cada contrato:

| Campo | Descrição | Observação de validação |
|---|---|---|
| **Trade Date** (Data de Negociação) | Data em que o negócio foi fechado. | Usada para agrupar os contratos por dia; formatos aceitos: `AAAA-MM-DD`, `DD/MM/AAAA` e `AAAA-MM-DD HH:MM:SS`. |
| **Maturity / Expiry Date** (Vencimento) | Data de vencimento/expiração do contrato. | Na *posição viva*, contratos vencidos são descartados da contagem. |
| **Strike Rate** (Preço de exercício) | Preço de exercício das opções. | Convertido para valor numérico; strike ausente em opção bloqueia a geração do arquivo. |
| **Notional** (Nocional) | Valor de referência (Total / Mínimo / Máximo). | Convertido de formato brasileiro (vírgula decimal) para numérico antes do registro. |
| **Data Base / Data de Referência MTM** | Data-âncora do processamento. | Se ausente, assume o dia útil anterior. |
| **Classe do Ativo Subjacente** | Categoria (ex.: Taxas de Câmbio, Commodities). | Usada para classificar e contabilizar os widgets de posição viva. |

### 3.5. Ciclo de vida de uma operação

```
   Definir Data Base
          │
          ▼
   Importar arquivo de posição  ──►  Validação de negócio (campos + regras)
          │                                    │
          │                             (erro) │ (ok)
          ▼                                    ▼
   Conferir contadores/telas          Gerar arquivo de registro (câmara)
          │                                    │
          ▼                                    ▼
   Conciliar (Recon) c/ retorno  ──►  Encerrar processo (End Process)
```

---

## 4. Passo a Passo Operacional

Esta seção descreve o fluxo genérico. Os produtos seguem a mesma sequência lógica — muda apenas a tela de origem.

### 4.1. Pré-requisitos (antes de começar)

- Estar com **sessão autenticada** válida (login + verificação em duas etapas). Sem autenticação, **toda** rota de processamento é recusada com erro `401`.
- Ter os **arquivos de posição do dia** disponíveis (na pasta de origem ou para arrastar na tela).
- Confirmar qual é a **Data Base** correta do processamento.

> **[IMAGEM 1: Tela de login do DeriskOne, com marcações apontando para — (1) campo de usuário, (2) campo de senha, (3) botão "Entrar" e (4) campo do código de verificação em duas etapas.]**

### 4.2. Passo 1 — Autenticar e definir a Data Base

1. Faça login e conclua a verificação em duas etapas.
2. Acesse o **Painel de Controle** (*Control Panel*).
3. No cartão da rotina desejada, localize o campo **Reference date** (Data de referência). Clique no ícone de calendário para abrir o *datepicker*.
4. Selecione a Data Base. **Deixe em branco** apenas se quiser processar o dia útil anterior automaticamente.

> **Exemplo fictício:** para reprocessar o fechamento do dia **02/03/2026** da contraparte **Aurora Trading Ltda.**, o operador seleciona `02/03/2026` no campo Reference date.

> **[IMAGEM 2: Cartão "Save CETIP Files" do Painel de Controle, com marcações apontando para — (1) campo "Reference date", (2) botão de calendário, (3) botão principal de processar e (4) botão secundário "Send to other areas".]**

### 4.3. Passo 2 — Importar / salvar os arquivos de posição

1. Na tela do produto (ex.: **MtM Swap**, **NDF Cockpit**, **OTM Settlements**), utilize a **área de upload (dropzone)** para arrastar os arquivos, ou acione o botão de importação da pasta.
2. O sistema **identifica automaticamente o tipo de arquivo** pelo nome (posição de swap, COE, valores de MtM, etc.) e o direciona para a porção correta do conjunto do dia.
3. Ao concluir, a tela exibe os **contadores por categoria** (quantas linhas foram carregadas em cada livro/tabela).

> **Exemplo fictício:** o operador arrasta o arquivo `Posicao_Swap_Aurora_20260302.xlsx`. O sistema reconhece que é o arquivo de swap, carrega **128** contratos e exibe o contador atualizado.

> **[IMAGEM 3: Tela de importação com a dropzone destacada — (1) área para arrastar arquivos, (2) lista de arquivos reconhecidos, (3) contadores por categoria após o processamento.]**

### 4.4. Passo 3 — Validar os campos da operação

1. Antes de gerar qualquer arquivo, revise as linhas na tabela (Trade Date, Vencimento, Strike, Nocional, Classe do Ativo).
2. Corrija linhas sinalizadas usando as ações **Adicionar / Editar / Remover** (`row/add`, `row/edit`, `row/delete`).
3. Marque as linhas conferidas com **Confirmar** (`row/confirm`).
4. Acione a rotina de **Validação** do produto (ex.: *Validation* no MtM/Accrual). Se houver linhas obrigatórias ausentes, o sistema **bloqueia** a etapa e retorna a lista dos itens pendentes.

> **Exemplo fictício:** ao rodar a Validação de fim de mês, o sistema retorna `missing_accrual` apontando **3** contratos da contraparte **Blue Harbor Fundo Multimercado** sem fator de accrual. O operador preenche os fatores e repete a validação.

> **[IMAGEM 4: Tabela de operações com marcações — (1) coluna Notional, (2) coluna Strike, (3) coluna Vencimento, (4) botões de ação por linha (Editar/Remover/Confirmar) e (5) botão "Validation".]**

### 4.5. Passo 4 — Processar / gerar o arquivo de registro

1. Com os dados válidos, acione o botão principal de processamento da tela (ex.: **Process**, **Send batch**, **Send to Conecta**).
2. O sistema gera o **arquivo de registro no layout da câmara** e o salva na pasta datada correspondente.
3. Quando aplicável, o sistema **dispara o e-mail** para a área responsável (o envio ocorre em segundo plano — a resposta da tela não fica travada aguardando o servidor de e-mail).
4. Confira a mensagem de sucesso, os contadores e os nomes dos arquivos gerados/anexados.

> **Exemplo fictício:** o operador clica em **Send batch**. O sistema gera `Registro_MTM_20260302.txt` com **128** registros, salva na pasta `2026 / 03. Março / 02` e enfileira o e-mail para a equipe de Operações OTC.

> **[IMAGEM 5: Cartão do produto após o processamento — (1) botão "Process/Send batch", (2) resumo com contagem de registros gerados, (3) lista de arquivos gerados e (4) indicador de e-mail enfileirado.]**

### 4.6. Passo 5 — Conferência (Recon) e encerramento

1. Importe o **arquivo de retorno** da câmara e acione a rotina de **Recon** (conciliação).
2. O sistema compara o registro enviado contra o retorno e sinaliza cada linha como **OK** ou **Check** (divergente).
3. Trate as divergências e, quando tudo estiver conciliado, acione **End Process** (encerrar processo) para consolidar o dia.

> **[IMAGEM 6: Tela de Recon com marcações — (1) importação do arquivo de retorno, (2) coluna de status OK/Check, (3) linhas divergentes destacadas e (4) botão "End Process".]**

---

## 5. Tratamento de Exceções

O DeriskOne devolve mensagens padronizadas por rota. A tabela abaixo mapeia os **erros reais retornados pelo backend** e a ação recomendada ao operador.

| Código / Mensagem | Quando ocorre | O que o operador deve fazer |
|---|---|---|
| **HTTP 401 — `Not authenticated`** | A sessão expirou ou o operador não está logado. | Refaça o login e a verificação em duas etapas; repita a ação. |
| **HTTP 400 — `No file provided.`** | Nenhum arquivo foi enviado na importação. | Selecione/arraste o arquivo antes de acionar o botão. |
| **HTTP 400 — `Invalid date (expected YYYY-MM-DD).`** | A data informada está em formato inválido. | Use o *datepicker* em vez de digitar; confira o formato da Data Base. |
| **HTTP 400 — `Unrecognized file. Expected the swap / COE / values file.`** | O nome do arquivo não corresponde a nenhum tipo esperado. | Verifique se está enviando o arquivo correto e com o nome padrão; renomeie se necessário. |
| **HTTP 400 — `No files found in the source folder.`** | A pasta de origem da Data Base está vazia. | Confirme se os arquivos do dia já foram depositados na pasta; aguarde a carga da câmara ou corrija a Data Base. |
| **HTTP 400 — `No CEM/EDG rows loaded for this date — import the … file first.`** | Tentou-se aplicar valores de MtM antes de importar a posição base. | Importe primeiro o arquivo de posição; depois aplique os valores. |
| **HTTP 400 — `missing_accrual` (+ lista de pendências)** | Existem contratos obrigatórios sem fator de accrual na validação de fim de mês. | Preencha os fatores dos contratos listados e rode a Validação novamente. |
| **HTTP 400 — `No … records to validate / No deals provided`** | Não há registros elegíveis para o processamento acionado. | Verifique se a importação trouxe linhas e se a Data Base está correta. |
| **HTTP 404 — `No saved data for this date.`** | Não existe conjunto salvo para a Data Base selecionada. | Rode primeiro a importação/processamento do dia antes da validação ou do recon. |
| **HTTP 500 — `Failed to read the file.` / `Failed to save.` / `Failed to write the batch files.`** | Falha interna ao ler, salvar ou gerar arquivos (erro registrado no log do servidor com *traceback*). | Não é erro de digitação: tente novamente uma vez; se persistir, acione o Suporte de TI informando a rotina, a Data Base e o horário. |
| **Validação de formulário (campo inválido na tela)** | Campo obrigatório vazio ou valor fora do padrão (ex.: Strike ausente em opção, Nocional não numérico). | Corrija o campo destacado na linha (Editar) e reconfirme antes de processar. |

> **Regra geral de leitura de erros:** mensagens **HTTP 400/404** indicam algo que o **operador pode corrigir** (arquivo, data ou dado faltante). Mensagens **HTTP 500** indicam **falha do sistema** — devem ser encaminhadas ao Suporte de TI, pois ficam registradas no log com o rastreamento completo.

---

## 6. Suporte

> Os contatos abaixo são **fictícios** e servem apenas de modelo para o preenchimento com os dados reais da sua organização.

| Nível | Canal | Contato | Horário |
|---|---|---|---|
| **1 — Central de Serviços de TI** | Portal / Telefone | portal.suporte.meridian.example · +55 (11) 4000-0000 | 24 x 7 |
| **2 — Suporte à Aplicação (DeriskOne)** | E-mail | suporte.deriskone@meridian.example | Dias úteis, 07h–20h (BRT) |
| **3 — Especialista de Back Office OTC (plantão)** | E-mail / Telefone | plantao.otc@meridian.example · +55 (11) 4000-0099 | Dias úteis, 06h–22h (BRT) |
| **Emergências de fechamento** | Telefone (plantão) | +55 (11) 90000-0000 | Durante a janela de liquidação |

**Ao abrir um chamado, informe sempre:**
1. A **rotina/tela** utilizada (ex.: MtM Swap → Send batch).
2. A **Data Base** do processamento.
3. A **mensagem de erro exata** exibida na tela e o **horário** aproximado.
4. O **nome do arquivo** envolvido (sem anexar dados sensíveis de clientes).

---

*Documento gerado pela área de Documentação Técnica — Meridian Capital Markets S.A. Uso interno. Revisar semestralmente ou a cada mudança relevante no fluxo de processamento OTC.*
