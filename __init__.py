import bpy
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import IntProperty, EnumProperty, BoolProperty, PointerProperty
from bpy.utils import register_class, unregister_class, previews
import os
import json
from mathutils import Matrix



bl_info = {
    "name": "loca",
    "author": "Pavel Kiba",
    "version": (1, 5, 0),
    "blender": (4, 1, 0),
    "location": "View3D > N-Panel > Animation",
    "description": "Create bone locators for animation",
    "warning": "",
    "doc_url": "",
    "category": "Animation", }

# Define axes for rotation target
axes = [
    ('TRACK_X', ' X', 'Select  X', 0),
    ('TRACK_Y', ' Y', 'Select  Y', 2),
    ('TRACK_Z', ' Z', 'Select  Z', 4),
    ('TRACK_NEGATIVE_X', '-X', 'Select  -X', 1),
    ('TRACK_NEGATIVE_Y', '-Y', 'Select  -Y', 3),
    ('TRACK_NEGATIVE_Z', '-Z', 'Select  -Z', 5),
]

# Global list to store locator names for rotation target
global locators_RT_name_list
locators_RT_name_list = []

def select_bones(context, bone_names):
    armature = context.object
    bpy.ops.pose.select_all(action='DESELECT')    
    if isinstance(bone_names, str):
        bone_names = [bone_names]
    for bone_name in bone_names:
        if bone_name in armature.pose.bones:
            armature.pose.bones[bone_name].bone.select = True

def set_armature_mode(context, mode):
    if context.mode != mode:
        bpy.ops.object.mode_set(mode=mode)

def remove_constraints_by_name_part(pose_bone, name_part):
    if pose_bone.constraints:
        constraints_to_remove = [constraint for constraint in pose_bone.constraints if name_part in constraint.name]
        for constraint in constraints_to_remove:
            pose_bone.constraints.remove(constraint)

def set_keys_on_constraint_influence(constraint, st_frame, end_frame):
    constraint.influence = 0
    constraint.keyframe_insert(data_path="influence", frame=st_frame-1)
    constraint.keyframe_insert(data_path="influence", frame=end_frame+1)
    constraint.influence = 1.0
    constraint.keyframe_insert(data_path="influence", frame=st_frame)
    constraint.keyframe_insert(data_path="influence", frame=end_frame)

def apply_constraint(pose_bone, constraint_type, target, subtarget, track_axis=None):
    constraint = pose_bone.constraints.new(constraint_type)
    constraint.target = target
    constraint.subtarget = subtarget
    if constraint_type == 'DAMPED_TRACK' and track_axis:
        constraint.track_axis = track_axis
    constraint.name += "_LOCA"
    return constraint

def show_message_box(message="", ttl="Message Box", ic='INFO'):
    def draw(self, context):
        self.layout.label(text=message)
    bpy.context.window_manager.popup_menu(draw, title=ttl, icon=ic)

# Remove all F-Curves from all actions that contain the target_string in their data_path
def remove_fcurves_by_data_path(context, target_string):
    armature = context.active_object
    if armature and armature.animation_data and armature.animation_data.action:
        action = armature.animation_data.action
        fcurves_to_remove = [fcurve for fcurve in action.fcurves if target_string in fcurve.data_path]
        for fcurve in fcurves_to_remove:
            action.fcurves.remove(fcurve)

def find_and_remove_broken_fcurves(context, constraint_name_part="__Loca"):
    obj = context.object
    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        fcurves_to_remove = []

        for fcurve in action.fcurves:
            data_path = fcurve.data_path
            if constraint_name_part in data_path:
                fcurves_to_remove.append(fcurve)
                continue                
            try:
                eval('obj.' + data_path)
                obj.path_resolve(data_path)
            except:
                fcurves_to_remove.append(fcurve)
        for fcurve in fcurves_to_remove:
            action.fcurves.remove(fcurve)

