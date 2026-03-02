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
from . import translations
from .ui import (
    MOTIONPATH_ToggleCustomDraw,
    MOTIONPATH_ResetPreferences,
    MOTIONPATH_PT_header_settings,
    MOTIONPATH_AddonPreferences,
    MOTIONPATH_MT_context_menu,
    draw_header_button
)
from .interaction import (
    MOTIONPATH_DirectManipulation,
    MOTIONPATH_DirectManipulationToggle,
    MOTIONPATH_AutoUpdateMotionPaths,
    MOTIONPATH_SetHandleType,
    update_custom_path_active
)


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
    
    if hasattr(bpy.types, "VIEW3D_HT_header"):
        bpy.types.VIEW3D_HT_header.append(draw_header_button)


def unregister():
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
