"""
3D Tessellation Addon v2.3 - Unified
Combines best of v1.5.0 + v2.0.0 + Cell Fracture boolean approach

Features:
- Delaunay 3D tessellation
- Voronoi 3D BOOLEAN: Cell Fracture-like boolean intersection
  * Generates proper Voronoi seed points inside the mesh
  * Computes convex hull for each Voronoi cell
  * Boolean INTERSECT each cell with the original mesh → perfect surface conformance
- Weight-aware Lloyd relaxation
- Comprehensive geometry cleanup
- Smooth SFD geometry nodes for edge smoothing
"""

bl_info = {
    "name": "3D Tessellation (Delaunay & Voronoi)",
    "author": "Ergo Cogito Design",
    "version": (2, 3, 0),
    "blender": (5, 0, 1),
    "location": "View3D > Sidebar > Tessellation",
    "description": "Complete 3D tessellation suite: Delaunay + Voronoi Boolean (Cell Fracture)",
    "category": "Mesh",
}

import sys
import subprocess
import importlib.util
import os

def ensure_scipy_installed():
    """Verifica e installa scipy se necessario - Windows compatible"""
    scipy_spec = importlib.util.find_spec("scipy")
    if scipy_spec is not None:
        return True

    python_exe = sys.executable

    try:
        try:
            import pip
        except ImportError:
            print("Installing pip using ensurepip...")
            subprocess.check_call([python_exe, "-m", "ensurepip", "--default-pip"])
            subprocess.check_call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])

        print("Installing scipy in user directory...")
        print("This may take a few minutes, please wait...")

        subprocess.check_call([
            python_exe, "-m", "pip", "install",
            "scipy",
            "--user"
        ])

        importlib.invalidate_caches()

        import site
        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.insert(0, user_site)
            print(f"Added user site-packages to path: {user_site}")

        scipy_spec = importlib.util.find_spec("scipy")
        if scipy_spec is None:
            raise ImportError("scipy installation completed but module not found")

        print("scipy installed successfully in user directory!")
        print("Please restart Blender to complete the installation.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Failed to install scipy: {str(e)}")
        print("\nTroubleshooting:")
        print("If on Windows with Blender in Program Files:")
        print("1. Run Blender as Administrator, OR")
        print("2. Install scipy manually from Command Prompt:")
        print(f'   "{python_exe}" -m pip install scipy --user')
        print("\nThen restart Blender.")
        return False
    except Exception as e:
        print(f"Failed to install scipy: {str(e)}")
        return False


