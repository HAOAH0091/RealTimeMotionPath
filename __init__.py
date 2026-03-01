bl_info = {
    "name" : "RealTimeMotionPath",
    "author" : "HAOAH",
    "description" : "在 3D 视口中显示和操作实时运动路径，支持直接手柄编辑和图形编辑器同步",
    "blender" : (5, 0, 0),
    "version" : (1, 0, 0),
    "location" : "3D Viewport › Header",
    "warning" : "",
    "doc_url" : "",
    "tracker_url" : "",
    "category" : "Animation"
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
 b          self.selected_handle_side = None
        self.selected_bone_name = None  # 骨骼名称字符串（安全，无直接RNA引用）
        self.handle_points = []
        self.selected_handle_point = None
        self.selected_handle_data = None  # 直接存储手柄数据以避免索引错误
        self.handle_dragging = False
        self.selected_drag_object_name = None  # 对象名称字符串（安全，无直接RNA引用）
        self.position_cache = {}  # {对象名: {缓存键: {帧: {'position': Vector}}}}
        self.initial_handle_values = {}  # 存储拖动时的初始手柄值：{(frame, array_index): value}
        self.draw_handler = None
        self.path_vertices = {}  # {(对象名, 骨骼名或None): [Vector, ...]}
        
    def reset(self):
        self.__init__()


_state = MotionPathState()

def get_addon_prefs(context):
    return context.preferences.addons[__package__].preferences

def _get_drag_obj(context):
    """根据存储的名称安全地解析拖动目标对象。绝不返回过期的 RNA 引用。"""
    global _state
    if _state.selected_drag_object_name:
        try:
            obj = bpy.data.objects.get(_state.selected_drag_object_name)
            if obj:
                return obj
        except Exception:
            pass
    return context.active_object

# 全局锁，防止智能更新中的递归
_is_updating_cache = False


HANDLE_SELECT_RADIUS = 20
SAFE_LIMIT = 1000000.0
MIN_HANDLE_SCALE = 0.1
MAX_HANDLE_SCALE = 100.0

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
        
        # 验证基向量
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
    # 确保 pos 是用于数学运算的 Vector（它可能是来自安全绘制代码的元组）
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

_circle_aa_shader = None
CIRCLE_AA_FEATHER = 0.1  # 抗锯齿圆形着色器的软边缘宽度
DEBUG_CIRCLE_DRAW = False  # 设置为 True 以打印圆形绘制中的异常


def _get_circle_aa_shader():
    """创建或返回缓存的抗锯齿圆形着色器（四边形 + smoothstep 软边缘）。"""
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

def draw_billboard_circle(context, pos, radius_in_pixels, color, shader=None):
    """使用四边形 + 自定义着色器绘制抗锯齿软边缘的圆形。
    注意：shader 参数被忽略（为保持 API 兼容性而保留）。
    """
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

    # 四边形角点：中心 ± right*scale ± up*scale, UV (0,0)-(1,1)
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
        # 预计算角点向量（纯浮点数）
        # 角点 1: right - up
        c1x, c1y, c1z = rx - ux, ry - uy, rz - uz
        # 角点 2: right + up
        c2x, c2y, c2z = rx + ux, ry + uy, rz + uz
        # 角点 3: -right + up
        c3x, c3y, c3z = -rx + ux, -ry + uy, -rz + uz
        # 角点 4: -right - up
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
    """使用四边形 + 自定义着色器绘制抗锯齿软边缘的圆形。
    注意：shader 和 segments 参数被忽略（为保持 API 兼容性而保留）。
    """
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
                # 使用显式浮点转换进行更安全的解包
                # 这将值从 C 支持的 Vector 对象中分离，以防止访问冲突
                px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
                
                if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(pz) and
                        abs(px) < SAFE_LIMIT and abs(py) < SAFE_LIMIT and abs(pz) < SAFE_LIMIT):
                    continue

                scale = get_pixel_scale(context, (px, py, pz), radius_in_pixels)
                if scale == 0:
                    continue
                
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
                # 捕获单个点的错误以保护批处理
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

def is_location_fcurve(fcurve, bone_name=None):
    """检查 fcurve 是否为对象或特定骨骼的位置 fcurve。"""
    if bone_name:
        return fcurve.data_path == f'pose.bones["{bone_name}"].location'
    return fcurve.data_path == 'location'

def is_keyframe_at_frame(fcurves, frame_num, bone_name=None):
    """检查位置 fcurve 在给定帧处是否存在关键帧。"""
    for fcurve in fcurves:
        if is_location_fcurve(fcurve, bone_name):
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame_num) < 0.5:
                    return True
    return False

def calculate_path_from_fcurves(obj, action, frames, bone_name=None):
    """
    直接从 fcurves 计算路径点，绕过场景评估。
    返回：{frame: {'position': Vector((x,y,z))}}
    """
    path_data = {}
    
    # 预取位置的 fcurves
    fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc, bone_name)]
    
    # 按轴分组
    fcurves_by_axis = {}
    for fc in fcurves:
        fcurves_by_axis[fc.array_index] = fc
        
    # 如果缺少 fcurve，则获取默认值（来自当前对象状态）
    # 注意：这假设默认值不会随时间变化（如果没有 fcurve，则为真）
    if bone_name:
        if bone_name in obj.pose.bones:
            defaults = obj.pose.bones[bone_name].location.copy()
        else:
            defaults = mathutils.Vector((0, 0, 0))
        delta_loc = mathutils.Vector((0, 0, 0)) # 骨骼通常没有增量位置
    else:
        defaults = obj.location.copy()
        delta_loc = obj.delta_location
    
    for frame in frames:
        pos = defaults.copy()
        for axis in range(3):
            if axis in fcurves_by_axis:
                pos[axis] = fcurves_by_axis[axis].evaluate(frame)
        
        # 应用增量位置
        pos = pos + delta_loc
        
        path_data[frame] = {
            'position': pos
        }
        
    return path_data

