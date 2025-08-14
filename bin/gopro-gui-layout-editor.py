import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import xml.etree.ElementTree as ET
import os
from PIL import Image, ImageTk
import traceback

def seleccionar_xml():
    root = tk.Tk()
    root.withdraw()
    # Carpeta por defecto: layouts XML
    default_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gopro_overlay", "layouts"))
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo de layout XML",
        filetypes=[("Archivos XML", "*.xml")],
        initialdir=default_dir
    )
    root.destroy()
    return file_path

class LayoutEditor:
    def __init__(self, master, xml_path):
        print(f"[INFO] Iniciando editor con archivo: {xml_path}")
        self.master = master
        self.master.title("Editor de Layout XML Simplificado")
        self.xml_path = xml_path
        self.tree = ET.parse(xml_path)
        self.root = self.tree.getroot()
        
        # Tamaño del canvas (4K por defecto)
        self.width = 3840
        self.height = 2160
        self.zoom = 0.5  # Factor de zoom inicial
        
        # Maximizar ventana
        self.master.update_idletasks()
        try:
            self.master.state('zoomed')  # Windows
        except:
            self.master.attributes('-zoomed', True)  # Linux/Mac
            
        # Frame principal
        self.main_frame = tk.Frame(master)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas con scrollbars
        self.canvas_frame = tk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Canvas para mostrar el layout
        self.canvas = tk.Canvas(self.canvas_frame, bg="gray20")
        self.v_scrollbar = tk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.h_scrollbar = tk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        # Configurar scrollbars
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.configure(xscrollcommand=self.h_scrollbar.set, yscrollcommand=self.v_scrollbar.set)
        
        # Panel lateral para edición
        self.side_panel = tk.Frame(self.main_frame, width=250, bg="#222")
        self.side_panel.pack(side=tk.RIGHT, fill=tk.Y)
        self.side_panel.pack_propagate(False)
        
        # Botón de guardar
        self.save_btn = tk.Button(self.side_panel, text="Guardar XML", command=self.save_xml, 
                                  bg="#2a52be", fg="white", padx=10, pady=5)
        self.save_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        
        # Información del elemento seleccionado
        self.selection_label = tk.Label(self.side_panel, text="Ningún elemento seleccionado", 
                                       fg="white", bg="#222", wraplength=240)
        self.selection_label.pack(pady=10)
        
        # Variables de estado
        self.items = []  # Lista de componentes para selección
        self.selected = None  # Componente seleccionado actualmente
        self.selected_translate = None  # Translate padre seleccionado
        self.rendered_image = None  # Imagen renderizada
        self.tk_image = None  # Referencia para evitar garbage collection
        self._dragging = False
        self._temp_rects = []  # Rectángulos temporales durante arrastre
        
        # Eventos del mouse
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<MouseWheel>', self.on_mousewheel)  # Windows
        
        # Realizar renderizado inicial
        self.master.after(100, self.render_layout)
    
    def render_layout(self):
        """Renderiza el layout completo una sola vez al inicio"""
        print("[INFO] Renderizando layout completo...")
        try:
            from gopro_overlay.layout_xml import layout_from_xml
            from gopro_overlay.layout import Overlay
            from gopro_overlay.config import Config
            from gopro_overlay.geo import MapRenderer, MapStyler, api_key_finder
            from gopro_overlay.font import load_font
            from gopro_overlay import fake
            from gopro_overlay.privacy import NoPrivacyZone
            from gopro_overlay.widgets.widgets import SimpleFrameSupplier
            from gopro_overlay.dimensions import Dimension
            from datetime import timedelta
            import pathlib
            import random
            
            # Crear datos falsos para el renderizado
            font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Coolvetica.otf"))
            print(f"[INFO] Usando fuente: {font_path}")
            font = load_font(font_path).font_variant(size=16)
            
            rng = random.Random(12345)
            timeseries = fake.fake_framemeta(timedelta(minutes=5), step=timedelta(seconds=1), rng=rng, point_step=0.0001)
            
            # Configurar MapRenderer
            config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            config_loader = Config(config_dir)
            key_finder = api_key_finder(config_loader, None)
            cache_dir_path = pathlib.Path(config_dir)
            
            # Renderizar el layout
            with MapRenderer(cache_dir=cache_dir_path, styler=MapStyler(api_key_finder=key_finder)).open("osm") as renderer:
                print("[INFO] Renderizando layout con componentes...")
                
                # Convertir el árbol XML actual a string para usar los cambios en memoria
                xml_str = ET.tostring(self.root, encoding="unicode")
                
                # También guardar a un archivo temporal para debug
                temp_xml = os.path.join(os.path.dirname(self.xml_path), "_temp_layout.xml")
                with open(temp_xml, "w", encoding="utf-8") as f:
                    f.write(xml_str)
                print(f"[DEBUG] XML temporal guardado en {temp_xml}")
                
                # Renderizar desde el string XML, no desde el archivo
                layout = layout_from_xml(xml_str, renderer, timeseries, font, NoPrivacyZone())
                overlay = Overlay(framemeta=timeseries, create_widgets=layout)
                supplier = SimpleFrameSupplier(Dimension(self.width, self.height))
                frame = overlay.draw(timeseries.mid, supplier.drawing_frame())
                
                # Convertir y guardar la imagen
                self.rendered_image = frame.convert("RGBA")
                
                # Redimensionar para mostrar en el canvas con zoom
                final_width = int(self.width * self.zoom)
                final_height = int(self.height * self.zoom)
                display_img = self.rendered_image.resize((final_width, final_height), Image.Resampling.LANCZOS)
                
                # Mostrar en canvas
                self.tk_image = ImageTk.PhotoImage(display_img)
                self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image, tags="layout_image")
                self.canvas.config(scrollregion=(0, 0, final_width, final_height))
                
                print("[INFO] Renderizado completo, analizando componentes...")
                self.parse_components()
                
        except Exception as e:
            print(f"[ERROR] Error al renderizar layout: {e}")
            traceback.print_exc()
    
    def parse_components(self):
        """Analiza el XML para identificar todos los componentes seleccionables"""
        self.items.clear()
        
        def walk(node, offset_x=0, offset_y=0, parent_translate=None):
            this_x = offset_x
            this_y = offset_y
            this_translate = parent_translate
            
            if node.tag == "translate":
                this_x += int(node.attrib.get("x", 0))
                this_y += int(node.attrib.get("y", 0))
                this_translate = node
            
            for child in node:
                if child.tag == "component":
                    # Para componentes, calcular posición absoluta
                    comp_x = int(child.attrib.get("x", 0))
                    comp_y = int(child.attrib.get("y", 0))
                    x = this_x + comp_x
                    y = this_y + comp_y
                    
                    # Determinar dimensiones según tipo
                    ctype = child.attrib.get("type", "")
                    width = int(child.attrib.get("width", 180))
                    height = int(child.attrib.get("height", 60))
                    
                    if ctype == "icon":
                        size = int(child.attrib.get("size", 55))
                        width = height = size
                    elif ctype == "text":
                        # Para textos, usamos el tamaño de la fuente para estimar dimensiones
                        font_size = int(child.attrib.get("size", 14))
                        # La altura aproximada debería ser proporcional al tamaño de fuente
                        height = int(font_size * 1.2)  # Factor aproximado para altura del texto
                        
                        # El ancho se calcula basado en el contenido del texto
                        texto = child.text or ""
                        # Estimamos aproximadamente 0.7 veces el tamaño de fuente por carácter
                        width = max(len(texto) * int(font_size * 0.7), 60)
                    
                    # Crear diccionario para el componente
                    item = {
                        "element": child,
                        "translate": this_translate,
                        "abs_x": x,
                        "abs_y": y,
                        "comp_x": comp_x,
                        "comp_y": comp_y,
                        "width": width,
                        "height": height,
                        "kind": "icon" if ctype == "icon" else "rect",
                        "type": ctype
                    }
                    
                    # Dibujar un rectángulo de selección
                    zx = x * self.zoom
                    zy = y * self.zoom
                    zw = width * self.zoom
                    zh = height * self.zoom
                    
                    # Crear rectángulo interactivo (invisible)
                    rect_id = self.canvas.create_rectangle(
                        zx, zy, zx+zw, zy+zh,
                        outline="", fill="", tags=f"comp_{len(self.items)}"
                    )
                    
                    item["rect_id"] = rect_id
                    self.items.append(item)
                    
                    # Verificar si tiene atributos x,y cuando no debería
                    # Solo los iconos pueden tener x,y directamente
                    if ctype != "icon" and ("x" in child.attrib or "y" in child.attrib):
                        print(f"[ADVERTENCIA] Componente tipo '{ctype}' tiene atributos x/y que deberían estar en el translate padre")
                    
                    # Información especial para textos
                    if ctype == "text":
                        texto = child.text or ""
                        print(f"[INFO] Componente de texto: '{texto}' en ({x}, {y}), tamaño de fuente {child.attrib.get('size', '14')}, dimensiones aprox. {width}x{height}")
                    else:
                        print(f"[INFO] Componente registrado: {ctype} en ({x}, {y}), tamaño {width}x{height}")
                
                else:
                    # Recursivamente procesar los hijos
                    walk(child, this_x, this_y, this_translate)
        
        walk(self.root)
        print(f"[INFO] Total de componentes registrados: {len(self.items)}")
        
        # Después de registrar todos los componentes, verificar la estructura
        self.check_layout_structure()
    
    def check_layout_structure(self):
        """Verifica y reporta problemas estructurales en el layout"""
        problemas = []
        
        # Comprobar componentes sin translate padre
        for i, item in enumerate(self.items):
            if item["type"] != "icon" and item["translate"] is None:
                problemas.append(f"Componente {i} ({item['type']}) no tiene translate padre")
            
            # Verificar atributos incorrectos
            element = item["element"]
            if item["type"] != "icon" and ("x" in element.attrib or "y" in element.attrib):
                problemas.append(f"Componente {i} ({item['type']}) tiene atributos x/y directos que deberían estar en translate")
        
        # Mostrar problemas encontrados
        if problemas:
            print("[ADVERTENCIA] Se encontraron problemas en la estructura del layout:")
            for problema in problemas:
                print(f" - {problema}")
            print("Estos problemas pueden afectar el comportamiento del editor. Considere corregir el XML.")
            
            # Mostrar botón para corregir problemas
            if not hasattr(self, 'fix_btn') or not self.fix_btn:
                self.fix_btn = tk.Button(
                    self.side_panel,
                    text="Corregir Problemas de Estructura",
                    bg="#CC4444",
                    fg="white",
                    command=self.fix_layout_structure
                )
                self.fix_btn.pack(fill=tk.X, padx=10, pady=5)
        else:
            print("[INFO] Estructura del layout correcta")
            # Eliminar botón de corrección si existe
            if hasattr(self, 'fix_btn') and self.fix_btn:
                self.fix_btn.destroy()
                self.fix_btn = None
        
        return len(problemas) == 0
        
    def fix_layout_structure(self):
        """Corrige automáticamente problemas comunes en la estructura del layout"""
        corregidos = 0
        
        # Recorrer todos los componentes
        for i, item in enumerate(self.items):
            element = item["element"]
            
            # Corregir atributos x,y incorrectos en componentes que no son iconos
            if item["type"] != "icon" and ("x" in element.attrib or "y" in element.attrib):
                # Obtener valores de x,y
                comp_x = int(element.attrib.get("x", 0))
                comp_y = int(element.attrib.get("y", 0))
                
                # Si no hay translate padre, crear uno
                if item["translate"] is None:
                    # Crear un nuevo elemento translate
                    translate = ET.Element("translate")
                    translate.set("x", str(comp_x))
                    translate.set("y", str(comp_y))
                    
                    # Mover el componente dentro del translate
                    parent = self.find_parent(element)
                    if parent is not None:
                        idx = list(parent).index(element)
                        parent.remove(element)
                        translate.append(element)
                        parent.insert(idx, translate)
                        
                        # Eliminar atributos x,y del componente
                        if "x" in element.attrib:
                            del element.attrib["x"]
                        if "y" in element.attrib:
                            del element.attrib["y"]
                        
                        corregidos += 1
                        print(f"[INFO] Creado translate para componente {i} ({item['type']})")
                else:
                    # Actualizar translate existente
                    translate = item["translate"]
                    trans_x = int(translate.attrib.get("x", 0))
                    trans_y = int(translate.attrib.get("y", 0))
                    
                    # Ajustar las coordenadas del translate
                    translate.set("x", str(trans_x + comp_x))
                    translate.set("y", str(trans_y + comp_y))
                    
                    # Eliminar atributos x,y del componente
                    if "x" in element.attrib:
                        del element.attrib["x"]
                    if "y" in element.attrib:
                        del element.attrib["y"]
                    
                    corregidos += 1
                    print(f"[INFO] Corregido componente {i} ({item['type']})")
        
        # Volver a renderizar y analizar el layout
        if corregidos > 0:
            self.render_layout()
            self.parse_components()
            print(f"[INFO] Se corrigieron {corregidos} problemas en la estructura del layout")
            
            # Mostrar mensaje
            messagebox.showinfo("Corrección Completada", f"Se corrigieron {corregidos} problemas en la estructura del layout")
        else:
            print("[INFO] No se encontraron problemas para corregir")
            messagebox.showinfo("Corrección Completada", "No se encontraron problemas para corregir")
    
    def find_parent(self, element):
        """Encuentra el elemento padre de un elemento dado en el árbol XML"""
        def _find_parent(node, target, parent=None):
            if node == target:
                return parent
            for child in node:
                result = _find_parent(child, target, node)
                if result is not None:
                    return result
            return None
        
        return _find_parent(self.root, element)
    
    def update_component_visuals(self):
        """Actualiza los rectángulos visuales de los componentes"""
        # Quitar rectángulos de selección anteriores
        self.canvas.delete("selection")
        
        # Dibujar un rectángulo para el componente seleccionado
        if self.selected:
            elem = self.selected["element"]
            x = self.selected.get("_temp_x", self.selected["abs_x"])
            y = self.selected.get("_temp_y", self.selected["abs_y"])
            
            # Calcular dimensiones
            if self.selected["kind"] == "icon":
                w = h = int(elem.attrib.get("size", 55))
            else:
                w = int(elem.attrib.get("width", 180))
                h = int(elem.attrib.get("height", 60))
                
                # Ajuste especial para texto
                if self.selected["type"] == "text":
                    # Para textos, usamos el tamaño de la fuente para estimar una altura más precisa
                    font_size = int(elem.attrib.get("size", 14))
                    # La altura aproximada debería ser proporcional al tamaño de fuente
                    h = int(font_size * 1.2)  # Factor aproximado para altura del texto
                    
                    # El ancho se calcula basado en el contenido del texto
                    texto = elem.text or ""
                    # Estimamos aproximadamente 0.7 veces el tamaño de fuente por carácter
                    w = max(len(texto) * int(font_size * 0.7), 60)
            
            # Dibujar rectángulo de selección con zoom aplicado
            zx = x * self.zoom
            zy = y * self.zoom
            zw = w * self.zoom
            zh = h * self.zoom
            
            self.canvas.create_rectangle(
                zx, zy, zx+zw, zy+zh,
                outline="red", width=2, dash=(6, 4), tags="selection"
            )
            
            # Actualizar información en panel lateral
            ctype = self.selected["element"].attrib.get("type", "")
            self.selection_label.config(
                text=f"Tipo: {ctype}\nPosición: ({x:.0f}, {y:.0f})\nTamaño: {w}x{h}"
            )
            
            # Actualizar panel de propiedades
            self.update_properties_panel()
    
    def update_properties_panel(self):
        """Actualiza el panel de propiedades según el elemento seleccionado"""
        # Limpiar panel excepto elementos fijos
        for widget in self.side_panel.pack_slaves():
            if widget not in [self.selection_label, self.save_btn]:
                widget.destroy()
        
        if not self.selected:
            return
        
        elem = self.selected["element"]
        ctype = elem.attrib.get("type", "")
        
        # Frame para propiedades
        props_frame = tk.Frame(self.side_panel, bg="#222")
        props_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Coordenadas X, Y solo para iconos o para el translate seleccionado
        if ctype == "icon" or (hasattr(self, 'selected_translate') and self.selected_translate is not None):
            pos_frame = tk.Frame(props_frame, bg="#222")
            pos_frame.pack(fill=tk.X, pady=5)
            
            # Si es un icono, editamos sus atributos x, y
            if ctype == "icon":
                tk.Label(pos_frame, text="X:", fg="white", bg="#222").pack(side=tk.LEFT)
                x_var = tk.IntVar(value=int(elem.attrib.get("x", 0)))
                x_spin = tk.Spinbox(
                    pos_frame, from_=-5000, to=5000, textvariable=x_var, width=6,
                    command=lambda: self.update_attribute("x", x_var.get())
                )
                x_spin.pack(side=tk.LEFT, padx=5)
                
                tk.Label(pos_frame, text="Y:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
                y_var = tk.IntVar(value=int(elem.attrib.get("y", 0)))
                y_spin = tk.Spinbox(
                    pos_frame, from_=-5000, to=5000, textvariable=y_var, width=6,
                    command=lambda: self.update_attribute("y", y_var.get())
                )
                y_spin.pack(side=tk.LEFT, padx=5)
            # Si hay un translate seleccionado, editamos las coordenadas del translate
            elif self.selected_translate is not None:
                tk.Label(pos_frame, text="Translate X:", fg="white", bg="#222").pack(side=tk.LEFT)
                tx_var = tk.IntVar(value=int(self.selected_translate.attrib.get("x", 0)))
                def update_translate_x():
                    self.selected_translate.set("x", str(tx_var.get()))
                    self.update_component_visuals()
                tx_spin = tk.Spinbox(
                    pos_frame, from_=-5000, to=5000, textvariable=tx_var, width=6,
                    command=update_translate_x
                )
                tx_spin.pack(side=tk.LEFT, padx=5)
                
                tk.Label(pos_frame, text="Y:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
                ty_var = tk.IntVar(value=int(self.selected_translate.attrib.get("y", 0)))
                def update_translate_y():
                    self.selected_translate.set("y", str(ty_var.get()))
                    self.update_component_visuals()
                ty_spin = tk.Spinbox(
                    pos_frame, from_=-5000, to=5000, textvariable=ty_var, width=6,
                    command=update_translate_y
                )
                ty_spin.pack(side=tk.LEFT, padx=5)
        
        # Propiedades específicas según tipo
        if ctype == "text":
            # Texto
            text_frame = tk.Frame(props_frame, bg="#222")
            text_frame.pack(fill=tk.X, pady=5)
            tk.Label(text_frame, text="Texto:", fg="white", bg="#222").pack(anchor=tk.W)
            text_var = tk.StringVar(value=elem.text or "")
            text_entry = tk.Entry(text_frame, textvariable=text_var)
            text_entry.pack(fill=tk.X, pady=2)
            text_var.trace_add("write", lambda *args: self.update_text(text_var.get()))
            
            # Tamaño
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño:", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 14)))
            size_spin = tk.Spinbox(
                size_frame, from_=5, to=200, textvariable=size_var, width=6,
                command=lambda: self.update_attribute("size", size_var.get())
            )
            size_spin.pack(side=tk.LEFT, padx=5)
            
            # Alineación
            align_frame = tk.Frame(props_frame, bg="#222")
            align_frame.pack(fill=tk.X, pady=5)
            tk.Label(align_frame, text="Alineación:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Crear variable para alineación
            align_var = tk.StringVar(value=elem.attrib.get("align", "left"))
            
            # Opciones de alineación
            align_options = ["left", "center", "right"]
            align_dropdown = tk.OptionMenu(align_frame, align_var, *align_options, 
                                         command=lambda val: self.update_attribute("align", val))
            align_dropdown.config(bg="#444", fg="white", width=10)
            align_dropdown["menu"].config(bg="#444", fg="white")
            align_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Color
            color_frame = tk.Frame(props_frame, bg="#222")
            color_frame.pack(fill=tk.X, pady=5)
            tk.Label(color_frame, text="Color RGB:", fg="white", bg="#222").pack(anchor=tk.W)
            
            # Frame para entrada y vista previa del color
            rgb_input_frame = tk.Frame(color_frame, bg="#222")
            rgb_input_frame.pack(fill=tk.X, pady=2)
            
            # Entrada de texto para el color
            rgb_var = tk.StringVar(value=elem.attrib.get("rgb", "255,255,255"))
            rgb_entry = tk.Entry(rgb_input_frame, textvariable=rgb_var, width=15)
            rgb_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            rgb_var.trace_add("write", lambda *args: self.update_attribute("rgb", rgb_var.get()))
            
            # Crear muestra de color
            color_preview = tk.Frame(rgb_input_frame, width=30, height=20, bg=self.rgb_to_hex(rgb_var.get()))
            color_preview.pack(side=tk.LEFT, padx=5)
            
            # Botón para selector de color
            color_button = tk.Button(rgb_input_frame, text="Elegir color", 
                                     command=lambda: self.open_color_picker(rgb_var, color_preview),
                                     bg="#336699", fg="white")
            color_button.pack(side=tk.LEFT, padx=5)
            
            # Contorno (outline)
            if "outline" in elem.attrib:
                outline_frame = tk.Frame(props_frame, bg="#222")
                outline_frame.pack(fill=tk.X, pady=5)
                tk.Label(outline_frame, text="Contorno:", fg="white", bg="#222").pack(anchor=tk.W)
                
                # Frame para entrada y vista previa del contorno
                outline_input_frame = tk.Frame(outline_frame, bg="#222")
                outline_input_frame.pack(fill=tk.X, pady=2)
                
                # Entrada de texto para el contorno
                outline_var = tk.StringVar(value=elem.attrib.get("outline", "0,0,0,100"))
                outline_entry = tk.Entry(outline_input_frame, textvariable=outline_var, width=15)
                outline_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
                outline_var.trace_add("write", lambda *args: self.update_attribute("outline", outline_var.get()))
                
                # Obtener color del contorno (excluyendo el valor alpha)
                outline_parts = outline_var.get().split(',')
                outline_color = ','.join(outline_parts[:3]) if len(outline_parts) >= 3 else "0,0,0"
                
                # Crear muestra de color para el contorno
                outline_preview = tk.Frame(outline_input_frame, width=30, height=20, bg=self.rgb_to_hex(outline_color))
                outline_preview.pack(side=tk.LEFT, padx=5)
                
                # Botón para selector de color del contorno
                outline_button = tk.Button(outline_input_frame, text="Elegir contorno", 
                                         command=lambda: self.open_outline_picker(outline_var, outline_preview),
                                         bg="#336699", fg="white")
                outline_button.pack(side=tk.LEFT, padx=5)
            
        elif ctype == "icon":
            # Tamaño de icono
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño:", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 55)))
            size_spin = tk.Spinbox(
                size_frame, from_=10, to=500, textvariable=size_var, width=6,
                command=lambda: self.update_attribute("size", size_var.get())
            )
            size_spin.pack(side=tk.LEFT, padx=5)
            
            # Archivo de icono
            file_frame = tk.Frame(props_frame, bg="#222")
            file_frame.pack(fill=tk.X, pady=5)
            tk.Label(file_frame, text="Archivo:", fg="white", bg="#222").pack(anchor=tk.W)
            
            # Lista de archivos de iconos disponibles
            icons_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "gopro_overlay", "icons"))
            icon_files = [f for f in os.listdir(icons_dir) if f.lower().endswith(".png")]
            
            file_var = tk.StringVar(value=elem.attrib.get("file", ""))
            file_menu = tk.OptionMenu(file_frame, file_var, *sorted(icon_files), 
                                      command=lambda value: self.update_attribute("file", value))
            file_menu.pack(fill=tk.X, pady=2)
        
        elif ctype in ["bar", "zone-bar"]:
            # Tamaño de barra
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(size_frame, text="Ancho:", fg="white", bg="#222").pack(side=tk.LEFT)
            width_var = tk.IntVar(value=int(elem.attrib.get("width", 180)))
            width_spin = tk.Spinbox(
                size_frame, from_=10, to=3000, textvariable=width_var, width=6,
                command=lambda: self.update_attribute("width", width_var.get())
            )
            width_spin.pack(side=tk.LEFT, padx=5)
            
            tk.Label(size_frame, text="Alto:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
            height_var = tk.IntVar(value=int(elem.attrib.get("height", 60)))
            height_spin = tk.Spinbox(
                size_frame, from_=10, to=1000, textvariable=height_var, width=6,
                command=lambda: self.update_attribute("height", height_var.get())
            )
            height_spin.pack(side=tk.LEFT, padx=5)
            
            # Métrica
            metric_frame = tk.Frame(props_frame, bg="#222")
            metric_frame.pack(fill=tk.X, pady=5)
            tk.Label(metric_frame, text="Métrica:", fg="white", bg="#222").pack(side=tk.LEFT)
            metric_var = tk.StringVar(value=elem.attrib.get("metric", ""))
            metric_entry = tk.Entry(metric_frame, textvariable=metric_var, width=10)
            metric_entry.pack(side=tk.LEFT, padx=5)
            metric_var.trace_add("write", lambda *args: self.update_attribute("metric", metric_var.get()))
            
            # Min/Max
            range_frame = tk.Frame(props_frame, bg="#222")
            range_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(range_frame, text="Min:", fg="white", bg="#222").pack(side=tk.LEFT)
            min_var = tk.StringVar(value=elem.attrib.get("min", "0"))
            min_entry = tk.Entry(range_frame, textvariable=min_var, width=6)
            min_entry.pack(side=tk.LEFT, padx=5)
            min_var.trace_add("write", lambda *args: self.update_attribute("min", min_var.get()))
            
            tk.Label(range_frame, text="Max:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
            max_var = tk.StringVar(value=elem.attrib.get("max", "100"))
            max_entry = tk.Entry(range_frame, textvariable=max_var, width=6)
            max_entry.pack(side=tk.LEFT, padx=5)
            max_var.trace_add("write", lambda *args: self.update_attribute("max", max_var.get()))
        
        # Botón para ver/editar todos los atributos
        all_attrs_btn = tk.Button(
            props_frame, text="Ver todos los atributos", 
            command=self.show_all_attributes, bg="#333", fg="white"
        )
        all_attrs_btn.pack(fill=tk.X, pady=10)
        
        # Botón para renderizar de nuevo
        rerender_btn = tk.Button(
            self.side_panel, text="Renderizar cambios", 
            command=self.rerender_layout, bg="#336699", fg="white"
        )
        rerender_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
    
    def rerender_layout(self):
        """Renderiza el layout y mantiene la selección actual"""
        # Guardar la referencia al elemento seleccionado
        selected_element = None
        if self.selected:
            selected_element = self.selected["element"]
        
        # Renderizar y analizar componentes
        self.render_layout()
        self.parse_components()
        
        # Restaurar selección si había un elemento seleccionado
        if selected_element:
            for i, item in enumerate(self.items):
                if item["element"] == selected_element:
                    self.selected = item
                    self.canvas.itemconfig(item["rect_id"], 
                                          outline=self.selection_color, 
                                          width=2)
                    self.update_properties_panel()
                    break
        
        print("[INFO] Layout re-renderizado con éxito")
    
    def show_all_attributes(self):
        """Muestra una ventana con todos los atributos para edición"""
        if not self.selected:
            return
            
        elem = self.selected["element"]
        
        # Crear ventana modal
        attr_window = tk.Toplevel(self.master)
        attr_window.title("Editar atributos")
        attr_window.geometry("400x500")
        attr_window.transient(self.master)
        attr_window.grab_set()
        
        # Frame principal
        main_frame = tk.Frame(attr_window, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollable frame para atributos
        canvas = tk.Canvas(main_frame)
        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Título
        tk.Label(scrollable_frame, text=f"Atributos del elemento {elem.tag} tipo {elem.attrib.get('type', '')}", 
                font=("Arial", 12, "bold")).pack(pady=(0, 10))
        
        # Añadir todos los atributos con entradas de texto
        attr_vars = {}
        for attr, value in elem.attrib.items():
            frame = tk.Frame(scrollable_frame)
            frame.pack(fill="x", pady=2)
            
            tk.Label(frame, text=f"{attr}:", width=15, anchor="w").pack(side="left")
            
            var = tk.StringVar(value=value)
            attr_vars[attr] = var
            
            entry = tk.Entry(frame, textvariable=var)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Contenido de texto (si es un elemento de texto)
        if elem.text:
            frame = tk.Frame(scrollable_frame)
            frame.pack(fill="x", pady=2)
            
            tk.Label(frame, text="Contenido:", width=15, anchor="w").pack(side="left")
            
            text_var = tk.StringVar(value=elem.text)
            attr_vars["_text"] = text_var
            
            entry = tk.Entry(frame, textvariable=text_var)
            entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # Botones
        button_frame = tk.Frame(attr_window)
        button_frame.pack(fill="x", pady=10)
        
        def apply_changes():
            # Aplicar todos los cambios
            for attr, var in attr_vars.items():
                if attr == "_text":
                    elem.text = var.get()
                else:
                    elem.set(attr, var.get())
            
            # Actualizar visualización
            self.update_component_visuals()
            attr_window.destroy()
        
        tk.Button(button_frame, text="Aplicar", command=apply_changes).pack(side="right", padx=5)
        tk.Button(button_frame, text="Cancelar", command=attr_window.destroy).pack(side="right", padx=5)
    
    def update_attribute(self, attr, value, render=False):
        """Actualiza un atributo del elemento seleccionado"""
        if not self.selected:
            return
        
        # Convertir a string si no lo es
        if not isinstance(value, str):
            value = str(value)
        
        # Actualizar el atributo en el XML
        self.selected["element"].set(attr, value)
        
        if render:
            # Re-renderizar el layout completo
            self.render_layout()
            self.parse_components()
            # Restaurar selección
            if self.selected:
                for i, item in enumerate(self.items):
                    if item["element"] == self.selected["element"]:
                        self.selected = item
                        self.canvas.itemconfig(item["rect_id"], 
                                              outline=self.selection_color, 
                                              width=2)
                        break
        else:
            # Solo actualizar la visualización del rectángulo
            self.update_component_visuals()
    
    def update_text(self, text):
        """Actualiza el texto de un elemento"""
        if not self.selected:
            return
        
        # Actualizar texto en el XML
        self.selected["element"].text = text
        
        # Re-renderizar el layout para ver los cambios inmediatamente
        self.rerender_layout()
    
    def on_click(self, event):
        """Maneja el evento de clic en el canvas"""
        # Convertir coordenadas del canvas a coordenadas reales
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        real_x, real_y = x / self.zoom, y / self.zoom
        
        print(f"[DEBUG] Click en ({x}, {y}) -> real ({real_x}, {real_y})")
        
        # Deseleccionar componente anterior
        self.selected = None
        self.selected_translate = None
        self._dragging = False
        
        # Buscar componente bajo el cursor
        for item in reversed(self.items):  # Reversed para seleccionar el de arriba primero
            abs_x = item["abs_x"] * self.zoom
            abs_y = item["abs_y"] * self.zoom
            width = item["width"] * self.zoom
            height = item["height"] * self.zoom
            
            if abs_x <= x <= abs_x + width and abs_y <= y <= abs_y + height:
                self.selected = item
                print(f"[DEBUG] Seleccionado: {item['type']} en ({item['abs_x']}, {item['abs_y']})")
                
                # Guardar offset para arrastrar
                self.drag_offset_x = x - abs_x
                self.drag_offset_y = y - abs_y
                
                # Si es un componente que tiene translate, guardar referencia
                if "translate" in item and item["translate"] is not None:
                    self.selected_translate = item["translate"]
                
                break
        
        # Actualizar visualización
        self.update_component_visuals()
        
        # Actualizar panel de propiedades
        self.update_properties_panel()
        
        # Mostrar información detallada para depuración
        if self.selected:
            self.print_component_details()
    
    def print_component_details(self):
        """Imprime detalles del componente seleccionado para depuración"""
        if not self.selected:
            return
        
        print("\n[DEBUG] === DETALLES DEL COMPONENTE ===")
        print(f"Tipo: {self.selected['type']}")
        print(f"Posición absoluta: ({self.selected['abs_x']}, {self.selected['abs_y']})")
        print(f"Tamaño: {self.selected['width']}x{self.selected['height']}")
        
        # Información especial para textos
        if self.selected['type'] == "text":
            elem = self.selected['element']
            texto = elem.text or ""
            font_size = elem.attrib.get("size", "14")
            align = elem.attrib.get("align", "left")
            print(f"Texto: '{texto}'")
            print(f"Tamaño de fuente: {font_size}")
            print(f"Alineación: {align}")
            print(f"Altura estimada: {int(int(font_size) * 1.2)}")
            print(f"Anchura estimada: {max(len(texto) * int(int(font_size) * 0.7), 60)}")
        
        # Mostrar atributos del componente
        print("Atributos:")
        for key, value in self.selected['element'].attrib.items():
            print(f"  {key}: {value}")
        
        # Mostrar información del translate padre
        if self.selected_translate is not None:
            print("Translate padre:")
            print(f"  x: {self.selected_translate.attrib.get('x', '0')}")
            print(f"  y: {self.selected_translate.attrib.get('y', '0')}")
            
            # Verificar si hay translates abuelos
            parent = self.find_parent(self.selected_translate)
            if parent is not None and parent.tag == "translate":
                print("Translate abuelo:")
                print(f"  x: {parent.attrib.get('x', '0')}")
                print(f"  y: {parent.attrib.get('y', '0')}")
        
        print("[DEBUG] === FIN DETALLES ===\n")
    
    def on_drag(self, event):
        """Maneja el evento de arrastrar en el canvas"""
        if not self.selected:
            return
        
        # Convertir coordenadas del canvas a coordenadas reales
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        # Calcular nueva posición manteniendo el offset
        new_x = (x - self.drag_offset_x) / self.zoom
        new_y = (y - self.drag_offset_y) / self.zoom
        
        # Guardar posición temporal durante el arrastre
        self.selected["_temp_x"] = new_x
        self.selected["_temp_y"] = new_y
        
        # Marcar que estamos arrastrando
        self._dragging = True
        
        # Actualizar visualización sin re-renderizar
        self.update_component_visuals()
    
    def on_release(self, event):
        """Maneja el evento de soltar el botón del mouse"""
        if not self.selected or not self._dragging:
            return
        
        # Obtener la posición final (temporal)
        new_x = self.selected["_temp_x"]
        new_y = self.selected["_temp_y"]
        
        # Determinar qué elemento debe ser modificado
        elem_type = self.selected["element"].attrib.get("type", "")
        
        # Para iconos, que deben tener sus propias coordenadas
        if elem_type == "icon":
            # Los iconos deben tener x e y directamente
            self.selected["element"].set("x", str(int(new_x)))
            self.selected["element"].set("y", str(int(new_y)))
            
            # Actualizar en el item
            self.selected["comp_x"] = int(new_x)
            self.selected["comp_y"] = int(new_y)
            self.selected["abs_x"] = new_x
            self.selected["abs_y"] = new_y
            
            print(f"[INFO] Actualizado posición del icono a x={int(new_x)}, y={int(new_y)}")
        # Para todos los demás componentes (incluidos textos), modificar el translate padre
        elif self.selected_translate is not None:
            # Calcular el delta de movimiento desde la posición original
            delta_x = new_x - self.selected["abs_x"]
            delta_y = new_y - self.selected["abs_y"]
            
            # Actualizar directamente el translate padre
            curr_x = int(self.selected_translate.attrib.get("x", "0"))
            curr_y = int(self.selected_translate.attrib.get("y", "0"))
            
            # Aplicar el delta al translate
            new_tx = curr_x + int(delta_x)
            new_ty = curr_y + int(delta_y)
            
            # Actualizar el translate
            self.selected_translate.set("x", str(new_tx))
            self.selected_translate.set("y", str(new_ty))
            
            print(f"[INFO] Actualizado translate de ({curr_x}, {curr_y}) a ({new_tx}, {new_ty})")
            print(f"[INFO] Delta aplicado: ({int(delta_x)}, {int(delta_y)})")
            
            # Actualizar la posición absoluta en el item
            self.selected["abs_x"] = new_x
            self.selected["abs_y"] = new_y
            
            # Eliminar atributos x, y del componente si no es un icono
            # Para textos y otros componentes, no deberían tener atributos x,y directos
            if "x" in self.selected["element"].attrib and elem_type != "icon":
                del self.selected["element"].attrib["x"]
                print(f"[INFO] Eliminado atributo x del componente tipo {elem_type}")
            if "y" in self.selected["element"].attrib and elem_type != "icon":
                del self.selected["element"].attrib["y"]
                print(f"[INFO] Eliminado atributo y del componente tipo {elem_type}")
        else:
            print("[INFO] Componente sin translate padre, no se puede mover")
        
        # Limpiar estados temporales
        if "_temp_x" in self.selected:
            del self.selected["_temp_x"]
        if "_temp_y" in self.selected:
            del self.selected["_temp_y"]
        
        # Reenderizar el layout para ver los cambios inmediatamente
        self.rerender_layout()
        
        # Mostrar información detallada del componente después del cambio
        if self.selected:
            self.print_component_details()
        
        self._dragging = False
        
        # Actualizar visualización
        self.update_component_visuals()
    
    def on_mousewheel(self, event):
        """Maneja el evento de la rueda del mouse para zoom"""
        # Determinar dirección del zoom
        if event.delta > 0:
            factor = 1.1
        else:
            factor = 0.9
        
        # Aplicar nuevo zoom
        new_zoom = self.zoom * factor
        
        # Limitar zoom entre 0.1 y 2.0
        if 0.1 <= new_zoom <= 2.0:
            # Guardar zoom anterior
            old_zoom = self.zoom
            self.zoom = new_zoom
            
            # Actualizar tamaño de la imagen
            if self.rendered_image:
                final_width = int(self.width * self.zoom)
                final_height = int(self.height * self.zoom)
                
                # Redimensionar imagen
                display_img = self.rendered_image.resize((final_width, final_height), Image.Resampling.LANCZOS)
                
                # Actualizar imagen en canvas
                self.canvas.delete("layout_image")
                self.tk_image = ImageTk.PhotoImage(display_img)
                self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image, tags="layout_image")
                
                # Actualizar región de scroll
                self.canvas.config(scrollregion=(0, 0, final_width, final_height))
                
                # Actualizar posición de rectángulos de selección
                self.update_component_visuals()
                
                # Actualizar coordenadas de los rectángulos interactivos
                for item in self.items:
                    x = item["abs_x"] * self.zoom
                    y = item["abs_y"] * self.zoom
                    w = item["width"] * self.zoom
                    h = item["height"] * self.zoom
                    
                    if "rect_id" in item:
                        self.canvas.coords(item["rect_id"], x, y, x+w, y+h)
    
    def rgb_to_hex(self, rgb_str):
        """Convierte una cadena RGB a formato hexadecimal para tkinter"""
        try:
            # Separar los valores R,G,B
            parts = rgb_str.split(',')
            if len(parts) >= 3:
                r = int(parts[0])
                g = int(parts[1])
                b = int(parts[2])
                
                # Asegurar que los valores estén en el rango 0-255
                r = max(0, min(r, 255))
                g = max(0, min(g, 255))
                b = max(0, min(b, 255))
                
                # Convertir a hexadecimal
                return f'#{r:02x}{g:02x}{b:02x}'
            return '#ffffff'  # Blanco por defecto
        except Exception as e:
            print(f"[ERROR] Error al convertir RGB a Hex: {e}")
            return '#ffffff'  # Blanco por defecto
    
    def hex_to_rgb(self, hex_color):
        """Convierte un color hexadecimal a formato RGB"""
        # Eliminar el símbolo # si existe
        hex_color = hex_color.lstrip('#')
        
        # Convertir de hex a RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        return f"{r},{g},{b}"
    
    def open_color_picker(self, rgb_var, preview_widget):
        """Abre el selector de color y actualiza el valor RGB"""
        # Convertir RGB actual a hex para el selector
        current_rgb = rgb_var.get()
        current_hex = self.rgb_to_hex(current_rgb)
        
        # Abrir el selector de color
        color = colorchooser.askcolor(color=current_hex, title="Seleccionar color")
        
        # Si se seleccionó un color (no se canceló)
        if color and color[1]:
            # Actualizar el valor RGB en la entrada
            new_rgb = self.hex_to_rgb(color[1])
            rgb_var.set(new_rgb)
            
            # Actualizar la vista previa del color
            preview_widget.config(bg=color[1])
            
            # Actualizar el atributo en el elemento
            self.update_attribute("rgb", new_rgb)
    
    def open_outline_picker(self, outline_var, preview_widget):
        """Abre el selector de color para el contorno (outline)"""
        # Separar el valor del contorno en R,G,B,A
        outline_parts = outline_var.get().split(',')
        
        # Asegurarse de que hay suficientes partes
        if len(outline_parts) < 4:
            outline_parts = ['0', '0', '0', '100']  # Valor por defecto
        
        # Extraer los valores RGB (sin alpha)
        r, g, b = outline_parts[:3]
        alpha = outline_parts[3] if len(outline_parts) > 3 else '100'
        
        # Convertir a hex para el selector
        current_hex = self.rgb_to_hex(f"{r},{g},{b}")
        
        # Abrir el selector de color
        color = colorchooser.askcolor(color=current_hex, title="Seleccionar color de contorno")
        
        # Si se seleccionó un color (no se canceló)
        if color and color[1]:
            # Convertir el nuevo color a RGB
            rgb = self.hex_to_rgb(color[1])
            
            # Mantener el valor alpha original
            new_outline = f"{rgb},{alpha}"
            
            # Actualizar el valor en la entrada
            outline_var.set(new_outline)
            
            # Actualizar la vista previa del color
            preview_widget.config(bg=color[1])
            
            # Actualizar el atributo en el elemento
            self.update_attribute("outline", new_outline)
    
    def save_xml(self):
        """Guarda los cambios en el archivo XML"""
        # Guardar el XML
        self.tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)
        print(f"[INFO] Archivo guardado: {self.xml_path}")
        
        # Mensaje de confirmación
        tk.messagebox.showinfo("Guardado", f"El archivo XML ha sido guardado correctamente:\n{self.xml_path}")

if __name__ == "__main__":
    xml_path = seleccionar_xml()
    if not xml_path:
        print("No se seleccionó ningún archivo XML.")
    else:
        root = tk.Tk()
        app = LayoutEditor(root, xml_path)
        root.mainloop()
