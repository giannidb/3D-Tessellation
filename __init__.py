"""
3D Tessellation Addon v2.3.0 for Blender 5.x.

Provides two volumetric tessellation algorithms inside arbitrary meshes:

- **Delaunay 3D** – tetrahedra-based tessellation, ideal for FEM / physics
  simulations.
- **Voronoi Boolean** – Cell Fracture-like approach that intersects each
  Voronoi cell with the source mesh via a boolean modifier, guaranteeing
  perfect surface conformance.

Additional features:
- Weight-aware seed-point generation and Lloyd relaxation.
- Adaptive geometry cleanup (merge doubles + dissolve planar faces).
- Smooth SFD geometry-nodes modifier for edge smoothing.
"""

from __future__ import annotations

# Standard-library imports must precede third-party and bpy imports.
import importlib.util
import math
import os
import subprocess
import sys
import traceback
from collections.abc import Callable
from typing import Any, Optional

bl_info = {
    "name": "3D Tessellation (Delaunay & Voronoi)",
    "author": "Ergo Cogito Design",
    "version": (2, 3, 0),
    "blender": (5, 0, 1),
    "location": "View3D > Sidebar > Tessellation",
    "description": (
        "Complete 3D tessellation suite: Delaunay + Voronoi Boolean (Cell Fracture)"
    ),
    "category": "Mesh",
}

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

#: Tolerance used for BVH proximity tests and ray-cast offsets.
_EPSILON: float = 1e-4

#: Multiplier above which the normal-dot test alone is trusted.
_EPSILON_FACTOR: int = 10

# ---------------------------------------------------------------------------
# scipy installation helper
# ---------------------------------------------------------------------------


def ensure_scipy_installed() -> bool:
    """Verify that *scipy* is importable, installing it when absent.

    Installation targets the user site-packages directory so that no
    administrator privileges are required.  On Windows, Blender's embedded
    Python may still need the user to run Blender as Administrator; a clear
    diagnostic message is printed in that case.

    Returns:
        ``True`` if scipy is (or becomes) importable, ``False`` otherwise.
    """
    if importlib.util.find_spec("scipy") is not None:
        return True

    python_exe = sys.executable

    try:
        try:
            import pip  # noqa: F401
        except ImportError:
            print("Installing pip via ensurepip …")
            subprocess.check_call([python_exe, "-m", "ensurepip", "--default-pip"])
            subprocess.check_call(
                [python_exe, "-m", "pip", "install", "--upgrade", "pip"]
            )

        print("Installing scipy in user directory …  (this may take a minute)")
        subprocess.check_call(
            [python_exe, "-m", "pip", "install", "scipy", "--user"]
        )

        importlib.invalidate_caches()

        import site

        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.insert(0, user_site)
            print(f"Added user site-packages to path: {user_site}")

        if importlib.util.find_spec("scipy") is None:
            raise ImportError(
                "scipy installation completed but module still not found."
            )

        print("scipy installed successfully.  Please restart Blender.")
        return True

    except subprocess.CalledProcessError as exc:
        print(f"Failed to install scipy: {exc}")
        print(
            "\nTroubleshooting:\n"
            "  On Windows with Blender in Program Files:\n"
            "    1. Run Blender as Administrator, OR\n"
            "    2. Install scipy manually from the Command Prompt:\n"
            f'       "{python_exe}" -m pip install scipy --user\n'
            "  Then restart Blender."
        )
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to install scipy: {exc}")
        return False


scipy_available: bool = ensure_scipy_installed()

