import bpy
import mathutils
import math
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils
from .state import _state, HANDLE_SELECT_RADIUS, SAFE_LIMIT, MIN_HANDLE_SCALE, MAX_HANDLE_SCALE, get_addon_prefs
from .cache import get_fcurves, is_location_fcurve, get_current_parent_matrix


_circle_aa_shader = None
CIRCLE_AA_FEATHER = 0.1
DEBUG_CIRCLE_DRAW = False


def _get_circle_aa_shader():
    global _circle_aa_shader
    if _circle_aa_shader is None:
        vert_out = gpu.types.GPUStageInterfaceInfo("circle_aa_interface")
        vert_out.smooth('VEC2', "uvInterp")
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.push_constant('MAT4', "ModelViewProjectionMatrix")
        shader_info.push_constant('VEC4', "color")
        shader_info.push_constant('FLOAT', "feather")
        shader_info.vertex_in(0, 'VEC3', "pos")
        shader_info.vertex_in(1, 'VEC2', "uv")
        shader_info.vertex_out(vert_out)
        shader_info.fragment_out(0, 'VEC4', "FragColor")
        shader_info.vertex_source(
            "void main()"
            "{"
            "  uvInterp = uv;"
            "  gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);"
            "}"
        )
        shader_info.fragment_source(
            "void main()"
            "{"
            "  vec2 uv_centered = uvInterp * 2.0 - 1.0;"
            "  float dist = length(uv_centered);"
            "  float alpha = 1.0 - smoothstep(1.0 - feather, 1.0 + feather, dist);"
            "  FragColor = color * alpha;"
            "}"
        )
        _circle_aa_shader = gpu.shader.create_from_info(shader_info)
        del vert_out
        del shader_info
    return _circle_aa_shader


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
        
        # 确保向量正交且长度一致
        right.normalize()
        up.normalize()
        
        # 重新计算up向量，确保它与right向量正交
        forward = right.cross(up)
        up = forward.cross(right)
        up.normalize()
        
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


def draw_billboard_circle(context, pos, radius_in_pixels, color, shader=None):
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

    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return

    scale = get_pixel_scale(context, pos, radius_in_pixels)
    if scale == 0:
        return

    # 确保使用相同的缩放因子来保持圆形
    c1 = (px - scale * rx - scale * ux, py - scale * ry - scale * uy, pz - scale * rz - scale * uz)
    c2 = (px + scale * rx - scale * ux, py + scale * ry - scale * uy, pz + scale * rz - scale * uz)
    c3 = (px + scale * rx + scale * ux, py + scale * ry + scale * uy, pz + scale * rz + scale * uz)
    c4 = (px - scale * rx + scale * ux, py - scale * ry + scale * uy, pz - scale * rz + scale * uz)
    for v in (c1, c2, c3, c4):
        if not (math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2]) and
                abs(v[0]) < SAFE_LIMIT and abs(v[1]) < SAFE_LIMIT and abs(v[2]) < SAFE_LIMIT):
            return

    verts = (c1, c2, c3, c4)
    uvs = ((0, 0), (1, 0), (1, 1), (0, 1))
    indices = ((0, 1, 2), (0, 2, 3))
    try:
        if len(color) >= 4:
            color_tuple = (float(color[0]), float(color[1]), float(color[2]), float(color[3]))
        elif len(color) == 3:
            color_tuple = (float(color[0]), float(color[1]), float(color[2]), 1.0)
        else:
            color_tuple = (1.0, 1.0, 1.0, 1.0)
    except Exception:
        color_tuple = (1.0, 1.0, 1.0, 1.0)

    shader_aa = _get_circle_aa_shader()
    batch = batch_for_shader(shader_aa, 'TRIS', {"pos": verts, "uv": uvs}, indices=indices)
    shader_aa.bind()
    try:
        matrix = context.region_data.perspective_matrix
    except Exception as e:
        if DEBUG_CIRCLE_DRAW:
            print(f"[MotionPathPro] Circle draw skipped: {e}")
        return
    shader_aa.uniform_float("ModelViewProjectionMatrix", matrix)
    shader_aa.uniform_float("color", color_tuple)
    shader_aa.uniform_float("feather", CIRCLE_AA_FEATHER)
    batch.draw(shader_aa)


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

    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return

    scale = get_pixel_scale(context, pos, half_size_in_pixels)
    if scale == 0:
        return
    
    try:
        c1x, c1y, c1z = rx - ux, ry - uy, rz - uz
        c2x, c2y, c2z = rx + ux, ry + uy, rz + uz
        c3x, c3y, c3z = -rx + ux, -ry + uy, -rz + uz
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


