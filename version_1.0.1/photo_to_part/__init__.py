# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {'name': 'Photo to Part', 'author': 'Ricardo Lugaresi', 'version': (1, 0, 1),
           'blender': (4, 2, 0), 'location': 'Vista 3D > N > Photo to Part',
           'description': 'De una foto a una pieza imprimible: saca el contorno (con agujeros) de una pieza plana, '
                          'a escala con una hoja A4 debajo o con una medida conocida, y la extruye. Todo en modo Objeto',
           'category': 'Object'}

from pathlib import Path

import bpy

from . import build, common


class PhotoProps(bpy.types.PropertyGroup):
    image: bpy.props.StringProperty(name='Foto', subtype='FILE_PATH')
    mode: bpy.props.EnumProperty(name='Medida', items=[
        ('SHEET', 'Hoja A4 debajo', 'La pieza encima de un folio A4: corrige la perspectiva y saca la escala sola (recomendado)'),
        ('KNOWN', 'Medida conocida', 'Sin hoja: escribe cuánto mide la pieza en su lado mayor (foto bien de frente)')],
        default='SHEET')
    known_mm: bpy.props.FloatProperty(name='Lado mayor (mm)', default=100.0, min=1, max=2000, precision=1)
    thickness: bpy.props.FloatProperty(name='Grosor (mm)', default=3.0, min=0.2, max=200, precision=1)
    polarity: bpy.props.EnumProperty(name='Pieza', items=[
        ('AUTO', 'Auto', 'Lo que no toca el borde de la foto'),
        ('DARK', 'Oscura', 'Pieza más oscura que el fondo'),
        ('LIGHT', 'Clara', 'Pieza más clara que el fondo')], default='AUTO')
    detail_mm: bpy.props.FloatProperty(name='Detalle (mm)', default=0.25, min=0.05, max=3, precision=2,
                                       description='Cuánto se simplifica el contorno: más alto = líneas más limpias')
    circles: bpy.props.BoolProperty(name='Agujeros redondos exactos', default=True,
                                    description='Los agujeros casi redondos salen como círculos perfectos con el diámetro redondeado')
    show_photo: bpy.props.BoolProperty(name='Poner la foto debajo', default=True)
    holes_on: bpy.props.BoolProperty(name='Agujeros', default=True, description='Desmárcalo para sacar solo la silueta (figuras: los detalles claros no se vuelven agujeros)')
    show_fine: bpy.props.BoolProperty(name='Ajustes', default=False)
    report: bpy.props.StringProperty(default='')


class OBJECT_OT_photo_part(bpy.types.Operator):
    """Saca el contorno de la pieza de la foto y crea la pieza extruida"""
    bl_idname = 'object.photo_part'; bl_label = 'Crear pieza'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context)

    def execute(self, context):
        p = context.scene.photo_props
        path = Path(bpy.path.abspath(p.image)) if p.image else None
        if path is None or not path.is_file():
            self.report({'ERROR'}, 'Elige la foto (JPG o PNG).'); return {'CANCELLED'}
        try:
            res = build.analyze(path, p.mode, p.known_mm, p.polarity, p.detail_mm, p.circles, p.holes_on)
            name = common.safe_name(path.stem)
            part, size = build.make_part(context, res, name, p.thickness, 1.0, p.show_photo)
        except common.AddonError as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        lines = res['notes'] + [f'pieza de {size[0]:.1f} × {size[1]:.1f} × {p.thickness:g} mm']
        circ = [h['diameter'] for h in res['holes'] if h['type'] == 'circle']
        other = len(res['holes']) - len(circ)
        if circ:
            lines.append('agujeros: ' + ', '.join(f'Ø{d:g}' for d in sorted(circ, reverse=True)))
        if other:
            lines.append(f'{other} hueco(s) con otra forma')
        lines.append('el perfil queda oculto como curva por si quieres retocarlo')
        p.report = '\n'.join(lines)
        self.report({'INFO'}, lines[-3] if len(lines) >= 3 else lines[-1])
        return {'FINISHED'}


