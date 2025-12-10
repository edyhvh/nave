#!/usr/bin/env python3
"""
AAII Sentiment Survey Scraper - Script Ultra Simple

Instalación rápida:
pip install playwright pandas
playwright install chromium

Uso:
python check_aaii.py
"""

import sys
import subprocess

def install_dependencies():
    """Instalar dependencias si no están disponibles"""
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        print("Instalando dependencias...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "pandas", "--quiet"])
            subprocess.check_call(["playwright", "install", "chromium", "--quiet"])
            print("Dependencias instaladas correctamente")
            return True
        except Exception as e:
            print(f"Error instalando dependencias: {e}")
            return False

def main():
    if not install_dependencies():
        print("No se pudieron instalar las dependencias. Instala manualmente:")
        print("pip install playwright pandas")
        print("playwright install chromium")
        return

    from playwright.sync_api import sync_playwright
    from datetime import datetime

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            # Cargar página
            page.goto("https://www.aaii.com/sentimentsurvey", wait_until="networkidle", timeout=30000)

            # Esperar contenido dinámico
            page.wait_for_timeout(3000)

            # Estrategia principal: buscar tabla con datos de sentimiento
            table = page.query_selector("table")

            if not table:
                print("AAII Survey no disponible o cambió la web → revisar selector")
                return

            # Verificar que tiene datos de sentimiento
            table_text = table.inner_text().lower()
            if not ('bull' in table_text and 'bear' in table_text and '%' in table_text):
                print("AAII Survey no disponible o cambió la web → revisar selector")
                return

            # Extraer filas
            rows = table.query_selector_all("tr")
            if len(rows) < 2:
                print("AAII Survey no disponible o cambió la web → revisar selector")
                return

            # Primera fila de datos (después del header)
            first_data_row = rows[1]
            cells = first_data_row.query_selector_all("td, th")

            # Extraer valores numéricos
            values = []
            for cell in cells:
                text = cell.inner_text().strip()
                if '%' in text:
                    try:
                        val = float(text.replace('%', '').replace(',', '').strip())
                        values.append(val)
                    except ValueError:
                        continue

            if len(values) < 2:
                print("AAII Survey no disponible o cambió la web → revisar selector")
                return

            bullish = values[0]
            bearish = values[1]
            spread = bullish - bearish

            fecha = datetime.now().strftime("%d %b %Y")

            print("AAII Survey funcionando correctamente")
            print(f"Última lectura ({fecha}): Bullish {bullish:.1f}% | Bearish {bearish:.1f}% | Spread {spread:+.1f}%")
            print("Indicador LISTO para usar en NAVE como filtro psicológico")

        except Exception as e:
            print("AAII Survey no disponible o cambió la web → revisar selector")
            print(f"Error: {str(e)}")

        finally:
            browser.close()

if __name__ == "__main__":
    main()