import bpy
import mathutils
import math
import time
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
from bpy.app.translations import pgettext_iface as iface_
from .state import _session, HANDLE_SELECT_RADIUS, SAFE_LIMIT
from .cache import collect_animation_curves, is_position_animation, resolve_parent_transform, refresh_position_store, frame_has_keyframe
from .drawing import compute_handle_display_factors, attach_render_callback, detach_render_callback


def _get_drag_obj(context):
    global _session
    if _session.drag_target_object:
        try:
            obj = bpy.data.objects.get(_session.drag_target_object)
            if obj:
                return obj
        except Exception:
            pass
    return context.active_object


@persistent
def on_depsgraph_update(scene, depsgraph):
    global _session
    
    if _session.drag_in_progress or _session.handle_edit_in_progress:
        return

    wm = bpy.context.window_manager
    if not wm.rtmp_path_display_enabled or wm.rtmp_refresh_strategy != 'SMART':
        return

    is_object_updated = depsgraph.id_type_updated('OBJECT')
    is_action_updated = depsgraph.id_type_updated('ACTION')
    
    if is_object_updated or is_action_updated:
        if bpy.context.screen and bpy.context.screen.is_animation_playing:
            return

        try:
            has_relevant_objects = (bpy.context.active_object or bpy.context.selected_objects)
            if has_relevant_objects:
                is_interaction_update = is_object_updated and not is_action_updated
                
                if is_interaction_update:
                    return

                refresh_position_store(bpy.context)
                
                for window in wm.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()
        except Exception as e:
            print(f"Error in smart update: {e}")


class RTMP_OT_PathRefreshDaemon(bpy.types.Operator):
    bl_idname = "rtmp.path_refresh_daemon"
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
        self._last_keyframe_values = self._collect_keyframe_snapshot(context)
        self._last_active_obj_name = context.active_object.name if context.active_object else None
        self._last_selected_obj_names = self._collect_selected_names(context)
        self._last_bone_selection = self._collect_bone_selection(context)
        self._needs_update = False
        
        if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
            
        interval = 1.0 / max(1, wm.rtmp_poll_frequency)
        self._timer = wm.event_timer_add(interval, window=context.window)
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        wm = context.window_manager

        active_obj = context.active_object
        current_obj_name = active_obj.name if active_obj else None
        if current_obj_name != self._last_active_obj_name:
            self._last_active_obj_name = current_obj_name
            _session.active_path_point = None
            _session.active_frame_number = None
            _session.active_handle_direction = None
            _session.active_bone_identifier = None
            _session.active_handle_index = None
            _session.active_handle_info = None
            _session.drag_in_progress = False
            _session.handle_edit_in_progress = False
            _session.drag_target_object = None
            self._needs_update = True

        current_selected = self._collect_selected_names(context)
        if current_selected != self._last_selected_obj_names:
            self._last_selected_obj_names = current_selected
            self._needs_update = True

        current_bone_selection = self._collect_bone_selection(context)
        if current_bone_selection != self._last_bone_selection:
            self._last_bone_selection = current_bone_selection
            if current_bone_selection is None:
                _session.active_bone_identifier = None
            self._needs_update = True
        
        if wm.rtmp_refresh_strategy == 'TIMER' and event.type == 'TIMER':
            current_values = self._collect_keyframe_snapshot(context)
            if current_values != self._last_keyframe_values:
                self._needs_update = True
                self._last_keyframe_values = current_values
                
        if self._needs_update:
            try:
                refresh_position_store(context)
            except Exception as e:
                print("Error updating position cache:", e)
            self._needs_update = False
            for window in wm.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        
        if not wm.rtmp_auto_refresh_active:
            self.cancel(context)
            return {'CANCELLED'}
        
        return {'PASS_THROUGH'}
    
    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
            self._timer = None
            
        if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
            bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    
    def _collect_object_keyframes(self, obj):
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return []
        action = obj.animation_data.action
        values = []
        for fcurve in collect_animation_curves(action):
            for keyframe in fcurve.keyframe_points:
                values.append((
                    keyframe.co[0], keyframe.co[1],
                    keyframe.handle_left[0], keyframe.handle_left[1],
                    keyframe.handle_right[0], keyframe.handle_right[1],
                    keyframe.select_control_point
                ))
        return values

    def _collect_keyframe_snapshot(self, context):
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
    
    def _collect_selected_names(self, context):
        return tuple(sorted(obj.name for obj in context.selected_objects)) if context.selected_objects else ()
    
    def _collect_bone_selection(self, context):
        active_object = context.active_object
        if not active_object or active_object.mode != 'POSE':
            return None
            
        active_bone_name = context.active_pose_bone.name if context.active_pose_bone else None
        selected_bone_names = tuple(sorted([b.name for b in context.selected_pose_bones])) if context.selected_pose_bones else ()
        
        return (active_bone_name, selected_bone_names)


