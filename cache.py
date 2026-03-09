import bpy
import mathutils
from .state import _session, _cache_update_lock, SAFE_LIMIT


def collect_animation_curves(action):
    """从Blender 5.0+分层动作系统中提取动画曲线集合"""
    if action is None:
        return []
    
    result = []
    
    try:
        action_layers = action.layers
        action_slots = action.slots
        
        if not action_layers or not action_slots:
            return result
        
        target_layer = action_layers[0]
        if not target_layer.strips:
            return result
        
        target_strip = target_layer.strips[0]
        target_slot = action_slots[0]
        
        channel_container = target_strip.channelbag(target_slot, ensure=True)
        
        if channel_container is not None:
            result = list(channel_container.fcurves)
            
    except Exception:
        pass
    
    return result


def is_position_animation(fcurve, target_bone=None):
    """判断动画曲线是否控制位置属性"""
    expected_path = 'location'
    if target_bone is not None:
        expected_path = f'pose.bones["{target_bone}"].location'
    
    return fcurve.data_path == expected_path


def frame_has_keyframe(curves_collection, frame_number, target_bone=None):
    """检查指定帧是否存在关键帧"""
    for curve in curves_collection:
        if is_position_animation(curve, target_bone):
            for keypoint in curve.keyframe_points:
                if abs(keypoint.co[0] - frame_number) < 0.5:
                    return True
    return False


def compute_motion_positions(obj, action, frame_list, target_bone=None):
    """从动画曲线计算指定帧的位置数据"""
    position_data = {}
    
    relevant_curves = [curve for curve in collect_animation_curves(action) if is_position_animation(curve, target_bone)]
    
    curves_by_axis = {}
    for curve in relevant_curves:
        curves_by_axis[curve.array_index] = curve
        
    if target_bone:
        if target_bone in obj.pose.bones:
            base_values = obj.pose.bones[target_bone].location.copy()
        else:
            base_values = mathutils.Vector((0, 0, 0))
        delta_offset = mathutils.Vector((0, 0, 0))
    else:
        base_values = obj.location.copy()
        delta_offset = obj.delta_location
    
    for frame in frame_list:
        computed_pos = base_values.copy()
        for axis in range(3):
            if axis in curves_by_axis:
                computed_pos[axis] = curves_by_axis[axis].evaluate(frame)
        
        computed_pos = computed_pos + delta_offset
        
        position_data[frame] = {
            'position': computed_pos
        }
        
    return position_data


def refresh_position_store(context):
    """刷新位置缓存存储"""
    global _session, _cache_update_lock
    
    if _cache_update_lock:
        return
        
    _cache_update_lock = True
    
    try:
        _session.cached_positions = {}
        _session.path_point_sequence = {}
        
        if hasattr(context.window_manager, 'skip_motion_path_cache'):
            if context.window_manager.skip_motion_path_cache:
                return
        
        obj = context.active_object
        wm = context.window_manager
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end
        frames_range = range(frame_start, frame_end + 1)
        
        if obj and obj.mode == 'POSE':
            if not obj.animation_data or not obj.animation_data.action:
                return
            action = obj.animation_data.action
            obj_name = obj.name
            
            bones_to_process = set(context.selected_pose_bones or [])
            if context.active_pose_bone:
                bones_to_process.add(context.active_pose_bone)

            for bone in bones_to_process:
                try:
                    bone_name = bone.name
                    curves = [curve for curve in collect_animation_curves(action) if is_position_animation(curve, bone_name)]
                    frames = set(int(kp.co[0]) for curve in curves for kp in curve.keyframe_points
                                 if frame_start <= kp.co[0] <= frame_end)
                    if not frames:
                        continue
                    position_data = compute_motion_positions(obj, action, frames, target_bone=bone_name)
                    _session.cached_positions.setdefault(obj_name, {})[bone_name] = position_data
                    
                    if wm.rtmp_path_display_enabled:
                        dense_data = compute_motion_positions(obj, action, frames_range, target_bone=bone_name)
                        _session.path_point_sequence[(obj_name, bone_name)] = [dense_data[f]['position'] for f in frames_range]
                except Exception:
                    continue
        else:
            objects_to_process = list(context.selected_objects or [])
            if obj and obj not in objects_to_process:
                objects_to_process.append(obj)
            
            for cache_obj in objects_to_process:
                try:
                    if not cache_obj.animation_data or not cache_obj.animation_data.action:
                        continue
                    action = cache_obj.animation_data.action
                    obj_name = cache_obj.name
                    
                    curves = [curve for curve in collect_animation_curves(action) if is_position_animation(curve)]
                    frames = sorted(set(int(kp.co[0]) for curve in curves for kp in curve.keyframe_points
                                 if frame_start <= kp.co[0] <= frame_end))
                    if not frames:
                        continue
                    position_data = compute_motion_positions(cache_obj, action, frames)
                    _session.cached_positions.setdefault(obj_name, {})[None] = position_data
                    
                    if wm.rtmp_path_display_enabled:
                        dense_data = compute_motion_positions(cache_obj, action, frames_range)
                        _session.path_point_sequence[(obj_name, None)] = [dense_data[f]['position'] for f in frames_range]
                except Exception:
                    continue
     
    finally:
        _cache_update_lock = False


def resolve_parent_transform(obj, bone=None):
    """解析父级变换矩阵"""
    try:
        if obj.mode == 'POSE' and bone:
            if bone.parent:
                parent_to_child_rest = bone.parent.bone.matrix_local.inverted() @ bone.bone.matrix_local
                return obj.matrix_world @ bone.parent.matrix @ parent_to_child_rest
            else:
                return obj.matrix_world @ bone.bone.matrix_local
        else:
            if obj.parent is None:
                return mathutils.Matrix.Identity(4)
            else:
                parent_mat = obj.parent.matrix_world.copy()
                if obj.parent_type == 'BONE' and obj.parent_bone:
                    if obj.parent.pose and obj.parent_bone in obj.parent.pose.bones:
                        pb = obj.parent.pose.bones[obj.parent_bone]
                        parent_mat = obj.parent.matrix_world @ pb.matrix
                return parent_mat @ obj.matrix_parent_inverse
    except Exception:
        return mathutils.Matrix.Identity(4)
