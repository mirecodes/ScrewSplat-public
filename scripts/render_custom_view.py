import sys
import os

# Add parent directory to sys.path to allow imports from root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
from argparse import ArgumentParser, Namespace
from arguments import get_combined_args
import numpy as np
import open3d as o3d
import open3d.visualization.rendering as rendering
from copy import deepcopy
from evaluator import Evaluator
from gaussian_renderer import ScrewGaussianModel
import cv2
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class RenderConfig:
    # Evaluator required args
    model_path: str
    white_background: bool = True
    sh_degree: int = 3
    
    # Custom render args
    ratio: float = 0.5
    cam_pos: List[float] = field(default_factory=lambda: [300.0, 300.0, 300.0])
    cam_lookat: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    res: List[int] = field(default_factory=lambda: [1280, 960])
    output_path: str = "custom_render.png"
    
    def to_args(self):
        return self

class CustomEvaluator(Evaluator):
    def load_trained_model(self, args):
        # load
        model_path = args.model_path
        white_background = args.white_background
        sh_degree = args.sh_degree

        # background color
        bg_color = [1, 1, 1] if white_background else [0, 0, 0]
        self.bg = torch.tensor(bg_color, dtype=torch.float32, device="cuda")

        # get recent checkpoint
        checkpoint_name_list = [file for file in os.listdir(model_path) if file.endswith('.pth')]
        sorted_checkpoints_names = sorted(checkpoint_name_list, key=lambda x: int(x.replace('chkpnt', '').replace('.pth', '')))
        checkpoint_name = sorted_checkpoints_names[-1]

        # initialize gaussian        
        self.gaussians = ScrewGaussianModel(sh_degree)
        checkpoint = os.path.join(model_path, checkpoint_name)
        (model_params, first_iter) = torch.load(checkpoint, weights_only=False)
        
        # Check if model_params is for vanilla Gaussian Model (12 elements)
        if len(model_params) == 12:
            print("Detected vanilla Gaussian Splatting checkpoint. Adapting to ScrewGaussianModel...")
            # Unpack vanilla params
            (
                active_sh_degree, 
                _xyz, 
                _features_dc, 
                _features_rest,
                _scaling, 
                _rotation, 
                _opacity,
                max_radii2D, 
                xyz_gradient_accum, 
                denom,
                opt_dict, 
                spatial_lr_scale
            ) = model_params
            
            # Create dummy screw params
            # _screws must be 2D [N_screws, 6]
            _screws = torch.empty((0, 6), device=_xyz.device)
            _screw_confs = torch.empty(0, device=_xyz.device)
            # part indices: all points belong to static part (index 0)
            # shape [N, 1]
            _part_indices = torch.ones(_xyz.shape[0], 1, device=_xyz.device)
            _joint_angles = []
            n_revol = 0
            n_pris = 0
            
            model_params = (
                active_sh_degree, 
                _xyz, 
                _features_dc, 
                _features_rest,
                _scaling, 
                _rotation, 
                _opacity,
                max_radii2D, 
                xyz_gradient_accum, 
                denom,
                opt_dict, 
                spatial_lr_scale,
                _screws,
                _screw_confs,
                _part_indices,
                _joint_angles,
                n_revol,
                n_pris
            )
            
        self.gaussians.restore(model_params)

        # get joint limit
        joint_angles = self.gaussians.get_joint_angles
        if len(joint_angles) > 0:
            lower_limit = torch.min(torch.stack(joint_angles), dim=0)[0]
            upper_limit = torch.max(torch.stack(joint_angles), dim=0)[0]
            self.joint_limits = torch.cat(
                (lower_limit.unsqueeze(-1), upper_limit.unsqueeze(-1)), dim=1)
        else:
            self.joint_limits = torch.zeros(0, 2)

def composite_on_white(img):
    if img.shape[2] == 4:
        alpha = img[:, :, 3] / 255.0
        rgb = img[:, :, :3]
        white_bg = np.ones_like(rgb, dtype=np.uint8) * 255
        blended = (alpha[..., None] * rgb + (1 - alpha[..., None]) * white_bg).astype(np.uint8)
        return blended
    else:
        return img