def draw_batched_billboard_circles(context, points, radius_in_pixels, color, shader=None, segments=8):
    if not points or radius_in_pixels <= 0:
        return
    
    right, up = get_billboard_basis(context)
    if right is None or up is None:
        return
    
    try:
        rx, ry, rz = right[0], right[1], right[2]
        ux, uy, uz = up[0], up[1], up[2]
    except Exception:
        return
    
    try:
        if hasattr(color, 'to_tuple'):
            safe_color = color.to_tuple()
        else:
            safe_color = tuple(float(c) for c in color)
        if len(safe_color) == 3:
            safe_color = (safe_color[0], safe_color[1], safe_color[2], 1.0)
        elif len(safe_color) != 4:
            safe_color = (1.0, 1.0, 1.0, 1.0)
    except Exception:
        safe_color = (1.0, 1.0, 1.0, 1.0)

    uv_quad = ((0, 0), (1, 0), (1, 1), (0, 1))
    BATCH_SIZE = 500
    try:
        matrix = context.region_data.perspective_matrix
    except Exception as e:
        if DEBUG_CIRCLE_DRAW:
            print(f"[MotionPathPro] Batched circles skipped: {e}")
        return
    shader_aa = _get_circle_aa_shader()

    for i in range(0, len(points), BATCH_SIZE):
        batch_points = points[i : min(i + BATCH_SIZE, len(points))]
        all_verts = []
        all_uvs = []
        all_indices = []
        base = 0
        for pos in batch_points:
            try:
                px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
                
                if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and
                        abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
                    continue

                scale = get_pixel_scale(context, (px, py, pz), radius_in_pixels)
                if scale == 0:
                    continue
                
                # 确保使用相同的缩放因子来保持圆形
                c1 = (px - scale * rx - scale * ux, py - scale * ry - scale * uy, pz - scale * rz - scale * uz)
                c2 = (px + scale * rx - scale * ux, py + scale * ry - scale * uy, pz + scale * rz - scale * uz)
                c3 = (px + scale * rx + scale * ux, py + scale * ry + scale * uy, pz + scale * rz + scale * uz)
                c4 = (px - scale * rx + scale * ux, py - scale * ry + scale * uy, pz - scale * rz + scale * uz)
                
                valid = True
                for v in (c1, c2, c3, c4):
                    if not (math.isfinite(v[0]) and math.isfinite(v[1]) and math.isfinite(v[2]) and
                            abs(v[0]) < SAFE_LIMIT and abs(v[1]) < SAFE_LIMIT and abs(v[2]) < SAFE_LIMIT):
                        valid = False
                        break
                if not valid:
                    continue
                    
                all_verts.extend((c1, c2, c3, c4))
                all_uvs.extend(uv_quad)
                all_indices.extend(((base, base + 1, base + 2), (base, base + 2, base + 3)))
                base += 4
            except Exception:
                continue
                
        if not all_verts or not all_indices:
            continue
        try:
            batch = batch_for_shader(shader_aa, 'TRIS', {"pos": all_verts, "uv": all_uvs}, indices=all_indices)
            shader_aa.bind()
            shader_aa.uniform_float("ModelViewProjectionMatrix", matrix)
            shader_aa.uniform_float("color", safe_color)
            shader_aa.uniform_float("feather", CIRCLE_AA_FEATHER)
            batch.draw(shader_aa)
        except Exception as e:
            if DEBUG_CIRCLE_DRAW:
                print(f"[MotionPathPro] Error drawing circles batch: {e}")


