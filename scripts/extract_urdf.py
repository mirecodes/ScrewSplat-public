import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import torch
import numpy as np
from argparse import ArgumentParser
from arguments import get_combined_args
from evaluator import Evaluator

def main(args):
    # Override settings to simple values if needed
    args.white_background = True

    # Extract object name from model_path.
    path_parts = os.path.normpath(args.model_path).split(os.sep)
    if len(path_parts) >= 4:
         object_name = path_parts[-4] # e.g. foldingchair from output/pretrained/foldingchair/102255/...
    else:
         object_name = "unknown_object"

    output_str = []
    urdf_lines = [
        '<?xml version="1.0" ?>',
        f'<robot name="{object_name}">',
        '  <link name="link_0">',
        '  </link>'
    ]
    
    def log(msg):
        print(msg)
        output_str.append(msg)

    log(f"Loading Evaluator for Model: {args.model_path}")
    evaluator = Evaluator(args)
    
    screws = evaluator.gaussians.get_screws.detach().cpu().numpy()
    n_screws = len(screws)
    screw_confs = evaluator.gaussians.get_screw_confs.detach().cpu().numpy()
    part_indices = evaluator.gaussians.get_part_indices.detach() > 0.5  # Softmax probabilities to boolean masks
    gaussians_xyz = evaluator.gaussians.get_xyz.detach().cpu().numpy()
    joint_limits = evaluator.joint_limits.detach().cpu().numpy() if hasattr(evaluator, 'joint_limits') else None

    log("\n" + "="*50)
    log(f"🔩 ScrewSplat Model Analysis: {n_screws} Screws Detected for {object_name}")
    log("="*50)
    
    # Base link (Part 0 -> static part)
    static_mask = part_indices[:, 0].cpu().numpy()
    if np.any(static_mask):
        static_pts = gaussians_xyz[static_mask]
        st_mn, st_mx = static_pts.min(axis=0), static_pts.max(axis=0)
        st_center = (st_mn + st_mx) / 2.0
    else:
        st_center = np.zeros(3)

    log(f"\n[ Link 0 ] Base Link (Static Part)")
    log(f"    • Center of BBox: {st_center.round(4)}")
    log(f"    • Points Count:   {np.sum(static_mask)}")

    # For each screw, the corresponding part is index `i + 1`
    for i in range(n_screws):
        w = screws[i, :3] # Direction
        q = screws[i, 3:6] # For revolute, q is origin.
        v = screws[i, 3:6] # For prismatic, v relates to translation velocity.
        conf = screw_confs[i]

        log(f"\n" + "-"*40)
        log(f"[ Joint {i+1} ]: connecting Link 0 to Link {i+1} (Confidence: {conf:.4f})")

        # Check type: Revolute if ||w|| > 0.1, Prismatic otherwise
        if np.linalg.norm(w) > 0.1:
            joint_type = "Revolute"
            urdf_type = "revolute"
            axis = w / np.linalg.norm(w)
            origin = q
            log(f"    • Type:   {joint_type}")
            log(f"    • Axis:   {axis.round(4)}")
            log(f"    • Origin: {origin.round(4)}")
        else:
            joint_type = "Prismatic"
            urdf_type = "prismatic"
            # In evaluator/screw logic, w = -v for purely translation, or v is translation axis.
            # Usually v is scaled direction
            v_norm = np.linalg.norm(v)
            if v_norm > 1e-6:
                axis = -v / v_norm  # Because the visualization mesh logic uses -v as axis
            else:
                axis = np.zeros(3)
            origin = np.zeros(3)
            # Origin is generally 0,0,0 (undefined for pure prismatic in space, but just an axis)
            log(f"    • Type:   {joint_type}")
            log(f"    • Axis:   {axis.round(4)}")
            log(f"    • Origin: [ undefined ] (Pure Translation)")

        # Link information
        part_mask = part_indices[:, i + 1].cpu().numpy()
        pts_count = np.sum(part_mask)
        if pts_count > 0:
            link_pts = gaussians_xyz[part_mask]
            mn, mx = link_pts.min(axis=0), link_pts.max(axis=0)
            center = (mn + mx) / 2.0
        else:
            center = np.zeros(3)
            
        log(f"\n[ Link {i+1} ] (Driven by Joint {i+1})")
        log(f"    • Center of BBox: {center.round(4)}")
        log(f"    • Points Count:   {pts_count}")

        # Add to URDF
        axis_str = f"{axis[0]:.4f} {axis[1]:.4f} {axis[2]:.4f}"
        origin_str = f"{origin[0]:.4f} {origin[1]:.4f} {origin[2]:.4f}"
        low = joint_limits[i, 0] if joint_limits is not None else -1.57
        high = joint_limits[i, 1] if joint_limits is not None else 1.57
        
        urdf_lines.append(f'  <joint name="joint_{i+1}" type="{urdf_type}">')
        urdf_lines.append(f'    <parent link="link_0"/>')
        urdf_lines.append(f'    <child link="link_{i+1}"/>')
        urdf_lines.append(f'    <origin xyz="{origin_str}" rpy="0 0 0"/>')
        urdf_lines.append(f'    <axis xyz="{axis_str}"/>')
        urdf_lines.append(f'    <limit lower="{low:.4f}" upper="{high:.4f}" effort="10.0" velocity="1.0"/>')
        urdf_lines.append(f'  </joint>')
        urdf_lines.append(f'  <link name="link_{i+1}">')
        urdf_lines.append(f'  </link>')

    # Output to file
    translate_dir = os.path.join("translate", object_name)
    os.makedirs(translate_dir, exist_ok=True)
    
    # Text Analysis
    output_txt_path = os.path.join(translate_dir, "urdf_analysis.txt")
    with open(output_txt_path, "w") as f:
        f.write("\n".join(output_str))
    
    # URDF XML
    urdf_lines.append('</robot>')
    output_urdf_path = os.path.join(translate_dir, f"{object_name}.urdf")
    with open(output_urdf_path, "w") as f:
        f.write("\n".join(urdf_lines))
    
    log(f"\n\n[SUCCESS] Files saved successfully to:")
    log(f"    • Analysis: 👉 {output_txt_path}")
    log(f"    • URDF XML: 👉 {output_urdf_path}")


if __name__ == "__main__":
    parser = ArgumentParser(description="Extract URDF information from trained ScrewSplat Model")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the trained model output directory.")

    args = get_combined_args(parser)
    main(args)
