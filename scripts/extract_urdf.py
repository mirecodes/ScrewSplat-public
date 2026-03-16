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
    def log(msg):
        print(msg)
        output_str.append(msg)

    log(f"Loading Evaluator for Model: {args.model_path}")
    evaluator = Evaluator(args)
    
    screws = evaluator.gaussians.get_screws.detach().cpu().numpy()
    n_screws = len(screws)
    part_indices = evaluator.gaussians.get_part_indices.detach() > 0.5  # Softmax probabilities to boolean masks
    gaussians_xyz = evaluator.gaussians.get_xyz.detach().cpu().numpy()

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

        log(f"\n" + "-"*40)
        log(f"[ Joint {i+1} ]: connecting Link 0 to Link {i+1}")

        # Check type: Revolute if ||w|| > 0.1, Prismatic otherwise
        if np.linalg.norm(w) > 0.1:
            joint_type = "Revolute"
            axis = w / np.linalg.norm(w)
            origin = q
            log(f"    • Type:   {joint_type}")
            log(f"    • Axis:   {axis.round(4)}")
            log(f"    • Origin: {origin.round(4)}")
        else:
            joint_type = "Prismatic"
            # In evaluator/screw logic, w = -v for purely translation, or v is translation axis.
            # Usually v is scaled direction
            v_norm = np.linalg.norm(v)
            if v_norm > 1e-6:
                axis = -v / v_norm  # Because the visualization mesh logic uses -v as axis
            else:
                axis = np.zeros(3)
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

    # Output to file
    translate_dir = os.path.join("translate", object_name)
    os.makedirs(translate_dir, exist_ok=True)
    output_path = os.path.join(translate_dir, "urdf_analysis.txt")
    
    with open(output_path, "w") as f:
        f.write("\n".join(output_str))
    
    log(f"\n\n[SUCCESS] Document saved successfully to: 👉 {output_path}")


if __name__ == "__main__":
    parser = ArgumentParser(description="Extract URDF information from trained ScrewSplat Model")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the trained model output directory.")

    args = get_combined_args(parser)
    main(args)