class RTMP_OT_ChangeHandleMode(bpy.types.Operator):
    bl_idname = "rtmp.change_handle_mode"
    bl_label = "Set Handle Type"
    bl_options = {'REGISTER', 'UNDO'}
    
    handle_type: bpy.props.StringProperty()
    
    def execute(self, context):
        handle_type = self.handle_type
        if not handle_type:
            handle_type = context.window_manager.rtmp_handle_type
        apply_handle_mode(context, handle_type)
        refresh_position_store(context)
        return {'FINISHED'}


class RTMP_OT_ToggleEditMode(bpy.types.Operator):
    bl_idname = "rtmp.toggle_edit_mode"
    bl_label = "Toggle Direct Manipulation"
    bl_description = "Enable/Disable Motion Path Editing"
    
    def execute(self, context):
        global _session
        wm = context.window_manager
        
        if not wm.rtmp_edit_mode_active:
            wm.rtmp_edit_mode_active = True
            bpy.ops.rtmp.path_point_drag('INVOKE_DEFAULT')
            wm.rtmp_auto_refresh_active = True
            bpy.ops.rtmp.path_refresh_daemon('INVOKE_DEFAULT')
            self.report({'INFO'}, iface_("Enable Direct Path Editing"))
        else:
            wm.rtmp_edit_mode_active = False
            wm.rtmp_auto_refresh_active = False
            if context.area:
                context.area.tag_redraw()
            self.report({'INFO'}, iface_("Disable Direct Path Editing"))
        
        return {'FINISHED'}


def find_region_under_mouse(context, event):
    mouse_x = event.mouse_x
    mouse_y = event.mouse_y

    windows_to_check = [context.window] if context.window else []
    for win in context.window_manager.windows:
        if win not in windows_to_check:
            windows_to_check.append(win)
            
    for window in windows_to_check:
        screen = window.screen
        if not screen: continue
        
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
                
            if (area.x <= mouse_x < area.x + area.width and
                area.y <= mouse_y < area.y + area.height):
                
                for region in area.regions:
                    if region.type == 'WINDOW':
                        if (region.x <= mouse_x < region.x + region.width and
                            region.y <= mouse_y < region.y + region.height):
                            
                            local_x = mouse_x - region.x
                            local_y = mouse_y - region.y
                            space_data = area.spaces.active
                            return region, space_data, (local_x, local_y), area

    return None, None, None, None