# Function to hide scale F-curves
def hide_scale_fcurves(armature_name, bone_name='_LOCA'):
    armature = bpy.data.objects[armature_name]
    if armature.animation_data and armature.animation_data.action:
        for fcurve in armature.animation_data.action.fcurves:
            if '_LOCA' in fcurve.data_path or bone_name in fcurve.data_path:
                if 'scale' in fcurve.data_path:
                    fcurve.hide = True


class WidgetCache:
    cache = None

    @classmethod
    def load_widgets(cls):
        if cls.cache is not None:
            return cls.cache
        json_file = os.path.join(os.path.dirname(__file__), 'widgets.json')
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r') as f:
                    cls.cache = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                show_message_box(f"File reading error: {e}", "Error", 'ERROR')
                cls.cache = {}
        else:
            cls.cache = {}
        return cls.cache

# Function to reate widget for bone
def create_widget(bone, widget_name, widget_scale=[1, 1, 1], relative_size=True):
    context = bpy.context
    data = bpy.data
    widgets = WidgetCache.load_widgets()    
    if widget_name not in widgets:
        show_message_box(f"Widget '{widget_name}' not found in widgets.json.", "Error", 'ERROR')
        return
    widget_data = widgets[widget_name]
    matrixBone = bone

    # Create a new mesh for the widget
    widget_mesh = data.meshes.new("wgt_loca_" + bone.name)

    # Preliminary calculation of bone length
    bone_length = 1 if relative_size else (1 / bone.bone.length)

    # Preliminary calculation of scaling
    scale_factors = [widget_scale[0] * bone_length, widget_scale[2] * bone_length, widget_scale[1] * bone_length]
    widget_vertices = [
        (v[0] * scale_factors[0], v[1] * scale_factors[1], v[2] * scale_factors[2])
        for v in widget_data['vertices']
    ]

    # Create and apply transformation matrix
    widget_transform_matrix = Matrix.Diagonal([bone_length, bone_length, bone_length, 1.0])

    # Apply matrix to mesh data
    widget_mesh.from_pydata(widget_vertices, widget_data['edges'], widget_data['faces'])
    widget_mesh.transform(widget_transform_matrix)
    widget_mesh.update(calc_edges=True)

    # Create a new widget object
    widget_object = data.objects.new("wgt_loca_" + bone.name, widget_mesh)
    widget_object.data = widget_mesh
    widget_object.name = "wgt_loca_" + bone.name

    # Apply world matrix and scale
    widget_object.matrix_world = context.active_object.matrix_world @ matrixBone.bone.matrix_local
    widget_object.scale = [matrixBone.bone.length] * 3
    context.view_layer.update()

    # Assign widget to bone
    bone.custom_shape = widget_object
    bone.bone.show_wire = True

def get_final_frame_from_locator(context, loc_name):
    armature = context.active_object
    end_frame = context.scene.frame_end
    if armature.animation_data and armature.animation_data.action:
        for fcurve in armature.animation_data.action.fcurves:
            if f'{loc_name}_LOCA' in fcurve.data_path.split('"')[1]:
                end_frame = int(fcurve.keyframe_points[-1].co[0])
    return end_frame

def delete_locators(context, locators):
    armature = context.active_object
    for loc_name in locators:
        if loc_name in armature.data.edit_bones:
            armature.data.edit_bones.remove(armature.data.edit_bones[loc_name])

def get_preview_range(context):
    scene = context.scene
    props = scene.loca
    props.bake_start_fr = scene.frame_preview_start
    props.bake_end_fr = scene.frame_preview_end

def update_locator_size(self, context):
    size = self.locator_size
    selected_bones = context.selected_pose_bones
    for bone_P in selected_bones:
        if '_LOCA' in bone_P.name:
            current_scale = bone_P.custom_shape_scale_xyz
            bone_P.custom_shape_scale_xyz = (
                current_scale[0] * size,
                current_scale[1] * size,
                current_scale[2] * size
            )
    self.locator_size = 1.0
    