scipy_available = ensure_scipy_installed()

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import math
from bpy.props import (
    EnumProperty, IntProperty, FloatProperty, BoolProperty, StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup

if scipy_available:
    from scipy.spatial import Delaunay, Voronoi, ConvexHull


# ============================================================================
# LLOYD RELAXATION - WEIGHT AWARE
# ============================================================================

def lloyd_relaxation_3d(points, bounds, iterations=3, density_weights=None):
    """
    Weight-aware Lloyd relaxation for 3D Voronoi.

    High weight → less movement → smaller cells maintained
    Low weight → normal movement → larger cells
    """
    if not scipy_available:
        print("Warning: scipy not available, skipping Lloyd relaxation")
        return points

    points = np.array(points, dtype=np.float64)

    if density_weights is None:
        density_weights = np.ones(len(points))
    else:
        density_weights = np.array(density_weights, dtype=np.float64)

    for iteration in range(iterations):
        vor = Voronoi(points)
        new_points = []

        for point_idx in range(len(points)):
            region_idx = vor.point_region[point_idx]
            region = vor.regions[region_idx]

            if -1 in region or len(region) == 0:
                new_points.append(points[point_idx])
                continue

            vertices = vor.vertices[region]
            centroid = np.mean(vertices, axis=0)

            weight = density_weights[point_idx]
            max_weight = np.max(density_weights)
            normalized_weight = weight / (max_weight + 0.01)

            movement_factor = 0.3 + 0.7 * (1.0 - normalized_weight)

            new_position = points[point_idx] + (centroid - points[point_idx]) * movement_factor

            new_position[0] = np.clip(new_position[0], bounds[0][0], bounds[0][1])
            new_position[1] = np.clip(new_position[1], bounds[1][0], bounds[1][1])
            new_position[2] = np.clip(new_position[2], bounds[2][0], bounds[2][1])

            new_points.append(new_position)

        points = np.array(new_points)

    return points


# ============================================================================
# BASE TESSELLATOR CLASS
# ============================================================================

class Tessellator3D:
    """Base class for 3D tessellation with common utilities"""

    def __init__(self, obj):
        self.obj = obj
        self.mesh = obj.data
        self.bm = bmesh.new()
        self.bm.from_mesh(self.mesh)
        # Apply the object's world transform so that all subsequent operations
        # (bounding box, point sampling, inside tests, BVH queries) work in
        # world space.  This fixes tessellation on objects that have been
        # moved, rotated or scaled without applying transforms.
        # Note: this does NOT modify the original object or its mesh data.
        self.bm.transform(obj.matrix_world)
        self.bm.verts.ensure_lookup_table()
        self.bm.edges.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        self.bvh = BVHTree.FromBMesh(self.bm)

    def get_vertex_weight_map(self, use_weight_paint=False, group_name=""):
        """Get weight map from vertex group or uniform"""
        weight_map = {}

        if use_weight_paint and group_name and group_name in self.obj.vertex_groups:
            group_index = self.obj.vertex_groups[group_name].index
            dvert_lay = self.bm.verts.layers.deform.verify()

            has_weights = False
            for vert in self.bm.verts:
                dvert = vert[dvert_lay]
                weight = dvert.get(group_index, 0.0) if group_index in dvert else 0.0
                weight_map[vert.index] = weight + 0.05
                if weight > 0:
                    has_weights = True

            if has_weights:
                return weight_map
            else:
                print("Warning: Vertex group empty, using uniform weights")

        for vert in self.bm.verts:
            weight_map[vert.index] = 1.0

        return weight_map

    def is_point_inside_mesh(self, point, epsilon=0.0001):
        """Check if point is inside mesh volume"""
        location, normal, face_index, distance = self.bvh.find_nearest(point)

        if location is None:
            return False

        to_point = point - location

        if distance < epsilon * 10:
            return self._is_inside_ray_casting(point)

        is_inside_normal = to_point.dot(normal) < -epsilon

        if distance > epsilon * 10:
            is_inside_ray = self._is_inside_ray_casting(point)
            return is_inside_normal and is_inside_ray

        return is_inside_normal

    def _is_inside_ray_casting(self, point):
        """Ray casting for robust inside test"""
        directions = [
            Vector((1, 0, 0)),
            Vector((0, 1, 0)),
            Vector((0, 0, 1))
        ]

        inside_count = 0
        epsilon = 0.0001

        for direction in directions:
            intersections = 0
            current_point = point.copy()
            max_iterations = 100
            iteration = 0

            while iteration < max_iterations:
                hit_location, hit_normal, hit_index, hit_distance = self.bvh.ray_cast(
                    current_point, direction
                )

                if hit_location is None:
                    break

                intersections += 1
                current_point = hit_location + direction * epsilon
                iteration += 1

            if intersections % 2 == 1:
                inside_count += 1

        return inside_count >= 2

    def get_mesh_bounds(self):
        """Return (min_co, max_co) as numpy arrays"""
        min_co = np.array([min(v.co[i] for v in self.bm.verts) for i in range(3)])
        max_co = np.array([max(v.co[i] for v in self.bm.verts) for i in range(3)])
        return min_co, max_co

    def cleanup(self):
        """Clean up resources"""
        self.bm.free()


# ============================================================================
# DELAUNAY TESSELLATOR
# ============================================================================

class DelaunayTessellator(Tessellator3D):
    """Delaunay 3D tessellation"""

    def get_all_volume_points(self, weight_map, base_samples, use_original_verts,
                              progress_callback=None):
        """Generate volume points with adaptive density"""
        min_co = Vector([min(v.co[i] for v in self.bm.verts) for i in range(3)])
        max_co = Vector([max(v.co[i] for v in self.bm.verts) for i in range(3)])

        points = []

        if use_original_verts:
            for vert in self.bm.verts:
                points.append(vert.co.copy())
            if progress_callback:
                progress_callback(f"Added {len(points)} original vertices")

        if progress_callback:
            progress_callback("Generating internal points...")

        total_attempts = base_samples * 5
        internal_points_added = 0

        max_weight = max(weight_map.values())

        for attempt in range(total_attempts):
            if progress_callback and attempt % 100 == 0:
                progress_callback(f"Attempts: {attempt}/{total_attempts}, Points: {internal_points_added}")

            test_point = Vector([
                np.random.uniform(min_co.x, max_co.x),
                np.random.uniform(min_co.y, max_co.y),
                np.random.uniform(min_co.z, max_co.z)
            ])

            if self.is_point_inside_mesh(test_point):
                closest_vert = min(self.bm.verts, key=lambda v: (v.co - test_point).length)
                local_density = weight_map[closest_vert.index] / max_weight

                if np.random.random() < local_density:
                    points.append(test_point)
                    internal_points_added += 1

            if internal_points_added >= base_samples:
                break

        if progress_callback:
            progress_callback(f"Total points: {len(points)}")

        return points

    def perform_tessellation(self, points, progress_callback=None):
        """Execute Delaunay tessellation"""
        if len(points) < 4:
            return None

        points_array = np.array([list(p) for p in points])

        if progress_callback:
            progress_callback(f"Computing Delaunay on {len(points)} points...")

        tri = Delaunay(points_array)
        return tri, points_array

    def filter_internal_simplices(self, tri, points_array, progress_callback=None):
        """Filter tetrahedra inside volume"""
        if progress_callback:
            progress_callback("Filtering internal tetrahedra...")

        internal_simplices = []

        for simplex in tri.simplices:
            centroid = np.mean(points_array[simplex], axis=0)
            centroid_vec = Vector(centroid)

            if self.is_point_inside_mesh(centroid_vec):
                internal_simplices.append(simplex)

        if progress_callback:
            progress_callback(f"Found {len(internal_simplices)}/{len(tri.simplices)} internal tetrahedra")

        return internal_simplices

    def extract_surface_faces(self, simplices, progress_callback=None):
        """Extract unique triangular faces from tetrahedra"""
        if progress_callback:
            progress_callback("Extracting surface...")

        face_dict = {}

        for simplex in simplices:
            faces = [
                tuple(sorted([simplex[0], simplex[1], simplex[2]])),
                tuple(sorted([simplex[0], simplex[1], simplex[3]])),
                tuple(sorted([simplex[0], simplex[2], simplex[3]])),
                tuple(sorted([simplex[1], simplex[2], simplex[3]]))
            ]

            for face in faces:
                if face in face_dict:
                    face_dict[face] += 1
                else:
                    face_dict[face] = 1

        internal_faces = [face for face, count in face_dict.items() if count == 2]

        if progress_callback:
            progress_callback(f"Found {len(internal_faces)} internal faces")

        return internal_faces

    def create_mesh(self, points_array, faces, name="Delaunay_Tessellation"):
        """Create Blender mesh from points and faces"""
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)

        bpy.context.collection.objects.link(obj)

        vertices = [tuple(p) for p in points_array]
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        return obj, vertices, faces



