bl_info = {
    "name" : "Motion-path pro",
    "author" : "Hamdi Amer", 
    "description" : "Update motion path in real time from graph editor and viewport",
    "blender" : (5, 0, 0),
    "version" : (2, 1, 0),
    "location" : "Graph Editor",
    "warning" : "",
    "doc_url": "", 
    "tracker_url": "", 
    "category" : "Graph" 
}



import bpy
import mathutils
import math
import gpu
import blf
import time
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from bpy.app.translations import pgettext_iface as iface_
from . import translations


class MotionPathState:
    def __init__(self):
        self.is_dragging = False
        self.drag_start_mouse = None
        self.drag_start_3d = None
        self.drag_start_item_pos = None
        self.selected_path_point = None
        self.selected_frame = None
        self.selected_handle_side = None
        self.selected_bone = None
        self.handle_points = []
        self.selected_handle_point = None
        self.selected_handle_data = None  # Store handle data directly to avoid index errors
        self.handle_dragging = False
        self.position_cache = {}
        self.initial_handle_values = {}  # Store initial handle values for drag: {(frame, array_index): value}
        self.draw_handler = None
        self.path_vertices = []
        self.path_batch = None
        
    def reset(self):
        self.__init__()


_state = MotionPathState()

# Global lock to prevent recursion in smart update
_is_updating_cache = False


HANDLE_SELECT_RADIUS = 20
SAFE_LIMIT = 1000000.0

def get_fcurves(action):
    try:
        if not action.layers or not action.slots:
            return []
        layer = action.layers[0]
        if not layer.strips:
            return []
        strip = layer.strips[0]
        slot = action.slots[0]
        channelbag = strip.channelbag(slot, ensure=True)
        return channelbag.fcurves
    except Exception:
        return []

def get_billboard_basis(context):
    try:
        if not context.space_data or not hasattr(context.space_data, 'region_3d'):
            return None, None
        rv3d = context.space_data.region_3d
        if not rv3d:
            return None, None
        view_rot = rv3d.view_rotation
        right = view_rot @ mathutils.Vector((1, 0, 0))
        up = view_rot @ mathutils.Vector((0, 1, 0))
        
        # Validate basis vectors
        if not all(math.isfinite(c) for c in right) or not all(math.isfinite(c) for c in up):
            return None, None
            
        return right, up
    except Exception:
        return None, None

def get_pixel_scale(context, pos, pixel_size):
    region = context.region
    rv3d = context.space_data.region_3d
    co2d = view3d_utils.location_3d_to_region_2d(region, rv3d, pos)
    if co2d is None:
        return 0.0
        
    right = rv3d.view_rotation @ mathutils.Vector((1, 0, 0))
    # Ensure pos is a Vector for math operations (it might be a tuple from safe drawing code)
    offset_pos = mathutils.Vector(pos) + right * 0.001
    co2d_offset = view3d_utils.location_3d_to_region_2d(region, rv3d, offset_pos)
    
    if co2d_offset is None:
        return 0.0
        
    pixel_dist = (co2d - co2d_offset).length
    if pixel_dist < 0.0001:
        return 0.0
        
    world_per_pixel = 0.001 / pixel_dist
    scale = pixel_size * world_per_pixel
    
    if not math.isfinite(scale) or scale > 10000.0:
        return 0.0
        
    return scale

def draw_billboard_circle(context, pos, radius_in_pixels, color, shader):
    # Validate position and unpack to floats for safety
    try:
        px, py, pz = pos[0], pos[1], pos[2]
        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and 
                abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
            return
    except Exception:
        return

    right, up = get_billboard_basis(context)
    if right is None or up is None:
        return

    # Unpack basis vectors to floats to avoid Vector operations in loop
    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return

    scale = get_pixel_scale(context, pos, radius_in_pixels)
    if scale == 0:
        return
    segments = 16
    # Use list of tuples instead of Vectors
    vertices = [(px, py, pz)]
    
    try:
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            
            # Pure float calculation, no mathutils.Vector needed in loop
            vx = px + scale * (cos_a * rx + sin_a * ux)
            vy = py + scale * (cos_a * ry + sin_a * uy)
            vz = pz + scale * (cos_a * rz + sin_a * uz)
            
            if not (math.isfinite(vx) and math.isfinite(vy) and math.isfinite(vz) and 
                    abs(vx) < SAFE_LIMIT and abs(vy) < SAFE_LIMIT and abs(vz) < SAFE_LIMIT):
                return
            vertices.append((vx, vy, vz))
    except Exception:
        return

    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def draw_billboard_square(context, pos, half_size_in_pixels, color, shader):
    try:
        px, py, pz = pos[0], pos[1], pos[2]
        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and 
                abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
            return
    except Exception:
        return

    right, up = get_billboard_basis(context)
    if right is None or up is None:
        return

    # Unpack basis
    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return

    scale = get_pixel_scale(context, pos, half_size_in_pixels)
    if scale == 0:
        return
    
    try:
        # Precompute vectors for corners (pure float)
        # corner 1: right - up
        c1x, c1y, c1z = rx - ux, ry - uy, rz - uz
        # corner 2: right + up
        c2x, c2y, c2z = rx + ux, ry + uy, rz + uz
        # corner 3: -right + up
        c3x, c3y, c3z = -rx + ux, -ry + uy, -rz + uz
        # corner 4: -right - up
        c4x, c4y, c4z = -rx - ux, -ry - uy, -rz - uz
        
        verts = (
            (px + scale * c1x, py + scale * c1y, pz + scale * c1z),
            (px + scale * c2x, py + scale * c2y, pz + scale * c2z),
            (px + scale * c3x, py + scale * c3y, pz + scale * c3z),
            (px + scale * c4x, py + scale * c4y, pz + scale * c4z),
        )
        
        for v in verts:
            if not (math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2]) and 
                    abs(v[0]) < SAFE_LIMIT and abs(v[1]) < SAFE_LIMIT and abs(v[2]) < SAFE_LIMIT):
                return
    except Exception:
        return
            
    indices = ((0, 1, 2), (0, 2, 3))
    batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

def draw_batched_billboard_circles(context, points, radius_in_pixels, color, shader, segments=8):
    if not points or radius_in_pixels <= 0 or segments <= 0 or not shader:
        return
    
    right, up = get_billboard_basis(context)
    if right is None or up is None:
        return
    
    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return
    
    # Precompute unit circle (pure floats)
    unit_verts = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        unit_verts.append((math.cos(angle), math.sin(angle)))
    
    # Batch processing - Reduced batch size to prevent driver crashes
    BATCH_SIZE = 500
    total_points = len(points)
    
    # Convert color to tuple if it's a Vector, for safety with GPU shader
    try:
        if hasattr(color, 'to_tuple'):
            safe_color = color.to_tuple()
        else:
            safe_color = tuple(float(c) for c in color)
            
        # Ensure color is RGBA
        if len(safe_color) == 3:
            safe_color = (safe_color[0], safe_color[1], safe_color[2], 1.0)
        elif len(safe_color) != 4:
            safe_color = (1.0, 1.0, 1.0, 1.0) # Fallback
    except Exception:
        safe_color = (1.0, 1.0, 1.0, 1.0)

    for i in range(0, total_points, BATCH_SIZE):
        try:
            batch_points = points[i : min(i + BATCH_SIZE, total_points)]
            
            all_vertices = []
            all_indices = []
            start_idx = 0
            
            for pos in batch_points:
                # Validate and unpack pos
                try:
                    px, py, pz = pos[0], pos[1], pos[2]
                except Exception:
                    continue

                if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and 
                        abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
                    continue

                scale = get_pixel_scale(context, pos, radius_in_pixels)
                if scale == 0: continue
                
                # Center
                center_vert = (px, py, pz)
                
                # Rim
                rim_verts = []
                valid_circle = True
                for x, y in unit_verts: # x, y are cos, sin
                    vx = px + scale * (x * rx + y * ux)
                    vy = py + scale * (x * ry + y * uy)
                    vz = pz + scale * (x * rz + y * uz)
                    
                    if not (math.isfinite(vx) and math.isfinite(vy) and math.isfinite(vz) and 
                            abs(vx) < SAFE_LIMIT and abs(vy) < SAFE_LIMIT and abs(vz) < SAFE_LIMIT):
                        valid_circle = False
                        break
                    rim_verts.append((vx, vy, vz))
                    
                if not valid_circle:
                    continue

                # Append vertices
                all_vertices.append(center_vert)
                all_vertices.extend(rim_verts)
                    
                # Indices
                # Center is at start_idx
                # Rim starts at start_idx + 1
                for k in range(segments):
                    v1 = start_idx + 1 + k
                    v2 = start_idx + 1 + ((k + 1) % segments)
                    all_indices.append((start_idx, v1, v2))
                    
                start_idx += (segments + 1)
            
            if not all_vertices or not all_indices:
                continue
                
            batch = batch_for_shader(shader, 'TRIS', {"pos": all_vertices}, indices=all_indices)
            shader.bind()
            shader.uniform_float("color", safe_color)
            batch.draw(shader)
            
            # Explicitly cleanup batch to prevent driver resource exhaustion
            del batch
        except Exception as e:
            print(f"Error drawing batch: {e}")
            continue

def is_location_fcurve(fcurve, bone_name=None):
    """Check if fcurve is a location fcurve for an object or a specific bone."""
    if bone_name:
        return fcurve.data_path == f'pose.bones["{bone_name}"].location'
    return fcurve.data_path == 'location'

def is_keyframe_at_frame(fcurves, frame_num, bone_name=None):
    """Check if there's a keyframe at the given frame for location fcurves."""
    for fcurve in fcurves:
        if is_location_fcurve(fcurve, bone_name):
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame_num) < 0.5:
                    return True
    return False

def calculate_path_from_fcurves(obj, action, frames, bone_name=None):
    """
    Calculate path points directly from fcurves, bypassing scene evaluation.
    Returns: {frame: {'position': Vector((x,y,z))}}
    """
    path_data = {}
    
    # Pre-fetch fcurves for location
    fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc, bone_name)]
    
    # Group by axis
    fcurves_by_axis = {}
    for fc in fcurves:
        fcurves_by_axis[fc.array_index] = fc
        
    # Get default values if fcurve missing (from current object state)
    # Note: This assumes defaults don't change over time (which is true if no fcurve)
    if bone_name:
        if bone_name in obj.pose.bones:
            defaults = obj.pose.bones[bone_name].location.copy()
        else:
            defaults = mathutils.Vector((0, 0, 0))
        delta_loc = mathutils.Vector((0, 0, 0)) # Bones don't have delta location usually
    else:
        defaults = obj.location.copy()
        delta_loc = obj.delta_location
    
    for frame in frames:
        pos = defaults.copy()
        for axis in range(3):
            if axis in fcurves_by_axis:
                pos[axis] = fcurves_by_axis[axis].evaluate(frame)
        
        # Apply Delta Location
        pos = pos + delta_loc
        
        path_data[frame] = {
            'position': pos
        }
        
    return path_data