def main(config: RenderConfig):
    # Initialize evaluator using CustomEvaluator
    evaluator = CustomEvaluator(config)

    # Figure settings
    width, height = config.res
    
    # Define ground plane (same as make_videos.py)
    a = 200.0
    plane = o3d.geometry.TriangleMesh.create_box(width=a, depth=0.05, height=a)
    plane.paint_uniform_color([1.0, 1.0, 1.0])
    plane.translate([-a/2, -a/2, -1.0])
    plane.compute_vertex_normals()
    mat_plane = rendering.MaterialRecord()
    mat_plane.shader = 'defaultLit'
    mat_plane.base_color = [1.0, 1.0, 1.0, 4.0]
    
    # Object material
    mat = rendering.MaterialRecord()
    mat.shader = 'defaultLit'
    mat.base_color = [1.0, 1.0, 1.0, 0.9]

    # Camera info
    camera_position = np.array(config.cam_pos)
    camera_lookat = np.array(config.cam_lookat)
    up_vector = np.array([0, 0, 1])

    # Setup renderer
    widget = o3d.visualization.rendering.OffscreenRenderer(width, height)
    widget.scene.camera.look_at(camera_lookat, camera_position, up_vector)
    
    # Lighting and background
    light_dir = (0.3, -0.3, -0.9)
    widget.scene.add_geometry('plane', plane, mat_plane)
    widget.scene.set_lighting(widget.scene.LightingProfile.DARK_SHADOWS, light_dir)
    widget.scene.set_background([1.0, 1.0, 1.0, 1.0], image=None)

    # Colors for parts
    rgbs = np.array([
        [128,128,128], # static
        [0,128,255],   # moving 1
        [0,255,0],     # moving 2
        [255,128,0]    # moving 3
    ])/255

    # Separate part-aware gaussians
    static_part_mask = evaluator.gaussians.get_part_indices[:,[0]] > 0.5
    dynamic_part_mask = evaluator.gaussians.get_part_indices[:,1:] > 0.5
    static_gaussians = deepcopy(evaluator.gaussians)
    
    with torch.no_grad():
        static_gaussians._opacity = static_gaussians._opacity.detach()
        static_gaussians._opacity[~static_part_mask] = evaluator.gaussians.inverse_opacity_activation(torch.tensor(1e-4))
        dynamic_gaussian_list = []
        for i in range(dynamic_part_mask.shape[-1]):
            dynamic_gaussians = deepcopy(evaluator.gaussians)
            dynamic_gaussians._opacity[~dynamic_part_mask[:,[i]]] = evaluator.gaussians.inverse_opacity_activation(torch.tensor(1e-4))
            dynamic_gaussian_list.append(dynamic_gaussians)

    # Calculate target configuration
    joint_angles_list = evaluator.gaussians.get_joint_angles
    if len(joint_angles_list) > 0:
        lower_limit = torch.min(torch.stack(joint_angles_list), dim=0)[0]
        upper_limit = torch.max(torch.stack(joint_angles_list), dim=0)[0]
        
        # Interpolate based on ratio
        ratio = config.ratio
        joint_angle = lower_limit + ratio * (upper_limit - lower_limit)
        
        print(f"Rendering with joint angle configuration (ratio {ratio}):")
        print(joint_angle)
    else:
        print("No joint angles found (static model). Rendering default configuration.")
        joint_angle = torch.tensor([], device=evaluator.gaussians.get_xyz.device)

    # Add meshes to scene
    # Static mesh
    static_mesh = evaluator.get_mesh_from_gaussians(static_gaussians, joint_angle)
    static_mesh.paint_uniform_color(rgbs[0])
    static_mesh.compute_vertex_normals()
    widget.scene.add_geometry("static_mesh", static_mesh, mat)
    
    # Dynamic meshes
    for j, dynamic_gaussian in enumerate(dynamic_gaussian_list):
        dynamic_mesh = evaluator.get_mesh_from_gaussians(dynamic_gaussian, joint_angle)
        dynamic_mesh.paint_uniform_color(rgbs[j+1])
        dynamic_mesh.compute_vertex_normals()
        widget.scene.add_geometry(f"dynamic_mesh{j}", dynamic_mesh, mat)

    # Render image
    img = widget.render_to_image()
    
    # Save image
    output_path = config.output_path
    o3d.io.write_image(output_path, img)
    print(f"Image saved to {output_path}")

if __name__ == "__main__":
    parser = ArgumentParser(description="Render custom view script")
    
    # Custom arguments for this script
    parser.add_argument("--ratio", type=float, default=0.5, help="Interpolation ratio between lower and upper limits (0.0 to 1.0)")
    parser.add_argument("--cam_pos", type=float, nargs=3, default=[-0.5, -0.3, 0.6], help="Camera position x y z")
    parser.add_argument("--cam_lookat", type=float, nargs=3, default=[0.0, 0.0, 0.0], help="Camera lookat x y z")
    parser.add_argument("--res", type=int, nargs=2, default=[1280, 960], help="Resolution width height")
    parser.add_argument("--output_path", type=str, default="custom_render.png", help="Output image path")
    
    # Standard arguments
    parser.add_argument("--model_path", type=str, required=True, help="Path to the model")
    
    args = get_combined_args(parser)
    
    # Create config object from args, including those needed by Evaluator
    config = RenderConfig(
        model_path=args.model_path,
        white_background=getattr(args, 'white_background', True),
        sh_degree=getattr(args, 'sh_degree', 3),
        ratio=args.ratio,
        cam_pos=args.cam_pos,
        cam_lookat=args.cam_lookat,
        res=args.res,
        output_path=args.output_path
    )
    
    main(config)