# ============================================================================
# VORONOI BOOLEAN TESSELLATOR - CELL FRACTURE APPROACH (new)
# ============================================================================

class VoronoiBooleanTessellator(Tessellator3D):
    """
    Cell Fracture-like Voronoi 3D with boolean intersection.

    Approach:
    1. Generate N seed points uniformly distributed inside the mesh
    2. Optionally apply Lloyd relaxation for more regular cells
    3. Compute 3D Voronoi diagram with ghost boundary points to bound it
    4. For each seed's Voronoi region:
       a. Build a watertight convex hull mesh of the cell
       b. Boolean INTERSECT with the original mesh → perfect surface conformance
       c. The resulting cell conforms exactly to the original surface
    5. All cells are joined into a single mesh object
    """

    def generate_seed_points(self, n_seeds, weight_map=None, use_weight_paint=False,
                             progress_callback=None):
        """
        Generate seed points uniformly inside the mesh volume.
        If weight_map is provided and use_weight_paint is True,
        biases density toward higher-weight regions.
        """
        if progress_callback:
            progress_callback(f"Generating {n_seeds} seed points inside mesh...")

        min_co, max_co = self.get_mesh_bounds()

        seed_points = []
        attempts = 0
        max_attempts = n_seeds * 50

        while len(seed_points) < n_seeds and attempts < max_attempts:
            p = Vector(np.random.uniform(min_co, max_co).tolist())

            if self.is_point_inside_mesh(p):
                # Weight-based acceptance-rejection
                if use_weight_paint and weight_map:
                    nearest_vert = min(self.bm.verts, key=lambda v: (v.co - p).length)
                    w = weight_map.get(nearest_vert.index, 1.0)
                    max_w = max(weight_map.values()) if weight_map else 1.0
                    if np.random.random() > (w / (max_w + 1e-6)):
                        attempts += 1
                        continue

                seed_points.append([p.x, p.y, p.z])

            attempts += 1

        if progress_callback:
            progress_callback(f"Generated {len(seed_points)}/{n_seeds} seed points "
                              f"({attempts} attempts)")

        return seed_points

    def compute_voronoi_bounded(self, seed_points, use_lloyd=False, lloyd_iterations=3,
                                progress_callback=None):
        """
        Compute 3D Voronoi diagram.
        Ghost boundary points are added to ensure all interior seeds
        have finite (bounded) Voronoi regions — same trick used by Cell Fracture.
        """
        if progress_callback:
            progress_callback("Computing bounded 3D Voronoi...")

        min_co, max_co = self.get_mesh_bounds()
        center = (min_co + max_co) / 2.0
        size = max_co - min_co

        seed_array = np.array(seed_points, dtype=np.float64)

        # Lloyd relaxation only on seed points (not ghost points)
        if use_lloyd and lloyd_iterations > 0 and len(seed_array) >= 4:
            if progress_callback:
                progress_callback(f"Applying Lloyd relaxation ({lloyd_iterations} iterations)...")
            bounds = tuple(zip(min_co.tolist(), max_co.tolist()))
            seed_array = lloyd_relaxation_3d(seed_array, bounds, lloyd_iterations)

        # Ghost points: corners and face centers of an expanded bounding box
        # Expand by 2× on each side so all interior cells are finite
        expand = size * 2.0
        ghost = []
        for sx in [-1, 0, 1]:
            for sy in [-1, 0, 1]:
                for sz in [-1, 0, 1]:
                    if abs(sx) + abs(sy) + abs(sz) >= 1:  # exclude center
                        ghost.append(center + np.array([sx, sy, sz]) * expand)

        ghost_array = np.array(ghost, dtype=np.float64)
        all_points = np.vstack([seed_array, ghost_array])

        vor = Voronoi(all_points)

        if progress_callback:
            progress_callback(f"Voronoi computed: {len(vor.regions)} regions, "
                              f"{len(vor.vertices)} vertices")

        return vor, seed_array

    def _make_cell_object(self, cell_verts_np, cell_idx, tmp_collection):
        """
        Build a watertight convex hull mesh for a Voronoi cell.
        Returns the Blender object or None on failure.
        """
        if len(cell_verts_np) < 4:
            return None

        try:
            hull = ConvexHull(cell_verts_np)
        except Exception as e:
            print(f"  ConvexHull failed for cell {cell_idx}: {e}")
            return None

        # hull.vertices: indices of vertices on the hull
        # hull.simplices: triangular faces (index into hull.points)
        hull_verts = cell_verts_np[hull.vertices]
        # Remap simplices to use local (hull.vertices) indices
        old_to_new = {old: new for new, old in enumerate(hull.vertices)}
        hull_faces = [[old_to_new[idx] for idx in face] for face in hull.simplices]

        mesh = bpy.data.meshes.new(f"_tmp_cell_{cell_idx}")
        obj = bpy.data.objects.new(f"_tmp_cell_{cell_idx}", mesh)
        tmp_collection.objects.link(obj)

        mesh.from_pydata([tuple(v) for v in hull_verts], [], hull_faces)
        mesh.update()

        # Recalculate normals so they point outward (required for boolean)
        bm_tmp = bmesh.new()
        bm_tmp.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm_tmp, faces=bm_tmp.faces)
        bm_tmp.to_mesh(mesh)
        bm_tmp.free()
        mesh.update()

        return obj

    def boolean_fracture(self, n_seeds, source_obj,
                         weight_map=None, use_weight_paint=False,
                         use_lloyd=False, lloyd_iterations=3,
                         output_name="Voronoi_Boolean",
                         boolean_solver='EXACT',
                         progress_callback=None):
        """
        Cell Fracture-like Voronoi boolean intersection.

        Computes each cell via boolean INTERSECT with the source mesh,
        then joins everything into a single output mesh object.
        Returns the joined object, or None on failure.
        """

