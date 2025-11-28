from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timedelta
import pandas as pd
import re
import os
from io import StringIO
from webdriver_manager.chrome import ChromeDriverManager

# === CONFIGURACIÓN ===

# Fecha de ayer
ayer = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

# URL del día anterior (tu misma URL)
url = f"https://www.wunderground.com/dashboard/pws/ITENJO7/table/{ayer}/{ayer}/daily"

# Archivo de salida (se guardará en el raíz del repo)
archivo = "datos_meteorologicos.xlsx"
hoja_excel = "historico"

# === CONVERSIONES ===

def fahrenheit_to_celsius(temp_str):
    try:
        value = float(str(temp_str).split('°')[0])
        if value > 45:  # Fahrenheit
            return round((value - 32) * 5 / 9, 1)
        return round(value, 1)
    except:
        return None

def mph_to_kmh(speed_str):
    try:
        value = float(str(speed_str).split()[0])
        return round(value * 1.60934, 1)
    except:
        return None

def inHg_to_hPa(pressure_str):
    try:
        value = float(str(pressure_str).split()[0])
        return round(value * 33.8639, 1)
    except:
        return None

def inches_to_mm(precip_str):
    try:
        value = float(str(precip_str).split()[0])
        return round(value * 25.4, 1)
    except:
        return None

def limpiar_humedad(humidity_str):
    try:
        return float(str(humidity_str).replace('%', '').replace('°', '').strip())
    except:
        return None

def limpiar_solar(solar_str):
    try:
        match = re.search(r"\d+(\.\d+)?", str(solar_str))
        return float(match.group()) if match else None
    except:
        return None

# === INICIAR NAVEGADOR (modo headless para servidor Linux / Windows) ===

chrome_options = Options()
chrome_options.add_argument("--headless=new")  # modo headless moderno
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# GitHub Actions puede proveer CHROME_PATH
chrome_path = os.environ.get("CHROME_PATH")
if chrome_path:
    chrome_options.binary_location = chrome_path

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

print(f"🌐 Abriendo: {url}")
driver.get(url)

try:
    wait = WebDriverWait(driver, 60)
    table_elem = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table.history-table.desktop-table"))
    )
    print("✅ Tabla cargada.")

    html = table_elem.get_attribute("outerHTML")
    df = pd.read_html(StringIO(html))[0]
    df.columns = [col.strip() for col in df.columns]

    print("🧾 Columnas detectadas:")
    for i, col in enumerate(df.columns):
        print(f"{i}: '{col}'")

    df['Fecha'] = ayer

    # === CONVERSIONES SEGÚN COLUMNAS DETECTADAS ===

    if 'Temperature' in df.columns:
        df['Temperature'] = df['Temperature'].apply(fahrenheit_to_celsius)
    if 'Dew Point' in df.columns:
        df['Dew Point'] = df['Dew Point'].apply(fahrenheit_to_celsius)
    if 'Speed' in df.columns:
        df['Speed'] = df['Speed'].apply(mph_to_kmh)
    if 'Gust' in df.columns:
        df['Gust'] = df['Gust'].apply(mph_to_kmh)
    if 'Pressure' in df.columns:
        df['Pressure'] = df['Pressure'].apply(inHg_to_hPa)
    if 'Precip. Rate.' in df.columns:
        df['Precip. Rate.'] = df['Precip. Rate.'].apply(inches_to_mm)
    if 'Precip. Accum.' in df.columns:
        df['Precip. Accum.'] = df['Precip. Accum.'].apply(inches_to_mm)
    if 'Humidity' in df.columns:
        df['Humidity'] = df['Humidity'].apply(limpiar_humedad)
    if 'Solar' in df.columns:
        df['Solar'] = df['Solar'].apply(limpiar_solar)

    # Renombrar columnas con unidad
    df.rename(columns={
        'Temperature': 'Temperature (°C)',
        'Dew Point': 'Dew Point (°C)',
        'Humidity': 'Humidity (%)',
        'Speed': 'Speed (km/h)',
        'Gust': 'Gust (km/h)',
        'Pressure': 'Pressure (hPa)',
        'Precip. Rate.': 'Precip. Rate. (mm/hr)',
        'Precip. Accum.': 'Precip. Accum. (mm)',
        'Solar': 'Solar Radiation (W/m²)'
    }, inplace=True)

    # Reordenar columnas: Fecha y Time al inicio
    if 'Time' in df.columns:
        cols = df.columns.tolist()
        for col in ['Fecha', 'Time']:
            if col in cols:
                cols.insert(0, cols.pop(cols.index(col)))
        df = df[cols]

    # === UNIFICAR CON ARCHIVO EXISTENTE ===
    if os.path.exists(archivo):
        try:
            df_existente = pd.read_excel(archivo, sheet_name=hoja_excel)
            df = pd.concat([df_existente, df], ignore_index=True)
        except Exception as e:
            print("⚠️ No se pudo leer archivo existente:", e)

    # Eliminar duplicados por Fecha y Time
    if 'Time' in df.columns:
        df.drop_duplicates(subset=['Fecha', 'Time'], keep='last', inplace=True)
    else:
        df.drop_duplicates(subset=['Fecha'], keep='last', inplace=True)

    # === ORDENAR POR FECHA Y HORA ===
    if 'Time' in df.columns:
        try:
            df['Orden'] = pd.to_datetime(
                df['Fecha'] + ' ' + df['Time'].astype(str),
                errors='coerce'
            )
            df = df.sort_values('Orden')
            df.drop(columns=['Orden'], inplace=True)
        except Exception as e:
            print("⚠️ Error al ordenar:", e)

    # === LIMPIEZA FINAL ===
    # eliminar filas donde falten Time o Temperature
    columnas_clave = ['Time', 'Temperature (°C)']
    df.dropna(subset=columnas_clave, how='any', inplace=True)

    # limpiar espacios de Time
    df['Time'] = df['Time'].astype(str).str.strip()

    # eliminar filas con Time vacío
    df = df[df['Time'] != '']

    # === GUARDAR A EXCEL ===
    with pd.ExcelWriter(archivo, engine='openpyxl', mode='w') as writer:
        df.to_excel(writer, sheet_name=hoja_excel, index=False)

    print(f"📁 Archivo actualizado correctamente: {archivo}")

except Exception as e:
    print("❌ Error general:", e)

finally:
    driver.quit()
    print("🚪 Navegador cerrado.")