def build_position_cache(context):
    """
    Build cache of 3D positions for keyframes and path line.

    UNIFIED FAST PATH (all objects and all bones):
      Always reads F-Curve values directly via fcurve.evaluate().
      scene.frame_set() is NEVER called — the scene state is never modified.
      This guarantees:
        - No interaction lag (G/R/S transforms are never disrupted).
        - Correct behaviour for rotation/scale constraints: the F-Curve-driven
          location is unaffected by constraints that only change rotation or scale.
          The corrected get_current_parent_matrix() ensures the displayed path is
          drawn without constraint-rotation contamination.
        - Bones with no location F-Curves (pure IK end-effectors, etc.) produce an
          empty frame set and are silently skipped — correct, nothing to display.

    COORDINATE SPACE CONTRACT:
      Object mode:
        Cached positions are in F-Curve local space:
          - Unparented: equals world space.
          - Parented:   equals parent-relative space (parent transform applied at draw).
        get_current_parent_matrix() returns Identity (unparented) or
        obj.parent.matrix_world (parented).

      Pose (bone) mode:
        Cached positions are in bone matrix_basis space (local bone offset).
        get_current_parent_matrix() returns:
          obj.matrix_world @ bone.parent.matrix @ bone.bone.matrix_local  (child bone)
          obj.matrix_world @ bone.bone.matrix_local                       (root bone)
        This converts the F-Curve offset to world space correctly without
        incorporating the bone's own constraint effects.

    NOTE on Smart Interaction:
      on_depsgraph_update skips this function when only OBJECT (not ACTION) changes,
      reusing the existing cache so interactive transforms (G/R/S) feel smooth.
    """
    global _state, _is_updating_cache
    
    # Atomic Lock: Prevent recursive updates
    if _is_updating_cache:
        return
        
    _is_updating_cache = True
    
    try:
        _state.position_cache = {}
        _state.path_vertices = []
        _state.path_batch = None
        
        obj = context.active_object
        
        # Combined early exit checks
        if (not obj or 
            not obj.animation_data or 
            not obj.animation_data.action or
            (hasattr(bpy.context.window_manager, 'skip_motion_path_cache') and 
             bpy.context.window_manager.skip_motion_path_cache)):
            return
                
        wm = context.window_manager
        action = obj.animation_data.action
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        
        # 1. Build Keyframe Cache (Sparse) for Handles and Points
        if obj.mode == 'POSE':
            bones_to_cache = set(context.selected_pose_bones or [])
            if context.active_pose_bone:
                bones_to_cache.add(context.active_pose_bone)

            # FAST PATH for all bones — read F-Curves directly, no frame_set needed.
            # Bones with constraints (IK, Damped Track, etc.) or drivers are handled
            # the same way: only the F-Curve-driven location offset is shown.
            # Bones with no location F-Curves (e.g. pure IK end-effectors) produce an
            # empty 'frames' set and are skipped — correct behaviour (nothing to display).
            for bone in bones_to_cache:
                bone_name = bone.name
                fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc, bone_name)]
                frames = set(int(kp.co[0]) for fc in fcurves for kp in fc.keyframe_points
                             if frame_start <= kp.co[0] <= frame_end)
                if not frames:
                    continue
                path_data = calculate_path_from_fcurves(obj, action, frames, bone_name=bone_name)
                _state.position_cache[bone_name] = path_data
        else:
            # OBJECT MODE — FAST PATH: read F-Curves directly for all objects.
            # Constraints / drivers that affect rotation or scale do not change the
            # F-Curve-driven location values, so this is always correct for position.
            # The parent matrix fix in get_current_parent_matrix ensures that
            # rotation-only constraints (Damped Track, etc.) no longer pollute the
            # displayed path.
            fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc)]
            frames = sorted(set(int(kp.co[0]) for fc in fcurves for kp in fc.keyframe_points
                         if frame_start <= kp.co[0] <= frame_end))
            path_data = calculate_path_from_fcurves(obj, action, frames)
            _state.position_cache[None] = path_data
    
        # 2. Build Path Line Batch (Dense) - Only if custom draw is active
        if wm.custom_path_draw_active:
            path_points = []
            # Determine which object/bone to trace
            target_bone = None
            if obj.mode == 'POSE':
                 # Use active pose bone for the path line
                 target_bone = context.active_pose_bone
                 if not target_bone and context.selected_pose_bones:
                     target_bone = context.selected_pose_bones[0]
            
            if (obj.mode == 'OBJECT') or (obj.mode == 'POSE' and target_bone):
                # Optimization: Only calculate path if there are location fcurves
                should_calculate_path = False
                
                if obj.mode == 'POSE' and target_bone:
                     if any(is_location_fcurve(fc, target_bone.name) for fc in get_fcurves(action)):
                         should_calculate_path = True
                else:
                     if any(is_location_fcurve(fc) for fc in get_fcurves(action)):
                         should_calculate_path = True
                
                if should_calculate_path:
                    # FAST PATH for path line — always read F-Curves directly.
                    # No frame_set; no scene state is touched.
                    target_bone_name = target_bone.name if (obj.mode == 'POSE' and target_bone) else None
                    frames_range = range(frame_start, frame_end + 1)
                    path_data = calculate_path_from_fcurves(obj, action, frames_range, bone_name=target_bone_name)
                    path_points = [path_data[f]['position'] for f in frames_range]
            
            _state.path_vertices = path_points
            if path_points:
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                _state.path_batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": path_points})
    
    finally:
        _is_updating_cache = False

def get_current_parent_matrix(context, obj, bone=None):
    """
    Unified calculation of the parent matrix (from cached-position space to world space).

    OBJECT mode:
      Positions are stored in 'parent-local' space (post-constraint world position for
      unparented objects, or post-constraint position relative to parent for parented
      objects). The correct transform to world space is therefore:
        - Unparented  → Identity  (positions ARE world positions)
        - Parented    → obj.parent.matrix_world  (parent's current world matrix)
      This avoids baking the object's own constraint effects (rotation, scale) into
      the parent matrix, which was the root cause of paths appearing to rotate when a
      rotation-only constraint (e.g. Damped Track) was active.

    POSE (bone) mode:
      Bone positions are stored in bone matrix_basis space (local translation offset
      driven by F-Curves). The parent matrix converts this to world space via:
          obj.matrix_world @ bone.parent.matrix @ bone.bone.matrix_local  (child bone)
          obj.matrix_world @ bone.bone.matrix_local                       (root bone)
      bone.bone.matrix_local is the REST-pose local matrix — unaffected by constraints.
      bone.parent.matrix is the parent's current POSE matrix — correctly reflects the
      animated parent chain while excluding this bone's own constraint effects.
      This mirrors the Object-mode fix: constraint effects on THIS bone cannot rotate
      or distort the displayed path.
      Also used for drag operations: parent_matrix.to_3x3().inverted() converts a
      world-space mouse offset to the F-Curve local space, giving correct drag direction
      even for bones with rotation constraints.
    """
    if obj.mode == 'POSE' and bone:
        # Bone Logic: derive parent matrix from the parent chain, NOT from this bone's
        # own final matrix.  Using bone.matrix (post-constraint) here produces the same
        # "spurious rotation residual" as the old object-mode formula did — the bone's
        # own rotation constraint (Damped Track, Look At, etc.) would contaminate the
        # parent matrix and make the displayed path appear rotated.
        #
        # Correct formula:
        #   parent_matrix = armature_world × parent_bone_pose × this_bone_rest_local
        #
        # bone.bone.matrix_local  = bone's 4x4 REST-pose matrix in armature local space
        #                           (independent of constraints, stable across frames).
        # bone.parent.matrix      = parent bone's POSE matrix in armature space
        #                           (includes parent's own constraints — correct, because
        #                           the parent's animated state defines the child's space).
        if bone.parent:
            return obj.matrix_world @ bone.parent.matrix @ bone.bone.matrix_local
        else:
            # Root bone: armature world matrix × bone's rest matrix in armature space.
            return obj.matrix_world @ bone.bone.matrix_local
    else:
        # Object Logic: derive from parent hierarchy directly.
        # Do NOT use matrix_world @ matrix_basis.inverted() here — that formula breaks
        # whenever a constraint (e.g. Damped Track) changes the object's rotation or
        # scale, because matrix_world then contains constraint effects that are absent
        # from matrix_basis, leaving a spurious rotation residual in the result.
        if obj.parent is None:
            # Unparented: F-Curve values / world positions are already in world space.
            return mathutils.Matrix.Identity(4)
        else:
            parent_mat = obj.parent.matrix_world.copy()
            # If parented to a specific bone, include that bone's transform.
            if obj.parent_type == 'BONE' and obj.parent_bone:
                if obj.parent.pose and obj.parent_bone in obj.parent.pose.bones:
                    pb = obj.parent.pose.bones[obj.parent_bone]
                    parent_mat = obj.parent.matrix_world @ pb.matrix
            return parent_mat

class DrawCollector:
    def __init__(self):
        self.lines = [] # flat list of vectors
        self.line_colors = [] # flat list of colors
        self.circles = {} # (radius, color) -> [pos]

    def add_line(self, p1, p2, color):
        try:
            # Validate points to prevent GPU driver crash
            if not (math.isfinite(p1[0]) and math.isfinite(p1[1]) and math.isfinite(p1[2]) and
                    math.isfinite(p2[0]) and math.isfinite(p2[1]) and math.isfinite(p2[2])):
                return
        except Exception:
            return

        self.lines.append(p1)
        self.lines.append(p2)
        self.line_colors.append(color)
        self.line_colors.append(color)

    def add_circle(self, pos, radius, color):
        # Round radius and color to avoid too many batches due to float precision
        r = round(radius, 2)
        
        # Ensure color is RGBA (4 components)
        if len(color) == 3:
            c_vals = (color[0], color[1], color[2], 1.0)
        elif len(color) >= 4:
            c_vals = (color[0], color[1], color[2], color[3])
        else:
            c_vals = (1.0, 1.0, 1.0, 1.0) # Fallback
            
        c = tuple(round(x, 3) for x in c_vals)
        
        key = (r, c)
        if key not in self.circles:
            self.circles[key] = []
        self.circles[key].append(pos)
        
    def draw(self, context):
        # Draw Lines
        if self.lines:
            try:
                shader = gpu.shader.from_builtin('SMOOTH_COLOR')
                batch = batch_for_shader(shader, 'LINES', {"pos": self.lines, "color": self.line_colors})
                shader.bind()
                
                # Explicitly set line width for handles to prevent inheriting path width
                wm = context.window_manager
                if hasattr(wm, 'motion_path_styles'):
                    gpu.state.line_width_set(wm.motion_path_styles.handle_line_width)
                else:
                    gpu.state.line_width_set(2.0)
                    
                batch.draw(shader)
            except Exception as e:
                print(f"Error drawing lines batch: {e}")
            
        # Draw Circles
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        for (radius, color), points in self.circles.items():
            draw_batched_billboard_circles(context, points, radius, color, shader)