def build_position_cache(context):
    """
    构建关键帧和路径线的 3D 位置缓存。

    统一快速路径（所有对象和所有骨骼）：
      始终通过 fcurve.evaluate() 直接读取 F-Curve 值。
      绝不调用 scene.frame_set() —— 场景状态从未被修改。
      这保证了：
        - 无交互延迟（G/R/S 变换从未中断）。
        - 旋转/缩放约束的正确行为：F-Curve 驱动的位置不受仅更改旋转或缩放的约束的影响。
          校正后的 get_current_parent_matrix() 确保绘制的路径没有约束旋转污染。
        - 没有位置 F-Curve 的骨骼（纯 IK 末端执行器等）产生空帧集并被静默跳过 —— 正确，无需显示。

    坐标空间契约：
      对象模式：
        缓存位置是原始 F-Curve 位置值（matrix_basis 空间）：
          - 无父级：等于世界空间。
          - 有父级：等于 matrix_basis 空间；在绘制时通过 parent.matrix_world @ matrix_parent_inverse 转换为世界空间。
        get_current_parent_matrix() 返回 Identity（无父级）或
        obj.parent.matrix_world @ obj.matrix_parent_inverse（有父级）。

      姿态（骨骼）模式：
        缓存位置是骨骼局部空间中的原始 F-Curve 位置值。
        get_current_parent_matrix() 返回：
          obj.matrix_world @ parent.matrix @ parent.bone.matrix_local.inv() @ bone.matrix_local  (子骨骼)
          obj.matrix_world @ bone.bone.matrix_local                                               (根骨骼)
        这将在不包含骨骼自身约束效果的情况下将骨骼局部 F-Curve 偏移转换为世界空间。

    关于智能交互的说明：
      当仅 OBJECT（非 ACTION）更改时，on_depsgraph_update 会跳过此函数，
      重用现有缓存，以便交互式变换（G/R/S）感觉流畅。
    """
    global _state, _is_updating_cache
    
    # 原子锁：防止递归更新
    if _is_updating_cache:
        return
        
    _is_updating_cache = True
    
    try:
        _state.position_cache = {}
        _state.path_vertices = {}
        
        if (hasattr(bpy.context.window_manager, 'skip_motion_path_cache') and 
             bpy.context.window_manager.skip_motion_path_cache):
            return
        
        obj = context.active_object
        wm = context.window_manager
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        frames_range = range(frame_start, frame_end + 1)
        
        if obj and obj.mode == 'POSE':
            # --- 姿态模式：单个骨架，所有选定骨骼 ---
            if not obj.animation_data or not obj.animation_data.action:
                return
            action = obj.animation_data.action
            obj_name = obj.name
            
            bones_to_cache = set(context.selected_pose_bones or [])
            if context.active_pose_bone:
                bones_to_cache.add(context.active_pose_bone)

            for bone in bones_to_cache:
                try:
                    bone_name = bone.name
                    fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc, bone_name)]
                    frames = set(int(kp.co[0]) for fc in fcurves for kp in fc.keyframe_points
                                 if frame_start <= kp.co[0] <= frame_end)
                    if not frames:
                        continue
                    path_data = calculate_path_from_fcurves(obj, action, frames, bone_name=bone_name)
                    _state.position_cache.setdefault(obj_name, {})[bone_name] = path_data
                    
                    if wm.custom_path_draw_active:
                        dense_data = calculate_path_from_fcurves(obj, action, frames_range, bone_name=bone_name)
                        _state.path_vertices[(obj_name, bone_name)] = [dense_data[f]['position'] for f in frames_range]
                except Exception:
                    continue
        else:
            # --- 对象模式：所有选定对象 ---
            objects_to_cache = list(context.selected_objects or [])
            if obj and obj not in objects_to_cache:
                objects_to_cache.append(obj)
            
            for cache_obj in objects_to_cache:
                try:
                    if not cache_obj.animation_data or not cache_obj.animation_data.action:
                        continue
                    action = cache_obj.animation_data.action
                    obj_name = cache_obj.name
                    
                    fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc)]
                    frames = sorted(set(int(kp.co[0]) for fc in fcurves for kp in fc.keyframe_points
                                 if frame_start <= kp.co[0] <= frame_end))
                    if not frames:
                        continue
                    path_data = calculate_path_from_fcurves(cache_obj, action, frames)
                    _state.position_cache.setdefault(obj_name, {})[None] = path_data
                    
                    if wm.custom_path_draw_active:
                        dense_data = calculate_path_from_fcurves(cache_obj, action, frames_range)
                        _state.path_vertices[(obj_name, None)] = [dense_data[f]['position'] for f in frames_range]
                except Exception:
                    continue
     
    finally:
        _is_updating_cache = False

def get_current_parent_matrix(obj, bone=None):
    """
    统一计算父级矩阵（从缓存位置空间到世界空间）。

    对象模式：
      F-Curve 位置值处于 matrix_basis 空间（由关键帧驱动的原始位置/旋转/缩放）。
      Blender 的完整世界变换是：
          matrix_world = parent.matrix_world @ matrix_parent_inverse @ matrix_basis
      因此，应用于 F-Curve 值的正确父级矩阵是：
        - 无父级  → Identity  (F-Curve 值就是世界位置)
        - 有父级    → obj.parent.matrix_world @ obj.matrix_parent_inverse
      matrix_parent_inverse 在建立父子关系时存储（它是那一刻父级世界矩阵的逆矩阵），
      并确保子级不会跳变。没有它，路径将出现在父级的原点而不是子级的实际位置。
      该公式仍然避免将对象自身的约束效果（旋转、缩放）烘焙到父级矩阵中，
      防止当仅旋转约束（例如阻尼跟踪）处于活动状态时路径发生旋转。

    姿态（骨骼）模式：
      骨骼 F-Curve 位置值是骨骼局部空间中的偏移量。转换为世界空间：

        根骨骼：
          armature_world @ bone.matrix_local @ [fx, fy, fz]
          bone.matrix_local (骨架空间) 将骨骼局部偏移转换为骨架空间。

        子骨骼：
          armature_world @ parent.matrix @ parent.bone.matrix_local.inverted() @ bone.matrix_local @ [fx, fy, fz]

          分步几何：
            bone.matrix_local              — 骨架空间中的子级静止姿态
            parent.bone.matrix_local.inv() — "撤销"父级静止姿态，给出父骨骼局部空间中的子级静止姿态
            parent.matrix                 — 应用父级的当前姿态（骨架空间）
          当父级没有动画时：parent.matrix == parent.bone.matrix_local，
          因此中间两项抵消为 Identity，公式简化为根骨骼的情况。

      bone.matrix_local 是静止姿态矩阵 — 不受此骨骼约束的影响。
      parent.matrix 是父级的当前姿态 — 正确反映动画父级，同时排除此骨骼自身的约束效果。
      也用于拖动：parent_matrix.to_3x3().inverted() 将世界空间鼠标偏移转换为骨骼局部 F-Curve 空间，
      以便在约束下获得正确的拖动方向。
    """
    try:
        if obj.mode == 'POSE' and bone:
            # 骨骼逻辑：使用父级链来推导空间，而不是此骨骼自己的
            # 约束后矩阵 (bone.matrix)。使用 bone.matrix 会将此骨骼的
            # 旋转/缩放约束烘焙到路径中，使其看起来旋转/扭曲。
            #
            # 子骨骼的正确公式：
            #   armature_world × parent_pose × parent_rest_inv × child_rest
            #
            # bone.parent.matrix                   — 骨架空间中父级的当前姿态
            # bone.parent.bone.matrix_local.inv()  — 转换骨架空间 → 父骨骼局部
            # bone.bone.matrix_local               — 转换父骨骼局部 → 骨架空间
            #                                        (子级静止位置)
            # 中间两项合起来是 parent_rest_inv × child_rest，即
            # 在父骨骼局部空间中表示的子级静止矩阵。当父级
            # 没有动画 (parent.matrix == parent.bone.matrix_local) 时，它们抵消为 Identity。
            if bone.parent:
                # parent_to_child_rest: 在父骨骼局部空间中表示的子级静止矩阵。
                parent_to_child_rest = bone.parent.bone.matrix_local.inverted() @ bone.bone.matrix_local
                return obj.matrix_world @ bone.parent.matrix @ parent_to_child_rest
            else:
                # 根骨骼：骨架世界矩阵 × 骨架空间中的骨骼静止矩阵。
                return obj.matrix_world @ bone.bone.matrix_local
        else:
            # 对象逻辑：parent.matrix_world @ matrix_parent_inverse 将 F-Curve
            # 值（matrix_basis 空间）转换为世界空间，而不烘焙对象自身的
            # 约束效果。不要使用 matrix_world @ matrix_basis.inverted() —
            # 当约束更改旋转/缩放时，该公式会失效，因为
            # matrix_world 包含 matrix_basis 中不存在的效果。
            if obj.parent is None:
                # 无父级：F-Curve 值已在世界空间中。
                return mathutils.Matrix.Identity(4)
            else:
                parent_mat = obj.parent.matrix_world.copy()
                # 如果作为特定骨骼的子级，请包含该骨骼的当前姿态。
                if obj.parent_type == 'BONE' and obj.parent_bone:
                    if obj.parent.pose and obj.parent_bone in obj.parent.pose.bones:
                        pb = obj.parent.pose.bones[obj.parent_bone]
                        parent_mat = obj.parent.matrix_world @ pb.matrix
                    # 回退：姿态中未找到骨骼（例如骨架无动作）；
                    # 视为普通对象父级 — 下面仍然应用 matrix_parent_inverse。
                # matrix_parent_inverse 补偿建立父子关系时父级的位置，
                # 使 F-Curve 值映射到正确的世界位置。
                return parent_mat @ obj.matrix_parent_inverse
    except Exception:
        # 捕获 Python 级别的 RNA 访问错误（例如 ReferenceError）。不捕获
        # C++ EXCEPTION_ACCESS_VIOLATION；主要修复方法是避免 _state 中的过期 RNA 引用。
        return mathutils.Matrix.Identity(4)