class DrawCollector:
    def __init__(self):
        self.lines = []
        self.line_colors = []
        self.circles = {}

    def add_line(self, p1, p2, color):
        try:
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
        r = round(radius, 2)
        
        if len(color) == 3:
            c_vals = (color[0], color[1], color[2], 1.0)
        elif len(color) >= 4:
            c_vals = (color[0], color[1], color[2], color[3])
        else:
            c_vals = (1.0, 1.0, 1.0, 1.0)
            
        c = tuple(round(x, 3) for x in c_vals)
        
        key = (r, c)
        if key not in self.circles:
            self.circles[key] = []
        self.circles[key].append(pos)
        
    def draw(self, context, styles):
        if self.lines:
            try:
                shader = gpu.shader.from_builtin('POLYLINE_SMOOTH_COLOR')
                batch = batch_for_shader(shader, 'LINES', {"pos": self.lines, "color": self.line_colors})
                shader.bind()
                viewport_size = gpu.state.viewport_get()[2:]
                shader.uniform_float("viewportSize", viewport_size)
                wm = context.window_manager
                line_width = styles.handle_line_width
                shader.uniform_float("lineWidth", line_width)
                batch.draw(shader)
            except Exception as e:
                print(f"Error drawing lines batch: {e}")
            
        for (radius, color), points in self.circles.items():
            draw_batched_billboard_circles(context, points, radius, color, segments=8)


def _build_ring_vertices(px, py, pz, scale, rx, ry, rz, ux, uy, uz, segments=32):
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
        style = styles.origin_indicator_style
        outer_size = styles.origin_indicator_size
        outer_color = tuple(styles.origin_indicator_color)
        inner_color = tuple(styles.origin_indicator_inner_color)

        gpu.state.blend_set('ALPHA')

        if style == 'DOT':
            draw_billboard_circle(context, pos, outer_size / 2, inner_color)

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
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'LINE_LOOP', {"pos": ring_verts})
            shader.bind()
            shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
            shader.uniform_float("lineWidth", 2.0)
            shader.uniform_float("color", outer_color)
            batch.draw(shader)
            if style == 'RING_DOT':
                draw_billboard_circle(context, pos, outer_size / 6, inner_color)

    except Exception as e:
        print(f"Error in draw_origin_indicator: {e}")


def get_handle_correction_factors(keyframes_for_location):
    dt_values = []
    
    for array_index, keyframe in keyframes_for_location.items():
        dt_l = abs(keyframe.handle_left[0] - keyframe.co[0])
        dt_r = abs(keyframe.handle_right[0] - keyframe.co[0])
        if dt_l > 0.001: dt_values.append(dt_l)
        if dt_r > 0.001: dt_values.append(dt_r)
        
    if not dt_values:
        S = 1.0
    else:
        S = sum(dt_values) / len(dt_values)
        
    factors_left = {}
    factors_right = {}
    
    for array_index, keyframe in keyframes_for_location.items():
        dt_l = abs(keyframe.handle_left[0] - keyframe.co[0])
        dt_r = abs(keyframe.handle_right[0] - keyframe.co[0])
        
        factors_left[array_index] = S / dt_l if dt_l > 0.001 else 1.0
        factors_right[array_index] = S / dt_r if dt_r > 0.001 else 1.0
        
        factors_left[array_index] = max(MIN_HANDLE_SCALE, min(factors_left[array_index], MAX_HANDLE_SCALE))
        factors_right[array_index] = max(MIN_HANDLE_SCALE, min(factors_right[array_index], MAX_HANDLE_SCALE))
        
    return factors_left, factors_right


