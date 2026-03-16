import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import torch
from argparse import ArgumentParser
from arguments import get_combined_args
import numpy as np
import os
import open3d as o3d
import open3d.visualization.rendering as rendering
from copy import deepcopy
from evaluator import Evaluator
import cv2
import imageio.v2 as imageio
from tqdm import tqdm
import math
from dataclasses import dataclass
from typing import Optional, List

# --- Dataclass for Image Configuration ---
@dataclass
class ImageConfig:
    width: int = 1920
    height: int = 1080
    cam_pos: Optional[List[float]] = None
    cam_lookat: Optional[List[float]] = None
    fov: float = 45.0
    white_background: bool = False


# --- Helper Math Functions for Custom Camera ---
def getProjectionMatrix(znear, zfar, fovX, fovY):
    tanHalfFovY = math.tan((fovY / 2))
    tanHalfFovX = math.tan((fovX / 2))

    top = tanHalfFovY * znear
    bottom = -top
    right = tanHalfFovX * znear
    left = -right

    P = torch.zeros(4, 4)

    z_sign = 1.0

    P[0, 0] = 2.0 * znear / (right - left)
    P[1, 1] = 2.0 * znear / (top - bottom)
    P[0, 2] = (right + left) / (right - left)
    P[1, 2] = (top + bottom) / (top - bottom)
    P[3, 2] = z_sign
    P[2, 2] = z_sign * zfar / (zfar - znear)
    P[2, 3] = -(zfar * znear) / (zfar - znear)
    return P


def getWorld2View2(R, t, translate=np.array([.0, .0, .0]), scale=1.0):
    Rt = np.zeros((4, 4))
    Rt[:3, :3] = R.transpose()
    Rt[:3, 3] = t
    Rt[3, 3] = 1.0

    C2W = np.linalg.inv(Rt)
    cam_center = C2W[:3, 3]
    cam_center = (cam_center + translate) * scale
    C2W[:3, 3] = cam_center
    Rt = np.linalg.inv(C2W)
    return np.float32(Rt)


class MiniCam:
    def __init__(self, width, height, fovy, fovx, znear, zfar, world_view_transform, full_proj_transform):
        self.image_width = width
        self.image_height = height
        self.FoVy = fovy
        self.FoVx = fovx
        self.znear = znear
        self.zfar = zfar
        self.world_view_transform = world_view_transform
        self.full_proj_transform = full_proj_transform
        view_inv = torch.inverse(self.world_view_transform)
        self.camera_center = view_inv[3][:3]


def create_custom_camera(width, height, position, lookat, up=np.array([0, 0, 1]), fov=45.0):
    # Calculate Forward, Right, Up vectors
    front = lookat - position
    front = front / np.linalg.norm(front)

    right = np.cross(front, up)
    right = right / np.linalg.norm(right)

    new_up = np.cross(right, front)
    new_up = new_up / np.linalg.norm(new_up)

    # Construct Rotation Matrix (View Matrix Rotation part)
    # Open3D/OpenGL convention: Camera looks down -Z
    # But 3DGS often uses COLMAP convention. We construct R such that:
    # R * world_point + t = camera_point

    R = np.zeros((3, 3))
    R[0, :] = right
    R[1, :] = -new_up  # Often Y is down in image space for CV, but let's stick to standard GL first
    R[2, :] = front  # Camera looks down +Z (OpenCV convention)

    # Translation
    t = -np.dot(R, position)

    # Fov to Radians
    fovy = math.radians(fov)
    fovx = 2 * math.atan(math.tan(fovy / 2) * (width / height))

    znear = 0.01
    zfar = 100.0

    # Create Matrices
    world_view_transform = torch.tensor(getWorld2View2(R.T, t)).transpose(0, 1).cuda()
    projection_matrix = getProjectionMatrix(znear=znear, zfar=zfar, fovX=fovx, fovY=fovy).transpose(0, 1).cuda()
    full_proj_transform = (world_view_transform.unsqueeze(0).bmm(projection_matrix.unsqueeze(0))).squeeze(0)

    return MiniCam(width, height, fovy, fovx, znear, zfar, world_view_transform, full_proj_transform)


# --- End Helper Functions ---

# for background composition
def composite_on_bg(img, white_bg=True):
    if img.shape[2] == 4:
        alpha = img[:, :, 3] / 255.0
        rgb = img[:, :, :3]
        if white_bg:
            bg = np.ones_like(rgb, dtype=np.uint8) * 255
        else:
            bg = np.zeros_like(rgb, dtype=np.uint8)
        blended = (alpha[..., None] * rgb + (1 - alpha[..., None]) * bg).astype(np.uint8)
        return blended
    else:
        return img


