# 修复手柄类型应用报错及默认值修改计划

## 问题分析
用户在使用 "Apply Type" 按钮修改手柄类型时遇到 `TypeError`，原因是传递给操作符的 `handle_type` 参数为空字符串。此外，用户希望了解修改范围并将默认类型设为 `ALIGNED`。

### 1. 报错原因
*   **现象**: `TypeError: ... enum "" not found ...`
*   **根源**: 在 UI 面板中调用 `motion_path.set_handle_type` 操作符时，没有将下拉菜单中选择的值（存储在 `context.window_manager.handle_type`）传递给操作符。操作符使用了其自身的 `handle_type` 属性，该属性默认为空字符串。
*   **影响**: `set_handle_type` 函数接收到空字符串，尝试将其赋值给 `keyframe.handle_left_type`（枚举类型），导致类型错误。

### 2. 功能澄清
*   **修改范围**: 代码逻辑显示 `set_handle_type` 函数中包含 `if keyframe.select_control_point:` 判断。
*   **结论**: "Apply Type" 按钮**只对当前选中的关键帧**生效，而非所有关键帧。

### 3. 默认值修改
*   当前默认值为 `'AUTO'`，需修改为 `'ALIGNED'`。

## 实施计划

### 步骤 1: 修复 `MOTIONPATH_SetHandleType` 操作符
修改 `__init__.py` 中的 `MOTIONPATH_SetHandleType` 类。
*   **目标**: 使其能够智能获取句柄类型。如果调用时未指定 `handle_type`（即为空），则自动从 `context.window_manager.handle_type` 获取当前 UI 上选择的值。
*   **代码位置**: `class MOTIONPATH_SetHandleType` -> `execute` 方法 (约 731 行)。

### 步骤 2: 修改默认句柄类型
修改 `__init__.py` 中的注册代码。
*   **目标**: 将 `bpy.types.WindowManager.handle_type` 的默认值改为 `'ALIGNED'`。
*   **代码位置**: `register` 函数中 (约 1754 行)。

### 步骤 3: 验证
*   在 UI 中选择不同的 Handle Type 并点击 Apply，确认不再报错。
*   重启插件或重载脚本，确认默认选项显示为 "Aligned"。
*   选中部分关键帧进行测试，确认只有选中的关键帧被修改。

## 待办事项
- [ ] 修改 `MOTIONPATH_SetHandleType.execute` 方法以处理空参数情况
- [ ] 修改 `register` 函数中的默认值为 `'ALIGNED'`
- [ ] (可选) 验证修改是否生效
