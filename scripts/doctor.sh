#!/usr/bin/env bash
set -uo pipefail

failed=0

ok() {
  printf 'OK    %s\n' "$1"
}

fail() {
  printf 'FALLO %s\n' "$1"
  failed=1
}

echo "== Entorno local =="
if ! command -v conda >/dev/null 2>&1; then
  fail "Conda no está disponible."
elif [ "${CONDA_DEFAULT_ENV:-}" != "etl-factory-databricks" ]; then
  fail "Activa el entorno: conda activate etl-factory-databricks"
else
  ok "Entorno Conda activo: ${CONDA_DEFAULT_ENV}"
fi

if command -v python >/dev/null 2>&1; then
  python_version=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
  python_minor=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  if [ "$python_minor" = "3.11" ]; then
    ok "Python ${python_version}"
  else
    fail "Python ${python_version}; se requiere 3.11.x."
  fi
else
  fail "Python no está disponible."
fi

echo
echo "== Herramientas =="
if command -v git >/dev/null 2>&1; then
  git_output=$(git --version)
  git_major=$(printf '%s' "$git_output" | grep -Eo '[0-9]+' | head -n 1)
  if [ "${git_major:-0}" -ge 2 ]; then
    ok "$git_output"
  else
    fail "${git_output}; se requiere Git 2.x o superior."
  fi
else
  fail "Git no está instalado."
fi

if command -v gh >/dev/null 2>&1; then
  gh_version=$(gh --version | head -n 1)
  gh_major=$(printf '%s' "$gh_version" | grep -Eo '[0-9]+' | head -n 1)
  if [ "${gh_major:-0}" -ge 2 ]; then
    ok "$gh_version"
  else
    fail "${gh_version}; se requiere GitHub CLI 2.x o superior."
  fi
else
  fail "GitHub CLI no está instalada."
fi

if command -v databricks >/dev/null 2>&1; then
  cli_output=$(databricks version 2>&1)
  cli_version=$(printf '%s' "$cli_output" | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)
  case "$cli_version" in
    1.12.*) ok "Databricks CLI ${cli_version}" ;;
    *) fail "Databricks CLI ${cli_version:-desconocida}; se requiere 1.12.x." ;;
  esac
else
  fail "Databricks CLI no está instalada."
fi

echo
echo "== Identidades =="
if gh auth status >/dev/null 2>&1; then
  ok "GitHub CLI autenticada."
else
  fail "GitHub CLI no está autenticada; ejecuta: gh auth login"
fi

if current_user=$(databricks current-user me --profile sandbox -o json 2>/dev/null); then
  if user_name=$(printf '%s' "$current_user" | python -c 'import json,sys; print(json.load(sys.stdin)["userName"])' 2>/dev/null) && [ -n "$user_name" ]; then
    ok "Profile sandbox autenticado como ${user_name}"
  else
    fail "La respuesta de sandbox no contiene un userName válido."
  fi
else
  fail "Profile sandbox inválido; repite databricks auth login."
fi

echo
echo "== Git =="
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  fail "La carpeta no es un repositorio Git."
else
  if git config --get user.name >/dev/null && git config --get user.email >/dev/null; then
    ok "Autor Git configurado."
  else
    fail "Configura user.name y user.email de Git."
  fi

  if remote_url=$(git remote get-url origin 2>/dev/null); then
    ok "Remoto origin: ${remote_url}"
  else
    fail "El remoto origin no está configurado."
  fi
fi

echo
echo "== Ingeniería Python =="
for tool in ruff pytest build; do
  if python -m "$tool" --version >/dev/null 2>&1; then
    tool_version=$(python -m "$tool" --version 2>&1 | head -n 1)
    ok "$tool_version"
  else
    fail "$tool no está disponible; ejecuta: make env-update"
  fi
done

if python -c 'import enterprise_fabric' >/dev/null 2>&1; then
  ok "Paquete enterprise_fabric instalado."
else
  fail "Paquete no instalado; ejecuta: make install"
fi

echo
if [ "$failed" -ne 0 ]; then
  echo "doctor.sh: hay problemas pendientes."
  exit 1
fi

echo "doctor.sh: todo en orden."
