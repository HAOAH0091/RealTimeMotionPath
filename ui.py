import bpy
from bpy.app.translations import pgettext_iface as iface_
from .state import get_addon_prefs
from . import interaction


class RTMP_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    path_width: bpy.props.FloatProperty(name="Path Width", default=2.0, min=1.0, max=10.0)
    path_color: bpy.props.FloatVectorProperty(name="Path Color", subtype='COLOR', size=4, default=(0.8, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    
    show_frame_points: bpy.props.BoolProperty(name="Show Frame Points", default=True)
    frame_point_size: bpy.props.FloatProperty(name="Frame Point Size", default=4.0, min=1.0, max=20.0)
    frame_point_color: bpy.props.FloatVectorProperty(name="Frame Point Color", subtype='COLOR', size=4, default=(1.0, 1.0, 1.0, 1.0), min=0.0, max=1.0)
    
    keyframe_point_size: bpy.props.FloatProperty(name="Keyframe Size", default=10.0, min=1.0, max=30.0)
    keyframe_point_color: bpy.props.FloatVectorProperty(name="Keyframe Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_keyframe_point_color: bpy.props.FloatVectorProperty(name="Selected Keyframe Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)
    
    handle_line_width: bpy.props.FloatProperty(name="Handle Line Width", default=2.0, min=1.0, max=10.0)
    handle_line_color: bpy.props.FloatVectorProperty(name="Handle Line Color", subtype='COLOR', size=4, default=(0.0, 0.0, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_line_color: bpy.props.FloatVectorProperty(name="Selected Handle Line Color", subtype='COLOR', size=4, default=(1.0, 0.776, 0.561, 1.0), min=0.0, max=1.0)
    
    handle_endpoint_size: bpy.props.FloatProperty(name="Handle Endpoint Size", default=7.0, min=1.0, max=20.0)
    handle_endpoint_color: bpy.props.FloatVectorProperty(name="Handle Endpoint Color", subtype='COLOR', size=4, default=(0.953, 0.78, 0.0, 1.0), min=0.0, max=1.0)
    selected_handle_endpoint_color: bpy.props.FloatVectorProperty(name="Selected Handle Endpoint Color", subtype='COLOR', size=4, default=(1.0, 0.102, 0.0, 1.0), min=0.0, max=1.0)

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
        
        row = layout.row()
        row.alignment = 'RIGHT'
        row.operator("rtmp.reset_preferences", text=iface_("Restore Defaults"), icon='LOOP_BACK')

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


class RTMP_PT_header_settings(bpy.types.Panel):
    bl_label = "Motion Path Settings"
    bl_idname = "RTMP_PT_header_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager
        
        layout.label(text=iface_("Performance"))
        
        layout.label(text=iface_("Update Mode"))
        row = layout.row()
        row.prop(wm, "rtmp_refresh_strategy", expand=True)
        
        layout.prop(wm, "rtmp_max_interaction_fps", text=iface_("Interaction FPS"))
        if wm.rtmp_refresh_strategy == 'TIMER':
            layout.prop(wm, "rtmp_poll_frequency", text=iface_("Auto Update FPS"))


class RTMP_MT_context_menu(bpy.types.Menu):
    bl_label = "Motion Path Context Menu"
    bl_idname = "RTMP_MT_context_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("rtmp.change_handle_mode", text=iface_("Free")).handle_type = 'FREE'
        layout.operator("rtmp.change_handle_mode", text=iface_("Aligned")).handle_type = 'ALIGNED'
        layout.operator("rtmp.change_handle_mode", text=iface_("Vector")).handle_type = 'VECTOR'
        layout.operator("rtmp.change_handle_mode", text=iface_("Auto")).handle_type = 'AUTO'
        layout.operator("rtmp.change_handle_mode", text=iface_("Auto Clamped")).handle_type = 'AUTO_CLAMPED'


class RTMP_OT_ResetPreferences(bpy.types.Operator):
    bl_idname = "rtmp.reset_preferences"
    bl_label = "Reset to Default"
    bl_description = "Reset all motion path settings to default values"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        prefs = get_addon_prefs(context)
        prefs.property_unset("path_width")
        prefs.property_unset("path_color")
        prefs.property_unset("show_frame_points")
        prefs.property_unset("frame_point_size")
        prefs.property_unset("frame_point_color")
        prefs.property_unset("keyframe_point_size")
        prefs.property_unset("keyframe_point_color")
        prefs.property_unset("selected_keyframe_point_color")
        prefs.property_unset("handle_line_width")
        prefs.property_unset("handle_line_color")
        prefs.property_unset("selected_handle_line_color")
        prefs.property_unset("handle_endpoint_size")
        prefs.property_unset("handle_endpoint_color")
        prefs.property_unset("selected_handle_endpoint_color")
        prefs.property_unset("show_origin_indicator")
        prefs.property_unset("origin_indicator_style")
        prefs.property_unset("origin_indicator_size")
        prefs.property_unset("origin_indicator_color")
        prefs.property_unset("origin_indicator_inner_color")
        
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
        return {'FINISHED'}


class RTMP_OT_ToggleCustomDraw(bpy.types.Operator):
    bl_idname = "rtmp.toggle_custom_draw"
    bl_label = "Toggle Custom Path"
    bl_description = "Enable/Disable Custom Motion Path Drawing"

    def execute(self, context):
        wm = context.window_manager
        new_state = not wm.rtmp_path_display_enabled
        wm.rtmp_path_display_enabled = new_state

        if new_state:
            if not interaction._find_and_start_motion_path_operators(context):
                self.report({'WARNING'}, iface_("Enabled Motion Path, but no 3D View found for interaction."))
        else:
            interaction._stop_motion_path_operators(context)

        if context.area:
            context.area.tag_redraw()
        return {'FINISHED'}


def draw_header_button(self, context):
    layout = self.layout
    wm = context.window_manager
    row = layout.row(align=True)
    row.prop(wm, "rtmp_path_display_enabled", text="", icon='IPO_BEZIER', toggle=True)
    row.popover(panel="RTMP_PT_header_settings", text="")