# Property group to store addon properties
class locaProps(PropertyGroup):
    axis: EnumProperty(
        items=axes,
        description="Select local axis for rotation target",
        default="TRACK_Y",
    )

    select_axis: BoolProperty(
        description="Select local axis for rotation target",
        default=False,
    )

    locator_positioning_active: BoolProperty(
        description="Locator is positioning",
        default=False,
    )

    without_baking: BoolProperty(
        description="Select to create locator without baking",
        default=False,
    )

    bake_start_fr: IntProperty(
        description="Select start frame for baking",
        default = 1,
    )

    bake_end_fr: IntProperty(
        description="Select end frame for baking",
        default = 1,
    )
    add_attached_locator: BoolProperty(
    description="Create Attached Locator",
    default=False,
    )
    locator_size: bpy.props.FloatProperty(
        name="Locator Size",
        description="Size of the selected locator",
        default=1.0,
        min=0.8,
        max=1.2,
        step=0.05,
        precision=2,
        update=update_locator_size
    )


# Operator to create locators
class ARMATURE_OT_loca_create_locator(Operator):
    """Create Locator"""

    bl_label = 'Create Locator'
    bl_idname = 'loca.create_locator'
    bl_options = {'REGISTER', 'UNDO'}

    add_rl_or_al: BoolProperty(
        description="Create Rotation Locator",
        default=False,
    )    
    
    def create_locator_name(self, props, bone_P):
        suffix = 'AL' if props.add_attached_locator else 'RL' if self.add_rl_or_al else 'TL'
        return f'{bone_P.name}_LOCA_{suffix}'

    def get_unique_locator_name(self, armature, base_name):
        locator_name = base_name
        count = 1
        while locator_name in armature.pose.bones:
            locator_name = f"{base_name}.{count:03d}"
            count += 1
        return locator_name    

    def create_bone_locator(self, context, armature, bone_P, locator_name):
        context.object.data.bones.active = context.object.data.bones.get(bone_P.name)
        saved_bone_source_matrix = armature.matrix_world @ context.active_pose_bone.matrix
        # create new bone for locator at the place of selected bone
        set_armature_mode(context, "EDIT")
        source_E = armature.data.edit_bones[bone_P.name]
        locator_E = armature.data.edit_bones.new(locator_name)
        locator_E.head = source_E.head
        locator_E.tail = source_E.tail
        locator_E.matrix = source_E.matrix

        set_armature_mode(context, "POSE")
        locator_P = context.object.pose.bones[locator_name]
        locator_P.matrix = armature.matrix_world.inverted() @ saved_bone_source_matrix
        # set widget for locator
        create_widget(locator_P, "locator")
        locator_P.color.palette = 'THEME13'

    def setup_rotation_attached_locator(self, context, locator_P, has_armature_constraint):
        locators_RT_name_list.append(locator_P.name)
        if not has_armature_constraint:
            bpy.ops.pose.visual_transform_apply()
            constraint = locator_P.constraints[0]
            locator_P.constraints.remove(constraint)
        context.scene.loca.locator_positioning_active = True
        select_bones(context, locator_P.name)

        # Set transform orientation to LOCAL
        bpy.context.scene.transform_orientation_slots[1].type = 'LOCAL'

        show_message_box('Choose position for locator and press button "Confirm Locator Position"', 'LOCATOR POSITIONING')
        
    def setup_transform_locator(self, context, locator_P, bone_P, st_frame, end_frame, has_armature_constraint):
        armature = context.active_object
        scene = context.scene
        props = scene.loca

        if props.without_baking:
                bpy.ops.pose.visual_transform_apply()
                if locator_P.constraints:
                    locator_P.constraints.remove(locator_P.constraints[0])
                apply_constraint(bone_P, 'COPY_TRANSFORMS', armature, locator_P.name)
        else:
            select_bones(context, locator_P.name)
            if not has_armature_constraint:
                bpy.ops.nla.bake(frame_start=st_frame, frame_end=end_frame, only_selected=True,
                                visual_keying=True, clear_constraints=True, use_current_action=True, bake_types={'POSE'})
                remove_fcurves_by_data_path(context, 'active_selection_set')

                hide_scale_fcurves(armature.name)
            copy_transforms = apply_constraint(bone_P, 'COPY_TRANSFORMS', armature, locator_P.name)
            set_keys_on_constraint_influence(copy_transforms, st_frame, end_frame)

        set_armature_mode(context, "POSE")
        select_bones(context, locator_P.name)
        create_widget(locator_P, "locator_tl")

    # Function to create a locator bone
    def create_locator(self, context, bone_P, props):
        armature = context.active_object
        scene = context.scene

        if scene.use_preview_range:
            get_preview_range(context)
        
        st_frame = props.bake_start_fr
        end_frame = props.bake_end_fr

        # Generate unique locator name
        locator_base_name = self.create_locator_name(props, bone_P)
        locator_name = self.get_unique_locator_name(armature, locator_base_name)

        self.create_bone_locator(context, armature, bone_P, locator_name)

        # Check if there's an 'Armature' constraint on the original bone
        has_armature_constraint = any(
            constraint.type == 'ARMATURE'
            for constraint in bone_P.constraints)
        
        locator_P = context.object.pose.bones[locator_name]
        if has_armature_constraint:
            show_message_box(
                f"Selected bone {bone_P.name} has an ARMATURE constraint. You will not be able to bake animation on it further" , 'THE BONE HAS AN ARMATURE CONSTRAINT')
        else:
            apply_constraint(locator_P, 'COPY_TRANSFORMS', armature, bone_P.name)

        # make locator active in POSEMODE
        context.object.data.bones.active = locator_P.bone

        if self.add_rl_or_al:
            self.setup_rotation_attached_locator(context, locator_P, has_armature_constraint)
        else:
            self.setup_transform_locator(context, locator_P, bone_P, st_frame, end_frame, has_armature_constraint)

        return locator_name

    @classmethod
    def poll(cls, context):
        return context.selected_pose_bones is not None

    def execute(self, context):
        props = context.scene.loca
        props.locator_positioning_active = False
        sel_bones = context.selected_pose_bones
        created_locators = []

        for bone in sel_bones:
            locator_name = self.create_locator(context, bone, props)
            created_locators.append(locator_name)
        if created_locators:
            select_bones(context, created_locators)

        if not self.add_rl_or_al:
            self.report({'INFO'}, 'Transform Locator Created')
        self.add_rot_locator = False
        return {'FINISHED'}
    

