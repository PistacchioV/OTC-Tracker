#!/usr/bin/env bash
# commit-push.sh
# Uso: ./scripts/commit-push.sh "mensagem do commit" [branch]
#
# Se apps/pages/routes.py estiver entre os arquivos alterados:
#   1. Remove o bloco DEV BYPASS do routes.py
#   2. Faz commit + push
#   3. Restaura o bloco DEV BYPASS no routes.py local

set -e

ROUTES="apps/pages/routes.py"
COMMIT_MSG="${1:?Informe a mensagem do commit como primeiro argumento}"
BRANCH="${2:-$(git rev-parse --abbrev-ref HEAD)}"

# Marcadores do bloco DEV BYPASS
DEV_MARKER_START="# DEV BYPASS"
DEV_MARKER_END="return redirect(url_for('pages_blueprint.dashboard'))"

# Verifica se routes.py está entre os arquivos modificados (staged ou unstaged)
ROUTES_CHANGED=false
if git diff --name-only HEAD 2>/dev/null | grep -q "$ROUTES"; then
    ROUTES_CHANGED=true
fi
if git diff --cached --name-only 2>/dev/null | grep -q "$ROUTES"; then
    ROUTES_CHANGED=true
fi
if git status --short 2>/dev/null | grep -q "$ROUTES"; then
    ROUTES_CHANGED=true
fi

if [ "$ROUTES_CHANGED" = true ]; then
    echo "⚠️  routes.py detectado — removendo bloco DEV BYPASS para o commit..."

    # Backup da versão dev
    cp "$ROUTES" "${ROUTES}.dev-backup"

    # Remove o bloco DEV BYPASS (do comentário até o return do dev_login)
    python3 - <<'PYEOF'
import re, sys

with open("apps/pages/routes.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove o bloco inteiro: do separador "# DEV BYPASS" até o final da função dev_login
pattern = r'\n\n# =+\n# DEV BYPASS.*?return redirect\(url_for\(.pages_blueprint\.dashboard.\)\)\n'
cleaned = re.sub(pattern, '', content, flags=re.DOTALL)

if cleaned == content:
    print("WARN: padrão DEV BYPASS não encontrado — routes.py não alterado")
    sys.exit(0)

with open("apps/pages/routes.py", "w", encoding="utf-8") as f:
    f.write(cleaned)

print("✅ Bloco DEV BYPASS removido")
PYEOF

fi

# Stage todos os arquivos modificados (ou mantém o staged atual)
git add -u

# Commit
git commit -m "$COMMIT_MSG

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"

# Push
git push origin "$BRANCH"
echo "✅ Push para $BRANCH concluído"

# Restaura a versão dev do routes.py
if [ "$ROUTES_CHANGED" = true ] && [ -f "${ROUTES}.dev-backup" ]; then
    mv "${ROUTES}.dev-backup" "$ROUTES"
    echo "✅ routes.py restaurado para versão dev local"
fi
