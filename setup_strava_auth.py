#!/usr/bin/env python3
"""
Helper script para configurar autenticación de Strava.
Guía paso a paso para obtener tokens y cookies.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def wait_continue():
    """Esperar a que el usuario presione ENTER para continuar"""
    print()
    input("⏎ Presioná ENTER para continuar...")
    print()


def setup_api_tokens():
    """Guía para obtener API tokens"""
    print_section("PASO 1: API Tokens de Strava")
    
    print("Necesitás crear una aplicación en Strava para obtener tokens de API.")
    print()
    print("1. Andá a https://www.strava.com/settings/api")
    print("2. Clickeá 'Create App'")
    print("3. Completá los datos:")
    print("   - Application Name: MiOverlayCiclismo (o lo que quieras)")
    print("   - Category: Training")
    print("   - Website: http://localhost")
    print("   - Authorization Callback Domain: localhost")
    print()
    print("4. Una vez creada, anotá:")
    print("   - Client ID")
    print("   - Client Secret")
    print()
    
    client_id = input("Ingresá tu Client ID: ").strip()
    client_secret = input("Ingresá tu Client Secret: ").strip()
    
    if not client_id or not client_secret:
        print("❌ Client ID y Client Secret son obligatorios")
        return False
    
    # Guardar en .env del proyecto Strava-Scraper-Leaderboard
    # Detectar ruta relativa (asume que está en el mismo directorio padre que este proyecto)
    strava_project = Path(__file__).parent.parent / "Strava-Scraper-Leaderboard"
    # Si no existe, permitir ingresar ruta manual
    if not strava_project.exists():
        print(f"⚠️  No se encontró el proyecto en: {strava_project}")
        custom_path = input("Ingresá la ruta al proyecto Strava-Scraper-Leaderboard (o ENTER para salir): ").strip()
        if custom_path:
            strava_project = Path(custom_path)
        else:
            print("❌ No se puede continuar sin el proyecto Strava-Scraper-Leaderboard")
            return False
    env_path = strava_project / ".env"
    
    env_content = f"""# Strava API Credentials
STRAVA_CLIENT_ID={client_id}
STRAVA_CLIENT_SECRET={client_secret}
STRAVA_REDIRECT_URI=http://localhost:8080/callback

# Tokens (se completan automáticamente con auth_strava.py)
STRAVA_ACCESS_TOKEN=
STRAVA_REFRESH_TOKEN=
STRAVA_EXPIRES_AT=

