import bpy
import mathutils
from .state import _state, _is_updating_cache, SAFE_LIMIT


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


def is_location_fcurve(fcurve, bone_name=None):
    if bone_name:
        return fcurve.data_path == f'pose.bones["{bone_name}"].location'
    return fcurve.data_path == 'location'


def is_keyframe_at_frame(fcurves, frame_num, bone_name=None):
    for fcurve in fcurves:
        if is_location_fcurve(fcurve, bone_name):
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame_num) < 0.5:
                    return True
    return False


def calculate_path_from_fcurves(obj, action, frames, bone_name=None):
    path_data = {}
    
    fcurves = [fc for fc in get_fcurves(action) if is_location_fcurve(fc, bone_name)]
    
    fcurves_by_axis = {}
    for fc in fcurves:
        fcurves_by_axis[fc.array_index] = fc
        
    if bone_name:
        if bone_name in obj.pose.bones:
            defaults = obj.pose.bones[bone_name].location.copy()
        else:
            defaults = mathutils.Vector((0, 0, 0))
        delta_loc = mathutils.Vector((0, 0, 0))
    else:
        defaults = obj.location.copy()
        delta_loc = obj.delta_location
    
    for frame in frames:
        pos = defaults.copy()
        for axis in range(3):
            if axis in fcurves_by_axis:
                pos[axis] = fcurves_by_axis[axis].evaluate(frame)
        
        pos = pos + delta_loc
        
        path_data[frame] = {
            'position': pos
        }
        
    return path_data


def build_position_cache(context):
    global _state, _is_updating_cache
    
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