# --- 0. Ensure OBJECT mode (required by modifier_apply / join ops) ------
        original_mode = bpy.context.object.mode if bpy.context.object else 'OBJECT'
        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Recupera la collection della mesh sorgente
        source_collection = (
            source_obj.users_collection[0]
            if source_obj.users_collection
            else bpy.context.scene.collection
        )

        # --- 1. Seed generation -------------------------------------------------
        seed_points = self.generate_seed_points(
            n_seeds, weight_map, use_weight_paint, progress_callback
        )

        if len(seed_points) < 2:
            print("ERROR: Not enough seed points generated inside mesh.")
            return None

        # --- 2. Voronoi computation ---------------------------------------------
        vor, seed_array = self.compute_voronoi_bounded(
            seed_points, use_lloyd, lloyd_iterations, progress_callback
        )

        # Temporary collection to keep the viewport tidy during processing
        tmp_col_name = "_tmp_voronoi_cells"
        tmp_collection = bpy.data.collections.get(tmp_col_name)
        if tmp_collection is None:
            tmp_collection = bpy.data.collections.new(tmp_col_name)
            bpy.context.scene.collection.children.link(tmp_collection)

        cell_objects = []
        n_actual = len(seed_array)

        # --- 3. Process each seed's Voronoi region ------------------------------
        for i in range(n_actual):
            if progress_callback:
                progress_callback(f"Boolean intersect cell {i + 1}/{n_actual}...")

            region_idx = vor.point_region[i]
            region = vor.regions[region_idx]

            # Skip degenerate / infinite regions
            if len(region) == 0 or -1 in region:
                continue

            cell_verts_np = vor.vertices[region]

            # Build the convex hull cell mesh (cutter object)
            cell_obj = self._make_cell_object(cell_verts_np, i, tmp_collection)
            if cell_obj is None:
                continue

            # Duplicate the source mesh for this cell's boolean
            result_data = source_obj.data.copy()
            result_obj = bpy.data.objects.new(f"_cell_{i:03d}", result_data)
            result_obj.matrix_world = source_obj.matrix_world.copy()
            source_collection.objects.link(result_obj)

            # Boolean INTERSECT: result_obj ∩ cell_obj
            bool_mod = result_obj.modifiers.new("BoolIntersect", 'BOOLEAN')
            bool_mod.operation = 'INTERSECT'
            bool_mod.object = cell_obj
            bool_mod.solver = boolean_solver

            # Apply modifier — use a context override so this works
            # regardless of the current interaction mode (Object/Weight Paint/Edit)
            bpy.context.view_layer.objects.active = result_obj
            bpy.context.view_layer.update()

            applied = False
            try:
                with bpy.context.temp_override(
                    active_object=result_obj,
                    selected_objects=[result_obj],
                    selected_editable_objects=[result_obj],
                    mode='OBJECT',
                ):
                    bpy.ops.object.modifier_apply(modifier="BoolIntersect")
                applied = True
            except Exception as e:
                print(f"  Boolean apply failed for cell {i}: {e}")

            # Always remove the temporary cutter
            bpy.data.objects.remove(cell_obj, do_unlink=True)
            cell_data = bpy.data.meshes.get(f"_tmp_cell_{i}")
            if cell_data:
                bpy.data.meshes.remove(cell_data)

            if not applied or len(result_obj.data.vertices) < 3:
                bpy.data.objects.remove(result_obj, do_unlink=True)
                continue

            cell_objects.append(result_obj)

        # --- 4. Clean up temporary collection -----------------------------------
        if tmp_col_name in bpy.data.collections:
            tmp_col = bpy.data.collections[tmp_col_name]
            for o in list(tmp_col.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(tmp_col)

        if not cell_objects:
            if progress_callback:
                progress_callback("No valid cells produced.")
            return None

        # --- 5. Join all cells into one single mesh object ----------------------
        if progress_callback:
            progress_callback(f"Joining {len(cell_objects)} cells into single mesh...")

        for o in cell_objects:
            o.select_set(False)
        for o in cell_objects:
            o.select_set(True)
        bpy.context.view_layer.objects.active = cell_objects[0]
        bpy.context.view_layer.update()

        with bpy.context.temp_override(
            active_object=cell_objects[0],
            selected_objects=cell_objects,
            selected_editable_objects=cell_objects,
            mode='OBJECT',
        ):
            bpy.ops.object.join()

        joined_obj = bpy.context.view_layer.objects.active
        joined_obj.name = output_name
        joined_obj.data.name = output_name

        if progress_callback:
            progress_callback(
                f"Boolean fracture complete: {len(cell_objects)}/{n_actual} cells → single mesh"
            )

        # Restore the original interaction mode on the source object
        if original_mode != 'OBJECT' and source_obj.name in bpy.data.objects:
            bpy.context.view_layer.objects.active = source_obj
            bpy.ops.object.mode_set(mode=original_mode)

        return joined_obj


# ============================================================================
# GEOMETRY CLEANUP UTILITIES
# ============================================================================

def cleanup_geometry(obj, merge_threshold=0.0001, decimate_planar=True,
                    decimate_angle=5.0, progress_callback=None):
    """
    Comprehensive geometry cleanup:
    1. Remove duplicate vertices
    2. Dissolve planar faces
    """
    if progress_callback:
        progress_callback("Cleaning up geometry...")

    bm = bmesh.new()
    bm.from_mesh(obj.data)

    bbox_diag = (obj.dimensions[0]**2 + obj.dimensions[1]**2 + obj.dimensions[2]**2)**0.5
    adaptive_threshold = merge_threshold

    if bbox_diag > 0:
        if bbox_diag < 0.1:
            adaptive_threshold *= 0.1
        elif bbox_diag > 100:
            adaptive_threshold *= 10.0

    initial_verts = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=adaptive_threshold)
    removed_verts = initial_verts - len(bm.verts)

    if progress_callback and removed_verts > 0:
        progress_callback(f"Removed {removed_verts} duplicate vertices")

    if decimate_planar:
        initial_faces = len(bm.faces)
        angle_rad = math.radians(decimate_angle)

        bmesh.ops.dissolve_limit(
            bm,
            angle_limit=angle_rad,
            use_dissolve_boundaries=False,
            verts=bm.verts,
            edges=bm.edges,
            delimit={'NORMAL'}
        )

        dissolved_faces = initial_faces - len(bm.faces)
        if progress_callback and dissolved_faces > 0:
            progress_callback(f"Dissolved {dissolved_faces} planar faces")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()

    if progress_callback:
        progress_callback(
            f"Cleanup complete: {len(obj.data.vertices)} verts, {len(obj.data.polygons)} faces"
        )