def draw_motion_path_handles(context, point_3d, keyframes_for_location, shader, styles, frame_num, bone=None, parent_matrix=None, collector=None, obj_name=None):
    global _state
    wm = context.window_manager
    global_scale = wm.global_handle_visual_scale
    
    if parent_matrix is None:
        parent_matrix = mathutils.Matrix.Identity(4)
            
    rotation_matrix = parent_matrix.to_3x3()
    
    handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
    handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
    
    factors_left, factors_right = get_handle_correction_factors(keyframes_for_location)
    
    for array_index in range(3):
        if array_index in keyframes_for_location:
            keyframe = keyframes_for_location[array_index]
            if hasattr(keyframe, 'handle_left') and hasattr(keyframe, 'handle_right'):
                factor_l = factors_left.get(array_index, 1.0)
                factor_r = factors_right.get(array_index, 1.0)
                
                diff_left = (keyframe.handle_left[1] - keyframe.co[1]) * factor_l
                diff_right = (keyframe.handle_right[1] - keyframe.co[1]) * factor_r
                
                if array_index == 0: 
                    handle_vector_left.x = diff_left
                    handle_vector_right.x = diff_right
                elif array_index == 1: 
                    handle_vector_left.y = diff_left
                    handle_vector_right.y = diff_right
                elif array_index == 2: 
                    handle_vector_left.z = diff_left
                    handle_vector_right.z = diff_right
    
    world_vector_left = rotation_matrix @ handle_vector_left
    world_vector_right = rotation_matrix @ handle_vector_right
    
    handle_left_pos = point_3d + (world_vector_left * global_scale)
    _state.handle_points.append({
        'position': handle_left_pos,
        'side': 'left',
        'frame': frame_num,
        'bone_name': bone.name if bone else None,
        'obj_name': obj_name
    })
    is_selected = (_state.selected_handle_point == len(_state.handle_points) - 1 and 
                  _state.handle_dragging)
    line_color = styles.handle_line_color if not is_selected else styles.selected_handle_line_color
    
    if collector:
        collector.add_line(point_3d, handle_left_pos, line_color)

    handle_right_pos = point_3d + (world_vector_right * global_scale)
    _state.handle_points.append({
        'position': handle_right_pos,
        'side': 'right',
        'frame': frame_num,
        'bone_name': bone.name if bone else None,
        'obj_name': obj_name
    })
    is_selected = (_state.selected_handle_point == len(_state.handle_points) - 1 and 
                  _state.handle_dragging)
    line_color = styles.handle_line_color if not is_selected else styles.selected_handle_line_color
    
    if collector:
        collector.add_line(point_3d, handle_right_pos, line_color)
    
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


def draw_motion_path_point(context, point_3d, frame_num,
                           is_keyframe_point, is_selected_keyframe,
                           keyframes_for_location, action,
                           shader, styles, bone=None, parent_matrix=None, collector=None, obj_name=None):
    global _state
    wm = context.window_manager
    
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
            draw_motion_path_handles(context, point_3d, keyframes_for_location, shader, styles, frame_num, bone=bone, parent_matrix=parent_matrix, collector=collector, obj_name=obj_name)

    if collector:
        collector.add_circle(point_3d, size / 2, color)


def draw_enhanced_path(context, obj, parent_matrix, collector, styles, bone=None, obj_name=None):
    global _state
    cache_key = bone.name if bone else None
    if obj_name is None:
        obj_name = obj.name
    obj_cache = _state.position_cache.get(obj_name, {})
    if cache_key not in obj_cache:
        return
    bone_name = bone.name if bone else None
    action = obj.animation_data.action if obj.animation_data else None

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

    for frame_num, cache_data in obj_cache[cache_key].items():
        local_point = cache_data['position']
        point_3d = parent_matrix @ local_point
        keyframes_for_location = frame_keyframe_map.get(frame_num, {})
        is_selected_keyframe = frame_num in frame_selected
        draw_motion_path_point(
            context, point_3d, frame_num,
            True, is_selected_keyframe,
            keyframes_for_location, action,
            None, styles,
            bone=bone, parent_matrix=parent_matrix,
            collector=collector, obj_name=obj_name
        )


