import torch
import os
from gaussian_renderer import ScrewGaussianModel
import numpy as np
from gaussian_renderer import render_with_screw
from scene import ScrewGaussianModel
from PIL import Image
from typing import NamedTuple
from utils.graphics_utils import getWorld2View2
from articulated_object.utils import exp_se3
from utils.tsdf_fusion import TSDFVolume
import open3d as o3d
from tqdm import tqdm

class MiniCam(NamedTuple):
    FoVx: np.array
    FoVy: np.array
    image_width: int
    image_height: int
    cx: np.array
    cy: np.array
    art_idx: int
    world_view_transform: torch.tensor
    

class Evaluator:

    def __init__(self, args):
        
        # load model
        self.load_trained_model(args)

        # camera setting
        self.get_cameras()

        # tsdf parameters
        self.z_far = 2.
        
    @torch.no_grad()
    def render(self, gaussians, joint_angle, camera):
        render_pkg = render_with_screw(
            camera, gaussians, None, self.bg, 
            use_trained_exp=None, separate_sh=None, activate_screw_thres=None,
            desired_joint_angle=joint_angle,
            )
        image = torch.clamp(render_pkg["render"], 0.0, 1.0).permute(1, 2, 0).detach().cpu().numpy()
        return image # (480, 640, 3)

    @torch.no_grad()
    def render_depth(self, gaussians, joint_angle, camera):
        render_pkg = render_with_screw(
            camera, gaussians, None, self.bg, 
            use_trained_exp=None, separate_sh=None, activate_screw_thres=None,
            desired_joint_angle=joint_angle,
            render_mode='D'
            )
        depth_image = render_pkg["render"][0].detach().cpu().numpy()
        return depth_image # (480, 640)

    @torch.no_grad()
    def get_single_rgb_from_gaussians(self, gaussians, joint_angle, plot_idx=0):
        # Check if plot_idx is within the range of self.cameras
        if plot_idx >= len(self.cameras):
             # If plot_idx is out of range, it might be a custom camera added externally
             # In make_custom_videos.py, we append to evaluator.scene.getTestCameras()
             # But here we are using self.cameras.
             # We need to check if there's a way to access the custom camera.
             # However, make_custom_videos.py tries to append to evaluator.scene.getTestCameras()
             # which doesn't seem to exist in this Evaluator class.
             # Instead, make_custom_videos.py should append to evaluator.cameras
             pass

        if plot_idx < len(self.cameras):
            camera = self.cameras[plot_idx]
        else:
            # Fallback or error handling if index is still out of bounds
            # For now, let's assume the user appended to self.cameras in make_custom_videos.py
            # If not, this will raise an IndexError, which is expected if the camera wasn't added.
            camera = self.cameras[plot_idx]

        rgb = self.render(gaussians, joint_angle, camera)
        rgb = (rgb*255).astype(np.uint8)
        return rgb

    @torch.no_grad()
    def get_rgbs_from_gaussians(self, gaussians, joint_angle):
        rgb_list = []
        for camera in tqdm(self.cameras, desc="rgb rendering..."):
            rgb = self.render(gaussians, joint_angle, camera)
            rgb = (rgb*255).astype(np.uint8)
            rgb_list.append(rgb)
        return rgb_list

    @torch.no_grad()
    def get_mesh_from_gaussians(self, gaussians, joint_angle, resolution=64, num_points=2048):
        mn, mx = self.get_bbox(gaussians, joint_angle)
        size = mx - mn
        vol_bnds = np.stack([mn-0.1*size, mx+0.1*size], axis=-1)
        voxel_size = (mx-mn).min() / resolution
        mesh = self.tsdf_fusion(gaussians, joint_angle, vol_bnds, voxel_size)
        return mesh

    @torch.no_grad()
    def get_uniform_pc_from_gaussians(self, gaussians, joint_angle, resolution=64, num_points=2048):
        mn, mx = self.get_bbox(gaussians, joint_angle)
        size = mx - mn
        vol_bnds = np.stack([mn-0.1*size, mx+0.1*size], axis=-1)
        voxel_size = (mx-mn).min() / resolution
        mesh = self.tsdf_fusion(gaussians, joint_angle, vol_bnds, voxel_size)
        uniform_pc = mesh.sample_points_uniformly(number_of_points=num_points)
        return uniform_pc
    
    @torch.no_grad()
    def tsdf_fusion(self, gaussians, joint_angle, vol_bnds, voxel_size):
        
        # tsdf initialize
        tsdf = TSDFVolume(vol_bnds, voxel_size, use_gpu=True)
        
        # fusion
        for camera, camera_pose in zip(self.cameras, self.camera_poses):
            depth_img = self.render_depth(gaussians, joint_angle, camera)
            depth_img[np.where(depth_img == 0)] = self.z_far
            color_img = np.ones((depth_img.shape[0], depth_img.shape[1], 3)) * 0.7
            tsdf.integrate(color_img, depth_img, self.intrinsic, camera_pose, obs_weight=1.)
        
        # get mesh
        verts, faces, _, _ = tsdf.get_mesh()
        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(verts)
        mesh.triangles = o3d.utility.Vector3iVector(faces)
        
        return mesh
    
    @torch.no_grad()
    def get_bbox(self, gaussians, joint_angle):
        xyzs = self.get_posed_pc(gaussians, joint_angle)

        # [수정] 점이 하나도 없으면 더미(0) 좌표를 반환하여 에러 방지
        if xyzs.shape[0] == 0:
            import numpy as np
            return np.zeros(3), np.zeros(3)

        mn, mx = xyzs.amin(0), xyzs.amax(0)
        return mn.detach().cpu().numpy(), mx.detach().cpu().numpy()
    
    @torch.no_grad()
    def get_posed_pc(self, gaussians, joint_angle):
        screw_confs = gaussians.get_screw_confs # [N_s, ]
        part_indices = gaussians.get_part_indices # [N, N_s+1]
        
        # screw transforms
        screws = gaussians.get_screws
        screws = screws * joint_angle.unsqueeze(1) # [N_s, 6]
        screw_transforms = exp_se3(screws) # [N_s, 4, 4]
        screw_transforms = torch.cat(
            (torch.eye(4).unsqueeze(0).to(screw_transforms), screw_transforms), 
            dim=0
        ) # [N_s+1, 4, 4]
        screw_rotations = screw_transforms[:, :3, :3] # [N_s+1, 3, 3]
        screw_translations = screw_transforms[:, :3, 3] # [N_s+1, 3]
        screw_confs = torch.cat(
            (torch.tensor([1.0]).to(screw_confs), screw_confs), 
            dim=0
        ) # [N_s+1, ]

        n_screws = screws.shape[0]
        # augmented gaussians
        n_gaussians = gaussians.get_xyz.shape[0]
        augmented_means3D = (
            screw_rotations.unsqueeze(0).repeat(n_gaussians, 1, 1, 1)
            @ gaussians.get_xyz.unsqueeze(1).repeat(1, n_screws+1, 1).unsqueeze(-1)
            + screw_translations.unsqueeze(0).repeat(n_gaussians, 1, 1).unsqueeze(-1)
        ).squeeze(-1) # [N, N_s+1, 3]
        augmented_opacity = (
            gaussians.get_opacity.repeat(1, n_screws+1) 
            * part_indices 
            * screw_confs.unsqueeze(0).repeat(n_gaussians, 1)
        )# [N, N_s+1]

        # pre-filter low opacity gaussians to save computation
        mask = (augmented_opacity > 0.005).squeeze(1)
        xyzs = augmented_means3D[mask]
        return xyzs
    
    @torch.no_grad()
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
        self.gaussians.restore(model_params)

        # get joint limit
        joint_angles = self.gaussians.get_joint_angles
        lower_limit = torch.min(torch.stack(joint_angles), dim=0)[0]
        upper_limit = torch.max(torch.stack(joint_angles), dim=0)[0]
        self.joint_limits = torch.cat(
            (lower_limit.unsqueeze(-1), upper_limit.unsqueeze(-1)), dim=1)

    def get_cameras(self):
        
        # load extrinsics and intrinsics
        intrinsic = np.load(os.path.join('cameras', 'intrinsic.npy'))
        fx = intrinsic[0, 0]
        fy = intrinsic[1, 1]
        cx = intrinsic[0, 2]
        cy = intrinsic[1, 2]
        self.intrinsic = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])

        # load extrinsics
        extrinsic_names = os.listdir(os.path.join('cameras', 'extrinsics'))
        extrinsic_names.sort()

        # process camera info
        self.cameras = []
        self.camera_poses = []
        for idx, name in enumerate(extrinsic_names):

            # get camera to world frame
            extrinsic = np.load(os.path.join('cameras', 'extrinsics', name))
            self.camera_poses.append(np.linalg.inv(extrinsic))

            # get the world-to-camera transform and set R, T
            R = np.transpose(extrinsic[:3,:3])  # R is stored transposed due to 'glm' in CUDA code
            T = extrinsic[:3, 3]

            # fov
            FoVx = 2 * np.arctan(int(cx * 2) / (2 * fy))
            FoVy = 2 * np.arctan(int(cy * 2) / (2 * fx))

            # world view transform
            world_view_transform = torch.tensor(
                getWorld2View2(R, T, np.array([0.0, 0.0, 0.0]), 1.0)).transpose(0, 1).cuda()

            self.cameras.append(
                MiniCam(
                    FoVx=FoVx, FoVy=FoVy, image_width=int(cx * 2),
                    image_height=int(cy * 2), cx=cx, cy=cy, art_idx=0,
                    world_view_transform=world_view_transform
                )
            )