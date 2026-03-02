import bpy
import mathutils


def get_addon_prefs(context):
    return context.preferences.addons[__package__].preferences


class MotionPathState:
    def __init__(self):
        self.is_dragging = False
        self.drag_start_mouse = None
        self.drag_start_3d = None
        self.drag_start_item_pos = None
        self.selected_path_point = None
        self.selected_frame = None
        self.selected_handle_side = None
        self.selected_bone_name = None
        self.handle_points = []
        self.selected_handle_point = None
        self.selected_handle_data = None
        self.handle_dragging = False
        self.selected_drag_object_name = None
        self.position_cache = {}
        self.initial_handle_values = {}
        self.draw_handler = None
        self.path_vertices = {}
        
    def reset(self):
        self.__init__()


_state = MotionPathState()

_is_updating_cache = False

HANDLE_SELECT_RADIUS = 20
SAFE_LIMIT = 1000000.0
MIN_HANDLE_SCALE = 0.1
MAX_HANDLE_SCALE = 100.0