class DrawCollector:
    def __init__(self):
        self.lines = [] # 向量的扁平列表
        self.line_colors = [] # 颜色的扁平列表
        self.circles = {} # (半径, 颜色) -> [位置]

    def add_line(self, p1, p2, color):
        try:
            # 验证点以防止 GPU 驱动程序崩溃
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
        # 对半径和颜色进行四舍五入，以避免因浮点精度而产生过多的批次
        r = round(radius, 2)
        
        # 确保颜色为 RGBA（4 个分量）
        if len(color) == 3:
            c_vals = (color[0], color[1], color[2], 1.0)
        elif len(color) >= 4:
            c_vals = (color[0], color[1], color[2], color[3])
        else:
            c_vals = (1.0, 1.0, 1.0, 1.0) # 回退
            
        c = tuple(round(x, 3) for x in c_vals)
        
        key = (r, c)
        if key not in self.circles:
            self.circles[key] = []
        self.circles[key].append(pos)
        
    def draw(self, context, styles):
        # 绘制线条（POLYLINE_SMOOTH_COLOR 用于抗锯齿）
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
            
        # 绘制圆形（POLYLINE 用于抗锯齿）
        for (radius, color), points in self.circles.items():
            draw_batched_billboard_circles(context, points, radius, color, segments=8)

def _build_ring_vertices(px, py, pz, scale, rx, ry, rz, ux, uy, uz, segments=32):
    """构建形成屏幕对齐环的 3D 顶点元组列表。"""
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
    """在运动路径之上为活动对象/骨骼绘制原点指示器。"""
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


def draw_motion_path_overlay():
    """绘制高级运动路径覆盖层"""
    # 动态获取当前绘制调用的上下文
    # 这在切换工作区或区域时至关重要
    context = bpy.context

    try:
        # 安全检查：确保我们处于 3D 视图上下文中
        if not context.space_data or context.space_data.type != 'VIEW_3D':
             return

        wm = context.window_manager
        if not wm.direct_manipulation_active and not wm.custom_path_draw_active:
            return
        
        global _state
        obj = context.active_object

        styles = get_addon_prefs(context)

        # 启用 Alpha 混合以获得更平滑的边缘
        gpu.state.blend_set('ALPHA')

        # 为所有缓存目标绘制连续路径线（POLYLINE 用于抗锯齿）
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
        
        # 初始化批处理收集器
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
            for obj_name, obj_cache in _state.position_cache.items():
                try:
                    draw_obj = bpy.data.objects.get(obj_name)
                    if not draw_obj:
                        continue
                    obj_parent_matrix = get_current_parent_matrix(draw_obj)
                    draw_enhanced_path(context, draw_obj, obj_parent_matrix, collector, styles, obj_name=obj_name)
                except Exception:
                    continue
             
        # 提交批次
        collector.draw(context, styles)

        # 在运动路径之上绘制原点指示器
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

def draw_enhanced_path(context, obj, parent_matrix, collector, styles, bone=None, obj_name=None):
    """绘制对象或姿态骨骼的高级运动路径关键帧点和手柄。"""
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

def draw_motion_path_point(context, point_3d, frame_num,
                           is_keyframe_point, is_selected_keyframe,
                           keyframes_for_location, action,
                           shader, styles, bone=None, parent_matrix=None, collector=None, obj_name=None):
    """绘制运动路径点，如果需要则带手柄"""
    global _state
    wm = context.window_manager
    # styles 作为参数传递
    
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

def get_handle_correction_factors(keyframes_for_location):
    """
    根据时间差 (dt) 计算手柄的校正因子。
    返回 (factors_left, factors_right)，其中 factor = S / dt。
    S 是所有手柄的平均持续时间。
    
    包括钳位以防止在 dt 极小（例如垂直手柄）时发生数值爆炸，
    这可能会导致 3D 视图伪影或崩溃。
    """
    dt_values = []
    
    # 1. 收集所有有效的 dt 值
    for array_index, keyframe in keyframes_for_location.items():
        dt_l = abs(keyframe.handle_left[0] - keyframe.co[0])
        dt_r = abs(keyframe.handle_right[0] - keyframe.co[0])
        if dt_l > 0.001: dt_values.append(dt_l)
        if dt_r > 0.001: dt_values.append(dt_r)
        
    # 2. 计算参考比例 S
    if not dt_values:
        S = 1.0
    else:
        S = sum(dt_values) / len(dt_values)
        
    # 3. 计算因子
    factors_left = {}
    factors_right = {}
    
    for array_index, keyframe in keyframes_for_location.items():
        dt_l = abs(keyframe.handle_left[0] - keyframe.co[0])
        dt_r = abs(keyframe.handle_right[0] - keyframe.co[0])
        
        factors_left[array_index] = S / dt_l if dt_l > 0.001 else 1.0
        factors_right[array_index] = S / dt_r if dt_r > 0.001 else 1.0
        
        # 钳位因子以防止爆炸（例如，如果 dt 非常小但 > 0.001）
        factors_left[array_index] = max(MIN_HANDLE_SCALE, min(factors_left[array_index], MAX_HANDLE_SCALE))
        factors_right[array_index] = max(MIN_HANDLE_SCALE, min(factors_right[array_index], MAX_HANDLE_SCALE))
        
    return factors_left, factors_right

def draw_motion_path_handles(context, point_3d, keyframes_for_location, shader, styles, frame_num, bone=None, parent_matrix=None, collector=None, obj_name=None):
    """绘制带有单独控制点的运动路径手柄"""
    global _state
    wm = context.window_manager
    # styles 作为参数传递
    global_scale = wm.global_handle_visual_scale
    
    # 注意：point_3d 已经在世界空间中（在调用者中转换）
    # parent_matrix 是当前帧的父级矩阵
    
    if parent_matrix is None:
        parent_matrix = mathutils.Matrix.Identity(4)
            
    rotation_matrix = parent_matrix.to_3x3()
    
    handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
    handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
    
    # 获取校正因子
    factors_left, factors_right = get_handle_correction_factors(keyframes_for_location)
    
    # 从 F-Curve 计算局部手柄向量
    for array_index in range(3):
        if array_index in keyframes_for_location:
            keyframe = keyframes_for_location[array_index]
            if hasattr(keyframe, 'handle_left') and hasattr(keyframe, 'handle_right'):
                # 手柄向量 = 手柄位置 - Co
                # 根据持续时间应用校正因子
                factor_l = factors_left.get(array_index, 1.0)
                factor_r = factors_right.get(array_index, 1.0)
                
                # 左手柄（传入）
                diff_left = (keyframe.handle_left[1] - keyframe.co[1]) * factor_l
                # 右手柄（传出）
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
    
    # 转换为世界空间
    # 我们使用 rotation_matrix @ vector，因为向量是方向，而不是点
    world_vector_left = rotation_matrix @ handle_vector_left
    world_vector_right = rotation_matrix @ handle_vector_right
    
    # 绘制左手柄
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

    # 绘制右手柄
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
    
    # 绘制端点
    # 正确地重新实现正方形绘制循环
    # 我们现在总是添加 2 个手柄（左和右）。
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
    """启用绘制处理程序"""
    global _state
    if _state.draw_handler is None:
        # 传递空元组作为参数，这样我们就不会绑定到过期的上下文。
        # 回调函数必须自行处理上下文检索。
        _state.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_motion_path_overlay, (), 'WINDOW', 'POST_VIEW')

