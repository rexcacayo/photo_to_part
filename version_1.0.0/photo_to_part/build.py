# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Photo to Part dentro de Blender: de la foto al perfil y a la pieza extruida."""
import math
from pathlib import Path

import bpy
import numpy as np

from . import common, vision

PPM = 4.0            # píxeles por mm de la foto enderezada (hoja A4: 1188 × 840)
MAX_SIDE = 1600      # las fotos del móvil se reducen a esto para ir rápido


def _nice(d):
    for step in (1.0, 0.5):
        q = round(d / step) * step
        if abs(q - d) <= max(0.08, d * 0.015):
            return q
    return round(d, 1)


def load_image(path):
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        if not w or not h:
            raise common.AddonError('No se pudo leer la foto.')
        k = min(1.0, MAX_SIDE / max(w, h))
        if k < 1.0:
            img.scale(max(1, int(w * k)), max(1, int(h * k)))
            w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
    finally:
        bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1].copy()          # fila 0 = arriba


def analyze(path, mode='SHEET', known_mm=100.0, polarity='AUTO', detail_mm=0.25, circles=True):
    """Devuelve dict con el contorno exterior y los agujeros en mm (y hacia arriba), la foto
    enderezada y notas."""
    rgba = load_image(path)
    lum = vision.luminance(rgba)
    notes = []
    if mode == 'SHEET':
        Q = vision.find_sheet(lum)
        if Q is None:
            raise common.AddonError('No encuentro la hoja: haz la foto desde arriba con la hoja A4 entera y '
                                    'bien iluminada, o usa «Medida conocida».')
        e1 = np.linalg.norm(Q[1] - Q[0]) + np.linalg.norm(Q[2] - Q[3])
        e2 = np.linalg.norm(Q[3] - Q[0]) + np.linalg.norm(Q[2] - Q[1])
        sw, sh = (vision.A4 if e1 >= e2 else vision.A4[::-1])
        W, H = int(sw * PPM), int(sh * PPM)
        dst = np.array([[0, 0], [W, 0], [W, H], [0, H]], float)
        Hm = vision.homography(dst, Q)                     # salida → foto
        flat = vision.warp(rgba, Hm, W, H)
        lumf = vision.luminance(flat)
        mask = vision.part_mask(lumf, margin_px=int(6 * PPM), polarity=polarity)
        scale = 1.0 / PPM
        notes.append('hoja A4 encontrada: perspectiva corregida')
    else:
        flat = rgba
        mask = vision.part_mask(lum, margin_px=2, polarity=polarity)
        scale = None
    outer, holes = vision.outline(mask, min_area_px=max(50, mask.size * 0.0005))
    if outer is None:
        raise common.AddonError('No distingo la pieza del fondo. Pon la pieza sobre un fondo liso que contraste '
                                '(oscura sobre papel blanco va perfecto).')
    if scale is None:
        # lado mayor de la pieza (en su propia dirección, no la de la foto)
        span = vision.min_rect(outer)[0]
        scale = known_mm / max(span, 1e-9)
        notes.append(f'escala por la medida conocida: {known_mm:g} mm en el lado mayor')
    Himg = flat.shape[0]

    def to_mm(P):
        Q = np.column_stack([P[:, 0], Himg - P[:, 1]]) * scale      # y hacia arriba
        return Q

    eps = max(detail_mm, 0.05) / scale
    out_mm = to_mm(vision.rdp(vision.smooth_loop(outer, 2), eps))
    hole_list = []
    for L in holes:
        P = to_mm(vision.smooth_loop(L, 2))
        if circles:
            cx, cy, r, err = vision.circle_fit(P)
            if err < max(0.08, r * 0.04) and len(L) > 12:
                d = _nice(2 * r)
                hole_list.append({'type': 'circle', 'center': (cx, cy), 'diameter': d})
                continue
        hole_list.append({'type': 'poly', 'points': to_mm(vision.rdp(vision.smooth_loop(L, 2), eps))})
    return {'outer': out_mm, 'holes': hole_list, 'flat': flat, 'scale': scale, 'notes': notes}


