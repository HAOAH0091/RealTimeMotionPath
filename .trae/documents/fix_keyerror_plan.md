# Motion Path Pro 修复计划：解决 KeyError: 0

## 问题分析
用户在 3D 视图中点击任意位置时，插件会报错 `KeyError: 0`。
这是因为 `get_motion_path_point_at_mouse` 函数在遍历 `_state.position_cache` 时，错误地将缓存字典（包含 `position`, `velocity`, `matrix` 等）直接赋值给了 `world_pos` 变量。
当后续代码尝试访问 `world_pos`（预期为 Vector）时，实际上是在访问字典，导致无法通过索引访问坐标分量。

## 受影响的代码
文件：`__init__.py`
函数：`get_motion_path_point_at_mouse`
行号：约 1576 行

## 修改计划

1.  **修正遍历逻辑**：
    将错误的遍历方式：
    ```python
    for frame_num, world_pos in _state.position_cache[active_bone.name].items():
    ```
    修改为正确的字典解包方式：
    ```python
    for frame_num, cache_data in _state.position_cache[active_bone.name].items():
        world_pos = cache_data['position']
    ```

2.  **验证其他位置**：
    已通过 grep 检查，确认 `__init__.py` 中其他遍历 `_state.position_cache` 的地方均已正确使用 `cache_data`，仅此一处遗漏。

## 验证步骤
1.  应用代码修改。
2.  重启 Blender 或重载脚本（模拟）。
3.  在 3D 视图中点击空白处，确认不再报错。
4.  点击关键帧点，确认仍能正常选中。
