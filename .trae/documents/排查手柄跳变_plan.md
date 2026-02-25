# 手柄跳变问题排查与修复方案

## 🐛 问题分析

**现象**：
在拖动手柄时，手柄会瞬间跳回起始位置附近，导致“拖不动”或“来回跳动”。

**根本原因**：
代码逻辑中犯了一个“刻舟求剑”的错误。
1.  **记录起点**：在鼠标按下时，记录了 `start_pos`（起跑线）。
2.  **计算移动**：在鼠标移动时，计算了 `offset`（这一帧比上一帧走了多远）。
3.  **错误计算**：`new_pos = start_pos + offset`。
    -   这意味着每次都只在起跑线上加了一点点距离。
    -   正确应该是：`new_pos = current_pos + offset`（在当前位置继续往前走）。
    -   或者：`new_pos = start_pos + total_offset`（起跑线 + 总路程）。

由于代码中 `_state.drag_start_3d`（参考点）在每次移动后都更新了，所以 `offset` 变成了**增量**。但 `_state.drag_start_item_pos`（起跑线）却没有更新。于是就出现了“每次都从起跑线重新出发”的 Bug。

---

## 🛠️ 修复计划

### 1. 核心修复逻辑
在 `MOTIONPATH_DirectManipulation` 类的 `modal` 方法中，修复坐标更新逻辑。

**方案**：采用**增量累加法**。
-   每次计算出微小的移动量 `offset` 后。
-   计算新位置：`new_handle_pos = _state.drag_start_item_pos + offset`。
-   **关键一步**：立即更新起点！`_state.drag_start_item_pos = new_handle_pos`。
-   这样，下一次移动就会基于这个新位置继续计算。

### 2. 具体代码修改
文件：`__init__.py`

在 `modal` 方法的 `MOUSEMOVE` 处理块中：

```python
# 旧代码
new_handle_pos = _state.drag_start_item_pos + offset
self.move_selected_handles(context, new_handle_pos, _state.selected_handle_side)
# (缺少更新 _state.drag_start_item_pos)

# 新代码
new_handle_pos = _state.drag_start_item_pos + offset
self.move_selected_handles(context, new_handle_pos, _state.selected_handle_side)
_state.drag_start_item_pos = new_handle_pos  # <--- 加上这一行
```

### 3. 验证目标
-   拖动手柄时，手柄应该平滑跟随鼠标。
-   不会出现跳回原点或卡顿的现象。
