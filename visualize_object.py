import numpy as np
import argparse
import torch
from omegaconf import OmegaConf
from articulated_object import ArticulatedObject
from articulated_object.get_camera_poses import get_camera_poses

if __name__ == '__main__':

	# load object infos
	object_infos = OmegaConf.load('configs/object_infos.yml')

	# argparse
	parser = argparse.ArgumentParser()
	parser.add_argument('--config', type=str, default='configs/vis_obj_config.yml')
	args, unknown = parser.parse_known_args()
	cfg = OmegaConf.load(args.config)

	# object information
	object_class = cfg.object_class
	model_id = object_infos[object_class].model_id
	scale = object_infos[object_class].scale
	joint_indices = object_infos[object_class].get('joint_indices', None)
	joint_limits = object_infos[object_class].get('joint_limits', None)

	# load articulated object
	articulated_object = ArticulatedObject(
		model_id, scale=scale)

	# articulation
	joint_angle = cfg.joint_angle
	
	# Handle custom joint limits and indices
	if joint_indices is not None or joint_limits is not None:
		# Get default limits
		default_limits = torch.stack([values['limit'] 
			for _, values in articulated_object.S_screws.items()])
		
		# Initialize target limits with default
		target_limits = default_limits.clone()
		
		# Apply custom limits if provided
		if joint_limits is not None:
			custom_limits = torch.tensor(joint_limits)
			if custom_limits.dim() == 1:
				custom_limits = custom_limits.unsqueeze(0)
			
			if joint_indices is None:
				# Apply to all joints if no indices specified
				if len(custom_limits) == 1:
					target_limits = custom_limits.repeat(len(articulated_object.S_screws), 1)
				else:
					target_limits = custom_limits
			else:
				# Apply to specific indices
				if len(custom_limits) == 1 and len(joint_indices) > 1:
					custom_limits = custom_limits.repeat(len(joint_indices), 1)
				
				for idx, limit in zip(joint_indices, custom_limits):
					target_limits[idx] = limit

		# Calculate theta based on joint_angle (0.0 to 1.0)
		# Interpolate between min and max limits
		thetas = target_limits[:, 0] + joint_angle * (target_limits[:, 1] - target_limits[:, 0])
		
		# If joint_indices is specified, only move those joints
		# For others, keep them at min limit (or 0 if that's preferred, but usually min limit is rest pose)
		if joint_indices is not None:
			final_thetas = default_limits[:, 0].clone() # Start with default min limits (rest pose)
			for i in joint_indices:
				final_thetas[i] = thetas[i]
			thetas = final_thetas
			
	else:
		# Fallback to simple scalar application if no custom config
		thetas = torch.ones(len(articulated_object.S_screws.keys())) * joint_angle
		# Map 0-1 to actual limits if needed, but original code seemed to take raw angle or ratio?
		# The original code took `joint_angle` and multiplied by 1 vector.
		# If `joint_angle` in config is meant to be a ratio (0~1), we should map it.
		# However, looking at previous code, it just passed `joint_angle` directly.
		# If `joint_angle` is raw radian/meter value, then `thetas` is correct.
		# But if `joint_angle` is 0.2 (from config), it might be ratio.
		# Let's assume it's a ratio if it's small, or check how it was used.
		# In generate_data.py, it interpolates. Here we should probably do the same if we want consistency.
		# But to preserve original behavior for non-configured objects:
		# The original code: `thetas = torch.ones(...) * theta`
		# If the user inputs 0.2, it sets all joints to 0.2 rad/m.
		pass

	# camera information
	camera_info = cfg.camera_info
	view_name = camera_info['view_name']
	radius = camera_info['radius']
	num_phi = camera_info['num_phi']
	phi_range = np.array(camera_info['phi_range']) / 180 * np.pi
	num_theta = camera_info['num_theta']
	theta_range = np.array(camera_info['theta_range']) / 180 * np.pi	

	# camera poses
	camera_poses = get_camera_poses(
		num_phi=num_phi,
		phi_range=phi_range,
		num_theta=num_theta,
		theta_range=theta_range,
		radius=radius
	)

	# interactive visualizer
	articulated_object.visualize_object(
		camera_poses=camera_poses, theta=thetas)