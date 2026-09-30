# -*- coding: utf-8 -*-
"""O cadastro de ESTRATÉGIAS de swap da B3 (Live Position › Swap › Strategy),
lido por contrato.

Mora na platform porque DUAS features perguntam por ele: a tela Strategy, que
o grava, e o Swap Calculator, que puxa dele as pontas do contrato que é de
estratégia — na posição da B3 esse contrato vem com as duas curvas `VCP`, e o
índice e a taxa de verdade só existem na consulta da estratégia. Feature não
importa feature (SoC-003).

Nada aqui importa `routes`.
"""
import re
import unicodedata

from apps.pages import data_store as _store
from apps.pages.data_paths import data_write


def norm_contract(s):
    """`#23F02430278` → `23F02430278` (a B3 escreve com `#`)."""
    return re.sub(r'\s+', '', str(s or '')).lstrip('#').strip().upper()


def norm_label(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', s).strip().lower()


def store_path():
    """O dataset. Função, não constante: montar no import abriria o armazém
    na subida (§522)."""
    return data_write('live-position', 'swap-strategy.json')


def read_all():
    """A lista gravada; ausente é lista vazia. Ocupado SOBE (`BancoOcupado`)."""
    fp = store_path()
    if not _store.exists(fp):
        return []
    lst = _store.read(fp)
    return lst if isinstance(lst, list) else []


def find(contract):
    """A estratégia de um contrato, ou `None`."""
    k = norm_contract(contract)
    if not k:
        return None
    for e in read_all():
        if norm_contract((e or {}).get('Contract')) == k:
            return e
    return None


def details(entry):
    """`{rótulo normalizado: valor}` dos dados da estratégia (vazio sem dados)."""
    out = {}
    for par in (entry or {}).get('Details') or []:
        if isinstance(par, (list, tuple)) and len(par) >= 2:
            out.setdefault(norm_label(par[0]), str(par[1] if par[1] is not None else '').strip())
    return out


def _unico(det, prefixo):
    """O único valor não vazio entre os rótulos que começam com `prefixo`;
    '' quando não há nenhum ou há mais de um diferente (não se chuta)."""
    vals = {v for k, v in det.items() if k.startswith(prefixo) and v}
    return vals.pop() if len(vals) == 1 else ''


def leg(det, n):
    """O que a estratégia diz da ponta `n` (1 = Parte, 2 = Contraparte — a
    mesma ordem de `Curva - Parte` / `Curva - Contraparte` da consulta):
    `{indicador, taxa, percentual, base}`, cada um '' quando a estratégia não
    tem a coluna. Os rótulos são os da B3 (`Indicador_1`, `taxa Cupom_1`,
    `Percentual Indicador_2`, `Base taxa Cupom_2`)."""
    def g(*nomes):
        for nome in nomes:
            v = det.get(norm_label(nome.format(n)), '')
            if v:
                return v
        return ''
    return {'indicador': g('Indicador_{}'), 'taxa': g('taxa Cupom_{}'),
            'percentual': g('Percentual Indicador_{}'), 'base': g('Base taxa Cupom_{}'),
            'contagem': g('Contagem de Dias_{}'),
            # A cotação INICIAL da moeda e o D-n da cotação final vêm de DUAS
            # formas. Numeradas (`Valor Inicial 1`, `Fixing 1`) são do
            # INDICADOR de mesmo número — só servem à ponta cujo indicador é a
            # própria moeda; na ponta de SOFR o `Fixing 2` seria o do índice.
            # Sem número (`Cotação Inicial Moeda`, `Data Cotação Moeda Final`)
            # valem para toda ponta convertida em moeda.
            'cotacao_indicador': g('Valor Inicial {}'),
            'deslocamento_indicador': g('Fixing {}'),
            'cotacao_moeda': g('Cotação Inicial Moeda'),
            'deslocamento_moeda': g('Data Cotação Moeda Final'),
            # O `_n` do lookback é o da TAXA flutuante, não o da ponta: na
            # USD × SOFR o `Lookback da Taxa_1` é da ponta 2. Vale o da ponta
            # quando existe; senão o ÚNICO que a estratégia traz.
            'lookback': g('Lookback da Taxa_{}') or _unico(det, 'lookback da taxa')}
