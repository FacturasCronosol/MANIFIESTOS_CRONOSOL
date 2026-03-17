import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import sqlite3
import hashlib

st.set_page_config(page_title="Escudo DIAN", layout="wide", page_icon="🛡️")

# Conexión persistente a la base de datos
conn = sqlite3.connect('gestion_dian.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS documentos 
             (id TEXT PRIMARY KEY, tipo TEXT, numero TEXT, fecha TEXT, contenido TEXT, nombre_archivo TEXT)''')
conn.commit()

st.title("🛡️ Sistema de Trazabilidad - Escudo DIAN")

menu = ["🔍 Buscador Rápido", "📤 Cargar Factura", "📥 Cargar Manifiesto"]
choice = st.sidebar.selectbox("Menú", menu)

if "Cargar" in choice:
    tipo = "Factura de Compra" if "Factura" in choice else "Manifiesto de Aduana"
    st.subheader(f"Registro de {tipo}")
    
    with st.container(border=True):
        numero = st.text_input(f"Número de {tipo}")
        fecha = st.date_input("Fecha del documento")
        archivo = st.file_uploader("Seleccionar PDF", type="pdf")

        if st.button("Guardar Documento"):
            if archivo and numero:
                with st.spinner("Procesando OCR..."):
                    texto = ""
                    with fitz.open(stream=archivo.read(), filetype="pdf") as doc:
                        for pagina in doc:
                            texto += pagina.get_text()
                    
                    doc_id = hashlib.sha256(archivo.getvalue()).hexdigest()
                    try:
                        c.execute("INSERT INTO documentos VALUES (?,?,?,?,?,?)", 
                                  (doc_id, tipo, numero, str(fecha), texto.upper(), archivo.name))
                        conn.commit()
                        st.success(f"✅ {tipo} guardado con éxito.")
                    except:
                        st.error("⚠️ Este documento ya fue cargado anteriormente.")
            else:
                st.warning("Por favor rellena el número y sube el archivo.")

elif choice == "🔍 Buscador Rápido":
    st.subheader("Buscador de Emergencia")
    query = st.text_input("Escribe la referencia (ej: NF7125)").upper()

    if query:
        df = pd.read_sql_query(f"SELECT tipo, numero, fecha, nombre_archivo FROM documentos WHERE contenido LIKE '%{query}%' ORDER BY fecha DESC", conn)
        if not df.empty:
            st.write(f"Resultados para: **{query}**")
            st.dataframe(df, use_container_width=True)
            st.info("💡 Consejo: Ten listos los archivos físicos si el funcionario los solicita.")
        else:
            st.error("❌ No se encontró la referencia en la base de datos.")