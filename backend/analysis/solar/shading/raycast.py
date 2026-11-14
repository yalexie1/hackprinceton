"""SHD-01 beam shading fraction and SHD-02 sky view factor by ray casting.

Ray-triangle test: Moller-Trumbore, vectorised over rays and triangles in NumPy and
processed in chunks so memory stays bounded. A ray is blocked if it hits any triangle
at a distance t > 1e-6 m (SHD-01).
"""
from __future__ import annotations

import math

import numpy as np

# --- constants destined for backend/config.py (kept local, workplan 2.6) ---
LIFT_M = 0.02                 # SHD-01: ray origin lifted off the panel along its normal (design choice)
T_MIN_M = 1e-6                # SHD-01: minimum hit distance
SVF_N_EL = 30                 # SHD-02: default elevation cells (0.0009 worst error, measured in the entry)
SVF_N_AZ = 120                # SHD-02: default azimuth cells
_EPS_DET = 1e-12              # parallel-ray guard in Moller-Trumbore
_CHUNK = 2_000_000            # rays x triangles evaluated per NumPy block


def _cull(origins: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Every ray here points upward (sun or sky above the horizon): drop triangles
    lying entirely below the lowest origin, which no such ray can reach."""
    if len(tris) == 0 or len(origins) == 0:
        return tris
    return tris[tris[:, :, 2].max(axis=1) > origins[:, 2].min()]


def rays_blocked(origins, directions, triangles) -> np.ndarray:
    """Boolean per ray: does the ray hit any triangle at t > T_MIN_M?

    ``origins`` and ``directions`` are (R, 3) (directions need not be unit, the test
    is on the sign of t only); ``triangles`` is (T, 3, 3).
    """
    o = np.asarray(origins, float).reshape(-1, 3)
    d = np.asarray(directions, float).reshape(-1, 3)
    tris = np.asarray(triangles, float).reshape(-1, 3, 3)
    out = np.zeros(len(o), dtype=bool)
    if len(o) == 0 or len(tris) == 0:
        return out
    v0 = tris[:, 0]
    e1 = tris[:, 1] - v0
    e2 = tris[:, 2] - v0
    step = max(1, _CHUNK // len(tris))
    for i in range(0, len(o), step):
        oc, dc = o[i:i + step, None, :], d[i:i + step, None, :]
        p = np.cross(dc, e2[None])                       # (r, T, 3)
        det = np.einsum("rtk,tk->rt", p, e1)
        ok = np.abs(det) > _EPS_DET
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = oc - v0[None]
        u = np.einsum("rtk,rtk->rt", tv, p) * inv
        q = np.cross(tv, e1[None])
        v = np.einsum("rtk,rk->rt", q, dc[:, 0, :]) * inv
        t = np.einsum("rtk,tk->rt", q, e2) * inv
        hit = ok & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > T_MIN_M)
        out[i:i + step] = hit.any(axis=1)
    return out


def beam_shading_fraction(sample_points_enu, normal_enu, sun_vector_enu, scene_mesh) -> float:
    """SHD-01 for one hour. f_b = share of the K sample points whose ray to the sun is blocked.

    Returns 0 when the sun is below the horizon or behind the panel (no beam to shade).
    """
    f = beam_shading_fractions(sample_points_enu, normal_enu, np.asarray(sun_vector_enu, float)[None], scene_mesh)
    return float(f[0])


def beam_shading_fractions(sample_points_enu, normal_enu, sun_vectors_enu, scene_mesh) -> np.ndarray:
    """SHD-01 for many hours at once; ``sun_vectors_enu`` (H, 3) -> f_b (H,)."""
    pts = np.asarray(sample_points_enu, float).reshape(-1, 3)
    n = np.asarray(normal_enu, float)
    s = np.asarray(sun_vectors_enu, float).reshape(-1, 3)
    fb = np.zeros(len(s))
    lit = (s[:, 2] > 0.0) & (s @ n > 0.0)                 # theta_z < 90 and cos(theta) > 0
    if not lit.any() or len(pts) == 0:
        return fb
    origins = pts + LIFT_M * n
    tris = _cull(origins, np.asarray(scene_mesh, float).reshape(-1, 3, 3))
    if len(tris) == 0:
        return fb
    sl = s[lit]
    k = len(origins)
    o = np.repeat(origins[None], len(sl), axis=0).reshape(-1, 3)
    d = np.repeat(sl[:, None, :], k, axis=1).reshape(-1, 3)
    blocked = rays_blocked(o, d, tris).reshape(len(sl), k)
    fb[lit] = blocked.mean(axis=1)
    return fb


def _sky_grid(n_el: int, n_az: int):
    d_el, d_az = (math.pi / 2) / n_el, (2 * math.pi) / n_az
    el = (np.arange(n_el) + 0.5) * d_el
    az = (np.arange(n_az) + 0.5) * d_az
    E, A = np.meshgrid(el, az, indexing="ij")
    w = np.stack([np.cos(E) * np.sin(A), np.cos(E) * np.cos(A), np.sin(E)], axis=-1).reshape(-1, 3)
    domega = (np.cos(E) * d_el * d_az).reshape(-1)
    return w, domega


def sky_view_factors(point_enu, normal_enu, scene_mesh, n_el: int = SVF_N_EL,
                     n_az: int = SVF_N_AZ) -> tuple[float, float]:
    """SHD-02 quadrature. Returns (SVF with the scene, SVF of the open sky on the same grid)."""
    n = np.asarray(normal_enu, float)
    w, dom = _sky_grid(n_el, n_az)
    cos_w = np.maximum(0.0, w @ n)
    keep = cos_w > 0.0
    w, dom, cos_w = w[keep], dom[keep], cos_w[keep]
    origin = np.asarray(point_enu, float).reshape(3) + LIFT_M * n
    tris = _cull(origin[None], np.asarray(scene_mesh, float).reshape(-1, 3, 3))
    vis = ~rays_blocked(np.repeat(origin[None], len(w), axis=0), w, tris)
    open_svf = float((cos_w * dom).sum() / math.pi)
    return float((vis * cos_w * dom).sum() / math.pi), open_svf


def sky_view_factor(point_enu, normal_enu, scene_mesh, n_el: int = SVF_N_EL, n_az: int = SVF_N_AZ) -> float:
    """SHD-02 tool function. SVF = (1/pi) sum V_j max(0, n.w_j) dOmega_j."""
    return sky_view_factors(point_enu, normal_enu, scene_mesh, n_el, n_az)[0]


def diffuse_shading_factor(svf: float, tilt_deg: float) -> float:
    """SHD-02 tool function. S_d = SVF / ((1 + cos beta) / 2)."""
    return float(svf) / ((1.0 + math.cos(math.radians(tilt_deg))) / 2.0)