def _build_ring_vertices(px, py, pz, scale, rx, ry, rz, ux, uy, uz, segments=32):
    """Build a list of 3D vertex tuples forming a screen-aligned ring."""
    verts = []
    for i in range(segments):
        angle = 2 * math.pi * i / segments
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        verts.append((
            px + scale * (cos_a * rx + sin_a * ux),
            py + scale * (cos_a * ry + sin_a * uy),
            pz + scale * (cos_a * rz + sin_a * uz),
        ))
    return verts


def draw_origin_indicator(context, obj, bone, styles):
    """Draw an origin indicator for the active object/bone on top of the motion path."""
    try:
        if bone is not None:
            world_pos = (obj.matrix_world @ bone.matrix).translation
        else:
            world_pos = obj.matrix_world.translation

        px = world_pos[0]
        py = world_pos[1]
        pz = world_pos[2]

        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and
                abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
            return

        pos = (px, py, pz)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        style = styles.origin_indicator_style
        outer_size = styles.origin_indicator_size
        outer_color = tuple(styles.origin_indicator_color)
        inner_color = tuple(styles.origin_indicator_inner_color)

        gpu.state.blend_set('ALPHA')

        if style == 'DOT':
            draw_billboard_circle(context, pos, outer_size / 2, inner_color, shader)

        elif style in {'RING', 'RING_DOT'}:
            right, up = get_billboard_basis(context)
            if right is None or up is None:
                return
            scale = get_pixel_scale(context, pos, outer_size / 2)
            if scale == 0:
                return
            ring_verts = _build_ring_vertices(
                px, py, pz, scale,
                right[0], right[1], right[2],
                up[0], up[1], up[2],
            )
            batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": ring_verts})
            shader.bind()
            shader.uniform_float("color", outer_color)
            gpu.state.line_width_set(2.0)
            batch.draw(shader)
            if style == 'RING_DOT':
                draw_billboard_circle(context, pos, outer_size / 6, inner_color, shader)

    except Exception as e:
        print(f"Error in draw_origin_indicator: {e}")


def draw_motion_path_overlay():
    """Drawing advanced motion path overlays"""
    # Dynamically get the context for the current draw call
    # This is crucial when switching workspaces or areas
    context = bpy.context

    try:
        # Safety check: Ensure we are in a 3D View context
        if not context.space_data or context.space_data.type != 'VIEW_3D':
             return

        wm = context.window_manager
        if not wm.direct_manipulation_active and not wm.custom_path_draw_active:
            return
        
        global _state
        obj = context.active_object
        if not obj:
            return

        styles = wm.motion_path_styles
        
        # Get current parent matrix for real-time update
        target_bone = None
        if obj.mode == 'POSE':
             target_bone = context.active_pose_bone
             if not target_bone and context.selected_pose_bones:
                 target_bone = context.selected_pose_bones[0]
        
        parent_matrix = get_current_parent_matrix(context, obj, target_bone)

        # Enable Alpha Blending for smoother edges
        gpu.state.blend_set('ALPHA')

        # Draw the continuous path line first
        if wm.custom_path_draw_active and _state.path_vertices:
            # Transform local vertices to world and validate explicitly
            # Replaces list comprehension to avoid Python 3.11/Vulkan crash (PyTuple_GetItem)
            world_points = []
            for v in _state.path_vertices:
                try:
                    # Transform
                    p = parent_matrix @ v
                    
                    # Explicit validation without using all() generator or implicit iteration
                    # Access components by index directly
                    px = p[0]
                    py = p[1]
                    pz = p[2]
                    
                    if (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and
                        abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
                        # Convert to pure tuple for GPU safety
                        world_points.append((px, py, pz))
                except Exception:
                    continue
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            
            if len(world_points) >= 2:
                batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": world_points})
                
                shader.bind()
                shader.uniform_float("color", styles.path_color) 
                gpu.state.line_width_set(styles.path_width)
                batch.draw(shader)
            
            # Draw Frame Points
            if styles.show_frame_points and world_points:
                draw_batched_billboard_circles(context, world_points, styles.frame_point_size / 2, styles.frame_point_color, shader, segments=8)
        
        _state.handle_points = []
        
        # Initialize Batch Collector
        collector = DrawCollector()
        
        if obj.mode == 'POSE':
            bones_to_draw = list(context.selected_pose_bones or [])
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_draw:
                bones_to_draw.append(active_bone)
            for bone in bones_to_draw:
                bone_parent_matrix = get_current_parent_matrix(context, obj, bone)
                draw_enhanced_path(context, obj, bone_parent_matrix, collector, bone=bone)
        else:
            draw_enhanced_path(context, obj, parent_matrix, collector)
            
        # Submit Batches
        collector.draw(context)

        # Draw origin indicator on top of motion path
        if styles.show_origin_indicator:
            draw_origin_indicator(context, obj, target_bone, styles)
        
    except Exception as e:
        print(f"Error in motion path overlay: {e}")
        import traceback
        traceback.print_exc()

def draw_enhanced_path(context, obj, parent_matrix, collector, bone=None):
    """Draw advanced motion path keyframe points and handles for an object or a pose bone."""
    global _state
    cache_key = bone.name if bone else None
    if cache_key not in _state.position_cache:
        return
    bone_name = bone.name if bone else None
    action = obj.animation_data.action if obj.animation_data else None

    # Pre-build frame→keyframe lookup to avoid O(frames × fcurves) scanning in the draw loop.
    # frame_keyframe_map: {frame_int: {array_index: BezierKeyframePoint}}
    frame_keyframe_map = {}
    frame_selected = set()
    if action:
        for fcurve in get_fcurves(action):
            if is_location_fcurve(fcurve, bone_name):
                for keyframe in fcurve.keyframe_points:
                    f = int(keyframe.co[0])
                    if f not in frame_keyframe_map:
                        frame_keyframe_map[f] = {}
                    frame_keyframe_map[f][fcurve.array_index] = keyframe
                    if keyframe.select_control_point:
                        frame_selected.add(f)

    for frame_num, cache_data in _state.position_cache[cache_key].items():
        local_point = cache_data['position']
        point_3d = parent_matrix @ local_point
        keyframes_for_location = frame_keyframe_map.get(frame_num, {})
        is_selected_keyframe = frame_num in frame_selected
        draw_motion_path_point(
            context, point_3d, frame_num,
            True, is_selected_keyframe,
            keyframes_for_location, action,
            None,
            bone=bone, parent_matrix=parent_matrix,
            collector=collector
        )

def draw_motion_path_point(context, point_3d, frame_num,
                           is_keyframe_point, is_selected_keyframe,
                           keyframes_for_location, action,
                           shader, bone=None, parent_matrix=None, collector=None):
    """Draw motion path points, with handles if needed"""
    global _state
    wm = context.window_manager
    styles = wm.motion_path_styles
    
    if _state.is_dragging and frame_num == _state.selected_frame:
        color = styles.selected_keyframe_point_color
        size = styles.keyframe_point_size
    elif is_selected_keyframe:
        color = styles.selected_keyframe_point_color
        size = styles.keyframe_point_size
    elif frame_num == context.scene.frame_current:
        color = (0.3, 0.7, 1.0, 1.0)  
        size = styles.keyframe_point_size * 0.8
    elif is_keyframe_point:
        color = styles.keyframe_point_color
        size = styles.keyframe_point_size
    else:
        return  
    
    
    if is_selected_keyframe or frame_num == context.scene.frame_current or (_state.is_dragging and frame_num == _state.selected_frame):
        
        for i in range(1, 4):
            glow_size = size + i * 2
            glow_alpha = 0.3 * (4 - i)
            
            glow_color = (
                min(1.0, color[0] + 0.3),
                min(1.0, color[1] + 0.3),
                min(1.0, color[2] + 0.3),
                glow_alpha
            )
            if collector:
                collector.add_circle(point_3d, glow_size / 2, glow_color)
    
    
    if is_selected_keyframe:
        if is_keyframe_point and keyframes_for_location:
            draw_motion_path_handles(context, point_3d, keyframes_for_location, shader, frame_num, bone=bone, parent_matrix=parent_matrix, collector=collector)

    if collector:
        collector.add_circle(point_3d, size / 2, color)

def draw_motion_path_handles(context, point_3d, keyframes_for_location, shader, frame_num, bone=None, parent_matrix=None, collector=None):
    """Draw motion path handles with individual control points"""
    global _state
    wm = context.window_manager
    styles = wm.motion_path_styles
    global_scale = wm.global_handle_visual_scale
    
    # NOTE: point_3d is already in World Space (transformed in caller)
    # parent_matrix is the current frame's parent matrix
    
    if parent_matrix is None:
        parent_matrix = mathutils.Matrix.Identity(4)
            
    rotation_matrix = parent_matrix.to_3x3()
    
    handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
    handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
    
    # Calculate Local Handle Vectors from F-Curve
    for array_index in range(3):
        if array_index in keyframes_for_location:
            keyframe = keyframes_for_location[array_index]
            if hasattr(keyframe, 'handle_left') and hasattr(keyframe, 'handle_right'):
                # Handle Vector = Handle Pos - Co
                # Left Handle (incoming)
                diff_left = keyframe.handle_left[1] - keyframe.co[1]
                # Right Handle (outgoing)
                diff_right = keyframe.handle_right[1] - keyframe.co[1]
                
                if array_index == 0: 
                    handle_vector_left.x = diff_left
                    handle_vector_right.x = diff_right
                elif array_index == 1: 
                    handle_vector_left.y = diff_left
                    handle_vector_right.y = diff_right
                elif array_index == 2: 
                    handle_vector_left.z = diff_left
                    handle_vector_right.z = diff_right
    
    # Transform to World Space
    # We use rotation_matrix @ vector because vectors are directions, not points
    world_vector_left = rotation_matrix @ handle_vector_left
    world_vector_right = rotation_matrix @ handle_vector_right
    
    # Draw Left Handle
    handle_left_pos = point_3d + (world_vector_left * global_scale)
    _state.handle_points.append({
        'position': handle_left_pos,
        'side': 'left',
        'frame': frame_num,
        'bone': bone
    })
    is_selected = (_state.selected_handle_point == len(_state.handle_points) - 1 and 
                  _state.handle_dragging)
    line_color = styles.handle_line_color if not is_selected else styles.selected_handle_line_color
    
    if collector:
        collector.add_line(point_3d, handle_left_pos, line_color)

    # Draw Right Handle
    handle_right_pos = point_3d + (world_vector_right * global_scale)
    _state.handle_points.append({
        'position': handle_right_pos,
        'side': 'right',
        'frame': frame_num,
        'bone': bone
    })
    is_selected = (_state.selected_handle_point == len(_state.handle_points) - 1 and 
                  _state.handle_dragging)
    line_color = styles.handle_line_color if not is_selected else styles.selected_handle_line_color
    
    if collector:
        collector.add_line(point_3d, handle_right_pos, line_color)
    
    # Draw Endpoints
    # Re-implementing the square drawing loop correctly
    # We always add 2 handles now (Left and Right).
    num_added = 2
    
    if num_added > 0:
        for i in range(num_added):
            idx = len(_state.handle_points) - num_added + i
            point = _state.handle_points[idx]
            
            is_selected = (idx == _state.selected_handle_point and _state.handle_dragging)
            if is_selected:
                color = styles.selected_handle_endpoint_color
                for j in range(1, 4):
                    glow_size = styles.handle_endpoint_size + j * 2
                    glow_alpha = 0.3 * (4 - j)
                    glow_color = (
                        min(1.0, color[0] + 0.2),
                        min(1.0, color[1] + 0.2),
                        min(1.0, color[2] + 0.2),
                        glow_alpha
                    )
                    if collector:
                        collector.add_circle(point['position'], glow_size / 2, glow_color)
            else:
                color = styles.handle_endpoint_color
            if collector:
                collector.add_circle(point['position'], styles.handle_endpoint_size / 2, color)

def enable_draw_handler(context):
    """Enable draw handler"""
    global _state
    if _state.draw_handler is None:
        # Pass empty tuple as args, so we don't bind to a stale context.
        # The callback function must then handle context retrieval itself.
        _state.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_motion_path_overlay, (), 'WINDOW', 'POST_VIEW')

