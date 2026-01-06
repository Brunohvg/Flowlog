#!/bin/bash

# ==========================================
# CONFIGURAÇÃO
# ==========================================
# Nome da imagem no Docker Hub
IMAGE_NAME="brunobh51/flowlog"

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== INICIANDO DEPLOY AUTOMATIZADO ===${NC}"

# 1. Verificar se está logado no Docker
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Erro: O Docker não está rodando ou você não tem permissão.${NC}"
    exit 1
fi

# 2. Perguntar a versão
echo -n "Digite a TAG da versão (ex: v1.0, v2, fix-bug): "
read VERSION

if [ -z "$VERSION" ]; then
    echo -e "${RED}Erro: A versão não pode ser vazia!${NC}"
    exit 1
fi

FULL_IMAGE_NAME="$IMAGE_NAME:$VERSION"
LATEST_IMAGE_NAME="$IMAGE_NAME:latest"

# 3. Build da Imagem
echo -e "\n${GREEN}[1/3] Construindo imagem Docker...${NC}"
# Usa o Dockerfile atual para criar a imagem com a tag escolhida
if docker build -t $FULL_IMAGE_NAME -t $LATEST_IMAGE_NAME .; then
    echo -e "${GREEN}Build com sucesso!${NC}"
else
    echo -e "${RED}Falha no Build. Verifique os erros acima.${NC}"
    exit 1
fi

# 4. Push para o Docker Hub
echo -e "\n${GREEN}[2/3] Enviando para o Docker Hub...${NC}"

echo "Enviando tag específica: $VERSION..."
docker push $FULL_IMAGE_NAME

echo "Enviando tag latest..."
docker push $LATEST_IMAGE_NAME

# 5. Conclusão
echo -e "\n${GREEN}=== SUCESSO! ===${NC}"
echo -e "A imagem foi enviada com as tags:"
echo -e "  -> $FULL_IMAGE_NAME"
echo -e "  -> $LATEST_IMAGE_NAME"
echo -e "\nAgora vá ao seu Portainer e atualize a Stack (Pull latest image)."
