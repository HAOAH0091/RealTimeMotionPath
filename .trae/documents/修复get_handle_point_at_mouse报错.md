# 计划：修复 `get_handle_point_at_mouse` 中的 `AttributeError`

## 问题分析
用户在 Blender 5.0 中遇到报错：`AttributeError: 'NoneType' object has no attribute 'region_3d'`。
错误发生在 `get_handle_point_at_mouse` 函数中，试图访问 `context.space_data.region_3d` 时。
原因是在某些情况下（例如鼠标不在 3D 视图区域内时），`context.space_data` 可能为 `None` 或者不是 `VIEW_3D` 类型，导致无法获取 `region_3d` 属性。

## 解决方案
在 `get_handle_point_at_mouse` 函数开头添加安全检查，确保 `context.space_data` 存在且类型为 `VIEW_3D`。如果条件不满足，直接返回 `None, None`。

## 实施步骤
1.  **编辑 `__init__.py` 文件**
    -   定位到 `get_handle_point_at_mouse` 函数（约第 1622 行）。
    -   在函数开头添加检查逻辑：
        ```python
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return None, None
        ```

## 验证
-   修复后，即使用户在非 3D 视图区域点击，插件也应正常运行而不会报错。
