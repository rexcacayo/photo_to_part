# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Visión sencilla con numpy (sin OpenCV): umbral, contornos, hoja A4 y perspectiva.

Imágenes como arrays float (alto × ancho) de luminancia 0..1, fila 0 = arriba.
"""
import math

import numpy as np

A4 = (297.0, 210.0)


# --------------------------------------------------------------------------- básicos
def luminance(rgba):
    return rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114


def otsu(img, mask=None):
    v = img[mask] if mask is not None else img.ravel()
    hist, edges = np.histogram(v, bins=256, range=(0, 1))
    p = hist / max(hist.sum(), 1)
    w = np.cumsum(p)
    mu = np.cumsum(p * (edges[:-1] + edges[1:]) / 2)
    mt = mu[-1]
    with np.errstate(divide='ignore', invalid='ignore'):
        sb = (mt * w - mu) ** 2 / (w * (1 - w))
    sb = np.nan_to_num(sb)
    return float(edges[int(np.argmax(sb)) + 1])


def _shift_or(m, r=1):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def _shift_and(m, r=1):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out &= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def clean(mask, r=1):
    """Abrir y cerrar: quita puntitos sueltos y rellena poros."""
    m = _shift_or(_shift_and(mask, r), r)
    return _shift_and(_shift_or(m, r), r)


def blur(img, rounds=2):
    out = img.copy()
    for _ in range(rounds):
        out = (out + np.roll(out, 1, 0) + np.roll(out, -1, 0) + np.roll(out, 1, 1) + np.roll(out, -1, 1)) / 5
    return out


# --------------------------------------------------------------------------- contornos
def contours(mask):
    """Marching squares sobre una máscara booleana. Devuelve contornos cerrados en
    coordenadas de píxel (x, y) con fila 0 arriba."""
    m = np.pad(mask.astype(np.uint8), 1)
    a = m[:-1, :-1]; b = m[:-1, 1:]; c = m[1:, 1:]; d = m[1:, :-1]
    code = a * 8 + b * 4 + c * 2 + d
    ys, xs = np.nonzero((code > 0) & (code < 15))
    # puntos medios de los lados de cada celda: arriba, derecha, abajo, izquierda
    def mid(x, y, side):
        return {0: (x + 0.5, y), 1: (x + 1, y + 0.5), 2: (x + 0.5, y + 1), 3: (x, y + 0.5)}[side]
    table = {1: [(3, 2)], 2: [(2, 1)], 3: [(3, 1)], 4: [(1, 0)], 5: [(3, 0), (1, 2)], 6: [(2, 0)], 7: [(3, 0)],
             8: [(0, 3)], 9: [(0, 2)], 10: [(0, 1), (2, 3)], 11: [(0, 1)], 12: [(1, 3)], 13: [(1, 2)], 14: [(2, 3)]}
    nxt = {}
    for y, x in zip(ys.tolist(), xs.tolist()):
        for s0, s1 in table[int(code[y, x])]:
            p0 = mid(x, y, s0); p1 = mid(x, y, s1)
            nxt[p0] = p1
    loops, seen = [], set()
    for start in list(nxt):
        if start in seen:
            continue
        loop, p = [], start
        while p not in seen and p in nxt:
            seen.add(p); loop.append(p); p = nxt[p]
        if len(loop) >= 8 and p == start:
            loops.append(np.array(loop) - 1.0)        # quitar el borde añadido
    return loops


def area(P):
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def inside(pt, P):
    x, y = pt
    xs, ys = P[:, 0], P[:, 1]
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    cond = (ys > y) != (y2 > y)
    xi = xs + (y - ys) * (x2 - xs) / np.where(y2 - ys == 0, 1e-12, y2 - ys)
    return bool(np.count_nonzero(cond & (x < xi)) % 2)


def rdp(P, eps):
    """Simplificar un contorno cerrado (Douglas-Peucker)."""
    if len(P) < 8:
        return P
    i0 = 0
    i1 = int(np.argmax(np.linalg.norm(P - P[0], axis=1)))

    def simp(Q):
        if len(Q) < 3:
            return Q
        a, b = Q[0], Q[-1]
        ab = b - a
        L = np.linalg.norm(ab)
        if L < 1e-12:
            d = np.linalg.norm(Q - a, axis=1)
        else:
            d = np.abs(np.cross(ab, Q - a)) / L
        k = int(np.argmax(d))
        if d[k] <= eps:
            return np.array([a, b])
        left = simp(Q[:k + 1]); right = simp(Q[k:])
        return np.vstack([left[:-1], right])
    A = simp(P[i0:i1 + 1])
    B = simp(np.vstack([P[i1:], P[:1]]))
    return np.vstack([A[:-1], B[:-1]])


def smooth_loop(P, rounds=2):
    for _ in range(rounds):
        P = (np.roll(P, 1, 0) + 2 * P + np.roll(P, -1, 0)) / 4
    return P


def circle_fit(P):
    x, y = P[:, 0], P[:, 1]
    A = np.stack([x, y, np.ones_like(x)], 1)
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0))
    err = float(np.std(np.hypot(x - cx, y - cy) - r))
    return cx, cy, r, err


# --------------------------------------------------------------------------- hoja A4 y perspectiva
def quad_corners(P):
    """4 esquinas de un contorno casi rectangular (hoja vista en perspectiva)."""
    c = P.mean(0)
    p1 = P[int(np.argmax(np.linalg.norm(P - c, axis=1)))]
    p2 = P[int(np.argmax(np.linalg.norm(P - p1, axis=1)))]
    d = p2 - p1
    side = np.cross(d, P - p1)
    p3 = P[int(np.argmax(side))]
    p4 = P[int(np.argmin(side))]
    Q = np.array([p1, p3, p2, p4])
    # orden en el sentido de las agujas empezando arriba a la izquierda
    ang = np.arctan2(Q[:, 1] - Q[:, 1].mean(), Q[:, 0] - Q[:, 0].mean())
    Q = Q[np.argsort(ang)]
    k = int(np.argmin(Q.sum(1)))
    return np.roll(Q, -k, 0)


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _u, _s, vt = np.linalg.svd(np.array(A, float))
    H = vt[-1].reshape(3, 3)
    return H / H[2, 2]


def warp(img, H_out_to_in, w, h):
    """Imagen de salida (h × w) muestreando la de entrada con interpolación bilineal."""
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    pts = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5, np.ones(xx.size)])
    q = H_out_to_in @ pts
    x = q[0] / q[2] - 0.5; y = q[1] / q[2] - 0.5
    H, W = img.shape[:2]
    x0 = np.clip(np.floor(x).astype(int), 0, W - 2); y0 = np.clip(np.floor(y).astype(int), 0, H - 2)
    fx = np.clip(x - x0, 0, 1); fy = np.clip(y - y0, 0, 1)
    if img.ndim == 3:
        fx = fx[:, None]; fy = fy[:, None]
    out = (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) +
           img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
    return out.reshape((h, w) + img.shape[2:])


def find_sheet(lum):
    """Contorno de la hoja (la zona clara más grande). Devuelve las 4 esquinas o None."""
    t = otsu(blur(lum, 2))
    paper = clean(lum > t, 2)
    loops = [L for L in contours(paper)]
    if not loops:
        return None
    big = max(loops, key=lambda L: abs(area(L)))
    if abs(area(big)) < 0.12 * lum.size:
        return None
    Q = quad_corners(big)
    # que de verdad sea un cuadrilátero: el contorno ocupa casi todo el cuadrilátero
    if abs(area(big)) < 0.85 * abs(area(Q)):
        return None
    return Q


# --------------------------------------------------------------------------- la pieza
def part_mask(lum, margin_px=0, polarity='AUTO'):
    """Máscara de la pieza: la clase (clara u oscura) que no toca el borde de la foto."""
    g = blur(lum, 1)
    inner = np.zeros_like(g, bool)
    inner[margin_px:g.shape[0] - margin_px, margin_px:g.shape[1] - margin_px] = True
    t = otsu(g, inner)
    dark = g < t
    if polarity == 'DARK':
        m = dark
    elif polarity == 'LIGHT':
        m = ~dark
    else:
        border = np.ones_like(g, bool); border[margin_px + 3:-margin_px - 3, margin_px + 3:-margin_px - 3] = False
        m = dark if dark[border & inner].mean() < 0.5 or not (border & inner).any() else ~dark
    m &= inner
    return clean(m, 1)


def outline(mask, min_area_px, min_hole_px=None):
    """Contorno exterior de la pieza (el mayor que no toca el borde) y sus agujeros."""
    min_hole_px = min_area_px * 0.05 if min_hole_px is None else min_hole_px
    loops = [L for L in contours(mask) if abs(area(L)) >= min_hole_px]
    if not loops:
        return None, []
    H, W = mask.shape

    def touches(L):
        return L[:, 0].min() <= 1 or L[:, 1].min() <= 1 or L[:, 0].max() >= W - 2 or L[:, 1].max() >= H - 2
    big = [L for L in loops if abs(area(L)) >= min_area_px]
    if not big:
        return None, []
    cands = [L for L in big if not touches(L)] or big
    outer = max(cands, key=lambda L: abs(area(L)))
    holes = [L for L in loops if L is not outer and abs(area(L)) < abs(area(outer)) and inside(L[0], outer)
             and not any(L2 is not outer and L2 is not L and abs(area(L2)) > abs(area(L)) and inside(L[0], L2)
                         and inside(L2[0], outer) for L2 in loops)]
    return outer, holes


def min_rect(P):
    """Rectángulo mínimo que envuelve el contorno (largo, ancho, ángulo): prueba las
    direcciones de los lados del contorno simplificado."""
    Q = rdp(P, max(1.0, 0.003 * float(np.ptp(P, axis=0).max())))
    best = None
    for k in range(len(Q)):
        d = Q[(k + 1) % len(Q)] - Q[k]
        L = np.linalg.norm(d)
        if L < 1e-9:
            continue
        u = d / L; v = np.array([-u[1], u[0]])
        a, b = np.ptp(P @ u), np.ptp(P @ v)
        if best is None or a * b < best[0] * best[1]:
            best = (a, b, math.atan2(u[1], u[0]))
    a, b, ang = best
    return (max(a, b), min(a, b), ang)
