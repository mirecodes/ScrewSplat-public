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

# for white background
def composite_on_white(img):
	if img.shape[2] == 4:
		alpha = img[:, :, 3] / 255.0
		rgb = img[:, :, :3]
		white_bg = np.ones_like(rgb, dtype=np.uint8) * 255
		blended = (alpha[..., None] * rgb + (1 - alpha[..., None]) * white_bg).astype(np.uint8)
		return blended
	else:
		return img

# main
def main(args):

	# paths
	evaluator = Evaluator(args)

	# video setting
	temp_path = 'temp'
	os.makedirs(temp_path, exist_ok=True)
	output_geometry_video = 'geometry.mp4'
	output_rgb_video = 'rendered_rgb.mp4'
	fps = 30

	# colors
	rgbs = np.array([
		[128,128,128], # static
		[0,128,255],   # moving 1
		[0,255,0],     # moving 2
		[255,128,0]    # moving 3
	])/255

	# figure settings
	image_size = [1280, 960]

	# define ground plane
	a = 200.0
	plane = o3d.geometry.TriangleMesh.create_box(width=a, depth=0.05, height=a)
	plane.paint_uniform_color([1.0, 1.0, 1.0])
	plane.translate([-a/2, -a/2, -1.0])
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

	# rendering camera info
	workspace_origin = np.array([0.0, 0.0, 0.0])
	camera_position = workspace_origin + np.array(
		[-0.5, -0.3, 0.6])
	camera_lookat = workspace_origin

	# draw voxel
	widget = o3d.visualization.rendering.OffscreenRenderer(
			image_size[0], image_size[1])
	widget.scene.camera.look_at(camera_lookat, camera_position, [0,0,1])
	# widget.scene.add_geometry(f"arrow", arrow, mat)

	# run
	light_dir = (0.3, -0.3, -0.9)
	widget.scene.add_geometry('plane', plane, mat_plane)
	widget.scene.set_lighting(widget.scene.LightingProfile.DARK_SHADOWS, light_dir)
	widget.scene.set_background([1.0, 1.0, 1.0, 1.0], image=None)

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
	static_part_mask = evaluator.gaussians.get_part_indices[:,[0]] > 0.5
	dynamic_part_mask = evaluator.gaussians.get_part_indices[:,1:] > 0.5
	static_gaussians = deepcopy(evaluator.gaussians)
	with torch.no_grad():
		static_gaussians._opacity = static_gaussians._opacity.detach()
		static_gaussians._opacity[~static_part_mask] = evaluator.gaussians.inverse_opacity_activation(torch.tensor(1e-4))
		dynamic_gaussian_list = []
		for i in range(dynamic_part_mask.shape[-1]):
			dynamic_gaussians  = deepcopy(evaluator.gaussians)
			dynamic_gaussians._opacity[~dynamic_part_mask[:,[i]]] = evaluator.gaussians.inverse_opacity_activation(torch.tensor(1e-4))
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
	).view(-1, *[1]*lower_limit.dim())
	weights2 = torch.linspace(
		1, 0, steps, 
		device=lower_limit.device, 
		dtype=lower_limit.dtype
	).view(-1, *[1]*lower_limit.dim())
	weights = torch.cat([weights, weights2], dim=0)
	thetas = lower_limit + weights * (upper_limit - lower_limit)

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
			dynamic_mesh.paint_uniform_color(rgbs[j+1])
			dynamic_mesh.compute_vertex_normals()
			widget.scene.add_geometry(f"dynamic_mesh{j}", dynamic_mesh, mat)

		# render mesh image
		img = widget.render_to_image()
		image_path = os.path.join(temp_path, f'temp{i}_1.png')
		o3d.io.write_image(image_path, img)
		mesh_image_paths.append(image_path)

		# render rgb image
		rgb = evaluator.get_single_rgb_from_gaussians(
			evaluator.gaussians, joint_angle, plot_idx=31)
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
		img_rgb = composite_on_white(img)
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
		img_rgb = composite_on_white(img)
		video.write(img_rgb)

if __name__ == "__main__":
	parser = ArgumentParser(description="Testing script parameters")
	parser.add_argument("--model_path", type=str)
	args = get_combined_args(parser)

	main(args)