def disable_draw_handler():
    """Disable custom drawing"""
    global _state
    if _state.draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state.draw_handler, 'WINDOW')
        _state.draw_handler = None

@persistent
def on_depsgraph_update(scene, depsgraph):
    """Smart update handler for motion paths"""
    global _state, _is_updating_cache
    
    # 1. Check Recursion Lock (Fast Path)
    # We still check here to avoid overhead of function call,
    # even though build_position_cache handles it too.
    if _is_updating_cache:
        return

    # 2. Check Dragging State (Conflict Resolution)
    # If operator is handling it, we do nothing.
    if _state.is_dragging or _state.handle_dragging:
        return

    wm = bpy.context.window_manager
    if not wm.custom_path_draw_active or wm.motion_path_update_mode != 'SMART':
        return

    # Check if we need to update
    # We care about Object transforms and Action data
    is_object_updated = depsgraph.id_type_updated('OBJECT')
    is_action_updated = depsgraph.id_type_updated('ACTION')
    
    if is_object_updated or is_action_updated:
        # Check if animation is playing to avoid heavy load during playback
        if bpy.context.screen and bpy.context.screen.is_animation_playing:
            return

        try:
            # Only update if there is an active object
            if bpy.context.active_object:
                # Detect Interaction: Object updated but Action (keyframes) did not.
                # This usually means the user is moving the object (G/Gizmo) but hasn't keyed it yet.
                is_interaction_update = is_object_updated and not is_action_updated
                
                # If we are in interaction mode, SKIP calculation entirely.
                # This reuses the existing cache (old path) for both Fast and Slow paths,
                # ensuring smooth object movement without lag or state resets.
                if is_interaction_update:
                    return

                # No need to manage lock manually here anymore.
                # build_position_cache handles atomic locking internally.
                build_position_cache(bpy.context)
                
                # Tag redraw for all 3D views
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
        except Exception as e:
            print(f"Error in smart update: {e}")

class MOTIONPATH_AutoUpdateMotionPaths(bpy.types.Operator):
    """Auto update motion paths when change keyframes"""
    bl_idname = "motion_path.auto_update_motion_paths"
    bl_label = "Auto Update Motion Paths"
    bl_description = "Real time update motion paths"
    bl_options = {'REGISTER', 'UNDO'}
    
    _timer = None
    _last_keyframe_values = None
    _needs_update = False
    
    @classmethod
    def poll(cls, context):
        return True
    
    def invoke(self, context, event):
        wm = context.window_manager
        self._last_keyframe_values = self._get_keyframe_values(context)
        self._last_active_obj_name = context.active_object.name if context.active_object else None
        self._last_bone_selection = self._get_bone_selection_state(context)
        self._needs_update = False
        
        # Register Smart Handler
        if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
            
        # Setup Timer for Timer Mode
        # We always create a timer to handle mode switching dynamically, 
        # but we only act on it if in TIMER mode.
        # Use auto_update_fps to calculate interval
        interval = 1.0 / max(1, wm.auto_update_fps)
        self._timer = wm.event_timer_add(interval, window=context.window)
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        wm = context.window_manager

        # Detect active object switch (Object mode)
        active_obj = context.active_object
        current_obj_name = active_obj.name if active_obj else None
        if current_obj_name != self._last_active_obj_name:
            self._last_active_obj_name = current_obj_name
            # Clear stale selection/drag state from the previous object
            _state.selected_path_point = None
            _state.selected_frame = None
            _state.selected_handle_side = None
            _state.selected_bone = None
            _state.selected_handle_point = None
            _state.selected_handle_data = None
            _state.is_dragging = False
            _state.handle_dragging = False
            self._needs_update = True

        # Check bone selection changes (Pose mode)
        current_bone_selection = self._get_bone_selection_state(context)
        if current_bone_selection != self._last_bone_selection:
            self._last_bone_selection = current_bone_selection
            self._needs_update = True
        
        # TIMER Mode Logic
        if wm.motion_path_update_mode == 'TIMER' and event.type == 'TIMER':
            current_values = self._get_keyframe_values(context)
            if current_values != self._last_keyframe_values:
                self._needs_update = True
                self._last_keyframe_values = current_values
                
        # Handle Updates
        if self._needs_update:
            try:
                build_position_cache(context)
            except Exception as e:
                print("Error updating position cache:", e)
            self._needs_update = False
            for window in wm.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        
        if not wm.auto_update_active:
            self.cancel(context)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}
    
    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
            
        # Remove Smart Handler
        if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    
    def _collect_object_keyframes(self, obj):
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return []
        action = obj.animation_data.action
        values = []
        for fcurve in get_fcurves(action):
            for keyframe in fcurve.keyframe_points:
                values.append((
                    keyframe.co[0], keyframe.co[1],
                    keyframe.handle_left[0], keyframe.handle_left[1],
                    keyframe.handle_right[0], keyframe.handle_right[1],
                    keyframe.select_control_point
                ))
        return values

    def _get_keyframe_values(self, context):
        active_object = context.active_object
        if not active_object:
            return None
        
        all_values = []
        
        # Current object
        all_values.extend(self._collect_object_keyframes(active_object))
        
        # Parent objects
        parent = active_object.parent
        while parent:
            all_values.extend(self._collect_object_keyframes(parent))
            parent = parent.parent
            
        return tuple(all_values) if all_values else None
    
    def _get_bone_selection_state(self, context):
        """Get current bone selection state"""
        active_object = context.active_object
        if not active_object or active_object.mode != 'POSE':
            return None
            
        active_bone_name = context.active_pose_bone.name if context.active_pose_bone else None
        selected_bone_names = tuple(sorted([b.name for b in context.selected_pose_bones])) if context.selected_pose_bones else ()
        
        return (active_bone_name, selected_bone_names)
    
class MOTIONPATH_SetHandleType(bpy.types.Operator):
    """Set handle type for selected keyframes"""
    bl_idname = "motion_path.set_handle_type"
    bl_label = "Set Handle Type"
    bl_options = {'REGISTER', 'UNDO'}
    
    handle_type: bpy.props.StringProperty()
    
    def execute(self, context):
        handle_type = self.handle_type
        if not handle_type:
            handle_type = context.window_manager.handle_type
        set_handle_type(context, handle_type)
        build_position_cache(context)
        return {'FINISHED'}



class MOTIONPATH_DirectManipulationToggle(bpy.types.Operator):
    """Enable/Disable Motion Path Editing"""
    bl_idname = "motion_path.direct_manipulation_toggle"
    bl_label = "Toggle Direct Manipulation"
    bl_description = "Enable/Disable Motion Path Editing"
    
    def execute(self, context):
        global _state
        wm = context.window_manager
        
        if not wm.direct_manipulation_active:
            wm.direct_manipulation_active = True
            bpy.ops.motion_path.direct_manipulation('INVOKE_DEFAULT')
            wm.auto_update_active = True
            bpy.ops.motion_path.auto_update_motion_paths('INVOKE_DEFAULT')
            self.report({'INFO'}, iface_("Enable Direct Path Editing"))
        else:
            wm.direct_manipulation_active = False
            wm.auto_update_active = False
            if context.area:
                context.area.tag_redraw()
            self.report({'INFO'}, iface_("Disable Direct Path Editing"))
        
        return {'FINISHED'}

def find_region_under_mouse(context, event):
    """
    Manually find the 3D View region under the mouse.
    This is required because 'context' in modal operators can be stale when switching workspaces.
    Returns: (region, space_data, local_mouse_pos) or (None, None, None)
    """
    mouse_x = event.mouse_x
    mouse_y = event.mouse_y

    # Support multi-window setups
    # Blender events are typically relative to the active window
    # We iterate over all windows to be safe
    
    target_window = None
    target_area = None
    target_region = None
    
    # Try current context window first
    windows_to_check = [context.window] if context.window else []
    # Then others
    for win in context.window_manager.windows:
        if win not in windows_to_check:
            windows_to_check.append(win)
            
    for window in windows_to_check:
        screen = window.screen
        if not screen: continue
        
        # Check all areas in this screen
        for area in screen.areas:
            # We only care about 3D Views
            if area.type != 'VIEW_3D':
                continue
                
            # Area bounds check (relative to window)
            if (area.x <= mouse_x < area.x + area.width and
                area.y <= mouse_y < area.y + area.height):
                
                # Check regions within area
                for region in area.regions:
                    if region.type == 'WINDOW': # The main viewport area
                        # Region bounds check
                        if (region.x <= mouse_x < region.x + region.width and
                            region.y <= mouse_y < region.y + region.height):
                            
                            # Found the specific region under mouse
                            local_x = mouse_x - region.x
                            local_y = mouse_y - region.y
                            space_data = area.spaces.active
                            return region, space_data, (local_x, local_y)

    return None, None, None