class OBJECT_OT_photo_rebuild(bpy.types.Operator):
    """Vuelve a crear la pieza desde el perfil (si has movido puntos de la curva o cambiado el grosor)"""
    bl_idname = 'object.photo_rebuild'; bl_label = 'Rehacer desde el perfil'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context)

    def execute(self, context):
        p = context.scene.photo_props
        obj = context.active_object
        prof = None
        if obj is not None and obj.type == 'CURVE' and obj.get('photo_part') is not None:
            prof = obj
        elif obj is not None:
            prof = next((o for o in bpy.data.objects if o.type == 'CURVE' and o.get('photo_part') == obj.name), None)
        if prof is None:
            self.report({'ERROR'}, 'Selecciona la pieza (o su perfil).'); return {'CANCELLED'}
        part = bpy.data.objects.get(prof['photo_part'])
        prof.data.extrude = p.thickness / 2
        prof.location.z = p.thickness / 2
        context.view_layer.update()
        graph = context.evaluated_depsgraph_get()
        me = build._solid_mesh(prof, graph)
        if part is None:
            part = bpy.data.objects.new(prof.name.replace('_perfil', ''), me)
            (prof.users_collection[0] if prof.users_collection else context.scene.collection).objects.link(part)
        else:
            old = part.data; part.data = me
            if old.users == 0:
                bpy.data.meshes.remove(old)
        part.matrix_world = prof.matrix_world.copy()
        prof.hide_set(True)
        for o in context.selected_objects:
            o.select_set(False)
        part.hide_set(False); part.select_set(True); context.view_layer.objects.active = part
        self.report({'INFO'}, f'Pieza rehecha con {p.thickness:g} mm de grosor')
        return {'FINISHED'}


def _wrap(layout, text, width=40):
    line = ''
    for w in text.split():
        if len(line) + len(w) + 1 > width and line:
            layout.label(text=line); line = w
        else:
            line = f'{line} {w}'.strip()
    if line:
        layout.label(text=line)


class VIEW3D_PT_photo(bpy.types.Panel):
    bl_label = 'Photo to Part'; bl_idname = 'VIEW3D_PT_photo'; bl_space_type = 'VIEW_3D'; bl_region_type = 'UI'
    bl_category = 'Photo to Part'

    def draw(self, context):
        layout = self.layout; p = context.scene.photo_props
        if common.draw_mode_warning(layout, context):
            return
        box = layout.box()
        box.prop(p, 'image')
        box.row().prop(p, 'mode', expand=True)
        if p.mode == 'KNOWN':
            box.prop(p, 'known_mm')
        else:
            t = box.column(align=True); t.scale_y = .8
            t.label(text='Pieza encima de un folio A4, foto desde')
            t.label(text='arriba con la hoja entera a la vista.')
        box.prop(p, 'thickness')
        box.prop(p, 'holes_on', text='Agujeros (desmarca para solo silueta)')
        col = box.column(); col.scale_y = 1.8
        col.operator('object.photo_part', icon='IMAGE_DATA')
        if p.report:
            col = layout.column(align=True); col.scale_y = .8
            for line in p.report.split('\n'):
                _wrap(col, '· ' + line)
            layout.operator('object.photo_rebuild', icon='FILE_REFRESH')
        box = layout.box()
        box.prop(p, 'show_fine', icon='TRIA_DOWN' if p.show_fine else 'TRIA_RIGHT', emboss=False)
        if p.show_fine:
            box.prop(p, 'polarity')
            box.prop(p, 'detail_mm')
            box.prop(p, 'holes_on')
            box.prop(p, 'circles')
            box.prop(p, 'show_photo')


classes = (PhotoProps, OBJECT_OT_photo_part, OBJECT_OT_photo_rebuild, VIEW3D_PT_photo)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.photo_props = bpy.props.PointerProperty(type=PhotoProps)


def unregister():
    del bpy.types.Scene.photo_props
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