def cleanup_geometry_list(obj_list, merge_threshold=0.0001, decimate_planar=True,
                          decimate_angle=5.0, progress_callback=None):
    """Apply cleanup_geometry to a list of objects"""
    for i, obj in enumerate(obj_list):
        if progress_callback:
            progress_callback(f"Cleaning cell {i + 1}/{len(obj_list)}...")
        try:
            cleanup_geometry(obj, merge_threshold, decimate_planar, decimate_angle)
        except Exception as e:
            print(f"Cleanup failed for {obj.name}: {e}")


# ============================================================================
# PROPERTIES
# ============================================================================

class TessellationProperties(PropertyGroup):

    tessellation_type: EnumProperty(
        name="Type",
        description="Tessellation algorithm",
        items=[
            ('DELAUNAY',        "Delaunay",         "Tetrahedra-based tessellation"),
            ('VORONOI_BOOLEAN', "Voronoi Boolean",  "Cell Fracture-like boolean intersection — perfect surface fit"),
        ],
        default='VORONOI_BOOLEAN'
    )

    # ── Shared ──────────────────────────────────────────────────────────────
    use_weight_paint: BoolProperty(
        name="Use Weight Paint",
        description="Use vertex group weights for adaptive density",
        default=False
    )

    vertex_group_name: StringProperty(
        name="Vertex Group",
        description="Vertex group for weight paint",
        default=""
    )

    use_lloyd_relaxation: BoolProperty(
        name="Lloyd Relaxation",
        description="Apply Lloyd relaxation for more regular cells (Voronoi only)",
        default=False
    )

    lloyd_iterations: IntProperty(
        name="Lloyd Iterations",
        description="Number of Lloyd relaxation iterations",
        default=3,
        min=1,
        max=10
    )

    auto_cleanup: BoolProperty(
        name="Auto Cleanup",
        description="Automatically clean up geometry after tessellation",
        default=True
    )

    merge_threshold: FloatProperty(
        name="Merge Distance",
        description="Distance for merging duplicate vertices",
        default=0.0001,
        min=0.00001,
        max=1.0
    )

    decimate_planar: BoolProperty(
        name="Dissolve Planar",
        description="Merge coplanar faces",
        default=True
    )

    decimate_angle: FloatProperty(
        name="Planar Angle",
        description="Maximum angle for planar dissolution (degrees)",
        default=5.0,
        min=0.1,
        max=30.0
    )

    auto_name: BoolProperty(
        name="Auto-name Output",
        description="Automatically name output based on input mesh",
        default=True
    )

    output_name: StringProperty(
        name="Output Name",
        description="Name for the output mesh object",
        default="Tessellation_Output"
    )

    # ── Delaunay / Voronoi Clip ─────────────────────────────────────────────
    base_samples: IntProperty(
        name="Volume Samples",
        description="Number of internal points to generate (Delaunay / Voronoi Clip)",
        default=20,
        min=2,
        max=500
    )


    use_original_vertices: BoolProperty(
        name="Include Original Vertices",
        description="Include mesh vertices as tessellation points (Delaunay only)",
        default=True
    )

    # ── Voronoi Boolean (Cell Fracture) ─────────────────────────────────────
    num_cells: IntProperty(
        name="Number of Cells",
        description="Number of Voronoi seed points (= number of cells) for Boolean mode",
        default=20,
        min=2,
        max=500
    )

    boolean_solver: EnumProperty(
        name="Boolean Solver",
        description="Solver for boolean intersection",
        items=[
            ('EXACT',    "Exact",    "Most accurate, slower — best surface fit"),
            ('FLOAT',    "Float",    "Faster, less accurate for complex meshes"),
            ('MANIFOLD', "Manifold", "Fastest, requires manifold (watertight) meshes"),
        ],
        default='EXACT'
    )