class MOTIONPATH_DirectManipulation(bpy.types.Operator):
    """Directly manipulate points on motion paths"""
    bl_idname = "motion_path.direct_manipulation"
    bl_label = "Direct Motion Path Manipulation"
    bl_options = {'REGISTER', 'UNDO'}
    
    _timer = None
    _mouse_pos = None
    _is_active = False
    _redraw_count = 0
    _last_frame = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer = None
        self._mouse_pos = None
        self._is_active = False
        self._redraw_count = 0
        self._last_frame = None
        self._last_draw_time = 0.0
    
    def convert_vector_handles_to_free(self, keyframes_for_location):
        """Convert vector handles to free handles to allow editing"""
        for array_index, keyframe in keyframes_for_location.items():
            if (keyframe.handle_left_type == 'VECTOR' and 
                keyframe.handle_right_type == 'VECTOR'):
                
                original_left = keyframe.handle_left.copy()
                original_right = keyframe.handle_right.copy()
                
                
                keyframe.handle_left_type = 'FREE'
                keyframe.handle_right_type = 'FREE'
                
                
                keyframe.handle_left = original_left
                keyframe.handle_right = original_right
    
    def modal(self, context, event):
        global _state
        
        # Override context with current global context to ensure we get the region under the mouse
        # This fixes issues when switching workspaces or areas
        context = bpy.context

        wm = context.window_manager
        if not wm.direct_manipulation_active or not self._is_active:
            return self.cancel(context)
        
        # REMOVED: Hardcoded block for Armature Object Mode
        # We now rely on hit-testing below to decide whether to intercept or pass through.
        # This fixes the issue where Armature objects could not have their motion paths edited in Object Mode.
        
        if event.type == 'MOUSEMOVE':
            self._mouse_pos = (event.mouse_region_x, event.mouse_region_y)
            
            # FPS Limiting
            target_interval = 1.0 / max(1, wm.motion_path_fps_limit)
            current_time = time.time()
            if (current_time - self._last_draw_time) < target_interval:
                return {'PASS_THROUGH'}
            self._last_draw_time = current_time
            
            # Use manual region finding to ensure we are interacting with the correct 3D View
            region, space_data, local_mouse_pos = find_region_under_mouse(context, event)
            if not region or not space_data:
                # Mouse is not over a 3D View, pass through event
                return {'PASS_THROUGH'}

            rv3d = space_data.region_3d

            if _state.is_dragging:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _state.drag_start_3d)

                if _state.selected_handle_side is None:
                    # Point dragging: incremental delta — anchor updated each frame so depth projection stays correct.
                    offset = new_3d_pos - _state.drag_start_3d
                    self.move_selected_points(context, offset)
                    _state.drag_start_3d = new_3d_pos
                else:
                    # Handle dragging: total offset from the original drag-start so handles don't drift.
                    total_offset = new_3d_pos - _state.drag_start_3d
                    self.move_selected_handles(context, total_offset, _state.selected_handle_side)

                try:
                    build_position_cache(context)
                except Exception:
                    pass

                if context.area and context.area.type == 'VIEW_3D':
                    context.area.tag_redraw()
                    
            elif _state.handle_dragging and _state.selected_handle_point is not None:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                
                # Use drag_start_3d as depth reference for consistent projection
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _state.drag_start_3d)
                total_offset = new_3d_pos - _state.drag_start_3d
                
                # Use cached handle data if available to avoid IndexError when handle_points changes
                if _state.selected_handle_data:
                    handle_point = _state.selected_handle_data
                    self.move_handle_point(context, total_offset, handle_point)
                elif _state.selected_handle_point is not None and _state.selected_handle_point < len(_state.handle_points):
                    handle_point = _state.handle_points[_state.selected_handle_point]
                    self.move_handle_point(context, total_offset, handle_point)
                
                # Update path line in real-time
                try:
                    build_position_cache(context)
                except Exception:
                    pass

                if context.area and context.area.type == 'VIEW_3D':
                    context.area.tag_redraw()
                    
            return {'PASS_THROUGH'}
        
        elif event.type == 'RIGHTMOUSE':
            if event.value == 'PRESS':
                # Use manual region finding
                region, space_data, local_mouse_pos = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d

                hit_point, hit_frame, hit_bone = self.get_motion_path_point_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _state.selected_path_point = hit_point
                    _state.selected_frame = hit_frame
                    
                    if context.mode == 'POSE':
                        _state.selected_bone = hit_bone
                    
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone.name if context.mode == 'POSE' and _state.selected_bone else None
                        
                        if not event.shift and not event.ctrl:
                            for fc in get_fcurves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        for fc in get_fcurves(action):
                            if is_location_fcurve(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    if context.area:
                        context.area.tag_redraw()
                    
                    bpy.ops.wm.call_menu(name="MOTIONPATH_MT_context_menu")
                    return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}

        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # Use manual region finding
                region, space_data, local_mouse_pos = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d

                if not event.shift:
                    _state.selected_handle_point = None
                    _state.selected_handle_data = None
                    _state.selected_path_point = None
                    _state.selected_frame = None
                
                handle_index, handle_point = get_handle_point_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if handle_index is not None:
                    _state.selected_handle_point = handle_index
                    _state.selected_handle_data = handle_point
                    _state.handle_dragging = True
                    _state.drag_start_3d = handle_point['position']
                    _state.drag_start_item_pos = handle_point['position']
                    # Store local mouse pos
                    _state.drag_start_mouse = local_mouse_pos
                    
                    # Capture initial values
                    self.capture_initial_handle_values(context, handle_point['frame'], handle_point['bone'].name if handle_point['bone'] else None, handle_point['side'])
                    
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = handle_point['bone'].name if handle_point['bone'] else None
                        frame = handle_point['frame']
                        
                        if not event.shift:
                            for fc in get_fcurves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        for fc in get_fcurves(action):
                            if is_location_fcurve(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    if context.area and context.area.type == 'VIEW_3D':
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                hit_side, hit_handle_pos, hit_frame, point_3d, hit_bone = self.get_motion_path_handle_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _state.selected_path_point = point_3d
                    _state.selected_frame = hit_frame
                    _state.selected_handle_side = hit_side
                    _state.drag_start_3d = point_3d  
                    _state.drag_start_item_pos = hit_handle_pos
                    # Store local mouse pos
                    _state.drag_start_mouse = local_mouse_pos
                    
                    # Capture initial values
                    self.capture_initial_handle_values(context, hit_frame, hit_bone.name if hit_bone else None, hit_side)
                    
                    if context.mode == 'POSE':
                        _state.selected_bone = hit_bone
                    
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone.name if context.mode == 'POSE' and _state.selected_bone else None
                        
                        for fc in get_fcurves(action):
                            if is_location_fcurve(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    _state.is_dragging = True
                    if context.area and context.area.type == 'VIEW_3D':
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                hit_point, hit_frame, hit_bone = self.get_motion_path_point_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _state.selected_path_point = hit_point
                    _state.selected_frame = hit_frame
                    _state.selected_handle_side = None  
                    _state.drag_start_3d = hit_point
                    _state.drag_start_item_pos = hit_point
                    _state.drag_start_mouse = local_mouse_pos
                    
                    if context.mode == 'POSE':
                        _state.selected_bone = hit_bone
                    
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone.name if context.mode == 'POSE' and _state.selected_bone else None
                        
                        if not event.shift and not event.ctrl:
                            for fc in get_fcurves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        if event.ctrl:
                            selected_frames = []
                            for fc in get_fcurves(action):
                                if is_location_fcurve(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        if kp.select_control_point:
                                            selected_frames.append(kp.co[0])
                            selected_frames.append(hit_frame)
                            if len(selected_frames) >= 2:
                                min_f = min(selected_frames)
                                max_f = max(selected_frames)
                                for fc in get_fcurves(action):
                                    if is_location_fcurve(fc, bone_name):
                                        for kp in fc.keyframe_points:
                                            if min_f <= kp.co[0] <= max_f:
                                                kp.select_control_point = True
                        else:
                            for fc in get_fcurves(action):
                                if is_location_fcurve(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        if abs(kp.co[0] - hit_frame) < 0.5:
                                            kp.select_control_point = True
                                            break
                    
                    _state.is_dragging = True
                    if context.area and context.area.type == 'VIEW_3D':
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                    
            elif event.value == 'RELEASE':
                if _state.is_dragging:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Points"))
                    _state.is_dragging = False
                    _state.selected_path_point = None
                    _state.selected_frame = None
                    _state.selected_handle_side = None
                    _state.drag_start_item_pos = None
                    
                    try:
                        build_position_cache(context)
                    except Exception:
                        pass
                    
                    if context.area and context.area.type == 'VIEW_3D':
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                elif _state.handle_dragging:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Handle"))
                    _state.handle_dragging = False
                    _state.selected_handle_point = None
                    _state.drag_start_item_pos = None
                    
                    try:
                        build_position_cache(context)
                    except Exception:
                        pass
                    
                    if context.area and context.area.type == 'VIEW_3D':
                        context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
        
        elif event.type == 'ESC':
            return {'PASS_THROUGH'}
        
        elif event.type == 'TIMER':
            if context.area and context.area.type == 'VIEW_3D':
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        
        # Explicitly pass through all other events (G, R, S, etc.)
        # This ensures we don't block standard Blender tools when not interacting with the path
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            build_position_cache(context)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            context.window_manager.modal_handler_add(self)
            self._is_active = True
            enable_draw_handler(context)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, iface_("View3D not found, cannot run operator"))
            return {'CANCELLED'}
    
    def cancel(self, context):
        global _state
        
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        
        _state.reset()
        self._is_active = False
        disable_draw_handler()
        
        if context.area:
            context.area.tag_redraw()
        
        return {'CANCELLED'}
    
    def move_selected_points(self, context, offset):
        # Validate input to prevent crash
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in offset):
            return

        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Motion Path Points")
        
        action = obj.animation_data.action
        bone = _state.selected_bone
        bone_name = bone.name if bone else None
        
        # Calculate parent matrix inverse to transform World Offset -> Local Offset (Parent Space)
        parent_matrix = get_current_parent_matrix(context, obj, bone)
        # We only care about rotation/scale for the offset vector
        parent_rot_inv = parent_matrix.to_3x3().inverted()
        
        # Transform offset to Local Space (Parent Space)
        bone_local_offset = parent_rot_inv @ offset
        
        selected_frames = set()
        for fcurve in get_fcurves(action):
            if 'location' not in fcurve.data_path:
                continue
            if bone_name and not is_location_fcurve(fcurve, bone_name):
                continue
            for kp in fcurve.keyframe_points:
                if kp.select_control_point:
                    selected_frames.add(int(kp.co[0]))
        
        for frame in selected_frames:
            for fcurve in get_fcurves(action):
                if 'location' not in fcurve.data_path:
                    continue
                if bone_name and not is_location_fcurve(fcurve, bone_name):
                    continue
                
                axis = fcurve.array_index
                for kp in fcurve.keyframe_points:
                    if abs(kp.co[0] - frame) < 0.5:
                        kp.co[1] += bone_local_offset[axis]
                        kp.handle_left[1] += bone_local_offset[axis]
                        kp.handle_right[1] += bone_local_offset[axis]
                        break
        
        for fcurve in get_fcurves(action):
            if 'location' in fcurve.data_path and (not bone_name or is_location_fcurve(fcurve, bone_name)):
                fcurve.update()
    
    def move_selected_handles(self, context, total_offset_world, side):
        # Validate input to prevent crash
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Motion Path Handles")
        
        action = obj.animation_data.action
        frame = _state.selected_frame
        global_scale = context.window_manager.global_handle_visual_scale
        bone = _state.selected_bone
        bone_name = bone.name if bone else None
        
        # Use helper to get current parent matrix
        parent_matrix = get_current_parent_matrix(context, obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        # Convert total offset to local space
        # Total Offset Local = Inverse(ParentRot) * Total Offset World
        total_offset_local = rotation_matrix.inverted() @ total_offset_world
        total_offset_local_scaled = total_offset_local / global_scale

        keyframes_for_location = {}
        for fcurve in get_fcurves(action):
            if not is_location_fcurve(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame) < 0.5:
                    keyframes_for_location[fcurve.array_index] = keyframe
                    break
        
        self.convert_vector_handles_to_free(keyframes_for_location)

        for array_index, keyframe in keyframes_for_location.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            # Retrieve initial handle value
            initial_val = _state.initial_handle_values.get((frame, array_index))
            if initial_val is None:
                continue # Should not happen if captured correctly
            
            initial_left = mathutils.Vector(initial_val) if side == 'left' else None
            initial_right = mathutils.Vector(initial_val) if side == 'right' else None
            
            # If side matches, initial_val is the handle pos. If not, we don't use it directly?
            # initial_handle_values stores the handle corresponding to 'side'
            # Wait, capture_initial_handle_values stores based on 'side'.
            # So _state.initial_handle_values[(frame, array_index)] IS the handle we are moving.
            
            initial_pos_2d = mathutils.Vector(initial_val)
            # initial_val is (x, y) tuple, but we only need the value for this axis (array_index).
            # Wait, F-Curve handle is (frame, value).
            # kp.handle_left is Vector((frame, value)).
            # initial_handle_values stores (kp.handle_left[0], kp.handle_left[1]).
            
            # New Handle Pos = Initial Handle Pos + Offset
            # But we only modify the Value (y), not Frame (x).
            # Actually, we might modify Frame (x) if we wanted to change timing, but here we only do value?
            # The offset is 3D (x,y,z).
            # offset_local[array_index] corresponds to the change in VALUE for that channel.
            
            if side == 'left':
                keyframe.handle_left[1] = initial_pos_2d[1] + total_offset_local_scaled[array_index]
                # Optional: Handle time change (x) if we supported it, but usually we constrain to frame.
            else:
                keyframe.handle_right[1] = initial_pos_2d[1] + total_offset_local_scaled[array_index]
            
            # Update opposite handle
            # For update_opposite_handle, we need a vector representing the CURRENT handle offset from Co.
            temp_handle_vector_local = mathutils.Vector((0.0, 0.0, 0.0))
            if side == 'left':
                temp_handle_vector_local[array_index] = keyframe.co[1] - keyframe.handle_left[1]
            else:
                temp_handle_vector_local[array_index] = keyframe.handle_right[1] - keyframe.co[1]
            
            self.update_opposite_handle(keyframe, side, temp_handle_vector_local, array_index)
            
            keyframe.handle_left_type = original_left_type
            keyframe.handle_right_type = original_right_type
        
        for fcurve in get_fcurves(action):
            if is_location_fcurve(fcurve, bone_name):
                fcurve.update()
    
    def update_opposite_handle(self, keyframe, moved_handle_side, handle_vector_local, array_index):
        """Update the opposite handle based on the moved handle and handle type"""
        if keyframe.handle_left_type == 'FREE' and keyframe.handle_right_type == 'FREE':
            return
        
        if keyframe.handle_left_type == 'VECTOR' or keyframe.handle_right_type == 'VECTOR':
            if moved_handle_side == 'left':
                keyframe.handle_right[1] = keyframe.co[1]
            else:
                keyframe.handle_left[1] = keyframe.co[1]
            return
        
        if (keyframe.handle_left_type in {'ALIGNED', 'AUTO', 'AUTO_CLAMPED'} or 
            keyframe.handle_right_type in {'ALIGNED', 'AUTO', 'AUTO_CLAMPED'}):
            
            # Use Slope Projection (Fixed X) instead of Length Preservation
            # This ensures the handle in Graph Editor only moves vertically, matching the active handle behavior.
            
            co = mathutils.Vector(keyframe.co)
            
            if moved_handle_side == 'left':
                handle_active = mathutils.Vector(keyframe.handle_left)
                handle_opposite = mathutils.Vector(keyframe.handle_right)
                target_handle_attr = 'handle_right'
            else:
                handle_active = mathutils.Vector(keyframe.handle_right)
                handle_opposite = mathutils.Vector(keyframe.handle_left)
                target_handle_attr = 'handle_left'
            
            # Calculate slope of the active handle
            dx_active = handle_active.x - co.x
            dy_active = handle_active.y - co.y
            
            if abs(dx_active) < 0.0001:
                # Active handle is vertical (unlikely in F-Curve), skip to avoid division by zero
                return

            slope = dy_active / dx_active
            
            # Apply slope to opposite handle, preserving its X offset
            dx_opposite = handle_opposite.x - co.x
            new_y_opposite = co.y + (slope * dx_opposite)
            
            # Update only the Y component of the opposite handle
            if target_handle_attr == 'handle_right':
                keyframe.handle_right[1] = new_y_opposite
            else:
                keyframe.handle_left[1] = new_y_opposite
            
            return
    
    def move_handle_point(self, context, total_offset_world, handle_point):
        """Move a handle control point using total offset from initial position"""
        # Validate input to prevent crash
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Handle Point")
        
        action = obj.animation_data.action
        frame = handle_point['frame']
        side = handle_point['side']
        bone = handle_point['bone']
        bone_name = bone.name if bone else None
        global_scale = context.window_manager.global_handle_visual_scale
        
        # Use helper
        parent_matrix = get_current_parent_matrix(context, obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        # Convert total offset to local space
        total_offset_local = rotation_matrix.inverted() @ total_offset_world
        total_offset_local_scaled = total_offset_local / global_scale
        
        keyframes_for_location = {}
        for fcurve in get_fcurves(action):
            if not is_location_fcurve(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame) < 0.5:
                    keyframes_for_location[fcurve.array_index] = keyframe
                    break
        
        self.convert_vector_handles_to_free(keyframes_for_location)
        
        for array_index, keyframe in keyframes_for_location.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            if original_left_type in {'AUTO', 'AUTO_CLAMPED'} or original_right_type in {'AUTO', 'AUTO_CLAMPED'}:
                keyframe.handle_left_type = 'ALIGNED'
                keyframe.handle_right_type = 'ALIGNED'
            
            # Retrieve initial handle value
            initial_val = _state.initial_handle_values.get((frame, array_index))
            if initial_val is None:
                continue
            
            initial_pos_2d = mathutils.Vector(initial_val)
            
            # Apply offset to initial value
            if side == 'left':
                if hasattr(keyframe, 'handle_left'):
                    keyframe.handle_left[0] = initial_pos_2d[0]
                    keyframe.handle_left[1] = initial_pos_2d[1] + total_offset_local_scaled[array_index]
            else:
                if hasattr(keyframe, 'handle_right'):
                    keyframe.handle_right[0] = initial_pos_2d[0]
                    keyframe.handle_right[1] = initial_pos_2d[1] + total_offset_local_scaled[array_index]
            
            # Update opposite handle
            temp_handle_vector_local = mathutils.Vector((0.0, 0.0, 0.0))
            if side == 'left':
                temp_handle_vector_local[array_index] = keyframe.co[1] - keyframe.handle_left[1]
            else:
                temp_handle_vector_local[array_index] = keyframe.handle_right[1] - keyframe.co[1]

            self.update_opposite_handle(keyframe, side, temp_handle_vector_local, array_index)
            
            if original_left_type in {'VECTOR', 'FREE'}:
                keyframe.handle_left_type = original_left_type
            if original_right_type in {'VECTOR', 'FREE'}:
                keyframe.handle_right_type = original_right_type
        
        for fcurve in get_fcurves(action):
            if is_location_fcurve(fcurve, bone_name):
                fcurve.update()
    
    def get_keyframe_position_for_handle(self, context, handle_point):
        """Helper function to get the 3D position of the keyframe associated with a handle point."""
        global _state
        obj = context.active_object
        frame = handle_point['frame']
        bone = handle_point['bone']
        bone_name = bone.name if bone else None
        
        if bone_name in _state.position_cache:
            cache_data = _state.position_cache[bone_name].get(frame)
            if cache_data:
                return cache_data['position']
        elif None in _state.position_cache:
            cache_data = _state.position_cache[None].get(frame)
            if cache_data:
                return cache_data['position']
        
        return mathutils.Vector((0, 0, 0))
    
    def capture_initial_handle_values(self, context, frame_num, selected_bone_name, handle_side):
        """Capture initial handle values at the start of drag."""
        global _state
        _state.initial_handle_values = {}
        
        obj = context.active_object
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        fcurves = get_fcurves(action)
        
        # Filter fcurves for location
        keyframes_for_location = {}
        for i, fcurve in enumerate(fcurves):
            if is_location_fcurve(fcurve, selected_bone_name):
                for kp in fcurve.keyframe_points:
                    if abs(kp.co[0] - frame_num) < 0.001:
                        array_index = fcurve.array_index
                        keyframes_for_location[array_index] = kp
                        break
        
        if not keyframes_for_location:
            return
        
        for array_index, kp in keyframes_for_location.items():
            if handle_side == 'left':
                _state.initial_handle_values[(frame_num, array_index)] = (kp.handle_left[0], kp.handle_left[1])
            else:
                _state.initial_handle_values[(frame_num, array_index)] = (kp.handle_right[0], kp.handle_right[1])

    def get_motion_path_handle_at_mouse(self, context, event, region=None, rv3d=None, local_mouse_pos=None):
        """Check if the mouse is over a handle end on the motion path"""
        if not region or not rv3d:
            if not context.space_data or context.space_data.type != 'VIEW_3D':
                 return None, None, None, None, None
            region = context.region
            rv3d = context.space_data.region_3d
        
        if local_mouse_pos:
            mouse_pos = mathutils.Vector(local_mouse_pos)
        else:
            mouse_pos = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))

        obj = context.active_object
        
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return None, None, None, None, None
        
        action = obj.animation_data.action
        
        # Helper to check handles for a specific bone/object and frame
        def check_handles_at_frame(bone_name, frame_num, point_3d, parent_matrix, bone_obj=None):
            if not is_keyframe_at_frame(get_fcurves(action), frame_num, bone_name):
                return None
            
            keyframes_for_location = {}
            for fcurve in get_fcurves(action):
                if is_location_fcurve(fcurve, bone_name):
                    for keyframe in fcurve.keyframe_points:
                        if abs(keyframe.co[0] - frame_num) < 0.5:
                            keyframes_for_location[fcurve.array_index] = keyframe
                            break
            
            if not keyframes_for_location:
                return None
            
            handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
            handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
            
            for array_index, keyframe in keyframes_for_location.items():
                diff = keyframe.handle_left[1] - keyframe.co[1]
                handle_vector_left[array_index] = diff
                diff = keyframe.handle_right[1] - keyframe.co[1]
                handle_vector_right[array_index] = diff
            
            rotation_matrix = parent_matrix.to_3x3()
            world_vector_left = rotation_matrix @ handle_vector_left
            world_vector_right = rotation_matrix @ handle_vector_right
            
            global_scale = context.window_manager.global_handle_visual_scale
            
            # Check Left Handle
            handle_left_pos = point_3d + (world_vector_left * global_scale)
            screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_left_pos)
            if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                return 'left', handle_left_pos
            
            # Check Right Handle
            handle_right_pos = point_3d + (world_vector_right * global_scale)
            screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_right_pos)
            if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                return 'right', handle_right_pos
            
            return None

        if obj.mode == 'POSE':
            # Check selected bones
            bones_to_check = list(context.selected_pose_bones)
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_check:
                bones_to_check.append(active_bone)
                
            for bone in bones_to_check:
                bone_name = bone.name
                if bone_name not in _state.position_cache:
                    continue
                
                parent_matrix = get_current_parent_matrix(context, obj, bone)
                
                for frame_num, cache_data in _state.position_cache[bone_name].items():
                    # Transform cached local position to world
                    point_3d = parent_matrix @ cache_data['position']
                    
                    result = check_handles_at_frame(bone_name, frame_num, point_3d, parent_matrix, bone)
                    if result:
                        side, handle_pos = result
                        return side, handle_pos, frame_num, point_3d, bone
            
            return None, None, None, None, None
            
        else:
            # Object Mode
            if None not in _state.position_cache:
                return None, None, None, None, None
            
            parent_matrix = get_current_parent_matrix(context, obj)
            
            for frame_num, cache_data in _state.position_cache[None].items():
                # Transform cached local position to world
                point_3d = parent_matrix @ cache_data['position']
                
                result = check_handles_at_frame(None, frame_num, point_3d, parent_matrix)
                if result:
                    side, handle_pos = result
                    return side, handle_pos, frame_num, point_3d, None
        
        return None, None, None, None, None
    
    def get_motion_path_point_at_mouse(self, context, event, region=None, rv3d=None, local_mouse_pos=None):
        """Check if the mouse is over a motion path point"""
        if not region or not rv3d:
            if not context.space_data or context.space_data.type != 'VIEW_3D':
                return None, None, None
            region = context.region
            rv3d = context.space_data.region_3d

        if local_mouse_pos:
            mouse_pos = mathutils.Vector(local_mouse_pos)
        else:
            mouse_pos = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
            
        obj = context.active_object
        
        if not obj:
            return None, None, None
        
        if obj.mode == 'POSE':
            for bone in context.selected_pose_bones:
                if bone.name not in _state.position_cache:
                    continue
                
                parent_matrix = get_current_parent_matrix(context, obj, bone)
                
                for frame_num, cache_data in _state.position_cache[bone.name].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        return world_pos, frame_num, bone
            
            active_bone = context.active_pose_bone
            if active_bone:
                if active_bone.name not in _state.position_cache:
                    return None, None, None
                
                parent_matrix = get_current_parent_matrix(context, obj, active_bone)
                
                for frame_num, cache_data in _state.position_cache[active_bone.name].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        return world_pos, frame_num, active_bone
            
            return None, None, None
        else:
            if None not in _state.position_cache:
                return None, None, None
            
            parent_matrix = get_current_parent_matrix(context, obj)
            
            for frame_num, cache_data in _state.position_cache[None].items():
                local_pos = cache_data['position']
                world_pos = parent_matrix @ local_pos
                
                screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                    return world_pos, frame_num, None
        
        return None, None, None

