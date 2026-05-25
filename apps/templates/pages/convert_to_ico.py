"""
============================================================================
SCRIPT:  convert_to_ico.py
DESCRIÇÃO: Converte uma imagem PNG para favicon . ico com múltiplos tamanhos
           Adiciona padding para deixar a imagem quadrada e evitar deformação

COMO USAR:
    1. Instale a biblioteca Pillow:  pip install Pillow
    2. Execute: python convert_to_ico. py
============================================================================
"""

from PIL import Image
import os

# ============================================================================
# CONFIGURAÇÃO
# Caminho da imagem original e destino do favicon
# ============================================================================

# Caminho da imagem original
INPUT_PATH = '/Users/giullianoaccarinideluccia/Desktop/OTC Tracker/apps/static/images/logo-sm.png'

# Caminho onde o favicon será salvo (mesma pasta)
OUTPUT_PATH = '/Users/giullianoaccarinideluccia/Desktop/OTC Tracker/apps/static/images/favicon.ico'

# ============================================================================
# TAMANHOS DO FAVICON
# Tamanhos padrão para compatibilidade com todos os navegadores
# ============================================================================
FAVICON_SIZES = [
    (16, 16),    # Aba do navegador
    (32, 32),    # Favoritos, atalhos
    (48, 48),    # Windows
    (64, 64),    # Alta resolução
    (128, 128),  # Chrome Web Store
    (256, 256),  # Dispositivos modernos
]


def convert_to_favicon(input_path, output_path):
    """
    Converte uma imagem para favicon .ico
    
    PROCESSO:
        1. Abre a imagem original
        2. Converte para RGBA (suporta transparência)
        3. Calcula padding para deixar quadrada
        4. Centraliza a imagem no canvas quadrado
        5. Gera múltiplos tamanhos
        6. Salva como .ico
    
    PARÂMETROS:
        input_path:  Caminho da imagem original (PNG, JPG, etc.)
        output_path: Caminho de destino do arquivo .ico
    """
    
    print(f"📂 Abrindo imagem: {input_path}")
    
    # Verifica se o arquivo existe
    if not os. path.exists(input_path):
        print(f"❌ ERRO: Arquivo não encontrado:  {input_path}")
        return False
    
    # Abre a imagem original
    img = Image.open(input_path)
    
    # Exibe informações da imagem original
    print(f"📐 Tamanho original: {img.size[0]}x{img.size[1]} pixels")
    print(f"🎨 Modo de cor: {img.mode}")
    
    # Converte para RGBA para suportar transparência
    if img.mode != 'RGBA':
        print("🔄 Convertendo para RGBA (transparência)...")
        img = img.convert('RGBA')
    
    # ========================================================================
    # CRIAÇÃO DO CANVAS QUADRADO
    # Para evitar deformação, a imagem precisa ser quadrada
    # Adicionamos padding transparente se necessário
    # ========================================================================
    
    width, height = img.size
    
    # Calcula o tamanho do lado do quadrado (usa o maior lado)
    max_side = max(width, height)
    
    print(f"📏 Criando canvas quadrado:  {max_side}x{max_side} pixels")
    
    # Cria um novo canvas quadrado com fundo transparente
    # (255, 255, 255, 0) = Branco totalmente transparente
    square_img = Image.new('RGBA', (max_side, max_side), (255, 255, 255, 0))
    
    # Calcula a posição para centralizar a imagem original
    x_offset = (max_side - width) // 2
    y_offset = (max_side - height) // 2
    
    print(f"📍 Centralizando imagem:  offset ({x_offset}, {y_offset})")
    
    # Cola a imagem original centralizada no canvas quadrado
    square_img.paste(img, (x_offset, y_offset), img)
    
    # ========================================================================
    # GERAÇÃO DOS MÚLTIPLOS TAMANHOS
    # Favicon . ico pode conter várias resoluções
    # ========================================================================
    
    print(f"\n🔧 Gerando favicon com {len(FAVICON_SIZES)} tamanhos...")
    
    # Lista para armazenar as imagens redimensionadas
    icon_images = []
    
    for size in FAVICON_SIZES: 
        # Redimensiona usando LANCZOS (melhor qualidade)
        resized = square_img.resize(size, Image.LANCZOS)
        icon_images.append(resized)
        print(f"   ✅ {size[0]}x{size[1]} pixels")
    
    # ========================================================================
    # SALVANDO O ARQUIVO .ICO
    # ========================================================================
    
    print(f"\n💾 Salvando favicon:  {output_path}")
    
    # Salva o primeiro tamanho e anexa os outros
    icon_images[0].save(
        output_path,
        format='ICO',
        sizes=[(img.size[0], img.size[1]) for img in icon_images],
        append_images=icon_images[1:]
    )
    
    # Verifica se o arquivo foi criado
    if os.path.exists(output_path):
        file_size = os.path.getsize(output_path)
        print(f"\n✅ SUCESSO!  Favicon criado!")
        print(f"   📁 Arquivo:  {output_path}")
        print(f"   📊 Tamanho: {file_size / 1024:.2f} KB")
        return True
    else:
        print(f"\n❌ ERRO: Falha ao criar o favicon")
        return False


# ============================================================================
# EXECUÇÃO DO SCRIPT
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🎨 CONVERSOR DE IMAGEM PARA FAVICON (. ico)")
    print("=" * 60)
    print()
    
    # Executa a conversão
    success = convert_to_favicon(INPUT_PATH, OUTPUT_PATH)
    
    print()
    print("=" * 60)
    
    if success:
        print("🎉 Conversão concluída com sucesso!")
        print()
        print("📋 PRÓXIMOS PASSOS:")
        print("   1. Verifique o arquivo favicon.ico gerado")
        print("   2. Teste no navegador")
        print("   3. Se necessário, ajuste e execute novamente")
    else:
        print("❌ Conversão falhou.  Verifique os erros acima.")
    
    print("=" * 60)