class RTMP_OT_PathPointDrag(bpy.types.Operator):
    bl_idname = "rtmp.path_point_drag"
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
    
    def prepare_handles_for_edit(self, frame_kf_map):
        for array_index, keyframe in frame_kf_map.items():
            if (keyframe.handle_left_type == 'VECTOR' and 
                keyframe.handle_right_type == 'VECTOR'):
                
                original_left = keyframe.handle_left.copy()
                original_right = keyframe.handle_right.copy()
                
                keyframe.handle_left_type = 'FREE'
                keyframe.handle_right_type = 'FREE'
                
                keyframe.handle_left = original_left
                keyframe.handle_right = original_right
    
    def modal(self, context, event):
        global _session

        wm = context.window_manager
        if not wm.rtmp_edit_mode_active or not self._is_active:
            return self.cancel(context)
        
        if event.type == 'MOUSEMOVE':
            self._mouse_pos = (event.mouse_region_x, event.mouse_region_y)
            
            target_interval = 1.0 / max(1, wm.rtmp_max_interaction_fps)
            current_time = time.time()
            if (current_time - self._last_draw_time) < target_interval:
                return {'PASS_THROUGH'}
            self._last_draw_time = current_time
            
            region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
            if not region or not space_data:
                return {'PASS_THROUGH'}

            rv3d = space_data.region_3d

            if _session.drag_in_progress:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _session.world_origin)

                if _session.active_handle_direction is None:
                    offset = new_3d_pos - _session.world_origin
                    self.apply_point_offset(context, offset)
                    _session.world_origin = new_3d_pos
                else:
                    total_offset = new_3d_pos - _session.world_origin
                    self.apply_handle_offset(context, total_offset, _session.active_handle_direction)

                try:
                    refresh_position_store(context)
                except Exception:
                    pass

                area_to_redraw = target_area if target_area else context.area
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            elif _session.handle_edit_in_progress and _session.active_handle_index is not None:
                mouse_coord = mathutils.Vector(local_mouse_pos)
                
                new_3d_pos = view3d_utils.region_2d_to_location_3d(region, rv3d, mouse_coord, _session.world_origin)
                total_offset = new_3d_pos - _session.world_origin
                
                if _session.active_handle_info:
                    handle_point = _session.active_handle_info
                    self.apply_handle_point_offset(context, total_offset, handle_point)
                elif _session.active_handle_index is not None and _session.active_handle_index < len(_session.handle_control_points):
                    handle_point = _session.handle_control_points[_session.active_handle_index]
                    self.apply_handle_point_offset(context, total_offset, handle_point)
                
                try:
                    refresh_position_store(context)
                except Exception:
                    pass

                area_to_redraw = target_area if target_area else context.area
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            return {'PASS_THROUGH'}
        
        elif event.type == 'RIGHTMOUSE':
            if event.value == 'PRESS':
                region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d

                hit_point, hit_frame, hit_bone = self.locate_point_under_cursor(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _session.active_path_point = hit_point
                    _session.active_frame_number = hit_frame
                    
                    if context.mode == 'POSE':
                        _session.active_bone_identifier = hit_bone.name if hit_bone else None
                    else:
                        _session.active_bone_identifier = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _session.active_bone_identifier if context.mode == 'POSE' else None
                        
                        hit_keyframe_already_selected = is_keyframe_selected(action, bone_name, hit_frame)
                        
                        if not hit_keyframe_already_selected:
                            for fc in collect_animation_curves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        for fc in collect_animation_curves(action):
                            if is_position_animation(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    area_to_redraw = target_area if target_area else context.area
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    
                    bpy.ops.wm.call_menu(name="RTMP_MT_context_menu")
                    return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}

        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                region, space_data, local_mouse_pos, target_area = find_region_under_mouse(context, event)
                if not region or not space_data:
                    return {'PASS_THROUGH'}
                rv3d = space_data.region_3d
                area_to_redraw = target_area if target_area else context.area

                if not event.shift:
                    _session.active_handle_index = None
                    _session.active_handle_info = None
                    _session.active_path_point = None
                    _session.active_frame_number = None
                
                handle_index, handle_point = get_handle_at_cursor(context, event, region, rv3d, local_mouse_pos)
                if handle_index is not None:
                    _session.active_handle_index = handle_index
                    _session.active_handle_info = handle_point
                    _session.handle_edit_in_progress = True
                    _session.world_origin = handle_point['position']
                    _session.item_initial_pos = handle_point['position']
                    _session.mouse_origin = local_mouse_pos
                    
                    hp_obj_name = handle_point.get('obj_name')
                    _session.drag_target_object = hp_obj_name or None
                    
                    self.record_handle_baseline(context, handle_point['frame'], handle_point.get('bone_name'), handle_point['side'])
                    
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                hit_side, hit_handle_pos, hit_frame, point_3d, hit_bone = self.locate_handle_under_cursor(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _session.active_path_point = point_3d
                    _session.active_frame_number = hit_frame
                    _session.active_handle_direction = hit_side
                    _session.world_origin = point_3d  
                    _session.item_initial_pos = hit_handle_pos
                    _session.mouse_origin = local_mouse_pos
                    
                    self.record_handle_baseline(context, hit_frame, hit_bone.name if hit_bone else None, hit_side)
                    
                    if context.mode == 'POSE':
                        _session.active_bone_identifier = hit_bone.name if hit_bone else None
                    else:
                        _session.active_bone_identifier = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _session.active_bone_identifier if context.mode == 'POSE' else None
                        
                        for fc in collect_animation_curves(action):
                            if is_position_animation(fc, bone_name):
                                for kp in fc.keyframe_points:
                                    if abs(kp.co[0] - hit_frame) < 0.5:
                                        kp.select_control_point = True
                                        break
                    
                    _session.drag_in_progress = True
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                hit_point, hit_frame, hit_bone = self.locate_point_under_cursor(context, event, region, rv3d, local_mouse_pos)
                if hit_frame is not None:
                    _session.active_path_point = hit_point
                    _session.active_frame_number = hit_frame
                    _session.active_handle_direction = None  
                    _session.world_origin = hit_point
                    _session.item_initial_pos = hit_point
                    _session.mouse_origin = local_mouse_pos
                    
                    if context.mode == 'POSE':
                        _session.active_bone_identifier = hit_bone.name if hit_bone else None
                    else:
                        _session.active_bone_identifier = None
                    
                    obj = _get_drag_obj(context)
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        bone_name = _session.active_bone_identifier if context.mode == 'POSE' else None
                        
                        hit_keyframe_already_selected = is_keyframe_selected(action, bone_name, hit_frame)
                        
                        if not hit_keyframe_already_selected and not event.shift and not event.ctrl:
                            for fc in collect_animation_curves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                        
                        if event.ctrl:
                            kf_frame_set = []
                            for fc in collect_animation_curves(action):
                                if is_position_animation(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        if kp.select_control_point:
                                            kf_frame_set.append(kp.co[0])
                            kf_frame_set.append(hit_frame)
                            if len(kf_frame_set) >= 2:
                                min_f = min(kf_frame_set)
                                max_f = max(kf_frame_set)
                                for fc in collect_animation_curves(action):
                                    if is_position_animation(fc, bone_name):
                                        for kp in fc.keyframe_points:
                                            if min_f <= kp.co[0] <= max_f:
                                                kp.select_control_point = True
                        else:
                            for fc in collect_animation_curves(action):
                                if is_position_animation(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        if abs(kp.co[0] - hit_frame) < 0.5:
                                            kp.select_control_point = True
                                            break
                    
                    _session.drag_in_progress = True
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                if context.mode == 'POSE':
                    obj = context.active_object
                    if obj and obj.animation_data and obj.animation_data.action:
                        action = obj.animation_data.action
                        obj_cache = _session.cached_positions.get(obj.name, {})
                        for bone_name in obj_cache.keys():
                            for fc in collect_animation_curves(action):
                                if is_position_animation(fc, bone_name):
                                    for kp in fc.keyframe_points:
                                        kp.select_control_point = False
                else:
                    for obj_name in _session.cached_positions.keys():
                        obj = bpy.data.objects.get(obj_name)
                        if obj and obj.animation_data and obj.animation_data.action:
                            action = obj.animation_data.action
                            for fc in collect_animation_curves(action):
                                for kp in fc.keyframe_points:
                                    kp.select_control_point = False
                
                if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                    area_to_redraw.tag_redraw()
                    
            elif event.value == 'RELEASE':
                if _session.drag_in_progress:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Points"))
                    _session.drag_in_progress = False
                    _session.active_path_point = None
                    _session.active_frame_number = None
                    _session.active_handle_direction = None
                    _session.item_initial_pos = None
                    _session.drag_target_object = None
                    
                    try:
                        refresh_position_store(context)
                    except Exception:
                        pass
                    
                    _, _, _, release_area = find_region_under_mouse(context, event)
                    area_to_redraw = release_area if release_area else context.area
                    if area_to_redraw and area_to_redraw.type == 'VIEW_3D':
                        area_to_redraw.tag_redraw()
                    return {'RUNNING_MODAL'}
                elif _session.handle_edit_in_progress:
                    bpy.ops.ed.undo_push(message=iface_("Move Motion Path Handle"))
                    _session.handle_edit_in_progress = False
                    _session.active_handle_index = None
                    _session.item_initial_pos = None
                    _session.drag_target_object = None
                    
                    try:
                        refresh_position_store(context)
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
        
        return {'PASS_THROUGH'}
    
    def invoke(self, context, event):
        if context.area.type == 'VIEW_3D':
            refresh_position_store(context)
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
            context.window_manager.modal_handler_add(self)
            self._is_active = True
            attach_render_callback()
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, iface_("View3D not found, cannot run operator"))
            return {'CANCELLED'}
    
    def cancel(self, context):
        global _session
        
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        
        _session.reset()
        self._is_active = False
        detach_render_callback()
        
        if context.area:
            context.area.tag_redraw()
        
        return {'CANCELLED'}
    
    def apply_point_offset(self, context, offset):
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in offset):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        bone_name = _session.active_bone_identifier if (obj and obj.mode == 'POSE') else None
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        
        parent_matrix = resolve_parent_transform(obj, bone)
        parent_rot_inv = parent_matrix.to_3x3().inverted()
        
        local_kf_delta = parent_rot_inv @ offset
        
        kf_frame_set = set()
        for fcurve in collect_animation_curves(action):
            if 'location' not in fcurve.data_path:
                continue
            if bone_name and not is_position_animation(fcurve, bone_name):
                continue
            for kp in fcurve.keyframe_points:
                if kp.select_control_point:
                    kf_frame_set.add(int(kp.co[0]))
        
        for frame in kf_frame_set:
            for fcurve in collect_animation_curves(action):
                if 'location' not in fcurve.data_path:
                    continue
                if bone_name and not is_position_animation(fcurve, bone_name):
                    continue
                
                axis = fcurve.array_index
                for kp in fcurve.keyframe_points:
                    if abs(kp.co[0] - frame) < 0.5:
                        kp.co[1] += local_kf_delta[axis]
                        kp.handle_left[1] += local_kf_delta[axis]
                        kp.handle_right[1] += local_kf_delta[axis]
                        break
        
        for fcurve in collect_animation_curves(action):
            if 'location' in fcurve.data_path and (not bone_name or is_position_animation(fcurve, bone_name)):
                fcurve.update()
    
    def apply_handle_offset(self, context, total_offset_world, side):
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        frame = _session.active_frame_number
        global_scale = context.window_manager.rtmp_handle_scale
        bone_name = _session.active_bone_identifier if (obj and obj.mode == 'POSE') else None
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        
        parent_matrix = resolve_parent_transform(obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        total_offset_local = rotation_matrix.inverted() @ total_offset_world
        total_offset_local_scaled = total_offset_local / global_scale

        frame_kf_map = {}
        for fcurve in collect_animation_curves(action):
            if not is_position_animation(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame) < 0.5:
                    frame_kf_map[fcurve.array_index] = keyframe
                    break
        
        self.prepare_handles_for_edit(frame_kf_map)

        factors_left, factors_right = compute_handle_display_factors(frame_kf_map)

        for array_index, keyframe in frame_kf_map.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            initial_val = _session.handle_start_values.get((frame, array_index))
            if initial_val is None:
                continue
            
            initial_pos_2d = mathutils.Vector(initial_val)
            
            if side == 'left':
                factor = factors_left.get(array_index, 1.0)
                delta_val = total_offset_local_scaled[array_index] / factor
                keyframe.handle_left[1] = initial_pos_2d[1] + delta_val
            else:
                factor = factors_right.get(array_index, 1.0)
                delta_val = total_offset_local_scaled[array_index] / factor
                keyframe.handle_right[1] = initial_pos_2d[1] + delta_val
            
            temp_handle_vector_local = mathutils.Vector((0.0, 0.0, 0.0))
            if side == 'left':
                temp_handle_vector_local[array_index] = keyframe.co[1] - keyframe.handle_left[1]
            else:
                temp_handle_vector_local[array_index] = keyframe.handle_right[1] - keyframe.co[1]
            
            self.update_linked_handle(keyframe, side, temp_handle_vector_local, array_index)
            
            keyframe.handle_left_type = original_left_type
            keyframe.handle_right_type = original_right_type
        
        for fcurve in collect_animation_curves(action):
            if is_position_animation(fcurve, bone_name):
                fcurve.update()
    
    def update_linked_handle(self, keyframe, moved_handle_side, handle_vector_local, array_index):
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
            
            co = mathutils.Vector(keyframe.co)
            
            if moved_handle_side == 'left':
                handle_active = mathutils.Vector(keyframe.handle_left)
                handle_opposite = mathutils.Vector(keyframe.handle_right)
                target_handle_attr = 'handle_right'
            else:
                handle_active = mathutils.Vector(keyframe.handle_right)
                handle_opposite = mathutils.Vector(keyframe.handle_left)
                target_handle_attr = 'handle_left'
            
            dx_active = handle_active.x - co.x
            dy_active = handle_active.y - co.y
            
            if abs(dx_active) < 0.0001:
                return

            slope = dy_active / dx_active
            
            dx_opposite = handle_opposite.x - co.x
            new_y_opposite = co.y + (slope * dx_opposite)
            
            if target_handle_attr == 'handle_right':
                keyframe.handle_right[1] = new_y_opposite
            else:
                keyframe.handle_left[1] = new_y_opposite
            
            return
    
    def apply_handle_point_offset(self, context, total_offset_world, handle_point):
        if not all(math.isfinite(c) and abs(c) < SAFE_LIMIT for c in total_offset_world):
            return

        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        frame = handle_point['frame']
        side = handle_point['side']
        bone_name = handle_point.get('bone_name')
        bone = (obj.pose.bones.get(bone_name) if (bone_name and obj.mode == 'POSE' and obj.pose) else None)
        global_scale = context.window_manager.rtmp_handle_scale
        
        parent_matrix = resolve_parent_transform(obj, bone)
        rotation_matrix = parent_matrix.to_3x3()
        
        total_offset_local = rotation_matrix.inverted() @ total_offset_world
        total_offset_local_scaled = total_offset_local / global_scale
        
        frame_kf_map = {}
        for fcurve in collect_animation_curves(action):
            if not is_position_animation(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if abs(keyframe.co[0] - frame) < 0.5:
                    frame_kf_map[fcurve.array_index] = keyframe
                    break
        
        self.prepare_handles_for_edit(frame_kf_map)
        
        factors_left, factors_right = compute_handle_display_factors(frame_kf_map)
        
        for array_index, keyframe in frame_kf_map.items():
            original_left_type = keyframe.handle_left_type
            original_right_type = keyframe.handle_right_type
            
            if original_left_type in {'AUTO', 'AUTO_CLAMPED'} or original_right_type in {'AUTO', 'AUTO_CLAMPED'}:
                keyframe.handle_left_type = 'ALIGNED'
                keyframe.handle_right_type = 'ALIGNED'
            
            initial_val = _session.handle_start_values.get((frame, array_index))
            if initial_val is None:
                continue
            
            initial_pos_2d = mathutils.Vector(initial_val)
            
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
            
            temp_handle_vector_local = mathutils.Vector((0.0, 0.0, 0.0))
            if side == 'left':
                temp_handle_vector_local[array_index] = keyframe.co[1] - keyframe.handle_left[1]
            else:
                temp_handle_vector_local[array_index] = keyframe.handle_right[1] - keyframe.co[1]

            self.update_linked_handle(keyframe, side, temp_handle_vector_local, array_index)
            
            if original_left_type in {'VECTOR', 'FREE'}:
                keyframe.handle_left_type = original_left_type
            if original_right_type in {'VECTOR', 'FREE'}:
                keyframe.handle_right_type = original_right_type
        
        for fcurve in collect_animation_curves(action):
            if is_position_animation(fcurve, bone_name):
                fcurve.update()
    
    def resolve_handle_anchor_pos(self, context, handle_point):
        global _session
        obj = _get_drag_obj(context)
        frame = handle_point['frame']
        bone_name = handle_point.get('bone_name')
        
        if not obj:
            return mathutils.Vector((0, 0, 0))
        
        obj_cache = _session.cached_positions.get(obj.name, {})
        cache_key = bone_name if bone_name else None
        sub_cache = obj_cache.get(cache_key, {})
        cache_data = sub_cache.get(frame)
        if cache_data:
            return cache_data['position']
        
        return mathutils.Vector((0, 0, 0))
    
    def record_handle_baseline(self, context, frame_num, selected_bone_name, handle_side):
        global _session
        _session.handle_start_values = {}
        
        obj = _get_drag_obj(context)
        if not obj or not obj.animation_data or not obj.animation_data.action:
            return
        
        action = obj.animation_data.action
        fcurves = collect_animation_curves(action)
        
        frame_kf_map = {}
        for i, fcurve in enumerate(fcurves):
            if is_position_animation(fcurve, selected_bone_name):
                for kp in fcurve.keyframe_points:
                    if abs(kp.co[0] - frame_num) < 0.001:
                        array_index = fcurve.array_index
                        frame_kf_map[array_index] = kp
                        break
        
        if not frame_kf_map:
            return
        
        for array_index, kp in frame_kf_map.items():
            if handle_side == 'left':
                _session.handle_start_values[(frame_num, array_index)] = (kp.handle_left[0], kp.handle_left[1])
            else:
                _session.handle_start_values[(frame_num, array_index)] = (kp.handle_right[0], kp.handle_right[1])

    def locate_handle_under_cursor(self, context, event, region=None, rv3d=None, local_mouse_pos=None):
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
            if not frame_has_keyframe(collect_animation_curves(check_action), frame_num, bone_name):
                return None
            
            frame_kf_map = {}
            for fcurve in collect_animation_curves(check_action):
                if is_position_animation(fcurve, bone_name):
                    for keyframe in fcurve.keyframe_points:
                        if abs(keyframe.co[0] - frame_num) < 0.5:
                            frame_kf_map[fcurve.array_index] = keyframe
                            break
            
            if not frame_kf_map:
                return None
            
            factors_left, factors_right = compute_handle_display_factors(frame_kf_map)
            
            handle_vector_left = mathutils.Vector((0.0, 0.0, 0.0))
            handle_vector_right = mathutils.Vector((0.0, 0.0, 0.0))
            
            for array_index, keyframe in frame_kf_map.items():
                factor_l = factors_left.get(array_index, 1.0)
                factor_r = factors_right.get(array_index, 1.0)
                
                diff = (keyframe.handle_left[1] - keyframe.co[1]) * factor_l
                handle_vector_left[array_index] = diff
                diff = (keyframe.handle_right[1] - keyframe.co[1]) * factor_r
                handle_vector_right[array_index] = diff
            
            rotation_matrix = parent_matrix.to_3x3()
            world_vector_left = rotation_matrix @ handle_vector_left
            world_vector_right = rotation_matrix @ handle_vector_right
            
            global_scale = context.window_manager.rtmp_handle_scale
            
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
            obj_cache = _session.cached_positions.get(obj.name, {})
            
            bones_to_check = list(context.selected_pose_bones or [])
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_check:
                bones_to_check.append(active_bone)
                
            for bone in bones_to_check:
                bone_name = bone.name
                if bone_name not in obj_cache:
                    continue
                
                parent_matrix = resolve_parent_transform(obj, bone)
                
                for frame_num, cache_data in obj_cache[bone_name].items():
                    point_3d = parent_matrix @ cache_data['position']
                    
                    result = check_handles_at_frame(bone_name, frame_num, point_3d, parent_matrix, action, bone)
                    if result:
                        side, handle_pos = result
                        return side, handle_pos, frame_num, point_3d, bone
            
            return None, None, None, None, None
            
        else:
            for cache_obj_name, cache_obj_data in _session.cached_positions.items():
                draw_obj = bpy.data.objects.get(cache_obj_name)
                if not draw_obj or None not in cache_obj_data:
                    continue
                draw_action = draw_obj.animation_data.action if draw_obj.animation_data else None
                if not draw_action:
                    continue
                parent_matrix = resolve_parent_transform(draw_obj)
                for frame_num, cache_data in cache_obj_data[None].items():
                    point_3d = parent_matrix @ cache_data['position']
                    result = check_handles_at_frame(None, frame_num, point_3d, parent_matrix, draw_action)
                    if result:
                        side, handle_pos = result
                        _session.drag_target_object = draw_obj.name
                        return side, handle_pos, frame_num, point_3d, None
        
        return None, None, None, None, None
    
    def locate_point_under_cursor(self, context, event, region=None, rv3d=None, local_mouse_pos=None):
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
        
        obj_cache = _session.cached_positions.get(obj.name, {})
        
        if obj.mode == 'POSE':
            bones_to_check = list(context.selected_pose_bones or [])
            active_bone = context.active_pose_bone
            if active_bone and active_bone not in bones_to_check:
                bones_to_check.append(active_bone)
            
            for bone in bones_to_check:
                if bone.name not in obj_cache:
                    continue
                
                parent_matrix = resolve_parent_transform(obj, bone)
                
                for frame_num, cache_data in obj_cache[bone.name].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        return world_pos, frame_num, bone
            
            return None, None, None
        else:
            for cache_obj_name, cache_obj_data in _session.cached_positions.items():
                draw_obj = bpy.data.objects.get(cache_obj_name)
                if not draw_obj or None not in cache_obj_data:
                    continue
                parent_matrix = resolve_parent_transform(draw_obj)
                for frame_num, cache_data in cache_obj_data[None].items():
                    local_pos = cache_data['position']
                    world_pos = parent_matrix @ local_pos
                    screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, world_pos)
                    if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
                        _session.drag_target_object = draw_obj.name
                        return world_pos, frame_num, None
        
        return None, None, None


def get_handle_at_cursor(context, event, region=None, rv3d=None, local_mouse_pos=None):
    global _session
    
    if not region or not rv3d:
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return None, None
        region = context.region
        rv3d = context.space_data.region_3d

    if local_mouse_pos:
        mouse_pos = mathutils.Vector(local_mouse_pos)
    else:
        mouse_pos = mathutils.Vector((event.mouse_region_x, event.mouse_region_y))
    
    for i, handle_point in enumerate(_session.handle_control_points):
        screen_pos = view3d_utils.location_3d_to_region_2d(region, rv3d, handle_point['position'])
        if screen_pos and (mouse_pos - screen_pos).length < HANDLE_SELECT_RADIUS:
            return i, handle_point
    return None, None


def is_keyframe_selected(action, bone_name, frame):
    for fc in collect_animation_curves(action):
        if is_position_animation(fc, bone_name):
            for kp in fc.keyframe_points:
                if abs(kp.co[0] - frame) < 0.5:
                    return kp.select_control_point
    return False


def apply_handle_mode(context, handle_type):
    targets = []

    if context.mode == 'POSE':
        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            selected_bones = list(context.selected_pose_bones or [])
            if selected_bones:
                for bone in selected_bones:
                    targets.append((obj, bone.name))
            elif context.active_pose_bone:
                targets.append((obj, context.active_pose_bone.name))
    else:
        selected_objects = list(context.selected_objects or [])
        if selected_objects:
            for obj in selected_objects:
                if obj.animation_data and obj.animation_data.action:
                    targets.append((obj, None))
        else:
            obj = context.active_object
            if obj and obj.animation_data and obj.animation_data.action:
                targets.append((obj, None))

    for obj, bone_name in targets:
        action = obj.animation_data.action
        for fcurve in collect_animation_curves(action):
            if not is_position_animation(fcurve, bone_name):
                continue
            for keyframe in fcurve.keyframe_points:
                if keyframe.select_control_point:
                    keyframe.handle_left_type = handle_type
                    keyframe.handle_right_type = handle_type
                    if handle_type == 'ALIGNED' or handle_type in {'AUTO', 'AUTO_CLAMPED'}:
                        vec = mathutils.Vector(keyframe.co) - mathutils.Vector(keyframe.handle_left)
                        len_right = (mathutils.Vector(keyframe.handle_right) - mathutils.Vector(keyframe.co)).length
                        if vec.length > 0.0001:
                            vec.normalize()
                            keyframe.handle_right = mathutils.Vector(keyframe.co) + vec * len_right
                    elif handle_type == 'VECTOR':
                        keyframe.handle_left[1] = keyframe.co[1]
                        keyframe.handle_right[1] = keyframe.co[1]
            fcurve.update()


def ensure_location_keyframes(context, obj):
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    
    targets = []
    if obj.mode == 'POSE':
        if context.selected_pose_bones:
            for bone in context.selected_pose_bones:
                 targets.append((f'pose.bones["{bone.name}"].location', bone.name))
    else:
        targets.append(('location', None))

    fcurves_collection = collect_animation_curves(action)
    if isinstance(fcurves_collection, list) and not fcurves_collection:
        return

    for data_path_base, bone_name in targets:
        all_frames = set()
        frame_indices = {} 
        
        target_fcurves = []
        for fc in fcurves_collection:
            if fc.data_path == data_path_base:
                target_fcurves.append(fc)
                for kp in fc.keyframe_points:
                    frame = int(round(kp.co[0]))
                    all_frames.add(frame)
                    if frame not in frame_indices:
                        frame_indices[frame] = set()
                    frame_indices[frame].add(fc.array_index)
        
        if not target_fcurves:
            continue

        sorted_frames = sorted(list(all_frames))
        
        modified = False
        
        for frame in sorted_frames:
            existing_indices = frame_indices.get(frame, set())
            missing_indices = {0, 1, 2} - existing_indices
            
            if missing_indices:
                for axis_index in missing_indices:
                    fc = next((f for f in target_fcurves if f.array_index == axis_index), None)
                    
                    if fc:
                        val = fc.evaluate(frame)
                        fc.keyframe_points.insert(frame, val)
                    else:
                        try:
                            if hasattr(fcurves_collection, 'new'):
                                fc = fcurves_collection.new(data_path=data_path_base, index=axis_index)
                                target_fcurves.append(fc)
                                
                                if bone_name:
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
    if wm.rtmp_path_display_enabled:
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


def _find_and_start_motion_path_operators(context):
    wm = context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    with context.temp_override(window=window, area=area, region=region):
                        if not wm.rtmp_edit_mode_active:
                            wm.rtmp_edit_mode_active = True
                            bpy.ops.rtmp.path_point_drag('INVOKE_DEFAULT')
                        if not wm.rtmp_auto_refresh_active:
                            wm.rtmp_auto_refresh_active = True
                            bpy.ops.rtmp.path_refresh_daemon('INVOKE_DEFAULT')
                    return True
    return False


def _stop_motion_path_operators(context):
    wm = context.window_manager
    wm.rtmp_edit_mode_active = False
    wm.rtmp_auto_refresh_active = False