# Operator to create locators for rotation target
class ARMATURE_OT_loca_create_locator_RL_AL(Operator):
    """Create Rotation Locator or Attached Locator"""

    bl_label = 'Create Rotation Locator or Attached Locator'
    bl_idname = 'loca.create_rl_al'
    bl_options = {'REGISTER', 'UNDO'}

    # Function to bake locator
    def bake_locator(self, context, loc_name):
        armature = context.active_object
        scene = context.scene
        props = scene.loca

        if scene.use_preview_range:
            get_preview_range(context)
        
        st_frame = props.bake_start_fr
        end_frame = props.bake_end_fr

        set_armature_mode(context, "POSE")
        bone_name = loc_name.rsplit('_LOCA', 1)[0]
        print('loc_name', loc_name)
        print('bone_name', bone_name)
        locator = context.object.data.bones[loc_name]
        locator_P = context.object.pose.bones[loc_name]
        context.object.data.bones.active = locator
        pose_bone = context.object.pose.bones[bone_name]

        apply_constraint(locator_P, 'CHILD_OF', armature, bone_name)

        if props.without_baking:
            bpy.ops.pose.visual_transform_apply()
            if locator_P.constraints:
                    locator_P.constraints.remove(locator_P.constraints[0])

            if props.add_attached_locator:
                child_of = apply_constraint(locator_P, 'CHILD_OF', armature, bone_name)
                set_keys_on_constraint_influence(child_of, st_frame, end_frame)
                create_widget(locator_P, "locator_al")
            else:
                damped_track = apply_constraint(pose_bone, 'DAMPED_TRACK', armature, loc_name, props.axis)
                set_keys_on_constraint_influence(damped_track, st_frame, end_frame)
                create_widget(locator_P, "locator_rl")
            if armature.animation_data and armature.animation_data.action:
                for fcurve in armature.animation_data.action.fcurves:
                    if loc_name in fcurve.data_path:
                        armature.animation_data_clear()
        else:
            if props.add_attached_locator:
                create_widget(locator_P, "locator_al")
                if armature.animation_data and armature.animation_data.action:
                    action = armature.animation_data.action
                    curves_to_remove = [fcurve for fcurve in action.fcurves if loc_name in fcurve.data_path]                    
                    for fcurve in curves_to_remove:
                        action.fcurves.remove(fcurve)                
            else:
                select_bones(context, loc_name)
                bpy.ops.anim.keyframe_insert_menu(type='Location')
                bpy.ops.nla.bake(frame_start=st_frame, frame_end=end_frame, only_selected=True,
                                visual_keying=True, clear_constraints=True, use_current_action=True, bake_types={'POSE'}, channel_types={'LOCATION'})
                remove_fcurves_by_data_path(context, 'active_selection_set')
                locator_P = context.object.pose.bones[locator.name]
                if locator_P.constraints:
                    locator_P.constraints.remove(locator_P.constraints[0])
                hide_scale_fcurves(armature.name)
                damped_track = apply_constraint(pose_bone, 'DAMPED_TRACK', armature, loc_name, props.axis)
                set_keys_on_constraint_influence(damped_track, st_frame, end_frame)
                create_widget(locator_P, "locator_rl")

            select_bones(context, loc_name)

    @classmethod
    def poll(cls, context):
        return context.selected_pose_bones is not None

    def execute(self, context):
        props = context.scene.loca
        props.locator_positioning_active = False

        for locator in locators_RT_name_list:
            self.bake_locator(context, locator)
        select_bones(context, locators_RT_name_list)
        locators_RT_name_list.clear()


        if props.add_attached_locator:
            self.report({'INFO'}, 'Attached Locator Created')
        else:
            self.report({'INFO'}, 'Rotation Locator Created')
        props.add_attached_locator = False

        return {'FINISHED'}
    
