import bpy
import mathutils


def get_addon_prefs(context):
    return context.preferences.addons[__package__].preferences


class MotionPathSession:
    """管理运动路径编辑会话的状态"""
    
    def __init__(self):
        self._initialize_defaults()
    
    def _initialize_defaults(self):
        """初始化所有状态变量"""
        self.drag_in_progress = False
        self.mouse_origin = None
        self.world_origin = None
        self.item_initial_pos = None
        self.active_path_point = None
        self.active_frame_number = None
        self.active_handle_direction = None
        self.active_bone_identifier = None
        self.handle_control_points = []
        self.active_handle_index = None
        self.active_handle_info = None
        self.handle_edit_in_progress = False
        self.drag_target_object = None
        self.cached_positions = {}
        self.handle_start_values = {}
        self.render_callback_id = None
        self.path_point_sequence = {}
    
    def reset(self):
        """重置会话状态"""
        self._initialize_defaults()
    
    def clear_handles(self):
        """清除手柄控制点"""
        self.handle_control_points = []


_session = MotionPathSession()

_cache_update_lock = False

HANDLE_SELECT_RADIUS = 20
SAFE_LIMIT = 1000000.0
MIN_HANDLE_SCALE = 0.1
MAX_HANDLE_SCALE = 100.0