def disable_draw_handler():
    """禁用自定义绘制"""
    global _state
    if _state.draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_state.draw_handler, 'WINDOW')
        _state.draw_handler = None

@persistent
def on_depsgraph_update(scene, depsgraph):
    """运动路径的智能更新处理程序"""
    global _state, _is_updating_cache
    
    # 1. 检查递归锁（快速路径）
    # 我们仍然在这里检查以避免函数调用的开销，
    # 即使 build_position_cache 也处理它。
    if _is_updating_cache:
        return

    # 2. 检查拖动状态（冲突解决）
    # 如果操作员正在处理它，我们什么也不做。
    if _state.is_dragging or _state.handle_dragging:
        return

    wm = bpy.context.window_manager
    if not wm.custom_path_draw_active or wm.motion_path_update_mode != 'SMART':
        return

    # 检查我们是否需要更新
    # 我们关心对象变换和动作数据
    is_object_updated = depsgraph.id_type_updated('OBJECT')
    is_action_updated = depsgraph.id_type_updated('ACTION')
    
    if is_object_updated or is_action_updated:
        # 检查动画是否正在播放以避免播放期间负载过重
        if bpy.context.screen and bpy.context.screen.is_animation_playing:
            return

        try:
            has_relevant_objects = (bpy.context.active_object or bpy.context.selected_objects)
            if has_relevant_objects:
                is_interaction_update = is_object_updated and not is_action_updated
                
                if is_interaction_update:
                    return

                build_position_cache(bpy.context)
                
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
        except Exception as e:
            print(f"Error in smart update: {e}")

class MOTIONPATH_AutoUpdateMotionPaths(bpy.types.Operator):
    """更改关键帧时自动更新运动路径"""
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
        self._last_selected_obj_names = self._get_selected_obj_names(context)
        self._last_bone_selection = self._get_bone_selection_state(context)
        self._needs_update = False
        
        # 注册智能处理程序
        if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
            
        # 为计时器模式设置计时器
        # 我们总是创建一个计时器来动态处理模式切换，
        # 但我们只在计时器模式下执行它。
        # 使用 auto_update_fps 计算间隔
        interval = 1.0 / max(1, wm.auto_update_fps)
        self._timer = wm.event_timer_add(interval, window=context.window)
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        wm = context.window_manager

        # 检测活动对象切换
        active_obj = context.active_object
        current_obj_name = active_obj.name if active_obj else None
        if current_obj_name != self._last_active_obj_name:
            self._last_active_obj_name = current_obj_name
            _state.selected_path_point = None
            _state.selected_frame = None
            _state.selected_handle_side = None
            _state.selected_bone_name = None
            _state.selected_handle_point = None
            _state.selected_handle_data = None
            _state.is_dragging = False
            _state.handle_dragging = False
            _state.selected_drag_object_name = None
            self._needs_update = True

        # 检测选定对象的更改（对象模式）
        current_selected = self._get_selected_obj_names(context)
        if current_selected != self._last_selected_obj_names:
            self._last_selected_obj_names = current_selected
            self._needs_update = True

        # 检查骨骼选择更改（姿态模式）
        current_bone_selection = self._get_bone_selection_state(context)
        if current_bone_selection != self._last_bone_selection:
            self._last_bone_selection = current_bone_selection
            if current_bone_selection is None:
                _state.selected_bone_name = None  # 退出姿态模式时清除
            self._needs_update = True
        
        # 计时器模式逻辑
        if wm.motion_path_update_mode == 'TIMER' and event.type == 'TIMER':
            current_values = self._get_keyframe_values(context)
            if current_values != self._last_keyframe_values:
                self._needs_update = True
                self._last_keyframe_values = current_values
                
        # 处理更新
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
            
        # 移除智能处理程序
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
        all_values = []
        
        active_object = context.active_object
        if active_object and active_object.mode == 'POSE':
            all_values.extend(self._collect_object_keyframes(active_object))
        else:
            seen = set()
            for obj in (context.selected_objects or []):
                if obj.name in seen:
                    continue
                seen.add(obj.name)
                all_values.extend(self._collect_object_keyframes(obj))
                parent = obj.parent
                while parent:
                    if parent.name not in seen:
                        seen.add(parent.name)
                        all_values.extend(self._collect_object_keyframes(parent))
                    parent = parent.parent
            if active_object and active_object.name not in seen:
                all_values.extend(self._collect_object_keyframes(active_object))
            
        return tuple(all_values) if all_values else None
    
    def _get_selected_obj_names(self, context):
        """获取选定对象名称的排序元组以进行更改检测。"""
        return tuple(sorted(obj.name for obj in context.selected_objects)) if context.selected_objects else ()
    
    def _get_bone_selection_state(self, context):
        """获取当前骨骼选择状态"""
        active_object = context.active_object
        if not active_object or active_object.mode != 'POSE':
            return None
            
        active_bone_name = context.active_pose_bone.name if context.active_pose_bone else None
        selected_bone_names = tuple(sorted([b.name for b in context.selected_pose_bones])) if context.selected_pose_bones else ()
        
        return (active_bone_name, selected_bone_names)
    