# ============================================================================
# OPERATORS
# ============================================================================

class MESH_OT_check_scipy(Operator):
    """Check if scipy is installed"""
    bl_idname = "mesh.check_scipy"
    bl_label = "Check scipy"

    def execute(self, context):
        try:
            import scipy
            self.report({'INFO'}, f"scipy {scipy.__version__} is installed")
        except ImportError:
            self.report({'WARNING'}, "scipy is not installed")
        return {'FINISHED'}


class MESH_OT_install_scipy(Operator):
    """Install scipy dependency"""
    bl_idname = "mesh.install_scipy"
    bl_label = "Install scipy"

    def execute(self, context):
        self.report({'INFO'}, "Installing scipy... This may take a minute...")
        success = ensure_scipy_installed()
        if success:
            self.report({'INFO'}, "scipy installed! Please restart Blender.")
        else:
            self.report({'ERROR'}, "Failed to install scipy. Check console.")
        return {'FINISHED'}


class MESH_OT_tessellation_3d(Operator):
    """Generate 3D Tessellation (Delaunay, Voronoi Clip or Voronoi Boolean)"""
    bl_idname = "mesh.tessellation_3d"
    bl_label = "Generate Tessellation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH')

    def execute(self, context):
        if not scipy_available:
            self.report({'ERROR'}, "scipy not installed! Click 'Install scipy' first.")
            return {'CANCELLED'}

        obj = context.active_object
        props = context.scene.tessellation_props

        def report_progress(msg):
            print(msg)
            self.report({'INFO'}, msg)

        try:
            # Output name
            if props.auto_name:
                output_name = f"{obj.name}_{props.tessellation_type}"
            else:
                output_name = props.output_name

            # ──────────────────────────────────────────────────────────────────
            # DELAUNAY
            # ──────────────────────────────────────────────────────────────────
            if props.tessellation_type == 'DELAUNAY':
                tessellator = DelaunayTessellator(obj)
                weight_map = tessellator.get_vertex_weight_map(
                    props.use_weight_paint, props.vertex_group_name
                )

                points = tessellator.get_all_volume_points(
                    weight_map, props.base_samples, props.use_original_vertices,
                    report_progress
                )

                if len(points) < 4:
                    self.report({'ERROR'}, "Not enough points generated!")
                    tessellator.cleanup()
                    return {'CANCELLED'}

                result = tessellator.perform_tessellation(points, report_progress)
                if result is None:
                    self.report({'ERROR'}, "Tessellation failed!")
                    tessellator.cleanup()
                    return {'CANCELLED'}

                tri, points_array = result
                simplices = tessellator.filter_internal_simplices(tri, points_array, report_progress)

                if len(simplices) == 0:
                    self.report({'ERROR'}, "No internal tetrahedra found!")
                    tessellator.cleanup()
                    return {'CANCELLED'}

                faces = tessellator.extract_surface_faces(simplices, report_progress)
                final_obj, vertices, faces = tessellator.create_mesh(points_array, faces, output_name)

                if props.auto_cleanup:
                    cleanup_geometry(
                        final_obj, props.merge_threshold,
                        props.decimate_planar, props.decimate_angle, report_progress
                    )

                tessellator.cleanup()

                # Seleziona esclusivamente la mesh tassellata
                bpy.ops.object.select_all(action='DESELECT')
                final_obj.select_set(True)
                bpy.context.view_layer.objects.active = final_obj

                self.report({'INFO'},
                    f"Delaunay complete: {len(vertices)} verts, "
                    f"{len(simplices)} tetrahedra, {len(faces)} faces")

            # ──────────────────────────────────────────────────────────────────
            # VORONOI BOOLEAN — Cell Fracture-like (new)
            # ──────────────────────────────────────────────────────────────────
            elif props.tessellation_type == 'VORONOI_BOOLEAN':
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
                    progress_callback=report_progress
                )

                if final_obj is None:
                    self.report({'ERROR'}, "No cells generated! Check mesh normals and try again.")
                    tessellator.cleanup()
                    return {'CANCELLED'}

                if props.auto_cleanup:
                    cleanup_geometry(
                        final_obj, props.merge_threshold,
                        props.decimate_planar, props.decimate_angle, report_progress
                    )

                tessellator.cleanup()

                # Seleziona esclusivamente la mesh tassellata (fix: deseleziona la sorgente)
                bpy.ops.object.select_all(action='DESELECT')
                final_obj.select_set(True)
                bpy.context.view_layer.objects.active = final_obj

                self.report({'INFO'},
                    f"Voronoi Boolean complete: {len(final_obj.data.vertices)} verts, "
                    f"{len(final_obj.data.polygons)} faces -> '{output_name}'")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class MESH_OT_check_normals(Operator):
    """Check and fix mesh normals"""
    bl_idname = "mesh.check_normals"
    bl_label = "Check & Fix Normals"

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH')

    def execute(self, context):
        obj = context.active_object

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)

        non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
        non_manifold_verts = [v for v in bm.verts if not v.is_manifold]

        if non_manifold_edges or non_manifold_verts:
            msg = (
                f"Mesh NON MANIFOLD: {len(non_manifold_edges)} bordi e "
                f"{len(non_manifold_verts)} vertici problematici. "
                f"Correggi prima di applicare la tessellazione."
            )

            # Report visibile nella barra di stato in basso
            self.report({'WARNING'}, msg)

            # Popup modale ben visibile
            def draw_nonmanifold_popup(self_popup, context):
                layout = self_popup.layout
                layout.label(text="⚠  Mesh NON MANIFOLD rilevata!", icon='ERROR')
                layout.separator()
                layout.label(text=f"Bordi non-manifold: {len(non_manifold_edges)}", icon='EDGESEL')
                layout.label(text=f"Vertici non-manifold: {len(non_manifold_verts)}", icon='VERTEXSEL')
                layout.separator()
                layout.label(text="La tessellazione Voronoi Boolean richiede", icon='INFO')
                layout.label(text="una mesh watertight (chiusa e manifold).")
                layout.separator()
                layout.label(text="Suggerimenti: Mesh > Clean Up >")
                layout.label(text="  • Merge by Distance")
                layout.label(text="  • Fill Holes")
                layout.label(text="  • Delete Loose")

            bpy.context.window_manager.popup_menu(
                draw_nonmanifold_popup,
                title="Attenzione: Mesh Non-Manifold",
                icon='ERROR'
            )

        else:
            self.report({'INFO'}, "Mesh is manifold ✓")

        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)

        bpy.ops.object.mode_set(mode='OBJECT')
        self.report({'INFO'}, "Normals recalculated")
        return {'FINISHED'}


