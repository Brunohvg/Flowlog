#!/bin/bash

# ==========================================
# FLOWLOG - DEPLOY SCRIPT (Robust Edition)
# ==========================================
# Este script automatiza o build, push e sincronização
# de dependências do sistema Flowlog.

set -e # Para o script no primeiro erro

# Nome da imagem no Docker Hub
IMAGE_NAME="brunobh51/flowlog"

# Cores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== INICIANDO DEPLOY AUTOMATIZADO ===${NC}"

# 1. Verificar se o Docker está acessível
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Erro: O Docker não está rodando ou você não tem permissão.${NC}"
    exit 1
fi

# 2. Sincronizar dependências (UV)
echo -e "\n${BLUE}[1/5] Sincronizando requirements.txt com uv...${NC}"
uv pip compile pyproject.toml --group infra -o requirements.txt
echo -e "${GREEN}Dependências sincronizadas!${NC}"

# 3. Rodar Qualidade & Testes
echo -e "\n${BLUE}[2/5] Rodando análise estática...${NC}"
uv run ruff check .

echo -e "\n${BLUE}[3/5] Rodando testes automatizados...${NC}"
USE_SQLITE=True DEBUG=True uv run pytest

# 4. Definir Versão
CURRENT_VERSION=$(grep -m 1 "version =" pyproject.toml | cut -d '"' -f 2)
echo -e "\n${BLUE}Qual a TAG desta versão? (Versão atual no pyproject: $CURRENT_VERSION)${NC}"
echo -e "Sugestão: v1.1.0 ou v1.2.0"

# Usar /dev/tty garante que a leitura venha do terminal mesmo se houver lixo no stdin
read -r -p "TAG: " VERSION < /dev/tty

if [ -z "$VERSION" ]; then
    echo -e "${RED}Erro: A versão não pode ser vazia!${NC}"
    exit 1
fi

FULL_IMAGE_NAME="$IMAGE_NAME:$VERSION"
LATEST_IMAGE_NAME="$IMAGE_NAME:latest"

# 5. Build da Imagem
echo -e "\n${BLUE}[4/5] Construindo imagem Docker...${NC}"
docker build -t $FULL_IMAGE_NAME -t $LATEST_IMAGE_NAME .

# 6. Push para o Docker Hub
echo -e "\n${BLUE}[5/5] Enviando para o Docker Hub...${NC}"
docker push $FULL_IMAGE_NAME
docker push $LATEST_IMAGE_NAME

# 7. Conclusão
echo -e "\n${GREEN}====================================${NC}"
echo -e "${GREEN}  DEPLOY CONCLUÍDO COM SUCESSO!     ${NC}"
echo -e "${GREEN}====================================${NC}"
echo -e "Imagens enviadas:"
echo -e "  -> $FULL_IMAGE_NAME"
echo -e "  -> $LATEST_IMAGE_NAME"
echo -e "\n${BLUE}Próximos passos:${NC}"
echo -e "1. Vá ao Portainer"
echo -e "2. Selecione a Stack Flowlog"
echo -e "3. Clique em 'Update the stack' e habilite 'Re-pull image'"