class MOTIONPATH_SetHandleType(bpy.types.Operator):
    """为选定的关键帧设置手柄类型"""
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
    """启用/禁用运动路径编辑"""
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
    手动查找鼠标下的 3D 视图区域。
    这是必需的，因为在切换工作区时，模态运算符中的 'context' 可能会过期。
    返回：(region, space_data, local_mouse_pos, area) 或 (None, None, None, None)
    """
    mouse_x = event.mouse_x
    mouse_y = event.mouse_y

    # 支持多窗口设置
    # Blender 事件通常相对于活动窗口
    # 我们遍历所有窗口以确保安全
    
    # 首先尝试当前上下文窗口
    windows_to_check = [context.window] if context.window else []
    # 然后是其他窗口
    for win in context.window_manager.windows:
        if win not in windows_to_check:
            windows_to_check.append(win)
            
    for window in windows_to_check:
        screen = window.screen
        if not screen: continue
        
        # 检查此屏幕中的所有区域
        for area in screen.areas:
            # 我们只关心 3D 视图
            if area.type != 'VIEW_3D':
                continue
                
            # 区域边界检查（相对于窗口）
            if (area.x <= mouse_x < area.x + area.width and
                area.y <= mouse_y < area.y + area.height):
                
                # 检查区域内的区域
                for region in area.regions:
                    if region.type == 'WINDOW': # 主视口区域
                        # 区域边界检查
                        if (region.x <= mouse_x < region.x + region.width and
                            region.y <= mouse_y < region.y + region.height):
                            
                            # 找到鼠标下的特定区域
                            local_x = mouse_x - region.x
                            local_y = mouse_y - region.y
                            space_data = area.spaces.active
                            return region, space_data, (local_x, local_y), area

    return None, None, None, None

class MOTIONPATH_DirectManipulation(bpy.types.Operator):
    """直接操作运动路径上的点"""
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
        """将矢量手柄转换为自由手柄以允许编辑"""
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
        
        # 使用当前全局上下文覆盖上下文，以确保我们获取鼠标下的区域
        # 这修复了切换工作区或区域时的问题
        context = bpy.context

        wm = context.window_manager
        if not wm.direct_manipulation_active or not self._is_active:
            return self.cancel(context)
        
        # 已移除：骨架对象模式的硬编码块
        # 我们现在依靠下面的命中测试来决定是拦截还是通过。
        # 这修复了骨架对象无法在对象模式下编辑其运动路径的问题。
        
        if event.type == 'MOUSEMOVE':
            self._mouse_pos = (event.mouse_region_x, event.mouse_region_y)
            
            # FPS 限制
            target_interval = 1.0 / max(1, wm.motion_path_fps_limit)
            current_time = time.time()
            if (current_time - self._last_draw_time) < target_interval:
                return {'PASS_THROUGH'}
            self._last_draw_time = current_time
            
            # 使用手动区域查找以确保我们正在与正确的 3D 视图交互
            region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
            if not region or not space_data:
                # 鼠标不在 3D 视图上方，传递事件
                return {'PASS_THROUGH'}

            rv3d = space_data.region_3d

            if _state.is_dragging:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _state.drag_start_3d)

                if _state.selected_handle_side is None:
                    # 点拖动：增量 delta — 每一帧更新锚点，以便深度投影保持正确。
                    offset = new_3d_pos - _state.drag_start_3d
                    self.move_selected_points(context, offset)
                    _state.drag_start_3d = new_3d_pos
                else:
                    # 手柄拖动：与原始拖动起点的总偏移量，因此手柄不会漂移。
                    total_offset = new_3d_pos - _state.drag_start_3d
                    self.move_selected_handles(context, total_offset, _state.selected_handle_side)

                try:
                    build_position_cache(context)
                except Exception:
                    pass

                area_to_redraw = target_area if target_area else context.area
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            elif _state.handle_dragging and _state.selected_handle_point is not None:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                
                # 使用 drag_start_3d 作为深度参考以实现一致的投影
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _state.drag_start_3d)
                total_offset = new_3d_pos - _state.drag_start_3d
                
                # 如果可用，使用缓存的手柄数据以避免当 handle_points 更改时出现 IndexError
                if _state.selected_handle_data:
                    handle_point = _state.selected_handle_data
                    self.move_handle_point(context, total_offset, handle_point)
                elif _state.selected_handle_point is not None and _state.selected_handle_point < len(_state.handle_points):
                    handle_point = _state.handle_points[_state.selected_handle_point]
                    self.move_handle_point(context, total_offset, handle_point)
                
                # 实时更新路径线
                try:
                    build_position_cache(context)
                except Exception:
                    pass

                area_to_redraw = target_area if target_area else context.area
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            return {'PASS_THROUGH'}
        
        elif event.type == 'RIGHTMOUSE':
            if event.value == 'PRESS':
                # 使用手动区域查找
                region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d

                hit_point, hit_frame, hit_bone = self.get_motion_path_point_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _state.selected_path_point = hit_point
                    _state.selected_frame = hit_frame
                    
                    if context.mode == 'POSE':
                        _state.selected_bone_name = hit_bone.name if hit_bone else None
                    else:
                        _state.selected_bone_name = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone_name if context.mode == 'POSE' else None
                        
                        # 检查右键命中的关键帧是否已选中
                        hit_keyframe_already_selected = is_keyframe_selected(action, bone_name, hit_frame)
                        
                        # 只有右键点击未选中的关键帧时才清除其他选中状态
                        if not hit_keyframe_already_selected:
                            for fc in get_fcurves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        for fc in get_fcurves(action):
                            if is_location_fcurve(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    area_to_redraw = target_area if target_area else context.area
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    
                    bpy.ops.wm.call_menu(name="MOTIONPATH_MT_context_menu")
                    return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}

        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                # 使用手动区域查找
                region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d
                area_to_redraw = target_area if target_area else context.area

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
                    _state.drag_start_mouse = local_mouse_pos
                    
                    hp_obj_name = handle_point.get('obj_name')
                    _state.selected_drag_object_name = hp_obj_name or None
                    
                    self.capture_initial_handle_values(context, handle_point['frame'], handle_point.get('bone_name'), handle_point['side'])
                    
                    # 手柄点击时不改变关键帧的选中状态
                    # 保持用户已有的多选状态，只操作手柄
                    
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                hit_side, hit_handle_pos, hit_frame, point_3d, hit_bone = self.get_motion_path_handle_at_mouse(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _state.selected_path_point = point_3d
                    _state.selected_frame = hit_frame
                    _state.selected_handle_side = hit_side
                    _state.drag_start_3d = point_3d  
                    _state.drag_start_item_pos = hit_handle_pos
                    _state.drag_start_mouse = local_mouse_pos
                    
                    self.capture_initial_handle_values(context, hit_frame, hit_bone.name if hit_bone else None, hit_side)
                    
                    if context.mode == 'POSE':
                        _state.selected_bone_name = hit_bone.name if hit_bone else None
                    else:
                        _state.selected_bone_name = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone_name if context.mode == 'POSE' else None
                        
                        for fc in get_fcurves(action):
                            if is_location_fcurve(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    _state.is_dragging = True
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
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
                        _state.selected_bone_name = hit_bone.name if hit_bone else None
                    else:
                        _state.selected_bone_name = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _state.selected_bone_name if context.mode == 'POSE' else None
                        
                        # 检查点击的关键帧是否已选中
                        hit_keyframe_already_selected = is_keyframe_selected(action, bone_name, hit_frame)
                        
                        # 只有未按住 Shift/Ctrl 且点击未选中的关键帧时才清除其他选中状态
                        if not hit_keyframe_already_selected and not event.shift and not event.ctrl:
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
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                # 点击空白区域检测：所有命中检测都未命中
                # - handle_index is None（未命中手柄点）
                # - 手柄 hit_frame is None（未命中手柄）
                # - 关键帧 hit_frame is None（未命中关键帧）
                # 清除所有选中状态
                if context.mode == 'POSE':
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        # 从 position_cache 获取当前骨架的所有骨骼
                        # 而不是只遍历 selected_pose_bones
                        # 因为用户可能取消选中了骨骼，但关键帧选中状态仍然保留
                        # 注意：当前只处理活动骨架（context.active_object）
                        # 因为运动路径只显示活动骨架的骨骼
                        obj_cache = _state.position_cache.get(obj.name, {})
                        for bone_name in obj_cache.keys():
                            for fc in get_fcurves(action):
                                if is_location_fcurve(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        kp.select_control_point = False
                else:
                    # Object 模式：清除所有显示运动路径对象的关键帧选中状态
                    # 使用 position_cache 中的对象，而不是 selected_objects
                    # 因为用户可能取消选中了对象，但关键帧选中状态仍然保留
                    for obj_name in _state.position_cache.keys():
                        obj = bpy.data.objects.get(obj_name)
                        if obj and obj.animation_data and obj.animation_data.action:
                            action = obj.animation_data.action
                            for fc in get_fcurves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            elif event.value == 'RELEASE':
                if _state.is_dragging:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Points"))
                    _state.is_dragging = False
                    _state.selected_path_point = None
                    _state.selected_frame = None
                    _state.selected_handle_side = None
                    _state.drag_start_item_pos = None
                    _state.selected_drag_object_name = None
                    
                    try:
                        build_position_cache(context)
                    except Exception:
                        pass
                    
                    _, _, _, release_area = find_region_under_mouse(context, event)
                    area_to_redraw = release_area if release_area else context.area
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                elif _state.handle_dragging:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Handle"))
                    _state.handle_dragging = False
                    _state.selected_handle_point = None
                    _state.drag_start_item_pos = None
                    _state.selected_drag_object_name = None
                    
                    try:
                        build_position_cache(context)
                    except Exception:
                        pass
                    
                    _, _, _, release_area = find_region_under_mouse(context, event)
                    area_to_redraw = release_area if release_area else context.area
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
        
        elif event.type == 'ESC':
            return {'PASS_THROUGH'}
        
        elif event.type == 'TIMER':
            if context.area and context.area.type == 'VIEW_3D':
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        
        # 显式传递所有其他事件（G、R、S 等）
        # 这确保了在不与路径交互时我们不会阻止标准 Blender 工具
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
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in offset):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Motion Path Points")
        
        action = obj.animation_data.action
        bone_name = _state.selected_bone_name if (obj and obj.mode == 'POSE') else None
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        
        # 计算父级矩阵逆矩阵以转换 世界偏移 -> 局部偏移（父级空间）
        parent_matrix = get_current_parent_matrix(obj, bone)
        # 我们只关心偏移向量的旋转/缩放
        parent_rot_inv = parent_matrix.to_3x3().inverted()
        
        # 将偏移转换为局部空间（父级空间）
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
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Motion Path Handles")
        
        action = obj.animation_data.action
        frame = _state.selected_frame
        global_scale = context.window_manager.global_handle_visual_scale
        bone_name = _state.selected_bone_name if (obj and obj.mode == 'POSE') else None
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        
        # 使用助手获取当前父级矩阵
        parent_matrix = get_current_parent_matrix(obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        # 将总偏移量转换为局部空间
        # 总偏移量局部 = Inverse(ParentRot) * 总偏移量世界
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

        # 获取校正因子
        factors_left, factors_right = get_handle_correction_factors(keyframes_for_location)

        for array_index, keyframe in keyframes_for_location.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            # 检索初始手柄值
            initial_val = _state.initial_handle_values.get((frame, array_index))
            if initial_val is None:
                continue # 如果正确捕获，不应发生这种情况
            
            initial_pos_2d = mathutils.Vector(initial_val)
            
            if side == 'left':
                factor = factors_left.get(array_index, 1.0)
                delta_val = total_offset_local_scaled[array_index] / factor
                keyframe.handle_left[1] = initial_pos_2d[1] + delta_val
            else:
                factor = factors_right.get(array_index, 1.0)
                delta_val = total_offset_local_scaled[array_index] / factor
                keyframe.handle_right[1] = initial_pos_2d[1] + delta_val
            
            # 更新对手柄
            # 对于 update_opposite_handle，我们需要一个表示当前手柄从 Co 的偏移量的向量。
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
        """根据移动的手柄和手柄类型更新对手柄"""
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
            
            # 使用斜率投影（固定 X）而不是长度保持
            # 这确保图形编辑器中的手柄仅垂直移动，与活动手柄行为匹配。
            
            co = mathutils.Vector(keyframe.co)
            
            if moved_handle_side == 'left':
                handle_active = mathutils.Vector(keyframe.handle_left)
                handle_opposite = mathutils.Vector(keyframe.handle_right)
                target_handle_attr = 'handle_right'
            else:
                handle_active = mathutils.Vector(keyframe.handle_right)
                handle_opposite = mathutils.Vector(keyframe.handle_left)
                target_handle_attr = 'handle_left'
            
            # 计算活动手柄的斜率
            dx_active = handle_active.x - co.x
            dy_active = handle_active.y - co.y
            
            if abs(dx_active) < 0.0001:
                # 活动手柄是垂直的（在 F-Curve 中不太可能），跳过以避免除以零
                return

            slope = dy_active / dx_active
            
            # 将斜率应用于对手柄，保持其 X 偏移
            dx_opposite = handle_opposite.x - co.x
            new_y_opposite = co.y + (slope * dx_opposite)
            
            # 仅更新对手柄的 Y 分量
            if target_handle_attr == 'handle_right':
                keyframe.handle_right[1] = new_y_opposite
            else:
                keyframe.handle_left[1] = new_y_opposite
            
            return
    
    def move_handle_point(self, context, total_offset_world, handle_point):
        """使用距初始位置的总偏移量移动手柄控制点"""
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        # bpy.ops.ed.undo_push(message="Move Handle Point")
        
        action = obj.animation_data.action
        frame = handle_point['frame']
        side = handle_point['side']
        bone_name = handle_point.get('bone_name')
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        global_scale = context.window_manager.global_handle_visual_scale
        
        # 使用助手
        parent_matrix = get_current_parent_matrix(obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        # 将总偏移量转换为局部空间
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
        
        # 获取校正因子
        factors_left, factors_right = get_handle_correction_factors(keyframes_for_location)
        
        for array_index, keyframe in keyframes_for_location.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            if original_left_type in {'AUTO', 'AUTO_CLAMPED'} or original_right_type in {'AUTO', 'AUTO_CLAMPED'}:
                keyframe.handle_left_type = 'ALIGNED'
                keyframe.handle_right_type = 'ALIGNED'
            
            # 检索初始手柄值
            initial_val = _state.initial_handle_values.get((frame, array_index))
            if initial_val is None:
                continue
            
            initial_pos_2d = mathutils.Vector(initial_val)
            
            # 将偏移应用于初始值
            if side == 'left':
                if hasattr(keyframe, 'handle_left'):
                    keyframe.handle_left[0] = initial_pos_2d[0]
                    factor = factors_left.get(array_index, 1.0)
                    delta_val = total_offset_local_scaled[array_index] / factor
                    keyframe.handle_left[1] = initial_pos_2d[1] + delta_val
            else:
                if hasattr(keyframe, 'handle_right'):
                    keyframe.handle_right[0] = initial_pos_2d[0]
                    factor = factors_right.get(array_index, 1.0)
                    delta_val = total_offset_local_scaled[array_index] / factor
                    keyframe.handle_right[1] = initial_pos_2d[1] + delta_val
            
            # 更新对手柄
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
        """获取与手柄点关联的关键帧的 3D 位置的辅助函数。"""
        global _state
        obj = _get_drag_obj(context)
        frame = handle_point['frame']
        bone_name = handle_point.get('bone_name')
        
        if not obj:
            return mathutils.Vector((0, 0, 0))
        
        obj_cache = _state.position_cache.get(obj.name, {})
        cache_key = bone_name if bone_name else None
        sub_cache = obj_cache.get(cache_key, {})
        cache_data = sub_cache.get(frame)
        if cache_data:
            return cache_data['position']
        
        return mathutils.Vector((0, 0, 0))
    
    def capture_initial_handle_values(self, context, frame_num, selected_bone_name, handle_side):
        """在拖动开始时捕获初始手柄值。"""
        global _state
        _state.initial_handle_values = {}
        
        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        fcurves = get_fcurves(action)
        
        # 过滤位置的 fcurves
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
        """检查鼠标是否在运动路径上的手柄末端上方"""
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
        
        if not obj:
            return None, None, None, None, None
        
        def check_handles_at_frame(bone_name, frame_num, point_3d, parent_matrix, check_action, bone_obj=None):
            if not is_keyframe_at_frame(get_fcurves(check_action), frame_num, bone_name):
                return None
            
            keyframes_for_location = {}
            for fcurve in get_fcurves(check_action):
                if is_location_fcurve(fcurve, bone_name):
                    for keyframe in fcurve.keyframe_points:
                        if abs(keyframe.co[0] - frame_num) < 0.5:
                            keyframes_for_location[fcurve.array_index] = keyframe
                            break
            
            if not keyframes_for_location:
                return None
            
            # 获取校正因子
            factors_left, factors_right = get_handle_correction_factors(keyframes_for_location)
            
            handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
            handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
            
            for array_index, keyframe in keyframes_for_location.items():
                factor_l = factors_left.get(array_index, 1.0)
                factor_r = factors_right.get(array_index, 1.0)
                
                diff = (keyframe.handle_left[1] - keyframe.co[1]) * factor_l
                handle_vector_left[array_index] = diff
                diff = (keyframe.handle_right[1] - keyframe.co[1]) * factor_r
                handle_vector_right[array_index] = diff
            
            rotation_matrix = parent_matrix.to_3x3()
            world_vector_left = rotation_matrix @ handle_vector_left
            world_vector_right = rotation_matrix @ handle_vector_right
            
            global_scale = context.window_manager.global_handle_visual_scale
            
            if world_vector_left.length > 1e-4:
                handle_left_pos = point_3d + (world_vector_left * global_scale)
                screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_left_pos)
                if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                    return 'left', handle_left_pos
            
            if world_vector_right.length > 1e-4:
                handle_right_pos = point_3d + (world_vector_right * global_scale)
                screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_right_pos)
                if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                    return 'right', handle_right_pos
            
            return None

        if obj.mode == 'POSE':
            if not obj.animation_data or not obj.animation_data.action:
                return None, None, None, None, None
            action = obj.animation_data.action
            obj_cache = _state.position_cache.get(obj.name, {})
            
            bones_to_check = list(context.selected_pose_bones or [])
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_check:
                bones_to_check.append(active_bone)
                
            for bone in bones_to_check:
                bone_name = bone.name
                if bone_name not in obj_cache:
                    continue
                
                parent_matrix = get_current_parent_matrix(obj, bone)
                
                for frame_num, cache_data in obj_cache[bone_name].items():
                    point_3d = parent_matrix @ cache_data['position']
                    
                    result = check_handles_at_frame(bone_name, frame_num, point_3d, parent_matrix, action, bone)
                    if result:
                        side, handle_pos = result
                        return side, handle_pos, frame_num, point_3d, bone
            
            return None, None, None, None, None
            
        else:
            for cache_obj_name, cache_obj_data in _state.position_cache.items():
                draw_obj = bpy.data.objects.get(cache_obj_name)
                if not draw_obj or None not in cache_obj_data:
                    continue
                draw_action = draw_obj.animation_data.action if draw_obj.animation_data else None
                if not draw_action:
                    continue
                parent_matrix = get_current_parent_matrix(draw_obj)
                for frame_num, cache_data in cache_obj_data[None].items():
                    point_3d = parent_matrix @ cache_data['position']
                    result = check_handles_at_frame(None, frame_num, point_3d, parent_matrix, draw_action)
                    if result:
                        side, handle_pos = result
                        _state.selected_drag_object_name = draw_obj.name
                        return side, handle_pos, frame_num, point_3d, None
        
        return None, None, None, None, None
    
    def get_motion_path_point_at_mouse(self, context, event, region=None, rv3d=None, local_mouse_pos=None):
        """检查鼠标是否在运动路径点上方"""
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
        
        obj_cache = _state.position_cache.get(obj.name, {})
        
        if obj.mode == 'POSE':
            bones_to_check = list(context.selected_pose_bones or [])
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_check:
                bones_to_check.append(active_bone)
            
            for bone in bones_to_check:
                if bone.name not in obj_cache:
                    continue
                
                parent_matrix = get_current_parent_matrix(obj, bone)
                
                for frame_num, cache_data in obj_cache[bone.name].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        return world_pos, frame_num, bone
            
            return None, None, None
        else:
            for cache_obj_name, cache_obj_data in _state.position_cache.items():
                draw_obj = bpy.data.objects.get(cache_obj_name)
                if not draw_obj or None not in cache_obj_data:
                    continue
                parent_matrix = get_current_parent_matrix(draw_obj)
                for frame_num, cache_data in cache_obj_data[None].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        _state.selected_drag_object_name = draw_obj.name
                        return world_pos, frame_num, None
        
        return None, None, None

def get_handle_point_at_mouse(context, event, region=None, rv3d=None, local_mouse_pos=None):
    """检查鼠标是否在手柄控制点上方"""
    global _state
    
    # 安全检查：如果未提供 region/rv3d，确保我们处于 3D 视图上下文中
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

def is_keyframe_selected(action, bone_name, frame):
    """检查指定帧处的关键帧是否被选中。
    
    Args:
        action: 包含 fcurves 的动作
        bone_name: 骨骼名称（用于姿态模式）或 None（用于对象模式）
        frame: 要检查的帧号
        
    Returns:
        bool: 如果关键帧被选中则为 True，否则为 False
    """
    for fc in get_fcurves(action):
        if is_location_fcurve(fc, bone_name):
            for kp in fc.keyframe_points:
                if abs(kp.co[0] - frame) < 0.5:
                    return kp.select_control_point
    return False

def set_handle_type(context, handle_type):
    """为所有选定对象/骨骼的选定关键帧设置手柄类型"""

    # 收集所有需要处理的对象和骨骼
    targets = []

    if context.mode == 'POSE':
        # Pose 模式：处理所有选中骨骼
        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            selected_bones = list(context.selected_pose_bones or [])
            if selected_bones:
                for bone in selected_bones:
                    targets.append((obj, bone.name))
            elif context.active_pose_bone:
                targets.append((obj, context.active_pose_bone.name))
    else:
        # Object 模式：处理所有选中对象
        selected_objects = list(context.selected_objects or [])
        if selected_objects:
            for obj in selected_objects:
                if obj.animation_data and obj.animation_data.action:
                    targets.append((obj, None))
        else:
            obj = context.active_object
            if obj and obj.animation_data and obj.animation_data.action:
                targets.append((obj, None))

    # 批量应用手柄类型
    for obj, bone_name in targets:
        action = obj.animation_data.action
        for fcurve in get_fcurves(action):
            if not is_location_fcurve(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if keyframe.select_control_point:
                    keyframe.handle_left_type = handle_type
                    keyframe.handle_right_type = handle_type
                    if handle_type == 'ALIGNED' or handle_type in {'AUTO', 'AUTO_CLAMPED'}:
                        vec = mathutils.Vector(keyframe.co) - mathutils.Vector(keyframe.handle_left)
                        # 保持右手柄的原始长度
                        len_right = (mathutils.Vector(keyframe.handle_right) - mathutils.Vector(keyframe.co)).length
                        if vec.length > 0.0001:
                            vec.normalize()
                            keyframe.handle_right = mathutils.Vector(keyframe.co) + vec * len_right
                    elif handle_type == 'VECTOR':
                        keyframe.handle_left[1] = keyframe.co[1]
                        keyframe.handle_right[1] = keyframe.co[1]
            fcurve.update()






def _find_and_start_motion_path_operators(context):
    """查找第一个可用的 3D 视图并启动运动路径操作员。
    如果找到视图并启动了操作员，则返回 True，否则返回 False。
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
    """停止运动路径操作员并清除活动标志。"""
    wm = context.window_manager
    wm.direct_manipulation_active = False
    wm.auto_update_active = False