# ============================================================================
# SMOOTH SFD INTEGRATION
# ============================================================================

def ensure_smooth_sfd_loaded():
    """Load Smooth SFD node group from bundled .blend file.
    Compatible with Blender 4.2+ and 5.x on all platforms (including macOS).
    """
    node_group_name = "Smooth SFD"

    # Already loaded — nothing to do
    if node_group_name in bpy.data.node_groups:
        return True

    addon_dir = os.path.dirname(os.path.realpath(__file__))
    blend_file = os.path.join(addon_dir, "Smooth_SFD.blend")

    if not os.path.exists(blend_file):
        print(f"ERROR: Smooth_SFD.blend not found at: {blend_file}")
        return False

    print(f"Loading Smooth SFD from: {blend_file}")

    # ── Primary method: bpy.data.libraries.load (reliable on all platforms) ──
    # bpy.ops.wm.append is intentionally avoided here because it requires an
    # active UI context (not always available on macOS / background calls) and
    # can fail silently when invoked from a non-operator scope.
    try:
        with bpy.data.libraries.load(blend_file, link=False) as (data_from, data_to):
            available = list(data_from.node_groups)
            print(f"Node groups found in .blend: {available}")

            if node_group_name not in available:
                print(f"ERROR: '{node_group_name}' not found in {blend_file}")
                print(f"       Available node groups: {available}")
                return False

            data_to.node_groups = [node_group_name]

        if node_group_name in bpy.data.node_groups:
            print(f"✓ Smooth SFD loaded successfully")
            return True

        print("ERROR: libraries.load completed but node group is still missing")

    except Exception as e:
        print(f"ERROR while loading Smooth_SFD.blend: {e}")
        import traceback
        traceback.print_exc()

    # ── Fallback: wm.append (only works when a UI context is available) ──────
    print("Trying fallback method via wm.append...")
    try:
        bpy.ops.wm.append(
            filepath=os.path.join(blend_file, "NodeTree", node_group_name),
            directory=os.path.join(blend_file, "NodeTree"),
            filename=node_group_name,
            link=False,
        )
        if node_group_name in bpy.data.node_groups:
            print(f"✓ Smooth SFD loaded successfully via wm.append (fallback)")
            return True
    except Exception as e:
        print(f"Fallback wm.append also failed: {e}")

    print(f"ERROR: All methods failed — could not load Smooth SFD node group")
    return False


class MESH_OT_apply_smooth_sfd(Operator):
    """Apply Smooth SFD geometry nodes modifier to smooth tessellation edges"""
    bl_idname = "mesh.apply_smooth_sfd"
    bl_label = "Apply Smooth SFD"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH')

    def execute(self, context):
        obj = context.active_object

        if not ensure_smooth_sfd_loaded():
            self.report({'ERROR'}, "Smooth SFD asset not found! Check console for details.")
            return {'CANCELLED'}

        node_group_name = "Smooth SFD"

        if node_group_name not in bpy.data.node_groups:
            self.report({'ERROR'}, f"'{node_group_name}' node group not found!")
            return {'CANCELLED'}

        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group and mod.node_group.name == node_group_name:
                self.report({'INFO'}, "Smooth SFD already applied to this object")
                return {'FINISHED'}

        modifier = obj.modifiers.new(name="Smooth SFD", type='NODES')
        modifier.node_group = bpy.data.node_groups[node_group_name]

        self.report({'INFO'}, f"Smooth SFD applied to {obj.name}")
        return {'FINISHED'}


class MESH_OT_load_smooth_sfd(Operator):
    """Manually load Smooth SFD asset"""
    bl_idname = "mesh.load_smooth_sfd"
    bl_label = "Load Smooth SFD Asset"

    def execute(self, context):
        if "Smooth SFD" in bpy.data.node_groups:
            self.report({'INFO'}, "Smooth SFD already loaded")
            return {'FINISHED'}

        if ensure_smooth_sfd_loaded():
            self.report({'INFO'}, "Smooth SFD loaded successfully!")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Failed to load Smooth SFD. Check console for details.")
            return {'CANCELLED'}


# ============================================================================
# UI PANEL
# ============================================================================

