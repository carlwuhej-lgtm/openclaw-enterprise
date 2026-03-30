#!/bin/bash
# OpenClaw Enterprise Agent Client - 多平台打包脚本

set -e

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION="1.0.0"
OUTPUT_DIR="./dist"
APP_NAME="ocw-agent"

echo -e "${GREEN}🐱 OpenClaw Enterprise Agent Client 打包脚本${NC}"
echo ""

# 清理旧文件
echo -e "${YELLOW}🗑️  清理旧文件...${NC}"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# 支持的平台
PLATFORMS=(
    "linux/amd64"
    "linux/arm64"
    "darwin/amd64"
    "darwin/arm64"
    "windows/amd64"
)

echo -e "${YELLOW}📦 开始编译...${NC}"

for PLATFORM in "${PLATFORMS[@]}"; do
    GOOS="${PLATFORM%/*}"
    GOARCH="${PLATFORM#*/}"
    
    OUTPUT_NAME="$APP_NAME"
    if [ "$GOOS" = "windows" ]; then
        OUTPUT_NAME="$APP_NAME.exe"
    fi
    
    OUTPUT_PATH="$OUTPUT_DIR/$OUTPUT_NAME"
    
    # 构建目录结构
    BUILD_DIR="$OUTPUT_DIR/${GOOS}-${GOARCH}"
    mkdir -p "$BUILD_DIR"
    
    echo -e "${GREEN}  编译 $GOOS/$GOARCH...${NC}"
    
    # 编译
    GOOS=$GOOS GOARCH=$GOARCH go build \
        -ldflags="-s -w -X main.Version=$VERSION" \
        -trimpath \
        -o "$BUILD_DIR/$OUTPUT_NAME" \
        .
    
    # 复制安装脚本
    if [ "$GOOS" = "windows" ]; then
        cp install.ps1 "$BUILD_DIR/"
    else
        cp install.sh "$BUILD_DIR/"
        chmod +x "$BUILD_DIR/install.sh"
    fi
    
    # 复制 README
    cp README.md "$BUILD_DIR/"
    
    # 打包
    echo -e "${GREEN}  打包 $GOOS-$GOARCH...${NC}"
    cd "$BUILD_DIR"
    if [ "$GOOS" = "windows" ]; then
        zip -q "../../${APP_NAME}-${VERSION}-${GOOS}-${GOARCH}.zip" *
    else
        tar -czf "../../${APP_NAME}-${VERSION}-${GOOS}-${GOARCH}.tar.gz" *
    fi
    cd - > /dev/null
    
    echo -e "${GREEN}  ✅ ${APP_NAME}-${VERSION}-${GOOS}-${GOARCH}.tar.gz${NC}"
done

echo ""
echo -e "${GREEN}✅ 打包完成！${NC}"
echo ""
echo -e "${YELLOW}📦 生成文件:${NC}"
ls -lh "$OUTPUT_DIR"/*.tar.gz "$OUTPUT_DIR"/*.zip 2>/dev/null || true
echo ""
echo -e "${YELLOW}📝 文件名格式: ${APP_NAME}-${VERSION}-{OS}-{ARCH}.{ext}${NC}"
echo ""
echo -e "${GREEN}🐱 Done!${NC}"