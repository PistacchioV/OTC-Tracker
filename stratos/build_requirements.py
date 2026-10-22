"""Gera stratos/requirements.txt: o bloco do template do Stratos + o que o OTC precisa.

O `requirements.txt` do singing-moose-flask tem um bloco DO NOT DELETE (o índice
do Artifactory, o Flask, o Stratos, o OpenTelemetry) e, abaixo da marca
`ADD YOUR OTHER REQUIREMENTS HERE`, o que a solução acrescenta. O acréscimo SAI
do requirements.txt da raiz — o mesmo que a instância do time instala —, então
dependência nova na dev chega ao Stratos no próximo merge, sem ninguém lembrar.

Fica de fora: o que o bloco já declara (lá vale a versão do template) e o que só
serve ao jeito de subir da instância do time, que o Stratos não usa.

    python stratos/build_requirements.py          # regrava
    python stratos/build_requirements.py --check  # 1 se o arquivo está velho
"""
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
ORIGEM = os.path.join(RAIZ, 'requirements.txt')
DESTINO = os.path.join(AQUI, 'requirements.txt')

# Verbatim do template (requirements.txt do singing-moose-flask). Não mexa:
# é o bloco que o pipeline do Stratos espera encontrar intacto.
TEMPLATE = """\
########### DO NOT DELETE ###########
--index-url=https://artifacts-read.gkp.jpmchase.net/artifactory/api/pypi/pypi/simple/

setuptools>=70.0.0
stratos-config==1.0.12
stratos-blocks>=1.3.19
Flask==3.1.2
werkzeug==3.1.6
pytest==9.1.1
pytest-cov==7.1.0
# OpenTelemetry (sends traces to the ADOT sidecar on http://localhost:4318).
opentelemetry-api>=1.29.0
opentelemetry-sdk>=1.29.0
opentelemetry-exporter-otlp-proto-http>=1.29.0
opentelemetry-instrumentation-flask>=0.50b0
opentelemetry-instrumentation-requests>=0.50b0
json-log-formatter>=1.1
requests==2.34.2
pytest-xdist==3.8.0
pywin32==311; sys_platform == 'win32'
########### DO NOT DELETE ###########



########### ADD YOUR OTHER REQUIREMENTS HERE ###########
"""

# Só servem à subida da instância do time: o run.py da raiz (Minify, .env) e os
# servidores WSGI do .bat. No Stratos quem sobe é o `python solution.py`.
NAO_USADOS = {
    'flask-minify': 'run.py da raiz',
    'python-dotenv': 'run.py da raiz',
    'gunicorn': 'servidor da instancia do time',
    'waitress': 'servidor da instancia do time',
}


def nome(linha):
    m = re.match(r'\s*([A-Za-z0-9][A-Za-z0-9._-]*)', linha)
    return re.sub(r'[-_.]+', '-', m.group(1)).lower() if m else None


def requisitos(texto):
    """[(nome normalizado, requisito sem comentário)] — pula opções do pip."""
    out = []
    for bruta in texto.splitlines():
        linha = bruta.split(' #')[0].split('\t#')[0].strip()
        if not linha or linha.startswith(('#', '-')):
            continue
        out.append((nome(linha), linha))
    return out


def gera():
    with open(ORIGEM, encoding='utf-8') as fh:
        otc = requisitos(fh.read())
    do_template = {n for n, _ in requisitos(TEMPLATE)}
    linhas = [
        '# Gerado por stratos/build_requirements.py a partir do requirements.txt',
        '# da raiz do OTC Tracker. Nao edite a mao: rode o script.',
    ]
    for n, req in otc:
        if n in do_template or n in NAO_USADOS:
            continue
        linhas.append(req)
    return TEMPLATE + '\n'.join(linhas) + '\n'


def main():
    novo = gera()
    atual = open(DESTINO, encoding='utf-8').read() if os.path.exists(DESTINO) else None
    if '--check' in sys.argv:
        if atual != novo:
            print('stratos/requirements.txt desatualizado: rode python stratos/build_requirements.py')
            return 1
        print('stratos/requirements.txt OK')
        return 0
    if atual != novo:
        with open(DESTINO, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(novo)
        print('stratos/requirements.txt regravado')
    else:
        print('stratos/requirements.txt ja estava em dia')
    return 0


if __name__ == '__main__':
    sys.exit(main())
