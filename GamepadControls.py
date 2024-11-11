bl_info = {
    "name": "Gamepad Controls",
    "author": "OhMyKing",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Gamepad",
    "description": "Control Blender with a gamepad",
    "category": "3D View",
}

import bpy
import mathutils
import threading
import time
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import FloatProperty, PointerProperty, BoolProperty

try:
    from inputs import get_gamepad
    GAMEPAD_AVAILABLE = True
except ImportError:
    GAMEPAD_AVAILABLE = False

from bpy_extras import view3d_utils

# 手柄状态类
class GamepadState:
    def __init__(self):
        self.left_stick_x = 0.0
        self.left_stick_y = 0.0
        self.right_stick_x = 0.0
        self.right_stick_y = 0.0
        self.buttons = {}
        self.button_states = {}
        self.dpad_up = 0
        self.dpad_down = 0
        self.dpad_left = 0
        self.dpad_right = 0

gamepad_state = GamepadState()

# 手柄输入监听线程
class GamepadThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.running = True
        self.error_message = None

    def run(self):
        while self.running and GAMEPAD_AVAILABLE:
            try:
                events = get_gamepad()
                for event in events:
                    self.process_event(event)
            except Exception as e:
                self.error_message = f"手柄错误: {e}"
                print(self.error_message)
                time.sleep(1)

    def process_event(self, event):
        if event.code == 'ABS_X':
            gamepad_state.left_stick_x = event.state / 32768.0
        elif event.code == 'ABS_Y':
            gamepad_state.left_stick_y = event.state / 32768.0
        elif event.code == 'ABS_RX':
            gamepad_state.right_stick_x = event.state / 32768.0
        elif event.code == 'ABS_RY':
            gamepad_state.right_stick_y = event.state / 32768.0
        elif event.code == 'ABS_HAT0Y':
            if event.state == -1:
                gamepad_state.dpad_up = 1
                gamepad_state.dpad_down = 0
            elif event.state == 1:
                gamepad_state.dpad_down = 1
                gamepad_state.dpad_up = 0
            else:
                gamepad_state.dpad_up = 0
                gamepad_state.dpad_down = 0
        elif event.code == 'ABS_HAT0X':
            if event.state == -1:
                gamepad_state.dpad_left = 1
                gamepad_state.dpad_right = 0
            elif event.state == 1:
                gamepad_state.dpad_right = 1
                gamepad_state.dpad_left = 0
            else:
                gamepad_state.dpad_left = 0
                gamepad_state.dpad_right = 0
        elif event.code.startswith('BTN_'):
            gamepad_state.buttons[event.code] = event.state
            gamepad_state.button_states[event.code] = event.state

# 设置属性
class GamepadSettings(PropertyGroup):
    pan_speed: FloatProperty(
        name="平移速度",
        description="视角平移的速度",
        default=0.1,
        min=0.01,
        max=1.0
    )
    rotation_speed: FloatProperty(
        name="旋转速度",
        description="视角旋转的速度",
        default=0.05,
        min=0.01,
        max=1.0
    )
    zoom_speed: FloatProperty(
        name="缩放速度",
        description="视角缩放的速度",
        default=0.5,
        min=0.1,
        max=2.0
    )
    scale_speed: FloatProperty(
        name="物体缩放速度",
        description="物体缩放的速度",
        default=0.05,
        min=0.01,
        max=0.5
    )
    move_speed: FloatProperty(
        name="物体移动速度",
        description="物体移动的速度",
        default=0.1,
        min=0.01,
        max=1.0
    )
    object_rotation_speed: FloatProperty(
        name="物体旋转速度",
        description="物体旋转的速度",
        default=0.05,
        min=0.01,
        max=1.0
    )
    invert_x_axis: BoolProperty(
        name="反转X轴",
        description="反转X轴的控制方向",
        default=False
    )
    invert_y_axis: BoolProperty(
        name="反转Y轴",
        description="反转Y轴的控制方向",
        default=False
    )
    invert_z_axis: BoolProperty(
        name="反转Z轴",
        description="反转Z轴的控制方向",
        default=False
    )

    def update_enable_gamepad_control(self, context):
        if self.enable_gamepad_control:
            bpy.ops.gamepad.control('INVOKE_DEFAULT')
        else:
            # 操作器会检测到这个变化并自行取消
            pass

    enable_gamepad_control: BoolProperty(
        name="启用手柄控制",
        description="启用或禁用手柄控制",
        default=False,
        update=update_enable_gamepad_control
    )