def get_handle_point_at_mouse(context, event, region=None, rv3d=None, local_mouse_pos=None):
    """Check if the mouse is over a handle control point"""
    global _state
    
    # Safety check: Ensure we are in a 3D View context if no region/rv3d provided
    if not region or not rv3d:
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return None, None
        region = context.region
        rv3d = context.space_data.region_3d

    if local_mouse_pos:
        mouse_pos = mathutils.Vector(local_mouse_pos)
    else:
        mouse_pos = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
    
    for i, handle_point in enumerate(_state.handle_points):
        screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_point['position'])
        if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
            return i, handle_point
    return None, None

def set_handle_type(context, handle_type):
    """Set handle type for selected keyframes and apply interactions"""
    obj = context.active_object
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return
    action = obj.animation_data.action
    bone_name = None
    if obj.mode == 'POSE':
        bone = context.active_pose_bone
        if bone:
            bone_name = bone.name
    for fcurve in get_fcurves(action):
        if not is_location_fcurve(fcurve, bone_name):
            continue
        for keyframe in fcurve.keyframe_points:
            if keyframe.select_control_point:
                keyframe.handle_left_type = handle_type
                keyframe.handle_right_type = handle_type
                if handle_type == 'ALIGNED' or handle_type in {'AUTO', 'AUTO_CLAMPED'}:
                    vec = mathutils.Vector(keyframe.co) - mathutils.Vector(keyframe.handle_left)
                    # Keep original length of the right handle
                    len_right = (mathutils.Vector(keyframe.handle_right) - mathutils.Vector(keyframe.co)).length
                    if vec.length > 0.0001:
                        vec.normalize()
                        keyframe.handle_right = mathutils.Vector(keyframe.co) + vec * len_right
                elif handle_type == 'VECTOR':
                    keyframe.handle_left[1] = keyframe.co[1]
                    keyframe.handle_right[1] = keyframe.co[1]
        fcurve.update()