import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402
from bpy.props import (  # noqa: E402
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup  # noqa: E402

if scipy_available:
    from scipy.spatial import ConvexHull, Delaunay, Voronoi  # noqa: E402


# ---------------------------------------------------------------------------
# Lloyd relaxation — weight-aware
# ---------------------------------------------------------------------------


def lloyd_relaxation_3d(
    points: np.ndarray,
    bounds: tuple[tuple[float, float], ...],
    iterations: int = 3,
    density_weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Apply weight-aware Lloyd relaxation to a set of 3-D seed points.

    High-weight points move less, resulting in smaller local cells.
    Low-weight points move normally, producing larger cells.

    Args:
        points: ``(N, 3)`` array of seed coordinates.
        bounds: Sequence of ``(min, max)`` pairs for each axis, used to
            clamp relaxed positions inside the bounding volume.
        iterations: Number of relaxation passes.
        density_weights: Per-point weight array of shape ``(N,)``.
            Defaults to uniform weights when ``None``.

    Returns:
        Relaxed ``(N, 3)`` coordinate array.
    """
    if not scipy_available:
        print("Warning: scipy unavailable — skipping Lloyd relaxation.")
        return points

    points = np.array(points, dtype=np.float64)

    if density_weights is None:
        density_weights = np.ones(len(points))
    else:
        density_weights = np.array(density_weights, dtype=np.float64)

    for _ in range(iterations):
        vor = Voronoi(points)
        new_points: list[np.ndarray] = []

        for idx in range(len(points)):
            region_idx = vor.point_region[idx]
            region = vor.regions[region_idx]

            if -1 in region or len(region) == 0:
                new_points.append(points[idx])
                continue

            centroid = np.mean(vor.vertices[region], axis=0)

            max_weight = np.max(density_weights)
            normalized_w = density_weights[idx] / (max_weight + 0.01)
            movement = 0.3 + 0.7 * (1.0 - normalized_w)

            pos = points[idx] + (centroid - points[idx]) * movement
            pos[0] = np.clip(pos[0], bounds[0][0], bounds[0][1])
            pos[1] = np.clip(pos[1], bounds[1][0], bounds[1][1])
            pos[2] = np.clip(pos[2], bounds[2][0], bounds[2][1])

            new_points.append(pos)

        points = np.array(new_points)

    return points


# ---------------------------------------------------------------------------
# Base tessellator class
# ---------------------------------------------------------------------------


class Tessellator3D:
    """Common foundation for all 3-D tessellation strategies.

    Builds a bmesh in **world space** from the given object so that every
    downstream operation (bounding-box queries, inside tests, BVH casts)
    works consistently regardless of the object's location, rotation or
    scale — without modifying the original mesh data.
    """

    def __init__(self, obj: Any) -> None:
        """Initialise the tessellator for *obj*.

        Args:
            obj: A Blender mesh object (``bpy.types.Object`` with
                ``type == 'MESH'``).
        """
        self.obj = obj
        self.mesh = obj.data
        self.bm: bmesh.types.BMesh = bmesh.new()
        self.bm.from_mesh(self.mesh)
        # Transform to world space so all downstream operations are
        # consistent with what the user sees in the viewport.
        # This does NOT alter the source object or its mesh data.
        self.bm.transform(obj.matrix_world)
        self.bm.verts.ensure_lookup_table()
        self.bm.edges.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        self.bvh: BVHTree = BVHTree.FromBMesh(self.bm)

    # ------------------------------------------------------------------
    # Weight map
    # ------------------------------------------------------------------

    def get_vertex_weight_map(
        self,
        use_weight_paint: bool = False,
        group_name: str = "",
    ) -> dict[int, float]:
        """Build a per-vertex weight dictionary.

        Args:
            use_weight_paint: When ``True``, read weights from a vertex
                group rather than returning uniform values.
            group_name: Name of the vertex group to read.

        Returns:
            Mapping from vertex index to weight in ``[0.05, 1.0]``.
        """
        weight_map: dict[int, float] = {}

        if use_weight_paint and group_name and group_name in self.obj.vertex_groups:
            group_index = self.obj.vertex_groups[group_name].index
            dvert_lay = self.bm.verts.layers.deform.verify()

            has_weights = False
            for vert in self.bm.verts:
                dvert = vert[dvert_lay]
                w = dvert.get(group_index, 0.0) if group_index in dvert else 0.0
                weight_map[vert.index] = w + 0.05
                if w > 0:
                    has_weights = True

            if has_weights:
                return weight_map

            print("Warning: vertex group is empty — using uniform weights.")

        for vert in self.bm.verts:
            weight_map[vert.index] = 1.0

        return weight_map

    # ------------------------------------------------------------------
    # Inside tests
    # ------------------------------------------------------------------

    def is_point_inside_mesh(self, point: Vector, epsilon: float = _EPSILON) -> bool:
        """Return ``True`` when *point* lies inside the mesh volume.

        Uses a combined BVH normal-dot test and ray-casting majority vote
        for robustness near surface boundaries.

        Args:
            point: Query point in world space.
            epsilon: Proximity threshold — points closer than
                ``epsilon * _EPSILON_FACTOR`` to the surface are resolved
                via ray casting only.

        Returns:
            ``True`` if the point is inside the closed mesh volume.
        """
        location, normal, _face_index, distance = self.bvh.find_nearest(point)

        if location is None:
            return False

        # Points very close to the surface are unreliable for the
        # normal-dot test; fall back to ray casting exclusively.
        if distance < epsilon * _EPSILON_FACTOR:
            return self._is_inside_ray_casting(point)

        to_point = point - location
        is_inside_normal = to_point.dot(normal) < -epsilon
        is_inside_ray = self._is_inside_ray_casting(point)
        return is_inside_normal and is_inside_ray

    def _is_inside_ray_casting(self, point: Vector) -> bool:
        """Majority-vote ray-casting inside test along three cardinal axes.

        Casts a ray along +X, +Y and +Z and counts intersections.  An odd
        count for at least two axes indicates the point is inside.

        Args:
            point: Query point in world space.

        Returns:
            ``True`` when the majority vote is *inside*.
        """
        directions = (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
        inside_count = 0

        for direction in directions:
            intersections = 0
            current = point.copy()

            for _ in range(100):  # guard against infinite loops
                hit_loc, _hit_norm, _hit_idx, _hit_dist = self.bvh.ray_cast(
                    current, direction
                )
                if hit_loc is None:
                    break
                intersections += 1
                current = hit_loc + direction * _EPSILON

            if intersections % 2 == 1:
                inside_count += 1

        return inside_count >= 2

    # ------------------------------------------------------------------
    # Bounding box
    # ------------------------------------------------------------------

    def get_mesh_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the axis-aligned bounding box of the (world-space) bmesh.

        Returns:
            A pair ``(min_co, max_co)`` of ``(3,)`` numpy float64 arrays.
        """
        coords = np.array([v.co for v in self.bm.verts], dtype=np.float64)
        return coords.min(axis=0), coords.max(axis=0)

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Release bmesh memory.  Call when the tessellator is no longer needed."""
        self.bm.free()


# ---------------------------------------------------------------------------
# Delaunay tessellator
# ---------------------------------------------------------------------------


class DelaunayTessellator(Tessellator3D):
    """Delaunay 3-D tessellation — tetrahedra-based interior structure."""

    def get_all_volume_points(
        self,
        weight_map: dict[int, float],
        base_samples: int,
        use_original_verts: bool,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[Vector]:
        """Sample points inside the mesh volume for Delaunay input.

        Points are distributed with acceptance-rejection sampling biased by
        the per-vertex weight map.

        Args:
            weight_map: Per-vertex weight dictionary from
                :meth:`get_vertex_weight_map`.
            base_samples: Target number of randomly sampled interior points.
            use_original_verts: When ``True``, prepend all mesh vertices to
                the sample set.
            progress_callback: Optional callable invoked with a status string
                after each milestone.

        Returns:
            List of :class:`~mathutils.Vector` points in world space.
        """
        min_co, max_co = self.get_mesh_bounds()
        min_v = Vector(min_co.tolist())
        max_v = Vector(max_co.tolist())

        points: list[Vector] = []

        if use_original_verts:
            for vert in self.bm.verts:
                points.append(vert.co.copy())
            if progress_callback:
                progress_callback(f"Added {len(points)} original vertices.")

        if progress_callback:
            progress_callback("Generating internal points …")

        total_attempts = base_samples * 5
        internal_added = 0
        max_weight = max(weight_map.values())

        for attempt in range(total_attempts):
            if progress_callback and attempt % 100 == 0:
                progress_callback(
                    f"Attempts: {attempt}/{total_attempts}, "
                    f"points: {internal_added}"
                )

            test_point = Vector([
                np.random.uniform(min_v.x, max_v.x),
                np.random.uniform(min_v.y, max_v.y),
                np.random.uniform(min_v.z, max_v.z),
            ])

            if self.is_point_inside_mesh(test_point):
                nearest = min(
                    self.bm.verts,
                    key=lambda v: (v.co - test_point).length,
                )
                local_density = weight_map[nearest.index] / max_weight

                if np.random.random() < local_density:
                    points.append(test_point)
                    internal_added += 1

            if internal_added >= base_samples:
                break

        if progress_callback:
            progress_callback(f"Total points: {len(points)}.")

        return points

    def perform_tessellation(
        self,
        points: list[Vector],
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[tuple[Any, np.ndarray]]:
        """Run scipy Delaunay on *points*.

        Args:
            points: Interior sample points (world space).
            progress_callback: Optional status callback.

        Returns:
            ``(tri, points_array)`` on success, ``None`` when fewer than
            4 points are provided.
        """
        if len(points) < 4:
            return None

        points_array = np.array([list(p) for p in points])

        if progress_callback:
            progress_callback(f"Computing Delaunay on {len(points)} points …")

        return Delaunay(points_array), points_array

    def filter_internal_simplices(
        self,
        tri: Any,
        points_array: np.ndarray,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[np.ndarray]:
        """Keep only tetrahedra whose centroid lies inside the mesh.

        Args:
            tri: :class:`scipy.spatial.Delaunay` triangulation.
            points_array: Coordinate array used to build *tri*.
            progress_callback: Optional status callback.

        Returns:
            List of simplex index arrays (shape ``(4,)``) for interior
            tetrahedra.
        """
        if progress_callback:
            progress_callback("Filtering internal tetrahedra …")

        internal: list[np.ndarray] = []

        for simplex in tri.simplices:
            centroid = Vector(np.mean(points_array[simplex], axis=0).tolist())
            if self.is_point_inside_mesh(centroid):
                internal.append(simplex)

        if progress_callback:
            progress_callback(
                f"Found {len(internal)}/{len(tri.simplices)} internal tetrahedra."
            )

        return internal

    def extract_surface_faces(
        self,
        simplices: list[np.ndarray],
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[tuple[int, ...]]:
        """Extract interior triangular faces shared by exactly two tetrahedra.

        Args:
            simplices: Interior simplex list from
                :meth:`filter_internal_simplices`.
            progress_callback: Optional status callback.

        Returns:
            List of sorted 3-tuples of vertex indices.
        """
        if progress_callback:
            progress_callback("Extracting surface …")

        face_count: dict[tuple[int, ...], int] = {}

        for simplex in simplices:
            s = simplex
            for tri_face in (
                (s[0], s[1], s[2]),
                (s[0], s[1], s[3]),
                (s[0], s[2], s[3]),
                (s[1], s[2], s[3]),
            ):
                key = tuple(sorted(tri_face))
                face_count[key] = face_count.get(key, 0) + 1

        interior_faces = [f for f, cnt in face_count.items() if cnt == 2]

        if progress_callback:
            progress_callback(f"Found {len(interior_faces)} interior faces.")

        return interior_faces

    def create_mesh(
        self,
        points_array: np.ndarray,
        faces: list[tuple[int, ...]],
        name: str = "Delaunay_Tessellation",
    ) -> tuple[Any, list[tuple[float, ...]], list[tuple[int, ...]]]:
        """Create a Blender mesh object from a Delaunay result.

        Args:
            points_array: Vertex coordinates ``(N, 3)``.
            faces: Triangle index tuples.
            name: Name for the new mesh and object.

        Returns:
            A 3-tuple ``(obj, vertices, faces)`` where *obj* is the new
            Blender object linked into the active collection.
        """
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)

        vertices = [tuple(p) for p in points_array]
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        return obj, vertices, faces


# ---------------------------------------------------------------------------
# Voronoi Boolean tessellator — Cell Fracture approach
# ---------------------------------------------------------------------------


class VoronoiBooleanTessellator(Tessellator3D):
    """Cell Fracture-like Voronoi tessellation via boolean intersection.

    Algorithm:

    1. Generate *N* seed points uniformly distributed inside the mesh.
    2. Optionally apply weight-aware Lloyd relaxation.
    3. Compute a bounded 3-D Voronoi diagram (ghost boundary points keep
       all interior regions finite).
    4. For each Voronoi region:

       a. Build a watertight convex-hull mesh of the cell.
       b. Boolean-INTERSECT the hull with a copy of the source mesh.
       c. The resulting cell conforms exactly to the original surface.

    5. Join all cells into a single output mesh object.
    """

    # ------------------------------------------------------------------
    # Seed generation
    # ------------------------------------------------------------------

    def generate_seed_points(
        self,
        n_seeds: int,
        weight_map: Optional[dict[int, float]] = None,
        use_weight_paint: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> list[list[float]]:
        """Sample *n_seeds* points uniformly inside the mesh volume.

        When *weight_map* is provided and *use_weight_paint* is ``True``,
        denser regions (higher weight) are preferred via acceptance-rejection.

        Args:
            n_seeds: Desired number of seed points.
            weight_map: Optional per-vertex weight dict.
            use_weight_paint: Activate weight-biased sampling.
            progress_callback: Optional status callback.

        Returns:
            List of ``[x, y, z]`` seed coordinates.
        """
        if progress_callback:
            progress_callback(f"Generating {n_seeds} seed points inside mesh …")

        min_co, max_co = self.get_mesh_bounds()
        seed_points: list[list[float]] = []
        attempts = 0
        max_attempts = n_seeds * 50

        while len(seed_points) < n_seeds and attempts < max_attempts:
            p = Vector(np.random.uniform(min_co, max_co).tolist())

            if self.is_point_inside_mesh(p):
                if use_weight_paint and weight_map:
                    nearest = min(
                        self.bm.verts,
                        key=lambda v: (v.co - p).length,
                    )
                    w = weight_map.get(nearest.index, 1.0)
                    max_w = max(weight_map.values()) if weight_map else 1.0
                    if np.random.random() > (w / (max_w + 1e-6)):
                        attempts += 1
                        continue

                seed_points.append([p.x, p.y, p.z])

            attempts += 1

        if progress_callback:
            progress_callback(
                f"Generated {len(seed_points)}/{n_seeds} seed points "
                f"({attempts} attempts)."
            )

        return seed_points

    # ------------------------------------------------------------------
    # Voronoi computation
    # ------------------------------------------------------------------

    def compute_voronoi_bounded(
        self,
        seed_points: list[list[float]],
        use_lloyd: bool = False,
        lloyd_iterations: int = 3,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> tuple[Any, np.ndarray]:
        """Compute a bounded 3-D Voronoi diagram from *seed_points*.

        Ghost boundary points are added outside the bounding box so that
        every interior seed produces a finite Voronoi region — the same
        technique used by Blender's built-in Cell Fracture.

        Args:
            seed_points: Interior seed coordinates.
            use_lloyd: Apply Lloyd relaxation before computing the diagram.
            lloyd_iterations: Number of relaxation passes.
            progress_callback: Optional status callback.

        Returns:
            ``(vor, seed_array)`` where *vor* is a
            :class:`scipy.spatial.Voronoi` object and *seed_array* is the
            ``(N, 3)`` array of (possibly relaxed) seed coordinates.
        """
        if progress_callback:
            progress_callback("Computing bounded 3-D Voronoi …")

        min_co, max_co = self.get_mesh_bounds()
        center = (min_co + max_co) / 2.0
        size = max_co - min_co

        seed_array = np.array(seed_points, dtype=np.float64)

        if use_lloyd and lloyd_iterations > 0 and len(seed_array) >= 4:
            if progress_callback:
                progress_callback(
                    f"Applying Lloyd relaxation ({lloyd_iterations} passes) …"
                )
            bounds = tuple(zip(min_co.tolist(), max_co.tolist()))
            seed_array = lloyd_relaxation_3d(seed_array, bounds, lloyd_iterations)

        # Ghost points at corners and face centres of a 2× expanded AABB
        # ensure all interior cells are bounded.
        expand = size * 2.0
        ghost: list[np.ndarray] = [
            center + np.array([sx, sy, sz]) * expand
            for sx in (-1, 0, 1)
            for sy in (-1, 0, 1)
            for sz in (-1, 0, 1)
            if abs(sx) + abs(sy) + abs(sz) >= 1  # exclude exact centre
        ]

        all_points = np.vstack([seed_array, np.array(ghost, dtype=np.float64)])
        vor = Voronoi(all_points)

        if progress_callback:
            progress_callback(
                f"Voronoi computed: {len(vor.regions)} regions, "
                f"{len(vor.vertices)} vertices."
            )

        return vor, seed_array

    # ------------------------------------------------------------------
    # Cell-object builder
    # ------------------------------------------------------------------

    def _make_cell_object(
        self,
        cell_verts_np: np.ndarray,
        cell_idx: int,
        tmp_collection: Any,
    ) -> Optional[Any]:
        """Build a watertight convex-hull mesh for a single Voronoi cell.

        Args:
            cell_verts_np: Vertex array for the cell's Voronoi region.
            cell_idx: Cell index used for unique naming.
            tmp_collection: Blender collection to link the temporary object.

        Returns:
            The Blender object, or ``None`` when the cell is degenerate.
        """
        if len(cell_verts_np) < 4:
            return None

        try:
            hull = ConvexHull(cell_verts_np)
        except Exception as exc:
            print(f"  ConvexHull failed for cell {cell_idx}: {exc}")
            return None

        hull_verts = cell_verts_np[hull.vertices]
        old_to_new = {old: new for new, old in enumerate(hull.vertices)}
        hull_faces = [[old_to_new[idx] for idx in face] for face in hull.simplices]

        mesh_name = f"_tmp_cell_{cell_idx}"
        mesh = bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(mesh_name, mesh)
        tmp_collection.objects.link(obj)

        mesh.from_pydata([tuple(v) for v in hull_verts], [], hull_faces)
        mesh.update()

        # Normals must point outward for the boolean modifier to work.
        bm_tmp = bmesh.new()
        bm_tmp.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm_tmp, faces=bm_tmp.faces)
        bm_tmp.to_mesh(mesh)
        bm_tmp.free()
        mesh.update()

        return obj

    # ------------------------------------------------------------------
    # Main fracture routine
    # ------------------------------------------------------------------

    def boolean_fracture(
        self,
        n_seeds: int,
        source_obj: Any,
        weight_map: Optional[dict[int, float]] = None,
        use_weight_paint: bool = False,
        use_lloyd: bool = False,
        lloyd_iterations: int = 3,
        output_name: str = "Voronoi_Boolean",
        boolean_solver: str = "EXACT",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Optional[Any]:
        """Perform Cell Fracture-like Voronoi boolean intersection.

        Each Voronoi cell is intersected with a duplicate of *source_obj*
        via a boolean modifier, then all resulting meshes are joined into a
        single output object.

        Args:
            n_seeds: Number of Voronoi seed points (= number of cells).
            source_obj: The mesh object to fracture.
            weight_map: Optional per-vertex weight dict for density bias.
            use_weight_paint: Activate weight-biased seed sampling.
            use_lloyd: Apply Lloyd relaxation to seed points.
            lloyd_iterations: Number of Lloyd relaxation passes.
            output_name: Name for the final joined mesh object.
            boolean_solver: One of ``'EXACT'``, ``'FLOAT'``, ``'MANIFOLD'``.
            progress_callback: Optional status callback.

        Returns:
            The joined Blender object on success, ``None`` on failure.
        """
        # --- 0. Ensure Object mode (required by modifier_apply / join) ---
        original_mode: str = (
            bpy.context.object.mode if bpy.context.object else "OBJECT"
        )
        if original_mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        source_collection = (
            source_obj.users_collection[0]
            if source_obj.users_collection
            else bpy.context.scene.collection
        )

        # --- 1. Seed generation ------------------------------------------
        seed_points = self.generate_seed_points(
            n_seeds, weight_map, use_weight_paint, progress_callback
        )

        if len(seed_points) < 2:
            print("ERROR: not enough seed points generated inside mesh.")
            return None

        # --- 2. Voronoi computation --------------------------------------
        vor, seed_array = self.compute_voronoi_bounded(
            seed_points, use_lloyd, lloyd_iterations, progress_callback
        )

        # Temporary collection keeps the viewport tidy during processing.
        tmp_col_name = "_tmp_voronoi_cells"
        tmp_collection = bpy.data.collections.get(tmp_col_name)
        if tmp_collection is None:
            tmp_collection = bpy.data.collections.new(tmp_col_name)
            bpy.context.scene.collection.children.link(tmp_collection)

        cell_objects: list[Any] = []
        n_actual = len(seed_array)

        # --- 3. Process each Voronoi region ------------------------------
        for i in range(n_actual):
            if progress_callback:
                progress_callback(f"Boolean intersect cell {i + 1}/{n_actual} …")

            region = vor.regions[vor.point_region[i]]

            # Skip degenerate or infinite regions.
            if len(region) == 0 or -1 in region:
                continue

            cell_obj = self._make_cell_object(vor.vertices[region], i, tmp_collection)
            if cell_obj is None:
                continue

            # Duplicate the source mesh for this cell's boolean.
            result_obj = bpy.data.objects.new(
                f"_cell_{i:03d}", source_obj.data.copy()
            )
            result_obj.matrix_world = source_obj.matrix_world.copy()
            source_collection.objects.link(result_obj)

            bool_mod = result_obj.modifiers.new("BoolIntersect", "BOOLEAN")
            bool_mod.operation = "INTERSECT"
            bool_mod.object = cell_obj
            bool_mod.solver = boolean_solver

            bpy.context.view_layer.objects.active = result_obj
            bpy.context.view_layer.update()

            applied = False
            try:
                with bpy.context.temp_override(
                    active_object=result_obj,
                    selected_objects=[result_obj],
                    selected_editable_objects=[result_obj],
                    mode="OBJECT",
                ):
                    bpy.ops.object.modifier_apply(modifier="BoolIntersect")
                applied = True
            except Exception as exc:
                print(f"  Boolean apply failed for cell {i}: {exc}")

            # Always remove the temporary cutter.
            bpy.data.objects.remove(cell_obj, do_unlink=True)
            cell_data = bpy.data.meshes.get(f"_tmp_cell_{i}")
            if cell_data:
                bpy.data.meshes.remove(cell_data)

            if not applied or len(result_obj.data.vertices) < 3:
                bpy.data.objects.remove(result_obj, do_unlink=True)
                continue

            cell_objects.append(result_obj)

        # --- 4. Remove temporary collection ------------------------------
        if tmp_col_name in bpy.data.collections:
            tmp_col = bpy.data.collections[tmp_col_name]
            for obj in list(tmp_col.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(tmp_col)

        if not cell_objects:
            if progress_callback:
                progress_callback("No valid cells produced.")
            return None

        # --- 5. Join all cells into one mesh -----------------------------
        if progress_callback:
            progress_callback(f"Joining {len(cell_objects)} cells into single mesh …")

        for obj in cell_objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = cell_objects[0]
        bpy.context.view_layer.update()

        with bpy.context.temp_override(
            active_object=cell_objects[0],
            selected_objects=cell_objects,
            selected_editable_objects=cell_objects,
            mode="OBJECT",
        ):
            bpy.ops.object.join()

        joined_obj = bpy.context.view_layer.objects.active
        joined_obj.name = output_name
        joined_obj.data.name = output_name

        if progress_callback:
            progress_callback(
                f"Boolean fracture complete: "
                f"{len(cell_objects)}/{n_actual} cells → single mesh."
            )

        # Restore the original interaction mode on the source object.
        if original_mode != "OBJECT" and source_obj.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = source_obj
            bpy.ops.object.mode_set(mode=original_mode)

        return joined_obj


# ---------------------------------------------------------------------------
# Geometry cleanup utilities
# ---------------------------------------------------------------------------


def cleanup_geometry(
    obj: Any,
    merge_threshold: float = 0.0001,
    decimate_planar: bool = True,
    decimate_angle: float = 5.0,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Remove duplicate vertices and dissolve coplanar faces on *obj*.

    The merge threshold is scaled automatically relative to the object's
    bounding-box diagonal so it stays meaningful across different scene
    scales.

    Args:
        obj: Target Blender mesh object.
        merge_threshold: Base distance for vertex merging.
        decimate_planar: When ``True``, dissolve planar face boundaries.
        decimate_angle: Maximum coplanarity angle in degrees.
        progress_callback: Optional status callback.
    """
    if progress_callback:
        progress_callback("Cleaning up geometry …")

    bm = bmesh.new()
    bm.from_mesh(obj.data)

    bbox_diag = math.sqrt(sum(d ** 2 for d in obj.dimensions))
    adaptive = merge_threshold
    if bbox_diag > 0:
        if bbox_diag < 0.1:
            adaptive *= 0.1
        elif bbox_diag > 100:
            adaptive *= 10.0

    initial_verts = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=adaptive)
    removed = initial_verts - len(bm.verts)
    if progress_callback and removed > 0:
        progress_callback(f"Removed {removed} duplicate vertices.")

    if decimate_planar:
        initial_faces = len(bm.faces)
        bmesh.ops.dissolve_limit(
            bm,
            angle_limit=math.radians(decimate_angle),
            use_dissolve_boundaries=False,
            verts=bm.verts,
            edges=bm.edges,
            delimit={"NORMAL"},
        )
        dissolved = initial_faces - len(bm.faces)
        if progress_callback and dissolved > 0:
            progress_callback(f"Dissolved {dissolved} planar faces.")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    if progress_callback:
        progress_callback(
            f"Cleanup complete: "
            f"{len(obj.data.vertices)} verts, "
            f"{len(obj.data.polygons)} faces."
        )


def cleanup_geometry_list(
    obj_list: list[Any],
    merge_threshold: float = 0.0001,
    decimate_planar: bool = True,
    decimate_angle: float = 5.0,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> None:
    """Apply :func:`cleanup_geometry` to every object in *obj_list*.

    Errors on individual objects are logged but do not abort the whole
    batch.

    Args:
        obj_list: Blender mesh objects to clean up.
        merge_threshold: Passed through to :func:`cleanup_geometry`.
        decimate_planar: Passed through to :func:`cleanup_geometry`.
        decimate_angle: Passed through to :func:`cleanup_geometry`.
        progress_callback: Optional status callback.
    """
    for i, obj in enumerate(obj_list):
        if progress_callback:
            progress_callback(f"Cleaning cell {i + 1}/{len(obj_list)} …")
        try:
            cleanup_geometry(obj, merge_threshold, decimate_planar, decimate_angle)
        except Exception as exc:
            print(f"Cleanup failed for {obj.name}: {exc}")


# ---------------------------------------------------------------------------
# Blender properties
# ---------------------------------------------------------------------------


class TessellationProperties(PropertyGroup):
    """Scene-level property group exposed in the Tessellation panel."""

    tessellation_type: EnumProperty(
        name="Type",
        description="Tessellation algorithm",
        items=[
            ("DELAUNAY", "Delaunay", "Tetrahedra-based tessellation"),
            (
                "VORONOI_BOOLEAN",
                "Voronoi Boolean",
                "Cell Fracture-like boolean intersection — perfect surface fit",
            ),
        ],
        default="VORONOI_BOOLEAN",
    )

    # -- Shared ----------------------------------------------------------

    use_weight_paint: BoolProperty(
        name="Use Weight Paint",
        description="Use vertex group weights for adaptive density",
        default=False,
    )

    vertex_group_name: StringProperty(
        name="Vertex Group",
        description="Vertex group for weight-paint density bias",
        default="",
    )

    use_lloyd_relaxation: BoolProperty(
        name="Lloyd Relaxation",
        description="Apply Lloyd relaxation for more regular cells (Voronoi only)",
        default=False,
    )

    lloyd_iterations: IntProperty(
        name="Lloyd Iterations",
        description="Number of Lloyd relaxation iterations",
        default=3,
        min=1,
        max=10,
    )

    auto_cleanup: BoolProperty(
        name="Auto Cleanup",
        description="Automatically clean up geometry after tessellation",
        default=True,
    )

    merge_threshold: FloatProperty(
        name="Merge Distance",
        description="Distance for merging duplicate vertices",
        default=0.0001,
        min=0.00001,
        max=1.0,
    )

    decimate_planar: BoolProperty(
        name="Dissolve Planar",
        description="Merge coplanar faces",
        default=True,
    )

    decimate_angle: FloatProperty(
        name="Planar Angle",
        description="Maximum angle for planar dissolution (degrees)",
        default=5.0,
        min=0.1,
        max=30.0,
    )

    auto_name: BoolProperty(
        name="Auto-name Output",
        description="Automatically name output based on input mesh",
        default=True,
    )

    output_name: StringProperty(
        name="Output Name",
        description="Name for the output mesh object",
        default="Tessellation_Output",
    )

    # -- Delaunay --------------------------------------------------------

    base_samples: IntProperty(
        name="Volume Samples",
        description="Number of internal points to generate (Delaunay)",
        default=20,
        min=2,
        max=500,
    )

    use_original_vertices: BoolProperty(
        name="Include Original Vertices",
        description="Include mesh vertices as tessellation points (Delaunay only)",
        default=True,
    )

    # -- Voronoi Boolean -------------------------------------------------

    num_cells: IntProperty(
        name="Number of Cells",
        description="Number of Voronoi seed points (= number of cells)",
        default=20,
        min=2,
        max=500,
    )

    boolean_solver: EnumProperty(
        name="Boolean Solver",
        description="Solver for boolean intersection",
        items=[
            ("EXACT", "Exact", "Most accurate, slower — best surface fit"),
            ("FLOAT", "Float", "Faster, less accurate for complex meshes"),
            (
                "MANIFOLD",
                "Manifold",
                "Fastest, requires manifold (watertight) meshes",
            ),
        ],
        default="EXACT",
    )


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class MESH_OT_check_scipy(Operator):
    """Check whether scipy is importable and report its version."""

    bl_idname = "mesh.check_scipy"
    bl_label = "Check scipy"

    def execute(self, context: Any) -> set[str]:
        """Run the scipy version check."""
        try:
            import scipy
            self.report({"INFO"}, f"scipy {scipy.__version__} is installed.")
        except ImportError:
            self.report({"WARNING"}, "scipy is not installed.")
        return {"FINISHED"}


class MESH_OT_install_scipy(Operator):
    """Install the scipy dependency via pip."""

    bl_idname = "mesh.install_scipy"
    bl_label = "Install scipy"

    def execute(self, context: Any) -> set[str]:
        """Trigger the scipy installation routine."""
        self.report({"INFO"}, "Installing scipy …  This may take a minute.")
        if ensure_scipy_installed():
            self.report({"INFO"}, "scipy installed!  Please restart Blender.")
        else:
            self.report({"ERROR"}, "Failed to install scipy.  Check the console.")
        return {"FINISHED"}


class MESH_OT_tessellation_3d(Operator):
    """Generate 3-D tessellation (Delaunay or Voronoi Boolean)."""

    bl_idname = "mesh.tessellation_3d"
    bl_label = "Generate Tessellation"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Any) -> bool:
        """Enable only when a mesh object is active."""
        return (
            context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context: Any) -> set[str]:
        """Dispatch to the selected tessellation algorithm."""
        if not scipy_available:
            self.report(
                {"ERROR"}, "scipy not installed!  Click 'Install scipy' first."
            )
            return {"CANCELLED"}

        obj = context.active_object
        props = context.scene.tessellation_props

        def report_progress(msg: str) -> None:
            print(msg)
            self.report({"INFO"}, msg)

        try:
            output_name = (
                f"{obj.name}_{props.tessellation_type}"
                if props.auto_name
                else props.output_name
            )

            # ----------------------------------------------------------------
            # Delaunay
            # ----------------------------------------------------------------
            if props.tessellation_type == "DELAUNAY":
                tessellator = DelaunayTessellator(obj)
                weight_map = tessellator.get_vertex_weight_map(
                    props.use_weight_paint, props.vertex_group_name
                )
                points = tessellator.get_all_volume_points(
                    weight_map,
                    props.base_samples,
                    props.use_original_vertices,
                    report_progress,
                )

                if len(points) < 4:
                    self.report({"ERROR"}, "Not enough points generated!")
                    tessellator.cleanup()
                    return {"CANCELLED"}

                result = tessellator.perform_tessellation(points, report_progress)
                if result is None:
                    self.report({"ERROR"}, "Tessellation failed!")
                    tessellator.cleanup()
                    return {"CANCELLED"}

                tri, points_array = result
                simplices = tessellator.filter_internal_simplices(
                    tri, points_array, report_progress
                )

                if len(simplices) == 0:
                    self.report({"ERROR"}, "No internal tetrahedra found!")
                    tessellator.cleanup()
                    return {"CANCELLED"}

                faces = tessellator.extract_surface_faces(simplices, report_progress)
                final_obj, vertices, faces = tessellator.create_mesh(
                    points_array, faces, output_name
                )

                if props.auto_cleanup:
                    cleanup_geometry(
                        final_obj,
                        props.merge_threshold,
                        props.decimate_planar,
                        props.decimate_angle,
                        report_progress,
                    )

                tessellator.cleanup()

                bpy.ops.object.select_all(action="DESELECT")
                final_obj.select_set(True)
                bpy.context.view_layer.objects.active = final_obj

                self.report(
                    {"INFO"},
                    f"Delaunay complete: {len(vertices)} verts, "
                    f"{len(simplices)} tetrahedra, {len(faces)} faces.",
                )

            # ----------------------------------------------------------------
            # Voronoi Boolean — Cell Fracture
            # ----------------------------------------------------------------
            elif props.tessellation_type == "VORONOI_BOOLEAN":
                tessellator = VoronoiBooleanTessellator(obj)
                weight_map = tessellator.get_vertex_weight_map(
                    props.use_weight_paint, props.vertex_group_name
                )

                final_obj = tessellator.boolean_fracture(
                    n_seeds=props.num_cells,
                    source_obj=obj,
                    weight_map=weight_map,
                    use_weight_paint=props.use_weight_paint,
                    use_lloyd=props.use_lloyd_relaxation,
                    lloyd_iterations=props.lloyd_iterations,
                    output_name=output_name,
                    boolean_solver=props.boolean_solver,
                    progress_callback=report_progress,
                )

                if final_obj is None:
                    self.report(
                        {"ERROR"},
                        "No cells generated!  Check mesh normals and try again.",
                    )
                    tessellator.cleanup()
                    return {"CANCELLED"}

                if props.auto_cleanup:
                    cleanup_geometry(
                        final_obj,
                        props.merge_threshold,
                        props.decimate_planar,
                        props.decimate_angle,
                        report_progress,
                    )

                tessellator.cleanup()

                bpy.ops.object.select_all(action="DESELECT")
                final_obj.select_set(True)
                bpy.context.view_layer.objects.active = final_obj

                self.report(
                    {"INFO"},
                    f"Voronoi Boolean complete: "
                    f"{len(final_obj.data.vertices)} verts, "
                    f"{len(final_obj.data.polygons)} faces → '{output_name}'.",
                )

            return {"FINISHED"}

        except Exception as exc:
            self.report({"ERROR"}, f"Error: {exc}")
            traceback.print_exc()
            return {"CANCELLED"}


class MESH_OT_check_normals(Operator):
    """Check mesh manifoldness and recalculate face normals."""

    bl_idname = "mesh.check_normals"
    bl_label = "Check & Fix Normals"

    @classmethod
    def poll(cls, context: Any) -> bool:
        """Enable only when a mesh object is active."""
        return (
            context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context: Any) -> set[str]:
        """Run the manifold check and recalculate normals."""
        obj = context.active_object

        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(obj.data)

        non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
        non_manifold_verts = [v for v in bm.verts if not v.is_manifold]

        if non_manifold_edges or non_manifold_verts:
            msg = (
                f"Mesh is NOT manifold: "
                f"{len(non_manifold_edges)} non-manifold edges, "
                f"{len(non_manifold_verts)} non-manifold vertices.  "
                "Fix before applying tessellation."
            )
            self.report({"WARNING"}, msg)

            def draw_nonmanifold_popup(popup_self: Any, context: Any) -> None:
                layout = popup_self.layout
                layout.label(text="⚠  Non-manifold mesh detected!", icon="ERROR")
                layout.separator()
                layout.label(
                    text=f"Non-manifold edges: {len(non_manifold_edges)}",
                    icon="EDGESEL",
                )
                layout.label(
                    text=f"Non-manifold vertices: {len(non_manifold_verts)}",
                    icon="VERTEXSEL",
                )
                layout.separator()
                layout.label(
                    text="Voronoi Boolean requires a watertight (manifold) mesh.",
                    icon="INFO",
                )
                layout.separator()
                layout.label(text="Suggestions:  Mesh › Clean Up ›")
                layout.label(text="  • Merge by Distance")
                layout.label(text="  • Fill Holes")
                layout.label(text="  • Delete Loose")

            bpy.context.window_manager.popup_menu(
                draw_nonmanifold_popup,
                title="Warning: Non-Manifold Mesh",
                icon="ERROR",
            )

        else:
            self.report({"INFO"}, "Mesh is manifold ✓")

        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        self.report({"INFO"}, "Normals recalculated.")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Smooth SFD integration
# ---------------------------------------------------------------------------


def ensure_smooth_sfd_loaded() -> bool:
    """Load the Smooth SFD node group from the bundled .blend file.

    Tries :func:`bpy.data.libraries.load` first (reliable on all
    platforms, including macOS background calls), then falls back to
    ``bpy.ops.wm.append`` when a UI context is available.

    Returns:
        ``True`` if the node group is (or becomes) available in
        ``bpy.data.node_groups``.
    """
    node_group_name = "Smooth SFD"

    if node_group_name in bpy.data.node_groups:
        return True

    addon_dir = os.path.dirname(os.path.realpath(__file__))
    blend_file = os.path.join(addon_dir, "Smooth_SFD.blend")

    if not os.path.exists(blend_file):
        print(f"ERROR: Smooth_SFD.blend not found at: {blend_file}")
        return False

    print(f"Loading Smooth SFD from: {blend_file}")

    # Primary method: bpy.data.libraries.load
    # bpy.ops.wm.append is intentionally avoided here because it requires
    # an active UI context (not always available on macOS / background
    # calls) and can fail silently when invoked outside an operator.
    try:
        with bpy.data.libraries.load(blend_file, link=False) as (src, dst):
            available = list(src.node_groups)
            print(f"Node groups in .blend: {available}")

            if node_group_name not in available:
                print(
                    f"ERROR: '{node_group_name}' not found in {blend_file}\n"
                    f"       Available: {available}"
                )
                return False

            dst.node_groups = [node_group_name]

        if node_group_name in bpy.data.node_groups:
            print("✓ Smooth SFD loaded successfully.")
            return True

        print("ERROR: libraries.load completed but node group is still missing.")

    except Exception as exc:
        print(f"ERROR loading Smooth_SFD.blend: {exc}")
        traceback.print_exc()

    # Fallback: wm.append (requires a UI context)
    print("Trying fallback via wm.append …")
    try:
        bpy.ops.wm.append(
            filepath=os.path.join(blend_file, "NodeTree", node_group_name),
            directory=os.path.join(blend_file, "NodeTree"),
            filename=node_group_name,
            link=False,
        )
        if node_group_name in bpy.data.node_groups:
            print("✓ Smooth SFD loaded via wm.append (fallback).")
            return True
    except Exception as exc:
        print(f"Fallback wm.append failed: {exc}")

    print("ERROR: all load methods failed — Smooth SFD unavailable.")
    return False


class MESH_OT_apply_smooth_sfd(Operator):
    """Apply the Smooth SFD geometry-nodes modifier to the active mesh."""

    bl_idname = "mesh.apply_smooth_sfd"
    bl_label = "Apply Smooth SFD"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Any) -> bool:
        """Enable only when a mesh object is active."""
        return (
            context.active_object is not None
            and context.active_object.type == "MESH"
        )

    def execute(self, context: Any) -> set[str]:
        """Add the Smooth SFD modifier to the active object."""
        obj = context.active_object
        node_group_name = "Smooth SFD"

        if not ensure_smooth_sfd_loaded():
            self.report(
                {"ERROR"},
                "Smooth SFD asset not found!  Check the console for details.",
            )
            return {"CANCELLED"}

        if node_group_name not in bpy.data.node_groups:
            self.report({"ERROR"}, f"'{node_group_name}' node group not found!")
            return {"CANCELLED"}

        for mod in obj.modifiers:
            if (
                mod.type == "NODES"
                and mod.node_group
                and mod.node_group.name == node_group_name
            ):
                self.report({"INFO"}, "Smooth SFD is already applied to this object.")
                return {"FINISHED"}

        modifier = obj.modifiers.new(name="Smooth SFD", type="NODES")
        modifier.node_group = bpy.data.node_groups[node_group_name]

        self.report({"INFO"}, f"Smooth SFD applied to {obj.name}.")
        return {"FINISHED"}


