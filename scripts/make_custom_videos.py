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

# --- Dataclass for Video Configuration ---
@dataclass
class VideoConfig:
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
    args.white_background = VIDEO_CONFIG.white_background

    # paths
    evaluator = Evaluator(args)

    # video setting
    temp_path = 'temp_custom'
    os.makedirs(temp_path, exist_ok=True)
    output_geometry_video = 'geometry_custom.mp4'
    output_rgb_video = 'rendered_rgb_custom.mp4'
    fps = 30

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
    image_size = [VIDEO_CONFIG.width, VIDEO_CONFIG.height]

    # define ground plane
    a = 200.0
    plane = o3d.geometry.TriangleMesh.create_box(width=a, depth=0.05, height=a)
    plane.paint_uniform_color([1.0, 1.0, 1.0])
    plane.translate([-a / 2, -a / 2, -1.0])
    plane.compute_vertex_normals()
    mat_plane = rendering.MaterialRecord()
    mat_plane.shader = 'defaultLit'
    mat_plane.base_color = [1.0, 1.0, 1.0, 4.0]
    mat_gripper = rendering.MaterialRecord()
    mat_gripper.shader = 'defaultLitTransparency'
    mat_gripper.base_color = [1.0, 1.0, 1.0, 0.8]
    mat_before = rendering.MaterialRecord()
    mat_before.shader = 'defaultLitTransparency'
    mat_before.base_color = [1.0, 1.0, 1.0, 0.4]

    # object material
    mat = rendering.MaterialRecord()
    mat.shader = 'defaultLit'
    mat.base_color = [1.0, 1.0, 1.0, 0.9]

    # rendering camera info (Customizable)
    # Default fallback if not provided
    workspace_origin = np.array([0.0, 0.0, 0.0])

    if VIDEO_CONFIG.cam_pos is not None:
        camera_position = np.array(VIDEO_CONFIG.cam_pos)
    else:
        camera_position = workspace_origin + np.array([-0.5, -0.3, 0.6])

    if VIDEO_CONFIG.cam_lookat is not None:
        camera_lookat = np.array(VIDEO_CONFIG.cam_lookat)
    else:
        camera_lookat = workspace_origin

    print(f"Rendering with Camera Position: {camera_position}, LookAt: {camera_lookat}, Size: {image_size}")

    # draw voxel
    widget = o3d.visualization.rendering.OffscreenRenderer(
        image_size[0], image_size[1])
    widget.scene.camera.look_at(camera_lookat, camera_position, [0, 0, 1])
    # widget.scene.add_geometry(f"arrow", arrow, mat)

    # run
    light_dir = (0.3, -0.3, -0.9)
    widget.scene.add_geometry('plane', plane, mat_plane)
    widget.scene.set_lighting(widget.scene.LightingProfile.DARK_SHADOWS, light_dir)
    
    # Set background color based on config
    bg_color = [1.0, 1.0, 1.0, 1.0] if VIDEO_CONFIG.white_background else [0.0, 0.0, 0.0, 1.0]
    widget.scene.set_background(bg_color, image=None)

    # load screws
    arrow_scale = 0.3
    cylinder_radius = 0.02
    cone_radius = 0.06
    cylinder_height = 1.2
    cone_height = 0.2
    arrows = []
    for i in range(len(evaluator.gaussians.get_screws)):

        # screw parameters
        w = evaluator.gaussians.get_screws[i, :3].detach().cpu().numpy()
        q = evaluator.gaussians._screws[i, 3:].detach().cpu().numpy()
        v = evaluator.gaussians.get_screws[i, 3:].detach().cpu().numpy()

        # revolute
        if np.linalg.norm(w) > 0.1:
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
            arrow.paint_uniform_color([0.9, 0.0, 0.0])

        # prismatic
        else:
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
            arrow.paint_uniform_color([0.0, 0.0, 0.9])

        # append screw mesh
        arrows.append(arrow)

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

    # thetas
    steps = 30
    lower_limit = torch.min(torch.stack(evaluator.gaussians.get_joint_angles), dim=0)[0]
    upper_limit = torch.max(torch.stack(evaluator.gaussians.get_joint_angles), dim=0)[0]
    weights = torch.linspace(
        0, 1, steps,
        device=lower_limit.device,
        dtype=lower_limit.dtype
    ).view(-1, *[1] * lower_limit.dim())
    weights2 = torch.linspace(
        1, 0, steps,
        device=lower_limit.device,
        dtype=lower_limit.dtype
    ).view(-1, *[1] * lower_limit.dim())
    weights = torch.cat([weights, weights2], dim=0)
    thetas = lower_limit + weights * (upper_limit - lower_limit)

    # --- Setup Custom Camera for RGB Rendering ---
    custom_cam = create_custom_camera(
        width=image_size[0],
        height=image_size[1],
        position=camera_position,
        lookat=camera_lookat,
        fov=VIDEO_CONFIG.fov
    )

    # Inject custom camera into evaluator's cameras list
    evaluator.cameras.append(custom_cam)
    custom_cam_idx = len(evaluator.cameras) - 1
    print(f"Successfully injected custom camera at index {custom_cam_idx}")

    # load joint angle
    mesh_image_paths = []
    rgb_images_paths = []
    pbar = tqdm(
        total=len(thetas),
        desc=f"processing ... ",
        leave=False
    )
    for i, joint_angle in enumerate(thetas):

        if i >= 1:
            for j in range(num_meshes):
                widget.scene.remove_geometry(f"dynamic_mesh{j}")

        if i == 0:
            static_mesh = evaluator.get_mesh_from_gaussians(static_gaussians, joint_angle)
            static_mesh.paint_uniform_color(rgbs[0])
            static_mesh.compute_vertex_normals()
            widget.scene.add_geometry(f"static_mesh", static_mesh, mat)
        for j, dynamic_gaussian in enumerate(dynamic_gaussian_list):
            dynamic_mesh = evaluator.get_mesh_from_gaussians(dynamic_gaussian, joint_angle)
            # Use modulo to cycle through colors, skipping index 0 (static)
            color_idx = (j % (len(rgbs) - 1)) + 1
            dynamic_mesh.paint_uniform_color(rgbs[color_idx])
            dynamic_mesh.compute_vertex_normals()
            widget.scene.add_geometry(f"dynamic_mesh{j}", dynamic_mesh, mat)

        # render mesh image
        img = widget.render_to_image()
        image_path = os.path.join(temp_path, f'temp{i}_1.png')
        o3d.io.write_image(image_path, img)
        mesh_image_paths.append(image_path)

        # render rgb image
        # Use the injected custom camera index
        rgb = evaluator.get_single_rgb_from_gaussians(
            evaluator.gaussians, joint_angle, plot_idx=custom_cam_idx)

        image_path = os.path.join(temp_path, f'temp{i}_2.png')
        imageio.imwrite(image_path, rgb)
        rgb_images_paths.append(image_path)
        pbar.update(1)

    # close
    pbar.close()

    # Read first image to get size
    frame = cv2.imread(mesh_image_paths[0])
    height, width, _ = frame.shape

    # Define the video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or use 'XVID'
    video = cv2.VideoWriter(output_geometry_video, fourcc, fps, (width, height))

    # Write each frame
    for img_path in mesh_image_paths:
        img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
        img_rgb = composite_on_bg(img, VIDEO_CONFIG.white_background)
        video.write(img_rgb)

    # Read first image to get size
    frame = cv2.imread(rgb_images_paths[0])
    height, width, _ = frame.shape

    # Define the video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or use 'XVID'
    video = cv2.VideoWriter(output_rgb_video, fourcc, fps, (width, height))

    # Write each frame
    for img_path in rgb_images_paths:
        img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
        img_rgb = composite_on_bg(img, VIDEO_CONFIG.white_background)
        video.write(img_rgb)


# Instantiate the config - User can modify values here
VIDEO_CONFIG = VideoConfig(
    width=1920,
    height=1080,
    cam_pos=[-3.0, 0, 1.5],  # e.g. [0.5, 0.5, 0.5]
    cam_lookat=[0, 0, 0], # e.g. [0.0, 0.0, 0.0]
    fov=45.0,
    white_background=False # Set to False for black background
)

if __name__ == "__main__":
    parser = ArgumentParser(description="Testing script parameters")
    parser.add_argument("--model_path", type=str, required=True)

    args = get_combined_args(parser)

    main(args)
