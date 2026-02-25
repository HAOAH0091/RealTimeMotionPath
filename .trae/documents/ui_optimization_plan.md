# 界面优化计划：头部下拉菜单与性能设置迁移

根据您的需求，我们将对插件的 UI 进行改进，在 3D 视图头部添加带下拉菜单的按钮，并将性能设置移动到该菜单中。

## 1. 定义下拉菜单面板
我们需要创建一个新的面板类，它将作为下拉菜单（Popover）的内容显示。

- **类名**: `MOTIONPATH_PT_header_settings`
- **功能**: 承载原本位于侧边栏的 "Performance" 设置项。
- **包含内容**:
  - Update Mode (更新模式)
  - Interaction FPS (交互帧率)
  - Auto Update FPS (自动更新帧率 - 仅在 Timer 模式下显示)

## 2. 修改头部按钮绘制
修改 `draw_header_button` 函数，将其改为组合按钮样式。

- **布局**: 使用 `layout.row(align=True)` 让按钮紧密排列。
- **左侧**: 原有的插件开关按钮 (`custom_path_draw_active`)。
- **右侧**: 新增的下拉菜单按钮 (`popover`)，指向 `MOTIONPATH_PT_header_settings`。

## 3. 清理原有侧边栏面板
修改 `MOTIONPATH_CustomDrawPanel` 类。

- **操作**: 删除其中的 "Performance" 设置部分，因为这些功能已经移动到了头部下拉菜单中。

## 4. 注册新组件
确保新创建的 `MOTIONPATH_PT_header_settings` 类被添加到注册列表中。

---

## 预期效果
- **3D 视图头部**: 插件图标旁会出现一个小箭头或设置图标，点击可展开性能设置菜单。
- **侧边栏 (N 面板)**: "Motion Path Pro" 面板将不再显示 Performance 区域，变得更加简洁。