# Para scraping (copiar desde DevTools)
STRAVA_COOKIES_HEADER=
"""
    
    env_path.write_text(env_content, encoding='utf-8')
    print(f"✅ Guardado en: {env_path}")
    
    print()
    print("🌐 Ahora se abrirá el navegador para autorizar la app...")
    print("   Después de autorizar, volvé acá para continuar.")
    print()
    
    wait_continue()
    
    # Ejecutar auth_strava.py automáticamente
    auth_script = strava_project / "auth_strava.py"
    if auth_script.exists():
        print("🔄 Ejecutando auth_strava.py...")
        print("   (Se abrirá el navegador)")
        print()
        
        result = subprocess.run(
            [sys.executable, str(auth_script)],
            cwd=str(strava_project)
        )
        
        if result.returncode == 0:
            print()
            print("✅ Tokens de API obtenidos exitosamente!")
            return True
        else:
            print()
            print("❌ Error al obtener tokens. Intentá manualmente:")
            print(f"   cd {strava_project}")
            print("   python auth_strava.py")
            return False
    else:
        print(f"❌ No se encontró {auth_script}")
        print("   Asegurate de tener el proyecto Strava-Scraper-Leaderboard")
        return False


def setup_cookies():
    """Guía para obtener cookies del navegador"""
    print_section("PASO 2: Cookies del Navegador")
    
    print("Las cookies son necesarias para hacer scraping de los leaderboards.")
    print("Strava no expone esta info por API pública.")
    print()
    print("INSTRUCCIONES:")
    print()
    print("1. Abrí Chrome/Edge y andá a https://www.strava.com")
    print("2. Logueate con tu cuenta")
    print("3. Presioná F12 para abrir DevTools")
    print("4. Andá a la pestaña 'Network' (o 'Red')")
    print("5. Recargá la página (F5)")
    print("6. En la lista de requests, buscá uno que diga 'strava.com'")
    print("7. Click en el request → Headers → Request Headers")
    print("8. Buscá 'cookie:' y copiá TODO el valor")
    print()
    print("   Ejemplo de cómo se ve:")
    print("   cookie: _strava4_session=abc123; _strava4_session_csrf_token=xyz789; ...")
    print()
    print("9. Pegalo acá abajo (podés pegar varias líneas, terminá con ENTER):")
    print()
    
    # Leer cookies (multilinea)
    print("Pegá las cookies (ENTER dos veces para terminar):")
    lines = []
    while True:
        try:
            line = input()
            if not line and lines:  # Enter en línea vacía, terminamos
                break
            lines.append(line)
        except EOFError:
            break
    
    cookies = " ".join(lines).strip()
    
    if not cookies:
        print("❌ No se ingresaron cookies")
        return False
    
    # Limpiar cookies (quitar posible prefijo "cookie: " o "Cookie: ")
    if cookies.lower().startswith("cookie:"):
        cookies = cookies.split(":", 1)[1].strip()
    
    # Guardar en .env
    strava_project = Path(__file__).parent.parent / "Strava-Scraper-Leaderboard"
    if not strava_project.exists():
        print(f"⚠️  No se encontró el proyecto en: {strava_project}")
        custom_path = input("Ingresá la ruta al proyecto Strava-Scraper-Leaderboard (o ENTER para salir): ").strip()
        if custom_path:
            strava_project = Path(custom_path)
        else:
            print("❌ No se puede continuar sin el proyecto Strava-Scraper-Leaderboard")
            return False
    env_path = strava_project / ".env"
    
    if env_path.exists():
        content = env_path.read_text(encoding='utf-8')
        # Reemplazar línea existente o agregar al final
        if 'STRAVA_COOKIES_HEADER=' in content:
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if line.startswith('STRAVA_COOKIES_HEADER='):
                    new_lines.append(f'STRAVA_COOKIES_HEADER={cookies}')
                else:
                    new_lines.append(line)
            content = '\n'.join(new_lines)
        else:
            content += f"\nSTRAVA_COOKIES_HEADER={cookies}\n"
        
        env_path.write_text(content, encoding='utf-8')
    else:
        print(f"❌ No se encontró {env_path}. Ejecutá primero el Paso 1.")
        return False
    
    print()
    print(f"✅ Cookies guardadas en: {env_path}")
    print()
    print("⚠️  IMPORTANTE: Las cookies expiran en ~1 semana.")
    print("    Si el scraping falla, repetí este paso para actualizarlas.")
    
    return True


def test_setup():
    """Testear la configuración"""
    print_section("PASO 3: Testear Configuración")
    
    strava_project = Path(__file__).parent.parent / "Strava-Scraper-Leaderboard"
    if not strava_project.exists():
        print(f"⚠️  No se encontró el proyecto en: {strava_project}")
        custom_path = input("Ingresá la ruta al proyecto Strava-Scraper-Leaderboard (o ENTER para salir): ").strip()
        if custom_path:
            strava_project = Path(custom_path)
        else:
            print("❌ No se puede continuar sin el proyecto Strava-Scraper-Leaderboard")
            return False
    env_path = strava_project / ".env"
    
    if not env_path.exists():
        print(f"❌ No se encontró {env_path}")
        print("   Ejecutá primero los pasos 1 y 2.")
        return False
    
    content = env_path.read_text(encoding='utf-8')
    
    has_client_id = 'STRAVA_CLIENT_ID=' in content and 'STRAVA_CLIENT_ID=\n' not in content
    has_cookies = 'STRAVA_COOKIES_HEADER=' in content and 'STRAVA_COOKIES_HEADER=\n' not in content
    
    print("Verificando configuración:")
    print()
    print(f"  [✓] API Client ID: {'SÍ' if has_client_id else 'NO'}")
    print(f"  [✓] Cookies: {'SÍ' if has_cookies else 'NO'}")
    print()
    
    if has_client_id and has_cookies:
        print("✅ Configuración completa!")
        print()
        print("Podés empezar a usar:")
        print("  python build_segment_overlay_data.py --gpx carrera.gpx --activity-url URL")
        return True
    else:
        print("❌ Faltan datos. Completá los pasos anteriores.")
        return False


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║     SETUP DE AUTENTICACIÓN STRAVA - Segment Overlays           ║
║                                                              ║
║  Este script te guía paso a paso para configurar todo lo     ║
║  necesario para obtener datos de segmentos de Strava.        ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    print("Menú:")
    print()
    print("  1. Configurar API Tokens (Paso 1)")
    print("  2. Configurar Cookies (Paso 2)")
    print("  3. Testear configuración (Paso 3)")
    print("  4. Todo el proceso completo")
    print()
    print("  q. Salir")
    print()
    
    choice = input("Elegí una opción (1-4 o q): ").strip().lower()
    
    if choice == '1':
        result = setup_api_tokens()
        if result:
            # Continuar automáticamente al paso 2
            print()
            print("=" * 60)
            print("¿Continuar con la configuración de cookies?")
            print("=" * 60)
            cont = input("Presioná ENTER para continuar, o 'n' para salir: ").strip().lower()
            if cont != 'n':
                setup_cookies()
                print()
                test_setup()
    elif choice == '2':
        setup_cookies()
    elif choice == '3':
        test_setup()
    elif choice == '4':
        # Proceso completo automático
        result = setup_api_tokens()
        if result:
            print("\n" + "=" * 60)
            print("PASO 1 completado. Continuando con PASO 2...")
            print("=" * 60)
            wait_continue()
            setup_cookies()
            print()
            test_setup()
    elif choice == 'q':
        print("👋 Chau!")
        return
    else:
        print("Opción inválida")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrumpido por el usuario.")
        sys.exit(0)
