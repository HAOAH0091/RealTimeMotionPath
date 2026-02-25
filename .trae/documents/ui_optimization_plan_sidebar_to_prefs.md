# UI 优化计划：侧边栏设置迁移至插件首选项

根据您的需求，我们将把侧边栏（N 面板）中的所有样式设置迁移到 Blender 的插件首选项面板中，并移除侧边栏面板。

## 1. 创建插件首选项类
我们需要创建一个新的 `MOTIONPATH_AddonPreferences` 类，用于在插件设置页面显示样式选项。

- **类名**: `MOTIONPATH_AddonPreferences`
- **继承**: `bpy.types.AddonPreferences`
- **ID**: `bl_idname = __name__`
- **绘制内容**: 将原 `MOTIONPATH_CustomDrawPanel` 中的绘制代码（Style Settings, Keyframes, Handles）完整复制过来。

## 2. 移除侧边栏面板
删除 `MOTIONPATH_CustomDrawPanel` 类。

- **操作**: 删除类定义。
- **注册**: 从 `classes` 列表中移除该类。

## 3. 注册新组件
将 `MOTIONPATH_AddonPreferences` 添加到 `classes` 列表中进行注册。

## 预期效果
- **侧边栏 (N 面板)**: "Motion Path Pro" 面板将完全消失。
- **插件首选项**: 在 Edit -> Preferences -> Add-ons -> Motion Path Pro 中，将显示所有的样式设置（路径颜色、关键帧大小、手柄颜色等）。