def _circle(cx, cy, d, n=None):
    r = d / 2
    n = n or max(24, min(128, int(math.pi * d / 0.5)))
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


def make_part(context, res, name, thickness, mm_per_bu=1.0, show_photo=True):
    """Crea el perfil (curva editable, oculta) y la pieza (malla cerrada)."""
    outer = res['outer']
    lo = outer.min(0)
    hi = outer.max(0)
    center = (lo + hi) / 2
    loops = [outer - center]
    for h in res['holes']:
        if h['type'] == 'circle':
            loops.append(_circle(*h['center'], h['diameter']) - center)
        else:
            loops.append(h['points'] - center)
    cu = bpy.data.curves.new(f'{name}_perfil', 'CURVE')
    cu.dimensions = '2D'
    cu.fill_mode = 'BOTH'
    cu.resolution_u = 1
    for L in loops:
        sp = cu.splines.new('POLY')
        sp.points.add(len(L) - 1)
        for p, (x, y) in zip(sp.points, L):
            p.co = (x / mm_per_bu, y / mm_per_bu, 0.0, 1.0)
        sp.use_cyclic_u = True
    cu.extrude = thickness / 2 / mm_per_bu
    col = context.collection or context.scene.collection
    prof = bpy.data.objects.new(f'{name}_perfil', cu)
    col.objects.link(prof)
    prof.location.z = thickness / 2 / mm_per_bu
    context.view_layer.update()
    graph = context.evaluated_depsgraph_get()
    me = _solid_mesh(prof, graph)
    if not len(me.polygons):
        bpy.data.meshes.remove(me)
        raise common.AddonError('El contorno se cruza consigo mismo: prueba con más «Detalle (mm)».')
    part = bpy.data.objects.new(name, me)
    col.objects.link(part)
    part.location.z = thickness / 2 / mm_per_bu
    prof.hide_set(True); prof.hide_render = True
    prof['photo_part'] = part.name
    part[common.UNIT_PROP] = 'MM' if mm_per_bu == 1.0 else 'M'
    if show_photo:
        _photo_plane(context, res, name, center, mm_per_bu, col)
    for o in context.selected_objects:
        o.select_set(False)
    part.select_set(True)
    context.view_layer.objects.active = part
    return part, (hi - lo)


def _solid_mesh(prof, graph):
    """Malla cerrada desde la curva extruida (Blender deja tapas y laterales sin soldar)."""
    import bmesh
    me = bpy.data.meshes.new_from_object(prof.evaluated_get(graph), depsgraph=graph)
    bm = bmesh.new(); bm.from_mesh(me)
    try:
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.to_mesh(me)
    finally:
        bm.free()
    me.update()
    return me


def _photo_plane(context, res, name, center, mm_per_bu, col):
    """La foto (ya enderezada) a escala, debajo de la pieza, para comparar."""
    flat = res['flat']
    h, w = flat.shape[:2]
    img = bpy.data.images.new(f'{name}_foto', w, h, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(flat[::-1]).astype(np.float32).ravel())
    img.pack()
    emp = bpy.data.objects.new(f'{name}_foto', None)
    emp.empty_display_type = 'IMAGE'
    emp.data = img
    s = res['scale']
    emp.empty_display_size = max(w, h) * s / mm_per_bu
    emp.empty_image_offset = (-0.5, -0.5)
    emp.location = ((w * s / 2 - center[0]) / mm_per_bu, (h * s / 2 - center[1]) / mm_per_bu, -0.05 / mm_per_bu)
    emp.show_in_front = False
    emp.color = (1, 1, 1, 0.6)
    emp.use_empty_image_alpha = True
    emp['showcase'] = False
    col.objects.link(emp)
    return emp
