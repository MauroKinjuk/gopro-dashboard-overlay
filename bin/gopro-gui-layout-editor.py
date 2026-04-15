import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import xml.etree.ElementTree as ET
import os
from PIL import Image, ImageTk
import traceback
import copy

# Intentar detectar si libraqm está disponible
LIBRAQM_AVAILABLE = False
try:
    from PIL import features
    LIBRAQM_AVAILABLE = features.check_feature('raqm')
    print(f"[INFO] Soporte libraqm disponible: {LIBRAQM_AVAILABLE}")
except (ImportError, AttributeError):
    # Pillow antiguo o característica no disponible
    print("[INFO] No se pudo detectar soporte libraqm, asumiendo no disponible")

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

        # Botón persistente para renderizar cambios (visible siempre encima del botón Guardar)
        self.rerender_btn = tk.Button(
            self.side_panel, text="Renderizar cambios",
            command=self.rerender_layout, bg="#336699", fg="white"
        )
        # Empaquetar encima del botón guardar
        self.rerender_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))

        # Botón Deshacer (persistente)
        self.undo_btn = tk.Button(self.side_panel, text="Deshacer (Ctrl+Z)", command=self.undo, bg="#666", fg="white")
        self.undo_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))

        # Botones de copiar/pegar (persistentes)
        self.copy_btn = tk.Button(self.side_panel, text="Copiar componente", command=self.copy_selected_component, bg="#444", fg="white")
        self.copy_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0,5))
        # Inicialmente deshabilitado hasta que haya selección
        try:
            self.copy_btn.config(state=tk.DISABLED)
        except Exception:
            pass

        self.paste_btn = tk.Button(self.side_panel, text="Pegar en centro", command=self.paste_clipboard_center, bg="#444", fg="white")
        self.paste_btn.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0,5))

        # Portapapeles interno para copia de componentes (XML string)
        self._clipboard = None
        
        # Información del elemento seleccionado
        self.selection_label = tk.Label(self.side_panel, text="Ningún elemento seleccionado", 
                                       fg="white", bg="#222", wraplength=240)
        self.selection_label.pack(pady=10)

        # Panel para añadir componentes (se mostrará solo cuando NO haya selección)
        self.add_frame = tk.Frame(self.side_panel, bg="#222")
        # Añadir etiquetas y controles
        tk.Label(self.add_frame, text="Añadir componente:", fg="white", bg="#222").pack(anchor=tk.W)

        types = ["text", "metric", "icon", "bar", "zone-bar"]
        self.add_type_var = tk.StringVar(value="text")
        self.add_type_menu = tk.OptionMenu(self.add_frame, self.add_type_var, *types)
        self.add_type_menu.config(bg="#444", fg="white")
        self.add_type_menu.pack(fill=tk.X, pady=2)

        coord_frame = tk.Frame(self.add_frame, bg="#222")
        coord_frame.pack(fill=tk.X, pady=2)
        tk.Label(coord_frame, text="X:", fg="white", bg="#222").pack(side=tk.LEFT)
        # Por defecto añadir en el centro del layout
        self.add_x_var = tk.IntVar(value=int(self.width // 2))
        self.add_x_spin = tk.Spinbox(coord_frame, from_=-5000, to=5000, textvariable=self.add_x_var, width=6)
        self.add_x_spin.pack(side=tk.LEFT, padx=5)
        tk.Label(coord_frame, text="Y:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(8,0))
        self.add_y_var = tk.IntVar(value=int(self.height // 2))
        self.add_y_spin = tk.Spinbox(coord_frame, from_=-5000, to=5000, textvariable=self.add_y_var, width=6)
        self.add_y_spin.pack(side=tk.LEFT, padx=5)

        def _add():
            self.add_component(self.add_type_var.get(), int(self.add_x_var.get()), int(self.add_y_var.get()))

        self.add_btn = tk.Button(self.add_frame, text="Añadir", command=_add, bg="#228833", fg="white")
        self.add_btn.pack(fill=tk.X, pady=4)
        # Selector de translate padre para añadir componentes
        parent_frame = tk.Frame(self.add_frame, bg="#222")
        parent_frame.pack(fill=tk.X, pady=4)
        tk.Label(parent_frame, text="Padre (translate):", fg="white", bg="#222").pack(anchor=tk.W)
        self.add_parent_label = tk.Label(parent_frame, text="Ninguno", fg="white", bg="#333")
        self.add_parent_label.pack(fill=tk.X, pady=2)

        pick_parent_frame = tk.Frame(self.add_frame, bg="#222")
        pick_parent_frame.pack(fill=tk.X, pady=2)
        self.select_parent_btn = tk.Button(pick_parent_frame, text="Seleccionar translate (clic en canvas)", command=self.start_select_parent, bg="#555", fg="white")
        self.select_parent_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,4))
        self.clear_parent_btn = tk.Button(pick_parent_frame, text="Limpiar", command=self.clear_add_parent, bg="#444", fg="white")
        self.clear_parent_btn.pack(side=tk.LEFT)
        # Mostrar inicialmente solo si no hay selección (al inicio no hay seleccion)
        try:
            if self.selected is None:
                self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        except Exception:
            self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        # Variable para parent seleccionado desde la UI (translate element)
        self.add_parent_translate = None
        self._selecting_parent = False
        # Offset por defecto al pegar para evitar solapamiento (px)
        self.paste_offset = 20
        
        # Variables de estado
        self.items = []  # Lista de componentes para selección
        self._rect_to_index = {}
        self.selected = None  # Componente seleccionado actualmente
        self.selected_translate = None  # Translate padre seleccionado
        self.rendered_image = None  # Imagen renderizada
        self.tk_image = None  # Referencia para evitar garbage collection
        self._dragging = False
        self._temp_rects = []  # Rectángulos temporales durante arrastre
        
        # Pila de deshacer (almacena snapshots XML como strings)
        self._undo_stack = []
        self._undo_limit = 50

        # Eventos del mouse
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<MouseWheel>', self.on_mousewheel)  # Windows
        # Tecla Delete para borrar componente seleccionado
        try:
            self.master.bind('<Delete>', self.on_delete_key)
        except Exception:
            pass
        # Tecla Ctrl+Z para deshacer
        try:
            self.master.bind('<Control-z>', self.on_undo_key)
        except Exception:
            pass
        
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
            
            # Usar la fecha/hora actual para asegurar que los componentes datetime muestren datos actuales
            import datetime
            current_time = datetime.datetime.now()
            
            rng = random.Random(12345)
            timeseries = fake.fake_framemeta(timedelta(minutes=5), step=timedelta(seconds=1), rng=rng, 
                                             point_step=0.0001, start_timestamp=int(current_time.timestamp()))
            
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
                
                # Si libraqm no está disponible, necesitamos crear una copia del árbol XML y eliminar
                # atributos que requieren libraqm para evitar errores de renderizado
                if not LIBRAQM_AVAILABLE:
                    print("[INFO] Libraqm no disponible, eliminando atributos de dirección de texto temporalmente para renderizado")
                    temp_tree = copy.deepcopy(self.tree)
                    temp_root = temp_tree.getroot()
                    self.remove_libraqm_attributes(temp_root)
                    xml_str = ET.tostring(temp_root, encoding="unicode")
                
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

    def compute_translate_bounds(self, translate_elem):
        """Compute approximate bounding box (minx,miny,maxx,maxy) for a <translate> element by
        walking its child components and nested translates using their x/y offsets and
        component sizes estimation similar to parse_components.
        Coordinates returned are absolute (not zoomed).
        """
        def walk(node, offx=0, offy=0):
            minx = float('inf')
            miny = float('inf')
            maxx = float('-inf')
            maxy = float('-inf')

            this_x = offx
            this_y = offy
            if node.tag == 'translate':
                try:
                    this_x += int(node.attrib.get('x', 0))
                    this_y += int(node.attrib.get('y', 0))
                except Exception:
                    pass

            for child in node:
                if child.tag == 'component':
                    cx = this_x + int(child.attrib.get('x', child.attrib.get('comp_x', 0)) or 0)
                    cy = this_y + int(child.attrib.get('y', child.attrib.get('comp_y', 0)) or 0)
                    ctype = child.attrib.get('type', '')
                    # Estimate size
                    try:
                        if ctype == 'icon':
                            s = int(child.attrib.get('size', 55))
                            w = h = s
                        elif ctype == 'text':
                            fs = int(child.attrib.get('size', 14))
                            text = child.text or ''
                            h = int(fs * 1.2)
                            w = max(len(text) * int(fs * 0.7), 60)
                        else:
                            w = int(child.attrib.get('width', 180))
                            h = int(child.attrib.get('height', 60))
                    except Exception:
                        w, h = 100, 40

                    minx = min(minx, cx)
                    miny = min(miny, cy)
                    maxx = max(maxx, cx + w)
                    maxy = max(maxy, cy + h)
                elif child.tag == 'translate':
                    sx, sy, ex, ey = walk(child, this_x, this_y)
                    minx = min(minx, sx)
                    miny = min(miny, sy)
                    maxx = max(maxx, ex)
                    maxy = max(maxy, ey)

            if minx == float('inf'):
                # No components; use translate coords as a tiny box
                try:
                    tx = offx + int(translate_elem.attrib.get('x', 0))
                    ty = offy + int(translate_elem.attrib.get('y', 0))
                except Exception:
                    tx, ty = offx, offy
                return tx, ty, tx + 10, ty + 10

            return minx, miny, maxx, maxy

        return walk(translate_elem, 0, 0)

    def find_translate_at(self, x, y):
        """Find the deepest translate element that contains point (x,y) in absolute coordinates.
        Returns the element or None.
        """
        candidates = []
        # walk all translate elements
        for t in self.root.findall('.//translate'):
            try:
                sx, sy, ex, ey = self.compute_translate_bounds(t)
                if sx <= x <= ex and sy <= y <= ey:
                    candidates.append((sx, sy, ex, ey, t))
            except Exception:
                continue

        if not candidates:
            return None

        # choose the smallest area (the deepest/smallest translate)
        candidates.sort(key=lambda it: (it[2]-it[0])*(it[3]-it[1]))
        return candidates[0][4]

    def start_select_parent(self):
        """Activa el modo para seleccionar un <translate> en el canvas como parent."""
        try:
            self._selecting_parent = True
            try:
                self.add_parent_label.config(text='(esperando clic...)')
            except Exception:
                pass
            messagebox.showinfo('Seleccionar parent', 'Haz clic en el canvas sobre el área del translate que quieres usar como padre.')
        except Exception as e:
            print(f"[ERROR] start_select_parent: {e}")

    def clear_add_parent(self):
        """Limpia la selección de parent para añadir componentes."""
        try:
            self.add_parent_translate = None
            try:
                self.add_parent_label.config(text='Ninguno')
            except Exception:
                pass
            messagebox.showinfo('Padre limpiado', 'Se ha limpiado la selección del parent para añadir componentes.')
        except Exception as e:
            print(f"[ERROR] clear_add_parent: {e}")
    
    def parse_components(self):
        """Analiza el XML para identificar todos los componentes seleccionables"""
        # Eliminar rectángulos previos del canvas para evitar superposición
        try:
            for rid in list(self._rect_to_index.keys()):
                try:
                    self.canvas.delete(rid)
                except Exception:
                    pass
        except Exception:
            pass

        self._rect_to_index.clear()
        self.items.clear()
        
        def get_align_offsets(elem, width, height):
            """Calcula el desplazamiento horizontal/vertical según el atributo 'align'.
            Devuelve (x_offset, y_offset) en píxeles que deben sumarse a la posición ancla.
            """
            align = elem.attrib.get("align", "left")
            # Normalizar
            a = align.lower()
            # Horizontal
            x_off = 0
            if a == "center" or a == "centre":
                x_off = -width // 2
            elif a == "right" or (len(a) >= 1 and a[0] == 'r'):
                # 'right' o anclas como 'rt','rm','rb'
                x_off = -width
            else:
                # izquierda por defecto o anclas que empiezan por 'l'
                x_off = 0

            # Vertical (soporte básico para anclas de dos letras: t,m,b)
            y_off = 0
            if len(a) == 2:
                v = a[1]
                if v == 'm':
                    y_off = -height // 2
                elif v == 'b':
                    y_off = -height
                else:
                    y_off = 0

            return x_off, y_off


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
                    
                    # Calcular desplazamientos por alineación (hitbox)
                    x_off, y_off = get_align_offsets(child, width, height)
                    hit_x = x + x_off
                    hit_y = y + y_off

                    # Dibujar un rectángulo de selección usando la hitbox
                    zx = hit_x * self.zoom
                    zy = hit_y * self.zoom
                    zw = width * self.zoom
                    zh = height * self.zoom
                    
                    # Crear rectángulo interactivo (invisible)
                    idx = len(self.items)
                    rect_id = self.canvas.create_rectangle(
                        zx, zy, zx+zw, zy+zh,
                        outline="", fill="", tags=f"comp_{idx}"
                    )

                    item["rect_id"] = rect_id
                    # Guardar hitbox para uso posterior (selección/drag)
                    item["hit_x"] = hit_x
                    item["hit_y"] = hit_y
                    self.items.append(item)
                    # Mapear rect_id a índice para selección rápida
                    self._rect_to_index[rect_id] = idx

                    # Debug: imprimir info de rectángulo para métricas
                    if ctype == "metric":
                        try:
                            print(f"[DEBUG] Metric rect #{idx} id={rect_id} box=({zx},{zy},{zx+zw},{zy+zh}) anchor=({x},{y}) hit=({hit_x},{hit_y}) zoom={self.zoom}")
                        except Exception:
                            pass

                    # Asegurar que el rectángulo esté por encima de la imagen para recibir clicks
                    try:
                        self.canvas.tag_raise(rect_id)
                    except Exception:
                        pass

                    # Nota: se suprimió el highlight al pasar el ratón que dibujaba un recuadro amarillo

                    # Asegurar que hacer click en el rectángulo selecciona el componente
                    # usamos i como valor por defecto para evitar cierre sobre la variable
                    self.canvas.tag_bind(rect_id, '<Button-1>', lambda e, i=idx: self._on_rect_click(i, e))
                    
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

    def _get_align_offsets_for_elem(self, elem, width, height):
        """Wrapper de utilidad para calcular offsets de alineación desde otros métodos.
        Devuelve (x_off, y_off).
        """
        try:
            align = elem.attrib.get("align", "left")
            a = align.lower()
            x_off = 0
            if a == "center" or a == "centre":
                x_off = -width // 2
            elif a == "right" or (len(a) >= 1 and a[0] == 'r'):
                x_off = -width
            else:
                x_off = 0

            y_off = 0
            if len(a) == 2:
                v = a[1]
                if v == 'm':
                    y_off = -height // 2
                elif v == 'b':
                    y_off = -height
                else:
                    y_off = 0

            return x_off, y_off
        except Exception:
            return 0, 0
        
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
            # x,y son coordenadas ancla (las que están en el XML o las temporales durante drag)
            anchor_x = self.selected.get("_temp_x", self.selected["abs_x"])
            anchor_y = self.selected.get("_temp_y", self.selected["abs_y"])
            x = anchor_x
            y = anchor_y
            
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
            
            # Calcular offsets por alineación y dibujar rectángulo de selección con zoom aplicado
            x_off, y_off = (0, 0)
            try:
                x_off, y_off = self._get_align_offsets_for_elem(elem, w, h)
            except Exception:
                # Fallback al comportamiento antiguo
                x_off, y_off = (0, 0)

            hit_x = x + x_off
            hit_y = y + y_off

            zx = hit_x * self.zoom
            zy = hit_y * self.zoom
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
            # Añadir información del padre si existe
            try:
                if self.selected_translate is not None:
                    px = self.selected_translate.attrib.get('x', '0')
                    py = self.selected_translate.attrib.get('y', '0')
                    # Añadir al label actual
                    cur = self.selection_label.cget('text')
                    self.selection_label.config(text=cur + f"\nPadre: translate x={px} y={py}")
            except Exception:
                pass
            self.update_properties_panel()
    
    def update_properties_panel(self):
        """Actualiza el panel de propiedades según el elemento seleccionado"""
        # Limpiar panel excepto elementos fijos
        fixed_widgets = [self.selection_label, self.save_btn]
        # Proteger botones persistentes para que no sean destruidos al actualizar el panel
        if hasattr(self, 'rerender_btn') and self.rerender_btn is not None:
            fixed_widgets.append(self.rerender_btn)
        if hasattr(self, 'undo_btn') and self.undo_btn is not None:
            fixed_widgets.append(self.undo_btn)
        if hasattr(self, 'add_frame') and self.add_frame is not None:
            fixed_widgets.append(self.add_frame)
        if hasattr(self, 'copy_btn') and self.copy_btn is not None:
            fixed_widgets.append(self.copy_btn)
        if hasattr(self, 'paste_btn') and self.paste_btn is not None:
            fixed_widgets.append(self.paste_btn)

        for widget in self.side_panel.pack_slaves():
            if widget not in fixed_widgets:
                widget.destroy()
        
        # Si no hay selección, mostrar panel 'Añadir componente' y salir
        if not self.selected:
            try:
                # Limpiar otros widgets ya realizados
                # Mostrar panel de añadir componente (si existe)
                if hasattr(self, 'add_frame') and self.add_frame is not None:
                    # Primero eliminar cualquier duplicate
                    for w in self.side_panel.pack_slaves():
                        protected = (
                            self.selection_label,
                            self.save_btn,
                            getattr(self, 'rerender_btn', None),
                            getattr(self, 'undo_btn', None),
                            getattr(self, 'copy_btn', None),
                            getattr(self, 'paste_btn', None)
                        )
                        if w not in protected and w is not self.add_frame:
                            w.destroy()
                    self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
                # Deshabilitar botón copiar cuando no hay selección
                try:
                    if hasattr(self, 'copy_btn') and self.copy_btn is not None:
                        self.copy_btn.config(state=tk.DISABLED)
                except Exception:
                    pass
                # Habilitar/deshabilitar pegar según portapapeles
                try:
                    if hasattr(self, 'paste_btn') and self.paste_btn is not None:
                        state = tk.NORMAL if getattr(self, '_clipboard', None) else tk.DISABLED
                        self.paste_btn.config(state=state)
                except Exception:
                    pass
                return
            except Exception:
                return
        
        elem = self.selected["element"]
        # Habilitar botón copiar y controlar estado del pegar
        try:
            if hasattr(self, 'copy_btn') and self.copy_btn is not None:
                self.copy_btn.config(state=tk.NORMAL)
        except Exception:
            pass
        try:
            if hasattr(self, 'paste_btn') and self.paste_btn is not None:
                state = tk.NORMAL if getattr(self, '_clipboard', None) else tk.DISABLED
                self.paste_btn.config(state=state)
        except Exception:
            pass
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
                    command=lambda: self.update_attribute("x", x_var.get(), render=True)
                )
                x_spin.pack(side=tk.LEFT, padx=5)
                
                tk.Label(pos_frame, text="Y:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
                y_var = tk.IntVar(value=int(elem.attrib.get("y", 0)))
                y_spin = tk.Spinbox(
                    pos_frame, from_=-5000, to=5000, textvariable=y_var, width=6,
                    command=lambda: self.update_attribute("y", y_var.get(), render=True)
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

            # Tamaño de fuente
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño:", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 14)))
            size_spin = tk.Spinbox(
                size_frame, from_=5, to=200, textvariable=size_var, width=6,
                command=lambda: self.update_attribute("size", size_var.get(), render=True)
            )
            size_spin.pack(side=tk.LEFT, padx=5)

            # Color RGB
            color_frame = tk.Frame(props_frame, bg="#222")
            color_frame.pack(fill=tk.X, pady=5)
            tk.Label(color_frame, text="Color RGB:", fg="white", bg="#222").pack(anchor=tk.W)
            rgb_input_frame = tk.Frame(color_frame, bg="#222")
            rgb_input_frame.pack(fill=tk.X, pady=2)
            rgb_var = tk.StringVar(value=elem.attrib.get("rgb", "255,255,255"))
            rgb_entry = tk.Entry(rgb_input_frame, textvariable=rgb_var, width=15)
            rgb_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            rgb_var.trace_add("write", lambda *args: self.update_attribute("rgb", rgb_var.get(), render=True))
            color_preview = tk.Frame(rgb_input_frame, width=30, height=20, bg=self.rgb_to_hex(rgb_var.get()))
            color_preview.pack(side=tk.LEFT, padx=5)
            color_button = tk.Button(rgb_input_frame, text="Elegir color", 
                                     command=lambda: self.open_color_picker(rgb_var, color_preview),
                                     bg="#336699", fg="white")
            color_button.pack(side=tk.LEFT, padx=5)

            # Transparencia (alpha)
            alpha_frame = tk.Frame(color_frame, bg="#222")
            alpha_frame.pack(fill=tk.X, pady=2)
            tk.Label(alpha_frame, text="Transparencia:", fg="white", bg="#222").pack(side=tk.LEFT)
            rgb_parts = rgb_var.get().split(',')
            has_alpha = len(rgb_parts) >= 4
            alpha_value = int(rgb_parts[3]) if has_alpha else 255
            alpha_var = tk.IntVar(value=alpha_value)
            alpha_scale = tk.Scale(alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                variable=alpha_var, bg="#333", fg="white",
                                highlightbackground="#222", troughcolor="#444",
                                command=lambda val: self.update_rgb_alpha(rgb_var, color_preview, int(val)))
            alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            alpha_label = tk.Label(alpha_frame, text=f"{alpha_value}", width=3, fg="white", bg="#222")
            alpha_label.pack(side=tk.LEFT)
            def update_alpha_label(*args):
                alpha_label.config(text=f"{alpha_var.get()}")
            alpha_var.trace_add("write", update_alpha_label)

            # Contorno (outline)
            outline_frame = tk.Frame(props_frame, bg="#222")
            outline_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_frame, text="Contorno:", fg="white", bg="#222").pack(anchor=tk.W)
            outline_input_frame = tk.Frame(outline_frame, bg="#222")
            outline_input_frame.pack(fill=tk.X, pady=2)
            outline_var = tk.StringVar(value=elem.attrib.get("outline", "0,0,0,100"))
            outline_entry = tk.Entry(outline_input_frame, textvariable=outline_var, width=15)
            outline_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            outline_var.trace_add("write", lambda *args: self.update_attribute("outline", outline_var.get(), render=True))
            outline_parts = outline_var.get().split(',')
            outline_color = ','.join(outline_parts[:3]) if len(outline_parts) >= 3 else "0,0,0"
            outline_preview = tk.Frame(outline_input_frame, width=30, height=20, bg=self.rgb_to_hex(outline_color))
            outline_preview.pack(side=tk.LEFT, padx=5)
            outline_button = tk.Button(outline_input_frame, text="Elegir contorno", 
                                     command=lambda: self.open_outline_picker(outline_var, outline_preview),
                                     bg="#336699", fg="white")
            outline_button.pack(side=tk.LEFT, padx=5)
            outline_alpha_frame = tk.Frame(outline_frame, bg="#222")
            outline_alpha_frame.pack(fill=tk.X, pady=2)
            tk.Label(outline_alpha_frame, text="Transparencia:", fg="white", bg="#222").pack(side=tk.LEFT)
            outline_has_alpha = len(outline_parts) >= 4
            outline_alpha_value = int(outline_parts[3]) if outline_has_alpha else 100
            outline_alpha_var = tk.IntVar(value=outline_alpha_value)
            outline_alpha_scale = tk.Scale(outline_alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                         variable=outline_alpha_var, bg="#333", fg="white",
                                         highlightbackground="#222", troughcolor="#444",
                                         command=lambda val: self.update_outline_alpha(outline_var, outline_preview, int(val)))
            outline_alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            outline_alpha_label = tk.Label(outline_alpha_frame, text=f"{outline_alpha_value}", width=3, fg="white", bg="#222")
            outline_alpha_label.pack(side=tk.LEFT)
            def update_outline_alpha_label(*args):
                outline_alpha_label.config(text=f"{outline_alpha_var.get()}")
            outline_alpha_var.trace_add("write", update_outline_alpha_label)
            outline_width_frame = tk.Frame(props_frame, bg="#222")
            outline_width_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_width_frame, text="Ancho de contorno:", fg="white", bg="#222").pack(side=tk.LEFT)
            outline_width_var = tk.IntVar(value=int(elem.attrib.get("outline_width", 1)))
            outline_width_spin = tk.Spinbox(
                outline_width_frame, from_=1, to=20, textvariable=outline_width_var, width=6,
                command=lambda: self.update_attribute("outline_width", outline_width_var.get(), render=True)
            )
            outline_width_spin.pack(side=tk.LEFT, padx=5)

            # Dirección del texto (direction)
            direction_frame = tk.Frame(props_frame, bg="#222")
            direction_frame.pack(fill=tk.X, pady=5)
            tk.Label(direction_frame, text="Dirección:", fg="white", bg="#222").pack(side=tk.LEFT)
            direction_var = tk.StringVar(value=elem.attrib.get("direction", "ltr"))
            direction_options = ["ltr", "rtl", "ttb"]
            direction_dropdown = tk.OptionMenu(direction_frame, direction_var, *direction_options, command=lambda val: self.update_attribute("direction", val, render=True))
            direction_dropdown.config(bg="#444", fg="white", width=10)
            direction_dropdown["menu"].config(bg="#444", fg="white")
            direction_dropdown.pack(side=tk.LEFT, padx=5)
            warning_label = tk.Label(direction_frame, text="(Requiere libraqm)", fg="#aaa", bg="#222", font=("Arial", 8))
            warning_label.pack(side=tk.LEFT, padx=5)

            # Alineación
            align_frame = tk.Frame(props_frame, bg="#222")
            align_frame.pack(fill=tk.X, pady=5)
            tk.Label(align_frame, text="Alineación:", fg="white", bg="#222").pack(side=tk.LEFT)
            align_var = tk.StringVar(value=elem.attrib.get("align", "left"))
            align_options = ["left", "center", "right", "lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"]
            align_dropdown = tk.OptionMenu(align_frame, align_var, *align_options, command=lambda val: self.update_attribute("align", val, render=True))
            align_dropdown.config(bg="#444", fg="white", width=10)
            align_dropdown["menu"].config(bg="#444", fg="white")
            align_dropdown.pack(side=tk.LEFT, padx=5)
            align_help_btn = tk.Button(align_frame, text="?", command=self.show_align_help, bg="#555", fg="white", width=2)
            align_help_btn.pack(side=tk.LEFT, padx=2)
            
        elif ctype == "datetime":
            # Formato de fecha/hora
            format_frame = tk.Frame(props_frame, bg="#222")
            format_frame.pack(fill=tk.X, pady=5)
            tk.Label(format_frame, text="Formato:", fg="white", bg="#222").pack(anchor=tk.W)
            format_var = tk.StringVar(value=elem.attrib.get("format", "%Y-%m-%d %H:%M:%S"))
            format_entry = tk.Entry(format_frame, textvariable=format_var)
            format_entry.pack(fill=tk.X, pady=2)
            # Al cambiar el formato, actualizar el atributo y re-renderizar inmediatamente
            format_var.trace_add("write", lambda *args: self.update_attribute("format", format_var.get(), render=True))
            
            # Mostrar ejemplos de formatos comunes
            examples_frame = tk.Frame(props_frame, bg="#222")
            examples_frame.pack(fill=tk.X, pady=5)
            tk.Label(examples_frame, text="Ejemplos:", fg="white", bg="#222").pack(anchor=tk.W)
            
            examples_list = tk.Frame(examples_frame, bg="#222")
            examples_list.pack(fill=tk.X, pady=2)
            
            # Botones para formatos predefinidos
            date_formats = [
                ("%Y-%m-%d", "2023-08-13", "Fecha ISO"),
                ("%d/%m/%Y", "13/08/2023", "Fecha Europa"),
                ("%m/%d/%Y", "08/13/2023", "Fecha EEUU"),
                ("%H:%M:%S", "14:30:45", "Hora 24h"),
                ("%I:%M:%S %p", "02:30:45 PM", "Hora 12h"),
                ("%H:%M:%S.%f", "14:30:45.123456", "Hora con ms"),
                ("%Y-%m-%d %H:%M:%S", "2023-08-13 14:30:45", "Fecha y hora completa"),
                ("%a, %d %b %Y", "Dom, 13 Ago 2023", "Fecha con día de semana")
            ]
            
            for i, (fmt, example, desc) in enumerate(date_formats):
                btn_frame = tk.Frame(examples_list, bg="#222")
                btn_frame.pack(fill=tk.X, pady=2)
                
                btn = tk.Button(btn_frame, text=example, 
                               command=lambda f=fmt: format_var.set(f),
                               bg="#336699", fg="white")
                btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
                
                # Label para mostrar el formato y descripción
                lbl = tk.Label(btn_frame, text=f"{fmt} - {desc}", fg="#aaa", bg="#222")
                lbl.pack(side=tk.LEFT, padx=5)
            
            # Truncar decimales de segundos
            truncate_frame = tk.Frame(props_frame, bg="#222")
            truncate_frame.pack(fill=tk.X, pady=5)
            tk.Label(truncate_frame, text="Truncar decimales:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            truncate_values = ["", "1", "2", "3", "4", "5"]
            truncate_var = tk.StringVar(value=elem.attrib.get("truncate", ""))
            
            truncate_dropdown = tk.OptionMenu(truncate_frame, truncate_var, *truncate_values, 
                                            command=lambda val: self.update_attribute("truncate", val, render=True))
            truncate_dropdown.config(bg="#444", fg="white", width=5)
            truncate_dropdown["menu"].config(bg="#444", fg="white")
            truncate_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Explicación del truncado
            tk.Label(truncate_frame, text="(1=décimas, 2=centésimas...)", 
                    fg="#aaa", bg="#222", font=("Arial", 8)).pack(side=tk.LEFT, padx=5)
            
            # Cache
            cache_frame = tk.Frame(props_frame, bg="#222")
            cache_frame.pack(fill=tk.X, pady=5)
            tk.Label(cache_frame, text="Caché:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            cache_var = tk.StringVar(value=elem.attrib.get("cache", "true"))
            cache_dropdown = tk.OptionMenu(cache_frame, cache_var, "true", "false", 
                                         command=lambda val: self.update_attribute("cache", val, render=True))
            cache_dropdown.config(bg="#444", fg="white", width=5)
            cache_dropdown["menu"].config(bg="#444", fg="white")
            cache_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Explicación del caché
            tk.Label(cache_frame, 
                    text="(false para segundos/milisegundos)", 
                    fg="#aaa", bg="#222", font=("Arial", 8)).pack(side=tk.LEFT, padx=5)
            
            # Botón para previsualizar el datetime con la fecha/hora actual
            preview_btn = tk.Button(
                props_frame, text="Previsualizar con fecha/hora actual", 
                command=self.rerender_layout, bg="#336699", fg="white"
            )
            preview_btn.pack(fill=tk.X, pady=10)
            
            # Tamaño de fuente
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño:", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 14)))
            size_spin = tk.Spinbox(
                size_frame, from_=5, to=200, textvariable=size_var, width=6,
                command=lambda: self.update_attribute("size", size_var.get(), render=True)
            )
            size_spin.pack(side=tk.LEFT, padx=5)
            
            # Color RGB
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
            rgb_var.trace_add("write", lambda *args: self.update_attribute("rgb", rgb_var.get(), render=True))
            
            # Crear muestra de color
            color_preview = tk.Frame(rgb_input_frame, width=30, height=20, bg=self.rgb_to_hex(rgb_var.get()))
            color_preview.pack(side=tk.LEFT, padx=5)
            
            # Botón para selector de color
            color_button = tk.Button(rgb_input_frame, text="Elegir color", 
                                     command=lambda: self.open_color_picker(rgb_var, color_preview),
                                     bg="#336699", fg="white")
            color_button.pack(side=tk.LEFT, padx=5)
            
            # Control de transparencia (alpha) para RGB
            alpha_frame = tk.Frame(color_frame, bg="#222")
            alpha_frame.pack(fill=tk.X, pady=2)
            tk.Label(alpha_frame, text="Transparencia:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Determinar si ya hay un valor alpha en el RGB
            rgb_parts = rgb_var.get().split(',')
            has_alpha = len(rgb_parts) >= 4
            alpha_value = int(rgb_parts[3]) if has_alpha else 255
            
            # Crear control deslizante para transparencia
            alpha_var = tk.IntVar(value=alpha_value)
            alpha_scale = tk.Scale(alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                variable=alpha_var, bg="#333", fg="white",
                                highlightbackground="#222", troughcolor="#444",
                                command=lambda val: self.update_rgb_alpha(rgb_var, color_preview, int(val)))
            alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Etiqueta para mostrar el valor actual
            alpha_label = tk.Label(alpha_frame, text=f"{alpha_value}", width=3, fg="white", bg="#222")
            alpha_label.pack(side=tk.LEFT)
            
            # Actualizar la etiqueta cuando cambie el valor
            def update_alpha_label(*args):
                alpha_label.config(text=f"{alpha_var.get()}")
            alpha_var.trace_add("write", update_alpha_label)
            
            # Alineación
            align_frame = tk.Frame(props_frame, bg="#222")
            align_frame.pack(fill=tk.X, pady=5)
            tk.Label(align_frame, text="Alineación:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Crear variable para alineación
            align_var = tk.StringVar(value=elem.attrib.get("align", "left"))
            
            # Opciones de alineación
            align_options = ["left", "center", "right", "lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"]
            align_dropdown = tk.OptionMenu(align_frame, align_var, *align_options, 
                                         command=lambda val: self.update_attribute("align", val, render=True))
            align_dropdown.config(bg="#444", fg="white", width=10)
            align_dropdown["menu"].config(bg="#444", fg="white")
            align_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Botón de ayuda para alineación
            align_help_btn = tk.Button(align_frame, text="?", 
                                   command=self.show_align_help,
                                   bg="#555", fg="white", width=2)
            align_help_btn.pack(side=tk.LEFT, padx=2)
            
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
            rgb_var.trace_add("write", lambda *args: self.update_attribute("rgb", rgb_var.get(), render=True))
            
            # Crear muestra de color
            color_preview = tk.Frame(rgb_input_frame, width=30, height=20, bg=self.rgb_to_hex(rgb_var.get()))
            color_preview.pack(side=tk.LEFT, padx=5)
            
            # Botón para selector de color
            color_button = tk.Button(rgb_input_frame, text="Elegir color", 
                                     command=lambda: self.open_color_picker(rgb_var, color_preview),
                                     bg="#336699", fg="white")
            color_button.pack(side=tk.LEFT, padx=5)
            
            # Control de transparencia (alpha) para RGB
            alpha_frame = tk.Frame(color_frame, bg="#222")
            alpha_frame.pack(fill=tk.X, pady=2)
            tk.Label(alpha_frame, text="Transparencia:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Determinar si ya hay un valor alpha en el RGB
            rgb_parts = rgb_var.get().split(',')
            has_alpha = len(rgb_parts) >= 4
            alpha_value = int(rgb_parts[3]) if has_alpha else 255
            
            # Crear control deslizante para transparencia
            alpha_var = tk.IntVar(value=alpha_value)
            alpha_scale = tk.Scale(alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                 variable=alpha_var, bg="#333", fg="white",
                                 highlightbackground="#222", troughcolor="#444",
                                 command=lambda val: self.update_rgb_alpha(rgb_var, color_preview, int(val)))
            alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Etiqueta para mostrar el valor actual
            alpha_label = tk.Label(alpha_frame, text=f"{alpha_value}", width=3, fg="white", bg="#222")
            alpha_label.pack(side=tk.LEFT)
            
            # Actualizar la etiqueta cuando cambie el valor
            def update_alpha_label(*args):
                alpha_label.config(text=f"{alpha_var.get()}")
            alpha_var.trace_add("write", update_alpha_label)
            
            # Contorno (outline)
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
            outline_var.trace_add("write", lambda *args: self.update_attribute("outline", outline_var.get(), render=True))
            
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
            
            # Control de transparencia (alpha) para el contorno
            outline_alpha_frame = tk.Frame(outline_frame, bg="#222")
            outline_alpha_frame.pack(fill=tk.X, pady=2)
            tk.Label(outline_alpha_frame, text="Transparencia:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Determinar si ya hay un valor alpha en el outline
            outline_parts = outline_var.get().split(',')
            outline_has_alpha = len(outline_parts) >= 4
            outline_alpha_value = int(outline_parts[3]) if outline_has_alpha else 100
            
            # Crear control deslizante para transparencia del contorno
            outline_alpha_var = tk.IntVar(value=outline_alpha_value)
            outline_alpha_scale = tk.Scale(outline_alpha_frame, from_=0, to=255, orient=tk.HORIZONTAL, 
                                         variable=outline_alpha_var, bg="#333", fg="white",
                                         highlightbackground="#222", troughcolor="#444",
                                         command=lambda val: self.update_outline_alpha(outline_var, outline_preview, int(val)))
            outline_alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            # Etiqueta para mostrar el valor actual
            outline_alpha_label = tk.Label(outline_alpha_frame, text=f"{outline_alpha_value}", width=3, fg="white", bg="#222")
            outline_alpha_label.pack(side=tk.LEFT)
            
            # Actualizar la etiqueta cuando cambie el valor
            def update_outline_alpha_label(*args):
                outline_alpha_label.config(text=f"{outline_alpha_var.get()}")
            outline_alpha_var.trace_add("write", update_outline_alpha_label)
            
            # Ancho del contorno (outline_width)
            outline_width_frame = tk.Frame(props_frame, bg="#222")
            outline_width_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_width_frame, text="Ancho de contorno:", fg="white", bg="#222").pack(side=tk.LEFT)
            outline_width_var = tk.IntVar(value=int(elem.attrib.get("outline_width", 1)))
            outline_width_spin = tk.Spinbox(
                outline_width_frame, from_=1, to=20, textvariable=outline_width_var, width=6,
                command=lambda: self.update_attribute("outline_width", outline_width_var.get(), render=True)
            )
            outline_width_spin.pack(side=tk.LEFT, padx=5)
            
            # Dirección del texto (direction)
            direction_frame = tk.Frame(props_frame, bg="#222")
            direction_frame.pack(fill=tk.X, pady=5)
            tk.Label(direction_frame, text="Dirección:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Crear variable para dirección
            direction_var = tk.StringVar(value=elem.attrib.get("direction", "ltr"))
            
            # Opciones de dirección
            direction_options = ["ltr", "rtl", "ttb"]  # izquierda a derecha, derecha a izquierda, arriba a abajo
            direction_dropdown = tk.OptionMenu(direction_frame, direction_var, *direction_options, 
                                            command=lambda val: self.update_attribute("direction", val, render=True))
            direction_dropdown.config(bg="#444", fg="white", width=10)
            direction_dropdown["menu"].config(bg="#444", fg="white")
            direction_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Advertencia sobre libraqm (suprimida para evitar UI intrusiva)
            
            # Avanzado: Anclaje de texto completo (align completo)
            advanced_align_frame = tk.Frame(props_frame, bg="#222")
            advanced_align_frame.pack(fill=tk.X, pady=5)
            tk.Label(advanced_align_frame, text="Alineación avanzada:", fg="white", bg="#222").pack(side=tk.LEFT)
            
            # Crear variable para alineación avanzada
            adv_align_var = tk.StringVar(value=elem.attrib.get("align", "left"))
            
            # Opciones de alineación avanzada según la documentación de Pillow
            adv_align_options = ["left", "center", "right", "lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"]
            adv_align_dropdown = tk.OptionMenu(advanced_align_frame, adv_align_var, *adv_align_options, 
                                            command=lambda val: self.update_attribute("align", val, render=True))
            adv_align_dropdown.config(bg="#444", fg="white", width=10)
            adv_align_dropdown["menu"].config(bg="#444", fg="white")
            adv_align_dropdown.pack(side=tk.LEFT, padx=5)
            
            # Mostrar mensaje informativo
            tk.Label(advanced_align_frame, text="(l=left, r=right, m=middle, t=top, b=bottom)", 
                    fg="#aaa", bg="#222", font=("Arial", 8)).pack(side=tk.LEFT, padx=5)
            
            # Nota sobre libraqm eliminada por problemas de UI (se conserva la advertencia breve más arriba)
            
        elif ctype == "icon":
            # Tamaño de icono
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño:", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 55)))
            size_spin = tk.Spinbox(
                size_frame, from_=10, to=500, textvariable=size_var, width=6,
                command=lambda: self.update_attribute("size", size_var.get(), render=True)
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
                                      command=lambda value: self.update_attribute("file", value, render=True))
            file_menu.pack(fill=tk.X, pady=2)
        
        elif ctype in ["bar", "zone-bar"]:
            # Tamaño de barra
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(size_frame, text="Ancho:", fg="white", bg="#222").pack(side=tk.LEFT)
            width_var = tk.IntVar(value=int(elem.attrib.get("width", 180)))
            width_spin = tk.Spinbox(
                size_frame, from_=10, to=3000, textvariable=width_var, width=6,
                command=lambda: self.update_attribute("width", width_var.get(), render=True)
            )
            width_spin.pack(side=tk.LEFT, padx=5)
            
            tk.Label(size_frame, text="Alto:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
            height_var = tk.IntVar(value=int(elem.attrib.get("height", 60)))
            height_spin = tk.Spinbox(
                size_frame, from_=10, to=1000, textvariable=height_var, width=6,
                command=lambda: self.update_attribute("height", height_var.get(), render=True)
            )
            height_spin.pack(side=tk.LEFT, padx=5)
            
            # Métrica (selector con etiquetas legibles)
            metric_frame = tk.Frame(props_frame, bg="#222")
            metric_frame.pack(fill=tk.X, pady=5)
            tk.Label(metric_frame, text="Métrica:", fg="white", bg="#222").pack(side=tk.LEFT)

            # Reusar mapping si ya existe, sino definir básico
            try:
                metric_labels_list
                metric_label_var_value = metric_labels.get(elem.attrib.get('metric',''), elem.attrib.get('metric',''))
            except Exception:
                # Definir mapeo mínimo
                metric_labels = {'hr':'Heart rate (hr)','cadence':'Cadence','speed':'Speed','odo':'Odometer (odo)','dist':'Distance (dist)'}
                label_to_short = {v:k for k,v in metric_labels.items()}
                metric_labels_list = [v for k,v in metric_labels.items()]
                metric_label_var_value = metric_labels.get(elem.attrib.get('metric',''), elem.attrib.get('metric',''))

            metric_label_var = tk.StringVar(value=metric_label_var_value)

            def on_bar_metric_selected(label):
                short = label_to_short.get(label, label)
                self.update_attribute('metric', short, render=True)

            metric_menu = tk.OptionMenu(metric_frame, metric_label_var, *metric_labels_list, command=on_bar_metric_selected)
            metric_menu.config(bg="#444", fg="white")
            metric_menu.pack(side=tk.LEFT, padx=5)
            
            # Min/Max
            range_frame = tk.Frame(props_frame, bg="#222")
            range_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(range_frame, text="Min:", fg="white", bg="#222").pack(side=tk.LEFT)
            min_var = tk.StringVar(value=elem.attrib.get("min", "0"))
            min_entry = tk.Entry(range_frame, textvariable=min_var, width=6)
            min_entry.pack(side=tk.LEFT, padx=5)
            min_var.trace_add("write", lambda *args: self.update_attribute("min", min_var.get(), render=True))
            
            tk.Label(range_frame, text="Max:", fg="white", bg="#222").pack(side=tk.LEFT, padx=(10, 0))
            max_var = tk.StringVar(value=elem.attrib.get("max", "100"))
            max_entry = tk.Entry(range_frame, textvariable=max_var, width=6)
            max_entry.pack(side=tk.LEFT, padx=5)

            # Colores de la barra: contenedor y controles reutilizables
            colors_frame = tk.Frame(props_frame, bg="#222")
            colors_frame.pack(fill=tk.X, pady=5)

            # Fill (relleno de la barra)
            fill_var, fill_preview, _, _ = self.create_color_control(colors_frame, "Fill (relleno)", elem.attrib.get('fill', ''), attr_name='fill', default_alpha="255")

            # Color de la propia barra (atributo 'bar')
            bar_var, bar_preview, _, _ = self.create_color_control(colors_frame, "Bar (color)", elem.attrib.get('bar', ''), attr_name='bar', default_alpha="255")

            # Color del marcador cero
            zero_var, zero_preview, _, _ = self.create_color_control(colors_frame, "Zero (cero)", elem.attrib.get('zero', ''), attr_name='zero', default_alpha="255")

            # Colores de los extremos (highlight negative/positive)
            hneg_var, hneg_preview, _, _ = self.create_color_control(colors_frame, "H-Neg", elem.attrib.get('h-neg', ''), attr_name='h-neg', default_alpha="255")
            hpos_var, hpos_preview, _, _ = self.create_color_control(colors_frame, "H-Pos", elem.attrib.get('h-pos', ''), attr_name='h-pos', default_alpha="255")

            # Outline y ancho (usar el picker existente para outline)
            outline_frame = tk.Frame(props_frame, bg="#222")
            outline_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_frame, text="Outline:", fg="white", bg="#222").pack(side=tk.LEFT)
            outline_var = tk.StringVar(value=elem.attrib.get('outline', '0,0,0,100'))
            outline_entry = tk.Entry(outline_frame, textvariable=outline_var)
            outline_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            outline_preview = tk.Frame(outline_frame, width=30, height=20, bg=self.rgb_to_hex(','.join(outline_var.get().split(',')[:3])))
            outline_preview.pack(side=tk.LEFT, padx=5)
            outline_btn = tk.Button(outline_frame, text="Elegir contorno", command=lambda: self.open_outline_picker(outline_var, outline_preview), bg="#336699", fg="white")
            outline_btn.pack(side=tk.LEFT, padx=5)
            outline_var.trace_add('write', lambda *args: self.update_attribute('outline', outline_var.get(), render=True))

            # Ancho de contorno específico para barra
            owidth_frame = tk.Frame(props_frame, bg="#222")
            owidth_frame.pack(fill=tk.X, pady=5)
            tk.Label(owidth_frame, text="Outline width:", fg="white", bg="#222").pack(side=tk.LEFT)
            owidth_var = tk.IntVar(value=int(elem.attrib.get('outline_width', elem.attrib.get('outline-width', '1'))))
            owidth_spin = tk.Spinbox(owidth_frame, from_=0, to=20, textvariable=owidth_var, width=6, command=lambda: self.update_attribute('outline_width', owidth_var.get(), render=True))
            owidth_spin.pack(side=tk.LEFT, padx=5)

            # Units simple entry (bar may have units)
            units_frame = tk.Frame(props_frame, bg="#222")
            units_frame.pack(fill=tk.X, pady=5)
            tk.Label(units_frame, text="Units:", fg="white", bg="#222").pack(side=tk.LEFT)
            units_var = tk.StringVar(value=elem.attrib.get('units', ''))
            units_entry = tk.Entry(units_frame, textvariable=units_var)
            units_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            units_var.trace_add('write', lambda *args: self.update_attribute('units', units_var.get(), render=True))
        
        elif ctype == "metric":
            # Métricas soportadas (short codes)
            metrics_list = [
                'hr','cadence','speed','cspeed','temp','gradient','alt','odo','dist','azi','lat','lon',
                'accl.x','accl.y','accl.z','grav.x','grav.y','grav.z','ori.pitch','ori.roll','ori.yaw',
                'power','cog','respiration','gear.front','gear.rear','sdps'
            ]

            # Mapeo short -> etiqueta legible para mostrar en la UI
            metric_labels = {
                'hr': 'Heart rate (hr)',
                'cadence': 'Cadence',
                'speed': 'Speed',
                'cspeed': 'Current speed (cspeed)',
                'temp': 'Temperature (temp)',
                'gradient': 'Gradient',
                'alt': 'Altitude (alt)',
                'odo': 'Odometer (odo)',
                'dist': 'Distance (dist)',
                'azi': 'Azimuth (azi)',
                'lat': 'Latitude (lat)',
                'lon': 'Longitude (lon)',
                'accl.x': 'Accel X', 'accl.y': 'Accel Y', 'accl.z': 'Accel Z',
                'grav.x': 'Grav X', 'grav.y': 'Grav Y', 'grav.z': 'Grav Z',
                'ori.pitch': 'Orientation Pitch', 'ori.roll': 'Orientation Roll', 'ori.yaw': 'Orientation Yaw',
                'power': 'Power', 'cog': 'Course over ground (cog)', 'respiration': 'Respiration',
                'gear.front': 'Gear Front', 'gear.rear': 'Gear Rear', 'sdps': 'SDPS'
            }

            # Reverse mapping label -> short
            label_to_short = {v: k for k, v in metric_labels.items()}

            # List of labels to show (preserve order of metrics_list)
            metric_labels_list = [metric_labels.get(k, k) for k in metrics_list]

            # Métrica (selector con etiquetas legibles)
            metric_frame = tk.Frame(props_frame, bg="#222")
            metric_frame.pack(fill=tk.X, pady=5)
            tk.Label(metric_frame, text="Métrica:", fg="white", bg="#222").pack(side=tk.LEFT)

            # Variable para mostrar la etiqueta
            cur_metric_short = elem.attrib.get("metric", "")
            cur_metric_label = metric_labels.get(cur_metric_short, cur_metric_short)
            metric_label_var = tk.StringVar(value=cur_metric_label)

            def on_metric_label_selected(label):
                # Map label back to short code (si no está, usar label como short)
                short = label_to_short.get(label, label)
                # Actualizar el XML y re-render
                self.update_attribute('metric', short, render=True)
                # Recargar menú de unidades acorde
                try:
                    reload_units_menu_for_metric(short)
                except Exception:
                    pass

            metric_menu = tk.OptionMenu(metric_frame, metric_label_var, *metric_labels_list, command=on_metric_label_selected)
            metric_menu.config(bg="#444", fg="white")
            metric_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            # --- Preparar fuentes de unidades (Converters + UnitRegistry) ---
            try:
                from gopro_overlay.layout_xml import Converters
                from gopro_overlay import units as units_module
                conv = Converters()
                conv_keys = list(conv.converters.keys())
            except Exception:
                conv_keys = []

            try:
                pint_keys = list(getattr(units_module.units, '_units', {}).keys()) if 'units_module' in locals() else []
            except Exception:
                pint_keys = []

            all_units = sorted(set(conv_keys + pint_keys + ['','number','location']))

            # Función que devuelve unidades sugeridas para una métrica concreta
            def units_for_metric(metric_name: str):
                m = (metric_name or '').lower()
                mapping = {
                    'speed': ['','mph','kph','mps','knots','speed','pace','pace_km','pace_mile'],
                    'cspeed': ['','mph','kph','mps','knots','speed','pace','pace_km','pace_mile'],
                    'dist': ['','distance','metres','miles','nautical_miles'],
                    'odo': ['','distance','metres','miles'],
                    'alt': ['','altitude','alt','feet','metres'],
                    'temperature': ['','temp','temperature','degC'],
                    'temp': ['','temp','temperature','degC'],
                    'hr': ['','bpm','number'],
                    'cadence': ['','spm','rpm','number'],
                    'power': ['','W','number'],
                    'gradient': ['','number','percent'],
                    'azi': ['','degree','number'],
                    'cog': ['','degree','number'],
                    'lat': ['','location'],
                    'lon': ['','location'],
                }
                # Si hay una entrada específica, retornarla (filtrando por lo disponible)
                opts = mapping.get(m)
                if opts:
                    # Filtrar por unidades realmente disponibles, pero permitir valores arbitrarios
                    filtered = [u for u in opts if (u == '' or u in conv_keys or u in pint_keys or u in ['number','location','percent','degree','W','rpm'])]
                    # Asegurar que siempre hay al menos la opción vacía
                    if '' not in filtered:
                        filtered.insert(0, '')
                    return filtered

                # Fallback: devolver todas las unidades conocidas (sin duplicados)
                return all_units

            # La creación del menú de unidades se realizará más abajo, una vez creado el frame

            # Unidades (menú desplegable poblado desde Converters y unidad personalizada)
            units_frame = tk.Frame(props_frame, bg="#222")
            units_frame.pack(fill=tk.X, pady=5)
            tk.Label(units_frame, text="Unidades:", fg="white", bg="#222").pack(side=tk.LEFT)
            units_var = tk.StringVar(value=elem.attrib.get("units", ""))

            # Intentar obtener la lista de unidades soportadas por Converters
            try:
                from gopro_overlay.layout_xml import Converters
                from gopro_overlay import units as units_module

                conv = Converters()
                conv_keys = list(conv.converters.keys())

                # Intentar leer unidades registradas en pint (si es accesible)
                pint_keys = []
                try:
                    # 'units' es un UnitRegistry; acceder a sus unidades registradas de forma segura
                    pint_keys = list(getattr(units_module.units, '_units', {}).keys())
                except Exception:
                    pint_keys = []

                units_options = sorted(set(conv_keys + pint_keys))
            except Exception:
                # Fallback con una lista razonable
                units_options = ['','mph','kph','mps','knots','pace','pace_km','pace_mile','spm','speed','distance','altitude','feet','miles','metres','nautical_miles','number','location']

            if '' not in units_options:
                units_options.insert(0, '')

            # Crear el menú de unidades inicialmente con las opciones generales
            units_menu = tk.OptionMenu(units_frame, units_var, *units_options, command=lambda v: self.update_attribute("units", v, render=True))
            units_menu.config(bg="#444", fg="white")
            units_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            # Botón para introducir unidad personalizada
            def set_custom_unit():
                try:
                    from tkinter import simpledialog
                    val = simpledialog.askstring("Unidad personalizada", "Introduce la unidad (p.e. 'm' o 'km'):", initialvalue=units_var.get())
                    if val is not None:
                        units_var.set(val)
                        self.update_attribute("units", val, render=True)
                except Exception:
                    val = None
                    try:
                        val = input('Introduce la unidad personalizada: ')
                    except Exception:
                        pass
                    if val:
                        units_var.set(val)
                        self.update_attribute("units", val, render=True)

            custom_btn = tk.Button(units_frame, text="Personalizada", command=set_custom_unit, bg="#555", fg="white", width=10)
            custom_btn.pack(side=tk.LEFT, padx=5)

            # Función para recargar las opciones del menú de unidades según la métrica seleccionada
            def reload_units_menu_for_metric(metric_name):
                opts = units_for_metric(metric_name)
                menu = units_menu['menu']
                menu.delete(0, 'end')

                # Asegurar que la opción actual aparece (si no está en la lista) al inicio
                cur = units_var.get()
                if cur and cur not in opts:
                    opts = [cur] + opts

                for opt in opts:
                    # crear comando que actualice la variable y el atributo XML
                    def _cmd(v=opt):
                        units_var.set(v)
                        self.update_attribute('units', v, render=True)
                    menu.add_command(label=opt, command=_cmd)

            # Handler cuando cambie la métrica: actualizar atributo y recargar menú de unidades
            def on_metric_change(*args):
                # Obtener etiqueta seleccionada y mapear a short code
                try:
                    label = metric_label_var.get()
                except Exception:
                    label = ''
                short = label_to_short.get(label, label)
                # actualizar atributo en XML y re-renderizar
                self.update_attribute('metric', short, render=True)
                # recargar menú de unidades acorde a la métrica
                try:
                    reload_units_menu_for_metric(short)
                except Exception:
                    pass

            # Conectar trazas: cuando cambie la métrica (etiqueta), actualizar también las unidades disponibles
            metric_label_var.trace_add('write', on_metric_change)

            # Color RGB (entrada + preview + selector) - usar control reutilizable
            rgb_var, color_preview, rgb_entry, _ = self.create_color_control(
                props_frame,
                "Color RGB",
                elem.attrib.get("rgb", "255,255,255"),
                attr_name="rgb",
                default_alpha="255"
            )
            # Format (string) - puede ser '.4f' o 'pace'
            format_frame = tk.Frame(props_frame, bg="#222")
            format_frame.pack(fill=tk.X, pady=5)
            tk.Label(format_frame, text="Format:", fg="white", bg="#222").pack(side=tk.LEFT)
            format_var = tk.StringVar(value=elem.attrib.get("format", ""))
            format_entry = tk.Entry(format_frame, textvariable=format_var)
            format_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            format_var.trace_add("write", lambda *args: self.update_attribute("format", format_var.get(), render=True))

            # Cache
            cache_frame = tk.Frame(props_frame, bg="#222")
            cache_frame.pack(fill=tk.X, pady=5)
            tk.Label(cache_frame, text="Caché:", fg="white", bg="#222").pack(side=tk.LEFT)
            cache_var = tk.StringVar(value=elem.attrib.get("cache", "true"))
            cache_dropdown = tk.OptionMenu(cache_frame, cache_var, "true", "false", command=lambda v: self.update_attribute("cache", v, render=True))
            cache_dropdown.config(bg="#444", fg="white", width=6)
            cache_dropdown.pack(side=tk.LEFT, padx=5)

            # Tamaño de fuente
            size_frame = tk.Frame(props_frame, bg="#222")
            size_frame.pack(fill=tk.X, pady=5)
            tk.Label(size_frame, text="Tamaño (size):", fg="white", bg="#222").pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(elem.attrib.get("size", 14)))
            size_spin = tk.Spinbox(size_frame, from_=5, to=200, textvariable=size_var, width=6, command=lambda: self.update_attribute("size", size_var.get(), render=True))
            size_spin.pack(side=tk.LEFT, padx=5)

            # Alineación
            align_frame = tk.Frame(props_frame, bg="#222")
            align_frame.pack(fill=tk.X, pady=5)
            tk.Label(align_frame, text="Alineación:", fg="white", bg="#222").pack(side=tk.LEFT)
            align_var = tk.StringVar(value=elem.attrib.get("align", "left"))
            align_options = ["left", "center", "right", "lt", "mt", "rt", "lm", "mm", "rm", "lb", "mb", "rb"]
            align_dropdown = tk.OptionMenu(align_frame, align_var, *align_options, command=lambda v: self.update_attribute("align", v, render=True))
            align_dropdown.config(bg="#444", fg="white", width=10)
            align_dropdown.pack(side=tk.LEFT, padx=5)

            # Color RGB
            color_frame = tk.Frame(props_frame, bg="#222")
            color_frame.pack(fill=tk.X, pady=5)
            tk.Label(color_frame, text="Color RGB:", fg="white", bg="#222").pack(anchor=tk.W)
            rgb_input_frame = tk.Frame(color_frame, bg="#222")
            rgb_input_frame.pack(fill=tk.X, pady=2)
            rgb_var = tk.StringVar(value=elem.attrib.get("rgb", "255,255,255"))
            rgb_entry = tk.Entry(rgb_input_frame, textvariable=rgb_var, width=15)
            rgb_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            rgb_var.trace_add("write", lambda *args: self.update_attribute("rgb", rgb_var.get(), render=True))
            color_preview = tk.Frame(rgb_input_frame, width=30, height=20, bg=self.rgb_to_hex(rgb_var.get()))
            color_preview.pack(side=tk.LEFT, padx=5)
            color_button = tk.Button(rgb_input_frame, text="Elegir color", command=lambda: self.open_color_picker(rgb_var, color_preview), bg="#336699", fg="white")
            color_button.pack(side=tk.LEFT, padx=5)

            # Contorno (outline)
            outline_frame = tk.Frame(props_frame, bg="#222")
            outline_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_frame, text="Contorno:", fg="white", bg="#222").pack(anchor=tk.W)
            outline_input_frame = tk.Frame(outline_frame, bg="#222")
            outline_input_frame.pack(fill=tk.X, pady=2)
            outline_var = tk.StringVar(value=elem.attrib.get("outline", "0,0,0,100"))
            outline_entry = tk.Entry(outline_input_frame, textvariable=outline_var, width=15)
            outline_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            outline_var.trace_add("write", lambda *args: self.update_attribute("outline", outline_var.get(), render=True))
            outline_preview = tk.Frame(outline_input_frame, width=30, height=20, bg=self.rgb_to_hex(','.join(outline_var.get().split(',')[:3])))
            outline_preview.pack(side=tk.LEFT, padx=5)
            outline_button = tk.Button(outline_input_frame, text="Elegir contorno", command=lambda: self.open_outline_picker(outline_var, outline_preview), bg="#336699", fg="white")
            outline_button.pack(side=tk.LEFT, padx=5)

            # Ancho de contorno
            outline_width_frame = tk.Frame(props_frame, bg="#222")
            outline_width_frame.pack(fill=tk.X, pady=5)
            tk.Label(outline_width_frame, text="Ancho contorno:", fg="white", bg="#222").pack(side=tk.LEFT)
            outline_width_var = tk.IntVar(value=int(elem.attrib.get("outline_width", 1)))
            outline_width_spin = tk.Spinbox(outline_width_frame, from_=0, to=20, textvariable=outline_width_var, width=6, command=lambda: self.update_attribute("outline_width", outline_width_var.get(), render=True))
            outline_width_spin.pack(side=tk.LEFT, padx=5)
        
        # Asegurarse de ocultar el panel de añadir cuando hay selección
        try:
            if hasattr(self, 'add_frame') and self.add_frame is not None:
                self.add_frame.forget()
        except Exception:
            pass

        # Botón para eliminar el componente seleccionado
        def _del():
            self.delete_selected_component()

        del_btn = tk.Button(props_frame, text="Eliminar componente", command=_del, bg="#CC4444", fg="white")
        del_btn.pack(fill=tk.X, pady=5)

        # Botón para ver/editar todos los atributos
        all_attrs_btn = tk.Button(
            props_frame, text="Ver todos los atributos", 
            command=self.show_all_attributes, bg="#333", fg="white"
        )
        all_attrs_btn.pack(fill=tk.X, pady=10)
        
    # Nota: el botón persistente "Renderizar cambios" se crea en el constructor
    
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
    
    def remove_libraqm_attributes(self, node):
        """Elimina temporalmente atributos que requieren libraqm de un árbol XML"""
        # Lista de atributos que requieren libraqm
        libraqm_attrs = ["direction"]
        
        # Procesar los componentes de texto
        for elem in node.findall(".//component[@type='text']"):
            for attr in libraqm_attrs:
                if attr in elem.attrib:
                    print(f"[INFO] Eliminando atributo '{attr}' temporalmente para el renderizado")
                    del elem.attrib[attr]
        
        # Procesar recursivamente todos los elementos
        for child in node:
            self.remove_libraqm_attributes(child)
    
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

    def on_delete_key(self, event):
        """Handler para la tecla Delete"""
        self.delete_selected_component()

    def delete_selected_component(self):
        """Elimina el componente seleccionado del árbol XML y re-renderiza."""
        if not self.selected:
            return

        elem = self.selected['element']
        parent = self.find_parent(elem)
        if parent is None:
            messagebox.showwarning("No se puede eliminar", "No se pudo encontrar el elemento padre.")
            return

        # Preguntar confirmación
        if not messagebox.askyesno("Eliminar componente", f"¿Eliminar este componente ({elem.attrib.get('type','')})?"):
            return

        # Guardar estado para poder deshacer
        try:
            self.push_undo_state()
        except Exception:
            pass

        # Eliminar del árbol
        try:
            parent.remove(elem)
        except Exception as e:
            print(f"[ERROR] No se pudo eliminar elemento: {e}")
            messagebox.showerror("Error", f"No se pudo eliminar el elemento: {e}")
            return
        # Después de eliminar, si el padre es un <translate> y quedó vacío, eliminarlo también.
        try:
            cur = parent
            # Recorrer hacia arriba eliminando <translate> vacíos
            while cur is not None and cur.tag == 'translate' and len(list(cur)) == 0:
                grand = self.find_parent(cur)
                if grand is None:
                    # No eliminar la raíz
                    break
                try:
                    grand.remove(cur)
                    print(f"[INFO] Eliminado translate vacío en x={cur.attrib.get('x','?')} y={cur.attrib.get('y','?')}")
                except Exception as e:
                    print(f"[WARN] No se pudo eliminar translate vacío: {e}")
                    break
                # Continuar hacia arriba
                cur = grand
        except Exception as e:
            print(f"[WARN] Error al limpiar translates vacíos: {e}")

        # Limpiar selección
        self.selected = None
        self.selected_translate = None

        # Re-render y re-analizar
        self.rerender_layout()
        print("[INFO] Componente eliminado y layout re-renderizado")
    
    def update_attribute(self, attr, value, render=False):
        """Actualiza un atributo del elemento seleccionado"""
        if not self.selected:
            return
        
        # Convertir a string si no lo es
        if not isinstance(value, str):
            value = str(value)
        
        # Actualizar el atributo en el XML
        # Determinar si este atributo debería forzar re-render (atributos que afectan apariencia)
        try:
            render_affecting = {
                'size', 'rgb', 'outline', 'outline_width', 'align', 'direction',
                'file', 'width', 'height', 'metric', 'format', 'truncate', 'cache'
            }
        except Exception:
            render_affecting = set()

        should_render = render or (attr in render_affecting)

        # Si vamos a re-renderizar, guardar snapshot para poder deshacer
        if should_render:
            try:
                self.push_undo_state()
            except Exception:
                pass

        # Aplicar cambio
        self.selected["element"].set(attr, value)

        if should_render:
            # Re-renderizar el layout completo y volver a analizar componentes
            self.render_layout()
            self.parse_components()
            # Restaurar selección al elemento modificado
            if self.selected:
                for i, item in enumerate(self.items):
                    if item["element"] == self.selected["element"]:
                        self.selected = item
                        try:
                            self.canvas.itemconfig(item["rect_id"], outline=self.selection_color, width=2)
                        except Exception:
                            pass
                        break
            # Actualizar panel de propiedades
            try:
                self.update_properties_panel()
            except Exception:
                pass
        else:
            # Solo actualizar la visualización del rectángulo si no re-renderizamos
            self.update_component_visuals()
    
    def update_text(self, text):
        """Actualiza el texto de un elemento"""
        if not self.selected:
            return
        
        # Guardar snapshot antes de cambiar texto
        try:
            self.push_undo_state()
        except Exception:
            pass

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

        # Si estamos en modo seleccionar parent, manejar prioridad y salir
        if getattr(self, '_selecting_parent', False):
            real_x, real_y = x / self.zoom, y / self.zoom
            found = None
            try:
                found = self.find_translate_at(real_x, real_y)
            except Exception:
                found = None

            self._selecting_parent = False
            if found is not None:
                self.add_parent_translate = found
                # Update label
                try:
                    info = f"translate @ x={found.attrib.get('x','0')} y={found.attrib.get('y','0')}"
                    self.add_parent_label.config(text=info)
                except Exception:
                    self.add_parent_label.config(text='translate (seleccionado)')
                messagebox.showinfo('Parent seleccionado', 'Translate seleccionado como padre para añadir componentes.')
            else:
                self.add_parent_translate = None
                self.add_parent_label.config(text='Ninguno')
                messagebox.showinfo('Parent no encontrado', 'No se encontró un <translate> bajo el cursor.')
            # Reiniciar y no proceder con selección normal
            self.update_properties_panel()
            return

        # Primero, probar el item 'current' del canvas (el objeto bajo el cursor según las bindtags)
        found = None
        try:
            current_items = list(self.canvas.find_withtag('current'))
            for hid in reversed(current_items):
                if hid in self._rect_to_index:
                    idx = self._rect_to_index[hid]
                    if 0 <= idx < len(self.items):
                        found = self.items[idx]
                        break
        except Exception:
            found = None

        # Si no encontramos con 'current', probar find_overlapping
        if found is None:
            try:
                hits = list(self.canvas.find_overlapping(x, y, x, y))
                for hid in reversed(hits):
                    if hid in self._rect_to_index:
                        idx = self._rect_to_index[hid]
                        if 0 <= idx < len(self.items):
                            found = self.items[idx]
                            break
            except Exception:
                found = None

        # Si no encontramos con find_overlapping, fallback al método antiguo
        if found is None:
            for item in reversed(self.items):  # Reversed para seleccionar el de arriba primero
                # Usar la hitbox almacenada (hit_x/hit_y) que respeta 'align'
                hit_x = item.get("hit_x", item.get("abs_x", 0)) * self.zoom
                hit_y = item.get("hit_y", item.get("abs_y", 0)) * self.zoom
                width = item.get("width", 0) * self.zoom
                height = item.get("height", 0) * self.zoom

                if hit_x <= x <= hit_x + width and hit_y <= y <= hit_y + height:
                    found = item
                    break

        # Si no hemos encontrado nada, asegurarse de que el editor está en estado "sin selección"
        if found is None:
            self.selected = None
            self.selected_translate = None
            # Borrar rectángulo de selección visible
            try:
                self.canvas.delete("selection")
            except Exception:
                pass

            # Mostrar panel de añadir componente si está disponible
            try:
                if hasattr(self, 'add_frame') and self.add_frame is not None:
                    try:
                        mapped = False
                        try:
                            mapped = bool(self.add_frame.winfo_ismapped())
                        except Exception:
                            mapped = False
                        if not mapped:
                            self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
                    except Exception:
                        try:
                            self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
                        except Exception:
                            pass
            except Exception:
                pass

        if found is not None:
            self.selected = found
            print(f"[DEBUG] Seleccionado: {found['type']} en ({found['abs_x']}, {found['abs_y']})")

            # Guardar offset para arrastrar
            self.drag_offset_x = x - (self.selected['abs_x'] * self.zoom)
            self.drag_offset_y = y - (self.selected['abs_y'] * self.zoom)

            # Si es un componente que tiene translate, guardar referencia
            if 'translate' in self.selected and self.selected['translate'] is not None:
                self.selected_translate = self.selected['translate']
        
        # Actualizar visualización
        self.update_component_visuals()
        
        # Actualizar panel de propiedades
        self.update_properties_panel()
        
        # Mostrar información detallada para depuración
        if self.selected:
            self.print_component_details()
        else:
            # Si no hay selección, forzar que el panel de añadir sea visible y esté encima
            try:
                if hasattr(self, 'add_frame') and self.add_frame is not None:
                    try:
                        if not self.add_frame.winfo_ismapped():
                            self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
                    except Exception:
                        try:
                            self.add_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
                        except Exception:
                            pass
                    try:
                        self.add_frame.lift()
                    except Exception:
                        pass
            except Exception:
                pass
    
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

    def push_undo_state(self):
        """Guarda un snapshot del XML actual en la pila de deshacer."""
        try:
            xml_str = ET.tostring(self.root, encoding='unicode')
            self._undo_stack.append(xml_str)
            # Limitar el tamaño de la pila
            if len(self._undo_stack) > self._undo_limit:
                self._undo_stack = self._undo_stack[-self._undo_limit:]
            print(f"[INFO] Snapshot guardado. Pila deshacer={len(self._undo_stack)}")
        except Exception as e:
            print(f"[WARN] No se pudo crear snapshot de undo: {e}")

    def undo(self):
        """Restaura el último snapshot si existe."""
        if not self._undo_stack:
            print("[INFO] Pila de deshacer vacía")
            return
        try:
            last = self._undo_stack.pop()
            # Parsear y reemplazar el árbol actual
            tree = ET.ElementTree(ET.fromstring(last))
            self.tree = tree
            self.root = self.tree.getroot()
            # Re-renderizar y re-analizar
            self.render_layout()
            self.parse_components()
            self.selected = None
            self.selected_translate = None
            self.update_component_visuals()
            self.update_properties_panel()
            print("[INFO] Undo aplicado")
        except Exception as e:
            print(f"[ERROR] Fallo al aplicar undo: {e}")

    def on_undo_key(self, event):
        """Handler de tecla Ctrl+Z"""
        self.undo()

    def _on_rect_click(self, index, event):
        """Handler para clicks en rectángulos de componente: selecciona el componente correspondiente."""
        if index < 0 or index >= len(self.items):
            return
        item = self.items[index]
        self.selected = item
        # Guardar referencia al translate padre si existe
        self.selected_translate = item.get("translate", None)

        # Guardar offset para arrastrar
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        abs_x = item["abs_x"] * self.zoom
        abs_y = item["abs_y"] * self.zoom
        self.drag_offset_x = x - abs_x
        self.drag_offset_y = y - abs_y

        # Actualizar visuales y panel
        self.update_component_visuals()
        self.update_properties_panel()
        self.print_component_details()
    
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
            # Guardar estado para undo
            try:
                self.push_undo_state()
            except Exception:
                pass

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
            # Guardar estado para undo
            try:
                self.push_undo_state()
            except Exception:
                pass
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
    
    def hex_to_rgb(self, hex_color, include_alpha=False, alpha_value="255"):
        """Convierte un color hexadecimal a formato RGB, opcionalmente incluyendo alpha"""
        # Eliminar el símbolo # si existe
        hex_color = hex_color.lstrip('#')
        
        # Convertir de hex a RGB
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        
        # Opcionalmente incluir alpha
        if include_alpha:
            return f"{r},{g},{b},{alpha_value}"
        else:
            return f"{r},{g},{b}"
    
    def open_color_picker(self, rgb_var, preview_widget):
        """Abre el selector de color y actualiza el valor RGB"""
        # Obtener el valor RGB actual
        current_rgb = rgb_var.get()
        current_parts = current_rgb.split(',')
        
        # Extraer el valor alpha si existe
        alpha_value = "255"  # Valor por defecto
        if len(current_parts) >= 4:
            alpha_value = current_parts[3]
        
        # Convertir RGB a hex para el selector
        current_hex = self.rgb_to_hex(current_rgb)
        
        # Abrir el selector de color
        color = colorchooser.askcolor(color=current_hex, title="Seleccionar color")
        
        # Si se seleccionó un color (no se canceló)
        if color and color[1]:
            # Decidir si incluir el valor alpha en el nuevo RGB
            include_alpha = len(current_parts) >= 4
            
            # Actualizar el valor RGB en la entrada
            new_rgb = self.hex_to_rgb(color[1], include_alpha, alpha_value)
            rgb_var.set(new_rgb)
            
            # Actualizar la vista previa del color
            preview_widget.config(bg=color[1])
            
            # Actualizar el atributo en el elemento
            self.update_attribute("rgb", new_rgb)
            
            # Mostrar información sobre el nuevo color
            rgb_parts = new_rgb.split(',')
            alpha_info = f", Alpha: {alpha_value}" if include_alpha else ""
            print(f"[INFO] Color actualizado a RGB: {','.join(rgb_parts[:3])}{alpha_info}")
    
    def open_outline_picker(self, outline_var, preview_widget):
        """Abre el selector de color para el contorno (outline)"""
        # Separar el valor del contorno en R,G,B,A
        outline_parts = outline_var.get().split(',')
        
        # Asegurarse de que hay suficientes partes
        if len(outline_parts) < 3:
            outline_parts = ['0', '0', '0']  # Valor por defecto
        
        # Extraer el valor alpha si existe
        alpha_value = "100"  # Valor por defecto para contornos
        if len(outline_parts) >= 4:
            alpha_value = outline_parts[3]
        
        # Extraer los valores RGB (sin alpha)
        r, g, b = outline_parts[:3]
        
        # Convertir a hex para el selector
        current_hex = self.rgb_to_hex(f"{r},{g},{b}")
        
        # Abrir el selector de color
        color = colorchooser.askcolor(color=current_hex, title="Seleccionar color de contorno")
        
        # Si se seleccionó un color (no se canceló)
        if color and color[1]:
            # Decidir si incluir el valor alpha en el nuevo outline
            include_alpha = len(outline_parts) >= 4
            
            # Convertir el nuevo color a RGB, manteniendo el valor alpha si existía
            new_outline = self.hex_to_rgb(color[1], include_alpha, alpha_value)
            
            # Actualizar el valor en la entrada
            outline_var.set(new_outline)
            
            # Actualizar la vista previa del color
            preview_widget.config(bg=color[1])
            
            # Actualizar el atributo en el elemento
            self.update_attribute("outline", new_outline, render=True)
            
            # Mostrar información sobre el nuevo color de contorno
            outline_parts = new_outline.split(',')
            alpha_info = f", Alpha: {alpha_value}" if include_alpha else ""
            print(f"[INFO] Color de contorno actualizado a RGB: {','.join(outline_parts[:3])}{alpha_info}")
    
    def update_rgb_alpha(self, rgb_var, preview_widget, alpha_value):
        """Actualiza el valor alpha (transparencia) del color RGB"""
        # Obtener el valor RGB actual
        current_rgb = rgb_var.get()
        rgb_parts = current_rgb.split(',')
        
        # Extraer los valores RGB (sin alpha)
        if len(rgb_parts) < 3:
            return  # No hay suficientes valores para actualizar
        
        r, g, b = rgb_parts[:3]
        
        # Crear nuevo valor RGB con alpha
        new_rgb = f"{r},{g},{b},{alpha_value}"
        
        # Actualizar el valor en la entrada
        rgb_var.set(new_rgb)
        
        # No es necesario actualizar la vista previa ya que el alpha no afecta la apariencia
        # en la interfaz de usuario, solo en el render final
        
        # Actualizar el atributo en el elemento
        self.update_attribute("rgb", new_rgb)
        
        print(f"[INFO] Transparencia de color actualizada a: {alpha_value}/255")

    def create_color_control(self, parent, label_text, init_value, attr_name=None, default_alpha="255"):
        """Crea un control reutilizable para color: entrada, preview y selector.

        Devuelve (var, preview_frame, entry_widget, container_frame).
        Si se proporciona attr_name, las modificaciones actualizan el atributo en el elemento con render=True.
        """
        frame = tk.Frame(parent, bg="#222")
        frame.pack(fill=tk.X, pady=5)

        tk.Label(frame, text=f"{label_text}:", fg="white", bg="#222").pack(anchor=tk.W)
        input_frame = tk.Frame(frame, bg="#222")
        input_frame.pack(fill=tk.X, pady=2)

        var = tk.StringVar(value=init_value or "")
        entry = tk.Entry(input_frame, textvariable=var, width=15)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        try:
            preview_color = self.rgb_to_hex(var.get()) if var.get() else '#ffffff'
        except Exception:
            preview_color = '#ffffff'
        preview = tk.Frame(input_frame, width=30, height=20, bg=preview_color)
        preview.pack(side=tk.LEFT, padx=5)

        def _pick():
            cur = var.get()
            parts = cur.split(',') if cur else []
            alpha = parts[3] if len(parts) >= 4 else default_alpha
            current_hex = self.rgb_to_hex(cur) if cur else '#ffffff'
            color = colorchooser.askcolor(color=current_hex, title=f"Seleccionar color para {label_text}")
            if color and color[1]:
                include_alpha = len(parts) >= 4
                new_val = self.hex_to_rgb(color[1], include_alpha, alpha)
                var.set(new_val)
                preview.config(bg=color[1])
                if attr_name:
                    self.update_attribute(attr_name, new_val, render=True)

        pick_btn = tk.Button(input_frame, text="Elegir color", command=_pick, bg="#336699", fg="white")
        pick_btn.pack(side=tk.LEFT, padx=5)

        if attr_name:
            var.trace_add('write', lambda *args: self.update_attribute(attr_name, var.get(), render=True))

        return var, preview, entry, frame
    
    def update_outline_alpha(self, outline_var, preview_widget, alpha_value):
        """Actualiza el valor alpha (transparencia) del contorno"""
        # Obtener el valor de contorno actual
        current_outline = outline_var.get()
        outline_parts = current_outline.split(',')
        
        # Extraer los valores RGB (sin alpha)
        if len(outline_parts) < 3:
            return  # No hay suficientes valores para actualizar
        
        r, g, b = outline_parts[:3]
        
        # Crear nuevo valor de contorno con alpha
        new_outline = f"{r},{g},{b},{alpha_value}"
        
        # Actualizar el valor en la entrada
        outline_var.set(new_outline)
        
        # No es necesario actualizar la vista previa ya que el alpha no afecta la apariencia
        # en la interfaz de usuario, solo en el render final
        
        # Actualizar el atributo en el elemento
        self.update_attribute("outline", new_outline)
        
        print(f"[INFO] Transparencia de contorno actualizada a: {alpha_value}/255")
    
    def save_xml(self):
        """Guarda los cambios en el archivo XML"""
        # Asegurar formato legible antes de guardar
        try:
            self.indent_xml(self.root)
        except Exception:
            pass

        # Guardar el XML
        self.tree.write(self.xml_path, encoding="utf-8", xml_declaration=True)
        print(f"[INFO] Archivo guardado: {self.xml_path}")
        
        # Mensaje de confirmación
        tk.messagebox.showinfo("Guardado", f"El archivo XML ha sido guardado correctamente:\n{self.xml_path}")

    def add_component(self, ctype: str, x: int = 0, y: int = 0):
        """Añade un componente simple al XML.

        Se crea un <translate x="..." y="..."> que contiene el <component .../>.
        Si hay una selección con translate, se añadirá dentro de ese translate en su lugar.
        """
        try:
            # Guardar snapshot para deshacer
            try:
                self.push_undo_state()
            except Exception:
                pass

            # Determinar contenedor (prioridad: add_parent_translate seleccionado manualmente,
            # luego selected_translate (si se eligió con selección), finalmente la raíz)
            if getattr(self, 'add_parent_translate', None) is not None:
                parent = self.add_parent_translate
            else:
                parent = self.selected_translate if self.selected_translate is not None else self.root

            # Crear translate que contendrá el componente si no añadimos a selected_translate
            if parent is self.root:
                trans = ET.Element('translate')
                trans.set('x', str(int(x)))
                trans.set('y', str(int(y)))
                parent.append(trans)
                container = trans
            else:
                container = parent

            comp = ET.Element('component')
            comp.set('type', ctype)
            # Valores por defecto según tipo
            if ctype == 'text':
                comp.text = 'Nuevo texto'
                # Atributos permitidos para text: size, rgb, align, direction, outline, outline_width, etc.
                comp.set('size', '75')
                comp.set('rgb', '255,255,255')
                # Pillow expects anchor codes like 'mm' for center
                comp.set('align', 'left')
            elif ctype == 'metric':
                comp.set('metric', 'speed')
                comp.set('size', '75')
                comp.set('width', '180')
                comp.set('height', '60')
            elif ctype == 'icon':
                comp.set('file', 'bicycle.png')
                comp.set('size', '55')
            elif ctype in ('bar', 'zone-bar'):
                comp.set('width', '300')
                comp.set('height', '40')
                comp.set('metric', 'speed')
                # Defaults for visual attributes commonly used by bar components
                comp.set('fill', '')
                comp.set('outline', '0,0,0,100')
                comp.set('outline_width', '1')
                comp.set('bar', '')
                comp.set('zero', '')
                comp.set('h-neg', '')
                comp.set('h-pos', '')
                comp.set('units', '')

            container.append(comp)
            # Intentar mantener el XML formateado correctamente
            try:
                self.indent_xml(self.root)
            except Exception:
                pass

            # Re-renderizar para mostrar el nuevo componente
            self.rerender_layout()

            # Seleccionar el nuevo componente si fue correctamente añadido
            try:
                for item in self.items:
                    if item.get('element') is comp:
                        self.selected = item
                        # selected_translate debe apuntar al contenedor si es translate
                        if container.tag == 'translate':
                            self.selected_translate = container
                        else:
                            self.selected_translate = None
                        break
                # Actualizar visual y panel de propiedades
                self.update_component_visuals()
                self.update_properties_panel()
                # Ocultar panel de añadir dado que ahora hay selección
                try:
                    if hasattr(self, 'add_frame') and self.add_frame is not None:
                        self.add_frame.forget()
                except Exception:
                    pass
            except Exception:
                pass

            messagebox.showinfo('Añadido', f'Componente {ctype} añadido.')
        except Exception as e:
            print(f"[ERROR] No se pudo añadir componente: {e}")
            traceback.print_exc()

    def indent_xml(self, elem, level=0):
        """Indent XML tree in-place for pretty printing.

        Produces 4-space indentation and newlines so elements are not jammed.
        """
        # Use 4 spaces per level to match layout style; keep 2 extra spaces for inner content
        i = "\n" + ("    " * level)
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            for child in elem:
                self.indent_xml(child, level+1)
                if not child.tail or not child.tail.strip():
                    child.tail = i + "  "
            if not elem[-1].tail or not elem[-1].tail.strip():
                elem[-1].tail = i
        else:
            if not elem.text or not elem.text.strip():
                elem.text = None

    def copy_selected_component(self):
        """Copia el componente seleccionado al portapapeles interno (XML)."""
        if not self.selected:
            messagebox.showwarning("Copiar", "No hay ningún componente seleccionado para copiar.")
            return
        try:
            elem = self.selected['element']
            # Si el componente tiene un translate padre, copiar el translate entero
            parent = self.selected.get('translate') or self.find_parent(elem)
            if parent is not None and parent.tag == 'translate':
                xml_elem = copy.deepcopy(parent)
                xml_str = ET.tostring(xml_elem, encoding='unicode')
                self._clipboard = xml_str
                # Store metadata to try to paste into same parent if it exists
                try:
                    self._clipboard_meta = {
                        'parent_x': parent.attrib.get('x', None),
                        'parent_y': parent.attrib.get('y', None),
                        'copied': 'translate'
                    }
                except Exception:
                    self._clipboard_meta = None
                copied_desc = f"translate (x={parent.attrib.get('x','?')}, y={parent.attrib.get('y','?')})"
            else:
                xml_elem = copy.deepcopy(elem)
                xml_str = ET.tostring(xml_elem, encoding='unicode')
                self._clipboard = xml_str
                # If there is a parent in the original selection, record its coords
                try:
                    parent = self.selected.get('translate') or self.find_parent(elem)
                    if parent is not None and parent.tag == 'translate':
                        self._clipboard_meta = {
                            'parent_x': parent.attrib.get('x', None),
                            'parent_y': parent.attrib.get('y', None),
                            'copied': 'component'
                        }
                    else:
                        self._clipboard_meta = None
                except Exception:
                    self._clipboard_meta = None
                copied_desc = f"component {elem.attrib.get('type','?')}"
            try:
                self.copy_btn.config(state=tk.NORMAL)
            except Exception:
                pass
            messagebox.showinfo('Copiado', f'{copied_desc} copiado al portapapeles interno.')
            print(f"[INFO] Copiado al portapapeles: {xml_str[:200]}")
        except Exception as e:
            print(f"[ERROR] Fallo al copiar componente: {e}")
            traceback.print_exc()

    def paste_clipboard_center(self):
        """Pega el componente del portapapeles en el centro del render."""
        if not self._clipboard:
            messagebox.showwarning('Pegar', 'Portapapeles vacío. Copia primero un componente.')
            return
        try:
            # Guardar estado para undo
            try:
                self.push_undo_state()
            except Exception:
                pass

            # Crear elemento(s) desde XML del portapapeles
            parsed_elements = None
            try:
                single = ET.fromstring(self._clipboard)
                parsed_elements = [single]
            except ET.ParseError:
                # Puede haber múltiples elementos o texto extra; envolver en un root temporal
                try:
                    wrapper = f"<root>{self._clipboard}</root>"
                    root_wrapped = ET.fromstring(wrapper)
                    parsed_elements = list(root_wrapped)
                except Exception as e:
                    # Fallo al parsear incluso envuelto
                    raise

            cx = int(self.width // 2)
            cy = int(self.height // 2)
            # Apply paste offset to avoid exact overlap with original
            try:
                px = cx + int(getattr(self, 'paste_offset', 20))
                py = cy + int(getattr(self, 'paste_offset', 20))
            except Exception:
                px, py = cx + 20, cy + 20

            # If clipboard metadata points to a parent translate, try to find it in current tree
            found_parent = None
            try:
                meta = getattr(self, '_clipboard_meta', None)
            except Exception:
                meta = None
            if meta and meta.get('parent_x') is not None:
                try:
                    px = str(meta.get('parent_x'))
                    py = str(meta.get('parent_y'))
                    for t in self.root.findall('.//translate'):
                        if t.attrib.get('x') == px and t.attrib.get('y') == py:
                            found_parent = t
                            break
                except Exception:
                    found_parent = None

            # Si se encontró parent equivalente, crear un nuevo <translate> independiente
            if found_parent is not None:
                try:
                    dest_parent = self.find_parent(found_parent) or self.root
                except Exception:
                    dest_parent = self.root

                new_trans = None
                try:
                    if len(parsed_elements) == 1 and parsed_elements[0].tag == 'translate':
                        new_trans = copy.deepcopy(parsed_elements[0])
                        new_trans.set('x', str(px))
                        new_trans.set('y', str(py))
                    else:
                        new_trans = ET.Element('translate')
                        new_trans.set('x', str(px))
                        new_trans.set('y', str(py))
                        for elem in parsed_elements:
                            new_trans.append(copy.deepcopy(elem))

                    dest_parent.append(new_trans)
                    try:
                        self.indent_xml(self.root)
                    except Exception:
                        pass
                    self.rerender_layout()
                    self.parse_components()

                    # Seleccionar el nuevo elemento añadido
                    try:
                        children = list(new_trans)
                        if children:
                            new_elem = children[-1]
                            for item in self.items:
                                if item.get('element') is new_elem:
                                    self.selected = item
                                    self.selected_translate = new_trans
                                    break
                            self.update_component_visuals()
                            self.update_properties_panel()
                    except Exception:
                        pass

                    messagebox.showinfo('Pegado', 'Componente pegado en una nueva copia del translate (independiente).')
                    print('[INFO] Pegado en translate independiente')
                    return
                except Exception as e:
                    print(f"[WARN] Fallo al pegar dentro del translate existente, cayendo al pegado estándar: {e}")
                    # Si falla, continuar con pegado estándar

            # Si solo hay un elemento, tratarlo según su tag
            if len(parsed_elements) == 1:
                elem = parsed_elements[0]
                if elem.tag == 'component':
                    trans = ET.Element('translate')
                    trans.set('x', str(px))
                    trans.set('y', str(py))
                    trans.append(elem)
                    self.root.append(trans)
                elif elem.tag == 'translate':
                    try:
                        elem.set('x', str(px))
                        elem.set('y', str(py))
                    except Exception:
                        pass
                    self.root.append(elem)
                else:
                    trans = ET.Element('translate')
                    trans.set('x', str(px))
                    trans.set('y', str(py))
                    trans.append(elem)
                    self.root.append(trans)
            else:
                # Múltiples elementos: envolver todos en un <translate> central
                trans = ET.Element('translate')
                trans.set('x', str(px))
                trans.set('y', str(py))
                for child in parsed_elements:
                    trans.append(child)
                self.root.append(trans)

            # Formatear, re-render y analizar
            try:
                self.indent_xml(self.root)
            except Exception:
                pass
            self.rerender_layout()
            self.parse_components()

            # Seleccionar el nuevo componente (buscar por igualdad de tag/attrs)
            # Preferir el último añadido
            try:
                if self.items:
                    # Try to find the most recently added item by matching element tag/attrs
                    new_item = self.items[-1]
                    self.selected = new_item
                    self.selected_translate = new_item.get('translate', None)
                    self.update_component_visuals()
                    self.update_properties_panel()
            except Exception:
                pass

            messagebox.showinfo('Pegado', 'Componente pegado en el centro.')
            print('[INFO] Componente pegado en el centro')
        except Exception as e:
            print(f"[ERROR] Fallo al pegar componente: {e}")
            traceback.print_exc()
    
    def show_align_help(self):
        """Muestra una ventana con ayuda sobre alineación de texto"""
        help_window = tk.Toplevel(self.master)
        help_window.title("Ayuda sobre alineación de texto")
        help_window.geometry("500x600")
        help_window.transient(self.master)
        help_window.grab_set()
        
        frame = tk.Frame(help_window, bg="#222", padx=15, pady=15)
        frame.pack(fill=tk.BOTH, expand=True)
        
        title = tk.Label(frame, text="Opciones de alineación de texto", fg="white", bg="#222", 
                       font=("Arial", 14, "bold"))
        title.pack(pady=(0, 10))
        
        scroll = tk.Scrollbar(frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        text = tk.Text(frame, bg="#333", fg="white", wrap=tk.WORD, yscrollcommand=scroll.set, 
                     font=("Consolas", 10), padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        scroll.config(command=text.yview)
        
        help_text = """Opciones de alineación de texto (atributo 'align'):

Las opciones básicas son:
- 'left': Alinea el texto a la izquierda
- 'right': Alinea el texto a la derecha

Opciones avanzadas (anclas de texto):
El sistema de anclas de texto permite un control más preciso usando dos letras:
- Primera letra: posición horizontal (l=izquierda, m=medio, r=derecha)
- Segunda letra: posición vertical (t=arriba, m=medio, b=abajo)

Por ejemplo:
- 'lt': Arriba a la izquierda (Left-Top)
- 'mt': Arriba en el centro (Middle-Top)
- 'rt': Arriba a la derecha (Right-Top)
- 'lm': Centro izquierda (Left-Middle)
- 'mm': Centro absoluto (Middle-Middle)
- 'rm': Centro derecha (Right-Middle)
- 'lb': Abajo a la izquierda (Left-Bottom)
- 'mb': Abajo en el centro (Middle-Bottom)
- 'rb': Abajo a la derecha (Right-Bottom)

Estas opciones controlan el punto de anclaje del texto en relación a las coordenadas x,y especificadas.

Para más información, consulta la documentación de Pillow sobre text anchors:
https://pillow.readthedocs.io/en/stable/handbook/text-anchors.html
"""
        
        text.insert(tk.END, help_text)
        text.config(state=tk.DISABLED)
        
        close_btn = tk.Button(frame, text="Cerrar", command=help_window.destroy, 
                            bg="#336699", fg="white")
        close_btn.pack(pady=10)

if __name__ == "__main__":
    xml_path = seleccionar_xml()
    if not xml_path:
        print("No se seleccionó ningún archivo XML.")
    else:
        root = tk.Tk()
        app = LayoutEditor(root, xml_path)
        root.mainloop()