# Operator to create attached locator
class ARMATURE_OT_loca_create_locator_AL(Operator):
    """Create attached locator"""

    bl_label = 'Create attached locator'
    bl_idname = 'loca.create_locator_al'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.loca
        props.add_attached_locator = True

        bpy.ops.loca.create_locator(add_rl_or_al=True)

        return {'FINISHED'}


class ARMATURE_OT_loca_bake_and_delete(Operator):
    """Bake relevant bones & delele all locators"""

    bl_label = 'Bake relevant bones & delele all locators'
    bl_idname = 'loca.bake_and_del'
    bl_options = {'REGISTER', 'UNDO'}

    bake_on_delete: BoolProperty(
        description="Bake relevant bones during locator deletion",
        default=True,
    )

    def bake(self, context, bone_name):
        armature = context.active_object
        scene = context.scene
        props = scene.loca
        bone_P = context.object.pose.bones[bone_name]
        if bone_name not in armature.pose.bones:
            self.report({'WARNING'}, f'Bone "{bone_name}" does not exist.')
            return 
        
        select_bones(context, bone_name)
        
        if scene.use_preview_range:
            get_preview_range(context)
        
        st_frame = props.bake_start_fr
        end_frame = props.bake_end_fr

        if self.bake_on_delete:
            bpy.ops.nla.bake(
                frame_start=st_frame, 
                frame_end=end_frame, 
                only_selected=True,
                visual_keying=True, 
                clear_constraints=False, 
                use_current_action=True, 
                bake_types={'POSE'}
            )

        remove_fcurves_by_data_path(context, 'active_selection_set')        
        remove_constraints_by_name_part(bone_P, '_LOCA')
        find_and_remove_broken_fcurves(context)      
        hide_scale_fcurves(armature.name, bone_name)

    def execute(self, context):
        armature = context.active_object

        bones_name_list = {bone.name.split('_LOCA')[0] for bone in armature.pose.bones if '_LOCA' in bone.name}

        for bone in bones_name_list:
            self.bake(context, bone)

        locators_to_remove  = [bone.name for bone in armature.pose.bones if '_LOCA' in bone.name]

        set_armature_mode(context, "EDIT")
        delete_locators(context, locators_to_remove )
        set_armature_mode(context, "POSE")
        remove_fcurves_by_data_path(context, '_LOCA')

        locators_RT_name_list.clear()

        if self.bake_on_delete:
            self.report({'INFO'}, 'Relevant Bones Baked & Locators Removed')
        else:
            self.report({'INFO'}, 'Locators Removed')

        return {'FINISHED'}
    

