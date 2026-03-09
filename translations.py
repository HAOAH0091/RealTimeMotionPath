import bpy

translations_dict = {
    "zh_HANS": {
        # --- Add-on Info ---
        ("*", "Real Time Motion Path"): "实时运动路径",
        ("*", "Update motion path in real time from graph editor and viewport"): "从图形编辑器和视口实时更新运动路径",
        ("*", "Graph Editor"): "图形编辑器",
        ("*", "Graph"): "图形",

        # --- Operators ---
        ("*", "Auto Update Motion Paths"): "自动更新运动路径",
        ("*", "Real time update motion paths"): "实时更新运动路径",
        ("*", "Set Handle Type"): "设置手柄类型",
        ("*", "Toggle Direct Manipulation"): "开关直接操控模式",
        ("*", "Enable/Disable Motion Path Editing"): "启用/禁用运动路径编辑",
        ("*", "Enable Direct Path Editing"): "已启用直接路径编辑",
        ("*", "Disable Direct Path Editing"): "已禁用直接路径编辑",
        ("*", "Direct Motion Path Manipulation"): "直接操控运动路径",
        ("*", "Move Motion Path Points"): "移动运动路径点",
        ("*", "Move Motion Path Handle"): "移动运动路径手柄",
        ("*", "Move Handle Point"): "移动手柄点",
        ("*", "View3D not found, cannot run operator"): "未找到3D视图，无法运行操作",
        ("*", "Toggle Custom Path"): "开关自定义路径显示",
        ("*", "Enable/Disable Custom Motion Path Drawing"): "启用/禁用自定义运动路径绘制",
        ("*", "Enabled Motion Path, but no 3D View found for interaction."): "已启用运动路径，但未找到可交互的3D视图。",
        ("*", "Motion Path Context Menu"): "运动路径上下文菜单",

        # --- Properties & Settings ---
        ("*", "Motion Path Settings"): "运动路径设置",
        ("*", "Performance"): "性能",
        ("*", "Update Mode"): "更新模式",
        ("*", "Interaction FPS"): "交互帧率限制",
        ("*", "Auto Update FPS"): "自动更新频率",
        
        # Style Settings
        ("*", "Style Settings"): "样式设置",
        ("*", "Path Width"): "路径宽度",
        ("*", "Path Color"): "路径颜色",
        ("*", "Show Frame Points"): "显示帧点",
        ("*", "Frame Point Size"): "帧点大小",
        ("*", "Frame Point Color"): "帧点颜色",
        
        # Keyframes
        ("*", "Keyframes"): "关键帧",
        ("*", "Keyframe Size"): "关键帧大小",
        ("*", "Keyframe Color"): "关键帧颜色",
        ("*", "Selected Keyframe Color"): "选中关键帧颜色",
        
        # Handles
        ("*", "Handles"): "手柄",
        ("*", "Handle Line Width"): "手柄线宽",
        ("*", "Handle Line Color"): "手柄线颜色",
        ("*", "Selected Handle Line Color"): "选中手柄线颜色",
        ("*", "Handle Endpoint Size"): "手柄端点大小",
        ("*", "Handle Endpoint Color"): "手柄端点颜色",
        ("*", "Selected Handle Endpoint Color"): "选中手柄端点颜色",

        # Origin Indicator
        ("*", "Origin Indicator"): "原点指示器",

        # --- WindowManager Properties ---
        ("*", "Enable Motion Path"): "启用运动路径",
        ("*", "Enable custom motion path drawing"): "启用自定义运动路径绘制",
        ("*", "Direct Manipulation Active"): "启用直接操控",
        ("*", "Enable direct manipulation of points on motion paths"): "启用在运动路径上直接操控点",
        ("*", "Auto Update Active"): "启用自动更新",
        ("*", "Max FPS Limit"): "最大帧率限制",
        ("*", "Limit the frame rate of interaction and redrawing to save power"): "限制交互和重绘帧率以节省电量",
        ("*", "Choose how the motion path updates"): "选择运动路径更新方式",
        ("*", "Smart (Event)"): "智能 (事件驱动)",
        ("*", "Update only when relevant data changes (Zero idle power)"): "仅在相关数据变化时更新 (零待机功耗)",
        ("*", "Timer (Polling)"): "定时器 (轮询)",
        ("*", "Update periodically (Stable but higher power)"): "周期性更新 (稳定但耗能)",
        ("*", "Frequency of checks in Timer mode (Hz)"): "定时器模式下的检查频率 (Hz)",
        
        ("*", "Handle Type"): "手柄类型",
        ("*", "Default handle type for new keyframes"): "新关键帧的默认手柄类型",
        ("*", "Free"): "自由 (Free)",
        ("*", "Handles can be adjusted independently"): "手柄可以独立调整",
        ("*", "Aligned"): "对齐 (Aligned)",
        ("*", "Handles are aligned to maintain smoothness"): "手柄保持对齐以维持平滑",
        ("*", "Vector"): "矢量 (Vector)",
        ("*", "Creates linear interpolation"): "创建线性插值",
        ("*", "Auto"): "自动 (Auto)",
        ("*", "Automatic smooth handles"): "自动平滑手柄",
        ("*", "Auto Clamped"): "自动钳制 (Auto Clamped)",
        ("*", "Automatic handles with clamped values"): "带钳制值的自动手柄",
        
        ("*", "Snap Handles"): "吸附手柄",
        ("*", "Snap handles to grid or other elements"): "吸附手柄到网格或其他元素",
        ("*", "Snap Increment"): "吸附增量",
        ("*", "Distance to snap handles"): "手柄吸附距离",
        ("*", "Global Handle Visual Scale"): "全局手柄视觉缩放",
        ("*", "Scale factor for handle visualization"): "手柄可视化的缩放因子",
    }
}

def register(module_name):
    # Try to unregister first to avoid "cache already contains some data" warning on reload
    try:
        bpy.app.translations.unregister(module_name)
    except Exception:
        pass
    
    try:
        bpy.app.translations.register(module_name, translations_dict)
    except Exception as e:
        print(f"Warning: Could not register translations for {module_name}: {e}")

def unregister(module_name):
    try:
        bpy.app.translations.unregister(module_name)
    except Exception:
        pass
