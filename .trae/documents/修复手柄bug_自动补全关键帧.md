# 计划：自动补全缺失的关键帧

用户遇到的问题是：当XYZ三个通道的关键帧没有对齐（即某个时间点只有部分通道有关键帧）时，运动路径插件的手柄功能会出现异常。
用户希望：在开启运动路径插件时，自动检测并补全缺失的关键帧，使得所有Location通道在同一时间点都有关键帧。

## 任务分解

1.  **分析现有的开启逻辑**
    - 确认插件开启的入口是 `update_custom_path_active` 函数（响应 `wm.custom_path_draw_active` 属性的变化）。
    - 确认需要处理的对象类型：物体模式下的物体（Object）和姿态模式下的骨骼（Pose Bone）。

2.  **实现关键帧补全逻辑 (`ensure_location_keyframes`)**
    - 创建一个新的工具函数 `ensure_location_keyframes(obj, bone_name=None)`。
    - **逻辑步骤**：
        1. 获取目标（物体或骨骼）的所有Location F-Curves。
        2. 收集所有Location通道上出现过的关键帧时间点（去重并排序）。
        3. 遍历每个时间点：
            - 检查 X, Y, Z 三个通道是否在该时间点都存在关键帧。
            - 如果某个通道缺失关键帧：
                - 计算该通道在该时间点的当前值（使用 `fcurve.evaluate(frame)` 或 `obj.matrix_local` 等方式）。
                - 在该通道的对应时间点插入一个新的关键帧。
                - 确保新插入的关键帧不会破坏原有的曲线形状（通常插入当前值即可）。

3.  **集成到开启流程**
    - 在 `update_custom_path_active` 函数中，当检测到插件被开启（`wm.custom_path_draw_active` 变为 `True`）时，调用上述补全逻辑。
    - 针对当前选中的物体或骨骼进行处理。

4.  **验证与测试**
    - 创建测试脚本，模拟XYZ通道关键帧不对齐的情况。
    - 运行插件开启功能，验证是否自动补全了缺失的关键帧。
    - 验证补全后的手柄交互是否正常。

## 文件修改计划

- 编辑 `__init__.py`：
    - 添加 `ensure_location_keyframes` 函数。
    - 修改 `update_custom_path_active` 函数以调用新逻辑。

## 详细逻辑设计 (ensure_location_keyframes)

```python
def ensure_location_keyframes(context, obj):
    """
    Ensure that for every frame where a location keyframe exists on any axis,
    keyframes exist on all 3 axes (X, Y, Z).
    """
    if not obj or not obj.animation_data or not obj.animation_data.action:
        return

    action = obj.animation_data.action
    
    # Determine targets: (data_path_prefix, bone_name_for_check)
    targets = []
    if obj.mode == 'POSE':
        # In Pose mode, only process selected bones
        for bone in context.selected_pose_bones:
             targets.append((f'pose.bones["{bone.name}"].location', bone.name))
    else:
        # In Object mode, process object location
        targets.append(('location', None))

    for data_path_base, bone_name in targets:
        # 1. Collect all existing frames for this target's location
        all_frames = set()
        # Also keep track of which indices exist at which frame
        # frame -> set of existing indices (0, 1, 2)
        frame_indices = {} 
        
        # Helper to find fcurves
        # We need to look for data_path that *matches* our target
        # e.g. "location" or 'pose.bones["Bone"].location'
        
        target_fcurves = []
        for fc in action.fcurves:
            if fc.data_path == data_path_base:
                target_fcurves.append(fc)
                for kp in fc.keyframe_points:
                    frame = int(round(kp.co[0])) # Use integer frames for alignment
                    all_frames.add(frame)
                    if frame not in frame_indices:
                        frame_indices[frame] = set()
                    frame_indices[frame].add(fc.array_index)
        
        if not target_fcurves:
            continue

        # 2. Fill missing frames
        sorted_frames = sorted(list(all_frames))
        
        # We need to know if we modified anything to update
        modified = False
        
        for frame in sorted_frames:
            existing_indices = frame_indices.get(frame, set())
            missing_indices = {0, 1, 2} - existing_indices
            
            if missing_indices:
                # We need to insert keyframes for these indices
                for axis_index in missing_indices:
                    # Insert keyframe using high-level API or low-level
                    # Low-level is faster if we have the fcurve, but if fcurve doesn't exist we need high-level or create it.
                    
                    # Check if fcurve exists for this axis
                    fc = next((f for f in target_fcurves if f.array_index == axis_index), None)
                    
                    if fc:
                        # Evaluate value at that frame
                        val = fc.evaluate(frame)
                        fc.keyframe_points.insert(frame, val)
                        # Set handle type to match neighbors or Auto?
                        # insert() usually handles this reasonably well
                    else:
                        # FCurve doesn't exist, use obj.keyframe_insert
                        # Need to set the value first? No, keyframe_insert reads the value.
                        # BUT, keyframe_insert reads the CURRENT property value (at current frame).
                        # We want to insert at a specific 'frame' with the EVALUATED value.
                        
                        # So we must change the scene frame, OR manually create fcurve.
                        # Changing scene frame is slow.
                        # Better: Create FCurve if missing.
                        fc = action.fcurves.new(data_path=data_path_base, index=axis_index)
                        target_fcurves.append(fc)
                        # Now evaluate? But we have no curve to evaluate!
                        # If the curve didn't exist, the value is constant (the current property value).
                        
                        # Get current static value
                        if bone_name:
                            # Pose bone location
                            # We need to access the property directly.
                            # obj.pose.bones[bone_name].location[axis_index]
                            # This is the current value.
                            # Since there was no animation, it's constant across all time.
                            val = obj.pose.bones[bone_name].location[axis_index]
                        else:
                            val = obj.location[axis_index]
                            
                        fc.keyframe_points.insert(frame, val)
                    
                    modified = True
        
        if modified:
             for fc in target_fcurves:
                 fc.update()
```

此逻辑看起来可行。我将将其写入 `__init__.py`。