class MESH_OT_load_smooth_sfd(Operator):
    """Manually trigger loading of the Smooth SFD asset."""

    bl_idname = "mesh.load_smooth_sfd"
    bl_label = "Load Smooth SFD Asset"

    def execute(self, context: Any) -> set[str]:
        """Load the Smooth SFD node group from disk."""
        if "Smooth SFD" in bpy.data.node_groups:
            self.report({"INFO"}, "Smooth SFD is already loaded.")
            return {"FINISHED"}

        if ensure_smooth_sfd_loaded():
            self.report({"INFO"}, "Smooth SFD loaded successfully!")
            return {"FINISHED"}

        self.report(
            {"ERROR"}, "Failed to load Smooth SFD.  Check the console for details."
        )
        return {"CANCELLED"}


# ---------------------------------------------------------------------------
# UI panel
# ---------------------------------------------------------------------------


class VIEW3D_PT_tessellation_3d(Panel):
    """3D Tessellation control panel in the N-panel."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tessellation"
    bl_label = "3D Tessellation"

    def draw(self, context: Any) -> None:
        """Render the panel layout."""
        layout = self.layout
        props = context.scene.tessellation_props
        obj = context.active_object

        # -- Header ----------------------------------------------------------
        box = layout.box()
        box.label(text="3D Tessellation v2.3", icon="MESH_ICOSPHERE")

        # -- scipy -----------------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Dependencies:", icon="PACKAGE")
        row = box.row(align=True)
        row.operator("mesh.check_scipy", icon="CHECKMARK")
        row.operator("mesh.install_scipy", icon="IMPORT")
        if scipy_available:
            try:
                import scipy
                box.label(text=f"✓ scipy {scipy.__version__}", icon="CHECKMARK")
            except ImportError:
                box.label(text="✓ scipy (restart required)", icon="INFO")
        else:
            box.label(text="✗ scipy not found", icon="ERROR")

        # -- Tessellation type -----------------------------------------------
        layout.separator()
        layout.prop(props, "tessellation_type", expand=True)

        # -- Info box --------------------------------------------------------
        box = layout.box()
        if props.tessellation_type == "DELAUNAY":
            box.label(text="Delaunay:", icon="INFO")
            col = box.column(align=True)
            col.label(text="• Tetrahedra-based structure")
            col.label(text="• Ideal for FEM / physics sims")
        else:
            box.label(text="Voronoi Boolean (Cell Fracture):", icon="INFO")
            col = box.column(align=True)
            col.label(text="• Each cell: boolean INTERSECT with source")
            col.label(text="• Perfect surface conformance")
            col.label(text="• Output: single joined mesh")
            col.label(text="• Needs watertight (manifold) mesh")

        # -- Parameters ------------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Parameters:", icon="PREFERENCES")
        col = box.column(align=True)

        if props.tessellation_type == "DELAUNAY":
            col.prop(props, "base_samples")
            col.prop(props, "use_original_vertices")
        else:
            col.prop(props, "num_cells")
            col.prop(props, "boolean_solver")

        col.separator()
        col.prop(props, "use_weight_paint")
        if props.use_weight_paint:
            if obj:
                col.prop_search(
                    props, "vertex_group_name", obj, "vertex_groups", text="Group"
                )
            else:
                col.label(text="Select a mesh first", icon="ERROR")

        # -- Lloyd relaxation ------------------------------------------------
        if props.tessellation_type != "DELAUNAY":
            layout.separator()
            box = layout.box()
            box.label(text="Lloyd Relaxation:", icon="SMOOTHCURVE")
            col = box.column(align=True)
            col.prop(props, "use_lloyd_relaxation")
            if props.use_lloyd_relaxation:
                col.prop(props, "lloyd_iterations")
                col.label(text="More regular cell sizes", icon="INFO")

        # -- Geometry cleanup ------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Geometry Cleanup:", icon="BRUSH_DATA")
        col = box.column(align=True)
        col.prop(props, "auto_cleanup")
        if props.auto_cleanup:
            col.prop(props, "merge_threshold")
            col.prop(props, "decimate_planar")
            if props.decimate_planar:
                col.prop(props, "decimate_angle")

        # -- Output ----------------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Output:", icon="OUTLINER_OB_MESH")
        col = box.column(align=True)
        col.prop(props, "auto_name")
        if not props.auto_name:
            col.prop(props, "output_name")

        # -- Action buttons --------------------------------------------------
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("mesh.check_normals", icon="NORMALS_FACE")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.8

        if obj and obj.type == "MESH":
            if scipy_available:
                row.operator(
                    "mesh.tessellation_3d",
                    icon="MOD_REMESH",
                    text="Generate Tessellation",
                )
            else:
                row.label(text="Install scipy first", icon="ERROR")
        else:
            row.label(text="Select a mesh object", icon="ERROR")

        # -- Smooth SFD ------------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Edge Smoothing:", icon="MOD_SMOOTH")
        row = box.row()
        row.scale_y = 1.3
        if obj and obj.type == "MESH":
            row.operator("mesh.apply_smooth_sfd", icon="GEOMETRY_NODES")
        else:
            row.label(text="Select a mesh object", icon="ERROR")
        col = box.column(align=True)
        col.label(text="Smooths edges via Geometry Nodes", icon="INFO")
        row2 = box.row()
        row2.scale_y = 0.8
        row2.operator("mesh.load_smooth_sfd", text="Load Asset Manually", icon="IMPORT")

        # -- Quick tips ------------------------------------------------------
        layout.separator()
        box = layout.box()
        box.label(text="Quick Tips:", icon="QUESTION")
        col = box.column(align=True)
        col.label(text="1. Check & fix normals first.")
        col.label(text="2. Higher samples or cells = more detail.")
        col.label(text="3. Use weight paint for adaptive density.")
        if props.tessellation_type == "VORONOI_BOOLEAN":
            col.label(text="4. EXACT solver = best surface fit.")
            col.label(text="5. Lloyd ON = more uniform cells.")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    TessellationProperties,
    MESH_OT_check_scipy,
    MESH_OT_install_scipy,
    MESH_OT_tessellation_3d,
    MESH_OT_check_normals,
    MESH_OT_apply_smooth_sfd,
    MESH_OT_load_smooth_sfd,
    VIEW3D_PT_tessellation_3d,
)


def register() -> None:
    """Register all addon classes and the scene property group."""
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.tessellation_props = bpy.props.PointerProperty(
        type=TessellationProperties
    )

    print("3D Tessellation v2.3.0 registered.")


def unregister() -> None:
    """Unregister all addon classes and remove the scene property."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.tessellation_props


if __name__ == "__main__":
    register()