class ARMATURE_OT_loca_bake_and_delete_selected(Operator):
    """Bake relevat bones & delete selected locators"""

    bl_label = 'Bake relevat bones & delete selected locators'
    bl_idname = 'loca.bake_and_del_selected'
    bl_options = {'REGISTER', 'UNDO'}

    def bake(self, context, bone_name):
        st_frame = context.scene.frame_start
        end_frame = context.scene.frame_end
        scene = context.scene
        props = scene.loca
        bone_P = context.object.pose.bones[bone_name]

        has_armature_constraint = any(
            constraint.type == 'ARMATURE'
            for constraint in bone_P.constraints)
        if has_armature_constraint:
            return

        select_bones(context, bone_name)
        
        if scene.use_preview_range:
            get_preview_range(context)
        
        st_frame = props.bake_start_fr
        end_frame = props.bake_end_fr

        bpy.ops.nla.bake(
            frame_start=st_frame, 
            frame_end=end_frame, 
            only_selected=True,
            visual_keying=True, 
            clear_constraints=False, 
            use_current_action=True, 
            bake_types={'POSE'}
        )
        remove_fcurves_by_data_path(context, 'active_selection_set')
        remove_constraints_by_name_part(bone_P, '_LOCA')
        remove_fcurves_by_data_path(context, f'{bone_name}_LOCA')
        find_and_remove_broken_fcurves(context)

    def execute(self, context):
        armature = context.active_object
        selected_bones = [bone for bone in armature.pose.bones if bone.bone.select]
        original_bone_list = set()
        locators_to_remove  = set()

        for bone in selected_bones:
            if any("_LOCA_" in constraint.subtarget for constraint in bone.constraints):
                    original_bone_list.add(bone)
                    print(bone.name)

        for bone in original_bone_list:
            if not any(constraint.type == 'ARMATURE' for constraint in bone.constraints):
                locators_to_remove .update(constraint.subtarget for constraint in bone.constraints 
                if '_LOCA' in constraint.name and constraint.target)
                self.bake(context, bone.name)
        print('locators_to_remove', locators_to_remove)

        set_armature_mode(context, "EDIT")
        # delete_locators(context, locators_to_remove )
        set_armature_mode(context, "POSE")

        self.report({'INFO'}, 'Relevant Bones Baked & Selected Locators Removed')
        return {'FINISHED'}
    