def _find_and_start_motion_path_operators(context):
    """Find first available 3D View and start the motion path operators.
    Returns True if a view was found and operators started, False otherwise.
    """
    wm = context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    with context.temp_override(window=window, area=area, region=region):
                        if not wm.direct_manipulation_active:
                            wm.direct_manipulation_active = True
                            bpy.ops.motion_path.direct_manipulation('INVOKE_DEFAULT')
                        if not wm.auto_update_active:
                            wm.auto_update_active = True
                            bpy.ops.motion_path.auto_update_motion_paths('INVOKE_DEFAULT')
                    return True
    return False


def _stop_motion_path_operators(context):
    """Stop motion path operators and clear active flags."""
    wm = context.window_manager
    wm.direct_manipulation_active = False
    wm.auto_update_active = False


class MOTIONPATH_ToggleCustomDraw(bpy.types.Operator):
    """Toggle Custom Motion Path Drawing"""
    bl_idname = "motion_path.toggle_custom_draw"
    bl_label = "Toggle Custom Path"
    bl_description = "Enable/Disable Custom Motion Path Drawing"

    def execute(self, context):
        wm = context.window_manager
        new_state = not wm.custom_path_draw_active
        wm.custom_path_draw_active = new_state

        if new_state:
            if not _find_and_start_motion_path_operators(context):
                self.report({'WARNING'}, iface_("Enabled Motion Path, but no 3D View found for interaction."))
        else:
            _stop_motion_path_operators(context)

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}

