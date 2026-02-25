# Motion Path Pro UI 优化计划

根据您的需求，我们将对插件的 UI 进行以下优化：

## 1. 移动插件开关至播放控制台
将插件的"开启/关闭"按钮从侧边栏移动到时间线（Dope Sheet）和曲线编辑器（Graph Editor）的头部播放控制台区域。

## 2. 优化手柄显示逻辑
- 移除 "Show All Handles" 和 "Show Selected Only" 选项。
- 强制默认为：**仅显示选中关键帧的手柄**。

## 3. 右键菜单更改手柄类型
- 在 3D 视图中，当用户右键点击关键帧点时，弹出上下文菜单。
- 菜单中包含更改手柄类型（Free, Aligned, Vector, Auto 等）的选项。
- 移除原面板中的下拉菜单。

## 4. 简化侧边栏面板
- **3D 视图侧边栏**：移除除 "Style Settings" 以外的所有内容。
- **曲线编辑器侧边栏**：完全移除插件面板。

## 执行步骤

1.  **修改手柄绘制逻辑**：
    - 在 `draw_motion_path_point` 函数中，修改判断条件，仅当 `is_selected_keyframe` 为真时绘制手柄。

2.  **创建右键菜单类**：
    - 定义 `MOTIONPATH_MT_context_menu` 类，包含各类手柄类型的设置按钮。

3.  **更新交互逻辑 (Modal Operator)**：
    - 在 `MOTIONPATH_DirectManipulation` 的 `modal` 方法中添加对 `RIGHTMOUSE` 事件的处理。
    - 当右键点击路径点时，选中该点并调用 `wm.call_menu` 弹出右键菜单。

4.  **调整 UI 面板注册**：
    - 定义 `draw_header` 函数，将开关按钮绘制到 `DOPESHEET_HT_header` 和 `GRAPH_HT_header`。
    - 修改 `MOTIONPATH_CustomDrawPanel`，仅保留样式设置内容。
    - 删除 `MOTIONPATH_CustomDrawGraphPanel` 类及其注册代码。
    - 清理不再需要的 `WindowManager` 属性（如 `show_all_handles` 等）。

5.  **验证与测试**：
    - 验证按钮是否出现在播放控制台。
    - 验证右键菜单是否正常弹出并生效。
    - 验证手柄是否仅在选中时显示。