class VIEW3D_PT_tessellation_3d(Panel):
    """Panel for 3D Tessellation addon"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tessellation'
    bl_label = "3D Tessellation"

    def draw(self, context):
        layout = self.layout
        props = context.scene.tessellation_props
        obj = context.active_object

        # ── Header ──────────────────────────────────────────────────────────
        box = layout.box()
        box.label(text="3D Tessellation v2.3", icon='MESH_ICOSPHERE')

        # ── scipy ────────────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Dependencies:", icon='PACKAGE')
        row = box.row(align=True)
        row.operator("mesh.check_scipy", icon='CHECKMARK')
        row.operator("mesh.install_scipy", icon='IMPORT')
        if scipy_available:
            try:
                import scipy
                box.label(text=f"✓ scipy {scipy.__version__}", icon='CHECKMARK')
            except:
                box.label(text="✓ scipy (restart required)", icon='INFO')
        else:
            box.label(text="✗ scipy not found", icon='ERROR')

        # ── Tessellation type ────────────────────────────────────────────────
        layout.separator()
        layout.prop(props, "tessellation_type", expand=True)

        # ── Info box ─────────────────────────────────────────────────────────
        box = layout.box()
        if props.tessellation_type == 'DELAUNAY':
            box.label(text="Delaunay:", icon='INFO')
            col = box.column(align=True)
            col.label(text="• Tetrahedra-based structure")
            col.label(text="• Ideal for FEM / physics sims")

        else:  # VORONOI_BOOLEAN
            box.label(text="Voronoi Boolean (Cell Fracture):", icon='INFO')
            col = box.column(align=True)
            col.label(text="• Each cell: boolean INTERSECT with source")
            col.label(text="• Perfect surface conformance")
            col.label(text="• Output: single joined mesh")
            col.label(text="• Needs watertight (manifold) mesh")

        # ── Parameters ───────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Parameters:", icon='PREFERENCES')
        col = box.column(align=True)

        if props.tessellation_type == 'DELAUNAY':
            col.prop(props, "base_samples")
            col.prop(props, "use_original_vertices")

        else:  # VORONOI_BOOLEAN
            col.prop(props, "num_cells")
            col.prop(props, "boolean_solver")

        col.separator()
        col.prop(props, "use_weight_paint")
        if props.use_weight_paint:
            if obj:
                col.prop_search(props, "vertex_group_name",
                               obj, "vertex_groups", text="Group")
            else:
                col.label(text="Select a mesh first", icon='ERROR')

        # ── Lloyd relaxation ─────────────────────────────────────────────────
        if props.tessellation_type != 'DELAUNAY':
            layout.separator()
            box = layout.box()
            box.label(text="Lloyd Relaxation:", icon='SMOOTHCURVE')
            col = box.column(align=True)
            col.prop(props, "use_lloyd_relaxation")
            if props.use_lloyd_relaxation:
                col.prop(props, "lloyd_iterations")
                col.label(text="More regular cell sizes", icon='INFO')

        # ── Geometry Cleanup ─────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Geometry Cleanup:", icon='BRUSH_DATA')
        col = box.column(align=True)
        col.prop(props, "auto_cleanup")
        if props.auto_cleanup:
            col.prop(props, "merge_threshold")
            col.prop(props, "decimate_planar")
            if props.decimate_planar:
                col.prop(props, "decimate_angle")

        # ── Output ────────────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Output:", icon='OUTLINER_OB_MESH')
        col = box.column(align=True)
        col.prop(props, "auto_name")
        if not props.auto_name:
            col.prop(props, "output_name")

        #if props.tessellation_type == 'VORONOI_BOOLEAN' and props.auto_name and obj:
        #    col.label(text=f"→ Collection: {obj.name}_VORONOI_BOOLEAN", icon='COLLECTION_NEW')

        # ── Action buttons ────────────────────────────────────────────────────
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("mesh.check_normals", icon='NORMALS_FACE')

        layout.separator()
        row = layout.row()
        row.scale_y = 1.8

        if obj and obj.type == 'MESH':
            if scipy_available:
                row.operator("mesh.tessellation_3d", icon='MOD_REMESH',
                             text="Generate Tessellation")
            else:
                row.label(text="Install scipy first", icon='ERROR')
        else:
            row.label(text="Select a mesh object", icon='ERROR')

        # ── Smooth SFD ────────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Edge Smoothing:", icon='MOD_SMOOTH')
        row = box.row()
        row.scale_y = 1.3
        if obj and obj.type == 'MESH':
            row.operator("mesh.apply_smooth_sfd", icon='GEOMETRY_NODES')
        else:
            row.label(text="Select a mesh object", icon='ERROR')
        col = box.column(align=True)
        col.label(text="Smooths edges via Geometry Nodes", icon='INFO')
        row2 = box.row()
        row2.scale_y = 0.8
        row2.operator("mesh.load_smooth_sfd", text="Load Asset Manually", icon='IMPORT')

        # ── Tips ──────────────────────────────────────────────────────────────
        layout.separator()
        box = layout.box()
        box.label(text="Quick Tips:", icon='QUESTION')
        col = box.column(align=True)
        col.label(text="1. Check & fix normals first")
        col.label(text="2. Higher samples or cells = more detail")
        col.label(text="3. Use weight paint for adaptive cells")
        if props.tessellation_type == 'VORONOI_BOOLEAN':
            col.label(text="4. EXACT solver = best surface fit")
            col.label(text="5. Lloyd ON = more uniform cells")




# ============================================================================
# REGISTRATION
# ============================================================================

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


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.tessellation_props = bpy.props.PointerProperty(
        type=TessellationProperties
    )

    print("3D Tessellation v2.3 registered.")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.tessellation_props


if __name__ == "__main__":
    register()