class ARMATURE_OT_loca_delete_selected_locators(Operator):
    """Delete selected locators"""

    bl_label = 'Delete selected locators'
    bl_idname = 'loca.delete_selected_locators'
    bl_description = "Delete selected locators"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_bones = context.selected_pose_bones
        locators_to_delete = []

        for bone in selected_bones:
            if '_LOCA' in bone.name:
                base_bone_name = bone.name.rsplit('_LOCA_', 1)[0]
                # Bone associated with the locator
                if base_bone_name in context.object.pose.bones:
                    base_bone_P = context.object.pose.bones[base_bone_name]
                    remove_constraints_by_name_part(base_bone_P, '_LOCA')
                locators_to_delete.append(bone.name)

        set_armature_mode(context, "EDIT")
        delete_locators(context, locators_to_delete)
        set_armature_mode(context, "POSE")

        self.report({'INFO'}, 'Selected Locators Removed')
        return {'FINISHED'}
    
class ARMATURE_OT_loca_select_all_locators(Operator):
    """Select All Locators"""
    bl_label = 'Select All Locators'
    bl_idname = 'loca.select_all_locators'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'ARMATURE' and context.object.mode == 'POSE'

    def execute(self, context):
        for bone in context.object.pose.bones:
            if 'LOCA' in bone.name:
                bone.bone.select = True
            else:
                bone.bone.select = False

        self.report({'INFO'}, 'All locators selected')
        return {'FINISHED'}
    
# Operator to cycle through widgets
class ARMATURE_OT_loca_cycle_widget(Operator):
    """Cycle through widgets for selected locators"""
    bl_label = "Cycle Locator Widget"
    bl_idname = "loca.cycle_widget"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        widgets = WidgetCache.load_widgets()
        widget_names = list(widgets.keys())
        if not widget_names:
            self.report({'WARNING'}, "No widgets found in widgets.json")
            return {'CANCELLED'}

        selected_bones = context.selected_pose_bones
        for bone_P in selected_bones:
            if '_LOCA' in bone_P.name:
                # Get current widget index
                bone = bone_P.bone
                widget_index = bone.get("widget_index", -1)
                # Increment index
                widget_index = (widget_index + 1) % len(widget_names)
                widget_name = widget_names[widget_index]
                # Assign widget
                create_widget(bone_P, widget_name)
                # Store widget index
                bone["widget_index"] = widget_index
                # Optionally, report which widget was assigned
                self.report({'INFO'}, f"Assigned widget '{widget_name}' to locator '{bone_P.name}'")
        return {'FINISHED'}
    
class ARMATURE_OT_loca_cycle_color(Operator):
    """Cycle through colors for selected locators"""
    bl_label = "Cycle Locator Color"
    bl_idname = "loca.cycle_color"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_bones = context.selected_pose_bones

        current_palette_str = selected_bones[0].color.palette if hasattr(selected_bones[0].color, 'palette') else "THEME13"
        print('current_palette_str', current_palette_str)
        try:
            current_palette_index = int(current_palette_str[-2:])
        except ValueError:
            current_palette_index = 13
        for bone_P in selected_bones:
            if '_LOCA' in bone_P.name:
                new_palette_index = (current_palette_index % 15) + 1
                bone_P.color.palette = f"THEME{new_palette_index:02d}"
                self.report({'INFO'}, f"Changed color to {bone_P.color.palette} for locator '{bone_P.name}'")
        return {'FINISHED'}
    
    

