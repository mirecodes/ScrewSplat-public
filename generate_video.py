import numpy as np
import argparse
import os
import torch
import cv2
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
    num_frames: int = 60
    camera_idx: int = 0
    fps: int = 30
    
    # Output settings
    output_dir: str = 'datasets/video_generation'
    verbose: bool = True

    # Optional overrides (if None, use values from config file)
    # You can add more fields here if you want to override specific config values programmatically

def generate_video(config: VideoGenerationConfig):
    # load object infos
    object_infos = OmegaConf.load('configs/object_video_infos.yml')

    # load main config
    cfg = OmegaConf.load(config.config_path)

    # object information
    object_classes = cfg.object_classes

    # camera poses
    camera_info = cfg.camera_info
    radius = camera_info['radius']
    num_phi = camera_info['num_phi']
    phi_range = np.array(camera_info['phi_range']) / 180 * np.pi
    num_theta = camera_info['num_theta']
    theta_range = np.array(camera_info['theta_range']) / 180 * np.pi	

    # camera intrinsics
    camera_intr = cfg.camera_intr

    # camera poses
    camera_poses = get_camera_poses(
        num_phi=num_phi,
        phi_range=phi_range,
        num_theta=num_theta,
        theta_range=theta_range,
        radius=radius
    )
    
    # Select specific camera pose
    if config.camera_idx >= len(camera_poses):
        print(f"[WARNING] Camera index {config.camera_idx} out of range. Using 0.")
        selected_camera_pose = camera_poses[0:1]
    else:
        selected_camera_pose = camera_poses[config.camera_idx:config.camera_idx+1]

    # rendering information
    render_info = cfg.render_info
    blender_root = render_info['blender_root']

    # dataset information
    dataset_info = cfg.dataset_info
    offset = dataset_info['offset']
    
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

        # Generate interpolation steps (linear)
        alphas = torch.linspace(0, 1, config.num_frames)
        
        thetas = []
        for alpha in alphas:
            theta = limits[:, 0] + alpha * (limits[:, 1] - limits[:, 0])
            thetas.append(theta)
        
        # Create output directory for video frames
        # Ensure model_id is a string to avoid TypeError in os.path.join
        video_dir = os.path.join(
            config.output_dir,
            category,
            str(model_id)
        )
        os.makedirs(video_dir, exist_ok=True)
        
        articulated_object.dir_save = video_dir
        
        print(f"[INFO] Generating {config.num_frames} frames in {video_dir}...")
        
        frame_paths = []
        
        for i, theta in enumerate(thetas):
            folder_name = f'frame_{i:03d}'
            
            if config.verbose:
                print(f"Rendering frame {i}/{config.num_frames}")
                
            # We only render for the selected camera pose
            articulated_object.generate(
                selected_camera_pose, theta, split='video', 
                folder_name=folder_name, shadow_on=shadow_on, verbose=config.verbose)
            
            # Collect image path for video creation
            img_path = os.path.join(video_dir, folder_name, 'images', 'image_000.png')
            frame_paths.append(img_path)

        # Create Video from frames
        if frame_paths:
            first_frame = cv2.imread(frame_paths[0])
            if first_frame is not None:
                height, width, layers = first_frame.shape
                video_path = os.path.join(video_dir, 'output_video.mp4')
                
                # Define codec and create VideoWriter
                fourcc = cv2.VideoWriter_fourcc(*'mp4v') 
                video = cv2.VideoWriter(video_path, fourcc, config.fps, (width, height))
                
                print(f"[INFO] Encoding video to {video_path}...")
                for path in frame_paths:
                    frame = cv2.imread(path)
                    if frame is not None:
                        video.write(frame)
                    else:
                        print(f"[WARNING] Could not read frame {path}")
                
                video.release()
                print("[INFO] Video generation complete.")
            else:
                print("[ERROR] Could not read the first frame to initialize video writer.")

if __name__ == '__main__':
    # You can modify the configuration here directly
    config = VideoGenerationConfig(
        config_path='configs/gen_video_config.yml',
        num_frames=60,
        camera_idx=0,
        fps=30,
        verbose=True
    )
    
    # Or override with command line arguments if needed, but primarily controlled by dataclass above
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--num_frames', type=int, help='Number of frames')
    parser.add_argument('--camera_idx', type=int, help='Camera index')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    # Update config from args if provided
    if args.config: config.config_path = args.config
    if args.num_frames: config.num_frames = args.num_frames
    if args.camera_idx is not None: config.camera_idx = args.camera_idx
    if args.verbose: config.verbose = True

    generate_video(config)