# 主操作器
class GAMEPAD_OT_control(Operator):
    bl_idname = "gamepad.control"
    bl_label = "手柄控制"
    bl_description = "启动手柄控制"

    _timer = None
    _thread = None

    def modal(self, context, event):
        settings = context.scene.gamepad_settings
        if not settings.enable_gamepad_control:
            self.cancel(context)
            return {'CANCELLED'}
        
        # 检查手柄线程中的错误信息
        if self._thread and self._thread.error_message:
            self.report({'ERROR'}, self._thread.error_message)
            settings.enable_gamepad_control = False
            self.cancel(context)
            return {'CANCELLED'}

        if event.type == 'TIMER':
            view3d = context.space_data.region_3d
            settings = context.scene.gamepad_settings

            self.handle_button_actions(context)

            if context.active_object and context.active_object.select_get():
                obj = context.active_object

                if abs(gamepad_state.left_stick_x) > 0.1 or abs(gamepad_state.left_stick_y) > 0.1:
                    move_speed = settings.move_speed
                    dx = gamepad_state.left_stick_x * move_speed
                    dy = -gamepad_state.left_stick_y * move_speed

                    if settings.invert_x_axis:
                        dx = -dx
                    if not settings.invert_y_axis:
                        dy = -dy

                    move_vector = mathutils.Vector((dx, dy, 0.0))
                    move_vector = view3d.view_rotation @ move_vector
                    obj.location += move_vector

                    obj.location = obj.location.copy()
                    obj.keyframe_insert(data_path='location', group="Location")

                if abs(gamepad_state.right_stick_x) > 0.1 or abs(gamepad_state.right_stick_y) > 0.1:
                    rot_speed = settings.object_rotation_speed

                    delta_rot_x = -gamepad_state.right_stick_y * rot_speed
                    delta_rot_z = -gamepad_state.right_stick_x * rot_speed

                    if settings.invert_x_axis:
                        delta_rot_x = -delta_rot_x
                    if settings.invert_z_axis:
                        delta_rot_z = -delta_rot_z

                    rot_euler = mathutils.Euler((delta_rot_x, 0, delta_rot_z), 'XYZ')
                    obj.rotation_euler.rotate(rot_euler)

                    obj.rotation_euler = obj.rotation_euler.copy()
                    obj.keyframe_insert(data_path='rotation_euler', group="Rotation")

                scale_speed = settings.scale_speed

                if gamepad_state.buttons.get('BTN_SOUTH'):
                    factor = 1.0 - scale_speed
                    obj.scale *= factor
                    obj.scale = obj.scale.copy()
                    obj.keyframe_insert(data_path='scale', group="Scale")
                if gamepad_state.buttons.get('BTN_EAST'):
                    factor = 1.0 + scale_speed
                    obj.scale *= factor
                    obj.scale = obj.scale.copy()
                    obj.keyframe_insert(data_path='scale', group="Scale")

                obj.update_tag()
                context.view_layer.update()

            else:
                if abs(gamepad_state.left_stick_x) > 0.1 or abs(gamepad_state.left_stick_y) > 0.1:
                    pan_speed = settings.pan_speed
                    dx = gamepad_state.left_stick_x * pan_speed
                    dy = -gamepad_state.left_stick_y * pan_speed

                    if settings.invert_x_axis:
                        dx = -dx
                    if not settings.invert_y_axis:
                        dy = -dy

                    view3d.view_location += view3d.view_rotation @ mathutils.Vector((dx, dy, 0.0))

                if abs(gamepad_state.right_stick_x) > 0.1 or abs(gamepad_state.right_stick_y) > 0.1:
                    rot_speed = settings.rotation_speed
                    euler = view3d.view_rotation.to_euler()

                    delta_euler_z = gamepad_state.right_stick_x * rot_speed
                    delta_euler_x = gamepad_state.right_stick_y * rot_speed

                    if settings.invert_z_axis:
                        delta_euler_z = -delta_euler_z
                    if settings.invert_x_axis:
                        delta_euler_x = -delta_euler_x

                    euler.z += delta_euler_z
                    euler.x += delta_euler_x
                    view3d.view_rotation = euler.to_quaternion()

                zoom_speed = settings.zoom_speed
                if gamepad_state.buttons.get('BTN_SOUTH'):
                    view3d.view_distance += zoom_speed
                if gamepad_state.buttons.get('BTN_EAST'):
                    view3d.view_distance -= zoom_speed

                self.handle_dpad_view_switch(context)

            context.area.tag_redraw()

            return {'PASS_THROUGH'}

        elif event.type == 'ESC':
            self.cancel(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def handle_button_actions(self, context):
        if gamepad_state.button_states.get('BTN_WEST') == 1:
            self.simulate_keypress(context, 'Z', ctrl=True)
            gamepad_state.button_states['BTN_WEST'] = 0

        if gamepad_state.button_states.get('BTN_NORTH') == 1:
            self.simulate_keypress(context, 'Z', ctrl=True, shift=True)
            gamepad_state.button_states['BTN_NORTH'] = 0

    def handle_dpad_view_switch(self, context):
        if gamepad_state.dpad_up == 1:
            bpy.ops.view3d.view_axis(type='TOP')
            gamepad_state.dpad_up = 0

        if gamepad_state.dpad_down == 1:
            bpy.ops.view3d.view_axis(type='FRONT')
            gamepad_state.dpad_down = 0

        if gamepad_state.dpad_left == 1:
            bpy.ops.view3d.view_axis(type='LEFT')
            gamepad_state.dpad_left = 0

        if gamepad_state.dpad_right == 1:
            bpy.ops.view3d.view_axis(type='RIGHT')
            gamepad_state.dpad_right = 0

    def simulate_keypress(self, context, key, ctrl=False, shift=False, alt=False):
        try:
            if key == 'Z' and ctrl and not shift and not alt:
                bpy.ops.ed.undo()
            elif key == 'Z' and ctrl and shift and not alt:
                bpy.ops.ed.redo()
        except Exception as e:
            if 'undo' in str(e).lower():
                self.report({'INFO'}, "没有可以撤销的操作")
            elif 'redo' in str(e).lower():
                self.report({'INFO'}, "没有可以重做的操作")
            else:
                self.report({'WARNING'}, f"操作失败: {str(e)}")

    def execute(self, context):
        if not GAMEPAD_AVAILABLE:
            self.report({'ERROR'}, "未检测到手柄支持。请安装 'inputs' 包。")
            return {'CANCELLED'}

        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "激活区域必须是3D视图")
            return {'CANCELLED'}

        self._thread = GamepadThread()
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(1/60, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        if self._thread:
            self._thread.running = False
            self._thread.join()

# UI 面板
class GAMEPAD_PT_panel(Panel):
    bl_label = "游戏手柄控制"
    bl_idname = "GAMEPAD_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Gamepad'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.gamepad_settings

        layout.prop(settings, "enable_gamepad_control")

        if not GAMEPAD_AVAILABLE:
            layout.label(text="请安装 'inputs' 包", icon='ERROR')
        else:
            layout.prop(settings, "pan_speed")
            layout.prop(settings, "rotation_speed")
            layout.prop(settings, "zoom_speed")
            layout.prop(settings, "scale_speed")
            layout.prop(settings, "move_speed")
            layout.prop(settings, "object_rotation_speed")
            layout.prop(settings, "invert_x_axis")
            layout.prop(settings, "invert_y_axis")
            layout.prop(settings, "invert_z_axis")

classes = (
    GamepadSettings,
    GAMEPAD_OT_control,
    GAMEPAD_PT_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gamepad_settings = PointerProperty(type=GamepadSettings)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.gamepad_settings

if __name__ == "__main__":
    register()