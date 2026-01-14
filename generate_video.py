import numpy as np
import argparse
import os
import torch
import cv2
import shutil
from dataclasses import dataclass, field
from typing import List, Optional
from omegaconf import OmegaConf
from articulated_object.articulated_object_renderer import ArticulatedObjectRenderer
from articulated_object.get_camera_poses import get_camera_poses

@dataclass
class VideoGenerationConfig:
    # Configuration file path
    config_path: str = 'configs/gen_data_config.yml'
    
    # Video settings
    duration: float = 8.0  # seconds
    fps: int = 16
    
    # Output settings
    output_dir: str = 'datasets/video_generation'
    verbose: bool = True

def generate_video(config: VideoGenerationConfig):
    # load object infos
    object_infos = OmegaConf.load('configs/object_video_infos.yml')

    # load main config
    cfg = OmegaConf.load(config.config_path)

    # object information
    object_classes = cfg.object_classes

    # camera info from config
    camera_info = cfg.camera_info
    radius = camera_info['radius']
    
    # Override camera settings for 4 views (90 degree azimuth intervals)
    # Use mean elevation from config
    mean_phi = np.mean(camera_info['phi_range'])
    phi_range_rad = np.array([mean_phi, mean_phi]) / 180 * np.pi
    
    # 4 azimuth angles: -180, -90, 0, 90 (covering 360 degrees with 90 deg steps)
    theta_range_rad = np.array([-180, 90]) / 180 * np.pi
    
    # camera intrinsics
    camera_intr = cfg.camera_intr

    # Generate 4 camera poses
    camera_poses = get_camera_poses(
        num_phi=1,
        phi_range=phi_range_rad,
        num_theta=4,
        theta_range=theta_range_rad,
        radius=radius
    )
    
    print(f"[INFO] Generated {len(camera_poses)} camera poses for video generation.")

    # rendering information
    render_info = cfg.render_info
    blender_root = render_info['blender_root']

    # dataset information
    dataset_info = cfg.dataset_info
    offset = dataset_info['offset']
    
    # Calculate total frames
    total_frames = int(config.duration * config.fps)
    
    # data generation
    for object_class in object_classes:
        if config.verbose:
            print(f"[INFO] Processing object class: {object_class}")

        # object info
        category = object_class.split('-')[0]
        model_id = object_infos[object_class].model_id
        scale = object_infos[object_class].scale
        joint_indices = object_infos[object_class].get('joint_indices', None)
        joint_limits = object_infos[object_class].get('joint_limits', None)
        shadow_on = object_infos[object_class].get('shadow_on', False)

        # load articulated object
        articulated_object = ArticulatedObjectRenderer(
            model_id, category, blender_root, camera_intr, scale=scale)

        # Determine joint limits
        if (joint_indices is None) and (joint_limits is None):
            limits = torch.stack([values['limit'] 
                for _, values in articulated_object.articulated_object.S_screws.items()])
            limits[:, 0] += offset
            limits[:, 1] -= offset
        elif (joint_indices is not None) and (joint_limits is None):
            limits = torch.stack([values['limit']
                if i in joint_indices else torch.tensor([values['limit'][0], values['limit'][0]])
                for i, (_, values) in enumerate(articulated_object.articulated_object.S_screws.items())
            ])
        elif (joint_indices is None) and (joint_limits is not None):
            limits = torch.tensor(joint_limits)
            if limits.dim() == 1:
                limits = limits.unsqueeze(0)
            if len(limits) == 1 and len(articulated_object.articulated_object.S_screws) > 1:
                limits = limits.repeat(len(articulated_object.articulated_object.S_screws), 1)
        elif (joint_indices is not None) and (joint_limits is not None):
            custom_limits = torch.tensor(joint_limits)
            if custom_limits.dim() == 1:
                custom_limits = custom_limits.unsqueeze(0)
            
            if len(custom_limits) == 1 and len(joint_indices) > 1:
                custom_limits = custom_limits.repeat(len(joint_indices), 1)
            
            limit_map = {idx: limit for idx, limit in zip(joint_indices, custom_limits)}
            
            limits = torch.stack([
                limit_map[i] if i in joint_indices else torch.tensor([values['limit'][0], values['limit'][0]])
                for i, (_, values) in enumerate(articulated_object.articulated_object.S_screws.items())
            ])

        # Generate motion: min -> max
        alphas = torch.linspace(0, 1, total_frames)
        
        thetas = []
        for alpha in alphas:
            theta = limits[:, 0] + alpha * (limits[:, 1] - limits[:, 0])
            thetas.append(theta)
        
        # Create output directory for video frames
        video_base_dir = os.path.join(
            config.output_dir,
            category,
            str(model_id)
        )
        os.makedirs(video_base_dir, exist_ok=True)
        
        # Generate video for each camera view
        for view_idx, pose in enumerate(camera_poses):
            print(f"[INFO] Generating video for View {view_idx+1}/{len(camera_poses)}...")
            
            # Temporary directory for frames of this view
            view_frames_dir = os.path.join(video_base_dir, f'temp_frames_view_{view_idx}')
            articulated_object.dir_save = view_frames_dir
            
            frame_paths = []
            
            # Render frames
            for i, theta in enumerate(thetas):
                folder_name = f'frame_{i:03d}'
                
                if config.verbose and i % 10 == 0:
                    print(f"  Rendering frame {i}/{total_frames}")
                    
                # Render single frame
                # We pass a list containing only the current pose
                articulated_object.generate(
                    [pose], theta, split='video', 
                    folder_name=folder_name, shadow_on=shadow_on, verbose=False)
                
                # Collect image path
                img_path = os.path.join(view_frames_dir, folder_name, 'images', 'image_000.png')
                frame_paths.append(img_path)

            # Create Video
            if frame_paths:
                first_frame = cv2.imread(frame_paths[0])
                if first_frame is not None:
                    height, width, layers = first_frame.shape
                    video_path = os.path.join(video_base_dir, f'video_view_{view_idx}.mp4')
                    
                    # Define codec and create VideoWriter
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
                    video = cv2.VideoWriter(video_path, fourcc, config.fps, (width, height))
                    
                    print(f"  Encoding video to {video_path}...")
                    for path in frame_paths:
                        frame = cv2.imread(path)
                        if frame is not None:
                            video.write(frame)
                    
                    video.release()
                else:
                    print(f"[ERROR] Could not read the first frame for view {view_idx}.")
            
            # Cleanup temporary frames
            if os.path.exists(view_frames_dir):
                if config.verbose:
                    print(f"  Cleaning up temporary frames in {view_frames_dir}...")
                shutil.rmtree(view_frames_dir)

        print(f"[INFO] All videos generated for {object_class}.")

if __name__ == '__main__':
    # Default configuration
    config = VideoGenerationConfig(
        config_path='configs/gen_video_config.yml',
        duration=8.0,
        fps=24,
        verbose=True
    )
    
    # Command line overrides
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--duration', type=float, help='Video duration in seconds')
    parser.add_argument('--fps', type=int, help='Frames per second')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    if args.config: config.config_path = args.config
    if args.duration: config.duration = args.duration
    if args.fps: config.fps = args.fps
    if args.verbose: config.verbose = True

    generate_video(config)