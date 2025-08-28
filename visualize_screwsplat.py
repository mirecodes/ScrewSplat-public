import torch
import os
from argparse import ArgumentParser
from arguments import get_combined_args
from scene.gaussian_model import ScrewGaussianModel
import numpy as np
import open3d as o3d
import open3d.visualization.gui as gui
import open3d.visualization.rendering as rendering
from articulated_object.utils import exp_se3
from articulated_object.rotation_conversions import quaternion_to_matrix
from datetime import datetime
from copy import deepcopy
from tqdm import tqdm
from utils.sh_utils import SH2RGB

class AppWindow:

    def __init__(self, args):

        # prune iteration
        self.prune_screws_iter = 20001
        self.min_load_opacity = 0.7

        # parser
        self.process_data(args)

        ######################################################
        ################## SCENE SETTINGS ####################
        ######################################################

        # parameters 
        image_size = [1280, 800]

        # object material
        self.mat = rendering.MaterialRecord()
        self.mat.shader = 'defaultLit'
        self.mat.base_color = [1.0, 1.0, 1.0, 0.9]
        mat_prev = rendering.MaterialRecord()
        mat_prev.shader = 'defaultLitTransparency'
        mat_prev.base_color = [1.0, 1.0, 1.0, 0.7]
        mat_coord = rendering.MaterialRecord()
        mat_coord.shader = 'defaultLitTransparency'
        mat_coord.base_color = [1.0, 1.0, 1.0, 0.87]

        # set window
        self.window = gui.Application.instance.create_window(
            str(datetime.now().strftime('%H%M%S')), 
            width=image_size[0], height=image_size[1])
        w = self.window
        self._scene = gui.SceneWidget()
        self._scene.scene = rendering.Open3DScene(w.renderer)

        # camera viewpoint
        self._scene.scene.camera.look_at(
            [0, 0, 0], # camera lookat
            [-0.5, 0, 0.65], # camera position
            [0, 0, 1] # fixed
        )

        # other settings
        self._scene.scene.set_lighting(
            self._scene.scene.LightingProfile.DARK_SHADOWS, 
            (-0.3, 0.3, -0.9))
        self._scene.scene.set_background(
            [1.0, 1.0, 1.0, 4.0], 
            image=None)

        ############################################################
        ######################### MENU BAR #########################
        ############################################################

        # callback function initialize
        self.generate_set_joint_angles()
        self.generate_screw_activations()

        # menu bar initialize
        em = w.theme.font_size
        separation_height = int(round(0.5 * em))
        self._settings_panel = gui.Vert(
            0, gui.Margins(0.25 * em, 0.25 * em, 0.25 * em, 0.25 * em))

        # initialize collapsable vert
        vis_config = gui.CollapsableVert(
            "Visualization Mode", 0.25 * em, gui.Margins(em, 0, 0, 0))    

        # visualization mode
        _color_button = gui.Button("Color")
        _color_button.horizontal_padding_em = 0.5
        _color_button.vertical_padding_em = 0
        _color_button.set_on_clicked(self._set_mode_color)
        _segmentation_button = gui.Button("Segmentation")
        _segmentation_button.horizontal_padding_em = 0.5
        _segmentation_button.vertical_padding_em = 0
        _segmentation_button.set_on_clicked(self._set_mode_segmentation)
        self._vis_mode_button_list = [_color_button, _segmentation_button]
        h = gui.Horiz(0.25 * em)
        h.add_stretch()
        h.add_child(_color_button)
        h.add_child(_segmentation_button)
        h.add_stretch()

        # add
        vis_config.add_child(h)
        vis_config.add_fixed(separation_height)

        # initialize collapsable vert
        iter_config = gui.CollapsableVert(
            "Iteration", 0.25 * em, gui.Margins(em, 0, 0, 0))

        # slider
        _iteration_slider = gui.Slider(gui.Slider.INT)
        _iteration_slider.set_limits(0, len(self.sorted_iters)-1)
        _iteration_slider.int_value = self.sorted_iters[-1]
        _iteration_slider.set_on_value_changed(
            self._set_iteration)

        # iteration
        self._iteration_text = gui.TextEdit()

        # add
        iter_config.add_child(self._iteration_text)
        iter_config.add_child(_iteration_slider)
        iter_config.add_fixed(separation_height)

        # initialize collapsable vert
        opacity_config = gui.CollapsableVert(
            "Opacity", 0.25 * em, gui.Margins(em, 0, 0, 0))

        # slider
        _opacity_slider = gui.Slider(gui.Slider.DOUBLE)
        _opacity_slider.set_limits(0.5, 1.0)
        _opacity_slider.double_value = 0.9
        _opacity_slider.set_on_value_changed(
            self._set_opacity)

        # add
        opacity_config.add_child(_opacity_slider)
        opacity_config.add_fixed(separation_height)

        # initialize collapsable vert
        screw_config = gui.CollapsableVert(
            "Screws", 0.25 * em, gui.Margins(em, 0, 0, 0))

        # parameter sliders
        self._button_list = []
        self._slider_list = []
        self._confidence_list = []
        for i in range(len(self.data[0]['screws'])):
            
            # button
            _screw_activation_button = gui.Button(
                f'Screw {i+1}')
            _screw_activation_button.horizontal_padding_em = 0.5
            _screw_activation_button.vertical_padding_em = 0
            _screw_activation_button.set_on_clicked(
                getattr(self, f'_screw_activation_{i+1}'))
            self._button_list.append(_screw_activation_button)

            _confidence_text = gui.TextEdit()
            self._confidence_list.append(_confidence_text)

            # slider
            _slider = gui.Slider(gui.Slider.DOUBLE)
            _slider.set_limits(-3.14, 3.14)
            _slider.double_value = 0.0
            _slider.set_on_value_changed(
                getattr(self, f'_set_joint_angle_{i+1}'))
            self._slider_list.append(_slider)

            # add
            h = gui.Horiz(0.25 * em)
            h.add_child(_screw_activation_button)
            h.add_child(_confidence_text)
            h.add_stretch()
            screw_config.add_child(h)
            screw_config.add_child(_slider)

        # screws after pruning
        if max(self.sorted_iters) > self.prune_screws_iter:
            
            # initialize collapsable vert
            final_screw_config = gui.CollapsableVert(
                "Final Screws", 0.25 * em, gui.Margins(em, 0, 0, 0))

            # parameter sliders
            self._final_button_list = []
            self._final_slider_list = []
            self._final_confidence_list = []
            for i in range(len(self.data[-1]['screws'])):
                
                # button
                _screw_activation_button = gui.Button(
                    f'Screw {i+1}')
                _screw_activation_button.horizontal_padding_em = 0.5
                _screw_activation_button.vertical_padding_em = 0
                _screw_activation_button.set_on_clicked(
                    getattr(self, f'_screw_activation_{i+1}'))
                self._final_button_list.append(_screw_activation_button)

                _confidence_text = gui.TextEdit()
                self._final_confidence_list.append(_confidence_text)

                # slider
                _slider = gui.Slider(gui.Slider.DOUBLE)
                _slider.set_limits(-3.14, 3.14)
                _slider.double_value = 0.0
                _slider.set_on_value_changed(
                    getattr(self, f'_set_joint_angle_{i+1}'))
                self._final_slider_list.append(_slider)

                # add
                h = gui.Horiz(0.25 * em)
                h.add_child(_screw_activation_button)
                h.add_child(_confidence_text)
                h.add_stretch()
                final_screw_config.add_child(h)
                final_screw_config.add_child(_slider)

            # declare config list
            self.config_list = [screw_config, final_screw_config]
            self.config_list[0].set_is_open(False)
            self.config_list[1].set_is_open(False)

        # add
        self._settings_panel.add_child(vis_config)
        self._settings_panel.add_child(iter_config)
        self._settings_panel.add_child(opacity_config)
        self._settings_panel.add_child(screw_config)
        if max(self.sorted_iters) > self.prune_screws_iter:
            self._settings_panel.add_child(final_screw_config)

        # add scene
        w.set_on_layout(self._on_layout)
        w.add_child(self._scene)
        w.add_child(self._settings_panel)

        ##########################################
        ################ INITIALIZE ##############
        ##########################################

        # initialize
        if max(self.sorted_iters) > self.prune_screws_iter:
            self.joint_angle = torch.zeros(len(self._final_slider_list))
        else:
            self.joint_angle = torch.zeros(len(self._slider_list))
        self.vis_mode = 'color'
        self.opacity = 0.9
        self.activated_screw = -1
        self.after_prune_iter = True
        self._set_iteration(-1)

    ############################################################
    ######################### FUNCTIONS ########################
    ############################################################

    def _on_layout(self, layout_context):
        r = self.window.content_rect
        self._scene.frame = r
        width = 17 * layout_context.theme.font_size
        height = min(
            r.height,
            self._settings_panel.calc_preferred_size(
                layout_context, gui.Widget.Constraints()).height)
        self._settings_panel.frame = gui.Rect(r.get_right() - width, r.y, width,
                                              height)		

    def process_data(self, model_path):

        # process args
        model_path = args.model_path
        sh_degree = args.sh_degree

        # initialize gaussian
        checkpoint_name_list = [file for file in os.listdir(model_path) if file.endswith('.pth')]
        sorted_checkpoints_names = sorted(checkpoint_name_list, key=lambda x: int(x.replace('chkpnt', '').replace('.pth', '')))
        self.sorted_iters = [int(x.replace('chkpnt', '').replace('.pth', '')) for x in sorted_checkpoints_names]

        # pbar
        pbar = tqdm(
            total=len(self.sorted_iters), 
            desc=f"loading {model_path} ... ", 
            leave=False
        )	
        self.data = []

        # load all checkpoints
        for checkpoint_name in sorted_checkpoints_names:

            # load gaussians
            gaussians = ScrewGaussianModel(sh_degree)
            checkpoint = os.path.join(model_path, checkpoint_name)
            (model_params, first_iter) = torch.load(checkpoint, weights_only=False)
            gaussians.restore(model_params)

            # process all
            scalings = gaussians.get_scaling.cpu().detach().numpy()
            rotations = gaussians.get_rotation.cpu()
            SO3s = quaternion_to_matrix(rotations).detach().numpy()
            xyzs = gaussians.get_xyz.cpu().detach().numpy()
            features = gaussians.get_features.cpu().detach().numpy()
            opacities = gaussians.get_opacity.cpu().detach().numpy()
            part_indices = gaussians.get_part_indices.cpu().detach().numpy()
            screws = gaussians.get_screws.cpu().detach().numpy()
            _screws = gaussians._screws.cpu().detach().numpy()
            screw_confs = gaussians.get_screw_confs.cpu().detach().numpy()
            joint_angles = gaussians.get_joint_angles
            lower_limit = torch.min(torch.stack(joint_angles), dim=0)[0]
            upper_limit = torch.max(torch.stack(joint_angles), dim=0)[0]
            joint_limits = torch.cat(
                (lower_limit.unsqueeze(-1), upper_limit.unsqueeze(-1)), dim=1
            ).cpu().detach().numpy()

            # process gaussians
            gaussian_ellipsoids = [[] for _ in range(part_indices.shape[1])]
            gaussian_colors = [[] for _ in range(part_indices.shape[1])]
            gaussian_opacities = [[] for _ in range(part_indices.shape[1])]
            for i in range(len(xyzs)):
                
                # Gaussian parameter
                scale = scalings[i]
                SO3 = SO3s[i] 
                position = xyzs[i]
                color = np.clip(SH2RGB(features[i, 0, :]), 0, 1)
                opacity = opacities[i]
                part_index = np.argmax(part_indices[i])

                # unit sphere
                ellipsoid = o3d.geometry.TriangleMesh.create_sphere(radius=1.0, resolution=4)
                ellipsoid.compute_vertex_normals()

                # transform Gaussian
                scaling_matrix = np.diag(scale)  # Convert to (3,3) diagonal scaling matrix
                transform_matrix = np.eye(4)  # 4x4 transformation matrix
                transform_matrix[:3, :3] = SO3 @ scaling_matrix  # Apply rotation & scaling
                transform_matrix[:3, 3] = position  # Set translation
                ellipsoid.transform(transform_matrix)

                if opacity > self.min_load_opacity:
                    gaussian_ellipsoids[part_index].append(ellipsoid)
                    gaussian_colors[part_index].append(color)
                    gaussian_opacities[part_index].append(opacity)

            # arrow parameters
            arrow_scale = 0.3
            cylinder_radius = 0.02
            cone_radius = 0.06
            cylinder_height = 1.2
            cone_height = 0.2

            # draw screws
            screw_lines = []
            screw_points = []
            screw_colors = []
            for j in range(len(screws)):

                # initialize
                w = screws[j, :3]
                v = screws[j, 3:]
                q = _screws[j, 3:]
                conf = screw_confs[j]

                # revolute
                if np.linalg.norm(w) > 1e-6:
                   # line segment
                    conf = conf * 2.0
                    color = np.array([1.0, 0, 0]) * conf + np.array([0.8, 0.8, 0.8]) * (1 - conf)
                    color = np.clip(color / np.max(color), 0, 1)

                    # arrow
                    arrow = o3d.geometry.TriangleMesh.create_arrow(
                        cylinder_radius=cylinder_radius * arrow_scale, 
                        cone_radius=cone_radius * arrow_scale, 
                        cylinder_height=cylinder_height * arrow_scale, 
                        cone_height=cone_height * arrow_scale, 
                        resolution=40, 
                        cylinder_split=4, 
                        cone_split=1)
                    arrow.compute_vertex_normals()
                    arrow.translate([0, 0, - cylinder_height * arrow_scale * 0.5])

                    # rotate R
                    z_axis = np.array([0, 0, 1])
                    v = np.cross(z_axis, w)
                    s = np.linalg.norm(v)
                    c = np.dot(z_axis, w)		
                    if s == 0:  # If w is already aligned with z-axis (either up or down)
                        R = np.eye(3) if c > 0 else -np.eye(3)
                    else:
                        Vx = np.array([[0, -v[2], v[1]],
                                    [v[2], 0, -v[0]],
                                    [-v[1], v[0], 0]])
                        R = np.eye(3) + Vx + (Vx @ Vx) * ((1 - c) / (s ** 2))
                    arrow.rotate(R, center=(0, 0, 0))	
                    arrow.translate(q)		

                    # screw point
                    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.01, resolution=10)
                    sphere.compute_vertex_normals()
                    sphere.translate(q)

                # prismatic
                else:

                    # line segment
                    conf = conf * 2.0
                    color = np.array([0, 0, 1.0]) * conf + np.array([0.8, 0.8, 0.8]) * (1 - conf)
                    color = np.clip(color / np.max(color), 0, 1)

                    arrow = o3d.geometry.TriangleMesh.create_arrow(
                        cylinder_radius=cylinder_radius * arrow_scale, 
                        cone_radius=cone_radius * arrow_scale, 
                        cylinder_height=cylinder_height * arrow_scale, 
                        cone_height=cone_height * arrow_scale, 
                        resolution=40, 
                        cylinder_split=4, 
                        cone_split=1)
                    arrow.compute_vertex_normals()
                    arrow.translate([0, 0, - cylinder_height * arrow_scale * 0.5])
                    
                    # rotate R
                    w = -v
                    z_axis = np.array([0, 0, 1])
                    v = np.cross(z_axis, w)
                    s = np.linalg.norm(v)
                    c = np.dot(z_axis, w)		
                    if s == 0:  # If w is already aligned with z-axis (either up or down)
                        R = np.eye(3) if c > 0 else -np.eye(3)
                    else:
                        Vx = np.array([[0, -v[2], v[1]],
                                    [v[2], 0, -v[0]],
                                    [-v[1], v[0], 0]])
                        R = np.eye(3) + Vx + (Vx @ Vx) * ((1 - c) / (s ** 2))
                    arrow.rotate(R, center=(0, 0, 0))

                    # screw point
                    sphere = o3d.geometry.TriangleMesh.create_sphere(radius=0.01, resolution=10)
                    sphere.compute_vertex_normals()

                screw_lines.append(arrow)
                screw_points.append(sphere)
                screw_colors.append(color)

            # total list
            self.data.append({
                'gaussian_ellipsoids': gaussian_ellipsoids, 
                'gaussian_colors': gaussian_colors,
                'gaussian_opacities': gaussian_opacities,
                'screws': torch.tensor(screws).float(),
                'screw_lines': screw_lines,
                'screw_points': screw_points,
                'screw_colors': screw_colors,
                'screw_confs': screw_confs,
                'joint_limits': joint_limits})
            pbar.update(1)

        # close
        pbar.close()

    def update_scene(self):
                
        # clear geometry
        self._scene.scene.clear_geometry()

        # set initial parameters
        if self.sorted_iters[self.iteration] > self.prune_screws_iter:
            self.joint_angle = torch.zeros(len(self._final_slider_list))
            for i, slider in enumerate(self._final_slider_list):
                self.joint_angle[i] = slider.double_value
        else:
            self.joint_angle = torch.zeros(len(self._slider_list))
            for i, slider in enumerate(self._slider_list):
                self.joint_angle[i] = slider.double_value

        # screw transforms
        screw_transforms = exp_se3(torch.tensor(
            self.screws * self.joint_angle.unsqueeze(1))).numpy()

        # add gaussians
        for i, (segmented_ellipsoids, segmented_colors, segmented_opacities) in enumerate(zip(self.gaussian_ellipsoids, self.gaussian_colors, self.gaussian_opacities)):
            ellipsoids = o3d.geometry.TriangleMesh()
            for ellipsoid, color, opacity in zip(segmented_ellipsoids, segmented_colors, segmented_opacities):

                # continue
                if opacity < self.opacity:
                    continue

                # deepcopy
                _ellipsoid = deepcopy(ellipsoid)

                # transform
                if i >= 1:
                    _ellipsoid.transform(screw_transforms[i-1])

                # color
                if self.vis_mode == 'color':    
                    _ellipsoid.paint_uniform_color(color)
                    ellipsoids += _ellipsoid
                else:
                    if i == self.activated_screw:
                        _ellipsoid.paint_uniform_color([1.0, 0.0, 0.0])
                    else:
                        _ellipsoid.paint_uniform_color([0.8, 0.8, 0.8])
                    ellipsoids += _ellipsoid

            # add
            self._scene.scene.add_geometry(f'ellipsoids_{i}', ellipsoids, self.mat)

        # add screws
        for i, (screw_line, screw_point, screw_color) in enumerate(zip(self.screw_lines, self.screw_points, self.screw_colors)):
            if self.vis_mode == 'color':
                screw_line.paint_uniform_color(screw_color)
                screw_point.paint_uniform_color(screw_color)
            else:
                if i == self.activated_screw - 1:
                    screw_line.paint_uniform_color(screw_color)
                    screw_point.paint_uniform_color(screw_color)
                else:
                    screw_line.paint_uniform_color([0.8, 0.8, 0.8])
                    screw_point.paint_uniform_color([0.8, 0.8, 0.8])
            
            self._scene.scene.add_geometry(f'screw_line_{i}', screw_line, self.mat)
            self._scene.scene.add_geometry(f'screw_point_{i}', screw_point, self.mat)

        # activated visualization mode
        if self.vis_mode == 'color':
            self._vis_mode_button_list[0].background_color = gui.Color(0.0, 0.0, 1.0, 1.0)
            self._vis_mode_button_list[1].background_color = gui.Color(0.5, 0.5, 0.5, 1.0)
        else:
            self._vis_mode_button_list[0].background_color = gui.Color(0.5, 0.5, 0.5, 1.0)
            self._vis_mode_button_list[1].background_color = gui.Color(0.0, 0.0, 1.0, 1.0)

        # activated screw
        if self.sorted_iters[self.iteration] > self.prune_screws_iter:
            for i, slider in enumerate(self._final_button_list):
                if i == self.activated_screw - 1:
                    slider.background_color = gui.Color(1.0, 0.0, 0.0, 1.0)
                else:
                    slider.background_color = gui.Color(0.5, 0.5, 0.5, 1.0)
        else:
            for i, slider in enumerate(self._button_list):
                if i == self.activated_screw - 1:
                    slider.background_color = gui.Color(1.0, 0.0, 0.0, 1.0)
                else:
                    slider.background_color = gui.Color(0.5, 0.5, 0.5, 1.0)

    def _set_mode_color(self):
        self.vis_mode = 'color'
        self.update_scene()

    def _set_mode_segmentation(self):
        self.vis_mode = 'segmentation'
        self.update_scene()

    def _set_iteration(self, value):

        # initialize data
        iteration = int(value)
        self.iteration = iteration
        self.gaussian_ellipsoids = self.data[iteration]['gaussian_ellipsoids']
        self.gaussian_colors = self.data[iteration]['gaussian_colors']
        self.gaussian_opacities = self.data[iteration]['gaussian_opacities']
        self.screws = self.data[iteration]['screws']
        self.screw_lines = self.data[iteration]['screw_lines']
        self.screw_points = self.data[iteration]['screw_points']
        self.screw_colors = self.data[iteration]['screw_colors']
        self.screw_confs = self.data[iteration]['screw_confs']
        self.joint_limits = self.data[iteration]['joint_limits']

        # update
        self._iteration_text.text_value = f'Iteration: {str(self.sorted_iters[iteration])}'
        if self.sorted_iters[iteration] > self.prune_screws_iter:
            if max(self.sorted_iters) > self.prune_screws_iter:
                self.config_list[0].set_is_open(False)
                self.config_list[1].set_is_open(True)
                self.window.set_needs_layout()
                if not self.after_prune_iter:
                    self.activated_screw = -1
                self.after_prune_iter = True
            for i, slider in enumerate(self._final_slider_list):
                slider.set_limits(self.joint_limits[i, 0], self.joint_limits[i, 1])
                slider.double_value = (self.joint_limits[i, 0] + self.joint_limits[i, 1]) / 2
            for i, editor in enumerate(self._final_confidence_list):
                editor.text_value = f' Confidence: {str(round(self.screw_confs[i], 3))}'
        else:
            if max(self.sorted_iters) > self.prune_screws_iter:
                self.config_list[0].set_is_open(True)
                self.config_list[1].set_is_open(False)
                self.window.set_needs_layout()
                if self.after_prune_iter:
                    self.activated_screw = -1
                self.after_prune_iter = False
            for i, slider in enumerate(self._slider_list):
                slider.set_limits(self.joint_limits[i, 0], self.joint_limits[i, 1])
                slider.double_value = (self.joint_limits[i, 0] + self.joint_limits[i, 1]) / 2
            for i, editor in enumerate(self._confidence_list):
                editor.text_value = f' Confidence: {str(round(self.screw_confs[i], 3))}'
        self.update_scene()

    def _set_opacity(self, value):
        self.opacity = value
        self.update_scene()

    def generate_set_joint_angles(self):
        for i in range(1, 30):
            def func(value, i=i):
                self.joint_angle[i-1] = value
                self.update_scene()
            setattr(self, f'_set_joint_angle_{i}', func)

    def generate_screw_activations(self):
        for i in range(1, 30):
            def func(i=i):
                self.activated_screw = i
                self.update_scene()
            setattr(self, f'_screw_activation_{i}', func)

if __name__ == "__main__":

    # parser
    parser = ArgumentParser(description="Testing script parameters")
    parser.add_argument("--model_path", type=str)
    args = get_combined_args(parser)

    # run
    gui.Application.instance.initialize()
    w = AppWindow(args)
    gui.Application.instance.run()