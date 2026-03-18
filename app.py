# ... (mantenemos las importaciones y funciones de base de datos)

# Nueva función para actualizar datos
def actualizar_documento(doc_id, nuevo_tipo, nuevo_nombre, nueva_fecha):
    c.execute("""UPDATE documentos 
                 SET tipo=?, nombre_archivo=?, fecha_iso=? 
                 WHERE id=?""", (nuevo_tipo, nuevo_nombre, nueva_fecha, doc_id))
    conn.commit()

# Nueva función para eliminar un solo registro
def eliminar_documento(doc_id):
    c.execute("DELETE FROM documentos WHERE id=?", (doc_id,))
    conn.commit()

# --- DENTRO DEL BUSCADOR ---
# (Modificamos la visualización de cada resultado)
if res:
    for r in res:
        doc_id, tipo, num, fecha_iso, nombre, pags, blob = r
        # ... (lógica de emoji y fecha) ...

        with st.expander(f"{emoji} {fecha_vis} | {tipo} - {nombre}"):
            # Creamos pestañas para no amontonar todo
            tab1, tab2 = st.tabs(["Ver / Descargar", "⚙️ Gestionar"])
            
            with tab1:
                # Aquí va lo que ya teníamos: botón de ver PDF y descargar
                col_i, col_b = st.columns([2, 1])
                # ... (lógica de resaltar y mostrar botones) ...

            with tab2:
                st.markdown("### Editar información")
                edit_nombre = st.text_input("Nombre del archivo", value=nombre, key=f"n_{doc_id}")
                col_e1, col_e2 = st.columns(2)
                edit_tipo = col_e1.selectbox("Tipo", ["Factura de Compra", "Manifiesto de Aduana"], 
                                           index=0 if tipo=="Factura de Compra" else 1, key=f"t_{doc_id}")
                edit_fecha = col_e2.text_input("Fecha (AAAA-MM-DD)", value=fecha_iso, key=f"f_edit_{doc_id}")
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("💾 Guardar Cambios", key=f"save_{doc_id}"):
                    actualizar_documento(doc_id, edit_tipo, edit_nombre, edit_fecha)
                    st.success("¡Actualizado!")
                    st.rerun()
                
                if col_btn2.button("🗑️ Eliminar Documento", key=f"del_{doc_id}"):
                    eliminar_documento(doc_id)
                    st.warning("Documento eliminado.")
                    st.rerun()