class MOTIONPATH_ToggleCustomDraw(bpy.types.Operator):
    """切换自定义运动路径绘制"""
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

class MOTIONPATH_ResetPreferences(bpy.types.Operator):
    """将运动路径首选项重置为默认值"""
    bl_idname = "motion_path.reset_preferences"
    bl_label = "Reset to Default"
    bl_description = "Reset all motion path settings to default values"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        prefs = get_addon_prefs(context)
        # 重置路径
        prefs.property_unset("path_width")
        prefs.property_unset("path_color")
        # 重置帧点
        prefs.property_unset("show_frame_points")
        prefs.property_unset("frame_point_size")
        prefs.property_unset("frame_point_color")
        # 重置关键帧
        prefs.property_unset("keyframe_point_size")
        prefs.property_unset("keyframe_point_color")
        prefs.property_unset("selected_keyframe_point_color")
        # 重置手柄
        prefs.property_unset("handle_line_width")
        prefs.property_unset("handle_line_color")
        prefs.property_unset("selected_handle_line_color")
        prefs.property_unset("handle_endpoint_size")
        prefs.property_unset("handle_endpoint_color")
        prefs.property_unset("selected_handle_endpoint_color")
        # 重置原点
        prefs.property_unset("show_origin_indicator")
        prefs.property_unset("origin_indicator_style")
        prefs.property_unset("origin_indicator_size")
        prefs.property_unset("origin_indicator_color")
        prefs.property_unset("origin_indicator_inner_color")
        
        # 重绘
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        return {'FINISHED'}

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

    # 路径
    path_width: bpy.props.FloatProperty(name="Path Width", default=2.0, min=1.0, max=10.0)
    path_color: bpy.props.FloatVectorProperty(name="Path Color", subtype='COLOR', size=4, default=(0.8, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    
    # 帧点
    show_frame_points: bpy.props.BoolProperty(name="Show Frame Points", default=True)
    frame_point_size: bpy.props.FloatProperty(name="Frame Point Size", default=4.0, min=1.0, max=20.0)
    frame_point_color: bpy.props.FloatVectorProperty(name="Frame Point Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0)
    
    # 关键帧点
    keyframe_point_size: bpy.props.FloatProperty(name="Keyframe Size", default=10.0, min=1.0, max=30.0)
    keyframe_point_color: bpy.props.FloatVectorProperty(name="Keyframe Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_keyframe_point_color: bpy.props.FloatVectorProperty(name="Selected Keyframe Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)
    
    # 手柄
    handle_line_width: bpy.props.FloatProperty(name="Handle Line Width", default=2.0, min=1.0, max=10.0)
    handle_line_color: bpy.props.FloatVectorProperty(name="Handle Line Color", subtype='COLOR', size=4, default=(0.0, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_line_color: bpy.props.FloatVectorProperty(name="Selected Handle Line Color", subtype='COLOR', size=4, default=(1.0, 0.776, 0.561, 1.0), min=0.0, max=1.0)
    
    handle_endpoint_size: bpy.props.FloatProperty(name="Handle Endpoint Size", default=7.0, min=1.0, max=20.0)
    handle_endpoint_color: bpy.props.FloatVectorProperty(name="Handle Endpoint Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_endpoint_color: bpy.props.FloatVectorProperty(name="Selected Handle Endpoint Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)

    # 原点指示器
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

    def draw(self, context):
        layout = self.layout
        prefs = self
        
        # 添加重置按钮
        row = layout.row()
        row.alignment = 'RIGHT'
        row.operator("motion_path.reset_preferences", text=iface_("Restore Defaults"), icon='LOOP_BACK')

        col = layout.column()
        col.label(text=iface_("Style Settings"))
        col.prop(prefs, "path_width")
        col.prop(prefs, "path_color")
        
        col.separator()
        col.prop(prefs, "show_frame_points")
        if prefs.show_frame_points:
            col.prop(prefs, "frame_point_size")
            col.prop(prefs, "frame_point_color")
            
        col.separator()
        col.label(text=iface_("Keyframes"))
        col.prop(prefs, "keyframe_point_size")
        col.prop(prefs, "keyframe_point_color")
        col.prop(prefs, "selected_keyframe_point_color")
        
        col.separator()
        col.label(text=iface_("Handles"))
        col.prop(prefs, "handle_line_width")
        col.prop(prefs, "handle_line_color")
        col.prop(prefs, "selected_handle_line_color")
        col.prop(prefs, "handle_endpoint_size")
        col.prop(prefs, "handle_endpoint_color")
        col.prop(prefs, "selected_handle_endpoint_color")

        col.separator()
        col.label(text=iface_("Origin Indicator"))
        col.prop(prefs, "show_origin_indicator")
        if prefs.show_origin_indicator:
            col.prop(prefs, "origin_indicator_style")
            col.prop(prefs, "origin_indicator_size")
            col.prop(prefs, "origin_indicator_color")
            if prefs.origin_indicator_style in {'RING_DOT', 'DOT'}:
                col.prop(prefs, "origin_indicator_inner_color")

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
    确保对于存在位置关键帧的每一帧（在任何轴上），
    在所有 3 个轴（X、Y、Z）上都存在关键帧。
    """
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    
    # 确定目标：(data_path_prefix, bone_name_for_check)
    targets = []
    if obj.mode == 'POSE':
        # 在姿态模式下，仅处理选定骨骼
        if context.selected_pose_bones:
            for bone in context.selected_pose_bones:
                 targets.append((f'pose.bones["{bone.name}"].location', bone.name))
    else:
        # 在对象模式下，处理对象位置
        targets.append(('location', None))

    # 使用 get_fcurves 助手来处理 Blender 5.0+ Actions
    fcurves_collection = get_fcurves(action)
    if isinstance(fcurves_collection, list) and not fcurves_collection:
        # 如果列表为空，如果结构缺失，我们可能无法轻松创建新曲线
        # 但如果我们在这里，我们可能有关键帧，所以尝试重新获取或优雅地失败
        return

    for data_path_base, bone_name in targets:
        # 1. 收集此目标位置的所有现有帧
        all_frames = set()
        # 还要跟踪哪些帧存在哪些索引
        # frame -> set of existing indices (0, 1, 2)
        frame_indices = {} 
        
        target_fcurves = []
        # 遍历 fcurves_collection 而不是 action.fcurves
        for fc in fcurves_collection:
            if fc.data_path == data_path_base:
                target_fcurves.append(fc)
                for kp in fc.keyframe_points:
                    frame = int(round(kp.co[0])) # 使用整数帧进行对齐
                    all_frames.add(frame)
                    if frame not in frame_indices:
                        frame_indices[frame] = set()
                    frame_indices[frame].add(fc.array_index)
        
        if not target_fcurves:
            continue

        # 2. 填充缺失的帧
        sorted_frames = sorted(list(all_frames))
        
        modified = False
        
        for frame in sorted_frames:
            existing_indices = frame_indices.get(frame, set())
            missing_indices = {0, 1, 2} - existing_indices
            
            if missing_indices:
                for axis_index in missing_indices:
                    # 检查此轴是否存在 fcurve
                    fc = next((f for f in target_fcurves if f.array_index == axis_index), None)
                    
                    if fc:
                        val = fc.evaluate(frame)
                        fc.keyframe_points.insert(frame, val)
                    else:
                        # 如果缺失，使用 fcurves_collection.new() 创建 FCurve
                        try:
                            # 验证 fcurves_collection 是否支持 .new()
                            if hasattr(fcurves_collection, 'new'):
                                fc = fcurves_collection.new(data_path=data_path_base, index=axis_index)
                                target_fcurves.append(fc)
                                
                                # 获取当前静态值
                                if bone_name:
                                    # 姿态骨骼位置
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
    MOTIONPATH_ResetPreferences,
    MOTIONPATH_PT_header_settings,
    MOTIONPATH_AddonPreferences,
    MOTIONPATH_MT_context_menu,
    
    MOTIONPATH_DirectManipulation,
    MOTIONPATH_DirectManipulationToggle,
    MOTIONPATH_AutoUpdateMotionPaths,
    MOTIONPATH_SetHandleType,
)

motion_path_update_mode_items = [
    ('SMART', "智能 (事件)", "仅在相关数据更改时更新（零空闲功耗）"),
    ('TIMER', "计时器 (轮询)", "定期更新（稳定但功耗较高）")
]

handle_type_items = [
    ('FREE', "自由", "手柄可以独立调整"),
    ('ALIGNED', "对齐", "手柄对齐以保持平滑"),
    ('VECTOR', "矢量", "创建线性插值"),
    ('AUTO', "自动", "自动平滑手柄"),
    ('AUTO_CLAMPED', "自动钳位", "具有钳位值的自动手柄"),
]

def register():
    translations.register(__package__)
    for cls in classes:
        bpy.utils.register_class(cls)
    


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
    
    # 性能设置
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
    
    # 附加到标题
    if hasattr(bpy.types, "VIEW3D_HT_header"):
        bpy.types.VIEW3D_HT_header.append(draw_header_button)

def unregister():
    global _circle_aa_shader
    _circle_aa_shader = None
    # 从标题中移除
    if hasattr(bpy.types, "VIEW3D_HT_header"):
        bpy.types.VIEW3D_HT_header.remove(draw_header_button)

    for cls in classes:
        bpy.utils.unregister_class(cls)
        

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