class MotionPathStyleSettings(bpy.types.PropertyGroup):
    # Path
    path_width: bpy.props.FloatProperty(name="Path Width", default=2.0, min=1.0, max=10.0)
    path_color: bpy.props.FloatVectorProperty(name="Path Color", subtype='COLOR', size=4, default=(0.8, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    
    # Frame Points
    show_frame_points: bpy.props.BoolProperty(name="Show Frame Points", default=True)
    frame_point_size: bpy.props.FloatProperty(name="Frame Point Size", default=4.0, min=1.0, max=20.0)
    frame_point_color: bpy.props.FloatVectorProperty(name="Frame Point Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0)
    
    # Keyframe Points
    keyframe_point_size: bpy.props.FloatProperty(name="Keyframe Size", default=10.0, min=1.0, max=30.0)
    keyframe_point_color: bpy.props.FloatVectorProperty(name="Keyframe Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_keyframe_point_color: bpy.props.FloatVectorProperty(name="Selected Keyframe Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)
    
    # Handles
    handle_line_width: bpy.props.FloatProperty(name="Handle Line Width", default=2.0, min=1.0, max=10.0)
    handle_line_color: bpy.props.FloatVectorProperty(name="Handle Line Color", subtype='COLOR', size=4, default=(0.0, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_line_color: bpy.props.FloatVectorProperty(name="Selected Handle Line Color", subtype='COLOR', size=4, default=(1.0, 0.776, 0.561, 1.0), min=0.0, max=1.0)
    
    handle_endpoint_size: bpy.props.FloatProperty(name="Handle Endpoint Size", default=7.0, min=1.0, max=20.0)
    handle_endpoint_color: bpy.props.FloatVectorProperty(name="Handle Endpoint Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_endpoint_color: bpy.props.FloatVectorProperty(name="Selected Handle Endpoint Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)

    # Origin Indicator
    show_origin_indicator: bpy.props.BoolProperty(name="Show Origin Indicator", default=True)
    origin_indicator_style: bpy.props.EnumProperty(
        name="Origin Style",
        items=[
            ('RING',     "Ring",     "Hollow circle ring"),
            ('DOT',      "Dot",      "Filled circle dot"),
            ('RING_DOT', "Ring+Dot", "Ring with center dot (like Blender origin)"),
        ],
        default='RING_DOT')
    origin_indicator_size: bpy.props.FloatProperty(name="Origin Size", default=12.0, min=4.0, max=40.0)
    origin_indicator_color: bpy.props.FloatVectorProperty(name="Origin Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 0.9), min=0.0, max=1.0)
    origin_indicator_inner_color: bpy.props.FloatVectorProperty(name="Origin Inner Color", subtype='COLOR', size=4, default=(1.0, 0.4, 0.0, 1.0), min=0.0, max=1.0)

class MOTIONPATH_PT_header_settings(bpy.types.Panel):
    bl_label = "Motion Path Settings"
    bl_idname = "MOTIONPATH_PT_header_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        
        layout.label(text=iface_("Performance"))
        
        layout.label(text=iface_("Update Mode"))
        row = layout.row()
        row.prop(wm, "motion_path_update_mode", expand=True)
        
        layout.prop(wm, "motion_path_fps_limit", text=iface_("Interaction FPS"))
        if wm.motion_path_update_mode == 'TIMER':
            layout.prop(wm, "auto_update_fps", text=iface_("Auto Update FPS"))

class MOTIONPATH_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        styles = wm.motion_path_styles
        
        col = layout.column()
        col.label(text=iface_("Style Settings"))
        col.prop(styles, "path_width")
        col.prop(styles, "path_color")
        
        col.separator()
        col.prop(styles, "show_frame_points")
        if styles.show_frame_points:
            col.prop(styles, "frame_point_size")
            col.prop(styles, "frame_point_color")
            
        col.separator()
        col.label(text=iface_("Keyframes"))
        col.prop(styles, "keyframe_point_size")
        col.prop(styles, "keyframe_point_color")
        col.prop(styles, "selected_keyframe_point_color")
        
        col.separator()
        col.label(text=iface_("Handles"))
        col.prop(styles, "handle_line_width")
        col.prop(styles, "handle_line_color")
        col.prop(styles, "selected_handle_line_color")
        col.prop(styles, "handle_endpoint_size")
        col.prop(styles, "handle_endpoint_color")
        col.prop(styles, "selected_handle_endpoint_color")

        col.separator()
        col.label(text=iface_("Origin Indicator"))
        col.prop(styles, "show_origin_indicator")
        if styles.show_origin_indicator:
            col.prop(styles, "origin_indicator_style")
            col.prop(styles, "origin_indicator_size")
            col.prop(styles, "origin_indicator_color")
            if styles.origin_indicator_style in {'RING_DOT', 'DOT'}:
                col.prop(styles, "origin_indicator_inner_color")

class MOTIONPATH_MT_context_menu(bpy.types.Menu):
    bl_label = "Motion Path Context Menu"
    bl_idname = "MOTIONPATH_MT_context_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("motion_path.set_handle_type", text=iface_("Free")).handle_type = 'FREE'
        layout.operator("motion_path.set_handle_type", text=iface_("Aligned")).handle_type = 'ALIGNED'
        layout.operator("motion_path.set_handle_type", text=iface_("Vector")).handle_type = 'VECTOR'
        layout.operator("motion_path.set_handle_type", text=iface_("Auto")).handle_type = 'AUTO'
        layout.operator("motion_path.set_handle_type", text=iface_("Auto Clamped")).handle_type = 'AUTO_CLAMPED'

def ensure_location_keyframes(context, obj):
    """
    Ensure that for every frame where a location keyframe exists on any axis,
    keyframes exist on all 3 axes (X, Y, Z).
    """
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    
    # Determine targets: (data_path_prefix, bone_name_for_check)
    targets = []
    if obj.mode == 'POSE':
        # In Pose mode, only process selected bones
        if context.selected_pose_bones:
            for bone in context.selected_pose_bones:
                 targets.append((f'pose.bones["{bone.name}"].location', bone.name))
    else:
        # In Object mode, process object location
        targets.append(('location', None))

    # Use get_fcurves helper to handle Blender 5.0+ Actions
    fcurves_collection = get_fcurves(action)
    if isinstance(fcurves_collection, list) and not fcurves_collection:
        # If empty list, we might not have access to create new curves easily if structure is missing
        # But if we are here, we probably have some keyframes, so try to re-fetch or fail gracefully
        return

    for data_path_base, bone_name in targets:
        # 1. Collect all existing frames for this target's location
        all_frames = set()
        # Also keep track of which indices exist at which frame
        # frame -> set of existing indices (0, 1, 2)
        frame_indices = {} 
        
        target_fcurves = []
        # Iterate over fcurves_collection instead of action.fcurves
        for fc in fcurves_collection:
            if fc.data_path == data_path_base:
                target_fcurves.append(fc)
                for kp in fc.keyframe_points:
                    frame = int(round(kp.co[0])) # Use integer frames for alignment
                    all_frames.add(frame)
                    if frame not in frame_indices:
                        frame_indices[frame] = set()
                    frame_indices[frame].add(fc.array_index)
        
        if not target_fcurves:
            continue

        # 2. Fill missing frames
        sorted_frames = sorted(list(all_frames))
        
        modified = False
        
        for frame in sorted_frames:
            existing_indices = frame_indices.get(frame, set())
            missing_indices = {0, 1, 2} - existing_indices
            
            if missing_indices:
                for axis_index in missing_indices:
                    # Check if fcurve exists for this axis
                    fc = next((f for f in target_fcurves if f.array_index == axis_index), None)
                    
                    if fc:
                        val = fc.evaluate(frame)
                        fc.keyframe_points.insert(frame, val)
                    else:
                        # Create FCurve if missing using fcurves_collection.new()
                        try:
                            # Verify if fcurves_collection supports .new()
                            if hasattr(fcurves_collection, 'new'):
                                fc = fcurves_collection.new(data_path=data_path_base, index=axis_index)
                                target_fcurves.append(fc)
                                
                                # Get current static value
                                if bone_name:
                                    # Pose bone location
                                    val = obj.pose.bones[bone_name].location[axis_index]
                                else:
                                    val = obj.location[axis_index]
                                    
                                fc.keyframe_points.insert(frame, val)
                            else:
                                print("Motion Path Pro: Cannot create new F-Curve, collection does not support .new()")
                        except Exception as e:
                            print(f"Motion Path Pro: Error creating fcurve for {data_path_base}[{axis_index}]: {e}")
                    
                    modified = True
        
        if modified:
             for fc in target_fcurves:
                 fc.update()

def update_custom_path_active(self, context):
    wm = context.window_manager
    if wm.custom_path_draw_active:
        try:
            ensure_location_keyframes(context, context.active_object)
        except Exception as e:
            print(f"Motion Path Pro: Error ensuring keyframes: {e}")
        if not _find_and_start_motion_path_operators(context):
            print("Motion Path Pro: Enabled, but no 3D View found for interaction.")
    else:
        _stop_motion_path_operators(context)

    if context.area:
        context.area.tag_redraw()

def draw_header_button(self, context):
    layout = self.layout
    wm = context.window_manager
    row = layout.row(align=True)
    row.prop(wm, "custom_path_draw_active", text="", icon='IPO_BEZIER', toggle=True)
    row.popover(panel="MOTIONPATH_PT_header_settings", text="")

classes = (
    MOTIONPATH_ToggleCustomDraw,
    MotionPathStyleSettings,
    MOTIONPATH_PT_header_settings,
    MOTIONPATH_AddonPreferences,
    MOTIONPATH_MT_context_menu,
    
    MOTIONPATH_DirectManipulation,
    MOTIONPATH_DirectManipulationToggle,
    MOTIONPATH_AutoUpdateMotionPaths,
    MOTIONPATH_SetHandleType,
)

motion_path_update_mode_items = [
    ('SMART', "Smart (Event)", "Update only when relevant data changes (Zero idle power)"),
    ('TIMER', "Timer (Polling)", "Update periodically (Stable but higher power)")
]

handle_type_items = [
    ('FREE', "Free", "Handles can be adjusted independently"),
    ('ALIGNED', "Aligned", "Handles are aligned to maintain smoothness"),
    ('VECTOR', "Vector", "Creates linear interpolation"),
    ('AUTO', "Auto", "Automatic smooth handles"),
    ('AUTO_CLAMPED', "Auto Clamped", "Automatic handles with clamped values"),
]

def register():
    translations.register(__package__)
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.WindowManager.motion_path_styles = bpy.props.PointerProperty(type=MotionPathStyleSettings)

    bpy.types.WindowManager.custom_path_draw_active = bpy.props.BoolProperty(
        name="Enable Motion Path",
        description="Enable custom motion path drawing",
        default=False,
        update=update_custom_path_active
    )
    
    bpy.types.WindowManager.direct_manipulation_active = bpy.props.BoolProperty(
        name="Direct Manipulation Active",
        description="Enable direct manipulation of points on motion paths",
        default=False
    )
    bpy.types.WindowManager.auto_update_active = bpy.props.BoolProperty(
        name="Auto Update Active",
        default=False
    )
    
    # Performance Settings
    bpy.types.WindowManager.motion_path_fps_limit = bpy.props.IntProperty(
        name="Max FPS Limit",
        description="Limit the frame rate of interaction and redrawing to save power",
        default=60,
        min=1,
        max=144
    )
    
    bpy.types.WindowManager.motion_path_update_mode = bpy.props.EnumProperty(
        name="Update Mode",
        description="Choose how the motion path updates",
        items=motion_path_update_mode_items,
        default='SMART'
    )
    
    bpy.types.WindowManager.auto_update_fps = bpy.props.IntProperty(
        name="Auto Update FPS",
        description="Frequency of checks in Timer mode (Hz)",
        default=10,
        min=1,
        max=60
    )
    
    bpy.types.WindowManager.handle_type = bpy.props.EnumProperty(
        name="Handle Type",
        description="Default handle type for new keyframes",
        items=handle_type_items,
        default='ALIGNED'
    )
    bpy.types.WindowManager.handle_snap = bpy.props.BoolProperty(
        name="Snap Handles",
        description="Snap handles to grid or other elements",
        default=False
    )
    bpy.types.WindowManager.handle_snap_increment = bpy.props.FloatProperty(
        name="Snap Increment",
        description="Distance to snap handles",
        default=0.1,
        min=0.01,
        max=10.0
    )
    bpy.types.WindowManager.global_handle_visual_scale = bpy.props.FloatProperty(
        name="Global Handle Visual Scale",
        description="Scale factor for handle visualization",
        default=1.0,
        min=0.1,
        max=10.0
    )
    
    # Append to headers
    if hasattr(bpy.types, "VIEW3D_HT_header"):
        bpy.types.VIEW3D_HT_header.append(draw_header_button)

def unregister():
    # Remove from headers
    if hasattr(bpy.types, "VIEW3D_HT_header"):
        bpy.types.VIEW3D_HT_header.remove(draw_header_button)

    for cls in classes:
        bpy.utils.unregister_class(cls)
        
    del bpy.types.WindowManager.motion_path_styles
    del bpy.types.WindowManager.custom_path_draw_active
    del bpy.types.WindowManager.direct_manipulation_active
    del bpy.types.WindowManager.auto_update_active
    del bpy.types.WindowManager.motion_path_fps_limit
    del bpy.types.WindowManager.motion_path_update_mode
    del bpy.types.WindowManager.auto_update_fps
    del bpy.types.WindowManager.handle_type
    del bpy.types.WindowManager.handle_snap
    del bpy.types.WindowManager.handle_snap_increment
    del bpy.types.WindowManager.global_handle_visual_scale
    
    translations.unregister(__package__)