class VIEW3D_PT_loca_locators_panel(Panel):
    version = f"{bl_info['version'][0]}.{bl_info['version'][1]}.{bl_info['version'][2]}"

    bl_label = f"Loca {version}"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    # bl_region_type = 'TOOLS'
    bl_category = f"Loca {version}"
    bl_context = "posemode"

    def draw(self, context):
        props = context.scene.loca
        scene = context.scene
        is_any_locator = False
        for bone in context.object.pose.bones:
            if 'LOCA' in bone.name:
                is_any_locator = True

        if context.object.mode == 'POSE':
            layout = self.layout
            col = layout.column()
            if not props.locator_positioning_active:
                col.prop(props, "without_baking", text='Skip Locator Bake')
                col1 = col.column(align=True)
                col1.operator(ARMATURE_OT_loca_create_locator.bl_idname,
                              text=" Add Transform Locator", icon='EVENT_T').add_rl_or_al = False
                col1.operator(ARMATURE_OT_loca_create_locator.bl_idname,
                              text=" Add Rotation Locator", icon='EVENT_R').add_rl_or_al = True
                col1.operator(ARMATURE_OT_loca_create_locator_AL.bl_idname,
                              text=" Add Attached Locator", icon='EVENT_A')
                col1.scale_y = 1.3
                if is_any_locator:
                    selected_pose_bones = context.selected_pose_bones
                    show_bake_selected = False
                    locator_selected = False
                    for bone in selected_pose_bones:
                        for constraint in bone.constraints:
                            if constraint.subtarget and "_LOCA_" in constraint.subtarget:
                                show_bake_selected = True
                                break
                        if "_LOCA_" in bone.name:
                            locator_selected = True

                    col.separator()
                    box = col.box()
                    col3 = box.column(align=True)
                    col3.operator(ARMATURE_OT_loca_select_all_locators.bl_idname,
                              text="Select All Locators")
                    col1 = box.column(align=True)
                    col1.operator(ARMATURE_OT_loca_bake_and_delete.bl_idname,
                                  text="Bake & Remove Locators").bake_on_delete = True

                    # Отобразить оператор только если найдено соответствие
                    row =col1.row()
                    row.enabled = show_bake_selected
                    row.operator(ARMATURE_OT_loca_bake_and_delete_selected.bl_idname, text="Bake Selected Bone")
                    
                    col2 = box.column(align=True)
                    row =col2.row()
                    row.enabled = locator_selected
                    row.operator(ARMATURE_OT_loca_delete_selected_locators.bl_idname, text="Remove Selected Locator")
                    col2.operator(ARMATURE_OT_loca_bake_and_delete.bl_idname,
                                  text="Remove All Locators").bake_on_delete = False

                    
                    col4 = box.column(align=True)
                    col4.enabled = locator_selected
                    row2 = col4.row(align=True)
                    row2.operator(ARMATURE_OT_loca_cycle_widget.bl_idname, text="Widget")
                    row2.operator(ARMATURE_OT_loca_cycle_color.bl_idname, text="Color")
                    col4.prop(props, "locator_size", text="Size", slider=True)
            else:
                col.prop(props, "select_axis", text='Select Local Axis')
                if props.select_axis:
                    row = col.row(align=True)
                    row.prop(props, "axis", expand=True)
                col.operator(ARMATURE_OT_loca_create_locator_RL_AL.bl_idname,
                             text=" Confirm Locator Position", icon='PLAY', depress=True)
                
            col1 = col.column(align=True)

            if not scene.use_preview_range and not props.add_attached_locator:
                box = col1.box()
                col = box.column()
                col.label(text="Bake in Frame Range:")
                row = col.row(align=True)
                row.prop(props, "bake_start_fr", text="")
                row.prop(props, "bake_end_fr", text="")


classes = [
    locaProps,
    ARMATURE_OT_loca_create_locator,
    ARMATURE_OT_loca_create_locator_RL_AL,
    ARMATURE_OT_loca_create_locator_AL,
    ARMATURE_OT_loca_bake_and_delete,
    ARMATURE_OT_loca_bake_and_delete_selected,
    ARMATURE_OT_loca_delete_selected_locators,
    ARMATURE_OT_loca_select_all_locators,
    ARMATURE_OT_loca_cycle_widget,
    ARMATURE_OT_loca_cycle_color,
    VIEW3D_PT_loca_locators_panel,
]

def register():
    for cl in classes:
        register_class(cl)

    bpy.types.Scene.loca = PointerProperty(type=locaProps)

def unregister():
    for cl in reversed(classes):
        unregister_class(cl)
    del bpy.types.Scene.loca

if __name__ == "__main__":
    register()