# main
def main(args):
    # Override args with config
    args.white_background = IMAGE_CONFIG.white_background

    # Parse q_values
    if args.q_values is None:
        raise ValueError("q_values must be provided, e.g., --q_values '0.5,1.2'")
    
    try:
        q_values_list = [float(q.strip()) for q in args.q_values.split(',')]
        q_target = torch.tensor(q_values_list, dtype=torch.float32, device="cuda")
    except Exception as e:
        raise ValueError(f"Failed to parse q_values. Ensure it's a comma-separated list of numbers. E.g. --q_values '0.5,1.2'. Error: {e}")

    # paths
    evaluator = Evaluator(args)

    # ensure q_target dimension matches Number of dynamic parameters
    actual_joints = evaluator.gaussians.get_joint_angles[0].shape[-1]
    if q_target.shape[0] != actual_joints:
         print(f"Warning: Expected {actual_joints} joints based on model, but got {q_target.shape[0]} in q_values.")
         # Padding or truncating based on the model if needed, but for now we expect a match or we reshape
         # Just creating one sample tensor of right shape:
         q_target = q_target[:actual_joints] if q_target.shape[0] > actual_joints else torch.cat([q_target, torch.zeros(actual_joints - q_target.shape[0], device="cuda")])
         print(f"Adjusted q_values to: {q_target.cpu().numpy()}")


    # image setting
    # Extract object name from model_path.
    # Typical path: output/.../{object_name}/{model_id}/...
    # We will just use the directory name two levels above the checkpoint UUID assuming typical structure, 
    # or just split path to find the appropriate name. 
    # Assuming path ends with: /{object_name}/{some_id}/sequential_steps.../{checkpoint_uuid}
    # Let's cleanly extract it using path properties or split.
    path_parts = os.path.normpath(args.model_path).split(os.sep)
    # The structure usually is output/<dataset_name>/<object_name>/... or output/<object_name>/...
    # We'll heuristic match or just take the 3rd to last dir if it has at least 3 parts
    if len(path_parts) >= 4:
         object_name = path_parts[-4] # e.g. foldingchair from output/pretrained/foldingchair/102255/sequential_steps.../uuid
    else:
         object_name = "unknown_object"
         
    output_dir = os.path.join('rendering', object_name)
    os.makedirs(output_dir, exist_ok=True)
    
    output_geometry_image = os.path.join(output_dir, 'geometry_custom.png')
    output_rgb_image = os.path.join(output_dir, 'rendered_rgb_custom.png')

    # colors
    rgbs = np.array([
        [128, 128, 128],  # static
        [0, 128, 255],    # moving 1
        [0, 255, 0],      # moving 2
        [255, 128, 0],    # moving 3
        [255, 0, 0],      # moving 4
        [128, 0, 128],    # moving 5
        [0, 255, 255],    # moving 6
        [255, 0, 255],    # moving 7
        [255, 255, 0],    # moving 8
        [0, 128, 128],    # moving 9
    ]) / 255

    # figure settings (Customizable)
    image_size = [IMAGE_CONFIG.width, IMAGE_CONFIG.height]

    # define ground plane
    a = 200.0
    plane = o3d.geometry.TriangleMesh.create_box(width=a, depth=0.05, height=a)
    plane.paint_uniform_color([1.0, 1.0, 1.0])
    plane.translate([-a / 2, -a / 2, -1.0])
    plane.compute_vertex_normals()
    mat_plane = rendering.MaterialRecord()
    mat_plane.shader = 'defaultLit'
    mat_plane.base_color = [1.0, 1.0, 1.0, 4.0]

    # object material
    mat = rendering.MaterialRecord()
    mat.shader = 'defaultLit'
    mat.base_color = [1.0, 1.0, 1.0, 0.9]

    # rendering camera info (Customizable)
    workspace_origin = np.array([0.0, 0.0, 0.0])

    if IMAGE_CONFIG.cam_pos is not None:
        camera_position = np.array(IMAGE_CONFIG.cam_pos)
    else:
        camera_position = workspace_origin + np.array([-0.5, -0.3, 0.6])

    if IMAGE_CONFIG.cam_lookat is not None:
        camera_lookat = np.array(IMAGE_CONFIG.cam_lookat)
    else:
        camera_lookat = workspace_origin

    print(f"Rendering with Camera Position: {camera_position}, LookAt: {camera_lookat}, Size: {image_size}")

    # draw voxel
    widget = o3d.visualization.rendering.OffscreenRenderer(
        image_size[0], image_size[1])
    widget.scene.camera.look_at(camera_lookat, camera_position, [0, 0, 1])

    # run
    light_dir = (0.3, -0.3, -0.9)
    widget.scene.add_geometry('plane', plane, mat_plane)
    widget.scene.set_lighting(widget.scene.LightingProfile.DARK_SHADOWS, light_dir)
    
    # Set background color based on config
    bg_color = [1.0, 1.0, 1.0, 1.0] if IMAGE_CONFIG.white_background else [0.0, 0.0, 0.0, 1.0]
    widget.scene.set_background(bg_color, image=None)


    # separate part-aware gaussians
    static_part_mask = evaluator.gaussians.get_part_indices[:, [0]] > 0.5
    dynamic_part_mask = evaluator.gaussians.get_part_indices[:, 1:] > 0.5
    static_gaussians = deepcopy(evaluator.gaussians)
    with torch.no_grad():
        static_gaussians._opacity = static_gaussians._opacity.detach()
        static_gaussians._opacity[~static_part_mask] = evaluator.gaussians.inverse_opacity_activation(
            torch.tensor(1e-4))
        dynamic_gaussian_list = []
        for i in range(dynamic_part_mask.shape[-1]):
            dynamic_gaussians = deepcopy(evaluator.gaussians)
            dynamic_gaussians._opacity[~dynamic_part_mask[:, [i]]] = evaluator.gaussians.inverse_opacity_activation(
                torch.tensor(1e-4))
            dynamic_gaussian_list.append(dynamic_gaussians)
    num_meshes = len(dynamic_gaussian_list)


    # --- Setup Custom Camera for RGB Rendering ---
    custom_cam = create_custom_camera(
        width=image_size[0],
        height=image_size[1],
        position=camera_position,
        lookat=camera_lookat,
        fov=IMAGE_CONFIG.fov
    )

    # Inject custom camera into evaluator's cameras list
    evaluator.cameras.append(custom_cam)
    custom_cam_idx = len(evaluator.cameras) - 1
    print(f"Successfully injected custom camera at index {custom_cam_idx}")

    print(f"Rendering frame for q_target: {q_target.cpu().numpy()}")

    # Render static mesh
    static_mesh = evaluator.get_mesh_from_gaussians(static_gaussians, q_target)
    static_mesh.paint_uniform_color(rgbs[0])
    static_mesh.compute_vertex_normals()
    widget.scene.add_geometry(f"static_mesh", static_mesh, mat)

    # Render dynamic meshes
    for j, dynamic_gaussian in enumerate(dynamic_gaussian_list):
        dynamic_mesh = evaluator.get_mesh_from_gaussians(dynamic_gaussian, q_target)
        color_idx = (j % (len(rgbs) - 1)) + 1
        dynamic_mesh.paint_uniform_color(rgbs[color_idx])
        dynamic_mesh.compute_vertex_normals()
        widget.scene.add_geometry(f"dynamic_mesh{j}", dynamic_mesh, mat)

    # Render mesh image (Geometry)
    img = widget.render_to_image()
    o3d.io.write_image(output_geometry_image, img)
    print(f"Saved Geometry Image to: {output_geometry_image}")

    # Render RGB image
    rgb = evaluator.get_single_rgb_from_gaussians(
        evaluator.gaussians, q_target, plot_idx=custom_cam_idx)
    
    imageio.imwrite(output_rgb_image, rgb)
    print(f"Saved RGB Image to: {output_rgb_image}")


# Instantiate the config - User can modify values here
IMAGE_CONFIG = ImageConfig(
    width=1920,
    height=1080,
    cam_pos=[-3.0, 3.0, 3.0],  # e.g. [0.5, 0.5, 0.5]
    cam_lookat=[0, 0, 0], # e.g. [0.0, 0.0, 0.0]
    fov=45.0,
    white_background=False # Set to False for black background
)

if __name__ == "__main__":
    parser = ArgumentParser(description="Testing script parameters")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the trained model output directory.")
    parser.add_argument("--q_values", type=str, required=True, help="Comma-separated list of target joint q_values, e.g., '0.5' or '0.5,1.2'.")

    args = get_combined_args(parser)

    main(args)