def draw_motion_path_overlay():
    context = bpy.context

    try:
        if not context.space_data or context.space_data.type != 'VIEW_3D':
             return

        wm = context.window_manager
        if not wm.direct_manipulation_active and not wm.custom_path_draw_active:
            return
        
        global _state
        obj = context.active_object

        styles = get_addon_prefs(context)

        gpu.state.blend_set('ALPHA')

        if wm.custom_path_draw_active and _state.path_vertices:
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            viewport_size = gpu.state.viewport_get()[2:]
            
            for (pv_obj_name, pv_bone_name), vertices in _state.path_vertices.items():
                if not vertices:
                    continue
                draw_obj = bpy.data.objects.get(pv_obj_name)
                if not draw_obj:
                    continue
                
                draw_bone = None
                if pv_bone_name and draw_obj.mode == 'POSE' and draw_obj.pose:
                    draw_bone = draw_obj.pose.bones.get(pv_bone_name)
                    if not draw_bone:
                        continue
                
                pv_parent_matrix = get_current_parent_matrix(draw_obj, draw_bone)
                
                world_points = []
                for v in vertices:
                    try:
                        p = pv_parent_matrix @ v
                        px = p[0]
                        py = p[1]
                        pz = p[2]
                        if (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and
                            abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
                            world_points.append((px, py, pz))
                    except Exception:
                        continue
                
                if len(world_points) >= 2:
                    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": world_points})
                    shader.bind()
                    shader.uniform_float("viewportSize", viewport_size)
                    shader.uniform_float("lineWidth", styles.path_width)
                    shader.uniform_float("color", styles.path_color)
                    batch.draw(shader)
                
                if styles.show_frame_points and world_points:
                    draw_batched_billboard_circles(context, world_points, styles.frame_point_size / 2, styles.frame_point_color, segments=8)
        
        _state.handle_points = []
        
        collector = DrawCollector()
        
        if obj and obj.mode == 'POSE':
            try:
                bones_to_draw = list(context.selected_pose_bones or [])
                active_bone = context.active_pose_bone
                if active_bone and active_bone not in bones_to_draw:
                    bones_to_draw.append(active_bone)
            except Exception:
                bones_to_draw = []
            for bone in bones_to_draw:
                try:
                    bone_parent_matrix = get_current_parent_matrix(obj, bone)
                    draw_enhanced_path(context, obj, bone_parent_matrix, collector, styles, bone=bone)
                except Exception:
                    continue
        else:
            for obj_name_cache, obj_cache in _state.position_cache.items():
                try:
                    draw_obj = bpy.data.objects.get(obj_name_cache)
                    if not draw_obj:
                        continue
                    obj_parent_matrix = get_current_parent_matrix(draw_obj)
                    draw_enhanced_path(context, draw_obj, obj_parent_matrix, collector, styles, obj_name=obj_name_cache)
                except Exception:
                    continue
             
        collector.draw(context, styles)

        if obj and styles.show_origin_indicator:
            target_bone = None
            if obj.mode == 'POSE':
                target_bone = context.active_pose_bone
                if not target_bone and context.selected_pose_bones:
                    target_bone = context.selected_pose_bones[0]
            draw_origin_indicator(context, obj, target_bone, styles)
        
    except Exception as e:
        print(f"Error in motion path overlay: {e}")
        import traceback
        traceback.print_exc()


def enable_draw_handler(context):
    global _state
    if _state.draw_handler is None:
        _state.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_motion_path_overlay, (), 'WINDOW', 'POST_VIEW')


def disable_draw_handler():
    global _state
    if _state.draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state.draw_handler, 'WINDOW')
        _state.draw_handler = None

