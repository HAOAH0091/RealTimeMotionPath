bl_info = {
    "name" : "RealTimeMotionPath",
    "author" : "HAOAH",
    "description" : "在 3D 视口中显示和操作实时运动路径，支持直接手柄编辑和图形编辑器同步",
    "blender" : (5, 0, 0),
    "version" : (1, 1, 0),
    "location" : "3D Viewport › Header",
    "warning" : "",
    "doc_url" : "",
    "tracker_url" : "",
    "category" : "Animation"
}


import bpy
from . import translations
from .ui import (
    RTMP_OT_ToggleCustomDraw,
    RTMP_OT_ResetPreferences,
    RTMP_PT_header_settings,
    RTMP_AddonPreferences,
    RTMP_MT_context_menu,
    draw_header_button
)
from .interaction import (
    RTMP_OT_PathPointDrag,
    RTMP_OT_ToggleEditMode,
    RTMP_OT_PathRefreshDaemon,
    RTMP_OT_ChangeHandleMode,
    update_custom_path_active
)


classes = (
    RTMP_OT_ToggleCustomDraw,
    RTMP_OT_ResetPreferences,
    RTMP_PT_header_settings,
    RTMP_AddonPreferences,
    RTMP_MT_context_menu,
    
    RTMP_OT_PathPointDrag,
    RTMP_OT_ToggleEditMode,
    RTMP_OT_PathRefreshDaemon,
    RTMP_OT_ChangeHandleMode,
)


refresh_strategy_items = [
    ('SMART', "智能 (事件)", "仅在相关数据更改时更新（零空闲功耗）"),
    ('TIMER', "计时器 (轮询)", "定期更新（稳定但功耗较高）")
]


handle_mode_items = [
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
    

    bpy.types.WindowManager.rtmp_path_display_enabled = bpy.props.BoolProperty(
        name="Enable Motion Path",
        description="Enable custom motion path drawing",
        default=False,
        update=update_custom_path_active
    )
    
    bpy.types.WindowManager.rtmp_edit_mode_active = bpy.props.BoolProperty(
        name="Direct Edit Active",
        description="Enable real-time direct editing of motion path control points",
        default=False
    )
    bpy.types.WindowManager.rtmp_auto_refresh_active = bpy.props.BoolProperty(
        name="Auto Update Active",
        default=False
    )
    
    bpy.types.WindowManager.rtmp_max_interaction_fps = bpy.props.IntProperty(
        name="Max FPS Limit",
        description="Limit the frame rate of interaction and redrawing to save power",
        default=60,
        min=1,
        max=144
    )
    
    bpy.types.WindowManager.rtmp_refresh_strategy = bpy.props.EnumProperty(
        name="Update Mode",
        description="Choose how the motion path updates",
        items=refresh_strategy_items,
        default='SMART'
    )
    
    bpy.types.WindowManager.rtmp_poll_frequency = bpy.props.IntProperty(
        name="Auto Update FPS",
        description="Frequency of checks in Timer mode (Hz)",
        default=10,
        min=1,
        max=60
    )
    
    bpy.types.WindowManager.rtmp_handle_type = bpy.props.EnumProperty(
        name="Keyframe Handle Type",
        description="Handle type used when editing keyframes on the motion path",
        items=handle_mode_items,
        default='ALIGNED'
    )
    bpy.types.WindowManager.rtmp_snap = bpy.props.BoolProperty(
        name="Snap to Grid",
        description="Snap handles to grid while dragging",
        default=False
    )
    bpy.types.WindowManager.rtmp_snap_step = bpy.props.FloatProperty(
        name="Snap Step",
        description="Grid step size for handle snapping",
        default=0.1,
        min=0.01,
        max=10.0
    )
    bpy.types.WindowManager.rtmp_handle_scale = bpy.props.FloatProperty(
        name="Handle Scale",
        description="Visual scale multiplier for handle display in viewport",
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
        

    del bpy.types.WindowManager.rtmp_path_display_enabled
    del bpy.types.WindowManager.rtmp_edit_mode_active
    del bpy.types.WindowManager.rtmp_auto_refresh_active
    del bpy.types.WindowManager.rtmp_max_interaction_fps
    del bpy.types.WindowManager.rtmp_refresh_strategy
    del bpy.types.WindowManager.rtmp_poll_frequency
    del bpy.types.WindowManager.rtmp_handle_type
    del bpy.types.WindowManager.rtmp_snap
    del bpy.types.WindowManager.rtmp_snap_step
    del bpy.types.WindowManager.rtmp_handle_scale
    
    translations.unregister(__package__)
